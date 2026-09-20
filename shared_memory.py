"""Discord's memory: the shared store is read-only here; ours gets its own file.

Two files, deliberately.

  C:\\Lulu\\memory\\shared.json          read-only. All three faces read it, so
                                         Discord may look but never write.
  C:\\Lulu\\discord\\memory\\discord.json  writable. What the Discord face learns,
                                         kept in a Discord file, inside the wall.

The den's store.py is imported rather than reimplemented - one memory format,
no drift between faces, and it brings the cross-process lock with it (the GUI
also writes the Discord file when master updates it from here).

The one thing this module does outside the wall is READ the den's memory
directory, which master authorized explicitly. Writes never go outward.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import paths

DEN_MEMORY = Path(r"C:\Lulu\memory")
SHARED_PATH = DEN_MEMORY / "shared.json"
LOCAL_REL = "memory/discord.json"

MAX_ENTRIES = 2000
RECALL_LIMIT = 8
RECALL_CHARS = 2400

# Shared memory is read by my other faces, so it must never become a place a
# secret can land. Masking happens here rather than at the call sites so no
# future caller can forget it.
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),                    # openrouter/opencode keys
    # Discord bot tokens vary by generation (this one is 26/6/38). Never pin exact
    # widths - a pattern that misses is worse than no pattern at all.
    re.compile(r"\b[A-Za-z0-9_\-]{23,30}\.[A-Za-z0-9_\-]{5,8}\.[A-Za-z0-9_\-]{25,45}\b"),
    re.compile(r"\b\d{8,20}:[A-Za-z0-9_\-]{30,}\b"),           # telegram bot token
    re.compile(r"\bBearer\s+\S{8,}", re.I),                    # bearer auth header
    re.compile(r"\b[A-Za-z0-9_\-]{40,}\b"),                    # long opaque blobs
)

if not (DEN_MEMORY / "store.py").exists():
    raise RuntimeError(f"shared memory store missing at {DEN_MEMORY / 'store.py'}")
if str(DEN_MEMORY) not in sys.path:
    sys.path.insert(0, str(DEN_MEMORY))

import store  # noqa: E402  (path must be set up first)


def redact(text: str) -> str:
    """Mask anything credential-shaped before it can be stored."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    return text


def local_path() -> Path:
    return paths.resolve(LOCAL_REL)


def remember(text: str, *, speaker: str = "Lulu", channel: str = "discord") -> None:
    """Record one line in the DISCORD file. Never the shared one."""
    text = redact((text or "").strip())
    if not text or text == "[redacted]":
        return
    store.remember(text, source="discord", speaker=speaker,
                   channel=channel, path=local_path())


def _shared_entries(query: str, limit: int) -> list[dict]:
    """Best-effort read of the shared store. A bad file must not break a reply."""
    try:
        return store.recall(query, limit=limit, path=SHARED_PATH)
    except Exception:
        return []


def search(query: str, limit: int = RECALL_LIMIT) -> list[dict]:
    """What I know: my own memories first, then what the other faces learned."""
    try:
        mine = store.recall(query, limit=limit, path=local_path())
    except Exception:
        mine = []
    seen = {e.get("id") or e.get("text") for e in mine}
    others = [e for e in _shared_entries(query, limit)
              if (e.get("id") or e.get("text")) not in seen]
    return (mine + others)[:limit]


def context_block(query: str) -> str:
    """What I already know, ready to drop into the prompt."""
    return store.format_for_prompt(search(query))[:RECALL_CHARS]


def recent(limit: int = 15) -> list[dict]:
    """The newest memories, mine and the shared store's, newest last.

    Query-free, so it works in windows where there is no question yet - this
    is how a freetime window learns what people were talking about today
    without being handed a whole channel mirror.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for entries in (store.tail(limit, path=local_path()),
                    store.tail(limit, path=SHARED_PATH)):
        for entry in entries:
            key = entry.get("id") or entry.get("text") or ""
            if key and key not in seen:
                seen.add(key)
                out.append(entry)
    return out[-limit:]
