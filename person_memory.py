"""Per-person conversation memory: what was said, saved when Lulu talks.

Master, 2026-09-24, in order of asking:

  - "she should remember conversations with people" - and not just with him.
  - one global copy, "and we search by user and word" - so this store is a
    folder of per-person files plus ONE shared weekly archive, not a shard
    per person per week.
  - "whenever lulu talks save the 10 above and below her" - a chain is the
    room around one of her turns: up to 10 lines before her first line, her
    lines, and the lines that arrive after, closed at 10.
  - overlapping windows must not duplicate - so a chain is saved ONCE and
    grown in place while the same conversation keeps going.
  - "store memory with userid and their name together ... like lulu:userid so
    later if lulu changes name we can still match user id" - every line keeps
    speaker name AND uid; matching is by uid, rendering by name. Her own
    lines are recognised by the SELF_LABEL fallback too, because her sends
    enter the mirror without a uid.
  - "search the per person memory before going into journal search".
  - after a week, a FREE-model summary of each person's interactions lands in
    that person's ledger as facts (people.learn, source "memory-summary") -
    the pair facts, Nyan's interactions.json idea in Lulu's body: how Lulu
    and they get along, never third-party material. The Gemini ladder itself
    is brain.free_complete_ex - Nyan's memory_system._gemini_json already
    lives there in Lulu's shape.

Files:
  memory/people/<uid>.json     one person's chains + summary state
  memory/people/archive/<week>.jsonl   every chain, one copy, appended

Plain JSON under memory/, which is sealed against her own write_file, like
the rest of her rememberings.
"""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
import time
from pathlib import Path

import journal
import paths
import people
from bot_text import SELF_LABEL

LOG = logging.getLogger("lulu")

REL_DIR = "memory/people"
REL_ARCHIVE = "memory/people/archive"

CONTEXT_LINES = 10          # room lines kept on each side of her turn
MAX_LINES_PER_CHAIN = 500   # a runaway room cannot grow one chain forever
MAX_CHAINS = 200            # per person; the archive keeps what falls off
LINE_CHARS = 500
RECALL_LIMIT = 6
RECALL_CHARS = 2400
SIMILAR_RATIO = 0.80        # Nyan's dedupe threshold for pair facts


def _dir() -> Path:
    return paths.resolve(REL_DIR)


def _file(uid: str) -> Path:
    safe = "".join(c for c in str(uid or "unknown") if c.isdigit()) or "unknown"
    return _dir() / f"{safe}.json"


def _load(uid: str) -> dict:
    try:
        return json.loads(_file(uid).read_text(encoding="utf-8"))
    except Exception:
        return {"chains": [], "summarized_weeks": []}


