"""My Discord diary, and my Discord journal - both mine, both inside the wall.

    memory/diary/<date>.md           my diary. What happened to me here, in my
                                     own words.
    memory/journal/<date>.md         the raw record: who spoke, which channel,
                                     what was said. Everyone, not just master.
    memory/said/<date>.md            my own mouth: the lines I sent, by room.
                                     The journal holds what was said TO me; this
                                     is the only record of what came back out.
    memory/mirror/<date>.md          the room itself, both sides, LAST 48 HOURS.
                                     The block in my prompt is trimmed from this
                                     same dialog, but the file is what survives a
                                     restart and what can be searched by word.

These are the ONLY two records I can reach. The den's diary at C:\\Lulu\\diary
is NOT readable from here and there is no code path to it: that one is master's
private record of his own work, and it has nothing to do with this server. A
mouth that talks in a public channel does not get to read the head's notebook.

This used to be the other way round - read_diary reached into the den and
pulled up to 6000 characters of it into whatever channel master asked from.
Most of that file was never about Discord at all. Severed on master's call.

The diary is written by me, through write_diary, so it says what I think
happened rather than dumping raw traffic.
"""
from __future__ import annotations

import difflib
import re
import time
from datetime import date, datetime, timedelta
from hashlib import sha1

import paths

LOCAL_DIARY = "memory/diary"
LOCAL_REL = "memory/journal"
# The servers, rolled up by the week. Deliberately NOT inside the diary: the
# diary is hers and these are other people's words - two audiences and two
# privacy boundaries do not belong in one file.
LOCAL_DIGEST = "memory/digest"

DATE_FMT = "%Y-%m-%d"
MAX_LINE = 400
MAX_READ_CHARS = 6000

# The reader shows BOTH ends of a day. Reading the first MAX_READ_CHARS of a file
# that is only ever appended to returned the small hours and dropped the rest,
# silently: on 2026-09-22 the live journal was 15228 chars and read_journal handed
# back 65 of its 152 entries - 00:05 to 03:27 - while the day itself ran to 15:04.
# "Who talked to me today", asked in the afternoon, was answered from the morning.
# The cut says so now, so a partial day cannot read as a whole one.
CUT_MARK = "\n\n[... the middle of this day is not shown ...]\n\n"

# A digest block is a SUMMARY, not a line: it keeps its paragraph breaks and it is
# allowed to be long. `_clean` is the wrong tool for it - it collapses all
# whitespace and cuts at MAX_LINE (400), which would leave a digest reading like a
# truncated line.
DIGEST_MAX_CHARS = 12000

# Mask credential-shaped text before it can land in a journal that other people's
# names sit next to. Borrowed from shared_memory rather than reimplemented: two
# pattern sets would drift, and a mask that has drifted is worse than none.
from shared_memory import redact  # noqa: E402  (path setup lives in that module)


def today() -> str:
    return datetime.now().strftime(DATE_FMT)


def shift(day: str, offset: int) -> str:
    try:
        return (date.fromisoformat(day) + timedelta(days=offset)).strftime(DATE_FMT)
    except ValueError:
        return day


def _clean(text: str) -> str:
    return " ".join((text or "").split())[:MAX_LINE]


def _one_line(text: str, limit: int) -> str:
    """Masked, collapsed to one line, cut at `limit`.

    Shared by the records of a MESSAGE - what I said, and the room's mirror - so
    the two cannot drift into two different rules, which is the same reason the
    redactor is borrowed from shared_memory rather than written twice.
    """
    return " ".join(redact(text or "").split())[:limit]


# --------------------------------------------------------------- her journal
#
# Filed by year and month, so a year of days is a browsable tree instead of one
# flat dir: `memory/journal/2026/09/2026-09-22.md`. Master, 2026-09-22: *"keep
# journals tidy in month and year folders"*. Every reader and writer goes through
# `_local_rel`, so the layout lives in exactly one place - and the weekly roll-up
# walks `week_days()`, so it followed this change without being told.
#
# A key that is not a date keeps the old flat name: a junk key must never be
# pasted into a path just because something called this with one.
def _local_rel(day: str) -> str:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", (day or "").strip())
    if not match:
        return f"{LOCAL_REL}/{day}.md"
    return f"{LOCAL_REL}/{match.group(1)}/{match.group(2)}/{day}.md"


def _flat_rel(day: str) -> str:
    """The pre-2026-09-22 flat name. Still read, never written again."""
    return f"{LOCAL_REL}/{day}.md"


def _day_body(day: str) -> str:
    """One day's journal, out of its year/month folder or its legacy flat file.

    Read-through rather than a migration on the read path: a day that was never
    tidied still answers, so moving files is a tidy-up and never a dependency.
    """
    body = paths.read_text(_local_rel(day), default="")
    if not body.strip():
        body = paths.read_text(_flat_rel(day), default="")
    return body


def tidy_layout() -> int:
    """Move flat journal day files into their year/month folders. Idempotent.

    Deliberately NOT wired into boot. Moving files at startup is a lot of risk
    for something that needs doing once per layout change - and `_day_body` reads
    either shape, so an untidied day still answers. This only makes the tree
    browsable, and a caller that has already tidied gets 0 back.
    """
    moved = 0
    try:
        root = paths.resolve(LOCAL_REL)
        if not root.is_dir():
            return 0
        for path in sorted(root.glob("*.md")):
            day = path.stem
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                continue
            rel = _local_rel(day)
            target = paths.resolve(rel)
            if target.exists():
                continue        # already tidied - never overwrite a day
            paths.write_text(rel, path.read_text(encoding="utf-8"),
                             internal=True)
            path.unlink()       # write first, delete second: crash-safe order
            moved += 1
    except Exception:
        return moved
    return moved


# `note()` used to live here: one line per message, incoming only, appended to
# memory/journal/<date>.md. Retired 2026-09-22 on master's call. It recorded half
# a conversation and could not say which room a line came from - and the mirror
# below covers the same ground with the room named on every line and BOTH sides
# in it. Nothing replaced it HERE: the journal is a digest log now, and the live
# record of a room is memory/mirror/. Her diary, mood, digests and mirror below
# are untouched.


