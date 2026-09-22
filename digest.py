"""What happened in each server, written down every few hours.

The channel mirror is RAM only: it holds the last MIRROR_LINES of every room she
can see and it dies on every restart. That is the right shape for answering the
message in front of her and the wrong shape for remembering a week. This module
does the remembering - every `interval_hours` (6 by default) it reads the mirror,
groups what moved by SERVER, has the free Gemini keys summarise it, and appends
the result to today's journal as a marked block.

Master, 2026-09-22: *"we should use a disk mirror to summarise events into
journal every 6 hours so she can know what's been happening in each server"*, and
*"use the gemini keys for this it's not very important, it can loop until
complete."*

Three rules fall out of that, and they ARE the design:

  - **Gemini only**, never the Go rung master pays for. A digest runs on a timer
    whether or not anyone is watching, and nobody's answer depends on it - so it
    is exactly the work that should ride the free ladder. `brain.gemini_complete`
    is that call, and it cannot descend past gemini.
  - **Loop until complete.** The ladder is walked until a rung answers, and a long
    transcript is CHUNKED and summarised piece by piece rather than truncated -
    a summary of the first third of a server's afternoon is a lie told with a
    straight face.
  - **Into the journal**, beside the raw lines, under a `## ` heading so
    `journal.read_digest` can find it again.

Which channel belongs to which server is NOT in the mirror: an entry there is
{id, author, text, reply_to} and the mirror is keyed by channel id alone. The
guild names come from the live guilds at digest time instead, which leaves the hot
path that feeds the mirror untouched.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

import brain
import journal
import paths

LOG = logging.getLogger("lulu")

POLL_SECONDS = 300
DEFAULT_INTERVAL_HOURS = 6.0
STATE_REL = "memory/digest.json"

CHUNK_CHARS = 5000      # transcript handed to one summariser call
MAX_CHUNKS = 8          # a window longer than this is capped, and says so
ATTEMPTS = 3            # full walks of the gemini ladder before giving up
MAX_TOKENS = 1500
CALL_TIMEOUT = 120.0

SYSTEM = (
    "You are writing a short factual digest of recent Discord activity in one "
    "server, for the bot that lives there to read back later. Say what actually "
    "happened: what was being discussed, who said what that mattered, anything "
    "decided, anything left open, anything funny. Two or three short paragraphs "
    "of plain prose. No headings and no bullet lists. Never invent anything - if "
    "the transcript is thin, the digest is short. Quote a line only when the "
    "exact wording is the point."
)


# --------------------------------------------------------------- the schedule
def settings(config) -> dict:
    """`enabled` and `interval_hours`, read from config.json's `digest` block."""
    raw = (config or {}).get("digest") or {}
    if not isinstance(raw, dict):
        raw = {}
    try:
        hours = float(raw.get("interval_hours", DEFAULT_INTERVAL_HOURS))
    except (TypeError, ValueError):
        hours = DEFAULT_INTERVAL_HOURS
    if hours <= 0:
        hours = DEFAULT_INTERVAL_HOURS
    return {"enabled": bool(raw.get("enabled")), "interval_hours": hours}


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _state() -> dict:
    try:
        data = paths.read_json(STATE_REL, default=None)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(**fields) -> None:
    data = _state()
    data.update(fields)
    try:
        paths.write_json(STATE_REL, data, internal=True)
    except Exception as exc:
        LOG.warning("could not stamp the digest state: %s", exc)


def due(config, now=None) -> bool:
    """Is a digest owed? Its interval has passed, or it has never run."""
    where = settings(config)
    if not where["enabled"]:
        return False
    moment = time.time() if now is None else now
    last = _state().get("last_run")
    if isinstance(last, bool) or not isinstance(last, (int, float)):
        return True
    return moment - last >= where["interval_hours"] * 3600


# ------------------------------------------------------------------ capturing
def channel_names(bot) -> dict:
    """channel id -> (server name, channel name), from the live guilds.

    Deliberately not from the mirror: a mirror entry carries no guild and the
    mirror is keyed by channel id alone. She is IN these guilds, so the names are
    already in hand - and asking here costs the message path nothing.
    """
    out: dict[int, tuple[str, str]] = {}
    for guild in getattr(bot, "guilds", None) or []:
        server = str(getattr(guild, "name", "") or "a server")
        for channel in getattr(guild, "text_channels", None) or []:
            try:
                out[int(channel.id)] = (
                    server, str(getattr(channel, "name", "") or "a channel"))
            except (TypeError, ValueError):
                continue
    return out