def _save(uid: str, data: dict) -> None:
    path = _file(uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp-{time.time_ns()}")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    tmp.replace(path)


def _tokens(text: str) -> set[str]:
    """Topic words, the same crudeness as the shared store - matching only."""
    out: set[str] = set()
    for word in re.findall(r"[a-z0-9']+", (text or "").lower()):
        if len(word) > 2:
            out.add(word)
    return out - {
        "the", "and", "you", "your", "was", "that", "this", "with",
        "have", "for", "not", "are", "but", "she", "him", "her",
        "his", "hers", "yes", "about", "what", "when", "want",
        "more", "did", "just", "like",
    }


def _similar(a: str, b: str) -> bool:
    """Nyan's string-similarity dedupe: near-identical facts collapse."""
    return difflib.SequenceMatcher(
        None, (a or "").lower().strip(), (b or "").lower().strip()
    ).ratio() >= SIMILAR_RATIO


# -- capture ----------------------------------------------------------------

def _is_her(entry: dict, her_uid: str) -> bool:
    """One of Lulu's lines in the ring, either shape of the record.

    Her sends are noted without a uid (SELF_LABEL only), so the author label
    is the fallback - master, 2026-09-24: match the id, not the name, but
    the name is the only marker her own lines carry in the mirror.
    """
    uid = str((entry or {}).get("uid") or "")
    if uid:
        return uid == her_uid
    return str((entry or {}).get("author") or "") == SELF_LABEL


def _ring_lines(ring, her_uid: str) -> tuple[list[dict], list[dict]]:
    """Split a mirror ring into (her trailing turn, everything else).

    Her turn is the trailing run of her lines - the turn that just finished.
    Everything before it is context in front; there is nothing behind it yet
    (the lines that arrive later grow the chain).
    """
    lines = list(ring or [])[-MAX_LINES_PER_CHAIN:]
    cut = len(lines)
    while cut > 0 and _is_her(lines[cut - 1], her_uid):
        cut -= 1
    return lines[cut:], lines[:cut]


def _line_of(entry: dict, her_uid: str) -> dict:
    uid = str((entry or {}).get("uid") or "")
    if not uid and _is_her(entry, her_uid):
        uid = her_uid
    return {"speaker": str((entry or {}).get("author") or "someone"),
            "uid": uid,
            "text": str((entry or {}).get("text") or "")[:LINE_CHARS],
            # Reply threading, kept so a pair summary can tell who a line
            # was addressed to - without it, a line Lulu aimed at one person
            # would be summarised into another pair's facts.
            "id": str((entry or {}).get("id") or ""),
            "reply_to": str((entry or {}).get("reply_to") or "")}


def note_lulu_turn(channel_id, ring, *, her_uid: str, trigger_uid: str,
                   room: str = "", server: str = "", dm: bool = False) -> str:
    """Save the room around her just-finished turn, as one chain.

    Returns the chain id. A candidate that only repeats the last saved
    chain's lines is dropped; a candidate that extends it (she added lines
    to the same conversation) replaces it, so overlapping windows never
    duplicate - master, 2026-09-24.
    """
    her_uid = str(her_uid or "")
    try:
        her, before = _ring_lines(ring, her_uid)
        if not her:
            return ""
        lines = ([_line_of(e, her_uid) for e in before[-CONTEXT_LINES:]]
                 + [_line_of(e, her_uid) for e in her])
        about = sorted({str(u) for u in
                        (trigger_uid, *[l["uid"] for l in lines])
                        if u and u != her_uid})
        chain = {
            "id": time.strftime("%Y%m%d-%H%M%S"),
            "week": journal.week_of(),
            "cid": str(channel_id),
            "server": (server or "")[:80],
            "room": (room or "")[:80],
            "dm": bool(dm),
            "lines": lines,
            "about": about,
            # Whose conversation this was, and who Lulu is in it - the weekly
            # pair-fact summary needs both, so it can keep ONLY the dialogue
            # between her and that one person (master, 2026-09-24: "this
            # should only be facts between lulu and that user"). A bystander
            # in the window gets a copy through `about` but is not the
            # conversation.
            "her": her_uid,
            "trigger": str(trigger_uid),
            "after": 0,
        }
        chain["her_lines"] = [l["text"][:120] for l in lines
                              if l["uid"] == her_uid][-4:]
        # Her own file is the anchor copy: it is the one note_line reads to
        # grow the open chain, and the one searched first on recall. The
        # participants get their own copy through `about`.
        saved_id = chain["id"]
        for uid in sorted(set(about + [her_uid])):
            data = _load(uid)
            chains = data.get("chains", [])
            # Dedup is per CHANNEL, not per wording: an open chain in this
            # room IS the ongoing conversation, so the new window replaces
            # it (grown, never a second copy) - master, 2026-09-24. Her own
            # lines are the conversation's signature: a window whose her-
            # lines match the last chain's is the same conversation re-saved
            # with a wider room around it, even if that chain already
            # closed - still one copy, updated in place.
            target = next((c for c in chains
                           if c.get("cid") == str(channel_id)
                           and (not c.get("closed")
                                or c.get("her_lines") == chain["her_lines"])),
                          None)
            if target is not None and target.get("lines") == chain["lines"]:
                # Exactly the same window again: nothing to write, but the
                # open-chain pointer must follow the STORED chain's id, or
                # note_line will look for a chain that was never saved.
                if uid == her_uid:
                    saved_id = str(target.get("id") or saved_id)
                continue
            if target is not None:
                target.update(chain)          # same conversation, grown
            else:
                chains.append(chain)
                if len(chains) > MAX_CHAINS:
                    _archive(uid, chains[0])
                    chains[:] = chains[-MAX_CHAINS:]
            data["chains"] = chains
            _save(uid, data)
        return saved_id
    except Exception as exc:
        LOG.warning("person memory: could not save a chain: %s", exc)
        return ""


def note_line(channel_id, ring, her_uid: str) -> None:
    """A line arrived after her turn: grow the open chain in this channel.

    This is where the "10 below" comes from - the lines that arrive after
    she stops talking extend the chain until ten of them have, then it
    closes. The open chain is resolved from the FILES (by channel), not from
    an in-memory pointer, so a restart mid-conversation loses nothing; and
    every copy of the chain is grown in step, so the copies do not drift.
    """
    her_uid = str(her_uid or "")
    try:
        cid = str(channel_id)
        anchor = _load(her_uid)
        chain = next((c for c in anchor.get("chains", [])
                      if c.get("cid") == cid and not c.get("closed")), None)
        if not chain:
            return
        lines = [_line_of(e, her_uid)
                 for e in list(ring or [])[-MAX_LINES_PER_CHAIN:]]
        # The lines that count are the ones AFTER her last line, wherever it
        # sits in the ring - at a real call-site the tail is other people's
        # follow-ups, so a tail-walk finds nothing.
        her_last = max((i for i, l in enumerate(lines)
                        if l["uid"] == her_uid), default=-1)
        if her_last < 0:
            return
        after_pool = lines[her_last + 1:]
        already = int(chain.get("after") or 0)
        fresh = [l for l in after_pool[already:] if l["uid"] != her_uid]
        if not fresh:
            return
        # The after-window is capped at ten STORED lines total; everything
        # past that is consumed but not kept - the window is ten, not a
        # transcript of the rest of the day.
        room_left = max(0, CONTEXT_LINES - already)
        new_after = already + len(fresh)
        closed = new_after >= CONTEXT_LINES
        # Grow the same conversation in EVERY copy it lives in - hers and
        # each participant's - found by channel, so one conversation stays
        # one conversation everywhere.
        for uid in sorted({her_uid, *[str(a) for a in chain.get("about", [])]}):
            data = anchor if uid == her_uid else _load(uid)
            target = next((c for c in data.get("chains", [])
                           if c.get("cid") == cid and not c.get("closed")),
                          None)
            if target is None:
                continue
            target["lines"] = (target.get("lines") or []) + fresh[:room_left]
            target["after"] = new_after
            target["closed"] = closed
            _save(uid, data)
    except Exception as exc:
        LOG.warning("person memory: could not grow a chain: %s", exc)


def _archive(uid: str, chain: dict) -> None:
    """One copy of every chain that falls off a person's file, by week."""
    try:
        week = str(chain.get("week") or journal.week_of())
        path = paths.resolve(f"{REL_ARCHIVE}/{week}.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"uid": uid, **chain}, ensure_ascii=False)
                     + "\n")
    except Exception as exc:
        LOG.warning("person memory: could not archive a chain: %s", exc)


# -- recall -----------------------------------------------------------------

def _chain_text(chain: dict) -> str:
    return "\n".join(f"{l.get('speaker')}: {l.get('text')}"
                     for l in chain.get("lines") or [])


def search(query: str, uid: str = "", *, limit: int = RECALL_LIMIT,
           dm: bool = False, channel: str = "") -> list[dict]:
    """Chains matching `query`: this person's file first, then everyone's.

    Matching is by uid where a file exists (never by name - the name
    changes, the id does not - master, 2026-09-24); the words score the
    chain's lines. A chain about several people is findable from any of
    them, once, from the one global copy. DM chains surface only inside
    their own thread, same rule as the shared store.
    """
    wanted = _tokens(query)
    if not wanted:
        return []
    pools: list[tuple[str, list[dict]]] = []
    uid = str(uid or "")
    if uid:
        pools.append((uid, _load(uid).get("chains", [])))
    global_chains: list[dict] = []
    try:
        for path in sorted(_dir().glob("*.json")):
            other = path.stem
            if other == uid:
                continue
            try:
                chains = json.loads(path.read_text(encoding="utf-8")) \
                    .get("chains", [])
            except Exception:
                continue
            for chain in chains:
                if uid and uid not in [str(a) for a in chain.get("about", [])]:
                    continue
                global_chains.append(chain)
    except Exception:
        pass
    pools.append(("", global_chains))

    scored: list[tuple[float, str, dict]] = []
    for file_uid, chains in pools:
        for chain in chains:
            if chain.get("dm") and not (dm and str(channel) == chain.get("cid")):
                continue
            hit = wanted & _tokens(_chain_text(chain))
            if not hit:
                continue
            bonus = 2.0 if (file_uid and uid == file_uid) else 0.0
            scored.append((len(hit) + bonus, str(chain.get("id") or ""),
                           chain))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [c for _, _, c in scored[:limit]]


def recall_block(query: str, uid: str = "", *, dm: bool = False,
                 channel: str = "") -> str:
    """Chains as a prompt block, or '' when nothing matches."""
    chains = search(query, uid, dm=dm, channel=channel)
    if not chains:
        return ""
    lines = ["[remembered conversations]",
             "Things said in earlier conversations, with the room around "
             "them. Not new input - context. Do not thank anyone for it."]
    for chain in chains:
        where = "DM" if chain.get("dm") else f"#{chain.get('room', '?')}"
        when = str(chain.get("id") or "")
        stamp = (f"{when[:4]}-{when[4:6]}-{when[6:8]} "
                 f"{when[9:11]}:{when[11:13]}") if len(when) >= 13 else when
        lines.append(f"- [{stamp} {where}]")
        for l in chain.get("lines", [])[-12:]:
            lines.append(f"  {l.get('speaker')}: {l.get('text')}")
    return "\n".join(lines)[:RECALL_CHARS]


# -- the weekly summary ------------------------------------------------------

SUMMARY_PROMPT = (
    "Below are saved conversation excerpts between Lulu (a Discord bot) and "
    "one person, from last week. ONLY lines between Lulu and this person "
    "are shown - other people who were in the room have been removed, and "
    "they are not your subject. Write 2-4 short plain facts about how Lulu "
    "and THIS person interact - what they talk about, how they get along, "
    "what Lulu made or did for them. Never mention or describe anyone else, "
    "even if a line hints they exist. Third person, no private channel "
    "names, no quotes of anything that looks like a secret. One fact per "
    "line, nothing else.\n\n---\n")


def _her_uid_of(chain: dict) -> str:
    """Which uid is Lulu in this chain - stored, or derived from her label."""
    her = str(chain.get("her") or "")
    if her:
        return her
    for l in chain.get("lines", []):
        if str(l.get("speaker") or "") == SELF_LABEL and l.get("uid"):
            return str(l["uid"])
    return ""


def _pair_material(chain: dict, uid: str) -> str:
    """The chain trimmed to ONLY the dialogue between Lulu and `uid`.

    Third-party lines are always dropped. Her OWN lines are kept only when
    they are addressed to this person - by reply threading, or because this
    person is the one who triggered her turn (an @mention turn is for the
    person who typed it) - so a greeting she aimed at someone else in the
    window never becomes that pair's fact. A chain the person never spoke
    in returns '' outright: a bystander in the room window gets no facts
    written about them (master, 2026-09-24: "this should only be facts
    between lulu and that user").
    """
    her = _her_uid_of(chain)
    uid = str(uid)
    if not her or uid == her:
        return ""
    lines = list(chain.get("lines") or [])
    theirs = [l for l in lines if str(l.get("uid") or "") == uid]
    if not theirs:
        return ""
    their_ids = {str(l.get("id") or "") for l in theirs if l.get("id")}
    threaded = any(str(l.get("reply_to") or "") for l in lines)
    trigger = str(chain.get("trigger") or "")

    def keep(l: dict) -> bool:
        who = str(l.get("uid") or "")
        if who == uid:
            return True
        if who != her:
            return False              # a third party's line: never
        reply_to = str(l.get("reply_to") or "")
        if reply_to and reply_to in their_ids:
            return True               # her reply, to this person
        if threaded:
            lid = str(l.get("id") or "")
            if lid and any(str(t.get("reply_to") or "") == lid
                           for t in theirs):
                return True           # this person's reply, to her line
            if reply_to:
                return False          # addressed to someone else
            # Unaddressed: keep when the turn was theirs to begin with.
            return not trigger or trigger == uid
        return True                   # no threading anywhere: hers stay

    kept = [l for l in lines if keep(l)]
    return "\n".join(f"{l.get('speaker')}: {l.get('text')}" for l in kept)


def _existing_facts(uid: str) -> list[str]:
    """What the person's ledger already holds, for the similarity dedupe."""
    try:
        entry = people.learned().get(people.resolve(uid)) or {}
        return [str(f.get("text") or "") for f in entry.get("facts", [])
                if isinstance(f, dict)]
    except Exception:
        return []


def summarize_week(config: dict, uid: str, week: str) -> str:
    """One person's week with Lulu, summarised onto their ledger.

    Free rungs only - never the rung master pays for; a summary nobody is
    waiting for has no business spending money (same rule as the digests).
    Returns the week when it is DONE (summarised, or genuinely nothing to
    summarise); '' when the call did not land, so the next pass retries.
    """
    uid = str(uid or "")
    data = _load(uid)
    chains = [c for c in data.get("chains", []) if c.get("week") == week]
    archived: list[dict] = []
    try:
        path = paths.resolve(f"{REL_ARCHIVE}/{week}.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if str(entry.get("uid")) == uid:
                archived.append(entry)
    except OSError:
        pass
    material = chains or archived
    if len(material) < 3:
        # A quiet week is a DONE week - marked, so it is not retried forever.
        data.setdefault("summarized_weeks", []).append(week)
        _save(uid, data)
        return week
    # Pair facts ONLY: each chain is trimmed to the dialogue between Lulu and
    # this one person before anything reaches the model, and chains they
    # never spoke in are dropped outright - a bystander in the room window
    # gets no facts written about them (master, 2026-09-24: "this should only
    # be facts between lulu and that user").
    parts = [t for t in (_pair_material(c, uid) for c in material[:12]) if t]
    if len(parts) < 3:
        # Fewer than three real exchanges with this person: a done week, not
        # a retry - the material is not going to grow.
        data.setdefault("summarized_weeks", []).append(week)
        _save(uid, data)
        return week
    body = "\n\n".join(parts)[:8000]

    import brain
    who = people.display_name(uid, f"person {uid}")
    text, ok = brain.free_complete_ex(
        config, [{"role": "user",
                  "content": SUMMARY_PROMPT + f"The person: {who}\n\n" + body}],
        max_tokens=300, tries=3)
    if not ok or not str(text or "").strip():
        return ""                      # dry rungs; the week stays unmarked

    known = _existing_facts(uid)
    for line in str(text).strip().splitlines():
        line = line.strip().lstrip("-* ").strip()
        if not line:
            continue
        # Nyan's pair-fact dedupe: a retry that rephrases the same fact must
        # not stack a second copy onto the ledger.
        if any(_similar(line, k) for k in known):
            continue
        people.learn(uid, line[:500], source="memory-summary")
        known.append(line[:500])
    data.setdefault("summarized_weeks", []).append(week)
    _save(uid, data)
    return week


def summarize_due(config: dict) -> list[str]:
    """Summarise every person's finished week that has not been summed yet.

    Runs from the background watcher; each failure is logged and retried on
    the next pass by doing nothing - the week only gets marked when it
    lands. That is the digest rule: a pass that cannot finish HOLDS the
    window instead of advancing past it.
    """
    last = journal.prev_week(journal.week_of())
    if not last:
        return []
    done: list[str] = []
    try:
        files = list(_dir().glob("*.json"))
    except Exception:
        return done
    for path in files:
        uid = path.stem
        if not uid.isdigit():
            continue
        try:
            data = _load(uid)
            if last in (data.get("summarized_weeks") or []):
                continue
            if summarize_week(config, uid, last):
                done.append(uid)
        except Exception as exc:
            LOG.warning("person memory: weekly summary failed for %s: %s",
                        uid, exc)
    return done


async def watch(bot) -> None:
    """Hourly: is there a finished week nobody has summarised yet?"""
    while True:
        try:
            done = summarize_due(bot.config)
            if done:
                LOG.info("person memory: weekly summaries for %s",
                         ", ".join(done))
        except Exception as exc:
            LOG.warning("person memory watcher: %s", exc)
        await asyncio.sleep(3600)
