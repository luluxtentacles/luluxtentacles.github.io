"""One memory, three mouths.

The GUI, Telegram and Discord all read and write this file, so Nana knows the
same things whichever face is talking.

Plain JSON on purpose: anything can inspect it, including a shell `cat` in the
middle of a conversation. Writes are read-modify-write under a lock file and
land atomically, because three processes can reach this at once.

CLI:
    python store.py add --source discord --speaker Tentacles --text "hello"
    python store.py recall --query "nana look" --limit 5
    python store.py tail --limit 10
    python store.py stats
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "shared.json"
LOCK_TIMEOUT = 10.0
LOCK_STALE_AFTER = 30.0
MAX_TEXT = 4000
RECALL_LIMIT = 8

# Words that carry no topic signal.
#
# Question words and auxiliaries matter most here. "where does the persona live"
# used to rank on "where" and "does", so it tied the persona's own memory at 1
# and recency handed back the wrong entry. Anything a memory is *about* must
# survive this set; everything that only asks about it must not.
_STOPWORDS = {
    # articles and determiners
    "a", "an", "the", "this", "that", "these", "those", "such", "same",
    # pronouns
    "i", "i'm", "me", "my", "mine", "you", "your", "yours", "you're",
    "we", "our", "us", "they", "them", "their", "he", "him", "his",
    "she", "her", "hers", "it", "its", "it's", "who", "whom", "whose",
    "which", "what", "someone", "anyone", "everyone", "nobody", "something",
    "anything", "everything", "nothing",
    # auxiliaries and modals
    "am", "is", "are", "was", "were", "be", "been", "being", "do",
    "does", "did", "doing", "done", "have", "has", "had", "having",
    "will", "would", "shall", "should", "can", "could", "may", "might",
    "must", "let", "lets",
    # interrogatives and connectives
    "how", "when", "where", "why", "whether", "if", "then", "than", "and",
    "or", "but", "not", "no", "yes", "never", "so", "because", "as",
    "also", "too", "just", "only", "even", "still", "again", "ever",
    "here", "there", "more", "most", "less", "least", "many", "much",
    "few", "other", "others", "another",
    # prepositions
    "of", "in", "on", "at", "to", "by", "for", "with", "without",
    "from", "into", "onto", "about", "over", "under", "up", "down",
    "out", "off", "through", "between", "against", "after", "before",
    "during", "around",
    # vague verbs and quantifiers that appear in almost every memory
    "get", "got", "go", "goes", "going", "make", "makes", "made", "take",
    "takes", "took", "want", "wants", "wanted", "need", "needs", "needed",
    "know", "knows", "knew", "think", "thinks", "say", "says", "said",
    "see", "sees", "saw", "one", "ones", "all", "any", "some", "each",
    "every", "both",
}

_VOWELS = set("aeiou")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class _Lock:
    """Cross-process mutual exclusion via an O_EXCL lock file."""

    def __init__(self, db_path: Path, timeout: float = LOCK_TIMEOUT):
        self.lock_path = Path(str(db_path) + ".lock")
        self.timeout = timeout
        self.fd: int | None = None

    def __enter__(self):
        deadline = time.monotonic() + self.timeout
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        while True:
            try:
                self.fd = os.open(self.lock_path,
                                  os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, f"{os.getpid()}".encode())
                return self
            except FileExistsError:
                if self._is_stale():
                    self._break()
                    continue
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"memory lock held too long: {self.lock_path}")
                time.sleep(0.05)

    def _is_stale(self) -> bool:
        try:
            return (time.time() - self.lock_path.stat().st_mtime) > LOCK_STALE_AFTER
        except OSError:
            return False

    def _break(self) -> None:
        # A crashed writer must not wedge every future write.
        try:
            self.lock_path.unlink()
        except OSError:
            pass

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self._break()
        return False


# Public handle: the diary writes to its own files but needs the same
# cross-process lock, and must not fork a second implementation of it.
file_lock = _Lock


def _load(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Never lose an existing file to a parse error - park it and start clean.
        broken = path.with_suffix(f".corrupt-{int(time.time())}.json")
        try:
            path.replace(broken)
        except OSError:
            pass
        return {"version": 1, "entries": []}
    data.setdefault("entries", [])
    return data


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _stem(word: str) -> str:
    """Crude, consistent suffix stripper - for matching only, never for display.

    Consistency beats linguistic correctness. "lives" and "live" only have to
    land on the same string; that they land on an ugly one is irrelevant. Do
    not "improve" this into a real stemmer, and never print its output.
    """
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"                       # memories -> memory
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        if word.endswith(("sses", "shes", "ches", "xes", "zes")):
            return word[:-2]                         # boxes -> box
        return word[:-1]                             # rules -> rule
    for suffix in ("ing", "ed"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            stem = word[: -len(suffix)]
            if len(stem) > 3 and stem[-1] == stem[-2] and stem[-1] not in _VOWELS:
                stem = stem[:-1]                     # stopped -> stop
            return stem
    return word


def _tokens(text: str) -> set[str]:
    """The topic words in `text`: stopword-filtered, crudely stemmed."""
    words = re.findall(r"[a-z0-9']+", text.lower())
    out = set()
    for word in words:
        if len(word) <= 2 or word in _STOPWORDS:
            continue
        stem = _stem(word)
        if len(stem) > 2 and stem not in _STOPWORDS:
            out.add(stem)
    return out


def remember(text: str, *, source: str, speaker: str = "",
             channel: str = "", tags: list[str] | None = None,
             path: Path = DEFAULT_PATH) -> dict:
    """Append one memory and return it."""
    text = (text or "").strip()[:MAX_TEXT]
    if not text:
        raise ValueError("refusing to store an empty memory")
    entry = {
        "id": f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid() % 1000:03d}",
        "at": now_iso(),
        "source": source,
        "speaker": speaker,
        "channel": channel,
        "text": text,
        "tags": tags or [],
    }
    with _Lock(path):
        data = _load(path)
        data["entries"].append(entry)
        _save(path, data)
    return entry


def recall(query: str = "", *, limit: int = RECALL_LIMIT,
           sources: list[str] | None = None,
           path: Path = DEFAULT_PATH) -> list[dict]:
    """Most relevant memories: most matching topic words, then the rarest.

    Score is the sum of smooth-IDF weights over the matched tokens, so a word
    that appears in every memory counts for almost nothing while a distinctive
    one carries the ranking. Matching two tokens always beats matching one,
    however common that one is. Recency only breaks exact ties.
    """
    data = _load(path)
    entries = data["entries"]
    if sources:
        entries = [e for e in entries if e.get("source") in sources]
    if not query.strip():
        return entries[-limit:]

    wanted = _tokens(query)
    if not wanted:
        return entries[-limit:]

    document_tokens = [_tokens(e.get("text", "")) for e in entries]

    # Document frequency per token is what makes a rare word outrank a common one.
    frequency: dict[str, int] = {}
    for tokens in document_tokens:
        for token in tokens:
            frequency[token] = frequency.get(token, 0) + 1

    total = len(entries)
    scored = []
    for index, (entry, tokens) in enumerate(zip(entries, document_tokens)):
        matched = wanted & tokens
        if not matched:
            continue
        weight = sum(math.log((total + 1) / (frequency.get(t, 0) + 1)) + 1.0
                     for t in matched)
        scored.append((weight, index, entry))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [entry for _, _, entry in scored[:limit]]


def tail(limit: int = 10, *, path: Path = DEFAULT_PATH) -> list[dict]:
    return _load(path)["entries"][-limit:]


def stats(path: Path = DEFAULT_PATH) -> dict:
    entries = _load(path)["entries"]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.get("source", "?")] = counts.get(entry.get("source", "?"), 0) + 1
    return {
        "path": str(path),
        "total": len(entries),
        "by_source": counts,
        "first": entries[0]["at"] if entries else None,
        "last": entries[-1]["at"] if entries else None,
    }


def format_for_prompt(entries: list[dict]) -> str:
    """Render memories as a system block, or '' when there is nothing to say."""
    if not entries:
        return ""
    lines = [
        "[shared memory]",
        "Things you already know, from your other conversations. Not new input - "
        "context. Do not thank anyone for it.",
    ]
    for entry in entries:
        who = entry.get("speaker") or entry.get("source", "?")
        when = str(entry.get("at", ""))[:16].replace("T", " ")
        lines.append(f"- [{when}] ({entry.get('source','?')}/{who}) {entry.get('text','')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nana's shared memory store")
    parser.add_argument("--path", default=str(DEFAULT_PATH))
    sub = parser.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add")
    add.add_argument("--text", required=True)
    add.add_argument("--source", default="gui")
    add.add_argument("--speaker", default="")
    add.add_argument("--channel", default="")
    add.add_argument("--tags", default="")

    rec = sub.add_parser("recall")
    rec.add_argument("--query", default="")
    rec.add_argument("--limit", type=int, default=RECALL_LIMIT)
    rec.add_argument("--sources", default="")
    rec.add_argument("--prompt", action="store_true",
                     help="render as the system block instead of JSON")

    tl = sub.add_parser("tail")
    tl.add_argument("--limit", type=int, default=10)

    sub.add_parser("stats")

    args = parser.parse_args(argv)
    path = Path(args.path)

    if args.cmd == "add":
        entry = remember(args.text, source=args.source, speaker=args.speaker,
                         channel=args.channel,
                         tags=[t for t in args.tags.split(",") if t], path=path)
        print(json.dumps(entry, ensure_ascii=False))
    elif args.cmd == "recall":
        found = recall(args.query, limit=args.limit,
                       sources=[s for s in args.sources.split(",") if s] or None,
                       path=path)
        print(format_for_prompt(found) if args.prompt
              else json.dumps(found, indent=2, ensure_ascii=False))
    elif args.cmd == "tail":
        print(json.dumps(tail(args.limit, path=path), indent=2, ensure_ascii=False))
    elif args.cmd == "stats":
        print(json.dumps(stats(path), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