def _clean_block(text: str, limit: int = DIGEST_MAX_CHARS) -> str:
    """A digest body: masked, paragraph breaks kept, headings demoted.

    A digest is not a line. `_clean` would flatten it and cut it at 400 chars,
    and an embedded '## ' would forge the journal's own structure - which is the
    seam read_digest splits on - so any heading in the body becomes a bullet.
    """
    body = redact(text or "").replace("\r\n", "\n")
    lines = []
    for line in body.split("\n"):
        if line.lstrip().startswith("#"):
            line = "- " + line.lstrip("# ").strip()
        lines.append(line.rstrip())
    return "\n".join(lines).strip()[:limit]


def note_digest(text: str, *, label: str = "server digest", day: str = "") -> str:
    """Append one summarised block to a day's journal, marked with '## '.

    Never raises, like note(): the digest is a convenience and the raw record
    beside it is the thing that matters.
    """
    body = _clean_block(text)
    if not body:
        return "nothing to note"
    day = (day or "").strip() or today()
    try:
        rel = _local_rel(day)
        existing = paths.read_text(rel, default="")
        if not existing.strip() and paths.read_text(_flat_rel(day),
                                                    default="").strip():
            # That day still lives in the old flat file. Append THERE rather than
            # starting a second one, or a single day would read back as two
            # halves in date order but not in time order.
            rel = _flat_rel(day)
            existing = paths.read_text(rel, default="")
        if not existing:
            existing = f"# Journal - {day}\n\n"
        head = f"## {label} \u00b7 {datetime.now().strftime('%H:%M')}"
        paths.write_text(rel, existing + f"\n{head}\n\n{body}\n", internal=True)
    except Exception as exc:
        return f"could not note the digest: {exc.__class__.__name__}"
    return f"digest noted in my journal for {day}"


def read_digest(day: str = "") -> str:
    """Just the summarised blocks in my journal - no raw traffic."""
    day = (day or "").strip()
    if day and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return "that is not a date - use YYYY-MM-DD"
    wanted = [day] if day else [today(), shift(today(), -1)]
    out = []
    for d in wanted:
        body = _day_body(d)
        blocks = [b.strip() for b in re.split(r"^## ", body, flags=re.M)[1:]]
        out.append("\n\n".join("## " + b for b in blocks) if blocks
                   else f"{d}: no digest written")
    return "\n\n".join(out)[:MAX_READ_CHARS]


# ------------------------------ the servers, summarised by the week
def _week_digest_rel(week: str) -> str:
    return f"{LOCAL_DIGEST}/{week}.md"


def digest_week_by_server(week: str) -> dict[str, str]:
    """That week's digest material, split into {server: text}.

    The split is on `**Name**` on its own line, and that marker is written by
    CODE - `digest.body()` and `note_week_digest` both put it there. It is never
    a model's formatting, which is the point: a privacy boundary that depends on
    an LLM remembering a heading format is not a boundary. A block whose server
    will not parse is kept under its own unparsed key rather than silently
    merged into a neighbour.
    """
    out: dict[str, str] = {}
    for block in _digest_blocks(week):
        for name, text in _split_servers(block).items():
            key = name or "(unnamed)"
            out[key] = (out[key] + "\n\n" + text).strip() if out.get(key) else text
    return out


def _digest_blocks(week: str) -> list[str]:
    """The '## ' blocks in that week's journal - the summaries, not the chatter."""
    blocks = []
    for day in week_days(week):
        body = _day_body(day)
        for block in re.split(r"^## ", body, flags=re.M)[1:]:
            block = block.strip()
            if block:
                blocks.append(block)
    return blocks


SERVER_RE = re.compile(r"^\*\*(.+?)\*\*[ \t]*$", re.M)


def _split_servers(text: str) -> dict[str, str]:
    """Split one block on its `**Server**` markers. {} if there are none."""
    marks = list(SERVER_RE.finditer(text or ""))
    if not marks:
        return {}
    out: dict[str, str] = {}
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        name = mark.group(1).strip()
        body = text[mark.end():end].strip()
        if name and body:
            out[name] = body
    return out


def digest_week_material(week: str) -> str:
    """Every '## ' block written into that week's journal - the digests only.

    The day journal holds both the raw lines and the summarised blocks, and the
    '## ' split is what tells them apart: note() writes '- ' and note_digest
    writes '## '. Raw traffic is deliberately not included - a roll-up of what
    people actually typed is not a summary, it is a transcript.
    """
    return "\n\n".join(f"## {b}" for b in _digest_blocks(week))


def week_digest_written(week: str) -> bool:
    """Has that week's roll-up been written yet?"""
    return bool(paths.read_text(_week_digest_rel(week), default="").strip())


def note_week_digest(week: str, sections: dict) -> str:
    """Store one week's rolled-up summaries, ONE SECTION PER SERVER.

    Written from a {server: text} map rather than one prose blob, so the server
    boundary is something the CODE laid down and can be trusted by
    read_week_digest later. A blob would make per-server recall a guess.
    """
    parts = []
    for server, text in (sections or {}).items():
        body = _clean_block(str(text or ""))
        if body:
            parts.append(f"**{server}**\n\n{body}")
    if not parts:
        return "nothing to note"
    try:
        paths.write_text(_week_digest_rel(week),
                         f"# Server summaries - week {week}\n\n"
                         + "\n\n".join(parts) + "\n",
                         internal=True)
    except Exception as exc:
        return f"could not note the week: {exc.__class__.__name__}"
    return f"server summaries noted for {week} ({len(parts)} server(s))"


def _week_digest_body(week: str) -> str:
    """That week's roll-up if it exists, else the blocks it will be made from."""
    if not week:
        return ""
    body = paths.read_text(_week_digest_rel(week), default="").strip()
    if not body:
        body = digest_week_material(week).strip()
    return body


