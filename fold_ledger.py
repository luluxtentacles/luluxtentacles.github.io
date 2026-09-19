"""Fold Nyan's ledger snapshot into my own notebook.

Reads memory/facts.json (the copy master dropped in my wall), merges every
person into memory/people.json, and reports what changed. Run it once; after
it comes back clean you can delete memory/facts.json safely.

Usage:
    python fold_ledger.py            # fold only, keep the snapshot
    python fold_ledger.py --delete   # fold, then remove the snapshot
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import paths

SNAPSHOT = "memory/facts.json"
LOCAL = "memory/people.json"

# My notebook caps per-person facts lower when learning live. For the fold we
# keep the tail (the newest ones - her facts are appended over time, so cutting
# the tail would drop the recent stuff).
MAX_FACTS_PER_PERSON = 100


def _load(relative: str, default):
    try:
        data = json.loads(paths.resolve(relative).read_text(encoding="utf-8"))
        return data if data is not None else default
    except Exception:
        return default


def main() -> int:
    snapshot = _load(SNAPSHOT, None)
    if not isinstance(snapshot, dict) or not snapshot:
        print(f"nothing to fold: {SNAPSHOT} missing, empty, or not a dict")
        return 1

    local = _load(LOCAL, {"version": 1, "people": {}})
    if not isinstance(local, dict):
        local = {"version": 1, "people": {}}
    people_ = local.setdefault("people", {})
    if not isinstance(people_, dict):
        people_ = {}
        local["people"] = people_

    now = time.strftime("%Y-%m-%d %H:%M")
    touched = 0
    added_names = 0
    added_facts = 0

    for uid, entry in snapshot.items():
        if not isinstance(entry, dict):
            continue
        mine = people_.get(uid)
        if not isinstance(mine, dict):
            mine = {}
            people_[uid] = mine

        name = str(entry.get("custom_name") or "").strip()
        if name and not str(mine.get("custom_name") or "").strip():
            mine["custom_name"] = name
            added_names += 1

        facts = mine.get("facts")
        if not isinstance(facts, list):
            facts = []
            mine["facts"] = facts
        existing = {f.get("text") for f in facts if isinstance(f, dict)}

        for item in entry.get("facts") or []:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text or text in existing:
                continue
            facts.append({
                "text": text[:500],
                "at": now,
                "source": "nyan-fold",
            })
            existing.add(text)
            added_facts += 1
        facts[:] = facts[-MAX_FACTS_PER_PERSON:]

        # likes/dislikes/interests ride along in my entry so the standalone
        # lookup can still show them after the snapshot is gone. people.py's
        # runtime merge ignores them for now - that is for the daily prompt.
        for key in ("likes", "dislikes", "interests"):
            items = entry.get(key)
            if isinstance(items, list) and items:
                mine[key] = items

        touched += 1

    local["version"] = 1
    paths.write_json(LOCAL, local, internal=True)

    print(f"folded {touched} people from {SNAPSHOT}")
    print(f"  custom names added: {added_names}")
    print(f"  facts added: {added_facts}")
    print(f"  my ledger now holds {len(people_)} people")

    if "--delete" in sys.argv:
        try:
            paths.resolve(SNAPSHOT).unlink()
            print(f"deleted {SNAPSHOT}")
        except FileNotFoundError:
            print(f"already gone: {SNAPSHOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())