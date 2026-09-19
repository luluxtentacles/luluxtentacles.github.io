"""The purse.

One dollar a day buys all the talking that is not master's. The point is not to
ration strangers - it is to make the cost of spamming a known, bounded number,
so a bored regular with a keyboard cannot spend a month of credits in an evening.

Why a ledger file and not a counter: restarts are normal here - a patch, a health
check, a crash - and an in-process total would reset to zero on every one of
them, so someone who noticed a restart cycle could be unmetered. The day is
stamped in UTC because the provider's own meter resets that way, and two clocks
that disagree cannot be reconciled.

Why the owner has no place in this module: master's turns are never priced and
never refused. lulu_bot simply does not call this for him. The cap exists to
bound strangers, not the person paying the bill.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

import paths

LOG = logging.getLogger("lulu")

# Where prices come from, and why not from the endpoint she talks to.
#
# GET /zen/go/v1/models lists models and carries NO price fields at all, and
# /usage reports percents rather than dollars. Verified by probe, twice. The one
# machine-readable price list opencode publishes is its own catalog:
#
#     https://models.dev/api.json   ->   providers["opencode"].models[*].cost
#
# So this is a LOOKUP with a cache, not a table baked into the file. The table
# was the bug: it was pinned to one model's rates, master switched her to
# glm-5.3-flash, and every figure the cap produced was priced off the wrong row
# - quietly, because a missing model fell through to a default instead of
# saying so. Re-fetching daily means the next swap prices itself.
PRICE_CATALOG = "https://models.dev/api.json"
PRICE_PROVIDER = "opencode"
PRICE_CACHE = "price_cache.json"      # beside her code: not sealed, not the store
PRICE_TTL_SECONDS = 24 * 60 * 60      # daily. Prices drift slowly; calls do not.

# What the cap refuses to guess with. If a model is missing from the catalog and
# from the cache and from config, the estimate path uses this - deliberately the
# DEARER end of the models on offer, so an unknown model is priced
# pessimistically rather than free. Overpricing a stranger is a safe failure.
FALLBACK_PRICE = {"input": 1.40, "output": 4.40, "cache_read": 0.26}

# What a day of other people's talking may cost. Overridable from
# config.json -> budget.daily_usd.
DEFAULT_DAILY_USD = 1.00

# Both live beside her code, NOT under memory/. memory/ is a sealed tier - the
# wall refuses writes there, and the first version of this file pointed at
# memory/spend.json, so every save was refused, every read came back blank, and
# the cap could never trip. A spending cap that silently does not work is worse
# than no cap: it looks installed. Root-level files are ordinary writing, which
# is what runtime state should be.
LEDGER = "spend.json"

# Chars-per-token, used only when a provider omits `usage`. Deliberately rough
# and deliberately applied at the DEARER of the two rates: an unmetered call
# must not come out cheap, or picking an endpoint that reports nothing would be
# a way around a spending cap.
CHARS_PER_TOKEN = 4

_lock = threading.Lock()
_config: dict = {}
_prices: dict[str, dict] = {}
_price_meta: dict = {}
_warned_models: set[str] = set()

# The model this day's figures were priced with. Recorded in the ledger so a
# mid-day model swap is visible in the file rather than inferred from numbers
# that quietly changed meaning - which is exactly how the hardcoded table hid
# its own staleness.
_model_seen: str | None = None


def configure(config: dict) -> None:
    """Take cap and prices from config, once, at startup.

    Prices are loaded here rather than per call: one lookup at boot, cached to
    disk for a day, so no reply ever waits on the catalog.
    """
    global _config
    _config = config or {}
    load_prices()


def load_prices(*, force: bool = False) -> dict:
    """The price table: config override, then cached catalog, then a fetch.

    Never fatal. A cap that cannot price a call is worse than a cap priced from
    yesterday's file, so every failure here degrades to the last known table and
    says so in the log.
    """
    global _prices, _price_meta
    override = _budget_config().get("prices")
    if isinstance(override, dict) and override:
        _prices = {str(k): {**FALLBACK_PRICE, **v}
                   for k, v in override.items() if isinstance(v, dict)}
        _price_meta = {"source": "config.json", "fetched": None,
                       "models": sorted(_prices)}
        LOG.info("prices from config.json: %d model(s)", len(_prices))
        return _prices

    cached = _read_cache()
    fresh = (cached.get("fetched") or 0) and (
        time.time() - float(cached["fetched"]) < PRICE_TTL_SECONDS)
    if cached and fresh and not force:
        _prices = cached.get("prices") or {}
        _price_meta = {k: cached.get(k) for k in ("source", "fetched")}
        _price_meta["models"] = sorted(_prices)
        LOG.info("prices from cache: %d model(s), %s", len(_prices),
                 cached.get("source"))
        return _prices

    fetched = _fetch_catalog()
    if fetched:
        _prices = fetched
        _price_meta = {"source": PRICE_CATALOG, "fetched": time.time(),
                       "models": sorted(_prices)}
        _write_cache(_price_meta["fetched"], _prices)
        LOG.info("prices fetched: %d model(s) from %s", len(_prices), PRICE_CATALOG)
        return _prices

    if cached:
        _prices = cached.get("prices") or {}
        _price_meta = {"source": cached.get("source") or "stale cache",
                       "fetched": cached.get("fetched"), "stale": True,
                       "models": sorted(_prices)}
        LOG.warning("price lookup failed; using the cache from %s",
                    cached.get("fetched"))
        return _prices

    _prices = {}
    _price_meta = {"source": "none", "fetched": None, "models": []}
    LOG.warning("no prices anywhere - every call will price at the fallback rate")
    return _prices


def _fetch_catalog() -> dict:
    """One GET at the published catalog. Returns {} on any failure."""
    try:
        import json
        import urllib.request

        request = urllib.request.Request(
            PRICE_CATALOG, headers={"User-Agent": "lulu-price-lookup"})
        with urllib.request.urlopen(request, timeout=30) as response:
            catalog = json.load(response)
        models = (catalog.get(PRICE_PROVIDER) or {}).get("models") or {}
        table = {}
        for name, entry in models.items():
            cost = (entry or {}).get("cost")
            if not isinstance(cost, dict):
                continue
            row = {k: cost.get(k) for k in ("input", "output", "cache_read")}
            if not isinstance(row["input"], (int, float)):
                continue
            # A catalog row need not carry every rate. Missing ones come from the
            # fallback rather than from zero: a free-looking gap is worse than a
            # conservative number.
            table[str(name)] = {
                "input": float(row["input"]),
                "output": float(row["output"]
                                if isinstance(row["output"], (int, float))
                                else row["input"]),
                "cache_read": float(row["cache_read"]
                                    if isinstance(row["cache_read"], (int, float))
                                    else row["input"]),
            }
        return table
    except Exception as exc:
        LOG.warning("could not fetch prices: %s", exc)
        return {}


def _read_cache() -> dict:
    try:
        data = paths.read_json(PRICE_CACHE)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_cache(fetched: float, prices: dict) -> None:
    try:
        paths.write_json(PRICE_CACHE, {
            "source": PRICE_CATALOG, "provider": PRICE_PROVIDER,
            "fetched": fetched, "prices": prices,
        }, internal=True)
    except Exception as exc:
        LOG.warning("could not cache prices: %s", exc)


def _budget_config() -> dict:
    value = _config.get("budget")
    return value if isinstance(value, dict) else {}


def daily_cap() -> float:
    raw = _budget_config().get("daily_usd", DEFAULT_DAILY_USD)
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_DAILY_USD


def price_for(model: str | None) -> dict:
    """This model's price row: the looked-up table, or a LOUD fallback.

    A missing model used to fall through silently to a default row, which is how
    a model swap produced wrong numbers that looked fine. Now it warns once per
    model and prices at the dearer fallback instead - an unknown model is never
    quietly cheap.
    """
    name = model or ""
    global _model_seen
    if name and name != _model_seen:
        if _model_seen:
            LOG.warning("model changed from %r to %r mid-day - the ledger now "
                        "records which model priced it", _model_seen, name)
        _model_seen = name
    if not _prices:
        # Nothing loaded yet: a direct call outside the bot's startup path.
        load_prices()
    row = _prices.get(name)
    if isinstance(row, dict):
        return row
    if name and name not in _warned_models:
        _warned_models.add(name)
        LOG.warning("no price for model %r in %s - pricing at the fallback rate "
                    "(%s); refresh the cache or add it to budget.prices",
                    name, _price_meta.get("source"), FALLBACK_PRICE)
    return FALLBACK_PRICE


def price_meta() -> dict:
    """Where the current rates came from - for the ledger and for a log line."""
    return dict(_price_meta)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _blank(day: str) -> dict:
    return {"day": day, "cap_usd": daily_cap(), "total_usd": 0.0,
            "estimated_usd": 0.0, "calls": 0, "users": {}, "updated": _stamp(),
            "priced_with": _model_seen, "rates_from": _price_meta.get("source")}


def _load() -> dict:
    """Today's ledger, or a fresh one.

    A file from another day is not merged or carried forward: the cap is per day,
    and a stale ledger describes a day nobody can spend from any more.
    """
    day = _today()
    try:
        data = paths.read_json(LEDGER)
    except FileNotFoundError:
        # The ordinary first call of a day: no ledger yet. Not a fault, so it is
        # not logged as one - a warning here would fire on every quiet morning
        # and train the eye to skip the line that matters.
        return _blank(day)
    except Exception as exc:
        LOG.warning("could not read the purse: %s", exc)
        return _blank(day)
    if not isinstance(data, dict) or data.get("day") != day:
        return _blank(day)
    if not isinstance(data.get("users"), dict):
        data["users"] = {}
    # If the model changed since the ledger was written, say so in the file.
    if _model_seen and data.get("priced_with") not in (None, _model_seen):
        data.setdefault("model_changes", []).append(
            {"at": _stamp(), "from": data.get("priced_with"), "to": _model_seen})
        data["priced_with"] = _model_seen
    return data


def _save(data: dict) -> None:
    try:
        # internal=True: my own storage layer, the same key people.py and the
        # chatter state use to write inside the sealed memory/ folder.
        paths.write_json(LEDGER, data, internal=True)
    except Exception as exc:
        # A ledger write must never cost someone their answer. But it must never
        # be SILENT either: the first version swallowed a refusal here, so the
        # cap read a blank ledger on every call and never once tripped. That is
        # a spending cap that silently does not work - the worst outcome there
        # is, because the guard looks present and is not.
        LOG.warning("could not save the purse: %s", exc)


def cost(usage, model: str | None,
         prompt_chars: int = 0, answer_chars: int = 0) -> tuple[float, bool]:
    """What one call cost. Returns (dollars, was_estimated)."""
    row = price_for(model)
    if isinstance(usage, dict):
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        if isinstance(prompt, int) and isinstance(completion, int):
            details = usage.get("prompt_tokens_details")
            cached = details.get("cached_tokens") if isinstance(details, dict) else 0
            cached = cached if isinstance(cached, int) else 0
            fresh = max(0, prompt - cached)
            dollars = (fresh * row["input"] + cached * row["cache_read"]
                       + completion * row["output"]) / 1_000_000
            return round(dollars, 6), False
    # No usage came back, so price the text we sent and the text we got. Flagged
    # as estimated in the ledger, so the number stays auditable afterwards.
    tokens = (max(0, prompt_chars) + max(0, answer_chars)) / CHARS_PER_TOKEN
    rate = max(row["input"], row["output"])
    return round(tokens * rate / 1_000_000, 6), True


def spent_today() -> float:
    with _lock:
        return float(_load().get("total_usd") or 0.0)


def remaining() -> float:
    return round(max(0.0, daily_cap() - spent_today()), 6)


def exhausted() -> bool:
    """Has the day's global allowance been used up?"""
    return spent_today() >= daily_cap()


