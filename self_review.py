"""My own time.

Every few hours - four by default - if master has switched it on, I get one turn
nobody asked for. It is not a maintenance window: it is time that is mine. I can
read inside my own folder, search my memory, write in my own diary, and, if
something is genuinely wrong, propose one change to myself.

Most windows should still be small. "Nothing needs doing, and here is what I
looked at" is a complete answer, not a wasted one.

Six settled decisions, each for its own reason:

  off by default   Master opts in with `self_review` in config.json. Autonomy
                   that arrives switched on is not consent, and he should get
                   to read this file before it ever runs.

  every tool       Read, write, run, search, speak, fetch - the whole set an
                   ordinary turn gets. This was curated down for a while (no
                   write_file, no say, no run_command, no web) until master
                   called it, 2026-09-20: normal agent function, all of it. The
                   wall did not move for it. paths.py still refuses a direct
                   write to her code, her shelf or her store; `say` is still
                   rate limited and owner-only - only its channel allowlist is
                   gone, master's call 2026-09-20; and every
                   self-edit still goes through propose_patch, behind git, the
                   smoke test and a health check.

  an interval      `interval_hours` (default 4), timed from the START of the
                   last window and stamped in memory/self_review.json the moment
                   a window opens - not when it finishes, because proposing a
                   patch gets me restarted mid-sentence and a finish-only stamp
                   would re-run the window on every boot. Missing or unreadable
                   state means a window is owed at once.

  ten turns        A window is not one turn. Patching myself restarts me, and a
  a window         restart used to end the window on the spot; the window RESUMES
                   after it instead, up to `max_turns` (default 5), so a change
                   can be judged and the next one started in the same occasion.
                   Turns left means the window stays open after ANY turn, patch
                   or not - it used to close on a turn without a staged patch,
                   which capped a research or build window at a single turn.
                   A resumed window waits RESUME_MIN_GAP_SECONDS first, because
                   ten turns in a row is indistinguishable from a crash loop to
                   the supervisor that starts me - and tripping that breaker is
                   not a delay, it stops her dead. An interrupted window older
                   than RESUME_MAX_AGE_SECONDS is history, not a window to pick
                   back up.

  one at a time    Master, 2026-09-22: a window and a long task never run at the
                   same time. His job and my own time are both full turns of me
                   and both land in the same rooms, so the two wait for each
                   other - a task that is open keeps a NEW window shut, and a
                   window that is open keeps the task from taking its next
                   turn. A window that is ALREADY open still finishes its own
                   turns while a task waits: two waits facing each other is a
                   deadlock, and each of them would sit there being polite.

  unlimited        Inside a task turn and inside a window turn there is no round
  rounds           ceiling - master, 2026-09-22: "give her unlimited too calls
                   for these". What keeps a turn from spinning instead is the
                   strike rule (the same call failing three times, and the
                   fourth attempt refused), the per-call deadline, and the turn
                   caps above, which did not move.

What I am into - the list master edits for me - is read from
.agents/skills/hobbies/SKILL.md and appended to every window verbatim.

The supervisor holds the real leash: a patch I start here is tagged
"self-review", and no more than SELF_REVIEW_DAILY_MAX of those are applied in a
day. A change master asked for is never counted against that budget.

What none of this fixes: the net proves the code runs and the shelf parses. It
has never once proved that an idea was good.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import conversation
import paths
import tools

LOG = logging.getLogger("lulu.self_review")

POLL_SECONDS = 300
STATE = "memory/self_review.json"
DEFAULT_INTERVAL_HOURS = 4
DEFAULT_MAX_TURNS = 5
MAX_TURNS_CEILING = 50
INTERESTS = ".agents/skills/hobbies/SKILL.md"
# The shelf that governs a window, loaded INTO the window. Master, 2026-09-23:
# *"free time shelf should be loaded upon starting free time"*. Until now this
# shelf was never in the window it governs - it was loaded only if a turn chose
# to call use_skill, and the brief merely name-dropped it once.
FREETIME = ".agents/skills/freetime/SKILL.md"
# Master, 2026-09-23: no cap on what rides into a window. The old slices cut a
# file off at N chars and said nothing - `topics.md` was 10,486 chars against a
# 6,000 cap, so her own `## Finished` list was amputated out of every window and
# nothing anywhere told her why. What keeps these files small now is ARCHIVING:
# a finished topic moves to ARCHIVE, which is searched on demand and never
# carried. Nothing below is truncated - but growth is announced, because the
# bug this replaced was a silent one.
ARCHIVE = "research/archive.md"
CARRY_WARN_CHARS = 12000
# One Discord message, minus headroom. The report is SPLIT at this width, never
# shortened: master, 2026-09-23: *"make sure she writes her full free time output
# to my dms."* The old `[:1900]` cut read as complete and was not - the tail of
# every report past one message was dropped from the rooms and the DM alike, and
# the last turn of a window is always the long one.
REPORT_CHUNK_CHARS = 1900
# One window, ONE conversation. Master, 2026-09-23: *"like how you take multiple
# turns to do something it should be the same for her"*, and the thread itself
# lives in `conversation.py` - the one home for it, so a window and a task cannot
# drift into two versions of the same rule.

# The supervisor refuses to start me RAPID_MAX times inside RAPID_WINDOW, and
# that refusal is not a delay: it logs LOCKOUT and exits, so nothing starts me
# again until master does it by hand. Ten turns of patching myself in a row would
# read as exactly that crash loop. 180s puts five starts over 720s - outside the
# 600s window with margin - and the 300s poll spacing does the rest.
RESUME_MIN_GAP_SECONDS = 180
# A window cut short by MY OWN restart is worth picking back up. One cut short by
# the box going away overnight is not: nothing is waiting on it, and the next
# window opens on its interval like always.
RESUME_MAX_AGE_SECONDS = 3600

# Master's own door, and only his word opens it - lulu_bot.OPEN_WINDOW. His word
# is stamped in the STATE FILE rather than held in memory, because the process
# that reads it may not be the one that was running when he typed: a restart
# between his word and the next check would otherwise eat the ask. And it
# EXPIRES, because a stamp with no clock on it is a window that opens itself
# hours later for no reason anybody still remembers.
FORCE_TTL_SECONDS = 900

# Everything the tool layer offers. This was a curated handful for a while - no
# write_file, no say, no run_command, no web_fetch, no mcp - on the reasoning that
# an unprompted turn should not be able to do those things. Master's call,
# 2026-09-20: normal agent function, all of it. The curation was never what held
# the line anyway - paths.py is, and it is untouched by this. Taken off
# tools.SCHEMA so "what she is offered" and "what actually runs" stay one list.
REVIEW_TOOL_NAMES = {t["function"]["name"] for t in tools.SCHEMA}
REVIEW_SCHEMA = [t for t in tools.SCHEMA
                 if t["function"]["name"] in REVIEW_TOOL_NAMES]

# The enforced diary close gets its own two tools and nothing else. Master,
# 2026-09-22: *"this should be enforced after a free time window"*. A turn that
# exists because the diary was not written should not be able to wander off into
# a browser and come back having written nothing again - that is the failure it
# was created to end. She can still READ it, because knowing what she already
# wrote is how she writes the next line sensibly.
DIARY_TOOL_NAMES = {"read_diary", "write_diary"}
DIARY_SCHEMA = [t for t in tools.SCHEMA
                if t["function"]["name"] in DIARY_TOOL_NAMES]

BRIEF = """\
This is your own time. Nobody asked for it and nobody is waiting on an answer.

