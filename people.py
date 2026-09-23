"""Who I am talking to.

Three files, merged at read time.

  C:\\Python\\DiscordBotN5\\memory\\facts.json         Nyan's people ledger. READ ONLY,
                                                    refreshed once a day.
  C:\\Python\\DiscordBotN5\\json_data\\user_info.json  the /setinfo cards. READ ONLY.
                                                    This is the bridge.
  memory/people.json                                Mine, inside the wall, writable,
                                                    updated continuously as I talk.

Nyan's file belongs to a live bot. Reading it on every message would be both
wasteful and rude to a process that is writing to it, so it is loaded once and
kept until a day has passed. What I learn myself lands immediately.

That is the whole split: she is the encyclopaedia, I am the notebook.

ONE KEY PER PERSON, and the cards are what make that possible. A carded person
is stored twice in the wider ledger: the facts live under the card ('char:ken')
while their own true key is the discord id written on that card. Reading the id
found nothing, so 48 of the 50 carded people had a permanently empty dossier.
The cards are also the only place that knows one human can hold SEVERAL
accounts - Ken has two, Roon has five - and an alt speaking from an unmapped id
is the same person walking in as a stranger.

So the card is the record for a carded person, every account of theirs resolves
to it, and every name they answer to hangs off it: the card's custom name, its
aliases, its username and display name, plus whatever name Discord actually
handed me as they spoke. Nyan keeps a single name per person, so a rename turns
a regular into a stranger with a good memory. Here it is demoted to an alias.
Mine also counts how often I have seen them and where, which is the difference
between a regular and a first meeting.

What I say out loud about someone: their custom name when there is one, and
their Discord display name only as the fallback for people nobody has carded.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import paths
from shared_memory import redact

NYAN_LEDGER = Path(r"C:\Python\DiscordBotN5\memory\facts.json")
# Nyanbot resolves its own identity and drops the result inside my wall, one
# dated file per day plus a 'latest' pointer. That is what I actually read: her
# file belongs to a live process and would vanish with it, and reaching into
# another bot's folder to re-derive what she already knows is how two resolvers
# end up disagreeing. See nyan_drop() for what a valid drop looks like.
DROP_DIR = "memory/nyan"
DROP_LATEST = "memory/nyan/latest.json"
CARDS = Path(r"C:\Python\DiscordBotN5\json_data\user_info.json")
LOCAL = "memory/people.json"
REFRESH_SECONDS = 24 * 60 * 60

MAX_FACTS = 12
MAX_LOCAL_FACTS = 40

# The dossier: my page of PROSE on a person, written by the daily facts pass.
# Master, 2026-09-23: "it should be like a page of text, not too short". A page
# is roughly 2000-3000 characters; the floor keeps it prose rather than a
# two-line stub, the ceiling keeps one busy day from writing a book.
DOSSIER_MIN_CHARS = 600
DOSSIER_MAX_CHARS = 8000
# How many described profile pictures I keep per person. A page, not a
# scrapbook: somebody who changes their pfp daily should not grow their record
# without end, and the newest is the one anybody is asking about.
MAX_AVATAR_NOTES = 6
AUTO_MAX_CHARS = 240
# What someone asked to be called, as they typed it. Shorter than the Discord
# cap on purpose: it lands above their facts in a prompt line, so it stays a
# name and cannot grow into a paragraph.
PREFERRED_MAX_CHARS = 32
_TEMPLATE_OPEN = "<|"
_TEMPLATE_SAFE = "\u27e8|"     # <| read the same, is not a chat-template token
SCHEMA_VERSION = 3
# The marker Nyanbot writes into every drop. A file without it is not a drop -
# it is something else wearing the name, and it is refused whole.
DROP_SCHEMA = "lulu-people-drop/1"
# Names I keep per person, including the ones they have thrown away.
MAX_ALIASES = 12
# People can have several accounts. Keep every one: an alt that speaks under an
# id I have not mapped is the same person arriving as a new stranger.
MAX_ACCOUNTS = 10
# How often a familiar person's last_seen/seen count is written. Without this,
# every single message would rewrite the whole ledger for a timestamp nobody
# reads that finely.
SEEN_BUCKET_MINUTES = 5

# Only things a person says about themselves are worth keeping automatically.
# Without this the ledger becomes a transcript, which is not what it is for.
_SELF_TALK = re.compile(
    r"\b(i|i'm|im|my|me|mine|myself)\b", re.IGNORECASE)


def clean_preferred(raw) -> str:
    """A name someone chose for themselves, made safe to keep and to speak.

    Untrusted by definition, because anyone may set their own, so it gets what a
    Discord display name already gets in the bot: no control characters, no
    newlines, one line, a cap, and `<|` broken so it cannot forge a
    chat-template header.
    """
    text = str(raw or "").replace(_TEMPLATE_OPEN, _TEMPLATE_SAFE)
    text = " ".join("".join(ch for ch in text if ch.isprintable()).split())
    return text[:PREFERRED_MAX_CHARS].strip()

_cache: dict = {"loaded_at": 0.0, "data": {}, "cards": {}, "drop": ""}


def _nyan_drop_valid(payload) -> dict:
    """The people in a drop, or {} when the drop is not whole.

    Everything the guard refuses comes back as an empty dict, so a caller can
    never half-apply a bad snapshot. Namely: not a dict/list, no schema marker,
    the wrong schema, no people, or a count that disagrees with the body - the
    last being the one that matters, because a truncated write says 'everyone
    else stopped existing' and nothing else would catch it.
    """
    if not isinstance(payload, dict):
        return {}
    people = payload.get("people")
    if payload.get("schema") != DROP_SCHEMA or not isinstance(people, dict):
        return {}
    if not people:
        return {}
    if int(payload.get("count") or 0) != len(people):
        return {}
    return people


def _read_drop() -> tuple[dict, str]:
    """The resolved drop Nyanbot left inside my wall, and where it came from.

    Pure read, no refresh: the loader below calls this from inside itself, so it
    must not reach back into anything that loads. See nyan_drop() for the public
    form.

    A valid drop is a snapshot, never a delta: it carries its own schema marker
    and the number of people in it. Both are checked, because the failure this
    guard exists for is silent - a half-written or partial file would read as
    'the rest of the world stopped existing' and quietly empty the ledger.
    Anything that fails is ignored whole; yesterday's copy stays in place.

    Order: the dated file named in latest.json, then latest.json itself, then
    the newest dated file. The pointer is only a shortcut, never a requirement.
    """
    def _valid(payload, source: str) -> tuple[dict, str] | None:
        people = _nyan_drop_valid(payload)
        return (people, source) if people else None

    base = paths.resolve(DROP_DIR)
    if not base.is_dir():
        return {}, ""

    pointer = ""
    try:
        pointer = str(json.loads(paths.resolve(DROP_LATEST).read_text(encoding="utf-8"))
                      .get("file") or "")
    except Exception:
        pointer = ""

    candidates = []
    if pointer:
        candidates.append(base / pointer)
    candidates.append(paths.resolve(DROP_LATEST))
    try:
        candidates.extend(sorted((p for p in base.glob("*.json")
                                  if p.name != "latest.json"), reverse=True))
    except OSError:
        pass

    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        ok = _valid(payload, path.name)
        if ok:
            return ok
    return {}, ""


def _canonical(key: str) -> str:
    """resolve() without the refresh() - safe to call from inside a load.

    resolve() keeps the public contract of always being current, which means it
    refreshes first. That is exactly what made the load below recurse into
    itself the first time it was written: refresh -> resolve -> refresh, until
    Python stopped it. Loading uses this raw form instead.
    """
    return _partner.get(key) or key


def refresh(force: bool = False) -> bool:
    """Re-read the people ledger if a day has gone by, or on demand.

    Order of preference: the resolved drop Nyanbot left inside my wall, then a
    card that fills a gap the drop did not cover, then her live file as the last
    resort. A drop wins when it is present and valid, because it is the only one
    of the three that has already resolved cards and alts. Nothing here writes
    any of those files.
    """
    now = time.monotonic()
    if not force and _cache["data"] and (now - _cache["loaded_at"]) < REFRESH_SECONDS:
        return False

    raw = dict(_partners_raw())
    data: dict = {}
    source = ""
    try:
        dropped, source = _read_drop()
    except Exception:
        dropped, source = {}, ""
    if dropped:
        _bridge_from_drop(dropped)
        # The drop already collapsed cards and alts, so this only has to collapse
        # anything left over. One pass, by the cards we just read.
        for key, entry in dropped.items():
            if not isinstance(entry, dict):
                continue
            canon = _partner.get(str(key)) or str(key)
            if canon in data:
                _fold_person(data[canon], entry)
            else:
                data[canon] = dict(entry)
        _absorb_cards(data)
        _cache["drop"] = source
    else:
        # No usable drop: her raw ledger, un-resolved. The bridge still puts a
        # carded person back together, so nothing is lost while a drop is absent.
        _cache["drop"] = ""
        try:
            loaded = json.loads(NYAN_LEDGER.read_text(encoding="utf-8"))
            data = loaded if isinstance(loaded, dict) else {}
        except Exception:
            # Keep whatever we had; a bad read must not wipe the day's knowledge.
            data = _cache["data"]

    _cache["data"] = {_canonical(str(k)): v for k, v in data.items()
                      if isinstance(v, dict)}
    _cache["loaded_at"] = now
    # And take a copy of what the wider ledger knows, into my own page on each
    # person. Never fatal - a ledger I could not absorb from is still a ledger.
    try:
        absorbed = _absorb_facts(_cache["data"])
        if absorbed:
            _cache["absorbed"] = absorbed
    except Exception:
        pass
    return True


def _absorb_facts(wide: dict) -> int:
    """Keep what the wider ledger knows as MY OWN page on a person.

    The drop is a SNAPSHOT, and it differs day to day. Master, 2026-09-21:
    "nyan's drop can divffer day to day, you should extract info from it and keep
    maybe a page of file on each person". Left as a live read of somebody else's
    latest export, knowledge does not decay - it vanishes all at once and
    silently, the day a fact stops being in the file: a person does not become a
    stranger gradually, they just stop existing in it.

    So the wider facts are COPIED IN, tagged with where they came from, and from
    then on they are mine - they survive a thin drop, and a later one only adds.
    Deduped by text, so a fact that is the same every day does not stack up, and
    bounded by the same cap my own facts already use.

    Returns how many people gained something.
    """
    people = learned()
    gained = 0
    for key, entry in (wide or {}).items():
        if not isinstance(entry, dict):
            continue
        wide_facts = []
        for item in entry.get("facts") or []:
            text = item.get("text") if isinstance(item, dict) else item
            if text:
                wide_facts.append(str(text))
        if not wide_facts:
            continue
        mine = _entry(people, str(key))
        known = {str(f.get("text")) for f in mine["facts"] if isinstance(f, dict)}
        added = False
        for text in wide_facts:
            text = redact(text.strip())[:500]
            if not text or text == "[redacted]" or text in known:
                continue
            mine["facts"].append({"text": text, "source": "nyan",
                                  "at": time.strftime("%Y-%m-%d %H:%M")})
            known.add(text)
            added = True
        if added:
            mine["facts"] = mine["facts"][-MAX_LOCAL_FACTS:]
            gained += 1
    if gained:
        _save(people)
    return gained


def _bridge_from_drop(dropped: dict) -> None:
    """Let the drop finish the bridge for anyone it resolved.

    A drop carries the account ids and aliases of every person in it, so once
    one lands, the live id of a carded person is known from the drop itself and
    does not have to come from the cards file. That matters because the cards
    file belongs to another bot: if it moves, the drop alone still resolves.
    """
    global _cards, _partner
    for key, entry in dropped.items():
        if not isinstance(entry, dict):
            continue
        key = str(key)
        accounts = [str(a).strip() for a in (entry.get("accounts") or []) if str(a).strip()]
        ids = [a for a in accounts if a.isdigit()] or ([key] if key.isdigit() else [])
        card = _cards.setdefault(key, {
            "key": key,
            "name": str(entry.get("custom_name") or "").strip(),
            "ids": [], "aliases": [], "username": "", "display": "",
            "handles": [],
        })
        for account in ids:
            if account not in card["ids"]:
                card["ids"].append(account)
            _partner.setdefault(account, key)
        for alias in entry.get("aliases") or []:
            alias = str(alias).strip()
            if alias and alias not in card["aliases"]:
                card["aliases"].append(alias)
                card["handles"].append(alias)


def _fold_person(into: dict, other: dict) -> None:
    """Merge one record into another: lists combine, first name wins."""
    for field in ("facts", "likes", "dislikes", "interests", "accounts", "aliases"):
        have = into.get(field) if isinstance(into.get(field), list) else []
        for item in other.get(field) or []:
            if item not in have:
                have.append(item)
        into[field] = have
    if not str(into.get("custom_name") or "").strip():
        into["custom_name"] = other.get("custom_name") or ""


def _partners_raw() -> dict:
    """Snapshot of the id -> card map, so a load cannot read it half-built."""
    refresh_guard = _cache.get("loading")
    return dict(_partner)


def _absorb_cards(people: dict) -> int:
    """Give every carded person a record, even one their drop never carried.

    Measured on the real ledgers: 6 of 56 cards had no facts record anywhere, so
    their knowledge lived only on the card. This creates that record, folds in
    the card's own name and handles, and wires up every account - so the bridge
    has one person to resolve to instead of two half-people.
    """
    made = 0
    for key, card in _cards.items():
        if key not in people:
            people[key] = {"facts": []}
            made += 1
        record = people[key]
        if not str(record.get("custom_name") or "").strip() and card.get("name"):
            record["custom_name"] = card["name"]
        accounts = record.get("accounts")
        if not isinstance(accounts, list):
            accounts = []
        for account in card.get("ids") or []:
            if account not in accounts:
                accounts.append(account)
        record["accounts"] = accounts[:MAX_ACCOUNTS]
        for field in ("facts", "likes", "dislikes", "interests"):
            if not isinstance(record.get(field), list):
                record[field] = []
    return made


def nyan_ledger() -> dict:
    """The ledger as loaded: the resolved drop when there is one, else her file.

    The fallback is for the window before Nyanbot has ever dropped, and for a
    drop that fails its guard. It is deliberately the raw file: un-resolved, so
    a carded person's facts stay under their card until the bridge puts them
    back together.
    """
    refresh()
    return _cache["data"]


def nyan_drop() -> tuple[dict, str]:
    """The drop as of now: refresh first, then hand back what was loaded."""
    refresh()
    return _cache["data"], _cache["drop"]


def drop_source() -> str:
    """Which file the ledger came from, for the log and the prompt line."""
    refresh()
    return _cache["drop"]


# -- the bridge ----------------------------------------------------------
#
#   _cards:   card key -> who that card is (name, ids, every handle it knows)
#   _partner: account id -> the card key that owns it
#
# Two maps, one rule: whoever is talking, resolve them to the ONE key their
# record lives under. A carded person resolves to their card, anyone else to
# their own discord id.
_cards: dict = {}
_partner: dict = {}


def _read_cards() -> None:
    """Index the /setinfo cards: who each card is, and every id that is them.

    A resolved drop carries its own accounts and aliases, so once one is in
    place this only has to fill the gaps for people the drop has not covered -
    a card with no record yet, or a handle it never resolved. The cards stay the
    authority for a live id, because a drop is only as fresh as the day it was
    written.
    """
    global _cards, _partner
    cards, partner = {}, {}
    try:
        raw = json.loads(CARDS.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    if isinstance(raw, dict):
        for key, card in raw.items():
            if not isinstance(card, dict):
                continue
            ids = [str(a).strip() for a in (card.get("accounts") or []) if str(a).strip()]
            aliases = [str(a).strip() for a in (card.get("aliases") or []) if str(a).strip()]
            name = str(card.get("custom_name") or "").strip()
            username = str(card.get("username") or "").strip()
            display = str(card.get("display_name") or "").strip()
            cards[str(key)] = {
                "key": str(key),
                "name": name,
                "ids": ids[:MAX_ACCOUNTS],
                "aliases": aliases[:MAX_ALIASES],
                "username": username,
                "display": display,
                # Every name that must resolve back to this one person.
                "handles": [h for h in [name, username, display] + aliases if h],
            }
            for account in ids:
                partner.setdefault(account, str(key))
    _cards = cards
    _partner = partner
    _cache["cards"] = cards


def card_for(key) -> dict:
    """The card that owns this person: by card name, or by any of their ids."""
    key = str(key or "").strip()
    if not key:
        return {}
    refresh()
    return _cards.get(key) or _cards.get(_partner.get(key, "")) or {}


def resolve(key) -> str:
    """The ONE key this person's record lives under.

    The card when they have one - so every account of theirs writes to the same
    record - and their own id otherwise. This is what keeps one human from
    arriving as two people.
    """
    key = str(key or "").strip()
    if not key:
        return ""
    refresh()
    return _partner.get(key) or key


def display_name(key, fallback: str = "") -> str:
    """What she should CALL this person, for the prompt and the mirror.

    Master's rule, 2026-09-21: their preferred name, then the ledger's custom
    name, then their live Discord display name. The preferred name is the one
    they asked for themselves, so it outranks everything - that is the whole
    point of asking. The custom name is what the ledgers carry (my own record
    first, then Nyan's drop, because mine is newer and it is mine), and the live
    display name is only the fallback for somebody nobody has carded, so nobody
    becomes "someone" over a missing field.

    NOT the @mention path: a ping has to stay the name the room can see, so
    readable_text() reads the live name directly instead of calling this.
    """
    preferred, custom = "", ""
    try:
        entry = learned().get(resolve(key)) or {}
        if isinstance(entry, dict):
            preferred = str(entry.get("preferred_name") or "").strip()
            custom = str(entry.get("custom_name") or "").strip()
    except Exception:
        pass
    if not custom:
        try:
            wider = nyan_ledger().get(resolve(key)) or {}
            if isinstance(wider, dict):
                custom = str(wider.get("custom_name") or "").strip()
        except Exception:
            custom = ""
    return preferred or custom or fallback


def known_person(key) -> bool:
    """True when either ledger already holds this person, under any of their keys."""
    key = str(key or "").strip()
    if not key:
        return False
    if key in nyan_ledger() or key in learned():
        return True
    card = card_for(key)
    return bool(card) and card.get("key") in nyan_ledger()


def ledger_age_hours() -> float:
    if not _cache["loaded_at"]:
        return -1.0
    return (time.monotonic() - _cache["loaded_at"]) / 3600


def summary() -> str:
    """A one-line picture of the wider ledger, for the prompt and the log."""
    ledger = nyan_ledger()
    mine = learned()
    known = 0
    for key, entry in ledger.items():
        if isinstance(entry, dict) and (entry.get("facts") or entry.get("custom_name")):
            known += 1
    if not ledger:
        return "no wider ledger loaded"
    return (f"{known} people in Nyan's ledger, "
            f"{len([k for k, v in mine.items() if isinstance(v, dict)])} in mine, "
            f"loaded {ledger_age_hours():.1f}h ago")


def learned() -> dict:
    """What I have learned about people, tolerating a ledger I cannot read.

    `paths.read_json` raises on a file it cannot parse, and an EMPTY file is one
    of those: `json.loads("")` is a JSONDecodeError, not "no people". On
    2026-09-22 `memory/people.json` was found at exactly 0 bytes, and that raise
    travelled much further than this function - it came out of on_ready ABOVE the
    health marker, so no fresh marker was ever written, the supervisor's health
    gate timed out at 120 seconds, and the patch she was staging was REVERTED.
    One truncated write cost her the self-edit pipeline and both restarts around
    it. A store I cannot read is a store with nothing in it - never a reason to
    fail.
    """
    try:
        data = paths.read_json(LOCAL, default={"people": {}})
    except (ValueError, UnicodeDecodeError, OSError):
        _quarantine()
        return {}
    people = data.get("people") if isinstance(data, dict) else None
    return people if isinstance(people, dict) else {}


def _quarantine() -> None:
    """Set a ledger I cannot read aside, instead of overwriting it.

    Learning nothing is survivable; eating the only copy of what I knew is not.
    The next _save writes a whole fresh file, so a corrupt one has to be moved
    out of its way FIRST - renamed, never deleted, because the bytes in it may
    be the last of something. Never fatal: if it cannot even be renamed, I still
    answer as though it were empty.
    """
    try:
        broken = paths.resolve(LOCAL)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        broken.replace(broken.with_name(f"{broken.name}.corrupt-{stamp}"))
    except Exception:
        pass


def _save(people: dict) -> None:
    """Write the ledger so a kill mid-write cannot leave it unreadable.

    `paths.write_text` is a plain open-and-truncate, so a process killed while
    writing leaves a ZERO-BYTE file - and an empty file does not read back as
    "no people", it raises. That is not hypothetical: it is exactly what
    `memory/people.json` was found as on 2026-09-22. So the text lands on a
    neighbour first and is moved into place. os.replace is atomic within one
    volume, so a reader sees the whole old ledger or the whole new one and never
    half of either.

    internal=True on the write: my own storage layer, not a tool call.
    """
    text = json.dumps({"version": SCHEMA_VERSION, "people": people},
                      indent=2, ensure_ascii=False)
    staged = paths.write_text(f"{LOCAL}.writing", text, internal=True)
    os.replace(staged, paths.resolve(LOCAL))


def _bucket(stamp: str) -> str:
    """A coarse time key, so last_seen can be updated without a write per message."""
    try:
        day, clock = str(stamp).split(" ")
        hour, minute = clock.split(":")[:2]
        return f"{day} {hour}:{int(minute) // SEEN_BUCKET_MINUTES}"
    except Exception:
        return ""


def _blank() -> dict:
    return {"names": {}, "preferred_name": "", "facts": [], "likes": [],
            "dislikes": [], "interests": []}


def _entry(people: dict, key: str) -> dict:
    """One person's record, upgraded in place to the current shape."""
    entry = people.get(key)
    if not isinstance(entry, dict):
        entry = _blank()
        people[key] = entry
    if not isinstance(entry.get("names"), dict):
        entry["names"] = {}
    if not isinstance(entry["names"].get("aliases"), list):
        entry["names"]["aliases"] = []
    for key_name in ("facts", "likes", "dislikes", "interests", "accounts"):
        if not isinstance(entry.get(key_name), list):
            entry[key_name] = []
    if not isinstance(entry.get("avatar_note"), dict):
        entry["avatar_note"] = {}
    if not isinstance(entry.get("preferred_name"), str):
        entry["preferred_name"] = ""
    return entry


# Discord builds an avatar url out of a HASH of the picture, so the hash in the
# url IS the picture's identity: same hash, same image, whatever the size or
# format suffix claims. That is what makes a look worth caching - it says
# whether the thing in front of me is a picture I have already seen, without
# spending a vision call or a single byte to find out.
_AVATAR_HASH = re.compile(r"/avatars/\d+/([0-9a-fA-F]{32})")


def avatar_hash(url: str) -> str:
    """The picture's own hash out of an avatar url, or "" if it is not one."""
    found = _AVATAR_HASH.search(str(url or ""))
    return found.group(1).lower() if found else ""


def note_avatar(user_id, text: str, avatar_hash: str,
                source: str = "look") -> str:
    """What I saw in somebody's profile picture, kept AT the hash I saw it at.

    So a second ask about an unchanged picture is a read and not another vision
    call, and a picture that HAS changed is looked at again without anyone
    telling me. Master, 2026-09-21: "you can grab the hash of their avatar and
    check if you need to update the info on their avatar by comparing the hash
    before sending to vision model".

    One note per picture, newest kept, redacted like anything else I write down
    about a person.
    """
    key = resolve(user_id)
    text = redact((text or "").strip())
    if not key or not text or text == "[redacted]":
        return "nothing worth storing"
    people = learned()
    entry = _entry(people, key)
    note = entry["avatar_note"]
    note[avatar_hash or "unknown"] = {
        "text": text[:600],
        "at": time.strftime("%Y-%m-%d %H:%M"),
        "source": source,
    }
    for stale in sorted(note, key=lambda k: str(note[k].get("at") or ""))[:-MAX_AVATAR_NOTES]:
        note.pop(stale, None)
    _save(people)
    return "noted"


def identify(user_id, username: str = "", display: str = "", global_name: str = "",
             nick: str = "", mention: str = "", channel: str = "",
             avatar: str = "") -> bool:
    """Record who someone is, every time they speak.

    The key is resolved first, so a carded person writes to their own record
    from whichever account they happen to be on, and every name anyone has used
    hangs off that one record: a rename demotes the old name to an alias instead
    of losing it. Writes are throttled - identity changes or a new 5-minute
    bucket, and nothing otherwise - because this is called on every message.
    """
    spoke_as = str(user_id or "").strip()
    if not spoke_as:
        return False

    key = resolve(spoke_as)
    people = learned()
    entry = _entry(people, key)
    names = entry["names"]
    changed = False

    aliases = names.get("aliases")
    if not isinstance(aliases, list):
        aliases = []
        names["aliases"] = aliases

    # Every account this person speaks from. An alt is not a stranger.
    if spoke_as != key:
        accounts = entry["accounts"]
        if spoke_as not in accounts:
            accounts.append(spoke_as)
            changed = True
        entry["accounts"] = accounts[-MAX_ACCOUNTS:]

    for field, value in (("username", username), ("display", display),
                         ("global", global_name), ("nick", nick)):
        value = str(value or "").strip()
        if not value:
            continue
        previous = str(names.get(field) or "").strip()
        if previous == value:
            continue
        # Keep the name they used to use. This is the whole point of the layer.
        if previous and previous not in aliases:
            aliases.append(previous[:64])
        names[field] = value[:64]
        changed = True
    if mention and names.get("mention") != str(mention):
        names["mention"] = str(mention)[:64]
        changed = True

    # Their profile picture, kept as a URL and never as bytes - and kept for
    # its HASH, which is the whole point. Discord builds an avatar url out of a
    # hash of the image, so two urls with the same hash are the same picture no
    # matter how the query string is dressed. Recorded here because this is the
    # only place the member object exists: a tool call runs in a worker thread
    # with no event loop and no client.
    #
    # Free: it costs no vision call and no request. What it does NOT do is look
    # at the picture - master, 2026-09-21: "you dont need to automatically grab
    # every user's profile picture, only update it when something requires you
    # to". The url and hash are facts about a message somebody already sent; the
    # LOOKING happens on demand, in tools.look_at_pfp.
    avatar = str(avatar or "").strip()
    if avatar:
        if entry.get("avatar") != avatar:
            entry["avatar"] = avatar[:512]
            changed = True
        seen_hash = avatar_hash(avatar)
        if seen_hash and entry.get("avatar_hash") != seen_hash:
            entry["avatar_hash"] = seen_hash
            changed = True

    names["aliases"] = aliases[-MAX_ALIASES:]

    # What the card knows and a single message cannot: the other accounts this
    # person speaks from, and every handle those accounts answer to. The card's
    # own name becomes an alias too - being able to find someone by the name I
    # first knew them as is the whole point of keeping aliases at all.
    card = card_for(key)
    if card:
        primary = str(entry.get("custom_name") or "").strip().lower()
        for handle in card.get("handles") or []:
            handle = str(handle).strip()
            if not handle or handle[:64] in aliases or handle.lower() == primary:
                continue
            aliases.append(handle[:64])
            changed = True
        accounts = entry["accounts"]
        for account in card.get("ids") or []:
            if account not in accounts:
                accounts.append(account)
                changed = True
        entry["accounts"] = accounts[-MAX_ACCOUNTS:]
        names["aliases"] = aliases[-MAX_ALIASES:]

    if channel:
        chans = entry.get("channels")
        if not isinstance(chans, list):
            chans = []
        if str(channel) not in chans:
            chans.append(str(channel))
            changed = True
        entry["channels"] = chans[-20:]

    # What I call them out loud: the custom name when there is one, because that
    # is the one the owner chose, and the Discord display name only as the
    # fallback for someone nobody has carded. A raw account id is never a name,
    # so it is replaced the moment anything better turns up.
    current = str(entry.get("custom_name") or "").strip()
    if card.get("name") and (not current or current.isdigit()):
        entry["custom_name"] = str(card["name"])[:64]
        changed = True
    elif not current:
        picked = (names.get("nick") or names.get("display")
                  or names.get("username") or names.get("global") or "")
        if picked:
            entry["custom_name"] = picked
            changed = True

    now = time.strftime("%Y-%m-%d %H:%M")
    if not changed and _bucket(entry.get("last_seen") or "") == _bucket(now):
        return False  # nothing new, and too soon for another familiar-count write

    entry["seen"] = int(entry.get("seen") or 0) + 1
    entry["last_seen"] = now
    if not entry.get("first_seen"):
        entry["first_seen"] = now
    _save(people)
    return True


def upgrade_all() -> int:
    """Rewrite every record into the current shape. Idempotent."""
    people = learned()
    for key in list(people):
        _entry(people, key)
    _save(people)
    return len(people)


def familiarity(user_id) -> str:
    """Plain words for how well I know someone, or empty if I do not.

    Master, 2026-09-23: the counts do not get SHOWN - "129 messages on record
    since the 22nd" reads as keeping a file on someone. The ledger still
    counts, because the dossier and the daily pass need it; what I say out
    loud is only the shape of it, never the number, the date or the room.
    """
    entry = learned().get(resolve(user_id)) or {}
    seen = int(entry.get("seen") or 0)
    if not seen:
        return ""
    if seen < 20:
        return "a new face i have seen a few times"
    if seen < 100:
        return "been around a while"
    return "a regular"


def _titles(entry: dict, key: str) -> list[str]:
    out = []
    for item in entry.get(key) or []:
        if isinstance(item, dict) and item.get("t"):
            out.append(str(item["t"]))
    return out


def _titles_many(entries, key: str) -> list[str]:
    """Likes/dislikes/interests from every ledger, mine first, deduped.

    This used to read Nyan's ledger ONLY. So the fold copied 129 people's
    likes into my notebook and every one of them was silently ignored - the
    facts and the name reached my prompt, the rest did not, which made the
    fold look complete while a third of it did nothing.
    """
    out, seen = [], set()
    for entry in entries:
        for title in _titles(entry, key):
            if title not in seen:
                seen.add(title)
                out.append(title)
    return out


def lookup(user_id) -> dict:
    """Merge both ledgers for one person. Mine wins, because it is newer.

    The key is resolved first, so it does not matter which account someone spoke
    from or whether they were called by a name, a nickname or a number: they
    all land on the one record that person has.
    """
    key = resolve(user_id)
    card = card_for(key)
    mine = learned().get(key) or {}
    hers = nyan_ledger().get(key) or {}

    # The name I say out loud. The card's custom name wins because it is the one
    # the owner chose; the wider ledger's name comes next; a live Discord name
    # is the fallback for anyone nobody has carded.
    names = mine.get("names") if isinstance(mine.get("names"), dict) else {}
    live = str(names.get("nick") or names.get("display") or "").strip()
    mine_name = str(mine.get("custom_name") or "").strip()
    # Their own preferred name outranks every ledger, master 2026-09-21: it is
    # the one they asked for. Everything after it is the old order, unchanged.
    preferred = str(mine.get("preferred_name") or "").strip()
    hero = (preferred or card.get("name") or hers.get("custom_name")
            or ("" if mine_name.isdigit() else mine_name) or live)

    facts: list[str] = []
    if isinstance(mine.get("facts"), list):
        for item in mine["facts"]:
            text = item.get("text") if isinstance(item, dict) else item
            if text:
                facts.append(str(text))
    if isinstance(hers.get("facts"), list):
        for item in hers["facts"]:
            if isinstance(item, dict) and item.get("text"):
                facts.append(str(item["text"]))

    seen, unique = set(), []
    for fact in facts:
        if fact not in seen:
            seen.add(fact)
            unique.append(fact)

    return {
        "key": key,
        "custom_name": hero or "",
        "dossier": _dossier_text(mine),
        "facts": unique[:MAX_FACTS],
        "likes": _titles_many((mine, hers), "likes"),
        "dislikes": _titles_many((mine, hers), "dislikes"),
        "interests": _titles_many((mine, hers), "interests"),
        # The identity layer - mine only, because the wider ledger has no such
        # thing to fall back to.
        "names": mine.get("names") if isinstance(mine.get("names"), dict) else {},
        "accounts": mine.get("accounts") if isinstance(mine.get("accounts"), list) else [],
        "card": card.get("key") or "",
        # The profile picture, and what I last saw in it. `avatar_hash` is the
        # picture's identity on Discord's side; `avatar_note` carries the hash it
        # was seen AT, so a look is only re-taken when the picture has actually
        # changed. Empty for anyone who has not spoken since this existed, which
        # the door says plainly rather than guessing.
        "avatar": mine.get("avatar") or "",
        "avatar_hash": mine.get("avatar_hash") or "",
        "avatar_note": mine.get("avatar_note") if isinstance(mine.get("avatar_note"), dict) else {},
        "first_seen": mine.get("first_seen") or "",
        "last_seen": mine.get("last_seen") or "",
        "seen": mine.get("seen") or 0,
        "channels": mine.get("channels") or [],
        "tags": mine.get("tags") or [],
    }


def _searchable(entry: dict) -> list[str]:
    """Every name this person answers to, lowercased, for matching.

    Aliases matter here: someone who renamed themselves should still be found by
    the name I first knew them as, which is the entire reason to keep them.
    """
    names = entry.get("names") if isinstance(entry.get("names"), dict) else {}
    out = [str(entry.get("custom_name") or "")]
    for field in ("username", "display", "nick", "global"):
        if names.get(field):
            out.append(str(names[field]))
    for alias in names.get("aliases") or []:
        out.append(str(alias))
    return [name.lower() for name in out if name]


def find(query: str, limit: int = 5) -> list[dict]:
    """People whose id or known name matches what was typed.

    So 'look up who I am talking to' is something I can actually do for anyone,
    not only for the person whose message I am answering. Matches on id, or on
    a chunk of the name, case-insensitively - so 'velvet' finds them.
    """
    q = (query or "").strip().lower()
    if not q:
        return []

    order = list(learned().keys())
    order += [uid for uid in nyan_ledger() if uid not in set(order)]

    hits, seen = [], set()
    for uid in order:
        # The two ledgers hold one person under different keys - their card and
        # their account id. Resolve first so they are never listed twice.
        uid = resolve(uid)
        if uid in seen:
            continue
        entry = lookup(uid)
        if q == uid.lower() or any(q in name for name in _searchable(entry)):
            seen.add(uid)
            hits.append({"id": uid, **entry})
            if len(hits) >= limit:
                break
    return hits


def block(user_id) -> str:
    """Compact 'who is this' text for the prompt, or empty string."""
    entry = lookup(user_id)
    parts = []
    if entry["custom_name"]:
        parts.append(f"you know this person as {entry['custom_name']}")

    # Names I have known them by, including their other accounts. Worth a line: it
    # is how I recognise someone who has renamed themselves instead of treating
    # them as a new arrival. Compared case-insensitively, so a name differing
    # only in capitals is not listed as though it were a second name.
    names = entry.get("names") or {}
    others = []
    lowered = []
    primary = str(entry["custom_name"] or "").strip().lower()
    for source in ("nick", "display", "username", "global"):
        value = str(names.get(source) or "").strip()
        if value and value.lower() != primary and value.lower() not in lowered:
            others.append(value)
            lowered.append(value.lower())
    for alias in names.get("aliases") or []:
        alias = str(alias).strip()
        if alias and alias.lower() != primary and alias.lower() not in lowered:
            others.append(alias)
            lowered.append(alias.lower())
    if others:
        parts.append("also known as: " + ", ".join(others[:4]))

    familiar = familiarity(user_id)
    if familiar:
        parts.append(f"seen them around: {familiar}")

    if entry["facts"]:
        parts.append("facts: " + " | ".join(entry["facts"][:5]))
    if entry["likes"]:
        parts.append("likes: " + ", ".join(entry["likes"][:5]))
    if entry["dislikes"]:
        parts.append("dislikes: " + ", ".join(entry["dislikes"][:5]))
    if entry["interests"]:
        parts.append("interests: " + ", ".join(entry["interests"][:5]))
    return "\n".join(parts)


def full_block(user_id) -> str:
    """The deep read: my compact block PLUS the dossier prose.

    A page of prose is too much to ride into every reply in a busy room, so
    the compact block is what ordinary turns carry and this is the upgrade:
    1-on-1 conversations only (a DM, or a reply chain with this person).
    Master, 2026-09-23: nyan's smaller facts for inference usually, the full
    dossier when it is one on one.
    """
    dossier = _dossier_text(learned().get(resolve(user_id)) or {})
    compact = block(user_id)
    if not dossier:
        return compact
    parts = ["dossier (my page on them):", dossier]
    if compact:
        parts.append(compact)
    return "\n\n".join(parts)


def learn(user_id, text: str, name: str = "", source: str = "told") -> str:
    """Record one fact about someone, in my own ledger."""
    key = resolve(user_id)
    text = redact((text or "").strip())
    if not key or not text or text == "[redacted]":
        return "nothing worth storing"

    people = learned()
    entry = _entry(people, key)
    if name:
        entry["custom_name"] = name

    facts = entry.get("facts")
    if not isinstance(facts, list):
        facts = []
    if text in [f.get("text") for f in facts if isinstance(f, dict)]:
        return "already knew that"
    facts.append({"text": text[:500], "at": time.strftime("%Y-%m-%d %H:%M"),
                  "source": source})
    entry["facts"] = facts[-MAX_LOCAL_FACTS:]
    _save(people)
    return "noted"


def set_dossier(user_id, text: str) -> str:
    """Write my page of prose on someone - the dossier, not a fact list.

    Master, 2026-09-23: the dossier should be like a page of text, not too
    short. A write REPLACES the stored page: it is written as the whole
    picture, old material merged in, never an append of one more line.
    """
    key = resolve(user_id)
    body = redact(str(text or "").strip())
    if not key or not body or body == "[redacted]":
        return "nothing worth storing"
    if len(body) < DOSSIER_MIN_CHARS:
        return (f"too short - a dossier is prose, most of a page "
                f"(at least {DOSSIER_MIN_CHARS} characters)")
    people = learned()
    entry = _entry(people, key)
    entry["dossier"] = {"text": body[:DOSSIER_MAX_CHARS],
                        "at": time.strftime("%Y-%m-%d %H:%M")}
    _save(people)
    return "dossier written"


def _dossier_text(mine: dict) -> str:
    """The stored dossier prose for one person, empty when there is none."""
    page = (mine or {}).get("dossier")
    if isinstance(page, dict):
        return str(page.get("text") or "")
    if isinstance(page, str):
        return page
    return ""


def set_preferred(user_id, name: str) -> str:
    """Record what someone asked to be CALLED, in their own words.

    The one thing a person writes into my ledger about themselves, and it is
    only ever about themselves: the key is the caller, never a name handed to
    me, so nobody renames anybody else through this. It writes one name and no
    facts - nothing a message contained lands in the record.

    Master's rule, 2026-09-21: a preferred name outranks the ledger's custom
    name and the live Discord display name, because it is the name they chose.
    """
    key = resolve(user_id)
    if not key:
        return "I do not know whose name that is"
    clean = clean_preferred(name)
    if not clean:
        return "that is not a name I can keep"
    people = learned()
    entry = _entry(people, key)
    if str(entry.get("preferred_name") or "") == clean:
        return "already had that"
    entry["preferred_name"] = clean
    _save(people)
    return "noted"


def observe(user_id, name: str, message: str) -> str:
    """Pick up what someone says about themselves, without being asked.

    Deliberately narrow: only first-person statements, only the first one in a
    message, and never a bare greeting. A ledger of everything is a log, and a
    log is not knowledge.
    """
    text = (message or "").strip()
    if len(text) < 12:
        return ""
    if not _SELF_TALK.search(text):
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", text)[0].strip()
    if not _SELF_TALK.search(sentence):
        sentence = text[:AUTO_MAX_CHARS]
    return learn(user_id, sentence[:AUTO_MAX_CHARS], name=name, source="observed")


def known_count() -> int:
    """Distinct people held across both ledgers, cards and accounts collapsed.

    A bare len(ledger) counted the same human twice - once as their card and
    once as their account id - so the number was never the number of people.
    """
    keys = {resolve(k) for k in nyan_ledger()}
    return len(keys)
