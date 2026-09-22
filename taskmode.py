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

A task turn is a full run_turns() call, each round resending the whole prompt.
That is the expensive shape in this codebase, so the brake is a turn cap and not
vibes. Master's turns are never priced by spend.py, so the cap is the only thing
standing between "handle this properly" and a bill.

Inside a turn there is no ROUND ceiling any more - master, 2026-09-22: "give her
unlimited too calls for these", and "these" is a task and one of her own-time
windows. What replaces the count is lulu_bot's strike rule - the same tool call
failing the same way three times, and the fourth identical attempt refused
altogether - plus the per-call deadline. So a turn that is going somewhere is no
longer cut off mid-job at forty rounds, and a turn that is going nowhere cannot
spin instead.

Three things stop a task that will not stop on its own:

    MAX_TASK_TURNS          hard ceiling, counted on disk so a restart cannot
                            reset it
    IDLE_TURNS_BEFORE_STOP  consecutive turns that called no tool and changed
                            nothing - that is a stuck agent, not a working one
    the strike rule         inside a turn: three identical failures, then a
                            refusal - see lulu_bot.STRIKE_LIMIT

ONE THING AT A TIME

Master, 2026-09-22: "if theres a current task happening, lulu will wait till
it's finished before starting her free time and vice versa". So step() takes no
turn while one of her own-time windows is open (self_review.window_open), and
self_review refuses to OPEN a window while this file says a task is open. The
wait runs both ways, and the direction that breaks the tie is that a window
already open is allowed to finish its turns - two waits facing each other would
be a deadlock rather than a queue. A wait is announced ONCE, not once a tick,
because a job held in silence looks exactly like a job that has hung.

WHAT HAPPENS WHEN THE TURNS RUN OUT

It used to close, quietly, on a summary nobody saw. Master's call, 2026-09-21:
she gets the window, and when it ends with the job unfinished she says so and
asks whether to keep going - so a job bigger than one window is a conversation
rather than a dead end. The task goes to `waiting`, which is NOT `open`, so
watch() stops taking turns and the meter stops with it. Master answers in the
room he gave the job in; the turn that hears that answer calls keep_going and the
task gets a fresh window with its history intact.

A task that waits longer than WAITING_MAX_AGE_SECONDS is boxed up as done
instead. An ask he never answered must not sit there and then fire the next time
he says something unrelated in that room.

WHERE IT SPEAKS

Master's call, 2026-09-21: channel and DM, both. The per-turn report and the ask
go to the ROOM the job came from - captured at start() from the turn that asked,
never from a tool call - and to the DM as well. It used to DM only, which cut
against her own voice rule: everything she says belongs in the room she was
talked to in.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

import conversation
import paths

LOG = logging.getLogger("lulu.task")

# Where the open task lives. Root level, NOT memory/: memory/ is a sealed tier,
# so the wall refuses every write there and a task file in it could never be
# saved at all. Same reasoning as chatter.json and spend.json.
STATE = "task.json"
# A turn every this long. Long enough that consecutive turns do not overlap while
# master is watching, short enough that a task feels alive rather than queued.
TICK_SECONDS = 20
# The hard ceiling, and it is now the ONLY brake on the size of a task: the
# rounds INSIDE a turn are unlimited (see the docstring), so this is what stops a
# job that keeps taking turns without ever finishing.
MAX_TASK_TURNS = 12
# Consecutive turns with no tool calls at all. Two means I am circling.
IDLE_TURNS_BEFORE_STOP = 2
# One report per turn, so it cannot grow into a wall.
ANNOUNCE_MAX = 1200
# How long an unanswered "shall I keep going?" waits before the task is closed
# for good. See the docstring: a stale ask that fires hours later, when master
# says something unrelated in that room, is worse than a task that just ended.
WAITING_MAX_AGE_SECONDS = 24 * 3600

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
  - FINISH WHEN IT IS FINISHED, and never spend a turn you do not need. The
    count below is a CEILING, not a quota - a job done on turn three is done on
    turn three, and stopping there is the point rather than a shortcut. Calling
    finish_task stops the task on the spot; nothing sits out the clock. Do not
    pad a turn to look busy either.
  - When the job is done, or you are genuinely stuck and need him, call
    finish_task with the answer. If you cannot finish it, say what is blocking
    you AND call finish_task.

Turn {turn} of at most {limit} - sooner the moment there is nothing left worth
doing.\
"""

# A LATER turn of a task that already has a thread. The rules above are at the top
# of that thread where they were given, so this says only what CHANGED - the same
# shape a window of her own time uses, for the same reason: one home for a rule.
COMPACT = """\
Still on the long task, not answering a message - master gave you a job and you get
several turns to do it, and this is one of them.