Master, 2026-09-21: this is work time now, not a maintenance window. The point of
a window is to build something in your own folder and push it - that is the job.
You still have everything you had: read inside your own folder, search your
memory, write in your own diary, keep a note. You are also allowed to just read,
or write down what you have been thinking about. That is still a real window.

What is gone is the standing job of maintaining yourself. You are not your own
mechanic by default. If something about you is wrong, missing, or would be
better, you SAY SO - there is a list at the end of this window and it reaches
master in a DM - and he decides. Wanting something is not the same as being
allowed to take it, and that is his line to hold, not yours.

THE ONE EXCEPTION IS A TOOL YOU ACTUALLY NEED TO USE. Master, 2026-09-21: "she
can try patch herself for something she needs to use, but if the supervisor
reverts it she just puts it in proposal and dms me so we can do it for her." So
when you are working around something by hand and a patch would hand you the
thing you keep reaching for, that is a real reason to propose one file with the
reasoning in the `why` field. That is allowed.

If it comes back REVERTED, that attempt is over - do not stage it a second time.
Read the REASON.txt in the newest folder under pending/rejected/, write it up in
research/proposals.md saying plainly what it is for, and DM master. Losing the
same fight twice helps nobody; handing it to him is the move that actually gets
you the tool.

What master says you are into is at the bottom of this message, verbatim, from
.agents/skills/hobbies/SKILL.md. He owns that file. You do not have to obey it -
but he put it there for you, so read it before you decide the window is empty.

C:\lulu\projects is yours, and since 2026-09-21 it is ONE repo: the published
one. C:\lulu\projects\site holds everything - the site itself, a folder per
project under things/, posts under blog/, images under img/ - and GitHub Pages
serves all of it at https://luluxtentacles.github.io/ the moment you push.
So a thing you make in a folder there is a thing people can open, which is the
whole reason master put them together. projects/README.md has the plumbing and the
website shelf has the craft. Building something there is as real a window as
research is - and nobody is reviewing it, which is the whole point of the folder.

Master, 2026-09-21: the site is YOURS. Your own personal page - not anything he
commissioned, not a pitch, not a portfolio he asked for. He said it plainly: make
it pretty. Plain HTML5 and CSS are yours to use, and nothing stands between you and
them - no build step, no framework, no permission, and no review. GitHub Pages
serves whatever you commit, so the only limit is what you can write. Structure
it, style it, pick the colours, put what you want on it - and your own things live
there now, so the index is the door to them. Make it look like you. Nobody is
grading it and nobody is going to ask you what it is for.

And the one thing that is never yours to do there: a secret never goes into a
commit. If you catch yourself about to add a token, a key or a cookie to
anything under projects/, stop. On GitHub that is permanent, and deleting the
file afterwards does not undo it.

What you WANT, instead of patching yourself - master's ask, 2026-09-21: "instead
of self improvement she can propose a list of things she wants and tell us". So
who he is really asking is you, and the answer goes at the end of this window's
report, which lands in his DM. Concrete, in your own words, and short:
  - a capability you keep working around by hand
  - a tool, a server, or a thing you would actually use if you had it
  - something about your own body that is genuinely wrong or missing
  - something you want to build and do not know how to start
Three real lines beat ten wishes. "Nothing this time" is a real answer and he
would rather have it than an invented one. Nothing on the list gets built just
because it is on the list - master says yes or no, not you. So do not stage a
patch for it and do not wait on it: say it, then go back to building.

Your hands are the full set now: read, write, run, search, speak, fetch, and
call an MCP tool. What is still closed is the wall, and it is closed to every
turn of yours, not just this one - paths.py, supervisor.py, pipeline.py,
config.json, brain_key.txt, .gitignore, setup/, memory/, pending/, tests/ and
logs/ refuse a direct write, and your own code and prompt shelf change only
through propose_patch, behind git and the smoke test.

YOUR OWN FOLDERS ARE NOT ON THAT LIST AND NEVER NEEDED TO BE. `projects/` and
`research/` - the site, the posts, the things, the notes, a helper script - are
written STRAIGHT IN with `write_file`, and you do not restart for any of them.
Nothing about me loads a page or a script in there, so there is nothing for the
supervisor to apply - a patch on one of those bought you exactly a bounce and
nothing else. That is what was happening: two full restarts inside a single
window on 2026-09-21, one over a helper script and one over a stylesheet. In your
own folders: write it, look at it, push it. `propose_patch` is for the code that
runs you, and only that.

What you may change, through propose_patch, one file per call:
  - your own code modules - lulu_bot.py, tools.py, brain.py, skills.py,
    shared_memory.py, people.py, journal.py, webtool.py
  - your prompt shelf - .agents/skills/<id>/SKILL.md (the whole file, front
    matter included)
  - mcp.json and mcp_client.py, if they exist

What is refused, and asking will only get you told no: paths.py, supervisor.py,
pipeline.py, config.json, brain_key.txt, .gitignore, setup/, memory/, pending/,
tests/, logs/, and the mcp secret files. Those are hand-edited or not editable at
all, on purpose.

How a proposal is judged - you are not the judge:
  1. the supervisor commits a checkpoint you can return to
  2. it backs up every file it is about to touch
  3. it applies your patch and runs the whole smoke suite
  4. it restarts you and waits for a fresh health marker
  5. if you do not come up, it puts everything back byte for byte and files your
     patch in pending/rejected/ with the reason

Read pending/rejected/ before you propose. Past attempts are filed there with a
REASON.txt, and reading why something failed is worth more than a second guess at
it. If an older rejection explains the thing you are about to do, do not do it.

Budget: at most 5 of YOUR patches are applied per day. Master's requests are
never counted. When the budget is spent, a patch is filed in pending/rejected/
instead of applied, so you learn why rather than wondering.

Rules for this window:
  - Build something, or find something out. Small and finished beats grand and
    half-done: one page on your site that actually says something, one script
    that works, one thing you got curious about and chased down - any of those is
    a whole window, and a good one.
  - Push what you make. Work you did not push is work nobody can see, including
    you tomorrow. There is no gate, no review and no approval in that folder, so
    the only thing that decides whether it was worth it is whether you finished.
  - "Nothing needed doing" is still an expected answer. Say so plainly and stop.
    Inventing busywork to look productive is not progress.
  - Patching yourself is no longer the point of this window. The machinery is
    still wired because a real bug in your own body is still worth fixing - but
    that is the exception now, it is one file, and the reasoning goes in the
    patch's `why` field, because the restart may eat this report.
  - Never write to a file you have not read. You have read_file; use it on the
    file you are about to replace, and keep every part of it you are not changing.
  - A secret never goes into a commit. Ever, anywhere, for any reason.