def _after(rows: list, last_id):
    """The entries newer than the watermark.

    A watermark that is no longer in the ring (200 lines is a real bound on a busy
    channel) means the WHOLE ring is taken. Re-summarising an afternoon beats a
    silently missing one.
    """
    if last_id is None:
        return list(rows)
    for index, entry in enumerate(rows):
        if entry.get("id") == last_id:
            return list(rows[index + 1:])
    return list(rows)


def collect(mirror, names, seen) -> tuple[dict, dict]:
    """New lines since the last digest, grouped by SERVER. -> (by_server, seen).

    Read-only against the mirror on purpose: it is a defaultdict, so touching
    `mirror[channel_id]` for a channel that has gone quiet would CREATE an entry
    and grow her memory every pass.
    """
    out: dict[str, list[str]] = {}
    fresh: dict = dict(seen or {})
    for channel_id, entries in (mirror or {}).items():
        rows = [entry for entry in entries if (entry or {}).get("text")]
        if not rows:
            continue
        key = str(channel_id)
        lines = _after(rows, (seen or {}).get(key))
        newest = next((entry.get("id") for entry in reversed(rows)
                       if entry.get("id")), None)
        if newest:
            fresh[key] = newest
        if not lines:
            continue
        server, channel = names.get(channel_id, ("a server", f"channel-{channel_id}"))
        for entry in lines:
            author = str(entry.get("author") or "someone").strip()
            out.setdefault(server, []).append(f"[#{channel}] {author}: {entry['text']}")
    return out, fresh


# --------------------------------------------------------------- summarising
def render(lines) -> str:
    return "\n".join(str(line) for line in lines)


def chunk(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Split on line boundaries, so a chunk never cuts a message in half.

    A window longer than MAX_CHUNKS is capped IN WORDS: the last piece says the
    rest was dropped. Silent truncation is the one thing this must not do.
    """
    pieces: list[str] = []
    current = ""
    for line in text.split("\n"):
        if current and len(current) + len(line) + 1 > size:
            pieces.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        pieces.append(current)
    if len(pieces) > MAX_CHUNKS:
        pieces = pieces[:MAX_CHUNKS]
        pieces[-1] += "\n[... the rest of this window was too long to summarise ...]"
    return pieces or [""]


def _ask(config, server: str, piece: str, part_note: str) -> str:
    """One summariser call, looping the gemini ladder until a rung answers."""
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Server: {server}{part_note}\n\n"
                                    f"Recent activity:\n{piece}"},
    ]
    for _ in range(max(1, ATTEMPTS)):
        text = brain.gemini_complete(config, messages, max_tokens=MAX_TOKENS,
                                     temperature=0.3, timeout=CALL_TIMEOUT)
        if text:
            return text
    return ""


def summarise(config, server: str, lines) -> str:
    """One server's digest. Chunked if long; "" when every rung was dry."""
    transcript = render(lines)
    if not transcript.strip():
        return ""
    pieces = chunk(transcript)
    parts = []
    for index, piece in enumerate(pieces, 1):
        note = f" (part {index} of {len(pieces)})" if len(pieces) > 1 else ""
        text = _ask(config, server, piece, note)
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def body(summaries: dict) -> str:
    """The journal block: one bold server name, then its digest."""
    return "\n\n".join(f"**{server}**\n\n{text}"
                       for server, text in summaries.items())


# ------------------------------------------------------------------ the loop
async def maybe_run(bot) -> bool:
    """One digest, if one is owed. True when it actually wrote something."""
    config = getattr(bot, "config", None) or {}
    if not due(config):
        return False
    mirror = getattr(bot, "mirror", None)
    if not mirror:
        return False

    state = _state()
    grouped, fresh = collect(mirror, channel_names(bot), state.get("seen") or {})
    if not grouped:
        # Nothing moved, but the clock did. Stamped anyway, or the poll would ask
        # the same empty question every five minutes until something happened.
        _save(last_run=time.time(), last_run_iso=_stamp(), seen=fresh)
        return False

    summaries: dict[str, str] = {}
    for server, lines in grouped.items():
        # Off the event loop: the ladder walk is blocking HTTP, and her reply
        # path must not wait behind a digest.
        text = await asyncio.to_thread(summarise, config, server, lines)
        if text:
            summaries[server] = text

    if summaries:
        journal.note_digest(body(summaries),
                            label=f"server digest - {len(summaries)} server(s)")
        LOG.info("digest written: %d server(s)", len(summaries))
    _save(last_run=time.time(), last_run_iso=_stamp(), seen=fresh)
    return bool(summaries)


async def watch(bot) -> None:
    """Poll forever. Free and idle until a digest is actually owed."""
    while True:
        try:
            await maybe_run(bot)
        except Exception as exc:
            LOG.warning("digest pass failed: %s", exc)
        await asyncio.sleep(POLL_SECONDS)
