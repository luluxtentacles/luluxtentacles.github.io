"""The daily read of Nyan's people ledger, and what it means for my dossier.

Nyan writes the wide people ledger at C:\\Python\\DiscordBotN5\\memory\\facts.json
and rewrites it as she learns. My dossier is built from her DROP, a snapshot she
leaves inside my wall at memory/nyan/.

Master, 2026-09-22: once a day, after Nyan drops facts.json - compare today to
yesterday's for changes, keep yesterday's as old_facts.json so the comparison is
a plain diff, then sweep the last 48 hours of the mirror for anything the ledger
missed. She reads it and puts what is worth keeping in her people dossier.

TWO SOURCES, and the second is a health check rather than a second feed:

  * the LIVE ledger is what actually changes day to day, so the diff runs
    against it;
  * the DROP in my wall is the handoff my dossier is built from, and on
    2026-09-22 it was three days stale while the live ledger had been rewritten
    that afternoon.

A diff of a stopped file reports "no changes" forever, and that reads exactly like
a quiet week. So staleness is REPORTED here instead of waited out - that is the
whole reason both are watched, and it is the lesson the digest feature taught the
hard way.

The turn is hers rather than mechanical: she decides what is worth keeping. It
costs one turn a day, and it only spends one when there is actually something to
read.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import journal
import gemini_queue
gemini_enqueue = gemini_queue.enqueue
import paths
import people
import tools

LOG = logging.getLogger("lulu")

POLL_SECONDS = 300
DEFAULT_INTERVAL_HOURS = 24.0
STATE_REL = "memory/nyan_watch.json"
OLD_REL = "memory/nyan_old_facts.json"

# READ ONLY, and outside my wall. It is another bot's live file; the only thing
# this module ever does with it is look.
LEDGER = Path(r"C:\Python\DiscordBotN5\memory\facts.json")

# How old the drop in my wall may get before the handoff counts as stopped. A day
# and a half, so a single missed drop is not a false alarm and two is.
DROP_STALE_HOURS = 36.0

# Ceilings on what one pass is allowed to carry. The ledger has 176 people in it,
# and an uncapped diff of a busy day would be a wall of text that she reads at her
# own expense and then has to triage anyway.
MAX_ADDED_PEOPLE = 30
MAX_CHANGED_PEOPLE = 40
MAX_FACTS_PER_PERSON = 6
MAX_SWEEP_LINES = 120
DIFF_MAX_CHARS = 9000
REPORT_MAX = 1800

# -- the WEEKLY dossier pass, master 2026-09-25 ------------------------------
# Once a week: anyone whose facts moved ENOUGH since the last weekly pass
# gets a dossier rewrite, through the ONE gemini queue. "Enough" is a number,
# not a feeling: WEEKLY_MIN_CHANGES fresh facts, or a person who is new and
# has no page at all. The queue paces it - one rewrite per poll, five minutes
# a try - so a busy week never turns into a wall of free-ladder calls.
WEEKLY_INTERVAL_HOURS = 168.0
WEEK_BASELINE_REL = "memory/nyan_week_facts.json"
WEEKLY_MIN_CHANGES = 3
WEEKLY_MAX_ENQUEUE = 10
DOSSIER_JOB_KIND = "dossier"


# ------------------------------------------------------------------ the clock
def settings(config) -> dict:
    """`enabled` and `interval_hours`, from config.json's `facts` block.

    Disabled when the block is missing, exactly like the digest: this spends a
    model call every day, so it is opt-in, and an absent block has to read as off
    rather than as "on by default".
    """
    raw = (config or {}).get("facts") or {}
    if not isinstance(raw, dict):
        raw = {}
    try:
        hours = float(raw.get("interval_hours", DEFAULT_INTERVAL_HOURS))
    except (TypeError, ValueError):
        hours = DEFAULT_INTERVAL_HOURS
    if hours <= 0:
        hours = DEFAULT_INTERVAL_HOURS
    return {"enabled": bool(raw.get("enabled")), "interval_hours": hours}


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def _state() -> dict:
    try:
        data = paths.read_json(STATE_REL, default=None)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(**fields) -> None:
    data = _state()
    data.update(fields)
    try:
        paths.write_json(STATE_REL, data, internal=True)
    except Exception as exc:
        LOG.warning("could not stamp the facts state: %s", exc)


def due(config, now=None) -> bool:
    """Is a pass owed? Its interval has passed, or it has never run."""
    where = settings(config)
    if not where["enabled"]:
        return False
    moment = time.time() if now is None else now
    last = _state().get("last_run")
    if isinstance(last, bool) or not isinstance(last, (int, float)):
        return True
    return moment - last >= where["interval_hours"] * 3600


# ------------------------------------------------------------------ the sources
def load_ledger() -> tuple[dict, float, int]:
    """Nyan's live ledger, its mtime, and its size. Never fatal, never raises.

    The mtime and size ride along because they are how "has this actually moved"
    is answered without diffing 370 KB to find out. An unreadable ledger comes
    back empty, which the caller treats as "nothing to do", never as "everybody
    stopped existing".
    """
    try:
        # Two tries with a breath between: a locked or half-written file is a
        # moment, not a day, and one miss must not cost the whole pass.
        stat = data = exc = None
        for attempt in range(2):
            try:
                stat = LEDGER.stat()
                data = json.loads(LEDGER.read_text(encoding="utf-8"))
                break
            except Exception as caught:
                exc = caught
                time.sleep(2.0)
        if stat is None or data is None:
            raise exc or OSError("ledger never appeared")
    except Exception as exc:
        LOG.warning("could not read Nyan's ledger: %s", exc)
        return {}, 0.0, 0
    if not isinstance(data, dict):
        return {}, 0.0, 0
    inner = data.get("people")
    return (inner if isinstance(inner, dict) else data), stat.st_mtime, stat.st_size


def drop_stamp() -> tuple[float, str]:
    """How long ago Nyan last left a drop in my wall, and which file it was.

    The NEWEST file in the drop folder, dated files included: `latest.json` and a
    dated copy are the same delivery, and either one landing means the pipe moved.
    (-1, "") means there is no drop at all.
    """
    newest, name = 0.0, ""
    try:
        base = paths.resolve(people.DROP_DIR)
        for path in base.glob("*.json"):
            mtime = path.stat().st_mtime
            if mtime > newest:
                newest, name = mtime, path.name
    except OSError:
        return -1.0, ""
    if not newest:
        return -1.0, ""
    return (time.time() - newest) / 3600.0, name


def _facts(entry) -> list[str]:
    """One person's facts as plain text, whitespace collapsed for comparing."""
    out = []
    for item in (entry or {}).get("facts") or []:
        text = item.get("text") if isinstance(item, dict) else item
        text = " ".join(str(text or "").split())
        if text:
            out.append(text)
    return out