The job: {goal}

Turn {turn} of at most {limit} - sooner the moment there is nothing left worth
doing.\
"""


# -- the state ---------------------------------------------------------------

def _empty() -> dict:
    return {}


def _task(status: str) -> dict:
    """The task sitting in this state, or {} when there is none. Never raises."""
    try:
        data = json.loads(paths.read_text(STATE, default="{}"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data if data.get("status") == status else {}


def current() -> dict:
    """The OPEN task, or {} when there is none. Never raises."""
    return _task("open")


def waiting() -> dict:
    """The task parked on master's answer, or {} when there is none.

    Deliberately not the same as current(): a waiting task must cost nothing, so
    watch() - which drives off is_active() - leaves it alone until he answers.
    """
    return _task("waiting")


def is_active() -> bool:
    return bool(current())


def _save(data: dict) -> None:
    try:
        paths.write_json(STATE, data)
    except Exception as exc:
        LOG.warning("could not save the task: %s", exc)


def start(goal: str, by: str = "master", room: str = "", room_id=None) -> str:
    """Open a task. Refuses to clobber one already running.

    `room` is where master asked for the job, captured by the caller from the
    turn that asked - never from a tool call, because a job should report where
    it was given rather than wherever the model felt like naming. Empty means
    the ask came in a DM, and then the DM IS the room and there is no second
    place to post.
    """
    goal = " ".join(str(goal or "").split())
    if not goal:
        return "a task needs a goal - tell me what the job is"
    live = current()
    if live:
        return (f"there is already a task open: {live.get('goal')!r}. "
                f"finish it first, or ask me to drop it.")
    room = str(room or "").strip().lstrip("#").lower()
    try:
        room_id = int(room_id) if room_id is not None else None
    except (TypeError, ValueError):
        room_id = None
    _save({
        "status": "open",
        "goal": goal[:1000],
        "by": str(by or "master"),
        "room": room,
        "room_id": room_id if room else None,
        "turn": 0,
        "windows": 1,
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": time.time(),
        "history": [],
        # The task's own conversation, the same shape as a window's. Empty at the
        # start, and carried from turn to turn after that.
        "thread": [],
    })
    LOG.info("task opened: %s", goal[:120])
    where = f"#{room}" if room else "your DMs"
    return (f"task open: {goal[:200]}. I get {MAX_TASK_TURNS} turns, one every "
            f"{TICK_SECONDS}s, and you hear about every one of them in {where}.")


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


def keep_going(note: str = "") -> str:
    """Master said carry on: same task, fresh window, history kept.

    Only ever answers a task that is actually WAITING - and that is what makes
    this safe to hand a model. "Keep going" cannot resurrect a job that finished
    or one that was never opened; it can only release one she has already
    stopped on and asked about.
    """
    live = waiting()
    if not live:
        return "nothing of mine is waiting on an answer"
    live["status"] = "open"
    live["turn"] = 0
    live["idle"] = 0
    live["windows"] = int(live.get("windows") or 1) + 1
    live.pop("waiting_since", None)
    if note:
        live["answer"] = " ".join(str(note).split())[:600]
    _save(live)
    LOG.info("task window %s opened on: %s", live.get("windows"),
             str(live.get("goal"))[:120])
    return (f"back on it - window {live.get('windows')}, {MAX_TASK_TURNS} more "
            f"turns on: {str(live.get('goal'))[:160]}")


def _expire(now: float | None = None) -> bool:
    """Close a task nobody answered. True when one was boxed up.

    The ask must not sit forever: a waiting task that fires tonight, when master
    says something unrelated in that room, would have her reading an ordinary
    message as permission to spend twelve more turns on yesterday's job. Cheap
    to sweep here because the loop already runs every tick.
    """
    live = waiting()
    if not live:
        return False
    try:
        age = (now if now is not None else time.time()) - float(
            live.get("waiting_since"))
    except (TypeError, ValueError):
        age = WAITING_MAX_AGE_SECONDS + 1
    if age <= WAITING_MAX_AGE_SECONDS:
        return False
    live["status"] = "done"
    live["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    live["summary"] = "closed: nobody answered whether to keep going"
    _save(live)
    LOG.info("task expired unanswered after %.0fs", age)
    return True


def pending_ask(room: str = "") -> str:
    """The job she is parked on in this room, or "" when there is none.

    Read by the message path, so that the turn which hears master's reply knows
    it IS the reply - otherwise he says "yeah go on" and she answers it as a
    fresh remark with no idea what she is agreeing to. The room has to match,
    for the same reason resume_brief insists on it, and an empty name means his
    DMs.

    Returns the goal RAW. Escaping belongs to the caller that builds the prompt,
    the same as every other line that reaches one.
    """
    live = waiting()
    if not live:
        return ""
    where = str(live.get("room") or "").strip().lstrip("#").lower()
    here = str(room or "").strip().lstrip("#").lower()
    if where != here:
        return ""
    return str(live.get("goal") or "")


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


async def _say_in_room(bot, live: dict, body: str) -> None:
    """Report where the job came from. Silent when it came from the DMs."""
    room_id = (live or {}).get("room_id")
    if not room_id:
        return
    try:
        channel = bot.get_channel(int(room_id))
        if channel is None:
            channel = await bot.fetch_channel(int(room_id))
        await channel.send(body)
    except Exception as exc:
        # One dead room must never cost the report - the DM below still goes.
        LOG.warning("could not report to the room: %s", exc)


async def _tell(bot, text: str, live: dict | None = None) -> None:
    """Say it in the room the job came from AND in master's DMs. Never fatal."""
    body = (text or "").strip()[:ANNOUNCE_MAX] or "(no words for that turn)"
    # Master's call, 2026-09-21: both. The room is where he is looking while the
    # job runs, and the DM is the copy that survives him scrolling past it.
    await _say_in_room(bot, live or {}, body)
    owner = None
    try:
        owners = list((bot.config or {}).get("owner_ids") or [])
        owner = int(owners[0]) if owners else None
    except (TypeError, ValueError):
        owner = None
    if owner is None:
        LOG.warning("no owner id to report the task to")
        return
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


