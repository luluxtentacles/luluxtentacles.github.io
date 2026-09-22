"""Why she went down, and what was done to her while she was down.

Two of the things she is told rather than told-off about, both as PLAIN
FUNCTIONS on purpose: the smoke net walks every branch of them with no live
gateway, and a branch nobody can exercise is a branch nobody can trust.

  restart_sentence / restart_context_note
      the same reason file, said twice for two different readers - the room gets
      a line, and SHE gets the version with the job still attached to it
  resume_brief
      master's own words, handed back to the room he said them in, once
  _changelog_entries / changelog_news / changelog_block
      what was done to her, split into entries so WHICH ones she has read can be
      tracked - an entry, not the file, is the smallest unit that can be read

Moved out of lulu_bot.py on 2026-09-22 (lulu_bot had hit its reader cap; see
CHANGELOG.md). What did NOT move are the four PATH constants - CHANGELOG_FILE,
CHANGELOG_SEEN_FILE, REASON_FILE and SEEN_FILE. They stayed defined in
lulu_bot.py deliberately: the smoke net REDIRECTS them into a sandbox by
rebinding lulu_bot.<name>, and a rebound name is only ever seen by code that
reads it through lulu_bot. Nothing in this module reads a path.

lulu_bot.py imports all of this back by name, so every caller in her body still
says lulu_bot.restart_sentence.
"""
from __future__ import annotations

from bot_text import escape_block

# How stale a "tell them I'm back" note may be before it is dropped. A note
# older than this belongs to a restart that happened and did not come up, and
# announcing it hours later would be a message out of nowhere.
RESTART_NOTICE_MAX_AGE = 30 * 60

# How much of the continuation brief is repeated back into the ROOM. The model
# gets the whole thing in its own turn; the room gets a marker, because what
# master asked for is not usually the room's business and quoting him into a
# public channel is not mine to do.
RESTART_BRIEF_ECHO_MAX = 500

# How many entries one turn may be handed, and the block's budget in characters.
#
# These were 3 and 4,000, and a crawl is the wrong shape for a bad day: a long
# day out-runs three entries per boot, so she spends hours quoting a claim the
# very NEXT entry retracts - reading perfectly faithfully, and wrong out loud.
# Master, 2026-09-21: "she needs to catch up can we just dump it all on her as
# many as we can and then keep going if it doesnt fit". So this is a catch-up
# ceiling now, not a drip.
#
# It still HAS one, for the reason it always did: this rides on a turn until it
# is read, so it cannot be unbounded. The number is measured against the real
# file rather than guessed - the 25-entry backlog she was stuck behind is 61,383
# characters, about 15k tokens, which is small next to her window (a room is
# 128k, her DM is 1M) - so 80,000 characters drains any realistic backlog in ONE
# turn. Anything past it is not lost and not skipped: the marker stops at the
# last entry actually handed over, so the rest comes on the next turn.
CHANGELOG_MAX_ENTRIES = 40
CHANGELOG_MAX_CHARS = 80_000

# A crash loop must not become one message per attempt.
CRASH_ANNOUNCE_COOLDOWN = 15 * 60
# How long after one resume turn another may run. A resume turn is a brain call
# I start myself, and a patch it stages restarts me - so without a leash,
# "continue my work" is also a loop that turns over once per restart. 180s is the
# gap self_review uses before it resumes a window, and for the same reason: the
# restart has to have actually happened before the next turn starts.
RESUME_TURN_COOLDOWN = 180


def restart_sentence(reason: dict, requested_why: str = "") -> str:
    """What to say about why I am back, in my own voice.

    A plain function so the smoke test can walk every kind without a live
    gateway. The kinds are the supervisor's: startup, crashed, exited,
    restart-requested, running-new-code, patch-reverted. `startup` returns an
    empty string on purpose - a box reboot is the most frequent start of all and
    is not news, so it stays silent the way it always was.
    """
    kind = str(reason.get("kind") or "")
    why = str(reason.get("why") or "").strip() or str(requested_why or "").strip()
    files = ", ".join(reason.get("files") or [])
    sha = str(reason.get("sha") or "").strip()
    code = reason.get("exit_code")

    if kind in ("patch-applied", "running-new-code"):
        text = f"back, and this time on new code: {files or 'a patch'}"
        if sha:
            text += f" (checkpoint {sha})"
        return text + (f". i asked for it: {why}" if why else ".")
    if kind == "patch-reverted":
        return ("back on the OLD code - the supervisor tried my patch, judged it, "
                f"and put everything back. {why or 'it failed the checks'}")
    if kind == "crashed":
        # The code is optional on purpose. `restart_context_note` always guarded
        # this; this line did not, so a reason file with no exit_code field - an
        # old supervisor, or any writer that forgot - came out as "i died in
        # there (exit code None)" and she said that in a room. A parenthetical
        # that cannot be filled is worse than no parenthetical.
        return ("i died in there"
                + (f" (exit code {code})" if code is not None else "")
                + " and the supervisor started me again. nobody asked for that "
                + (f"one: {why}" if why else "one."))
    if kind == "restart-requested":
        return f"back. i asked to be bounced: {why or 'no reason given'}"
    if kind == "exited":
        return ("back. i shut down on my own"
                + (f" (exit code {code})" if code is not None else "") + ".")
    if kind == "startup":
        return ""
    return "back. the supervisor started me."