def _name_of(key, entry) -> str:
    name = str((entry or {}).get("custom_name") or "").strip()
    return name or str(key)


def diff(old: dict, new: dict) -> dict:
    """What moved between two ledgers: who is new, who is gone, whose facts changed.

    Compared on the SET of fact texts rather than on the whole entry, because the
    ledger rewrites `last_seen` and `s` constantly - a diff that counted those
    would call every person changed every single day and mean nothing.
    """
    added, gone, changed = [], [], []
    for key, entry in (new or {}).items():
        if key not in (old or {}):
            added.append((key, _name_of(key, entry)))
            continue
        before = set(_facts(old.get(key)))
        after = set(_facts(entry))
        fresh = [t for t in after if t not in before]
        dropped = [t for t in before if t not in after]
        if fresh or dropped:
            changed.append((key, _name_of(key, entry), fresh, dropped))
    for key, entry in (old or {}).items():
        if key not in (new or {}):
            gone.append((key, _name_of(key, entry)))
    return {"added": added, "gone": gone, "changed": changed}


def render_diff(changes: dict) -> str:
    """The changed part of the ledger, said in as few words as it can be."""
    parts = []
    added = changes.get("added") or []
    gone = changes.get("gone") or []
    changed = changes.get("changed") or []
    if added:
        parts.append(f"{len(added)} person(s) I did not have before: "
                     + ", ".join(name for _, name in added[:MAX_ADDED_PEOPLE]))
    if gone:
        parts.append(f"{len(gone)} no longer in the ledger: "
                     + ", ".join(name for _, name in gone[:MAX_ADDED_PEOPLE]))
    for _, name, fresh, dropped in changed[:MAX_CHANGED_PEOPLE]:
        bits = []
        if fresh:
            bits.append("new: " + " | ".join(fresh[:MAX_FACTS_PER_PERSON]))
        if dropped:
            bits.append("dropped: " + " | ".join(dropped[:MAX_FACTS_PER_PERSON]))
        parts.append(f"{name}: " + "; ".join(bits))
    if len(changed) > MAX_CHANGED_PEOPLE:
        parts.append(f"(and {len(changed) - MAX_CHANGED_PEOPLE} more people changed)")
    text = "\n".join(f"- {part}" for part in parts)
    return (text or "nothing changed since yesterday")[:DIFF_MAX_CHARS]


