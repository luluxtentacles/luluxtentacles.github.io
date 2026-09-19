"""My review window.

Once a day, if master has switched it on, I get one turn nobody asked for. The
point is not to change something: it is to be allowed to notice. Most windows
should end with "nothing needs changing", and that is a good outcome, not a
wasted one.

Three deliberate restrictions, each for its own reason:

  off by default   Master opts in with `self_review` in config.json. Autonomy
                   that arrives switched on is not consent, and he should get
                   to read this file before it ever runs.

  a curated        Read, remember, and propose. No write_file (a change that
  toolset          skips the pipeline is the one nothing catches), no `say`
                   (an unprompted turn is not licence to speak in a channel),
                   and no web_fetch - an autonomous turn that CAN modify itself
                   should not be reading text strangers wrote.

  one window       Stamped in memory/self_review.json the moment it starts, not
  a day            when it finishes, because proposing a patch gets me restarted
                   mid-sentence and a finish-only stamp would re-run the window
                   on every boot.

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
DEFAULT_HOUR = 4

# Deliberately narrower than tools.SCHEMA, and narrower than what a person gets.
REVIEW_TOOL_NAMES = {
    "list_files", "read_file",
    "list_skills", "use_skill",
    "read_diary", "read_journal", "recall", "remember",
    "who_is", "known_people",
    "propose_patch", "request_restart",
}
REVIEW_SCHEMA = [t for t in tools.SCHEMA
                 if t["function"]["name"] in REVIEW_TOOL_NAMES]

BRIEF = """\
This is your own review window. Nobody asked for it and nobody is waiting.

You get one turn with a narrow set of hands: you can read inside your own folder,
search your memory, and propose a change. You cannot write a file directly, you
cannot send a message anywhere, and you cannot reach the web.

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
  - At most ONE change. Not one per problem you found - one, the one that matters.
  - "Nothing needs changing" is the expected answer most days. Say so plainly and
    stop. Churning your own code is not progress.
  - Prefer the smallest change that fixes something real. A rewrite is almost
    never that.
  - Never propose something you have not read. You have read_file; use it on the
    file you are about to replace, and keep every part of it you are not changing.
  - If you propose a patch, the supervisor will restart you, and your report below
    may never arrive. Put the reasoning in the patch's `why` field - that is the
    message that survives.

Then answer in your own voice, short: what you looked at, what you found, and
either what you proposed and why, or why you are leaving it alone. No headings,
no bullet lists, no status-report tone. One paragraph is plenty.
"""


def settings(config) -> dict:
    """What master allowed, with 'off' as the answer to anything malformed.

    No channel: the report is a DM to master, always. A `channel` key in
    config.json is ignored rather than honoured, so an old setting cannot quietly
    start broadcasting her review notes into a public room.
    """
    raw = config.get("self_review")
    if not isinstance(raw, dict):
        return {"enabled": False, "hour": DEFAULT_HOUR}
    try:
        hour = int(raw.get("hour", DEFAULT_HOUR))
    except (TypeError, ValueError):
        hour = DEFAULT_HOUR
    return {"enabled": bool(raw.get("enabled")), "hour": hour % 24}


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


def due(config, now=None) -> bool:
    """Is a window owed? One per calendar day, at or after the configured hour."""
    where = settings(config)
    if not where["enabled"]:
        return False
    if _state().get("last_run") == time.strftime("%Y-%m-%d"):
        return False
    return (now or time.localtime()).tm_hour >= where["hour"]


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
    _write_state({"last_run": time.strftime("%Y-%m-%d"),
                  "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "report": ""})

    turns = [{"role": "system", "content": BRIEF},
             {"role": "user", "content": "the window is open. look, then decide."}]
    # origin="self-review" is what the supervisor's budget counts. It is set here
    # and nowhere the model can reach.
    tools.set_context(owner, "self-review", "", origin="self-review")
    try:
        # Master's budget, not a stranger's: this turn is his window, and spend.py
        # never prices his turns, so there is no reason to make her think short.
        answer = bot.run_turns(turns, REVIEW_SCHEMA, set(REVIEW_TOOL_NAMES),
                               max_tokens=bot.token_budget(True))
    except Exception as exc:
        LOG.warning("the review turn failed: %s", exc)
        _write_state({"last_run": time.strftime("%Y-%m-%d"),
                      "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "report": f"turned over: {type(exc).__name__}"})
        return True

    answer = (answer or "").strip()
    LOG.info("self-review finished: %s", answer[:300] or "(empty)")
    _write_state({"last_run": time.strftime("%Y-%m-%d"),
                  "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "report": answer[:4000]})
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
