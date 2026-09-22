"""My Discord diary, and my Discord journal - both mine, both inside the wall.

    memory/diary/<date>.md           my diary. What happened to me here, in my
                                     own words.
    memory/journal/<date>.md         the raw record: who spoke, which channel,
                                     what was said. Everyone, not just master.

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
