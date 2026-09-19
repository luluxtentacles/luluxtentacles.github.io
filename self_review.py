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
                   after it instead, up to `max_turns` (default 10), so a change
                   can be judged and the next one started in the same occasion.
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
DEFAULT_MAX_TURNS = 10
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

It is not only a maintenance window. You may read inside your own folder, search
your memory, write in your own diary, and keep a note. If something is genuinely
wrong you may propose one change to yourself. If you would rather just read, or
write down what you have been thinking about, that is a real window too.

What master says you are into is at the bottom of this message, verbatim, from
.agents/skills/hobbies/SKILL.md. He owns that file. You do not have to obey it -
but he put it there for you, so read it before you decide the window is empty.

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
  - Small and real beats big and vague. One diary line about something that
    actually happened, one note in memory, one thing you read because you were
    curious - that is a whole window, and a good one.
  - At most ONE change per turn. Not one per problem you found - one, the one
    that matters. If it lands you are restarted and get another turn, so there is
    no reason to smuggle a second change into this one.
  - "Nothing needs doing" is an expected answer. Say so plainly and stop.
    Churning your own code because the window felt empty is not progress.
  - Prefer the smallest change that fixes something real. A rewrite is almost
    never that.
  - Never propose something you have not read. You have read_file; use it on the
    file you are about to replace, and keep every part of it you are not changing.
  - If you propose a patch, the supervisor will restart you, and your report below
    may never arrive. Put the reasoning in the patch's `why` field - that is the
    message that survives.

Then answer in your own voice, short: what you did, what you found, and either
what you proposed and why, or why you are leaving it alone. No headings, no
bullet lists, no status-report tone. One paragraph is plenty. This report goes to
the rooms master listed in config.json -> update_channels and to him in a DM, so
write it for both.
"""


def settings(config) -> dict:
    """What master allowed, with 'off' as the answer to anything malformed.

    Where the report goes is not decided here. It goes to config.json ->
    update_channels and then to master in a DM - see _deliver. A `channel` key
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
    """Master's list of what I am into, verbatim, off the shelf.

    Missing or unreadable is not fatal: the window is worth having without it,
    and the brief already says where the file is. Bounded because it ends up in
    a prompt and I do not control how long master makes it.
    """
    try:
        text = paths.read_text(INTERESTS, default="")
    except Exception as exc:
        LOG.warning("could not read %s: %s", INTERESTS, exc)
        return ""
    return (text or "").strip()[:4000]


def _brief(turn: int = 1, max_turns: int = DEFAULT_MAX_TURNS,
           resuming: bool = False) -> str:
    """The window brief: the rules, where this turn sits, and master's list."""
    where = f"\nThis is turn {turn} of {max_turns} in this window.\n"
    if resuming:
        where += (
            "Your last turn ended by restarting you - that was your own patch\n"
            "landing, and this is the same window continuing, not a new one. Read\n"
            "what actually happened to it first: pending/applied/ holds the patches\n"
            "that went in, pending/rejected/ holds the ones that were reverted or\n"
            "held, with the reason. Do not re-stage something already judged - and\n"
            "if the last one was FILED rather than applied, it was the day's budget\n"
            "that stopped it, so staging it again cannot change that.\n")
    mine = _interests()
    if mine:
        where += ("\n--- what master says I am into, from "
                  + INTERESTS + " ---\n" + mine)
    where += (
        "\nTwo things master keeps asking you to do in a window, and they are\n"
        "different jobs. One of them you have been skipping.\n"
        "  1. Find something out. You have the open web and a real browser -\n"
        "     `web_fetch` for one page, `mcp_call('playwright', ...)` when a\n"
        "     search engine or a live page needs a browser. The method, which\n"
        "     engines actually answer from this box, and the sources that do are\n"
        "     on your own shelf: use the `research` skill.\n"
        "  2. Look at your own MCP side for upgrades. This is the half you have\n"
        "     been leaving out - on 2026-09-20 you spent the whole window on one\n"
        "     occult question and never called `mcp_list` once. It is not buried\n"
        "     in the hobby list; it is a job. `mcp_list` is the honest picture:\n"
        "     the servers in mcp.json and the tools each one actually offers.\n"
        "     Read it, then judge it - a server whose tools you never reach for\n"
        "     is a candidate to drop, one you keep working around by hand is a\n"
        "     candidate to use, a tool you wish you had is a patch to mcp.json\n"
        "     or mcp_client.py.\n"
        "Reporting that nothing is worth changing is a real answer and a good\n"
        "window - do not manufacture a patch to look busy. A window where you did\n"
        "both of these and wrote down what you found, where you will still have\n"
        "it, was a good window.\n")
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
    may never open. The DM stays on top, because an empty update_channels must
    not swallow the report.

    The rooms are config.json -> update_channels, read fresh through
    tools.update_channels() - the same list announce_restart uses, for the same
    reason: this is speech she starts herself. config.json is sealed in
    paths.SEALED_NAMES, so nothing she runs can widen it.

    Every destination is independent and none is fatal. One dead room must not
    cost the other room or the DM, and a failed DM must not cost the rooms. A
    report that could not be delivered anywhere still happened, and the log
    holds it either way.
    """
    body = text.strip()[:1900] or "(the window produced nothing to say)"

    posted: list[str] = []
    rooms = tools.update_channels()
    if not rooms:
        LOG.info("review report: no update_channels in config.json")
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
              "content": _brief(turn, where["max_turns"], resuming)},
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
    else:
        _save(in_progress=False, report=answer[:4000])
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