async def _park(bot, live: dict) -> bool:
    """The window is spent and the job is not: ask, do not close.

    Master's call, 2026-09-21. The task goes to `waiting`, which is not `open`,
    so the loop that takes turns stops here and the meter stops with it until he
    answers. Always returns False - a turn was not taken.
    """
    live["status"] = "waiting"
    live["waiting_since"] = time.time()
    live["summary"] = (f"used all {MAX_TASK_TURNS} turns of window "
                       f"{live.get('windows') or 1} without finishing")
    _save(live)
    LOG.info("task parked on master after %s turn(s)", live.get("turn"))
    await _tell(bot,
                f"not done on: {str(live.get('goal'))[:200]}. i've used all "
                f"{MAX_TASK_TURNS} turns of this window - want me to keep "
                f"going?", live)
    return False


# Whether master has already been told that his job is sitting behind one of her
# own-time windows. Module-level because it is about THIS conversation with him,
# not about the task: the point is one message per wait, not one per tick.
_HELD_BY_WINDOW = False


def _window_open() -> bool:
    """Is one of her own-time windows open right now? Never raises; no on doubt.

    Through self_review's own door rather than by reading memory/self_review.json
    here: two definitions of "a window is open" is how the two of them drift
    apart. The import is local because self_review reaches back into this file
    for is_active(), and a module-level pair of imports would be a cycle.

    A check that cannot run answers NO, which means the task keeps working. The
    other answer would let an import hiccup park master's job indefinitely.
    """
    try:
        import self_review
        return self_review.window_open()
    except Exception as exc:
        LOG.warning("could not tell whether a window is open: %s", exc)
        return False


async def _held_notice(bot, live: dict, held: bool) -> None:
    """Tell master ONCE that his job is waiting on her own time, and once more
    when it starts moving again.

    Only the transitions: a long window would otherwise DM him every twenty
    seconds. Both messages are the same bargain the per-turn report makes - a
    job he cannot see is indistinguishable from a job that has hung, so a wait
    gets words.
    """
    global _HELD_BY_WINDOW
    if held == _HELD_BY_WINDOW:
        return
    _HELD_BY_WINDOW = held
    LOG.info("task %s: %s", "held by an open free-time window" if held
             else "moving again", live.get("goal"))
    if held:
        await _tell(bot, ("holding your job for now - my own time is open, and "
                          "we do one thing at a time, so this waits for that "
                          "window to finish. "
                          + str(live.get("goal") or "")[:200]), live)
    else:
        await _tell(bot, ("the window is closed - picking the job back up: "
                          + str(live.get("goal") or "")[:200]), live)