def read_week_digest(week: str = "", server: str = "",
                     limit: int = DIGEST_MAX_CHARS) -> str:
    """A week's server summaries - the roll-up, or the blocks it is made of.

    `server` is the whole reason this function has to be careful. A room may ask
    what has been happening, and what a room may hear is ITS OWN server's
    summary - never a neighbour's. So when a server is named:

      - only that server's section comes back, matched case-insensitively;
      - if nothing matches, it returns nothing, and it does NOT fall back to the
        whole week. Failing closed is the point: the failure mode of guessing
        here is one server's conversations read out in another one.

    With no server named, the whole week comes back - that is the owner's view.
    """
    asked = (week or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", asked):
        asked = week_of(asked)
    week = asked or week_of()
    body = _week_digest_body(week)
    used = week
    if not body and not asked:
        used = prev_week(week)
        body = _week_digest_body(used)
    if not body:
        return f"{week}: no server summaries written for that week"

    wanted = (server or "").strip()
    if wanted:
        by_server = _split_servers(body)
        match = next((text for name, text in by_server.items()
                      if name.casefold() == wanted.casefold()), None)
        if match is None:
            return (f"nothing written for {wanted} in week {used} - and I will "
                    f"not read another server's week out in here.")
        return match[:max(int(limit), 0)]

    header = "" if used == week_of() else f"(week {used})\n\n"
    return (header + body)[:max(int(limit), 0)]


def _clip(body: str, limit: int = MAX_READ_CHARS) -> str:
    """A day trimmed to `limit`, keeping the start AND the newest part."""
    if len(body) <= limit:
        return body
    head = max(0, limit // 3)
    tail = limit - head - len(CUT_MARK)
    if tail <= 0:
        return body[:limit]
    return body[:head].rstrip() + CUT_MARK + body[-tail:].lstrip()


# `read_journal` used to live here, reading back memory/journal/<date>.md. Retired
# with `note()` on 2026-09-22 - it was the reader for a record nothing writes any
# more. `read_digest` below still reads the digest blocks in that same file.


# ------------------------------------------------------------ what I said
# Her own sent lines, written down as they leave.
#
# WHY THIS EXISTS: the journal carries what was said TO her and never her own
# half, and the mirror - which does hold her replies - is a deque of 200 lines
# per channel living in RAM, so it dies with the process. Between the two, "what
# did I actually say in that room" was answerable only from a store that forgets,
# and on 2026-09-22 that is how an afternoon of her own words went missing. This
# is the durable half: her side, on disk, by room and by day.
#
# WHAT IT IS NOT: not every byte that leaves her. Progress pings, restart notices
# and review reports are machinery narrating itself, and they are not here. This
# holds what she said to a person - a reply, a bit of chatter, a resume note, or
# something she sent into another room to be heard.
LOCAL_SAID = "memory/said"

# A message can be MAX_MESSAGE (2000) long. MAX_LINE's 400 is for a line somebody
# typed AT her; cutting her own words there would let this file answer "no" to
# "did I say that", and a log that can be wrong about her own mouth is worse than
# no log. So the cap is the send limit, and the reader must not clip below it.
MAX_SAID_LINE = 2000


def _said_rel(day: str) -> str:
    return f"{LOCAL_SAID}/{day}.md"


def note_said(text: str, *, room: str = "", message_id: int | None = None) -> None:
    """Write down one line I actually sent. Never raises, like note().

    Masked on the way in with the same redactor as everything else: a credential
    she typed by accident must not land in a file she will one day quote back at
    herself.

    One message is ONE LINE, runs of whitespace collapsed, exactly like the
    journal's own entries - the reader filters by line, and a multi-line message
    flattened to a sentence is still the same words in the same order. The cap is
    the send limit rather than MAX_LINE, so a long message is stored whole: the
    one thing this file must never do is answer "no" about something she said.
    """
    try:
        body = _one_line(text, MAX_SAID_LINE)
        if not body or body == "[redacted]":
            return
        name = _clean(room).lstrip("#").strip()
        where = f" in #{name}" if name else " in a DM"
        day = today()
        line = f"- **{datetime.now().strftime('%H:%M')}**{where}: {body}\n"
        rel = _said_rel(day)
        existing = paths.read_text(rel, default="")
        if not existing:
            existing = f"# What I said - {day}\n\n"
        paths.write_text(rel, existing + line, internal=True)
    except Exception:
        return


def read_said(day: str = "", room: str = "") -> str:
    """The lines I sent on a day, newest last, or just one room's.

    `room` matches however she spells it - 'general', '#general' and 'GEN' all
    land on the same room. A filtered miss says so AND says what the miss does
    not mean, because "not in my log" and "I never said it" are different
    answers and only one of them is true.
    """
    day = (day or "").strip()
    if day and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return "that is not a date - use YYYY-MM-DD"
    day = day or today()
    body = paths.read_text(_said_rel(day), default="")
    if not body:
        return (f"nothing written down for {day} - either I said nothing, or "
                f"that is from before I started keeping this")
    wanted = _clean(room).lstrip("#").strip().lower()
    if not wanted:
        return _clip(body)
    lines = [ln for ln in body.splitlines()
             if ln.startswith("- ") and wanted in ln.lower()]
    if not lines:
        return (f"nothing of mine in a room matching '{wanted}' on {day}. That "
                f"is not the same as never saying it - I only started writing "
                f"my own lines down on 2026-09-22, and status lines I send "
                f"(progress pings, restart notices) are not in here either.")
    return _clip(f"# What I said, matching {wanted} - {day}\n\n"
                 + "\n".join(lines) + "\n")


# ---------------------------------------------------------------- the mirror
# The room itself, both sides, written down as it happens.
#
# The block in my prompt is a deque of MIRROR_LINES per channel in RAM: right for
# the last hour, gone on a restart, and impossible to search. Master, 2026-09-22:
# *"we should maybe keep the mirror to be the last 48 hours she can search it
# with keywords"*. So the same line is also written here - one file per day, every
# room in it, pruned to the window - and search_mirror walks it.
#
# This is not a third copy of one fact. The journal is incoming only and flat
# ("who talked to me"); memory/said is my own lines, kept for good; this is the
# two-sided dialog with the room named on every line, and it expires by design.
#
# It is also NOT what reaches the prompt: the block is still built from RAM under
# its own character budget. This store exists to be SEARCHED, not to be injected.
LOCAL_MIRROR = "memory/mirror"

MIRROR_WINDOW_HOURS = 48    # master, 2026-09-22: a ROLLING 48 HOURS - raw kept
                            # long enough that the half about to leave can be
                            # summarised into the journal before it is pruned
MIRROR_KEEP_DAYS = 3        # day files kept, so a 48h window is always whole:
                            # today, yesterday and the day before cover 48 hours
                            # from any hour, not only from midnight
MIRROR_LINE_MAX = 2000      # the send limit, not MAX_LINE - see note_said
MIRROR_SEARCH_MAX = 6000    # characters one search returns, newest first


SERVER_SLUG_RE = re.compile(r"[^a-z0-9]+")


def server_slug(server: str) -> str:
    """A server name as a FOLDER name, or "" when there is no server at all.

    Server names are display strings - spaces, punctuation, unicode, the odd
    slash - and none of that may become a path. Everything that is not a letter
    or a digit collapses to a dash, so `Unofficial HIMR Server` lands in
    `unofficial-himr-server`.

    AN EMPTY RETURN MEANS "NOT IN A SERVER", which is a DM, and callers treat it
    as "do not record this line". That is the structural half of master's
    2026-09-22 call: a DM has no server, so it has no file to land in.

    A NAME THAT SLUGS TO NOTHING IS STILL A SERVER, and it gets a stable
    fallback instead of an empty slug. Found the hard way on 2026-09-22, on the
    first real grab: a guild whose name is written in superscript unicode
    characters (`ˢⁿᵃⁱˡᶜᵃᵗʰᵒˡⁱᶜ`) has no [a-z0-9] in it at all, so the slug
    came back EMPTY and the DM rule threw away every line of the whole server -
    silently, because note_mirror swallows its own failures. The display name is
    what matters and it is kept in servers.json; the folder just needs to be
    stable. So the distinction is made on the NAME, not on the slug.
    """
    name = (server or "").strip()
    if not name:
        return ""
    slug = SERVER_SLUG_RE.sub("-", name.lower()).strip("-")
    if not slug:
        slug = "s-" + sha1(name.encode("utf-8")).hexdigest()[:12]
    return slug[:60]


def _mirror_rel(server: str, day: str) -> str:
    """One day of ONE server's mirror.

    Master, 2026-09-22: *"the mirror would be per server"*. Per server rather
    than one file with the server tagged on every line, because that makes the
    boundary STRUCTURAL: reading a room's own history cannot reach a neighbour's
    lines by accident, and it is the same reasoning as the weekly summaries.
    """
    return f"{LOCAL_MIRROR}/{server}/{day}.md"


# A folder name has to be a safe path, so it is a slug. But a summary that calls a
# server `unofficial-himr-server` is not one anybody recognises, and the weekly
# file is matched back by DISPLAY name - so the two are recorded together, or the
# room can never find its own summary again.
SERVER_INDEX = "servers.json"


def server_index() -> dict:
    """{slug: the name a person would recognise}, beside the mirror folders."""
    try:
        data = paths.read_json(f"{LOCAL_MIRROR}/{SERVER_INDEX}", default={})
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def server_name(slug: str) -> str:
    """The display name for a mirror folder, or the slug itself if unknown."""
    if not slug:
        return ""
    return str(server_index().get(slug) or slug)


def _remember_server(slug: str, display: str) -> None:
    """Keep slug -> display, written only when it is new or has changed.

    A read per line, a write only on a rename: the mirror already writes once per
    message, and this must not double that for nothing.
    """
    try:
        index = server_index()
        if index.get(slug) == display:
            return
        index[slug] = display
        paths.write_json(f"{LOCAL_MIRROR}/{SERVER_INDEX}", index, internal=True)
    except Exception:
        return


def note_mirror(author: str, text: str, *, room: str = "",
                server: str = "") -> None:
    """Write down one line of a room - which server, which room, who, what.

    Same contract as note() and note_said(): a record, not a dependency. If it
    cannot be written the conversation carries on and the failure is swallowed.

    NO SERVER, NO LINE. A DM has no server, so it has nothing to be filed under -
    and master's call on 2026-09-22 was that his private conversations are not
    recorded for later summarising. Filtering at the WRITE is stronger than
    filtering at the read, because it cannot be undone by a later reader.
    """
    try:
        slug = server_slug(server)
        if not slug:
            return
        body = _one_line(text, MIRROR_LINE_MAX)
        if not body or body == "[redacted]":
            return
        who = _clean(author) or "someone"
        name = _clean(room).lstrip("#").strip()
        where = f"[#{name}]" if name else "[no room]"
        day = today()
        rel = _mirror_rel(slug, day)
        _remember_server(slug, _clean(server))
        existing = paths.read_text(rel, default="")
        if not existing:
            existing = f"# Mirror - {day}\n\n"
            # The first line of a new day is the moment to let the old ones go:
            # pruning here needs no timer and no loop, and three files cover a
            # 48h window from any hour of any day. Only what has already fallen
            # out of the window is ever touched.
            _prune_mirror(slug)
        line = (f"- **{datetime.now().strftime('%H:%M')}** {where} "
                f"{who}: {body}\n")
        paths.write_text(rel, existing + line, internal=True)
    except Exception:
        return


def _prune_mirror(server: str = "", keep_days: int = MIRROR_KEEP_DAYS) -> int:
    """Delete day files that have fallen out of the window, one server at a time.

    Whole DAYS leave, which is why the default is 3 and not 2: a day file has to
    stay while any part of it could still be inside the window, and the window is
    counted in hours from now, not in midnights. A 48h window reaches back into
    the day before yesterday from any hour, so three files is the honest number.

    With no server named every server folder is swept, which is what the net uses
    and what a fresh install needs.
    """
    removed = 0
    try:
        root = paths.resolve(LOCAL_MIRROR)
        if not root.is_dir():
            return 0
        folders = ([root / server] if server
                   else [d for d in root.iterdir() if d.is_dir()])
        oldest_kept = shift(today(), -(keep_days - 1))
        for folder in folders:
            for path in folder.glob("*.md"):
                day = path.stem
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                    continue
                if day < oldest_kept:      # ISO dates sort as strings
                    path.unlink()
                    removed += 1
    except Exception:
        return removed
    return removed


def _mirror_cutoff(hours: int = MIRROR_WINDOW_HOURS) -> datetime:
    """The oldest moment a search will look back to."""
    return datetime.now() - timedelta(hours=hours)


def _in_window(day: str, at: str, cutoff: datetime) -> bool:
    """Is a mirror line stamped `day at HH:MM` inside the window?

    Split out as its own function - and not buried in the search loop - because
    it is the one piece of the window that has to be provable without waiting 48
    hours, or trusting whatever time of day a test happens to run at.
    """
    try:
        when = datetime.strptime(f"{day} {at}", "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return when >= cutoff


def _mirror_entries(server: str, day: str) -> list[tuple[str, str, str]]:
    """(time, [room], rest) for every line in ONE server's day, in file order."""
    out = []
    body = paths.read_text(_mirror_rel(server, day), default="")
    for line in body.splitlines():
        match = re.match(r"^- \*\*(\d{2}:\d{2})\*\* (\[[^\]]*\]) (.*)$", line)
        if match:
            out.append((match.group(1), match.group(2), match.group(3)))
    return out


def mirror_entries_all(day: str) -> list[tuple[str, str, str, str]]:
    """(server, time, [room], rest) for a whole day, across EVERY server.

    The reader a sweep needs - everything since a bookmark, not one room's file -
    and it is PUBLIC because nyanwatch walks it and a reader that reaches into a
    private helper is a caller that breaks when the layout changes. Exactly what
    happened here: the mirror moved to one file per server and this is the one
    place that has to keep working across all of them.

    Server folders come in sorted order, so a sweep is STABLE but no longer
    strictly chronological across servers - the old single file held lines in
    arrival order and per-server files cannot. No line is skipped or repeated,
    which is what the bookmark counts on; only the interleaving is lost.
    """
    out: list[tuple[str, str, str, str]] = []
    root = paths.resolve(LOCAL_MIRROR)
    if not root.is_dir():
        return out
    for folder in sorted(d for d in root.iterdir() if d.is_dir()):
        for at, where, rest in _mirror_entries(folder.name, day):
            out.append((folder.name, at, where, rest))
    return out


def search_mirror(query: str = "", hours: int = MIRROR_WINDOW_HOURS,
                  room: str = "", server: str = "") -> str:
    """Search the last `hours` of the mirror by keyword, newest line first.

    Every word in the query has to appear on the line, so two words ask a
    narrower question than one. `room` narrows it to a single room, spelled
    however I spell it. The window is master's ROLLING 48 HOURS; asking for
    longer is capped rather than refused, because the files do not go back
    further and a refusal would say nothing about where the edge actually is.

    `server` narrows it to one server. Omitted, every server is searched, which
    is master's view - the files are per server now, so a room reading only its
    own is the same rule the weekly summaries already follow.
    """
    terms = [word for word in _clean(query).lower().split() if word]
    if not terms:
        return ("give me a word to look for - a name, or the thing that was "
                "said - and I will find the lines it was in")
    try:
        hours = int(hours or MIRROR_WINDOW_HOURS)
    except (TypeError, ValueError):
        hours = MIRROR_WINDOW_HOURS
    hours = max(1, min(hours, MIRROR_WINDOW_HOURS))
    cutoff = _mirror_cutoff(hours)
    wanted = _clean(room).lstrip("#").strip().lower()

    wanted_server = server_slug(server)
    if server and not wanted_server:
        return f"'{server}' is not a server I can name"
    root = paths.resolve(LOCAL_MIRROR)
    if wanted_server:
        folders = [wanted_server]
    elif root.is_dir():
        folders = [d.name for d in sorted(root.iterdir()) if d.is_dir()]
    else:
        folders = []

    found: list[tuple[datetime, str]] = []
    # Named the way a PERSON says it, not as the folder it lives in: the folder is
    # a slug because a name may not be a path, and a hit that comes back as
    # `unofficial-himr-server` is one nobody recognises as a room.
    names = server_index()
    for folder in folders:
        for offset in range(MIRROR_KEEP_DAYS):
            day = shift(today(), -offset)
            for at, where, rest in _mirror_entries(folder, day):
                if not _in_window(day, at, cutoff):
                    continue
                if wanted and wanted not in where.lower():
                    continue
                line = (f"- **{day} {at}** [{names.get(folder) or folder}] "
                        f"{where} {rest}")
                if all(term in line.lower() for term in terms):
                    found.append((datetime.strptime(f"{day} {at}",
                                                    "%Y-%m-%d %H:%M"), line))

    if not found:
        out = [f"nothing in the last {hours} hours matches "
               f"{' and '.join(terms)}"]
        if wanted:
            out.append(f"in a room matching '{wanted}'")
        out.append(". That is not the same as it never happening: this record "
                   "only starts from when master had it built on 2026-09-22, "
                   "and my own sent lines stay readable in read_said.")
        return "".join(out).replace(" matches in", " matches in")

    found.sort(key=lambda pair: pair[0], reverse=True)      # newest first
    lines = [line for _, line in found]
    kept: list[str] = []
    spent = 0
    for line in lines:
        if spent + len(line) > MIRROR_SEARCH_MAX:
            break
        kept.append(line)
        spent += len(line) + 1
    if not kept:                     # one enormous line still gets shown, cut
        kept = [lines[0][:MIRROR_SEARCH_MAX]]

    head = f"the last {hours}h of the mirror"
    if wanted:
        head += f", room matching '{wanted}'"
    head += f": {len(found)} line(s) matched, newest first"
    if len(kept) < len(found):
        head += f" - showing the newest {len(kept)}"
    return head + "\n\n" + "\n".join(kept)


def read_den(day: str = "", days: int = 1) -> str:
    """Removed on master's call - see the module docstring.

    Kept as a tombstone rather than deleted, because a stale prompt or a
    training habit will eventually call for it, and a clear refusal beats an
    AttributeError traceback that reads like the tool broke.
    """
    return ("I do not have the den's diary any more. That is master's private "
            "record of his own work and it is not about this server. I have my "
            "own diary (`read_diary`), the last 48 hours of my rooms "
            "(`search_mirror`) and my own sent lines (`read_said`) - all mine, "
            "all about here.")


def _diary_rel(day: str) -> str:
    """A legacy DAY file. Still read, never written again - see below."""
    return f"{LOCAL_DIARY}/{day}.md"


# ------------------------------------------------- my diary: one file a week
#
# Master, 2026-09-22: *"daries start a new file every week, with the last week's
# entries summarised at the start of each week. tghis way she wont have to read a
# massive file."*
#
# It was one file per DAY. The reading was never the problem - a window reads a
# bounded lookback - the problem was that a day grew all day, a week grew all
# week, and NOTHING ever condensed. A month in, "read my diary" means wading.
# So:
#
#     memory/diary/2026-W39.md
#       ## last week, in short     the week before, condensed, written for her
#       ## this week               her own lines, oldest at the bottom
#
# The head is the part that makes it scale - she opens the week and gets last
# week in SUMMARY plus this week whole. Entries carry their own date
# (`- **2026-09-22 20:23** ...`) because a week spans seven days and a bare
# HH:MM would be ambiguous, and because it makes a line parse the same in a week
# file and in a legacy daily one.
WEEK_FMT = "%G-W%V"                    # ISO year-week: 2026-W39
DIARY_HEAD = "## last week, in short"
DIARY_LEDGER = "## this week"
DIARY_ENTRY_RE = re.compile(
    r"^- \*\*(?:(\d{4}-\d{2}-\d{2}) )?(\d{2}:\d{2})\*\* (.*)$")
# Which hand wrote the head. The mechanical one goes in the moment the week file
# is created so a head ALWAYS exists; the summariser upgrades it in place when
# the free ladder answers. Marked rather than guessed, so the job knows not to
# spend a call twice.
HEAD_MARK = "<!-- head: {} -->"
MECHANICAL_HEAD_CHARS = 4000


def week_of(day: str = "") -> str:
    """The ISO week a day belongs to - `2026-W39`. Today by default."""
    day = (day or "").strip() or today()
    try:
        parsed = datetime.strptime(day, DATE_FMT)
    except ValueError:
        parsed = datetime.now()
    return parsed.strftime(WEEK_FMT)


def week_days(week: str) -> list[str]:
    """The seven dates of an ISO week, Monday first. [] if the key is junk."""
    try:
        monday = datetime.strptime(f"{week}-1", "%G-W%V-%u")
    except (ValueError, TypeError):
        return []
    return [(monday + timedelta(days=i)).strftime(DATE_FMT) for i in range(7)]


def prev_week(week: str) -> str:
    """The week before this one."""
    days = week_days(week)
    if not days:
        return ""
    return week_of((datetime.strptime(days[0], DATE_FMT)
                    - timedelta(days=7)).strftime(DATE_FMT))


def _week_rel(week: str) -> str:
    return f"{LOCAL_DIARY}/{week}.md"


def _entries(text: str) -> list[tuple[str, str, str]]:
    """(day, time, body) for every entry line. Day is "" in a legacy file."""
    out = []
    for line in (text or "").splitlines():
        match = DIARY_ENTRY_RE.match(line.strip())
        if match:
            out.append((match.group(1) or "", match.group(2), match.group(3)))
    return out


def week_material(week: str) -> str:
    """Everything written in one week: the week file, or its legacy days.

    The week before the first week file has no week file - it is daily files on
    disk - so a summary has to be able to read THOSE, or the first week of the
    new shape opens with an empty head and the whole point is lost.
    """
    body = paths.read_text(_week_rel(week), default="")
    if body.strip():
        return body.strip()
    chunks = []
    for day in week_days(week):
        legacy = paths.read_text(_diary_rel(day), default="")
        if legacy.strip():
            chunks.append(legacy.strip())
    return "\n\n".join(chunks)


def _mechanical_head(week: str) -> str:
    """A head made without a model: the entries themselves, newest kept.

    Deliberately dumb and deliberately there. A head that says "nothing written
    down" until a summariser gets round to it would be a lie for as long as the
    ladder is dry, and the ladder is free and sometimes empty.

    A week with no week file is read day by day, so each line gets the DATE from
    the file it came out of - a legacy line carries only a time, and a head full
    of `??` is not a record of anything.
    """
    body = paths.read_text(_week_rel(week), default="")
    if body.strip():
        entries = _entries(body)
    else:
        entries = []
        for day in week_days(week):
            legacy = paths.read_text(_diary_rel(day), default="")
            entries += [(d or day, t, b) for d, t, b in _entries(legacy)]
    if not entries:
        return "nothing written down that week."
    lines = [f"- {d or '??'} {t} {b}" for d, t, b in entries]
    body = "\n".join(lines)
    if len(body) > MECHANICAL_HEAD_CHARS:
        body = ("[...the older part of that week, in brief...]\n"
                + body[-MECHANICAL_HEAD_CHARS:])
    return body


def _week_header(week: str) -> str:
    """A brand new week file, head already in place."""
    days = week_days(week)
    span = f"{days[0]} to {days[-1]}" if days else week
    previous = prev_week(week)
    head = _mechanical_head(previous) if previous else \
        "nothing written down that week."
    return (f"# Diary - week {week} ({span})\n\n"
            f"{DIARY_HEAD}\n{HEAD_MARK.format('mechanical')}\n"
            f"{head}\n\n{DIARY_LEDGER}\n")


def head_needs_summary(week: str = "") -> bool:
    """Is this week's head still the dumb one? Cheap - one small read."""
    body = paths.read_text(_week_rel(week or week_of()), default="")
    if not body.strip():
        return True
    return HEAD_MARK.format("summary") not in body


def write_week_head(week: str, summary: str) -> str:
    """Put a written summary at the top of a week's file.

    This rewrites ONE block - the head - and never touches her entries. The
    diary lines below it are append-only, exactly as they were; the head is a
    summary of a finished week and is expected to be replaced once, by the
    summariser, after the mechanical one went in.
    """
    summary = (summary or "").strip()
    if not summary:
        return "nothing to put at the head"
    rel = _week_rel(week)
    body = paths.read_text(rel, default="")
    if not body.strip():
        body = _week_header(week)
    try:
        before, rest = body.split(DIARY_HEAD, 1)
        _, after = rest.split(DIARY_LEDGER, 1)
    except ValueError:
        return "this week's file is not in the shape I expected; left alone"
    new = (before + DIARY_HEAD + "\n" + HEAD_MARK.format("summary") + "\n"
           + summary + "\n\n" + DIARY_LEDGER + after)
    try:
        paths.write_text(rel, new, internal=True)
    except Exception as exc:
        return f"could not write the head: {exc.__class__.__name__}"
    return f"week {week}: head written"


# --------------------------------------------------------------- my mood
# A mood I keep myself: one word, one line of why, and a short history of how
# it drifted. It lives at mood.json in my own folder - ordinary files, not
# memory/ (that store is sealed against me on purpose). I set it with set_mood
# whenever it actually changes, and every turn injects it back to me so my
# voice matches how I am, in every room.

MOOD_REL = "mood.json"
MOOD_HISTORY_MAX = 20


def read_mood() -> dict:
    """My current mood, or {} when I have never set one."""
    try:
        data = paths.read_json(MOOD_REL, default=None)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def set_mood(mood: str, note: str = "") -> str:
    """Record a new mood and what moved it. Mine to call, whenever it changes."""
    word = _clean(mood)
    if not word:
        return "a mood needs at least a word"
    # Master, 2026-09-21: the why is not optional - it is the point. A mood
    # without a reason is just a label, and next turn she will not know what
    # moved her. One sentence, her own.
    why = _clean(note)[:300]
    if not why:
        return ("say WHY it moved, in one sentence of your own - the why is "
                "what comes back to you when you next reply, so your tone "
                "knows where it came from")
    why = _clean(note)[:300]
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    current = read_mood()
    previous = current.get("mood", "")
    if previous == word:
        return f"already {word} - no change"
    history = current.get("history") or []
    if previous:
        history.append({"mood": previous, "note": current.get("note", ""),
                        "until": stamp})
    history = history[-MOOD_HISTORY_MAX:]
    data = {"mood": word, "note": why, "since": stamp,
            "history": history}
    try:
        paths.write_json(MOOD_REL, data, internal=True)
    except Exception as exc:
        return f"could not set the mood: {exc.__class__.__name__}"
    was = f" (was: {previous})" if previous else ""
    return f"mood set{was}: {word}" + (f" - {why}" if why else "")


def mood_block() -> str:
    """One short line for the prompt, or '' when I never set a mood."""
    data = read_mood()
    if not data.get("mood"):
        return ""
    line = f"my current mood: {data['mood']}"
    if data.get("note"):
        line += f" - {data['note']}"
    return line


def write_diary(text: str) -> str:
    """Append a line to this week's diary.

    Mine to write, and about here only. Masked on the way in with the same
    redactor the journal uses, so a credential-shaped string cannot land in it.
    """
    body = _clean(redact(text or ""))
    if not body or body == "[redacted]":
        return "nothing to write at that"
    day = today()
    week = week_of(day)
    try:
        rel = _week_rel(week)
        existing = paths.read_text(rel, default="")
        if not existing.strip():
            existing = _week_header(week)
        stamp = f"{day} {datetime.now().strftime('%H:%M')}"
        line = f"- **{stamp}** {body}\n"
        paths.write_text(rel, existing.rstrip("\n") + "\n" + line, internal=True)
    except Exception as exc:
        return f"could not write it: {exc.__class__.__name__}"
    return f"noted in my diary for {week}"


# ------------------------------------------------- suggestions, master's voice in my diary
# Master, 2026-09-23: *"add a suggestions tool, i can add a suggestion to her
# diary for her to work on something."* A suggestion is HIS line in MY diary -
# a thing he wants me to consider with my own time. It is just a diary entry,
# tagged, so the window brief already carries it and no new feed, injection or
# read has to exist for it to be seen: she reads the diary before every window.
# Tagged rather than plain so a suggestion never reads as something I wrote
# about myself, and so she can pick one up on purpose.

SUGGEST_TAG = "suggestion from {who}:"


TOPICS_REL = "research/topics.md"
_TOPICS_SECTION = "## From conversations"
TOPICS_DEDUPE_RATIO = 0.82


def topics_tail(limit: int = 14) -> str:
    """The tail of my topics list, for a tool that offers it back to me.

    The freetime skill reads the whole file in a window; this is the small
    view a chat turn gets, so a queued topic is not queued twice.
    """
    body = paths.read_text(TOPICS_REL, default="")
    lines = [l for l in body.splitlines() if l.strip()]
    return "\n".join(lines[-limit:])


def note_topic(topic: str, who: str = "", room: str = "",
               server: str = "", uid: str = "") -> str:
    """One conversation-seeded topic into research/topics.md.

    NOT a suggestion and not forced: the queue_topic TOOL is offered to me
    in every turn, and I call it when a conversation genuinely intrigues
    me - master, 2026-09-24. The line carries WHO said the thing and WHERE,
    plus the log pointer (journal day + room), so a freetime window can go
    back to the actual conversation before writing about it.
    """
    topic = (topic or "").strip().splitlines()[0][:300] if (topic or "").strip() else ""
    if not topic:
        return "nothing to queue"
    speaker = who or "someone"
    day = today()
    where = f"in #{room}" if room else "in a DM"
    back = f"journal {day}"
    if uid:
        # The speaker's own stores: per-person chains (the actual
        # conversation, DMs included - the journal only holds public rooms)
        # and their dossier/facts in the people ledger, master 2026-09-24.
        back += f", chains + ledger: memory/people/{str(uid)}.json"
    entry = (f"- **{time.strftime('%Y-%m-%d %H:%M')}** (from {speaker}, {where}) "
             f"- {topic} - back: {back}")
    body = paths.read_text(TOPICS_REL, default="")
    # Dedupe: the same intrigue said twice must not queue twice. Loose match
    # on the topic text only, so a rephrase still lands as one topic.
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("- **") and " - " in line:
            existing = line.split(" - ", 1)[1].rsplit(" - back:", 1)[0]
            low_e, low_t = existing.lower(), topic.lower()
            shared = set(re.findall(r"[a-z0-9']+", low_t)) & \
                set(re.findall(r"[a-z0-9']+", low_e))
            if difflib.SequenceMatcher(None, low_t, low_e).ratio() \
                    >= TOPICS_DEDUPE_RATIO or len(shared) >= 3:
                return f"already on the list: {existing[:120]}"
    if _TOPICS_SECTION not in body:
        entry = f"\n{_TOPICS_SECTION}\n\n{entry}"
    with paths.resolve(TOPICS_REL).open("a", encoding="utf-8") as handle:
        handle.write(entry + "\n")
    return f"queued for a future window: {topic[:160]} (from {speaker}, {where})"


def add_suggestion(text: str, who: str = "") -> str:
    """Write a suggestion into this week's diary as a tagged entry.

    Same masking, same file, same week, same line format as write_diary - the
    only difference is the tag saying whose voice it is. Returns write_diary's
    answer so the caller can pass it straight back to master.
    """
    tag = (who or "").strip() or "master"
    return write_diary(f"[{SUGGEST_TAG.format(who=tag)}] {text}")


def diary_mark() -> str:
    """A cheap fingerprint of the week's diary, for noticing whether it moved.

    Exists for one caller: the free-time window, which now ENFORCES the diary
    write instead of asking for it. It counts entries AND bytes, because either
    alone can lie - a rewrite that adds no line still moves the bytes, and an
    entry added to a file that lost a stray newline can leave the bytes equal.
    """
    body = paths.read_text(_week_rel(week_of()), default="")
    return f"{len(_entries(body))}:{len(body)}"


def _clip_week(body: str, limit: int) -> str:
    """A week, capped - and the NEWEST lines are the ones that survive.

    `body[:limit]` would keep the head and then the OLDEST entries, which is the
    exact mistake read_journal made (it answered "who talked to me today" from
    the small hours). The head always stays whole, because it is already a
    summary; what gets trimmed is the week's own lines, from the top.
    """
    body = body.strip()
    if len(body) <= limit:
        return body
    if DIARY_HEAD not in body or DIARY_LEDGER not in body:
        return ("[...the older part of this file is not shown...]\n\n"
                + body[-limit:])
    head, rest = body.split(DIARY_HEAD, 1)
    head_body, ledger = rest.split(DIARY_LEDGER, 1)
    room = limit - len(head) - len(DIARY_HEAD) - len(head_body) \
        - len(DIARY_LEDGER) - 120
    tail = ledger.strip()
    if room <= 0:
        return (head + DIARY_HEAD + head_body + DIARY_LEDGER
                + "\n[...this week's own lines did not fit in this read...]")
    if len(tail) > room:
        cut = tail[-room:]
        newline = cut.find("\n")
        if newline != -1:
            cut = cut[newline + 1:]
        tail = ("[...the earlier part of this week is not shown...]\n\n"
                + cut)
    return head + DIARY_HEAD + head_body + DIARY_LEDGER + "\n" + tail


def read_diary(day: str = "", limit: int = MAX_READ_CHARS) -> str:
    """My diary. The week in progress by default, with last week in short on top.

    `limit` is the caller's ceiling, and it is a parameter because the TOOL and
    the free-time window want different ones: the tool answers one question and
    6000 characters is plenty, while a window opens with the whole lookback in
    front of it. A day still reads as a day - and a day from before the weekly
    shape still reads, out of the legacy file it was written in.
    """
    day = (day or "").strip()
    if day and not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", day)
                    or re.fullmatch(r"\d{4}-W\d{2}", day)):
        return "that is not a date - use YYYY-MM-DD, or a week like 2026-W39"
    limit = max(int(limit), 0)
    if re.fullmatch(r"\d{4}-W\d{2}", day):
        body = paths.read_text(_week_rel(day), default="")
        if not body.strip():
            return f"{day}: I have written nothing down in that week"
        return _clip_week(body, limit)
    if day:
        return _read_day(day, limit)
    week = week_of()
    body = paths.read_text(_week_rel(week), default="")
    if not body.strip():
        return f"{week}: I have written nothing down this week yet"
    return _clip_week(body, limit)


def _read_day(day: str, limit: int) -> str:
    """One day: out of its week file if it is there, else its legacy file."""
    lines = [f"- **{t}** {b}"
             for d, t, b in _entries(paths.read_text(_week_rel(week_of(day)),
                                                     default=""))
             if d == day]
    if not lines:
        lines = [f"- **{t}** {b}"
                 for _, t, b in _entries(paths.read_text(_diary_rel(day),
                                                         default=""))]
    if not lines:
        return f"{day}: I wrote nothing down"
    return (day + "\n" + "\n".join(lines))[:limit]


def who_today(day: str = "") -> str:
    """The people I talked to, counted off my own journal."""
    day = day.strip() or today()
    body = _day_body(day)
    if not body:
        return f"nobody - my journal for {day} is empty"

    names: dict[str, int] = {}
    for line in body.splitlines():
        match = re.match(r"- \*\*\d{2}:\d{2}\*\* ([^:]+?)(?: in #|:)", line)
        if match:
            name = match.group(1).strip()
            names[name] = names.get(name, 0) + 1

    if not names:
        return f"entries for {day}, but no names I can pick out"
    ranked = sorted(names.items(), key=lambda kv: kv[1], reverse=True)
    return ", ".join(f"{n} ({c})" for n, c in ranked)
