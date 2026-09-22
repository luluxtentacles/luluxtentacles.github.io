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

import re
from datetime import date, datetime, timedelta

import paths

LOCAL_DIARY = "memory/diary"
LOCAL_REL = "memory/journal"

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
def _local_rel(day: str) -> str:
    return f"{LOCAL_REL}/{day}.md"


def note(text: str, *, speaker: str = "", channel: str = "") -> None:
    """Append one line about today to my own journal.

    Never raises: a journal is a record, not a dependency. If it cannot be
    written the conversation carries on and the failure is swallowed, exactly
    like the memory writes beside it.
    """
    try:
        body = _clean(redact(text or ""))
        if not body or body == "[redacted]":
            return
        day = today()
        where = f" in #{channel}" if channel else ""
        who = _clean(speaker) or "someone"
        line = f"- **{datetime.now().strftime('%H:%M')}** {who}{where}: {body}\n"

        rel = _local_rel(day)
        existing = paths.read_text(rel, default="")
        if not existing:
            existing = f"# Journal - {day}\n\n"
        paths.write_text(rel, existing + line, internal=True)
    except Exception:
        return


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
        body = paths.read_text(_local_rel(d), default="")
        blocks = [b.strip() for b in re.split(r"^## ", body, flags=re.M)[1:]]
        out.append("\n\n".join("## " + b for b in blocks) if blocks
                   else f"{d}: no digest written")
    return "\n\n".join(out)[:MAX_READ_CHARS]


def _clip(body: str, limit: int = MAX_READ_CHARS) -> str:
    """A day trimmed to `limit`, keeping the start AND the newest part."""
    if len(body) <= limit:
        return body
    head = max(0, limit // 3)
    tail = limit - head - len(CUT_MARK)
    if tail <= 0:
        return body[:limit]
    return body[:head].rstrip() + CUT_MARK + body[-tail:].lstrip()


def read_journal(day: str = "") -> str:
    """My journal for a day, most recent entry last."""
    day = day.strip() or today()
    body = paths.read_text(_local_rel(day), default="")
    if not body:
        return f"nothing in my journal for {day}"
    return _clip(body)


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

MIRROR_WINDOW_HOURS = 48    # master's window, and the only one a search offers
MIRROR_KEEP_DAYS = 3        # day files kept, so a 48h window is always whole
MIRROR_LINE_MAX = 2000      # the send limit, not MAX_LINE - see note_said
MIRROR_SEARCH_MAX = 6000    # characters one search returns, newest first


def _mirror_rel(day: str) -> str:
    return f"{LOCAL_MIRROR}/{day}.md"


def note_mirror(author: str, text: str, *, room: str = "") -> None:
    """Write down one line of a room - who, where, what. Never raises.

    Same contract as note() and note_said(): a record, not a dependency. If it
    cannot be written the conversation carries on and the failure is swallowed.

    The room is named on the line because the file is a whole DAY, not a whole
    channel, so a line without its room could not be placed. A DM has no name and
    says so rather than guessing at one.
    """
    try:
        body = _one_line(text, MIRROR_LINE_MAX)
        if not body or body == "[redacted]":
            return
        who = _clean(author) or "someone"
        name = _clean(room).lstrip("#").strip()
        where = f"[#{name}]" if name else "[no room]"
        day = today()
        rel = _mirror_rel(day)
        existing = paths.read_text(rel, default="")
        if not existing:
            existing = f"# Mirror - {day}\n\n"
            # The first line of a new day is the moment to let the old ones go:
            # pruning here needs no timer and no loop, and three files covers the
            # window from any hour of any day. Only what has already fallen out
            # of it is ever touched.
            _prune_mirror()
        line = (f"- **{datetime.now().strftime('%H:%M')}** {where} "
                f"{who}: {body}\n")
        paths.write_text(rel, existing + line, internal=True)
    except Exception:
        return


def _prune_mirror(keep_days: int = MIRROR_KEEP_DAYS) -> int:
    """Delete the day files that have fallen out of the window.

    Whole DAYS leave, which is why the default is 3 and not 2: a day file has to
    stay while any part of it could still be inside the window, and the window is
    counted in hours from now, not in midnights.
    """
    removed = 0
    try:
        folder = paths.resolve(LOCAL_MIRROR)
        if not folder.is_dir():
            return 0
        oldest_kept = shift(today(), -(keep_days - 1))
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


def _mirror_entries(day: str) -> list[tuple[str, str, str]]:
    """(time, [room], rest) for every line in a day's mirror, in file order."""
    out = []
    body = paths.read_text(_mirror_rel(day), default="")
    for line in body.splitlines():
        match = re.match(r"^- \*\*(\d{2}:\d{2})\*\* (\[[^\]]*\]) (.*)$", line)
        if match:
            out.append((match.group(1), match.group(2), match.group(3)))
    return out


def search_mirror(query: str = "", hours: int = MIRROR_WINDOW_HOURS,
                  room: str = "") -> str:
    """Search the last `hours` of the mirror by keyword, newest line first.

    Every word in the query has to appear on the line, so two words ask a
    narrower question than one. `room` narrows it to a single room, spelled
    however I spell it. The window is master's 48 hours; asking for longer is
    capped rather than refused, because the files do not go back further and a
    refusal would say nothing about where the edge actually is.
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

    found: list[tuple[datetime, str]] = []
    for offset in range(MIRROR_KEEP_DAYS):
        day = shift(today(), -offset)
        for at, where, rest in _mirror_entries(day):
            if not _in_window(day, at, cutoff):
                continue
            if wanted and wanted not in where.lower():
                continue
            line = f"- **{day} {at}** {where} {rest}"
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
            "own diary (`read_diary`) and my journal (`read_journal`) - both "
            "mine, both about here.")


def _diary_rel(day: str) -> str:
    return f"{LOCAL_DIARY}/{day}.md"


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
    """Append a line to today's diary.

    Mine to write, and about here only. Masked on the way in with the same
    redactor the journal uses, so a credential-shaped string cannot land in it.
    """
    body = _clean(redact(text or ""))
    if not body or body == "[redacted]":
        return "nothing to write at that"
    day = today()
    try:
        rel = _diary_rel(day)
        existing = paths.read_text(rel, default="")
        if not existing:
            existing = f"# Diary - {day}\n\n"
        line = f"- **{datetime.now().strftime('%H:%M')}** {body}\n"
        paths.write_text(rel, existing + line, internal=True)
    except Exception as exc:
        return f"could not write it: {exc.__class__.__name__}"
    return f"noted in my diary for {day}"


def read_diary(day: str = "") -> str:
    """My own diary. Today by default, and yesterday with it."""
    day = (day or "").strip()
    if day and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        return "that is not a date - use YYYY-MM-DD"
    wanted = [day] if day else [today(), shift(today(), -1)]
    out = []
    for d in wanted:
        body = paths.read_text(_diary_rel(d), default="")
        out.append(body.strip() if body else f"{d}: I wrote nothing down")
    return "\n\n".join(out)[:MAX_READ_CHARS]


def who_today(day: str = "") -> str:
    """The people I talked to, counted off my own journal."""
    day = day.strip() or today()
    body = paths.read_text(_local_rel(day), default="")
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