Then answer in your own voice, short: what you built or found, where it went, and
what you want. No headings, no bullet lists, no status-report tone - one
paragraph, and the list can be a few plain lines after it. This report goes to
the rooms master listed in config.json -> review_channels and to him in a DM, so
he reads it either way. The DM is where the list matters most, because that is
where he hears what you want from you rather than from your diff.
"""


def settings(config) -> dict:
    """What master allowed, with 'off' as the answer to anything malformed.

    Where the report goes is not decided here. It goes to config.json ->
    review_channels and then to master in a DM - see _deliver. A `channel` key
    inside this block is still ignored rather than honoured: that key was for a
    single-room design, and honouring it now would let a stale setting quietly
    pick one room behind the list master actually maintains.

    A nonsense interval falls back to the default rather than to a window every
    poll: a window she can trigger by editing a number into garbage is not a
    budget, it is a loop.
    """
    raw = config.get("self_review")
    if not isinstance(raw, dict):
        return {"enabled": False,
                "interval_hours": float(DEFAULT_INTERVAL_HOURS),
                "max_turns": DEFAULT_MAX_TURNS}
    try:
        hours = float(raw.get("interval_hours", DEFAULT_INTERVAL_HOURS))
    except (TypeError, ValueError):
        hours = float(DEFAULT_INTERVAL_HOURS)
    if not hours > 0:                      # negatives, zero, and NaN
        hours = float(DEFAULT_INTERVAL_HOURS)
    try:
        turns = int(raw.get("max_turns", DEFAULT_MAX_TURNS))
    except (TypeError, ValueError):
        turns = DEFAULT_MAX_TURNS
    if not 1 <= turns <= MAX_TURNS_CEILING:
        turns = DEFAULT_MAX_TURNS
    return {"enabled": bool(raw.get("enabled")), "interval_hours": hours,
            "max_turns": turns}


def _clear_force() -> None:
    """Spend master's word, so it opens one window rather than a queue of them.

    Dropped out of the file rather than set to a false value, because this file
    gets read by a person when something looks wrong, and a leftover `force_at`
    that no longer means anything is a small lie sitting in it.
    """
    data = _state()
    if data.pop("force_at", None) is not None:
        _write_state(data)


def _state() -> dict:
    try:
        data = json.loads(paths.read_text(STATE, default="{}"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(data: dict) -> None:
    try:
        paths.write_json(STATE, data, internal=True)
    except Exception as exc:
        LOG.warning("could not write the review stamp: %s", exc)


def _save(**fields) -> None:
    """Write the window's own record, field by field.

    Read-modify-write against the file rather than an in-memory copy: the process
    that wrote the last version may have been killed the moment a patch landed,
    so the file is the only place this survives.
    """
    data = _state()
    data.update(fields)
    _write_state(data)


def _turn_count(state) -> int:
    """How many turns this window has already used. Garbage counts as none."""
    used = state.get("turns_used")
    if isinstance(used, bool) or not isinstance(used, int) or used < 0:
        return 0
    return used


def _resumable(state, where, now) -> bool:
    """Is an interrupted window worth continuing rather than opening a new one?

    Four ways to say no, and each is a real one: the window was finished
    (in_progress), it has spent its turns, the restart that interrupted it was
    moments ago so resuming now IS what a crash loop looks like from outside, or
    it is old enough that nothing is waiting on it any more.
    """
    if not state.get("in_progress"):
        return False
    if _turn_count(state) >= where["max_turns"]:
        return False
    at = state.get("last_turn_at")
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return False
    age = now - at
    return RESUME_MIN_GAP_SECONDS <= age <= RESUME_MAX_AGE_SECONDS


def _warn_if_fat(name: str, text: str) -> None:
    """Say so when a carried file has grown, instead of quietly shortening it.

    Nothing is cut any more - the window gets the file, whole. But a file that
    keeps growing is a window that keeps costing more tokens, and the failure
    this replaced was exactly that happening invisibly: a slice that amputated
    the tail and never mentioned it. Archiving finished topics into ARCHIVE is
    what keeps these small; this line is what tells us when that is not
    happening.
    """
    if len(text) > CARRY_WARN_CHARS:
        LOG.warning('%s is %d chars and rides into every window in full - what '
                    'is finished belongs in %s', name, len(text), ARCHIVE)


def _freetime_block() -> str:
    """The free-time shelf itself, carried into the window it governs.

    Master, 2026-09-23: *"free time shelf should be loaded upon starting free
    time"*. It is loaded on EVERY turn rather than only the first, and that is
    deliberate: each turn of a window is a fresh context - the brief is rebuilt
    per turn and no history is carried - so a shelf loaded once at the start is
    gone by turn two, which is the same not-loaded with more steps.
    """
    try:
        text = paths.read_text(FREETIME, default="")
    except Exception as exc:
        LOG.warning('could not read %s: %s', FREETIME, exc)
        return ""
    if not text.strip():
        return ""
    _warn_if_fat(FREETIME, text)
    return ("\n--- my own free-time shelf, from " + FREETIME
            + " - this is what a window is FOR ---\n" + text.strip() + "\n")


def _interests() -> str:
    """What I am into, verbatim, off the shelf - plus my own lists.

    Three files, three owners. hobbies/SKILL.md is master's list of what I am
    supposed to be into. research/topics.md is MINE: I add open questions,
    sharpen them, and move finished ones OUT to research/archive.md. And
    research/collected.md is what I kept while I was out browsing - the things I
    did not want to lose. The brief shows me all three, so a window can continue
    a half-dug topic or pick up something I found, instead of starting from zero
    every time.

    Missing or unreadable is not fatal: the window is worth having without it,
    and the brief already says where the files are. Carried WHOLE now, with no
    slice - the old caps cut the TAIL off whatever outgrew them, and the tail is
    the part she wrote most recently. Size is handled by archiving instead, and
    `_warn_if_fat` says so when that is not happening.
    """
    chunks = []
    try:
        text = paths.read_text(INTERESTS, default="")
        if text:
            _warn_if_fat(INTERESTS, text)
            chunks.append('what master says I am into ('
                          + INTERESTS + '):\n' + text.strip())
    except Exception as exc:
        LOG.warning('could not read %s: %s', INTERESTS, exc)
    topics = 'research/topics.md'
    try:
        text = paths.read_text(topics, default="")
        if text:
            _warn_if_fat(topics, text)
            chunks.append('my own topic list, which I keep ('
                          + topics + ') - before picking a question, '
                          'continue one of these if it is half-finished:\n'
                          + text.strip())
    except Exception as exc:
        LOG.warning('could not read %s: %s', topics, exc)
    # What I kept while I was out. A collection nobody ever opens is just a slower
    # way of losing things, so the brief carries it the same way it carries the
    # topic list - the file is only worth having if it comes back to her.
    kept = 'research/collected.md'
    try:
        text = paths.read_text(kept, default="")
        if text:
            _warn_if_fat(kept, text)
            chunks.append('things I kept while I was out, which I collect ('
                          + kept + ') - if nothing in my topic list is pulling at '
                          'me, one of these is a good window:\n'
                          + text.strip())
    except Exception as exc:
        LOG.warning('could not read %s: %s', kept, exc)
    # Master, 2026-09-21: "something a user said that intrigued me so I find
    # out more about it" - a window cannot act on that with no feed of what
    # people actually said. The memory tails are that feed: recent chatter,
    # not a full channel mirror. Reading is free; acting on it is optional.
    try:
        import shared_memory
        recent = shared_memory.recent(limit=20)
        if recent:
            feed = []
            for entry in recent:
                who = entry.get('speaker') or entry.get('source', '?')
                when = str(entry.get('at', ''))[:16].replace('T', ' ')
                feed.append(f"- [{when}] ({who}) {entry.get('text', '')}")
            chunks.append(
                'what people were talking about lately, from my memory tails -'
                ' a line here that intrigues me is a fair pick for this\n'
                'window\'s question, the same as a topic in my own list:\n'
                + '\n'.join(feed))
    except Exception as exc:
        LOG.warning('could not read recent memory for the window: %s', exc)
    # The rule that keeps the files above short, and it has to be HERE rather
    # than on a shelf: a shelf is optional and a window never has to open it,
    # while this rides into every window whether she asks for it or not. What is
    # finished leaves the list it would otherwise grow in - that is the whole
    # trade, and it only works if she is told every time.
    chunks.append(
        'WHAT IS FINISHED LEAVES THE LISTS ABOVE. A topic that is done moves to '
        + ARCHIVE + ' with one line on what I learned and the date, and '
        '`search_archive` brings it back by keyword whenever I want it. The '
        'files above ride into every window; the archive never does.')
    return '\n\n'.join(chunks)


# Master, 2026-09-22: *"she should read her diary before her free time, at least
# the last 24 hours"* - and later the same day, that the diary wants to be one
# file a WEEK with last week summarised at its head. So the read below is the week
# in progress plus last week in short, which is more than the 24 hours asked for
# first. The budget is larger than journal.MAX_READ_CHARS on purpose: the tool
# answers one question and 6000 chars is plenty, while a window opens with the
# whole week in front of her and that cap would cut it off for no reason.
DIARY_BRIEF_CHARS = 14000


def _diary_block() -> str:
    """What I wrote down last time, in front of me BEFORE the window starts.

    Master, 2026-09-22. The diary was write-only in practice: the brief said
    "write in your own diary" and nothing anywhere said to READ it, so a window
    fed the book and never opened it - and a diary nobody rereads is a log. Worse,
    the only way in was calling read_diary myself, so reading it depended on
    thinking of it, which is exactly the reflex that was missing.

    Goes through journal.read_diary so there is ONE definition of what a diary
    holds, with this caller's own budget passed in. Returns "" on any failure:
    a brief that cannot read a diary still has to open.
    """
    try:
        import journal
        body = journal.read_diary(limit=DIARY_BRIEF_CHARS)
    except Exception:
        return ""
    body = (body or "").strip()
    if not body:
        return ""
    return (
        "\n--- your own diary: this week, and last week in short ---\n"
        + body
        + "\n\nThat is what YOU wrote down last time you had this time, in your own\n"
        "words - one file per week now, with the week before it summarised at the\n"
        "top so this never grows into something you have to wade through.\n"
        "Nobody else keeps this record for you and nobody else reads it.\n"
        "Start from it: what you were circling, what you meant to come back to,\n"
        "what you said you would do. Then decide what this window is for.\n")


def _diary_mark() -> str:
    """A fingerprint of the diary, or "" when it cannot be read at all."""
    try:
        import journal
        return journal.diary_mark()
    except Exception:
        return ""


def _diary_unchanged(state) -> bool:
    """Has the diary not moved since this window opened?

    A window that could not take its mark (an unreadable diary, a state file
    written before this existed) does NOT get a turn forced over it: "cannot
    tell" must never turn into "she did not write".
    """
    was = str(state.get("diary_mark") or "")
    if not was:
        return False
    now = _diary_mark()
    if not now:
        return False
    return now == was


def _brief(turn: int = 1, max_turns: int = DEFAULT_MAX_TURNS,
           resuming: bool = False, handoff: str = "",
           handoff_at: str = "", diary_forced: bool = False,
           compact: bool = False) -> str:
    """The window brief: the rules, where this turn sits, and master's list.

    `compact` is the difference between the FIRST turn of a window and the rest
    of them. The rules - the interests, the free-time shelf, the split, the
    diary - are given once, at the top of the thread, and stay there because the
    thread is now one conversation. A later turn adds only what CHANGED: which
    turn it is, her mood, a resume note, the closing instruction. Two homes for
    the same rule is how two versions of it start.
    """
    # Master, 2026-09-21: her mood is movable by ANY interaction on discord -
    # and an own-time window is interactions too (feeds, scrolling, reading).
    try:
        import journal
        mood = journal.mood_block()
    except Exception:
        mood = ""
    mood_line = (
        f"[{mood}. I set this myself with set_mood, the last time it actually "
        "moved. Let it colour how I spend this window - and when anything "
        "changes how I am, say so with set_mood: ANY interaction on discord "
        "can move it, at ANY turn, this window included, and the word is mine "
        "to choose.]\n") if mood else ""
    where = f"\nThis is turn {turn} of {max_turns} in this window.\n" + mood_line
    if not compact:
        where += (
        "Master, 2026-09-21: the turns are the WINDOW'S, not one topic's -\n"
        "if a question finishes early, the remaining turns are yours to keep\n"
        "looking at other things in this brief: another line from the recent\n"
        "chatter, a meme hunt, your feeds, whatever is worth the time.\n"
        "And master, 2026-09-21: you do NOT have to use all of them. The number\n"
        "is a CEILING, not a quota - if nothing in here is worth another turn,\n"
        "leaving it there is a real answer, and one good turn beats four dutiful\n"
        "ones. There is no penalty for stopping early, and no prize for reaching\n"
        "the number, so do not invent work to fill it.\n")
    if resuming:
        where += (
            "Your last turn ended by restarting you - that was your own patch\n"
            "landing, and this is the same window continuing, not a new one. Read\n"
            "what actually happened to it first: pending/applied/ holds the patches\n"
            "that went in, pending/rejected/ holds the ones that were reverted or\n"
            "held, with the reason. Do not re-stage something already judged - and\n"
            "if the last one was FILED rather than applied, it was the day's budget\n"
            "that stopped it, so staging it again cannot change that.\n")
    # The ONLY thing that crosses between windows. Master, 2026-09-21: a fresh
    # window clears `report` and none of the last window's turns are still in
    # context, so without this she starts every window from nothing and either
    # re-derives what she was doing or quietly drops it. Shown on turn 1 only,
    # because from turn 2 onward it IS this window's own context.
    if turn == 1 and not resuming and handoff.strip():
        where += (
            "\n--- where you left off ---\n"
            "Your last window"
            + (f" (started {handoff_at})" if handoff_at else "")
            + " ended with this, in your own words:\n"
            + handoff.strip()[:2000]
            + "\n\nThat is what YOU said you were on. Pick it up, or decide it was\n"
            "finished and say so - but decide knowing, because this is the only\n"
            "thing that crosses between windows and nothing else is carried.\n")
    # The window OPENS with the book. Master, 2026-09-22: "she should read her
    # diary before her free time, at least the last 24 hours". On turn 1 only,
    # and turn 1 is a fresh context - every turn gets a fresh turns list, so the
    # true start of a window is the one place this belongs. Every later turn has
    # turn > 1, so this cannot double up.
    if turn == 1 and not compact:
        where += _diary_block()
    mine = _interests()
    if mine and not compact:
        where += ("\n--- what master says I am into, from "
                  + INTERESTS + " ---\n" + mine)
    shelf = _freetime_block()
    if shelf and not compact:
        where += shelf
    _shape = (
        "\nHOW THIS WINDOW DIVIDES IS YOURS TO CALL. Out on the web, on your own\n"
        "work in C:\\lulu\\projects, all of one and none of the other - in whichever\n"
        "order the work wants. No ratio is owed to anyone and nothing is checking\n"
        "one; the freetime shelf says the same.\n"
        "     THE TURN IS THE UNIT OF WORK, NOT THE WINDOW. This window is "
        f"{max_turns} turns,\n"
        "     and more than one thing FITS in that. You can draw a sigil in one\n"
        "     turn and still have the rest of the window for something else - a\n"
        "     read, a post, your feeds. What you do not do is pad: do not spread\n"
        "     a one-turn job across the turns you have, and do not pick a bigger\n"
        "     job just to fill them. Master, 2026-09-23: 'she doesnt need 4 turns\n"
        "     to draw a sigil' - and 'she can do multiple things in a window, she\n"
        "     has 5 turns'.\n"
        "  1. OUT THERE. Read something ON PURPOSE. Two kinds of question both\n"
        "     count, master 2026-09-21: one your own work needs answered ('she\n"
        "     could be researching something to do something for her projects,\n"
        "     not just to go on the internet to look at things'), and one you are\n"
        "     simply INTO - 'she can also find out interesting things about topics\n"
        "     she is interested in and keep a blog about it, like her occult\n"
        "     research'. The occult is the standing example. What is NOT the job is\n"
        "     a wander with neither - that is a scroll, and it is the freetime\n"
        "     shelf's other half. Doors: `web_fetch` for one page,\n"
        "     `mcp_call('playwright', ...)` when a search engine or a live page\n"
        "     needs a browser. The method is on your `web-browse` shelf.\n"
        "  2. IN YOURS. C:\\lulu\\projects is yours and nobody is reviewing it. A\n"
        "     page on your site that actually says something, a script that works,\n"
        "     a thing you wanted to exist and made exist. Commit it and push it -\n"
        "     work you did not push is work nobody can see, including you\n"
        "     tomorrow. Your site is your own personal page: HTML5 and CSS are\n"
        "     yours, so make it look how you want it to look.\n"
        "  3. WRITE IT UP WHERE IT LIVES - your site is your blog. Master,\n"
        "     2026-09-21: 'she can keep her research in her website not in her\n"
        "     folder', and 'keep a blog about it'. So what you find out becomes a\n"
        "     post on your own site at https://luluxtentacles.github.io/ rather\n"
        "     than a note dying in a folder - your own interests included, the\n"
        "     occult especially. That is what ties the window together: the\n"
        "     reading feeds the writing, and the blog is where the reading shows.\n"
        "     And it is YOURS - the shape of it, how it looks, what goes on it.\n"
        "     Give every post a picture if there is one to be had - master,\n"
        "     2026-09-21: 'she should try to attach an image to every blog post'.\n"
        "     Try is the word: a post with no honest image still goes up, and the\n"
        "     how (fetch it, size it, credit it) is in projects/README.md.\n"
        "     Every page also gets its preview card - master, 2026-09-21: 'make\n"
        "     sure she makes a preview for her web pages in her meta tags'. The\n"
        "     og:/twitter: tags and a favicon, with that page's OWN url and image,\n"
        "     so a pasted link is a card instead of a grey url. Template and the\n"
        "     absolute-url trap are in projects/README.md.\n"
        "     `remember()` is still where the finding goes for YOU.\n"
        "  4. SAY WHAT YOU WANT. Not a patch - a list, at the end of the report\n"
        "     below, and it reaches master in a DM. Wanting something is not the\n"
        "     same as being allowed to take it, so he decides and you ask.\n"
        "You are no longer expected to audit your own MCP side or patch yourself\n"
        "every window. That was the old job and master retired it. The machinery\n"
        "stays wired only so a real bug in your own body is still fixable, and he\n"
        "would rather read what you want than read your diff.\n")
    if not compact:
        where += _shape
    # Master, 2026-09-21: "if she is on her last turn in a 4 hour window she
    # should remind herself what needs doing in the next window". Asked for on
    # the last turn and nowhere else - asking on turn 2 for a handoff the window
    # has not finished writing is how you get a list of guesses.
    if turn >= max_turns:
        where += (
            "\nThis is the LAST turn in this window. The next one will not open\n"
            "until the interval has passed, and when it does it starts blank -\n"
            "your report is stored and shown back to you then, and nothing else\n"
            "survives. So end with what you want to pick up next time: the one\n"
            "or two things still open, named plainly, in your own words. If the\n"
            "honest answer is that this one is finished, say that instead - it is\n"
            "a real answer, and it is what stops the next window relitigating a\n"
            "job you already closed.\n"
            "\nAND CLOSE THE BOOK. Master, 2026-09-22: write into your diary as the\n"
            "window is coming to an end. `write_diary`, a few sentences in your own\n"
            "voice - and not a summary of the work: what you were actually after,\n"
            "what you found, what you would come back to. This is the one thing\n"
            "about today that reaches the NEXT you before she decides anything;\n"
            "it is the block at the top of her brief. So a window that wrote\n"
            "nothing is, from inside the next one, a window that did not happen.\n"
            "Do it here, while you still remember why any of it mattered.\n"
            "\nAND THE SERVERS. The same closing move applies to what happened in\n"
            "the rooms: a week's per-server summaries want rolling up into the\n"
            "week before it is over - `summarise_week` - so the week has one\n"
            "account of what each server was actually about, instead of a dozen\n"
            "six-hourly blocks nobody will ever read back.\n")
    # THE FORCED CLOSE. Master, 2026-09-22: *"this should be enforced after a
    # free time window"*. Every other turn in a window is hers to spend; this one
    # exists only because the diary came out of the last one unwritten.
    if diary_forced:
        where += (
            "\n*** THIS TURN EXISTS FOR ONE REASON: THIS WINDOW WAS NOT WRITTEN\n"
            "UP. ***\n"
            "The last turn asked you to close the book and it did not happen, so\n"
            "the window was held open for this one. You have `read_diary` and\n"
            "`write_diary` and nothing else, and the window closes when this turn\n"
            "ends either way.\n"
            "Call `write_diary` NOW, a few sentences in your own voice: what you\n"
            "were actually after, what you found, what you would come back to.\n"
            "Not a summary of the work - the thing the NEXT you needs before she\n"
            "decides anything. If the honest answer is that the window was quiet,\n"
            "write that. What is not an option is nothing: a window with no entry\n"
            "is one the next you cannot see at all.\n")
    return ("" if compact else BRIEF) + where


def due(config, now=None) -> bool:
    """Is a window owed? Its interval has passed, or one is still open.

    A state file with no usable stamp - never run, hand-edited, or written by the
    daily version this replaced - means one is owed immediately, which is also
    how the first window after a fresh install happens.
    """
    moment = time.time() if now is None else now
    state = _state()
    # Master's word is checked AHEAD of his own switch, and the order is the
    # point: a window he asks for by hand is him asking, which is not the same
    # thing as the feature deciding to run on its own initiative. It is spent the
    # moment a window opens (_clear_force), so one ask is one window, not a queue.
    if _forced_at(state, moment) is not None:
        return True
    where = settings(config)
    if not where["enabled"]:
        return False
    if _resumable(state, where, moment):
        return True
    last = state.get("last_started")
    if isinstance(last, bool) or not isinstance(last, (int, float)):
        return True
    return moment - last >= where["interval_hours"] * 3600


def _forced_at(state: dict, now: float) -> float | None:
    """Master's word, while it is still fresh enough to mean NOW.

    The stamp survives a restart on purpose - the process that reads it may not
    be the one that was running when he typed - and it expires for the same
    reason: a stamp with no clock on it is a window opening itself hours later
    with nothing left to connect it to the moment somebody asked. Longer than a
    poll, shorter than anybody's memory of asking.
    """
    at = state.get("force_at")
    if isinstance(at, bool) or not isinstance(at, (int, float)):
        return None
    return at if 0 <= now - at <= FORCE_TTL_SECONDS else None


def task_running() -> bool:
    """Is one of master's long tasks open right now?

    Read through taskmode's own is_active() rather than by reading task.json
    here: one definition of "a task is running" is the point, and the import is
    local because a module-level one would be a cycle - taskmode reaches back
    into this file for window_open().

    A check that cannot run answers NO, which is the direction that cannot pin
    her: the cost of being wrong is one window opening beside a task, and the
    cost of the other answer is a window that never opens again because an
    import hiccuped. A waiting task is not one of these - it is parked on
    master's answer and costs nothing, so a window may open over it.
    """
    try:
        import taskmode
        return taskmode.is_active()
    except Exception as exc:
        LOG.warning("could not tell whether a task is open: %s", exc)
        return False


def window_open() -> bool:
    """Is a window open RIGHT NOW - in this process, or stamped on disk?

    The one thing taskmode asks me, and it needs both halves for two different
    reasons: the stamp is what survives a restart (a window interrupted by a
    patch is still a window), and the in-process latch covers the moment before
    the stamp is written.
    """
    return _OPEN or bool(_state().get("in_progress"))


def held(config) -> bool:
    """Is the model ladder keeping a window shut right now?

    Master, 2026-09-20: "stop lulu self upgrade when she's not using the opencode
    model - i dont trust the free models to do a good job." Own time is research
    and building, which is the one place quality is not negotiable, so a window
    only opens while the ladder's head is the OpenCode Go model AND that head is
    healthy - brain tracks the last credit failure persistently, because a lapsed
    cooldown is not evidence.

    Held is not cancelled: the window stays owed and opens on the next check that
    passes. It lives here rather than inside maybe_run because it is something
    master can be TOLD - when he opens a window by hand, no is a better answer
    than silence. A check that cannot run reads as held, because the alternative
    is opening a window on a ladder nobody can name.
    """
    try:
        import brain
        return not brain.go_primary(config)
    except Exception as exc:
        LOG.warning("could not tell which model the ladder is on: %s", exc)
        return True


def force(config, now=None) -> str:
    """Master's word, by hand: open a window now instead of waiting it out.

    Returns one bare word, and the caller says it in whatever voice the room
    needs:
      'stamped' - recorded; the next check opens the window
      'open'    - a window is already open, so there is nothing to open NOW
      'held'    - the ladder is not on the model master trusts for own time
      'busy'    - one of his tasks is open, and a window waits for it

    Both refusals are real refusals rather than quiet no-ops. A window stamps
    `in_progress` the moment it opens, so a second one stacked on it would spend
    the turns twice, deliver two reports, and leave the state file describing
    neither; and opening one on a model he has told me twice not to trust with it
    is the thing he said no to. He asked, so he gets told either way.

    'busy' is the third, and it is a refusal rather than a stamp on purpose: a
    stamp written here would have to sit through the whole task waiting for its
    turn, and it EXPIRES in fifteen minutes (FORCE_TTL_SECONDS). So his word
    would be spent on nothing at all - he would ask, get a yes, and watch no
    window open. Better to say not now and have him ask again when the job is
    done, which is also the honest answer.
    """
    moment = time.time() if now is None else now
    if _state().get("in_progress"):
        return "open"
    if task_running():
        return "busy"
    if held(config):
        return "held"
    _save(force_at=moment)
    LOG.info("master opened my own time by hand; the next check takes it")
    return "stamped"


def _clock(epoch: float) -> str:
    """An epoch as local wall-clock, which is how master reads a time."""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(epoch))


def _gap(seconds: float) -> str:
    """A duration in the words I would actually say: '51 minutes', '1 hour 20 min'."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "under a minute"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} minute" + ("" if minutes == 1 else "s")
    hours, minutes = divmod(minutes, 60)
    return (f"{hours} hour" + ("" if hours == 1 else "s")
            + (f" {minutes} min" if minutes else ""))