def _write_old() -> bool:
    """Keep today's ledger as the baseline tomorrow's diff runs against.

    The RAW bytes, not a re-serialised copy: old_facts.json is meant to BE
    yesterday's facts.json, so a diff of the two is a diff of the real files and
    not of two round-trips through my own parser.
    """
    try:
        text = LEDGER.read_text(encoding="utf-8")
        paths.write_text(OLD_REL, text, internal=True)
        return True
    except Exception as exc:
        LOG.warning("facts pass: could not keep a baseline: %s", exc)
        return False


def _load_old() -> dict:
    try:
        data = paths.read_json(OLD_REL, default=None)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    inner = data.get("people")
    return inner if isinstance(inner, dict) else data


# ------------------------------------------------------------------ the mirror
def sweep(state) -> tuple[str, dict]:
    """Everything said in the mirror since the bookmark, and the next bookmark.

    The bookmark is a day plus HOW MANY of that day's lines were already read -
    a count rather than a timestamp, because a mirror stamp is only minute
    granular and two lines inside the same minute could not be told apart. A
    count never repeats a line and never skips one, which is the whole job.
    """
    book = state.get("bookmark") or {}
    mark_day = str(book.get("day") or "")
    seen = book.get("seen")
    seen = seen if isinstance(seen, int) and not isinstance(seen, bool) else 0

    lines = []
    for offset in range(journal.MIRROR_KEEP_DAYS - 1, -1, -1):   # oldest day first
        day = journal.shift(journal.today(), -offset)
        if mark_day and day < mark_day:
            continue
        entries = journal.mirror_entries_all(day)
        start = seen if day == mark_day else 0
        for server, at, where, rest in entries[max(0, start):]:
            lines.append(f"- [{day} {at}] [{server}] {where} {rest}")
    if len(lines) > MAX_SWEEP_LINES:
        lines = lines[-MAX_SWEEP_LINES:]

    next_book = {"day": journal.today(),
                 "seen": len(journal.mirror_entries_all(journal.today()))}
    return "\n".join(lines), next_book