def restart_context_note(reason: dict, requested_why: str = "") -> str:
    """Why I went down, as something I am HANDED rather than something I posted.

    A plain function like restart_sentence above and for the same reason: the
    smoke net walks every branch with no live gateway.

    The restart sentence already goes into a room and into master's DM. This is a
    different job, and master asked for both on 2026-09-21: "make sure she gets
    handed why she restarted as a turn though with full context". A line I posted
    and then forgot tells me nothing about why I am not the me I was a minute
    ago, and it says nothing at all about the thing I was in the middle of.

    The kind that matters most is a reverted patch, because it now has a next
    step that is not "try again". Master, 2026-09-21: "she can try patch herself
    for something she needs to use, but if the supervisor reverts it she just
    puts it in proposal and dms me so we can do it for her."
    """
    kind = str(reason.get("kind") or "")
    if kind in ("", "startup"):
        # A box reboot is the most frequent start of all and is not news, here
        # exactly as much as in restart_sentence.
        return ""
    why = str(reason.get("why") or "").strip() or str(requested_why or "").strip()
    files = ", ".join(reason.get("files") or []) or "a patch"
    sha = str(reason.get("sha") or "").strip()
    code = reason.get("exit_code")

    if kind == "patch-reverted":
        lines = [
            "You have just come back up and you are on the OLD code: a patch of "
            f"your own went in, was judged, and was put back. Files: {files}"
            + (f" (the checkpoint it made first was {sha})" if sha else "") + ".",
        ]
        if why:
            lines.append(f"What you said you wanted from it: {why}")
        lines.append(
            "Your attempt is filed WITH ITS REASON under pending/rejected/ - the "
            "newest folder there is yours, and the REASON.txt in it says what the "
            "smoke test or the health check objected to. Read that before you "
            "decide anything; reading why it failed beats a second guess at it.")
        lines.append(
            "Do NOT stage that patch again. Master's rule, 2026-09-21: you may "
            "patch yourself for something you actually need to USE, but when one "
            "comes back reverted the next move is a PROPOSAL, not another "
            "attempt - write it into research/proposals.md saying plainly what it "
            "is for, and DM master about it. He would rather build it WITH you "
            "than watch you lose the same fight twice.")
        return "\n".join(lines)

    if kind in ("patch-applied", "running-new-code"):
        return ("A patch of yours was applied, so you are running new code now: "
                f"{files}"
                + (f" (checkpoint {sha})" if sha else "")
                + (f". What it was for: {why}" if why else ".")
                + "\nThe changelog note in this same turn says what actually "
                  "changed in you - go by that rather than by the diff in your "
                  "head, which is the version that was never applied.")

    if kind == "crashed":
        return ("Nobody asked for this one: you died in there"
                + (f" (exit code {code})" if code is not None else "")
                + " and the supervisor started you again."
                + (f" What was recorded: {why}" if why else "")
                + "\nAnything you were only holding in your head is gone. If a "
                  "turn was open, say where it actually got to instead of "
                  "starting it over as though it were new.")

    if kind == "restart-requested":
        return ("You asked to be bounced"
                + (f", because: {why}" if why else "; no reason was recorded")
                + ".")

    if kind == "exited":
        return ("You shut down on your own"
                + (f" (exit code {code})" if code is not None else "") + ".")

    return f"The supervisor started you again ({kind})."