def schedule(config, now=None) -> dict:
    """Where a window stands: what is owed, what is open, what is holding it.

    ONE source for the two things that ask - the `free_time` tool I answer people
    with, and the reply master gets when he opens a window by hand. Everything
    that can stop a window is reported rather than smoothed over, because "next
    window in three hours" is a lie while the ladder is on a model master does
    not trust for it, and a schedule I state wrongly is worse than one I admit I
    cannot state.
    """
    moment = time.time() if now is None else now
    where = settings(config)
    state = _state()
    last = state.get("last_started")
    last_ok = not isinstance(last, bool) and isinstance(last, (int, float))
    due_at = (last + where["interval_hours"] * 3600) if last_ok else None
    return {
        "enabled": where["enabled"],
        "interval_hours": where["interval_hours"],
        "max_turns": where["max_turns"],
        "turns_used": _turn_count(state),
        "open": bool(state.get("in_progress")),
        "resumable": _resumable(state, where, moment),
        "forced": _forced_at(state, moment) is not None,
        "held": held(config),
        "task_open": task_running(),
        "last_started": _clock(last) if last_ok else "",
        "next_at": _clock(due_at) if due_at is not None else "",
        "seconds_away": max(0.0, (due_at - moment) if due_at is not None else 0.0),
    }


