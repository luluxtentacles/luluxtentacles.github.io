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
import hashlib
import time
from datetime import datetime, timedelta

import brain
import journal
import paths
import people

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


def _ask_ex(config, server: str, piece: str, part_note: str,
            system: str = SYSTEM) -> tuple[str, bool]:
    """One summariser call on the FREE ladder - gemini keys, then openrouter.

    Never the Go rung: see brain.free_complete_ex. Returns (text, blocked):
    `blocked` is True when a rung refused the piece on content policy -
    deterministic, which is what the quarter ladder below keys on. `tries`
    sweeps the whole free ladder ATTEMPTS times back to back for a rung
    that answers on a second sweep; a piece that still comes back empty is
    the CALLER's problem, because the retry that matters happens a level up.
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Server: {server}{part_note}\n\n"
                                    f"Recent activity:\n{piece}"},
    ]
    return brain.free_complete_ex(config, messages, max_tokens=MAX_TOKENS,
                                  temperature=0.3, timeout=CALL_TIMEOUT,
                                  tries=ATTEMPTS)


# The quarter ladder. A content-policy block is deterministic, so a rejected
# chunk is not retried - it is cut into four and each quarter is retried; any
# quarter still refused is given up on and the hole is MARKED in the digest.
# Below this size a quarter cannot usefully shrink further (a summary of a
# couple of chat lines is not worth a call).
QUARTER_MIN_CHARS = 400
QUARTER_MAX_DEPTH = 2      # chunk -> quarter -> sixteenth, then give up


def _summarise_piece(config, server: str, piece: str, note: str,
                     depth: int = 0, system: str = SYSTEM) -> tuple[str, str]:
    """One chunk, with the quarter-and-retry ladder for policy blocks.

    Returns (text, status): 'ok' (text is a summary), 'dry' (transient -
    the caller holds the window and the next pass walks the ladder again),
    or 'blocked' (refused on content policy even after quartering - the
    caller gives up on this section and writes the hole into the record).
    """
    text, blocked = _ask_ex(config, server, piece, note, system)
    if text:
        return text, "ok"
    if not blocked:
        return "", "dry"
    if depth >= QUARTER_MAX_DEPTH or len(piece) < 2 * QUARTER_MIN_CHARS:
        LOG.warning("digest: %s section (%d chars) refused by content policy "
                    "at quarter depth %d - giving up on it",
                    server, len(piece), depth)
        return "", "blocked"
    quarters = chunk(piece, size=max(QUARTER_MIN_CHARS, len(piece) // 4 + 1))
    parts: list[str] = []
    dropped = 0
    for index, quarter in enumerate(quarters, 1):
        sub_note = f"{note} (retried as quarter {index}/{len(quarters)})"
        text, status = _summarise_piece(config, server, quarter, sub_note,
                                        depth + 1, system)
        if status == "dry":
            # A quarter that failed for TRANSIENT reasons means the ladder is
            # down, not the content rejected: hold the whole window.
            return "", "dry"
        if text:
            parts.append(text)
        else:
            dropped += 1
    if dropped:
        LOG.warning("digest: %s gave up on %d/%d quarter(s) after a content "
                    "policy block", server, dropped, len(quarters))
        parts.append(f"[{dropped} of {len(quarters)} smaller sections of this "
                     f"part were refused by a provider content filter and are "
                     f"not covered.]")
    return "\n\n".join(parts), ("ok" if parts else "blocked")


def summarise(config, server: str, lines) -> str:
    """One server's digest. Chunked if long; "" when a chunk came back DRY.

    Mostly-all-or-nothing, with one carve-out (master, 2026-09-23): a chunk
    refused by a provider CONTENT POLICY is not a dry chunk - retrying it
    never answers, it only holds the window hostage forever. So the quarter
    ladder (see _summarise_piece) cuts it into four and gives up on any
    section still refused, and the hole is written into the digest as a
    marked note. A summary with a marked hole is a lie of omission; an
    eternally-retried window is a hole the size of a whole day.

    Transient failures (quota, busy, network) keep the old rule exactly: a
    dry chunk fails the WHOLE server, the window is held, and the next poll
    - five minutes later - walks the free ladder again. Master, 2026-09-22:
    retry "every 5 minutes until success".
    """
    transcript = render(lines)
    if not transcript.strip():
        return ""
    pieces = chunk(transcript)
    parts: list[str] = []
    refused = 0
    for index, piece in enumerate(pieces, 1):
        note = f" (part {index} of {len(pieces)})" if len(pieces) > 1 else ""
        text, status = _summarise_piece(config, server, piece, note)
        if status == "dry":
            LOG.warning("digest: %s part %d/%d came back dry - holding the "
                        "window for the next pass", server, index, len(pieces))
            return ""
        if text:
            parts.append(text)
        else:
            refused += 1
    if refused:
        LOG.warning("digest: %s: %d/%d part(s) refused by content policy - "
                    "writing the rest with the hole marked",
                    server, refused, len(pieces))
        parts.append(f"[{refused} of {len(pieces)} part(s) of this window were "
                     f"refused by a provider content filter and could not be "
                     f"summarised.]")
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


# ------------------------------------------------- the drop, not the mirror
# Master, 2026-09-25: Nyan summarizes the shared servers anyway (her Layer 1),
# and both bots chewing the same transcript was double spend. Her DROP now
# carries her server summaries, and THIS module ingests them instead of
# re-summarizing the same chat on the free ladder - for every guild I am
# actually in. Servers her drop does not cover still fall through to the
# mirror path below; servers I am not in are excluded, exactly as master said.
def _ingest_nyan_summaries(bot, state) -> set:
    """Write Nyan's fresh server summaries into the journal. Returns the set
    of server NAMES her drop covers, so the mirror path can skip them."""
    try:
        drop = paths.read_json(people.DROP_LATEST, default=None)
    except Exception:
        return set()
    if not isinstance(drop, dict):
        return set()
    section = drop.get("server_summaries")
    if not isinstance(section, dict):
        return set()
    mine = {str(g.id): str(g.name) for g in
            (getattr(bot, "guilds", None) or [])}
    my_names = set(mine.values())
    seen = state.setdefault("nyan_summaries", {})
    covered: set = set()
    for guild_id, s in section.items():
        if not isinstance(s, dict) or str(guild_id) not in mine:
            continue
        name = str(s.get("guild_name") or mine[str(guild_id)] or guild_id)
        if name not in my_names:
            continue
        daily = [d for d in (s.get("daily") or []) if isinstance(d, dict)]
        parts = [f"[{d.get('date')}] {d.get('text')}"
                 for d in daily if str(d.get("text") or "").strip()]
        long_term = str(s.get("long_term") or "").strip()
        if long_term:
            parts.append("(her long-term memory of this server):\n" + long_term)
        body = "\n\n".join(parts).strip()
        if not body:
            covered.add(name)
            continue
        fresh = hashlib.sha1(body.encode("utf-8")).hexdigest()
        if seen.get(str(guild_id)) == fresh:
            covered.add(name)
            continue
        try:
            journal.note_digest(
                body, label=f"server digest - {name} (from Nyan's watch)")
        except Exception as exc:
            LOG.warning("digest: could not journal Nyan's summary for %s: %s",
                        name, exc)
            continue
        seen[str(guild_id)] = fresh
        covered.add(name)
        LOG.info("digest: ingested Nyan's summary of %s from the drop", name)
    return covered



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
    covered = _ingest_nyan_summaries(bot, state)
    grouped = {server: lines for server, lines in collect(since, until).items()
               if server not in done and server not in covered}
    if not grouped:
        # Nothing moved, or every server in this window is already written.
        # Stamped either way, or the poll would ask the same question forever.
        _save(last_run=time.time(), last_run_iso=_stamp(), window={}, done=[])
        return False

    # Refresh the live model ladders (OpenRouter free + Gemini) before
    # walking them (master, 2026-09-23).
    await asyncio.to_thread(brain.refresh_models, config)

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

    Runs on the FREE ladder, like the daily pass - nobody's answer depends
    on a roll-up, so it must never spend the rung master pays for. The live
    model ladders (OpenRouter free + Gemini) are refreshed FIRST, so a run
    never walks a stale ladder. Mostly-all-or-nothing: an empty dict when a
    chunk failed for TRANSIENT reasons, so maybe_week writes nothing and the
    next poll retries the week; a chunk refused by CONTENT POLICY goes
    through the same quarter ladder as the daily pass instead.

    Per server, and not one blob, because the result is read back with a
    per-server filter: a room may hear its own server's summary and no other. If
    the model wrote the whole week as one piece of prose, that boundary would
    have to be guessed from its formatting, which is not a boundary at all. So
    the CODE decides where one server ends and the next begins here, and the
    model only ever writes the middle of a section.
    """
    # Refresh the live ladders before walking them (master, 2026-09-23).
    brain.refresh_models(config)
    by_server = journal.digest_week_by_server(week)
    if not by_server:
        by_server = {"(unnamed server)": journal.digest_week_material(week)}
    out: dict[str, str] = {}
    for server, material in by_server.items():
        if not material.strip():
            continue
        pieces = chunk(material)
        parts, refused = [], 0
        for index, piece in enumerate(pieces, 1):
            note = f" (part {index} of {len(pieces)})" if len(pieces) > 1 else ""
            text, status = _summarise_piece(config, server, piece, note,
                                            system=WEEK_SYSTEM)
            if status == "dry":
                # Same rule as the daily pass: a piece that does not answer
                # for TRANSIENT reasons fails the WHOLE week, so nothing is
                # written and the next poll tries again. A week with a hole
                # reads exactly like a week without one.
                LOG.warning("week roll-up: %s part %d/%d came back dry - "
                            "holding week %s for the next pass",
                            server, index, len(pieces), week)
                return {}
            if text:
                parts.append(text)
            else:
                refused += 1
        if refused:
            LOG.warning("week roll-up: %s: %d/%d part(s) refused by content "
                        "policy - writing the rest with the hole marked",
                        server, refused, len(pieces))
            parts.append(f"[{refused} of {len(pieces)} part(s) of this week "
                         f"were refused by a provider content filter and "
                         f"could not be summarised.]")
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
