"""What happened in each server, written down every few hours.

The channel mirror is RAM only: it holds the last MIRROR_LINES of every room she
can see and it dies on every restart. That is the right shape for answering the
message in front of her and the wrong shape for remembering a week. This module
does the remembering - every `interval_hours` (24 by default) it reads the OLDEST
slice of the DISK mirror, groups it by SERVER, has the free Gemini keys summarise
it, and appends the result to today's journal as a marked block.

WHY THE OLDEST SLICE AND NOT THE NEWEST. Master, 2026-09-22: *"disk mirror should
hold 48 hours, and then we should summarise the oldest 24 hours into journal every
24 hours"*. The mirror keeps 48 hours of raw; the newest 24 of those are still
fresh in front of her, so summarising them buys nothing. What needs saving is the
24-to-48-hour-old half, because that is the half that ages out of the mirror next.
Each pass therefore covers [now - MIRROR_WINDOW_HOURS, now - interval_hours], so a
line is written down before it is pruned and never falls off the end unrecorded -
see `_archive_window`.

Master, 2026-09-22: *"we should use a disk mirror to summarise events into
journal every 6 hours so she can know what's been happening in each server"*, and
*"use the gemini keys for this it's not very important, it can loop until
complete."*

Three rules fall out of that, and they ARE the design:

  - **Free rungs only** - the Gemini keys, then OpenRouter's free models -
    never the Go rung master pays for. A digest runs on a timer whether or not
    anyone is watching, and nobody's answer depends on it, so it is exactly the
    work that should ride the free ladder. `brain.free_complete` is that call and
    cannot reach Go at all. Master, 2026-09-22: *"all gemini and openrouter free
    only"*.
  - **Retry until it lands.** A pass that cannot summarise every server in its
    window HOLDS that window and does not advance the watermark, so the next poll
    - five minutes later - walks the whole free ladder again. Master, 2026-09-22:
    *"which continues to retry models every 5 minutes until success"*.
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
from datetime import datetime, timedelta

import brain
import journal
import paths

LOG = logging.getLogger("lulu")

POLL_SECONDS = 300
DEFAULT_INTERVAL_HOURS = 6.0
STATE_REL = "memory/digest.json"

CHUNK_CHARS = 5000      # transcript handed to one summariser call
MAX_CHUNKS = 8          # a window longer than this is capped, and says so
ATTEMPTS = 3            # full walks of the FREE ladder per chunk before giving up
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
def _window_days(since: datetime | None,
                 until: datetime | None = None) -> list[str]:
    """Which mirror day files a window can touch, oldest first."""
    days = [journal.shift(journal.today(), -offset)
            for offset in range(journal.MIRROR_KEEP_DAYS - 1, -1, -1)]
    if since is not None:
        cut = since.strftime("%Y-%m-%d")
        days = [day for day in days if day >= cut]
    if until is not None:
        cap = until.strftime("%Y-%m-%d")
        days = [day for day in days if day <= cap]
    return days


def _in_range(day: str, at: str, since: datetime | None,
              until: datetime | None = None) -> bool:
    """Is this line inside the window? Unreadable stamps are KEPT.

    Dropping a line because its own stamp would not parse is how a digest gets a
    silent hole in it; the mirror only ever writes HH:MM, so a bad stamp means
    something changed, and re-summarising one line beats losing it.

    Both ends matter now. The archive window is a SLICE - [now-48h, now-24h] - not
    everything since a bookmark, so a line that is merely too RECENT is as much
    outside it as one that is too old. That is the rule: the newest day is left
    alone because she can still see it for herself.
    """
    if since is None and until is None:
        return True
    try:
        when = datetime.strptime(f"{day} {at}", "%Y-%m-%d %H:%M")
    except ValueError:
        return True
    if since is not None and when < since.replace(second=0, microsecond=0):
        return False
    if until is not None and when > until:
        return False
    return True


def collect(since: datetime | None = None,
            until: datetime | None = None) -> dict[str, list[str]]:
    """Every mirror line since `since`, grouped by SERVER, read OFF DISK.

    Master, 2026-09-22: *"we need to have a disk stored one that survives
    restarts, not just ram"*. The first cut of this read the RAM ring, which dies
    on every bounce - so a 24-hourly digest on a bot that restarts would lose most
    of the day and never know it had. The mirror on disk is already per server and
    already rolling, so the digest reads THAT.

    `since` and `until` are TIMES here, not message ids: the disk lines carry a
    stamp and no ids at all. A server with nothing in the slice simply has no key,
    which is the honest answer - the caller summarises what exists and does not
    invent the rest.
    """
    out: dict[str, list[str]] = {}
    # One read of the slug -> display map for the whole pass. The folders are
    # slugs because a name may not be a path; the digest summarises under the name
    # a PERSON recognises, because that is what server_summary matches a room
    # against later. `server-one` in a weekly file is a summary nobody can ever
    # look up again.
    names = journal.server_index()
    for day in _window_days(since, until):
        for server, at, where, rest in journal.mirror_entries_all(day):
            if not _in_range(day, at, since, until):
                continue
            out.setdefault(names.get(server) or server, []).append(
                f"{where} {rest}")
    return out


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
    """One summariser call on the FREE ladder - gemini keys, then openrouter.

    Never the Go rung: see brain.free_complete. `tries` sweeps the whole free
    ladder ATTEMPTS times back to back for a rung that answers on a second
    sweep; a chunk that still comes back empty is the CALLER's problem, because
    the retry that matters happens a level up - summarise() reports the failure
    and maybe_run() retries the whole window on the next poll.
    """
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Server: {server}{part_note}\n\n"
                                    f"Recent activity:\n{piece}"},
    ]
    return brain.free_complete(config, messages, max_tokens=MAX_TOKENS,
                               temperature=0.3, timeout=CALL_TIMEOUT,
                               tries=ATTEMPTS)


def summarise(config, server: str, lines) -> str:
    """One server's digest. Chunked if long; "" when ANY chunk came back dry.

    ALL-OR-NOTHING per server, and that is the point. This used to keep the
    chunks that answered and drop the rest - a summary of two thirds of an
    afternoon wearing the shape of a summary of all of it, which is the exact
    class of silent hole this module keeps having to fix. Master, 2026-09-22:
    retry "every 5 minutes until success", so an incomplete digest reports
    failure and maybe_run() holds the window for the next pass instead of
    writing down half a day as if it were the day.
    """
    transcript = render(lines)
    if not transcript.strip():
        return ""
    pieces = chunk(transcript)
    parts = []
    for index, piece in enumerate(pieces, 1):
        note = f" (part {index} of {len(pieces)})" if len(pieces) > 1 else ""
        text = _ask(config, server, piece, note)
        if not text:
            LOG.warning("digest: %s part %d/%d came back dry - holding the "
                        "window for the next pass", server, index, len(pieces))
            return ""
        parts.append(text)
    return "\n\n".join(parts)


def body(summaries: dict) -> str:
    """The journal block: one bold server name, then its digest."""
    return "\n\n".join(f"**{server}**\n\n{text}"
                       for server, text in summaries.items())


# ------------------------------------------------------------------ the loop
def _archive_window(where) -> tuple[datetime, datetime]:
    """The slice this pass summarises: the OLDEST `interval_hours` of the mirror.

    Master, 2026-09-22: *"disk mirror should hold 48 hours, and then we should
    summarise the oldest 24 hours into journal every 24 hours"*. So the window is
    measured from NOW rather than from the last run: the newest `interval` hours
    are skipped because they are still in front of her, and the slice that ages
    out next is the one that gets written down.

    A fixed lag rather than a bookmark, deliberately - a bookmark can be lost (a
    fresh state file, a restored backup) and would then re-summarise the whole
    mirror, while the clock can only ever point at one slice. `span` comes from
    MIRROR_WINDOW_HOURS so the two cannot drift: change the retention and this
    window follows it instead of quietly summarising a slice that no longer exists.

    On a bot younger than the window there is simply no material this old yet, so
    the pass writes nothing - the honest answer, not an error.
    """
    now = datetime.now()
    span = float(journal.MIRROR_WINDOW_HOURS)
    lag = max(1.0, float(where["interval_hours"]))
    return (now - timedelta(hours=span),
            now - timedelta(hours=max(0.0, span - lag)))


def _window(state: dict, where) -> tuple[datetime, datetime]:
    """The window this pass summarises: the LAST UNFINISHED one, or a fresh slice.

    Sticky on purpose. A window that could not be fully summarised has to be
    retried EXACTLY, not slid forward - a moving window would re-summarise the
    servers that already succeeded (a second digest block for the same day) while
    the one that failed drifted quietly out of range. So the slice is written into
    the state while it is in progress and only released once every server in it
    has been written.

    Master, 2026-09-22: retry *"every 5 minutes until success"*. The poll is five
    minutes (POLL_SECONDS), and because a failed pass does not advance
    `last_run`, `due()` stays true and that retry IS the next poll.
    """
    saved = state.get("window") or {}
    try:
        return (datetime.fromisoformat(str(saved.get("since"))),
                datetime.fromisoformat(str(saved.get("until"))))
    except (TypeError, ValueError):
        return _archive_window(where)


async def maybe_run(bot) -> bool:
    """One digest, if one is owed. True when it actually wrote something.

    Reads the DISK mirror now, not the RAM ring - master, 2026-09-22: *"we need to
    have a disk stored one that survives restarts, not just ram"*. The window is
    therefore a TIME rather than a set of message ids, and a restart in the middle
    of the day costs nothing: the lines are still in the files, and the watermark
    is the clock.
    """
    config = getattr(bot, "config", None) or {}
    if not due(config):
        return False

    where = settings(config)
    state = _state()
    since, until = _window(state, where)
    done = set(state.get("done") or [])
    grouped = {server: lines for server, lines in collect(since, until).items()
               if server not in done}
    if not grouped:
        # Nothing moved, or every server in this window is already written.
        # Stamped either way, or the poll would ask the same question forever.
        _save(last_run=time.time(), last_run_iso=_stamp(), window={}, done=[])
        return False

    summaries: dict[str, str] = {}
    failed: list[str] = []
    for server, lines in grouped.items():
        # Off the event loop: the ladder walk is blocking HTTP, and her reply
        # path must not wait behind a digest.
        text = await asyncio.to_thread(summarise, config, server, lines)
        if text:
            summaries[server] = text
            done.add(server)
        else:
            failed.append(server)

    if summaries:
        journal.note_digest(body(summaries),
                            label=f"server digest - {len(summaries)} server(s)")
        LOG.info("digest written: %d server(s)", len(summaries))

    if failed:
        # HOLD the window and do NOT stamp last_run. due() stays true, so the
        # poll returns in POLL_SECONDS and walks the whole free ladder again -
        # and the servers already written are skipped via `done`, so a retry can
        # never write the same day's digest twice.
        _save(window={"since": since.isoformat(), "until": until.isoformat()},
              done=sorted(done))
        LOG.warning("digest: %d server(s) still dry (%s) - retrying in %ds",
                    len(failed), ", ".join(failed), POLL_SECONDS)
        return bool(summaries)

    _save(last_run=time.time(), last_run_iso=_stamp(), window={}, done=[])
    return bool(summaries)


# ----------------------------------------------------- the weekly roll-up
# Master, 2026-09-22: *"she should also summarize the events in each server every
# 24 hours and keep a server summary each week"*.
#
# The rolling half already runs: this module has digested every server on
# `interval_hours` since 2026-09-22 - 24 now, over the oldest day of the 48h
# mirror (see `_archive_window`). What did not exist was the WEEK. A week of
# six-hourly blocks is a dozen separate accounts of the same rooms and NOTHING
# ever condensed them, so what survived a month was volume. So once a week the
# week that just ended is rolled into one
# account per server at memory/digest/<week>.md.
#
# Same ladder rule as the six-hourly pass, for the same reason: nobody's answer
# depends on this, so it rides the free gemini rungs and never the Go rung master
# pays for.
WEEK_SYSTEM = (
    "You are condensing a week of per-server Discord digests into one short "
    "account of ONE server, for the bot that lives there to read back later. Give "
    "one short plain paragraph: what that server was actually about this week, "
    "what changed, anything decided, anything left open, anything worth "
    "remembering. Plain prose, no headings, no bullet lists, and do NOT name any "
    "other server or describe anything outside the material you were given. Never "
    "invent anything, and if the week was thin, say that in one line."
)


def week_target() -> str | None:
    """The finished week that wants rolling up, or None when nothing is owed."""
    week = journal.prev_week(journal.week_of())
    if not week or journal.week_digest_written(week):
        return None
    if not journal.digest_week_material(week).strip():
        return None
    return week


def summarise_week(config, week: str) -> dict:
    """One account per server for a whole week -> {server: text}.

    On the FREE ladder (brain.free_complete), like the daily pass - nobody's
    answer depends on a roll-up, so it must never spend the rung master pays for.
    ALL-OR-NOTHING: an empty dict when any server or chunk failed, so maybe_week
    writes nothing and the next poll retries the week. Master, 2026-09-22: retry
    "every 5 minutes until success".

    Per server, and not one blob, because the result is read back with a
    per-server filter: a room may hear its own server's summary and no other. If
    the model wrote the whole week as one piece of prose, that boundary would
    have to be guessed from its formatting, which is not a boundary at all. So
    the CODE decides where one server ends and the next begins here, and the
    model only ever writes the middle of a section.
    """
    by_server = journal.digest_week_by_server(week)
    if not by_server:
        by_server = {"(unnamed server)": journal.digest_week_material(week)}
    out: dict[str, str] = {}
    for server, material in by_server.items():
        if not material.strip():
            continue
        pieces = chunk(material)
        parts = []
        for index, piece in enumerate(pieces, 1):
            note = f" (part {index} of {len(pieces)})" if len(pieces) > 1 else ""
            messages = [
                {"role": "system", "content": WEEK_SYSTEM},
                {"role": "user", "content": f"Server: {server}{note}\n\n"
                                            f"That server's week:\n{piece}"},
            ]
            text = brain.free_complete(config, messages, max_tokens=MAX_TOKENS,
                                       temperature=0.3, timeout=CALL_TIMEOUT,
                                       tries=ATTEMPTS)
            if not text:
                # Same rule as the daily pass: a piece that does not answer
                # fails the WHOLE week, so nothing is written and the next poll
                # tries again. Writing the servers that answered would mark the
                # week done and quietly bury the one that did not - a week with
                # a hole in it reads exactly like a week without one.
                LOG.warning("week roll-up: %s part %d/%d came back dry - holding "
                            "week %s for the next pass",
                            server, index, len(pieces), week)
                return {}
            parts.append(text)
        out[server] = "\n\n".join(parts)
    return out


async def maybe_week(bot) -> bool:
    """Roll up the week that just ended, once. True when it wrote something."""
    config = getattr(bot, "config", None) or {}
    week = week_target()
    if not week:
        return False
    sections = await asyncio.to_thread(summarise_week, config, week)
    if not sections:
        return False
    journal.note_week_digest(week, sections)
    LOG.info("weekly server summary written: %s (%d server(s))",
             week, len(sections))
    return True


async def watch(bot) -> None:
    """Poll forever. Free and idle until a digest is actually owed."""
    while True:
        try:
            await maybe_run(bot)
        except Exception as exc:
            LOG.warning("digest pass failed: %s", exc)
        try:
            await maybe_week(bot)
        except Exception as exc:
            LOG.warning("weekly roll-up failed: %s", exc)
        await asyncio.sleep(POLL_SECONDS)