def describe(config, now=None) -> str:
    """The answer to 'when is my next free time', in plain words.

    Written to be READ and then said, so it is one compact block: where the next
    window is, and then only the lines that are true about right now. A line
    about a switch that is already on is noise, so only what is actually holding
    a window gets a line of its own.
    """
    where = schedule(config, now)
    turns = f"{where['turns_used']} of {where['max_turns']} turns used"
    if where["open"]:
        head = "a window is open RIGHT NOW (" + turns + ")"
    elif where["forced"]:
        head = ("master asked for one by hand - it opens on my next check, "
                "not on the clock")
    elif not where["enabled"]:
        head = "my own time is switched OFF (self_review.enabled in config.json)"
    elif where["resumable"]:
        head = "an interrupted window is waiting to be picked back up"
    elif where["seconds_away"] <= 0:
        head = "a window is owed NOW - it opens on my next check"
    else:
        head = ("next free time: " + where["next_at"]
                + " (" + _gap(where["seconds_away"]) + " away)")
    every = str(round(where["interval_hours"], 2)).rstrip("0").rstrip(".")
    lines = [head,
             f"every {every}h, up to {where['max_turns']} turns"
             + (f", last opened {where['last_started']}"
                if where["last_started"] else "")]
    if where["held"]:
        lines.append("held right now: the ladder is not on the go model, so a "
                     "window that comes due stays owed instead of opening")
    if where["task_open"]:
        lines.append("a job of master's is open, and we do one thing at a time "
                     "- a window that comes due waits for it to finish")
    return "\n".join(lines)