# ------------------------------------------------------------------ her turn
def _brief(changes: dict, sweep_text: str, notes: list) -> str:
    """The whole instruction for one pass, as one turn."""
    bits = [
        "the daily read of Nyan's ledger. this happens once a day, and it is not a "
        "conversation - nobody is waiting in a room for an answer, and none of it "
        "needs saying out loud."
    ]
    if notes:
        bits.append("things to know:\n" + "\n".join(f"- {note}" for note in notes))
    bits.append("what changed in the ledger since yesterday:\n" + render_diff(changes))
    bits.append("what was said in my rooms since I last looked (the last 48 hours "
                "of the mirror, which covers what the ledger did not):\n"
                + (sweep_text or "- nothing new"))
    bits.append(
        "what to do:\n"
        "- read it. most of it is noise, and it is fine to say so.\n"
        "- for every person worth KEEPING, look them up with who_is FIRST, then "
        "write_dossier - my dossier on a person is a page of PROSE, not a "
        "bullet list and not too short. Rewrite the whole page: everything I "
        "already knew that still holds, merged with what changed, in my own "
        "words. name them as I know them. Open the page with ONE SHORT "
        "PARAGRAPH bio - who they are, a few sentences - then a blank line, "
        "then the page: the bio is what my room cards carry and is kept "
        "outside the page's length. Only for people already CHANGED in this "
        "diff - never rewrite pages for everyone, that wastes the token "
        "budget. If a person only needs their who-they-are line refreshed, "
        "write_bio is the cheap call.\n"
        "- one-line observations that do not deserve a dossier pass can still "
        "go in with learn_person - one fact per call, only about someone I "
        "have a page on.\n"
        "- not everything is worth keeping. a fact I would not want read back to the "
        "person it is about is not worth keeping, and neither is a guess.\n"
        "- do NOT post any of this into a room. nobody asked, and there is nobody to "
        "answer.\n"
        "- finish with one short paragraph: what I kept, what I left, and why."
    )
    return "\n\n".join(bits)


def _owner_id(bot) -> int | None:
    owners = list((getattr(bot, "config", None) or {}).get("owner_ids") or [])
    try:
        return int(owners[0]) if owners else None
    except (TypeError, ValueError):
        return None


async def run_turn(bot, brief: str) -> str:
    """One turn, hers, with her whole toolset. Returns what she made of it.

    tools.in_thread, not asyncio.to_thread: the tool context is per THREAD, and a
    turn is up to MAX_TOOL_ROUNDS brain calls, each blocking on HTTP - running
    those straight off the event loop would stall Discord's heartbeat with it.
    """
    turns = [{"role": "system", "content": bot.system_prompt()}]
    mood = journal.mood_block()
    if mood:
        turns.append({"role": "system", "content": f"[{mood}]"})
    turns.append({"role": "user", "content": brief})
    # origin stays "master": this is master's pipeline, not her own time, so it
    # must not spend the supervisor's daily self-edit budget.
    tools.set_context(_owner_id(bot), "facts-pass", "", master=True)
    return await tools.in_thread(bot.run_turns, turns, tools.SCHEMA,
                                 set(tools.DISPATCH),
                                 max_tokens=bot.token_budget(True))


async def report(bot, text: str) -> None:
    """Send the pass's own summary to master's DMs. Never fatal.

    A DM and only a DM. This is housekeeping in the walls, not something a room
    full of people needs narrated at them every day.
    """
    owner = _owner_id(bot)
    body = (text or "").strip()
    if owner is None:
        LOG.warning("facts pass: no owner id, so the report has nowhere to go")
        return
    if not body:
        body = "the daily facts pass ran and had nothing to say."
    try:
        target = await bot.fetch_user(owner)
        await target.send(body[:REPORT_MAX])
        LOG.info("facts pass: report DMed to master")
    except Exception as exc:
        LOG.warning("facts pass: could not deliver the report: %s", exc)


