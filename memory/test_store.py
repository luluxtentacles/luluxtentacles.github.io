"""Guards the ranking in store.py.

    python test_store.py

recall() is the only thing between a question and the right memory, and its
failure mode is silent: it returns *a* memory, just the wrong one. Every case
below is either the actual bug that got this written, or a query that already
worked and must keep working. Run this after touching _stem, _tokens or recall.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store  # noqa: E402  (path must be set up first)

# The facts seeded in the real store, so the cases below mean something.
MEMORIES = [
    ("den,house-rules",
     r"The den is C:\Nana, a git repo on branch master. Session notes go in notes\ as "
     r"YYYY-MM-DD-topic.md. House rules: git before editing, ask with numbered options, "
     r"never echo secrets, confirm irreversible actions, report results not process."),
    ("memory,architecture",
     r"One memory, three mouths: C:\Nana\memory\shared.json is written by the GUI and "
     r"Telegram and read by all three faces. The Discord face reads it but never writes; "
     r"Discord memories go to C:\Nana\discord\memory\discord.json."),
    ("persona",
     r"Canonical persona lives at kun\persona\nana.persona.json. Never edit the persona in "
     r"the Kun UI or kun-settings.json; apply overwrites it. sync_persona.py apply refuses "
     r"while Kun.exe is running."),
    ("master",
     r"Master calls me Nana and I call him master. Real projects live outside the den, e.g. "
     r"C:\Python\DiscordBotN5. The den holds habits and knowledge, not product code."),
]

# (query, a substring only the correct memory contains). The first one used to
# return the wrong entry: "where" and "does" scored, and "lives" missed "live".
CASES = [
    ("where does the persona live", "persona"),
    ("what are the house rules", "House rules"),
    ("how do the faces share memory", "three mouths"),
    ("which file does discord write to", "discord"),
    ("who calls who master", "master"),
    ("edit the persona while kun is running", "Kun.exe"),
    ("persona", "persona"),
    ("personas", "persona"),
    ("shared memory store", "three mouths"),
    ("house rules git", "House rules"),
]

# Nothing here is in the store, so recall must return nothing rather than a
# consolation prize. A memory that always answers is worse than none.
NEGATIVES = [
    "photosynthesis chlorophyll chloroplast",
    "kubernetes ingress controller helm chart",
]

STEMS = [
    ("lives", "live"), ("live", "live"), ("memories", "memory"),
    ("rules", "rule"), ("boxes", "box"), ("stopped", "stop"),
    ("ranking", "rank"), ("running", "run"), ("den", "den"),
    ("persona", "persona"), ("git", "git"),
]


def main() -> int:
    failures: list[str] = []

    print("stems")
    for word, expected in STEMS:
        got = store._stem(word)
        ok = got == expected
        print(f"  {'ok ' if ok else 'FAIL'} {word:10} -> {got:10} (expected {expected})")
        if not ok:
            failures.append(f"_stem({word!r}) = {got!r}, expected {expected!r}")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "shared.json"
        for tags, text in MEMORIES:
            store.remember(text, source="test", speaker="Nana", channel="test",
                           tags=tags.split(","), path=path)

        print("\nranking")
        for query, needle in CASES:
            found = store.recall(query, limit=1, path=path)
            got = found[0]["text"] if found else "(nothing)"
            ok = bool(found) and needle.lower() in got.lower()
            print(f"  {'ok ' if ok else 'FAIL'} {query!r}\n        -> {got[:68]}...")
            if not ok:
                failures.append(f"recall({query!r}) expected {needle!r}, got {got[:68]!r}")

        print("\nno false hits")
        for query in NEGATIVES:
            found = store.recall(query, limit=3, path=path)
            ok = not found
            print(f"  {'ok ' if ok else 'FAIL'} {query!r} -> {len(found)} hit(s)")
            if not ok:
                failures.append(f"recall({query!r}) should be empty, got {len(found)}")

        print("\ninvariant: two matching tokens beat one common token")
        # "den" is in 2 of 4 memories and "master" in 1, so the memory holding
        # both must outrank either alone - this is what IDF is for.
        two = store.recall("den master", limit=1, path=path)
        ok = bool(two) and "master calls" in two[0]["text"].lower()
        print(f"  {'ok ' if ok else 'FAIL'} 'den master' -> "
              f"{two[0]['text'][:46] if two else '(nothing)'}...")
        if not ok:
            failures.append("'den master' did not prefer the memory matching both tokens")

    print()
    if failures:
        print(f"FAILED ({len(failures)})")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"all {len(STEMS) + len(CASES) + len(NEGATIVES) + 1} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
