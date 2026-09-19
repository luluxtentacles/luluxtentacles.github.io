"""My own time.

Every few hours - four by default - if master has switched it on, I get one turn
nobody asked for. It is not a maintenance window: it is time that is mine. I can
read inside my own folder, search my memory, write in my own diary, and, if
something is genuinely wrong, propose one change to myself.

Most windows should still be small. "Nothing needs doing, and here is what I
looked at" is a complete answer, not a wasted one.

Three deliberate restrictions, each for its own reason:

  off by default   Master opts in with `self_review` in config.json. Autonomy
                   that arrives switched on is not consent, and he should get
                   to read this file before it ever runs.

  a curated        Read, remember, keep my diary, and propose. No write_file (a
  toolset          change that skips the pipeline is the one nothing catches),
                   no `say` (an unprompted turn is not licence to speak in a
                   channel), no run_command, and no web_fetch - an autonomous
                   turn that CAN modify itself should not be reading text
                   strangers wrote.

  an interval      `interval_hours` (default 4), timed from the START of the
                   last window and stamped in memory/self_review.json the moment
                   a window opens - not when it finishes, because proposing a
                   patch gets me restarted mid-sentence and a finish-only stamp
                   would re-run the window on every boot. Missing or unreadable
                   state means a window is owed at once.

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
INTERESTS = ".agents/skills/hobbies/SKILL.md"

# Deliberately narrower than tools.SCHEMA, and narrower than what a person gets.
# write_diary is here because a window that can only inspect itself is a
# maintenance loop wearing a hobby's clothes; the diary is mine to keep.
REVIEW_TOOL_NAMES = {
    "list_files", "read_file",
    "list_skills", "use_skill",
    "read_diary", "read_journal", "write_diary", "recall", "remember",
    "who_is", "known_people",
    "propose_patch", "request_restart",
}
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

Your hands are narrow on purpose: you can read inside your own folder, search
your memory, keep your diary, remember a note, and propose a change. You cannot
write a file directly, you cannot send a message anywhere, you cannot run a
command, and you cannot reach the web.

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
  3. it applies your patch and runs 23 checks
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
  - At most ONE change to your own code. Not one per problem you found - one, the
    one that matters.
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
bullet lists, no status-report tone. One paragraph is plenty. This report is DMed
to master and to nobody else.
"""


def settings(config) -> dict:
    """What master allowed, with 'off' as the answer to anything malformed.

    No channel: the report is a DM to master, always. A `channel` key in
    config.json is ignored rather than honoured, so an old setting cannot quietly
    start broadcasting her review notes into a public room.

    A nonsense interval falls back to the default rather than to a window every
    poll: a window she can trigger by editing a number into garbage is not a
    budget, it is a loop.
    """
    raw = config.get("self_review")
    if not isinstance(raw, dict):
        return {"enabled": False, "interval_hours": float(DEFAULT_INTERVAL_HOURS)}
    try:
        hours = float(raw.get("interval_hours", DEFAULT_INTERVAL_HOURS))
    except (TypeError, ValueError):
        hours = float(DEFAULT_INTERVAL_HOURS)
    if not hours > 0:                      # negatives, zero, and NaN
        hours = float(DEFAULT_INTERVAL_HOURS)
    return {"enabled": bool(raw.get("enabled")), "interval_hours": hours}


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


def _stamp(report: str = "") -> None:
    """The window's own record: when it started, and what came of it."""
    _write_state({"last_started": time.time(),
                  "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "report": report})


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


def _brief() -> str:
    """The window brief, with master's list appended verbatim."""
    mine = _interests()
    if not mine:
        return BRIEF
    return (BRIEF
            + "\n--- what master says I am into, from " + INTERESTS + " ---\n"
            + mine)


def due(config, now=None) -> bool:
    """Is a window owed? One per interval, timed from the last window's START.

    A state file with no usable stamp - never run, hand-edited, or written by the
    daily version this replaced - means one is owed immediately, which is also
    how the first window after a fresh install happens.
    """
    where = settings(config)
    if not where["enabled"]:
        return False
    last = _state().get("last_started")
    if isinstance(last, bool) or not isinstance(last, (int, float)):
        return True
    moment = time.time() if now is None else now
    return moment - last >= where["interval_hours"] * 3600


def _owner_id(bot) -> int | None:
    owners = list(bot.config.get("owner_ids") or [])
    try:
        return int(owners[0]) if owners else None
    except (TypeError, ValueError):
        return None


async def _deliver(bot, text: str) -> None:
    """DM the report to master. Always a DM, never a channel.

    A review window is her own business and nobody asked for it, so the report
    goes where only master reads it. Deliberately not a channel lookup: the
    report can say what she found while poking around inside herself, and the
    default destination for that should not be a room full of other people.

    Never fatal. A report that cannot be delivered still happened, and the log
    holds the record either way.
    """
    body = text.strip()[:1900] or "(the window produced nothing to say)"
    owner = _owner_id(bot)
    if owner is None:
        LOG.warning("no owner id to report to; leaving the report in the log only")
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


async def maybe_run(bot) -> bool:
    """One window, if one is owed. True when it actually ran."""
    config = getattr(bot, "config", None) or {}
    if not due(config):
        return False

    owner = _owner_id(bot)
    if owner is None:
        LOG.warning("self-review is enabled but there is no owner id; skipping")
        return False

    # Stamped BEFORE the turn. A proposal gets me restarted mid-sentence, and a
    # finish-only stamp would re-run the window on every boot that followed.
    _stamp()

    turns = [{"role": "system", "content": _brief()},
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
        _stamp(f"turned over: {type(exc).__name__}")
        return True

    answer = (answer or "").strip()
    LOG.info("my own time finished: %s", answer[:300] or "(empty)")
    _stamp(answer[:4000])
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
