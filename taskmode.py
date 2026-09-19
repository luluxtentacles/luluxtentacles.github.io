"""Long tasks - the one thing I do over several turns instead of one reply.

A normal message gets one turn: I think, maybe call a tool or two, and answer.
That is right for a question and useless for a job. This is for a job.

WHAT MAKES IT DIFFERENT

    a task has state on disk    goal, what I have done, which turn I am on. It
                                survives a restart, because a long task and a
                                restart are not mutually exclusive events.
    a worker takes turns        taskmode.watch() takes ONE step every tick while
                                a task is open, so "several turns" is real
                                rather than a bigger tool budget inside one turn.
    master hears every turn     after each step he gets a DM saying what just
                                happened. That is the point: a long task he
                                cannot see is indistinguishable from a hang.

WHO GETS IT

Only master, and structurally rather than by politeness: start_task and
finish_task are in tools.DISPATCH but deliberately NOT in tools.LOOKUP_TOOL_NAMES,
and that list is the only thing non-master is ever offered. A stranger cannot
start a task because a stranger is never told the tool exists.

WHAT IT COSTS, HONESTLY

A task turn is a full run_turns() call, which is up to MAX_TOOL_ROUNDS brain
calls, each resending the whole prompt. That is the expensive shape in this
codebase, so the brake is a turn cap and not vibes. Master's turns are never
priced by spend.py, so the cap is the only thing standing between "handle this
properly" and a bill.

Two things stop a task that will not stop on its own:

    MAX_TASK_TURNS          hard ceiling, counted on disk so a restart cannot
                            reset it
    IDLE_TURNS_BEFORE_STOP  consecutive turns that called no tool and changed
                            nothing - that is a stuck agent, not a working one
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import paths

LOG = logging.getLogger("lulu.task")

# Where the open task lives. Root level, NOT memory/: memory/ is a sealed tier,
# so the wall refuses every write there and a task file in it could never be
# saved at all. Same reasoning as chatter.json and spend.json.
STATE = "task.json"
# A turn every this long. Long enough that consecutive turns do not overlap while
# master is watching, short enough that a task feels alive rather than queued.
TICK_SECONDS = 20
# The hard ceiling. See the module docstring: this is the brake, because a task
# turn is up to MAX_TOOL_ROUNDS brain calls.
MAX_TASK_TURNS = 12
# Consecutive turns with no tool calls at all. Two means I am circling.
IDLE_TURNS_BEFORE_STOP = 2
# One DM per turn, so the report cannot grow into a wall.
ANNOUNCE_MAX = 1200

BRIEF = """\
You are on a long task, not answering a message. Master gave you a job and you
get several turns to do it - this is one of them.

The job: {goal}

What you have done so far:
{history}

Rules for a task turn:
  - Take ONE useful step. Do the next real thing, not a survey of everything.
  - Use your tools. A turn that calls no tool is usually a turn you should have
    spent working.
  - Say what you DID, in a sentence or two, in your own voice. Master is reading
    this in Discord between turns - no headings, no bullet lists, no status
    report tone.
  - When the job is finished, or you are genuinely stuck and need him, call
    finish_task with the answer. Do not keep a task open to look busy.
  - If you cannot finish it, say what is blocking you AND call finish_task. A
    task that runs out of turns and goes quiet is the one bad outcome.

Turn {turn} of at most {limit}.\
"""


# -- the state ---------------------------------------------------------------

def _empty() -> dict:
    return {}


def current() -> dict:
    """The open task, or {} when there is none. Never raises."""
    try:
        data = json.loads(paths.read_text(STATE, default="{}"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data if data.get("status") == "open" else {}


def is_active() -> bool:
    return bool(current())


def _save(data: dict) -> None:
    try:
        paths.write_json(STATE, data)
    except Exception as exc:
        LOG.warning("could not save the task: %s", exc)


def start(goal: str, by: str = "master") -> str:
    """Open a task. Refuses to clobber one already running."""
    goal = " ".join(str(goal or "").split())
    if not goal:
        return "a task needs a goal - tell me what the job is"
    live = current()
    if live:
        return (f"there is already a task open: {live.get('goal')!r}. "
                f"finish it first, or ask me to drop it.")
    _save({
        "status": "open",
        "goal": goal[:1000],
        "by": str(by or "master"),
        "turn": 0,
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": time.time(),
        "history": [],
    })
    LOG.info("task opened: %s", goal[:120])
    return (f"task open: {goal[:200]}. I get {MAX_TASK_TURNS} turns, one every "
            f"{TICK_SECONDS}s, and master gets a DM after each one.")


def finish(summary: str = "") -> str:
    """Close the task and say how it went."""
    live = current()
    if not live:
        return "no task is open"
    summary = " ".join(str(summary or "").split())
    live["status"] = "done"
    live["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    live["summary"] = summary[:2000] or "(no summary given)"
    _save(live)
    LOG.info("task closed after %s turn(s): %s", live.get("turn"), summary[:120])
    return f"task closed after {live.get('turn')} turn(s)"


def drop() -> str:
    """Abandon the open task without finishing it."""
    live = current()
    if not live:
        return "no task is open"
    live["status"] = "dropped"
    live["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save(live)
    LOG.info("task dropped by hand")
    return "task dropped"


def _record(live: dict, said: str, used_tools: bool) -> dict:
    """Fold one turn into the task's own memory of itself."""
    history = list(live.get("history") or [])
    history.append({"turn": live.get("turn"),
                    "at": time.strftime("%H:%M:%S"),
                    "said": said[:600],
                    "tools": bool(used_tools)})
    # Keep the brief bounded. The last few turns are what matters; an unbounded
    # history would be re-sent every turn and grow the prompt without limit.
    live["history"] = history[-6:]
    return live