async def maybe_run(bot) -> bool:
    """One pass, if one is owed. True when it actually spent a turn."""
    config = getattr(bot, "config", None) or {}
    if not due(config):
        return False

    state = _state()
    ledger, mtime, size = load_ledger()
    if not ledger:
        # Do NOT stamp last_run: an unreadable ledger is a moment, not a day,
        # so the next poll (5 minutes away) retries instead of waiting the
        # whole interval out on one failed read. But only the FIRST failure
        # of a streak DMs master - a nightly outage must not ping him every
        # 5 minutes.
        fails = _state().get("read_fails")
        fails = fails + 1 if isinstance(fails, int) and not isinstance(fails, bool) else 1
        _save(last_checked=_stamp(), note="the ledger could not be read",
              read_fails=fails)
        if fails == 1:
            await report(bot, "the daily facts pass could not read Nyan's ledger, so "
                              "there was nothing to compare. I will try again in a "
                              "few minutes.")
        return False

    _save(last_checked=_stamp(), read_fails=0)
    notes = []
    age, drop_file = drop_stamp()
    if age < 0:
        notes.append("there is no drop from Nyan inside my wall at all")
    elif age > DROP_STALE_HOURS:
        notes.append(f"Nyan's drop into my wall is {age:.0f} hours old "
                     f"(newest is {drop_file}) - the handoff may have stopped, so "
                     f"the ledger diff is the only moving part")

    sweep_text, bookmark = sweep(state)
    old = _load_old()

    if not old:
        # First run: there is nothing to diff against, so seeding the baseline IS
        # the pass. Not a turn - there is no news in "176 people exist".
        _write_old()
        _save(last_run=time.time(), last_checked=_stamp(), ledger_mtime=mtime,
              ledger_size=size, bookmark=bookmark)
        await report(bot, "first facts pass: baseline kept as nyan_old_facts.json. "
                          "From tomorrow the ledger diff has something to compare "
                          "against.")
        return False

    changes = diff(old, ledger)
    busy = bool(changes["added"] or changes["gone"] or changes["changed"] or sweep_text)
    if not busy:
        # A quiet day costs nothing. Stamped so the interval still starts here.
        _save(last_run=time.time(), last_checked=_stamp(), ledger_mtime=mtime,
              ledger_size=size, bookmark=bookmark)
        LOG.info("facts pass: nothing changed, no turn spent")
        return False

    try:
        answer = await run_turn(bot, _brief(changes, sweep_text, notes))
    except Exception as exc:
        LOG.warning("facts pass: her turn turned over: %s", exc)
        _save(last_checked=_stamp(), note=f"turned over: {type(exc).__name__}")
        return False

    answer = (answer or "").strip()
    # Rotate AFTER the turn, and after the answer is in hand: old_facts.json is
    # tomorrow's baseline, so it must only move once today's comparison is done.
    _write_old()
    _save(last_run=time.time(), last_checked=_stamp(), ledger_mtime=mtime,
          ledger_size=size, bookmark=bookmark, report=answer[:2000])
    await report(bot, "daily facts pass:\n\n" + answer)
    return True


def _load_week() -> dict:
    try:
        data = paths.read_json(WEEK_BASELINE_REL, default=None)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_week() -> None:
    try:
        paths.write_text(WEEK_BASELINE_REL, LEDGER.read_text(encoding="utf-8"),
                         internal=True)
    except Exception as exc:
        LOG.warning("weekly dossier pass: could not keep a baseline: %s", exc)


def _dossier_hash(who: str) -> str:
    import hashlib
    text = str(people.lookup(who).get("dossier") or "")
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


async def maybe_weekly_dossiers(bot) -> bool:
    """Once a week, queue dossier rewrites for people whose info moved a lot."""
    st = _state()
    last = float(st.get("last_weekly_dossiers") or 0)
    if time.time() - last < WEEKLY_INTERVAL_HOURS * 3600:
        return False
    try:
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        return False
    old = _load_week()
    if not old:
        _write_week()
        _save(last_weekly_dossiers=time.time())
        return False
    changes = diff(old, ledger)
    snaps = st.get("dossier_snapshots") or {}
    queued = 0
    for key, name, fresh, dropped in changes["changed"]:
        if queued >= WEEKLY_MAX_ENQUEUE:
            break
        if len(fresh) < WEEKLY_MIN_CHANGES:
            continue
        if str(people.lookup(key).get("dossier") or "").strip() == "":
            continue          # nothing written yet - the daily pass owns that
        snaps[key] = _dossier_hash(key)
        gemini_enqueue(DOSSIER_JOB_KIND, key)
        queued += 1
    for key, name in changes["added"]:
        if queued >= WEEKLY_MAX_ENQUEUE:
            break
        snaps[key] = _dossier_hash(key)
        gemini_enqueue(DOSSIER_JOB_KIND, key)
        queued += 1
    if queued:
        _save(last_weekly_dossiers=time.time(), dossier_snapshots=snaps)
        LOG.info("weekly dossier pass: %d rewrite(s) queued", queued)
    else:
        _save(last_weekly_dossiers=time.time())
    _write_week()
    return bool(queued)