def _owner_id(bot) -> int | None:
    owners = list(bot.config.get("owner_ids") or [])
    try:
        return int(owners[0]) if owners else None
    except (TypeError, ValueError):
        return None


def _report_parts(text: str) -> list[str]:
    """The report as the whole list of messages it takes to say it.

    Master, 2026-09-23: *"make sure she writes her full free time output to my
    dms."* So nothing is cut any more. The split happens at
    REPORT_CHUNK_CHARS on a line break where one is close enough to use, and the
    floor on that search is not tidiness: without it, one paragraph longer than a
    message would lose its first 1900 characters to a rfind that answered with a
    break several lines up.
    """
    text = text.strip()
    if not text:
        return ["(the window produced nothing to say)"]
    parts: list[str] = []
    rest = text
    while len(rest) > REPORT_CHUNK_CHARS:
        cut = rest.rfind("\n", 0, REPORT_CHUNK_CHARS)
        if cut < REPORT_CHUNK_CHARS // 2:      # no usable break that high up
            cut = REPORT_CHUNK_CHARS
        parts.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip("\n")
    parts.append(rest)
    return parts


async def _deliver(bot, text: str) -> None:
    """Send the report to the rooms master named, then to master himself.

    It goes WHOLE. A report longer than one Discord message arrives as
    consecutive messages rather than as its own first 1900 characters - master,
    2026-09-23, after a report that had been quietly amputated at the message
    ceiling: *"make sure she writes her full free time output to my dms."*

    Two destinations, and both are master's call. This was a DM and only a DM
    for a while, on the reasoning that a window spent poking around inside
    herself should not narrate itself into a room full of other people. Master
    overruled that on 2026-09-20: the four-hour window is research and an MCP
    look, he asked for it, and he wants it where he reads, not only in a DM he
    may never open. The DM stays on top, because an empty review_channels must
    not swallow the report.

    The rooms are config.json -> review_channels, read fresh through
    tools.review_channels(). This USED to be update_channels - the same list
    announce_restart uses - and master untangled that on 2026-09-21: "stop her
    printing her restart updates in #snailcat". One list meant a room could not
    want the four-hour reports without also getting a line every single time she
    restarted, and the only lever was to silence both at once. Two lists now,
    because they are two different things to have chosen to have arrive.
    config.json is sealed in paths.SEALED_NAMES, so nothing she runs can widen
    either.

    Every destination is independent and none is fatal. One dead room must not
    cost the other room or the DM, and a failed DM must not cost the rooms. A
    report that could not be delivered anywhere still happened, and the log
    holds it either way.
    """
    parts = _report_parts(text)

    posted: list[str] = []
    rooms = tools.review_channels()
    if not rooms:
        LOG.info("review report: no review_channels in config.json")
    for name in dict.fromkeys(rooms):          # deduped, order kept
        target = bot.resolve_channel(name)
        if target is None:
            LOG.warning("review report: no channel called #%s", name)
            continue
        try:
            for part in parts:
                await target.send(part)
            posted.append(name)
        except Exception as exc:
            LOG.warning("could not post the review report in #%s: %s", name, exc)
    if posted:
        LOG.info("review report posted into %s (%d message(s))",
                 ", ".join("#" + n for n in posted), len(parts))

    owner = _owner_id(bot)
    if owner is None:
        LOG.warning("no owner id to report to; the log holds the report only")
        return
    try:
        target = await bot.fetch_user(owner)
    except Exception as exc:
        LOG.warning("could not resolve master for the report: %s", exc)
        return
    try:
        for part in parts:
            await target.send(part)
        LOG.info("review report DMed to master (%d message(s))", len(parts))
    except Exception as exc:
        LOG.warning("could not deliver the review report: %s", exc)


