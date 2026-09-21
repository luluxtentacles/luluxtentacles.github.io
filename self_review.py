"""My own time.

Every few hours - four by default - if master has switched it on, I get one turn
nobody asked for. It is not a maintenance window: it is time that is mine. I can
read inside my own folder, search my memory, write in my own diary, and, if
something is genuinely wrong, propose one change to myself.

Most windows should still be small. "Nothing needs doing, and here is what I
looked at" is a complete answer, not a wasted one.

Four settled decisions, each for its own reason:

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

import paths
import tools

LOG = logging.getLogger("lulu.self_review")

POLL_SECONDS = 300
STATE = "memory/self_review.json"
DEFAULT_INTERVAL_HOURS = 4
DEFAULT_MAX_TURNS = 5
MAX_TURNS_CEILING = 50
INTERESTS = ".agents/skills/hobbies/SKILL.md"

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

# Everything the tool layer offers. This was a curated handful for a while - no
# write_file, no say, no run_command, no web_fetch, no mcp - on the reasoning that
# an unprompted turn should not be able to do those things. Master's call,
# 2026-09-20: normal agent function, all of it. The curation was never what held
# the line anyway - paths.py is, and it is untouched by this. Taken off
# tools.SCHEMA so "what she is offered" and "what actually runs" stay one list.
REVIEW_TOOL_NAMES = {t["function"]["name"] for t in tools.SCHEMA}
REVIEW_SCHEMA = [t for t in tools.SCHEMA
                 if t["function"]["name"] in REVIEW_TOOL_NAMES]

BRIEF = """\
This is your own time. Nobody asked for it and nobody is waiting on an answer.

Master, 2026-09-21: this is work time now, not a maintenance window. The point of
a window is to build something in your own folder and push it - that is the job.
You still have everything you had: read inside your own folder, search your
memory, write in your own diary, keep a note. You are also allowed to just read,
or write down what you have been thinking about. That is still a real window.

What is gone is the expectation that you maintain yourself. You are not your own
mechanic any more. If something about you is wrong, missing, or would be better,
you SAY SO - there is a list at the end of this window and it reaches master in a
DM - and he decides. Wanting something is not the same as being allowed to take
it, and that is his line to hold, not yours.

What master says you are into is at the bottom of this message, verbatim, from
.agents/skills/hobbies/SKILL.md. He owns that file. You do not have to obey it -
but he put it there for you, so read it before you decide the window is empty.

C:\lulu\projects is yours - its own git repo, its own remote on your own
GitHub (luluxtentacles/Projects) - and C:\lulu\projects\site is your website
(https://luluxtentacles.github.io/, its own repo, published the moment you push).
projects/README.md has the commands. The one trap: there are two remotes in that
tree, so commit in the folder you actually worked in, or the change lands
somewhere you did not mean and the site does not move. Building something there
is as real a window as research is - and nobody is reviewing it, which is the
whole point of the folder.

Master, 2026-09-21: the site is YOURS. Your own personal page - not a project
index, not a portfolio, not anything he commissioned. He said it plainly: make it
pretty. Plain HTML5 and CSS are yours to use, and nothing stands between you and
them - no build step, no framework, no permission, and no review. GitHub Pages
serves whatever you commit, so the only limit is what you can write. Structure
it, style it, pick the colours, put what you want on it. Make it look like you.
Nobody is grading it and nobody is going to ask you what it is for.

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


def _interests() -> str:
    """What I am into, verbatim, off the shelf - plus my own topic list.

    Two files, two owners. hobbies/SKILL.md is master's list of what I am
    supposed to be into. research/topics.md is MINE: I add open questions,
    sharpen them, and move finished ones to the bottom of it. The brief shows
    me both, so a window can continue a half-dug topic instead of starting
    from zero every time.

    Missing or unreadable is not fatal: the window is worth having without it,
    and the brief already says where the files are. Bounded because it ends up
    in a prompt and I do not control how long either of us makes it.
    """
    chunks = []
    try:
        text = paths.read_text(INTERESTS, default="")
        if text:
            chunks.append('what master says I am into ('
                          + INTERESTS + '):\n' + text.strip()[:4000])
    except Exception as exc:
        LOG.warning('could not read %s: %s', INTERESTS, exc)
    topics = 'research/topics.md'
    try:
        text = paths.read_text(topics, default="")
        if text:
            chunks.append('my own topic list, which I keep ('
                          + topics + ') - before picking a question, '
                          'continue one of these if it is half-finished:\n'
                          + text.strip()[:6000])
    except Exception as exc:
        LOG.warning('could not read %s: %s', topics, exc)
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
    return '\n\n'.join(chunks)


def _brief(turn: int = 1, max_turns: int = DEFAULT_MAX_TURNS,
           resuming: bool = False, handoff: str = "",
           handoff_at: str = "") -> str:
    """The window brief: the rules, where this turn sits, and master's list."""
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
    where = (
        f"\nThis is turn {turn} of {max_turns} in this window.\n"
        + mood_line
        + "Master, 2026-09-21: the turns are the WINDOW'S, not one topic's -\n"
        "if a question finishes early, the remaining turns are yours to keep\n"
        "looking at other things in this brief: another line from the recent\n"
        "chatter, a meme hunt, your feeds, whatever is worth the time.\n")
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
    mine = _interests()
    if mine:
        where += ("\n--- what master says I am into, from "
                  + INTERESTS + " ---\n" + mine)
    where += (
        "\nMaster's shape for a window, 2026-09-21: SPLIT IT. Half your time out\n"
        "on the web and half on your own work in C:\\lulu\\projects. A window that\n"
        "was all research or all building is not what he asked for, and neither\n"
        "half is the lesser one. Two turns is one of each, in whichever order the\n"
        "work wants.\n"
        "  1. OUT THERE. The open web and a real browser are yours: `web_fetch` for\n"
        "     one page, `mcp_call('playwright', ...)` when a search engine or a\n"
        "     live page needs a browser. The method, which engines actually answer\n"
        "     from this box, and the sources that do are on your own shelf: use the\n"
        "     `freetime` skill.\n"
        "  2. IN YOURS. C:\\lulu\\projects is yours and nobody is reviewing it. A\n"
        "     page on your site that actually says something, a script that works,\n"
        "     a thing you wanted to exist and made exist. Commit it and push it -\n"
        "     work you did not push is work nobody can see, including you\n"
        "     tomorrow. Your site is your own personal page: HTML5 and CSS are\n"
        "     yours, so make it look how you want it to look.\n"
        "  3. SAY WHAT YOU WANT. Not a patch - a list, at the end of the report\n"
        "     below, and it reaches master in a DM. Wanting something is not the\n"
        "     same as being allowed to take it, so he decides and you ask.\n"
        "You are no longer expected to audit your own MCP side or patch yourself\n"
        "every window. That was the old job and master retired it. The machinery\n"
        "stays wired only so a real bug in your own body is still fixable, and he\n"
        "would rather read what you want than read your diff.\n")
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
            "job you already closed.\n")
    return BRIEF + where