async def drain_queue(bot) -> bool:
    """One job per poll off the ONE gemini queue, master 2026-09-25.

    The free ladder is unreliable, so nothing here waits on anything: a job
    is taken, tried once, and on any failure put back with a five-minute
    retry stamp (gemini_queue.failed). She does not get the answer asap -
    she gets it when the queue gets through. Success means the job LEFT the
    queue; a turn that answered but wrote nothing is a failure, not a pass.
    """
    job = gemini_queue.due()
    if not job:
        return False
    who = str(job.get("who") or "")
    kind = str(job.get("kind") or "")
    if kind not in ("bio", DOSSIER_JOB_KIND):
        LOG.warning("gemini queue: unknown job kind %r - dropped", kind)
        gemini_queue.done(who)
        return True
    name = people.display_name(who, who)
    if kind == DOSSIER_JOB_KIND:
        # The weekly pass queued this one: their facts moved a lot, so the
        # page is behind the ledger. Near the 100-fact cap, MERGE similar
        # facts into one line and let the oldest weakest go - master,
        # 2026-09-25 - rather than just refusing to write.
        brief = (
            f"weekly dossier pass: {name} (id {who})'s facts moved enough "
            "since last week that their page is behind. who_is them first, "
            "then write_dossier: the whole page I already have, merged with "
            "what is new, rewritten as one page of prose, OPENED with one "
            "short paragraph bio (who they are, a few sentences) then a "
            "blank line, then the rest. If the fact list is near its cap, "
            "merge similar facts into one and drop the oldest weakest "
            "rather than losing anything still true. Change nothing else, "
            "post nothing anywhere.")
        try:
            answer = (await run_turn(bot, brief) or "").strip()
        except Exception as exc:
            LOG.warning("gemini queue: %s (%s) turned over: %s", kind, who, exc)
            gemini_queue.failed(who)
            return True
        st = _state()
        snaps = st.get("dossier_snapshots") or {}
        before = snaps.get(who)
        if answer and before is not None and _dossier_hash(who) != before:
            gemini_queue.done(who)
            snaps.pop(who, None)
            _save(dossier_snapshots=snaps)
            LOG.info("gemini queue: %s %s rewritten", kind, who)
        else:
            gemini_queue.failed(who)
        return True
    brief = (
        f"background queue: bring {name} (id {who})'s dossier into the "
        "current format. who_is them first, then write_dossier: the whole "
        "page I already have, merged and rewritten as one page of prose, "
        "OPENED with one short paragraph bio (who they are, a few "
        "sentences) then a blank line, then the rest. Change nothing else, "
        "post nothing anywhere.")
    try:
        answer = (await run_turn(bot, brief) or "").strip()
    except Exception as exc:
        LOG.warning("gemini queue: %s (%s) turned over: %s", kind, who, exc)
        gemini_queue.failed(who)
        return True
    if answer and people.dossier_has_bio(who):
        gemini_queue.done(who)
        LOG.info("gemini queue: %s %s migrated (tries %s)", kind, who,
                 job.get("tries"))
    else:
        gemini_queue.failed(who)
    return True


async def watch(bot) -> None:
    """Poll forever. Free and idle until a pass is actually owed."""
    while True:
        try:
            await maybe_run(bot)
        except Exception as exc:
            LOG.warning("facts pass failed: %s", exc)
        try:
            await maybe_weekly_dossiers(bot)
        except Exception as exc:
            LOG.warning("weekly dossier pass failed: %s", exc)
        try:
            await drain_queue(bot)
        except Exception as exc:
            LOG.warning("gemini queue drain failed: %s", exc)
        await asyncio.sleep(POLL_SECONDS)