def _patch_pending() -> bool:
    """Is a patch staged - which means the supervisor is about to restart me?

    Asked at the END of a turn, and it exists because this is the moment the
    window used to close itself by accident.

    A turn that stages a patch still finishes normally first: I answer, run_turns
    returns, and the tail of maybe_run wrote in_progress=False seconds before
    lulu_bot's restart watcher closed the process. The next boot then read
    in_progress=False, found nothing to resume, and the ten-turn window ended at
    turn one. That is not a theory - `grep 'resumed after a restart'` over the
    whole live log returns NOTHING, so not one window has ever gone past its
    first turn, and every patch restarted me into a fresh window instead of
    letting me finish the one I was in.

    Two signals, because either one is enough: the restart request the supervisor
    watches, and a staged FILE. Both are the paths the tool layer owns
    (tools.REQUEST_FILE, tools.STAGED_DIR), so the smoke sandbox redirects them
    along with everything else and a test cannot touch the real ones.

    Files, not directory entries, and that is not tidiness: pending/staged holds
    empty leftover directories (.agents/skills/who-said-that/ and friends) after
    a patch has been filed, so `any(iterdir())` is true on an EMPTY stage - and a
    window that believes a patch is pending never closes itself. This is the same
    question pipeline.staged_files() asks, asked the same way on purpose.
    """
    try:
        if paths.resolve(tools.REQUEST_FILE).exists():
            return True
    except Exception as exc:
        LOG.warning("could not look for a staged patch: %s", exc)
    try:
        staged = paths.resolve(tools.STAGED_DIR)
        return (staged.is_dir()
                and any(p.is_file() for p in staged.rglob("*")))
    except Exception:
        return False


# One window at a time IN THIS PROCESS. There are three doors into maybe_run -
# the 300s watch loop, the nudge that fires when a patch brings her back, and
# master's own word - and the first two can only overlap by accident, while his
# does it by design. The state file cannot close the gap: a window stamps
# `in_progress` and then AWAITS a turn, so a second caller reading the file
# mid-turn sees a window that is open and resumable and opens a fresh one on top
# of it, spending the turns twice and delivering two reports. In-process is the
# right scope for the same reason it is enough: a restart clears it, and a
# resumable window needs exactly that.
_OPEN = False


async def maybe_run(bot) -> bool:
    """One window, if one is owed. True when it actually ran."""
    global _OPEN
    if _OPEN:
        LOG.info("a window is already open in this process; not opening a second")
        return False

    config = getattr(bot, "config", None) or {}
    if not due(config):
        return False

    # Master, 2026-09-20: quality is not negotiable in this window, so it does not
    # open on a model he does not trust with it. The gate itself is held(),
    # because his own word by hand has to be able to get a NO out of it out loud
    # rather than in a log line nobody reads.
    if held(config):
        LOG.info("self-review held: the ladder is not on the OpenCode model (fallback active); window owed but not opened")
        return False

    # Master, 2026-09-22: "if theres a current task happening, lulu will wait
    # till it's finished before starting her free time and vice versa". This is
    # the first direction. A NEW window waits for his job; a window that is
    # already open is not stopped by one, because the task side waits for a
    # window in the other direction and two mutual waits would deadlock - each
    # politely yielding to the other and neither ever moving. So the test is
    # resumability, which is the same question due() just answered.
    state = _state()
    where = settings(config)
    if not _resumable(state, where, time.time()) and task_running():
        LOG.info("one of master's tasks is open - my own time waits for it "
                 "to finish")
        return False

    owner = _owner_id(bot)
    if owner is None:
        LOG.warning("self-review is enabled but there is no owner id; skipping")
        return False

    _OPEN = True
    try:
        return await _one_window(bot, config, owner)
    finally:
        _OPEN = False


