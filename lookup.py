"""Look up what I know about a person.

Usage:
    python lookup.py <discord-id>
    python lookup.py <name-or-part-of-name>

Reads my folded notebook first, then the snapshot if it is still there, then
Nyan's live ledger if this machine can see it. Prints one compact block per
match: name, facts, likes, dislikes, interests.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SNAPSHOT = Path("memory/facts.json")
NYAN_LIVE = Path(r"C:\Python\DiscordBotN5\memory\facts.json")
LOCAL = Path("memory/people.json")


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _local_people() -> dict:
    data = _read(LOCAL)
    people_ = data.get("people") if isinstance(data, dict) else None
    return people_ if isinstance(people_, dict) else {}


def _titles(entry: dict, key: str) -> list[str]:
    out = []
    for item in entry.get(key) or []:
        if isinstance(item, dict) and item.get("t"):
            out.append(str(item["t"]))
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    needle = sys.argv[1].strip().lower()

    candidates: dict[str, dict] = {}
    for source in (_local_people(), _read(SNAPSHOT), _read(NYAN_LIVE)):
        for uid, entry in source.items():
            if not isinstance(entry, dict):
                continue
            cand = candidates.setdefault(str(uid), {})
            for key, value in entry.items():
                if key == "facts":
                    continue
                cand.setdefault(key, value)
            facts = cand.setdefault("facts", [])
            seen = {f.get("text") for f in facts if isinstance(f, dict)}
            for item in entry.get("facts") or []:
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or "").strip()
                if text and text not in seen:
                    facts.append(item)
                    seen.add(text)

    matches = []
    for uid, entry in candidates.items():
        name = str(entry.get("custom_name") or "").lower()
        if needle == uid.lower() or (name and needle in name):
            matches.append((uid, entry))

    if not matches:
        print(f"nobody in the ledgers matches '{sys.argv[1]}'")
        return 1

    for uid, entry in matches:
        print(f"{entry.get('custom_name') or uid} ({uid})")
        facts = [f.get("text") for f in entry.get("facts", []) if isinstance(f, dict)]
        if facts:
            print("facts:")
            for f in facts[:12]:
                print(f"  - {f}")
        likes = _titles(entry, "likes")
        if likes:
            print("likes: " + ", ".join(likes[:8]))
        dislikes = _titles(entry, "dislikes")
        if dislikes:
            print("dislikes: " + ", ".join(dislikes[:8]))
        interests = _titles(entry, "interests")
        if interests:
            print("interests: " + ", ".join(interests[:8]))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())