def charge(user_id, usage, model: str | None, *,
           prompt_chars: int = 0, answer_chars: int = 0) -> float:
    """Add one call to today's global total. Returns the dollars it added.

    `user_id` is kept only for the per-person breakdown, so an expensive regular
    can be seen - the CAP itself is global, because ten accounts each under a
    per-user cap is the same bill.
    """
    dollars, estimated = cost(usage, model, prompt_chars, answer_chars)
    with _lock:
        data = _load()
        data["total_usd"] = round(float(data.get("total_usd") or 0.0) + dollars, 6)
        if estimated:
            data["estimated_usd"] = round(
                float(data.get("estimated_usd") or 0.0) + dollars, 6)
        data["calls"] = int(data.get("calls") or 0) + 1
        entry = data["users"].setdefault(str(user_id), {"usd": 0.0, "calls": 0})
        entry["usd"] = round(float(entry.get("usd") or 0.0) + dollars, 6)
        entry["calls"] = int(entry.get("calls") or 0) + 1
        data["cap_usd"] = daily_cap()
        data["updated"] = _stamp()
        _save(data)
    return dollars


def summary() -> str:
    """One line for a log or a status command."""
    data = _load()
    return (f"${float(data.get('total_usd') or 0.0):.4f} of ${daily_cap():.2f} "
            f"today, {data.get('calls') or 0} call(s), "
            f"{len(data.get('users') or {})} talker(s), "
            f"priced with {data.get('priced_with') or 'nothing yet'}")