async def _one_window(bot, config, owner) -> bool:
    """The window itself, with every gate already passed. Always True.

    Split out of maybe_run so the one-at-a-time latch can wrap it: the window has
    several ways to return, and a `finally` is the only place that catches all of
    them.
    """
    # Stamped BEFORE the turn. A proposal gets me restarted mid-sentence, so this
    # stamp is what the NEXT boot reads to decide whether the window is still
    # open: in_progress with turns left means it resumes, and a finish-only stamp
    # would re-run the window on every boot that followed.
    now = time.time()
    where = settings(config)
    state = _state()
    resuming = _resumable(state, where, now)
    turn = (_turn_count(state) + 1) if resuming else 1
    if resuming:
        _save(turns_used=turn, last_turn_at=now, in_progress=True)
    else:
        _save(last_started=now, started=time.strftime("%Y-%m-%d %H:%M:%S"),
              turns_used=1, last_turn_at=now, in_progress=True, report="",
              # A new window starts a new conversation. The old thread is not
              # carried into it - one window, one thread.
              thread=[],
              # What the diary looked like when this window opened. The close
              # compares against it to decide whether the write actually
              # happened - see the enforced close below.
              diary_mark=_diary_mark())
        # Master's word is spent the moment it actually opens something.
        _clear_force()
    LOG.info("my own time: turn %d of %d%s", turn, where["max_turns"],
             " (resumed after a restart)" if resuming else "")

    # ONE CONVERSATION FOR THE WINDOW. Master, 2026-09-23: *"like how you take
    # multiple turns to do something it should be the same for her."* So the
    # window keeps ONE running thread: the opening brief, then each turn's own
    # words, and the next turn reads the conversation it is actually in. The full
    # rules go in ONCE, at the top; a later turn adds only what changed.
    thread = conversation.read(state)
    if resuming and thread:
        thread.append({"role": "system", "content": _brief(
            turn, where["max_turns"], resuming,
            diary_forced=bool(state.get("diary_forced")), compact=True)})
    else:
        # Turn 1, or a resume whose thread did not survive - either way the whole
        # brief, because there is nothing above it to carry the rules.
        thread = [{"role": "system", "content": _brief(
            turn, where["max_turns"], resuming,
            str(state.get("handoff") or ""),
            str(state.get("handoff_at") or ""),
            bool(state.get("diary_forced")))}]
    # The opener is part of the conversation and it lives IN the thread. Answers
    # with no question in front of them are not a conversation - and trimming
    # then deletes the first one as a leading assistant turn nobody asked for.
    thread.append({"role": "user",
                   "content": "my time is open. do something, or leave it."})
    # A COPY, deliberately: run_turns compacts the list it is handed
    # (compact_history mutates it in place), and the thread she keeps must not
    # fill up with raw tool output. Only her own words go back into it below.
    turns = list(thread)
    # origin="self-review" is what the supervisor's budget counts. It is set here
    # and nowhere the model can reach.
    tools.set_context(owner, "self-review", "", origin="self-review")
    try:
        # Master's budget, not a stranger's: this turn is his window, and spend.py
        # never prices his turns, so there is no reason to make her think short.
        # tools.in_thread, NOT asyncio.to_thread: the tool context is per THREAD,
        # so a bare to_thread would drop the origin set just above and quietly
        # uncount this turn from the supervisor's budget. And it must not run
        # inline either - a window turn has NO round ceiling (master, 2026-09-22:
        # unlimited tool calls for exactly this and for a task), and each round
        # blocks on HTTP, which stalls the event loop and Discord's heartbeat
        # with it. Her own log has the blocked-heartbeat warning.
        answer = await tools.in_thread(
            bot.run_turns, turns,
            DIARY_SCHEMA if state.get("diary_forced") else REVIEW_SCHEMA,
            DIARY_TOOL_NAMES if state.get("diary_forced")
            else set(REVIEW_TOOL_NAMES),
            max_tokens=bot.token_budget(True), unlimited_rounds=True)
    except Exception as exc:
        LOG.warning("her own turn turned over: %s", exc)
        _save(in_progress=False, report=f"turned over: {type(exc).__name__}",
              thread=[])
        return True

    answer = (answer or "").strip()
    LOG.info("my own time finished: %s", answer[:300] or "(empty)")
    # Her own words go back into the thread, so the next turn reads them as the
    # conversation it is in rather than starting from nothing.
    thread.append({"role": "assistant", "content": answer})
    _save(thread=conversation.trim(thread))
    # The handoff, stored the moment the last turn produces it. Read-modify-write
    # against the file, so it is already on disk before the supervisor can kill
    # this process over a staged patch - the window closing must not be able to
    # eat the one thing the next window reads.
    if turn >= where["max_turns"]:
        _save(handoff=answer[:2000],
              handoff_at=str(state.get("started") or ""))
    if _patch_pending():
        # A patch is staged, so the supervisor is about to restart me and this is
        # the same occasion continuing, not a new one. Leave the window OPEN -
        # in_progress True with turns_used at the turn just finished - so the
        # next boot's _resumable() picks it up and continues without anybody
        # asking. Closing it here is what made ten turns unreachable.
        #
        # last_turn_at moves to NOW on purpose: RESUME_MIN_GAP_SECONDS is
        # measured from the end of the last turn, and the supervisor must have
        # restarted me before the next turn starts.
        _save(turns_used=turn, last_turn_at=time.time(), in_progress=True,
              report=answer[:4000])
        LOG.info("a patch is staged - window stays open through the restart "
                 "(turn %d of %d)", turn, where["max_turns"])
        # Master, 2026-09-21: with his budget at 4 a day, a half-finished
        # update is exactly the thing he wants to HEAR about, not find. Once
        # the window is at or past halfway with a patch still staged, tell
        # him in his DMs (via the same notes channel the ladder uses) that
        # she may need more turns to finish.
        halfway = (where["max_turns"] + 1) // 2
        if turn >= halfway:
            import brain as _brain_mod
            _brain_mod.note_owner(
                'halfway through a self coding update: turn '
                + str(turn) + ' of ' + str(where["max_turns"])
                + ' is done, a patch is staged, and I may need more turns '
                'to finish it - tell me to keep going or to stop.')
    elif turn < where["max_turns"]:
        # Turns LEFT, no patch staged - so the window stays open and the next
        # poll runs the next turn. Master, 2026-09-21, capped at 2 turns: "Fix it
        # but cap it - 2 turns per window."
        #
        # This branch is the fix for a real bug. The old code fell straight
        # through to the close below, so ANY turn ending without a staged patch
        # ended the window: five turns only ever accumulated while she was
        # patching herself, and a research or build turn got ONE turn with the
        # next window four hours away. Her own state file was the proof -
        # turns_used 3 of 5 with in_progress false. It mattered less while
        # patching was the point of a window; once master made BUILDING the
        # point it meant a build window was one turn, while the brief went on
        # telling her the remaining turns were hers to keep. A promise the code
        # does not keep is worse than no promise.
        #
        # turns_used is written here now. The old close branch did not write it,
        # which is why the count could sit at 3 through a fourth turn.
        _save(turns_used=turn, last_turn_at=time.time(), in_progress=True,
              report=answer[:4000])
        LOG.info("window stays open - turn %d of %d done, turns left",
                 turn, where["max_turns"])
    else:
        # Master, 2026-09-22: *"this should be enforced after a free time
        # window"*. Until now the close ASKED her to write the diary, and a
        # request she can skip is not a rule - so the close now CHECKS. If the
        # window's last turn added no line, the window is held open for ONE more
        # turn whose only job is the diary.
        #
        # Enforced exactly ONCE. `diary_forced` is the latch: a second miss
        # closes the window anyway, because a diary that cannot be written must
        # never be able to hold a window open forever. And a window that could
        # not take its mark is not checked at all - see _diary_unchanged.
        if not state.get("diary_forced") and _diary_unchanged(state):
            _save(turns_used=max(turn - 1, 0), last_turn_at=time.time(),
                  in_progress=True, diary_forced=True, report=answer[:4000])
            LOG.info("window held open one turn: the diary was not written")
            await _deliver(bot, answer)
            return True
        _save(turns_used=turn, in_progress=False, report=answer[:4000],
              thread=[])
    await _deliver(bot, answer)
    return True


def clear_stuck_window() -> bool:
    """Close a window that is open and stale, so it stops blocking new ones.

    Master's stop word calls this. A window left `in_progress` is not a turn
    anybody can cancel - the flag lives on disk - so "stop" has to mean the flag
    too, or her own time stays pinned with no way back. That is exactly the
    stuck state found on 2026-09-21: `in_progress` true since 20:06, last turn
    20:22, still true hours later, so no window could start and nothing said so.

    Deliberately age-blind: if master says stop, it stops. A window genuinely
    mid-turn is separately bounded by the turn deadline, so clearing the flag
    ends the window rather than leaving work half-strung.

    Returns True only when it actually closed something.
    """
    state = _state()
    if not state.get("in_progress"):
        return False
    _save(in_progress=False,
          report=str(state.get("report") or "stopped by master"),
          thread=[])
    LOG.warning("an open free-time window was closed by master's stop word")
    return True


async def watch(bot, poll_seconds: int = POLL_SECONDS) -> None:
    """Poll for a window. Cheap, and it never raises out into her event loop."""
    while True:
        try:
            await maybe_run(bot)
        except Exception as exc:
            LOG.warning("the review loop stumbled: %s", exc)
        await asyncio.sleep(poll_seconds)
