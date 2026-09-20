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


def read_journal(day: str = "") -> str:
    """My journal for a day, most recent entry last."""
    day = day.strip() or today()
    body = paths.read_text(_local_rel(day), default="")
    if not body:
        return f"nothing in my journal for {day}"
    return body[:MAX_READ_CHARS]


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
    word = word[:40]
    why = _clean(note)[:200]
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