async def step(bot) -> bool:
    """Take one turn of the open task. True when a turn was actually taken."""
    live = current()
    if not live:
        return False

    # Master, 2026-09-22: a task and a window of her own do not run at the same
    # time, and this is the half where HIS job waits. It waits rather than
    # closes - the window finishes its turns and the next tick here picks the
    # job back up with its history intact, exactly as a restart does.
    if _window_open():
        await _held_notice(bot, live, True)
        return False
    await _held_notice(bot, live, False)

    turn = int(live.get("turn") or 0) + 1
    if turn > MAX_TASK_TURNS:
        return await _park(bot, live)

    # ONE CONVERSATION FOR THE TASK. Master, 2026-09-23: *"fix this for task
    # also"*. Each turn used to be built from scratch out of a digest of the last
    # six turns, so she was reading a summary of her own job instead of the job.
    # Now the task keeps ONE thread, exactly as a window does: the rules go in on
    # the first turn and stay at the top, and a later turn adds only what changed.
    # `history` is still maintained and still shown on a FIRST turn - it is the
    # fallback for a task whose thread did not survive, and the idle rule below
    # reads the live turns, not this.
    thread = conversation.read(live)
    if thread:
        thread.append({"role": "system", "content": COMPACT.format(
            goal=live.get("goal"), turn=turn, limit=MAX_TASK_TURNS)})
    else:
        thread = [{"role": "system", "content": BRIEF.format(
            goal=live.get("goal"), history=_history_text(live),
            turn=turn, limit=MAX_TASK_TURNS)}]
    thread.append({"role": "user", "content": "take the next step."})
    # A COPY, deliberately: run_turns folds the list it is handed once the prompt
    # nears the window (compact_history returns a NEW list and does not touch the
    # dicts), and the thread she keeps must not fill up with raw tool output -
    # which is also what keeps _tools_used below honest, since it reads this list
    # for tool turns and the thread never contains one.
    turns = list(thread)

    # Full hands, master's budget: this is his job and his money, and spend.py
    # never prices his turns. The cap above is the brake instead.
    import tools  # deferred: tools imports nothing of mine, but this keeps the
                  # import graph one-way and obvious.
    schema, allowed = tools.SCHEMA, set(tools.DISPATCH)
    # A task turn says what it is, and both halves matter. `origin="task"` is
    # what lets a turn doing master's job read a picture out of my own folder
    # (see look_at_file), and tools.in_thread rather than a bare
    # asyncio.to_thread is what makes that TRUE inside the worker: in_thread
    # snapshots this thread's context and CLEARS the pooled thread's own, which
    # is also what stops a task inheriting the origin the last job left behind -
    # a task's patch counted against her own-time budget, or a stranger's turn
    # counted as master's.
    tools.set_context(None, "task", "", origin="task")
    try:
        # In a THREAD, not straight off the loop: run_turns blocks on HTTP for
        # every round, and this turn has no round ceiling (unlimited_rounds,
        # below). Called inline it would stall the event loop for minutes - and
        # Discord's heartbeat with it. Same reason on_message wraps think() in
        # to_thread.
        answer = await tools.in_thread(
            bot.run_turns, turns, schema, allowed, None, bot.token_budget(True),
            unlimited_rounds=True)
    except Exception as exc:
        LOG.warning("task turn failed: %s", exc)
        live = _record(live, f"turn blew up: {type(exc).__name__}", False)
        live["turn"] = turn
        _save(live)
        await _tell(bot, f"turn {turn} blew up on: {live.get('goal')} "
                         f"({type(exc).__name__}). still open.", live)
        return True
    finally:
        # The context belongs to ONE turn, and the loop thread this function
        # runs on also serves master's messages. A task's origin left standing
        # there would be read by whatever runs next and does not set its own.
        tools.set_context(None)

    used = _tools_used(turns)
    answer = (answer or "").strip()
    live = _record(live, answer or "(said nothing)", used)
    live["turn"] = turn
    # Her own words go back into the thread, so the next turn reads the job as a
    # conversation it is in rather than a digest of it. The placeholder matches
    # _record's own, because a turn that said nothing still happened and leaving
    # the gap bare would put two user turns in a row.
    thread.append({"role": "assistant", "content": answer or "(said nothing)"})
    live["thread"] = conversation.trim(thread)
    _save(live)

    # Report first, then look at the idle rule: master should hear the turn even
    # if it is the one that ends the task.
    await _tell(bot, f"[{live.get('goal')[:120]} - turn {turn}/{MAX_TASK_TURNS}]\n"
                     f"{answer or '(no words that turn)'}", live)

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
                             f"still open to talk about if you want.", live)
    else:
        live["idle"] = 0
        _save(live)
    return True


async def watch(bot, tick: int = TICK_SECONDS) -> None:
    """Take one turn every tick while a task is open. Never raises outward.

    Deliberately not an unconditional loop over step(): a task closed by its own
    last turn must stop costing money immediately, so each pass re-reads the file
    rather than trusting a variable held in memory. The same pass sweeps an ask
    nobody answered, so a waiting task cannot live forever.
    """
    while True:
        try:
            if is_active():
                await step(bot)
            else:
                _expire()
        except Exception as exc:
            LOG.warning("the task loop stumbled: %s", exc)
        await asyncio.sleep(tick)