# -- the turn ----------------------------------------------------------------

def _history_text(live: dict) -> str:
    history = live.get("history") or []
    if not history:
        return "  (nothing yet - this is the first turn)"
    lines = []
    for item in history:
        mark = "did" if item.get("tools") else "said, no tools"
        lines.append(f"  turn {item.get('turn')}: {mark} - {item.get('said')}")
    return "\n".join(lines)


async def _tell(bot, text: str) -> None:
    """DM master. Never fatal - a task that cannot report still ran."""
    owner = None
    try:
        owners = list((bot.config or {}).get("owner_ids") or [])
        owner = int(owners[0]) if owners else None
    except (TypeError, ValueError):
        owner = None
    if owner is None:
        LOG.warning("no owner id to report the task to")
        return
    body = (text or "").strip()[:ANNOUNCE_MAX] or "(no words for that turn)"
    try:
        target = await bot.fetch_user(owner)
        await target.send(body)
    except Exception as exc:
        LOG.warning("could not DM the task update: %s", exc)


def _tools_used(turns: list) -> bool:
    """Did this turn actually call anything? Read straight off the transcript."""
    for turn in turns:
        if turn.get("role") == "tool":
            return True
    return False


async def step(bot) -> bool:
    """Take one turn of the open task. True when a turn was actually taken."""
    live = current()
    if not live:
        return False

    turn = int(live.get("turn") or 0) + 1
    if turn > MAX_TASK_TURNS:
        live["status"] = "done"
        live["summary"] = f"ran out of turns ({MAX_TASK_TURNS}) without finishing"
        _save(live)
        await _tell(bot, f"out of turns on: {live.get('goal')} - "
                         f"{live.get('summary')}. tell me to pick it up again "
                         f"if you want me to keep going.")
        return False

    brief = BRIEF.format(goal=live.get("goal"), history=_history_text(live),
                         turn=turn, limit=MAX_TASK_TURNS)
    turns = [{"role": "system", "content": brief},
             {"role": "user", "content": "take the next step."}]

    # Full hands, master's budget: this is his job and his money, and spend.py
    # never prices his turns. The cap above is the brake instead.
    import tools  # deferred: tools imports nothing of mine, but this keeps the
                  # import graph one-way and obvious.
    schema, allowed = tools.SCHEMA, set(tools.DISPATCH)
    try:
        # In a THREAD, not straight off the loop: run_turns blocks on HTTP for
        # every round, and one turn here can be MAX_TOOL_ROUNDS of them. Called
        # inline it would stall the event loop for minutes - and Discord's
        # heartbeat with it. Same reason on_message wraps think() in to_thread.
        answer = await asyncio.to_thread(
            bot.run_turns, turns, schema, allowed, None, bot.token_budget(True))
    except Exception as exc:
        LOG.warning("task turn failed: %s", exc)
        live = _record(live, f"turn blew up: {type(exc).__name__}", False)
        live["turn"] = turn
        _save(live)
        await _tell(bot, f"turn {turn} blew up on: {live.get('goal')} "
                         f"({type(exc).__name__}). still open.")
        return True

    used = _tools_used(turns)
    answer = (answer or "").strip()
    live = _record(live, answer or "(said nothing)", used)
    live["turn"] = turn
    _save(live)

    # Report first, then look at the idle rule: master should hear the turn even
    # if it is the one that ends the task.
    await _tell(bot, f"[{live.get('goal')[:120]} - turn {turn}/{MAX_TASK_TURNS}]\n"
                     f"{answer or '(no words that turn)'}")

    if not used:
        idle = int(live.get("idle") or 0) + 1
        live["idle"] = idle
        if idle >= IDLE_TURNS_BEFORE_STOP:
            live["status"] = "done"
            live["summary"] = ("stopped: consecutive turns that did nothing and "
                               "called no tools")
            _save(live)
            await _tell(bot, f"stopping that task - {idle} turns in a row with no "
                             f"tools called, so I am circling rather than working. "
                             f"still open to talk about if you want.")
    else:
        live["idle"] = 0
        _save(live)
    return True


async def watch(bot, tick: int = TICK_SECONDS) -> None:
    """Take one turn every tick while a task is open. Never raises outward.

    Deliberately not an unconditional loop over step(): a task closed by its own
    last turn must stop costing money immediately, so each pass re-reads the file
    rather than trusting a variable held in memory.
    """
    while True:
        try:
            if is_active():
                await step(bot)
        except Exception as exc:
            LOG.warning("the task loop stumbled: %s", exc)
        await asyncio.sleep(tick)