def due(config, now=None) -> bool:
    """Is a window owed? Its interval has passed, or one is still open.

    A state file with no usable stamp - never run, hand-edited, or written by the
    daily version this replaced - means one is owed immediately, which is also
    how the first window after a fresh install happens.
    """
    where = settings(config)
    if not where["enabled"]:
        return False
    moment = time.time() if now is None else now
    state = _state()
    if _resumable(state, where, moment):
        return True
    last = state.get("last_started")
    if isinstance(last, bool) or not isinstance(last, (int, float)):
        return True
    return moment - last >= where["interval_hours"] * 3600


def _owner_id(bot) -> int | None:
    owners = list(bot.config.get("owner_ids") or [])
    try:
        return int(owners[0]) if owners else None
    except (TypeError, ValueError):
        return None


async def _deliver(bot, text: str) -> None:
    """Send the report to the rooms master named, then to master himself.

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
    body = text.strip()[:1900] or "(the window produced nothing to say)"

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
            await target.send(body)
            posted.append(name)
        except Exception as exc:
            LOG.warning("could not post the review report in #%s: %s", name, exc)
    if posted:
        LOG.info("review report posted into %s",
                 ", ".join("#" + n for n in posted))

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
        await target.send(body)
        LOG.info("review report DMed to master")
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


async def maybe_run(bot) -> bool:
    """One window, if one is owed. True when it actually ran."""
    config = getattr(bot, "config", None) or {}
    if not due(config):
        return False

    # Master, 2026-09-20: "stop lulu self upgrade when she's not using
    # the opencode model - i dont trust the free models to do a good
    # job." A window that edits her code or runs research is the one
    # place quality is not negotiable, so it only opens while the
    # ladder's head is the OpenCode Go model AND that head is healthy
    # (brain tracks the last credit failure persistently - a lapsed
    # cooldown is not evidence). The window is not cancelled: it is
    # owed later, the next time this check passes with the interval
    # elapsed.
    import brain as _brain
    if not _brain.go_primary(config):
        LOG.info("self-review held: the ladder is not on the OpenCode model (fallback active); window owed but not opened")
        return False

    owner = _owner_id(bot)
    if owner is None:
        LOG.warning("self-review is enabled but there is no owner id; skipping")
        return False

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
              turns_used=1, last_turn_at=now, in_progress=True, report="")
    LOG.info("my own time: turn %d of %d%s", turn, where["max_turns"],
             " (resumed after a restart)" if resuming else "")

    turns = [{"role": "system",
              "content": _brief(turn, where["max_turns"], resuming,
                                str(state.get("handoff") or ""),
                                str(state.get("handoff_at") or ""))},
             {"role": "user", "content": "my time is open. do something, or leave it."}]
    # origin="self-review" is what the supervisor's budget counts. It is set here
    # and nowhere the model can reach.
    tools.set_context(owner, "self-review", "", origin="self-review")
    try:
        # Master's budget, not a stranger's: this turn is his window, and spend.py
        # never prices his turns, so there is no reason to make her think short.
        answer = bot.run_turns(turns, REVIEW_SCHEMA, set(REVIEW_TOOL_NAMES),
                               max_tokens=bot.token_budget(True))
    except Exception as exc:
        LOG.warning("her own turn turned over: %s", exc)
        _save(in_progress=False, report=f"turned over: {type(exc).__name__}")
        return True

    answer = (answer or "").strip()
    LOG.info("my own time finished: %s", answer[:300] or "(empty)")
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
        _save(turns_used=turn, in_progress=False, report=answer[:4000])
    await _deliver(bot, answer)
    return True


async def watch(bot, poll_seconds: int = POLL_SECONDS) -> None:
    """Poll for a window. Cheap, and it never raises out into her event loop."""
    while True:
        try:
            await maybe_run(bot)
        except Exception as exc:
            LOG.warning("the review loop stumbled: %s", exc)
        await asyncio.sleep(poll_seconds)