def resume_brief(note, channel_name: str = "") -> str:
    """What master asked for before I went down, or "" if there is nothing.

    A plain function, like restart_sentence above and for the same reason: the
    smoke net walks every branch without a live gateway.

    Returns the whole note the first time a turn runs in the room it names, so
    the next thing that comes out of my mouth is the job I was already on, and
    then nothing. The wrong room is worse than no reminder, because it would
    have me answering a question nobody asked HERE.

    An empty name means master's DM - a DM channel has no name, and that is
    where a private ask comes from. Comparing the two keys as plain strings is
    what keeps the two cases apart: an empty note can never fire in a guild
    room, and a note from #lulu-den can never fire in his DMs.

    The brief is master's own words, so it is escaped like any line on its way
    into a prompt - the fact that it is mine and sealed does not make it
    trusted, it only makes it not-forged.
    """
    if not isinstance(note, dict):
        return ""
    asked = str(note.get("brief") or "").strip()
    if not asked:
        return ""
    where = str(note.get("channel") or "").strip().lstrip("#").lower()
    here = str(channel_name or "").strip().lstrip("#").lower()
    if where != here:
        return ""
    return escape_block(asked)


def _changelog_entries(text) -> list[dict]:
    """The changelog split into entries at its `## ` headings.

    An entry is a heading plus everything under it until the next heading. Kept
    structurally rather than as one blob because the thing being tracked is WHICH
    entries have been read, and an entry is the smallest unit that can be read.
    """
    entries: list[dict] = []
    current: dict | None = None
    for line in str(text or "").splitlines():
        if line.startswith("## "):
            if current is not None:
                entries.append(current)
            current = {"heading": line[3:].strip(), "lines": []}
        elif current is not None:
            current["lines"].append(line)
    if current is not None:
        entries.append(current)
    for index, entry in enumerate(entries):
        entry["index"] = index
        entry["body"] = "\n".join(entry.pop("lines")).strip()
    return entries


def changelog_news(text, seen, limit: int = CHANGELOG_MAX_ENTRIES):
    """What was done to me since I last read, and the marker that says so.

    Returns (entries, marker, more). The marker names the last entry being handed
    over, so anything left is picked up on the NEXT start rather than skipped -
    a changelog that can silently drop its own entries is worse than no
    changelog, because it reads as complete.

    An append keeps its place. If the marker does not line up - the file was
    rewritten, or the count went backwards - the newest few are shown instead of
    the whole history, because a marker that has lost its place must degrade to
    "here is what is recent", never to "here is everything" or to silence.
    """
    entries = _changelog_entries(text)
    if not entries:
        return [], dict(seen or {}), False
    # `-0` is `0` in Python, so a limit of zero would silently mean "all of it".
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = CHANGELOG_MAX_ENTRIES

    count, last = 0, None
    if isinstance(seen, dict):
        try:
            count = int(seen.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        last = seen.get("last")

    in_order = (count > 0 and count <= len(entries)
                and entries[count - 1]["heading"] == last)
    if in_order:
        unread = entries[count:]
    else:
        # The marker lost its place - the file was rewritten, or the count went
        # backwards. Show the newest few and land on the present; deliberately
        # NOT the whole history, and deliberately not the oldest.
        unread = entries[-limit:]

    if not unread:
        return [], dict(seen or {}), False

    shown: list[dict] = []
    used = 0
    for entry in unread:
        size = len(entry["heading"]) + len(entry["body"])
        # The first one always goes, however big: a single oversized entry must
        # not wedge the queue forever. The rest wait for the next start.
        if shown and (len(shown) >= limit or used + size > CHANGELOG_MAX_CHARS):
            break
        shown.append(entry)
        used += size

    marker = {"count": shown[-1]["index"] + 1, "last": shown[-1]["heading"]}
    # "More" means there is an entry she has NOT been handed over. Two ways that
    # happens: the block stopped early while reading in order (those arrive on the
    # next start), or the marker lost its place and everything older was skipped
    # - so point her at the file rather than letting a blind spot read as
    # completeness. Counting from the marker outward covers both: `covered` is
    # what she has already been told about, or nothing when the marker is no use.
    more = len(entries) - (count if in_order else 0) - len(shown) > 0
    return shown, marker, more


def changelog_block(entries, more: bool = False) -> str:
    """The entries as one block for the prompt, escaped like any other.

    Mine, and tracked by git, but it still goes through escape_block: what
    reaches a prompt is escaped on the way in, and an exception here would be the
    kind that only bites the day one of us forgets why the rule exists.
    """
    parts = []
    for entry in entries:
        heading = f"## {entry.get('heading') or ''}".strip()
        body = entry.get("body") or ""
        parts.append(f"{heading}\n{body}" if body else heading)
    text = escape_block("\n\n".join(parts))
    if more:
        text += ("\n\n(there is more after this - read_file CHANGELOG.md for "
                 "the rest)")
    return text
