"""The mouth.

One OpenAI-compatible chat endpoint, chosen entirely by config.json, so a
local llama.cpp server, OpenRouter, or anything else that speaks the same
shape all work without touching this file.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
import urllib.error
import urllib.request
import uuid

# How long one model call may hang before we give up on it. Master raised this
# to 600s on 2026-09-20: a tool loop resends a growing prompt every round, and a
# slow round was being cut off at two minutes - which surfaced as her going
# quiet rather than as an error. A whole TURN is bounded separately, by the
# supersede check in run_turns, so a follow-up message still cuts a stuck turn
# short without waiting for this to expire.
TIMEOUT_SECONDS = 600

# opencode.ai sits behind Cloudflare, which rejects urllib's default agent and
# route the Go tier by session rather than by key alone. Both are required.
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# The session id sent on every call, generated ONCE per process.
#
# It used to be a fresh uuid4 per call - `str(uuid.uuid4())` inline in the
# headers - and that is the one detail in this file that can defeat a provider's
# automatic prompt cache. The prefix is what gets cached; if the routing session
# changes on every request there is nothing stable to match it against. A tool
# loop is up to 12 rounds resending a growing prefix, which is exactly the case
# caching exists to pay for, and it was mints a new identity between rounds.
#
# Overridable on purpose: the bot can set this to rotate a session mid-run if a
# measurement ever shows that is what the provider wants.
SESSION_ID = str(uuid.uuid4())

# config.json -> brain.prompt_cache / brain.base_url, folded in on the
# first complete() call (module-level so _providers can read them).
_PROMPT_CACHE = None
_BASE_URL = ""


# ---------------------------------------------------------------------------
# Key ladder (2026-09-20, master).
#
# brain_key.txt is gone. Keys now live in brain_keys.json beside this file:
#   open_code_key  - the OpenCode Go subscription (primary, same endpoint
#                    config.json -> brain.base_url already points at);
#   gemini_key .. gemini_key5 - Google AI Studio keys, each its own free
#                    quota bucket, tried in order via Google's
#                    OpenAI-compatible endpoint;
#   or_key         - OpenRouter, the last resort. FREE-tier models only, so
#                    a spent or_key still can't cost master money - the ids
#                    live in OR_MODELS_DEFAULT, edit those to taste.
#
# The shape is nyan's (DiscordBotN5/opencode_go.py): Go is the primary, a
# provider-level failure (quota/auth) BENCHES it for a cooldown so a spent
# subscription is not hammered by every turn, and the fallbacks are only
# entered on those credit/quota errors - other errors are ours, not the
# provider's, and falling back on them would hide bugs.
# ---------------------------------------------------------------------------

_KEYS_FILE = Path(__file__).resolve().parent / "brain_keys.json"
_keys_cache = {"mtime": None, "keys": {}}

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
OR_BASE_URL = "https://openrouter.ai/api/v1"
GEMINI_MODELS_DEFAULT = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-2.5-flash",
    "gemini-flash-latest",
]
OR_MODELS_DEFAULT = [
    "openrouter/free",
    "nvidia/nemotron-3.5-lightning:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "poolside/laguna-s-2.1:free",
]

_GO_COOLDOWN_SECONDS = 15 * 60
_go_blocked_until = 0.0
_go_healthy = True


def load_keys() -> dict:
    """brain_keys.json, re-read when the file changes (mtime-checked)."""
    mtime = None
    try:
        mtime = _KEYS_FILE.stat().st_mtime
    except OSError:
        pass
    if mtime != _keys_cache["mtime"]:
        try:
            _keys_cache["keys"] = json.loads(_KEYS_FILE.read_text("utf-8"))
        except Exception:
            _keys_cache["keys"] = {}
        _keys_cache["mtime"] = mtime
    return _keys_cache["keys"]


def global_set(name: str, value) -> None:
    """Module-global writer for the ladder loop (which cannot rebind a
    module global it is iterating inside - it can, but this is clearer)."""
    globals()[name] = value


def bench_go() -> None:
    """Bench the Go endpoint for the cooldown after a quota/auth failure."""
    global _go_blocked_until
    _go_blocked_until = time.time() + _GO_COOLDOWN_SECONDS
    # Master, 2026-09-20: self-review windows must never run on the free
    # fallbacks - he does not trust them to edit her code. The bench alone
    # lapses after 15 quiet minutes, which is NOT evidence that Go has
    # credit again, so health is tracked separately: False here, and back
    # to True only when a Go call actually succeeds.
    global _go_healthy
    _go_healthy = False


def go_primary(config: dict) -> bool:
    """True when the ladder's head is the OpenCode Go rung AND it is
    demonstrably healthy (keyed, and the last Go call was not a credit
    failure). The 4-hour self-review/research window runs only while this
    is true - see self_review.maybe_run."""
    keys = load_keys()
    go_key = config.get("api_key") or keys.get("open_code_key") or ""
    return bool(go_key) and _go_healthy


def _providers(config: dict, wants_vision: bool, *,
               free_only: bool = False) -> list[dict]:
    """The ladder for this call: [(base_url, key, model, label), ...].

    TWO ORDERS, and the difference is not tidiness - it is two providers with
    opposite strengths.

    A TEXT call: Go first (primary), then the Gemini key ladder (each key a
    separate quota bucket, so exhaustion on one does not touch the next), then
    OpenRouter's free models.

    A VISION call: Go+mimo FIRST, then the Gemini ladder, and OpenRouter not at
    all. Master, 2026-09-21: "actually change lulu to use opencode go mimo first
    for vision, the others are too unreliable". That supersedes the order he
    asked for earlier the same evening ("we should cycle through gemini for
    vision before finally usuing open code go mimo") - he has now watched the
    gemini rungs fail often enough that he does not want to lead with them.

      - Go is the endpoint configured with vision_model, so rung one is the
        model actually chosen for looking at pictures;
      - Gemini flash stays on the ladder behind it: natively multimodal, and
        each key is its own quota bucket, so it is a real second reader rather
        than a repeat of the same attempt;
      - and the OpenRouter ladder is free TEXT models by construction
        (_or_models, and _OR_DENYLIST drops image-capable ids), so a rung down
        there handed an image can only fail or INVENT one. A made-up
        description of a picture is the worst answer available, because it is
        indistinguishable from a real one - and she would believe it.

    So a vision call never descends into OpenRouter at all, whatever happens on
    the rungs above it.

    A provider with no key configured is skipped, so a missing brain_keys.json
    degrades to exactly the old behaviour.

    `free_only` drops the Go rung from the head of the ladder. That is the
    digests' rule - master, 2026-09-22: the journal summaries run on "gemini and
    openrouter free only", because they fire on a timer nobody is watching and
    no answer depends on them, so they must never be able to spend the rung he
    pays for. A PARAMETER rather than a second builder on purpose: two builders
    would drift, and the rung ORDER is the part that must not.
    """
    keys = load_keys()
    go: list[dict] = []
    gemini: list[dict] = []
    openrouter: list[dict] = []

    go_key = config.get("api_key") or keys.get("open_code_key") or ""
    if go_key and not free_only and time.time() >= _go_blocked_until:
        model = config.get("vision_model") if wants_vision else None
        go.append({"base_url": str(config["base_url"]).rstrip("/"),
                   "key": go_key,
                   "model": model or config["model"],
                   "label": "go"})

    gemini_key = keys.get("gemini_key") or ""
    if gemini_key:
        # Gemini flash is multimodal natively - the Go vision model belongs
        # to the Go endpoint only and is NOT carried up here.
        #
        # Free-tier quota is tracked per (key, MODEL) pair, so models and
        # keys are both ladders: every key gets a shot at every model, best
        # model first. Losing the newest model on one key only moves to the
        # next key on the SAME model before stepping down a generation.
        for model in _gemini_models(config):
            for index in range(1, 6):
                key = keys.get(f"gemini_key{index}") if index > 1 else gemini_key
                if key:
                    gemini.append({"base_url": GEMINI_BASE_URL, "key": key,
                                   "model": model,
                                   "label": f"{model}/key{index}"})

    # OpenRouter is built for a TEXT call only. See the docstring: its rungs are
    # free text models, so a vision call must not have them to descend into.
    if not wants_vision:
        or_key = keys.get("or_key") or ""
        if or_key:
            for model in _or_models(config, or_key):
                openrouter.append({"base_url": OR_BASE_URL, "key": or_key,
                                   "model": model, "label": f"or:{model}"})

    if wants_vision:
        # Go+mimo first, master's call - see the docstring. The gemini ladder is
        # still the backup, not a replacement.
        return go + gemini
    return go + gemini + openrouter


def _gemini_models(config: dict) -> list[str]:
    """Gemini rotation, best first. config -> gemini_models (list or
    comma-separated string) wins; a single gemini_model is one rung;
    otherwise GEMINI_MODELS_DEFAULT."""
    raw = config.get("gemini_models")
    if isinstance(raw, str):
        models = raw.split(",")
    elif isinstance(raw, list):
        models = raw
    else:
        one = config.get("gemini_model")
        models = [one] if one else list(GEMINI_MODELS_DEFAULT)
    models = [str(m).strip() for m in models if m and str(m).strip()]
    return models or list(GEMINI_MODELS_DEFAULT)


# ---------------------------------------------------------------------------
# OpenRouter free-model discovery.
#
# Like nyan's live ladder: on first use (and every TTL after) the live
# /models list is fetched, filtered to free CHAT models, ranked by context
# length, and cached. A fetch failure just keeps the curated default list,
# so a dead network never costs her a call - it only costs freshness.
# ---------------------------------------------------------------------------

_OR_FREE_TTL = 6 * 3600
_or_free_cache = {"ts": 0.0, "models": []}
_OR_DENYLIST = ("lyria", "clip", "content-safety", "embedding", "tts",
                "whisper", "transcribe", "veo", "image")


def _is_free(m: dict) -> bool:
    mid = m.get("id", "")
    pricing = m.get("pricing") or {}
    try:
        price = float(pricing.get("prompt") or 0)
    except (TypeError, ValueError):
        price = 0.0
    return mid.endswith(":free") or price == 0


_or_limits: dict[str, dict] = {}      # or model id -> context/max_output
_gemini_limits: dict[str, dict] = {}  # gemini model name -> context/max_output
_gemini_limits_ts = 0.0

GEMINI_MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _fetch_gemini_limits(gemini_key: str) -> None:
    """Model token limits from Google's v1beta models list.

    Limits are a property of the MODEL (not of the key), so one fetch per
    TTL covers every key in the ladder. Failures are silent: an absent
    entry just means no cap is applied for that model.
    """
    global _gemini_limits_ts
    try:
        request = urllib.request.Request(
            GEMINI_MODELS_URL + "?key=" + gemini_key,
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.load(response)
        for m in data.get("models", []):
            name = str(m.get("name", "")).removeprefix("models/")
            if not name or not name.startswith("gemini"):
                continue
            _gemini_limits[name] = {
                "context": int(m.get("inputTokenLimit") or 0),
                "max_output": int(m.get("outputTokenLimit") or 0),
            }
        _gemini_limits_ts = time.time()
    except Exception:
        _gemini_limits_ts = time.time()  # do not retry every single call


def model_limits(config: dict) -> dict:
    """Known token limits per model: {model: {context, max_output}}.

    Merges the Gemini and OpenRouter discoveries, refreshed at the same
    TTLs those fetches run on. Modules that size prompts or budgets
    against a model should read this instead of hardcoding numbers.
    """
    gemini_key = load_keys().get("gemini_key") or ""
    if gemini_key and time.time() - _gemini_limits_ts > _OR_FREE_TTL:
        _fetch_gemini_limits(gemini_key)
    out = dict(_gemini_limits)
    out.update(_or_limits)
    return out


def _or_models(config: dict, or_key: str) -> list[str]:
    """OpenRouter ladder: explicit config -> live free list -> defaults.

    The fetch runs even when config pins or_models: it is what fills
    _or_limits with each model's real context_length and whether it can
    call tools at all. Skipping it because the list is pinned left every
    pinned rung blind - context=None, tool support unknown - and a pinned
    list is exactly the case where she trusts the models enough to walk
    them, so those are the ones that most need measuring.
    """
    now = time.time()
    if now - _or_free_cache["ts"] > _OR_FREE_TTL:
        try:
            request = urllib.request.Request(
                f"{OR_BASE_URL}/models",
                headers={"Authorization": f"Bearer {or_key}",
                         "User-Agent": USER_AGENT},
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.load(response)
            ranked = []
            for m in data.get("data", []):
                mid = m.get("id", "")
                if (not mid or ":batch" in mid or not _is_free(m)
                        or any(bad in mid for bad in _OR_DENYLIST)):
                    continue
                out_mods = (m.get("architecture") or {}).get(
                    "output_modalities") or ["text"]
                if "text" not in out_mods:
                    continue
                ranked.append((int(m.get("context_length") or 0), mid))
                top = (m.get("top_provider") or {}).get(
                    "max_completion_tokens")
                sp = m.get("supported_parameters") or []
                _or_limits[mid] = {
                    "context": int(m.get("context_length") or 0),
                    "max_output": int(top) if isinstance(top, int) else None,
                    # Free models are not equal: gemma-class ones cannot call
                    # tools at all. A browsing turn that lands on one would
                    # break mid-loop, so record it and skip those rungs.
                    "tools": ("tools" in sp) or ("tool_choice" in sp)
                             or ("tool_use" in sp),
                }
            ranked.sort(reverse=True)
            models = [mid for _, mid in ranked]
            if models:
                _or_free_cache["models"] = models
                _or_free_cache["ts"] = now
        except Exception:
            # keep whatever cache we had; fall through to defaults below
            _or_free_cache["ts"] = now  # do not retry every single call
    return _or_free_cache["models"] or list(OR_MODELS_DEFAULT)

def _retired_error(code: int, detail: str) -> bool:
    """True when the failure is 'this model was taken away', not a bad shape.

    Google retires gemini flash models: the endpoint answers 404 with
    'This model models/... is no longer available'. That is a dead RUNG,
    not a bug in what we sent - the ladder has more models below it, so
    the right move is to strike the name and descend, exactly like a dry
    key. Reported to master as a note, because a model dying is news he
    wants even when the turn still succeeds on the next rung.
    """
    lowered = detail.lower()
    if code == 404 and ("no longer available" in lowered
                        or "not found" in lowered):
        return True
    # Master, 2026-09-21: some OpenRouter free models refuse EVERYONE who is
    # not an "agentic harness" with a 403. The rung is dead for her no matter
    # how many times it is tried, so it retires like a taken-away model.
    if code == 403 and ("only available on agentic" in lowered
                        or "agentic harness" in lowered):
        return True
    return False


# Models proven dead (retired by the provider) this session. A rung whose
# model is here is skipped without a round trip - the 404 already told us.
_dead_models: set[str] = set()

# Master, 2026-09-21: when the WHOLE ladder comes back dry (every rung out
# of quota), stop calling for twelve hours. Before this, one addressed turn
# walked the whole ladder up to twelve tool-loop rounds in a row and torched
# every free key it touched, and the next turn did it again.
_LADDER_DRY_SECONDS = 12 * 3600
_ladder_dry_until = 0.0

# Notes for master, drained by lulu_bot.flush_outbox and sent as owner DMs.
# brain.py has no Discord here, so it queues; the bot side drains.
_OWNER_NOTES: list[str] = []


def note_owner(text: str) -> None:
    """Queue one line for master's DMs. Never fatal, never blocking."""
    line = " ".join(str(text or "").split())
    if line and len(_OWNER_NOTES) < 20:
        _OWNER_NOTES.append(line)


def drain_owner_notes() -> list[str]:
    out = list(_OWNER_NOTES)
    _OWNER_NOTES.clear()
    return out


def _credit_error(code: int, detail: str) -> bool:
    """True when the failure is 'the money ran out', not 'the shape broke'."""
    lowered = detail.lower()
    return (code == 429
            or "usage limit" in lowered
            or "credit" in lowered
            or "quota" in lowered
            or "insufficient" in lowered)


def _busy_error(code: int, detail: str) -> bool:
    """True when the provider is alive but overloaded (503 'high demand',
    or a 429 that is rate-limiting rather than billing). These must NEVER
    reach her as printed refusals: the ladder has other rungs, so a busy
    rung just loses the turn's call to the next one quietly."""
    lowered = detail.lower()
    return (code == 503
            or (code == 429 and not _credit_error(code, detail))
            or "high demand" in lowered
            or "unavailable" in lowered
            or "temporarily" in lowered)


def _attempt(provider: dict, payload: dict, cache: bool,
             limits: dict | None = None,
             timeout: float | None = None) -> dict:
    """One round trip to one provider. Returns the raw assistant message.

    On a provider-level failure the returned dict carries "_credit" (true
    when it was a quota/credit error) and "_detail" so the caller can
    decide to descend the ladder.
    """
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "x-opencode-session": SESSION_ID,
        "Authorization": f"Bearer {provider['key']}",
    }
    body = dict(payload)
    body["model"] = provider["model"]
    limits = limits or {}
    if "max_tokens" in body:
        cap = (limits.get(provider["model"]) or {}).get("max_output")
        if isinstance(cap, int) and cap > 0:
            # Reasoning tokens are billed to the same budget, and the rungs
            # disagree (gemini 65536 vs a free OR model's 4096), so the cap
            # is per RUNG: a budget the model cannot honour is a 400
            # waiting to happen, while one above its ceiling is harmless.
            body["max_tokens"] = min(body["max_tokens"], cap)
    if cache and config_cache_ok(provider["base_url"]):
        body["messages"] = cache_breakpoints(body["messages"])

    request = urllib.request.Request(
        f"{provider['base_url']}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(
                request, timeout=timeout or TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if 400 <= exc.code < 500:
            _dump_rejected(body, exc.code, detail)
        if _credit_error(exc.code, detail):
            return {"_credit": True, "_detail": detail}
        if _busy_error(exc.code, detail):
            return {"_busy": True, "_detail": detail}
        if _retired_error(exc.code, detail):
            return {"_retired": True, "_detail": detail}
        return {"_error": f"[my brain refused: HTTP {exc.code}] {detail}"}
    except Exception as exc:  # network, DNS, timeout, bad JSON
        return {"_error": f"[my brain is unreachable: {type(exc).__name__}]"}

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return {"_error": f"[my brain answered in a shape I do not read: {str(data)[:200]}]"}
    if isinstance(message, dict):
        message["_usage"] = data.get("usage") or {}
        # Master, 2026-09-21: she was cutting off mid-sentence and nobody
        # could see why. finish_reason=length is the tell - the answer hit
        # max_tokens (gemini's hidden reasoning tokens are billed to the same
        # budget), so it is stamped here and logged where she replies.
        try:
            message["_finish"] = data["choices"][0].get("finish_reason")
        except (KeyError, IndexError, TypeError):
            pass
        # Which rung answered, so the caller (and the log, and the bill) can
        # see the model that ACTUALLY inferred - the ladder means it is often
        # not the config's model at all.
        message["_model"] = provider["model"]
        message["_rung"] = provider["label"]
    return message


def config_cache_ok(base_url: str) -> bool:
    """Prompt-cache breakpoints are opt-in and Go-shaped: only the endpoint
    config.json names may see the cache_control blocks, and only when
    brain.prompt_cache is set. A provider that does not know the field
    would answer a 400, so unknown endpoints get the plain payload.
    """
    return bool(_PROMPT_CACHE) and base_url == str(_BASE_URL).rstrip("/")


def cache_stats(usage: dict) -> dict:
    """What the provider reported about caching on this call, as numbers.

    Two spellings of the same fact exist in the wild and both are read: the
    OpenAI-style `prompt_tokens_details.cached_tokens`, and a flat
    `cache_read_input_tokens` / `prompt_cache_hit_tokens` at the top level.
    """
    usage = usage if isinstance(usage, dict) else {}
    prompt = usage.get("prompt_tokens")
    prompt = prompt if isinstance(prompt, int) else None
    cached = None
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        for key in ("cached_tokens", "cache_read", "cache_read_input_tokens"):
            value = details.get(key)
            if isinstance(value, int):
                cached = value
                break
    if cached is None:
        for key in ("cache_read_input_tokens", "prompt_cache_hit_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                cached = value
                break
    out = {"prompt": prompt, "cached": cached}
    if prompt:
        out["hit_percent"] = round(100.0 * (cached or 0) / prompt, 1)
    return out


def usage_note(usage: dict) -> str:
    """One line for the log: what this call cost and how much came from cache.

    The distinction this exists to keep: an endpoint that reports prompt_tokens
    but never a cached count is one we CANNOT measure, while one that reports
    cached: 0 is one we can, and which is simply not caching. Printing "0" for
    both would hide the difference between "no cache" and "no news", and those
    two need different fixes - so they are worded differently here.
    """
    usage = usage if isinstance(usage, dict) else {}
    stats = cache_stats(usage)
    if stats["prompt"] is None and stats["cached"] is None:
        return ""
    parts = []
    if stats["prompt"] is not None:
        parts.append(f"prompt={stats['prompt']}")
    if stats["cached"] is None:
        parts.append("cached=? (this endpoint reports no cache field)")
    else:
        parts.append(f"cached={stats['cached']}")
        if "hit_percent" in stats:
            parts.append(f"{stats['hit_percent']}% hit")
    completion = usage.get("completion_tokens")
    if isinstance(completion, int):
        parts.append(f"completion={completion}")
    return "usage: " + ", ".join(parts)


# Explicit prompt-cache breakpoints.
#
# MEASURED, not assumed, and the answer is "available, but not on demand".
# With no directive, the same prompt sent twice in one session reported
# cached_tokens 0 both times: automatic prefix caching is not on. With one
# Anthropic-style breakpoint, the next identical call reported cached_tokens
# 4352 - 96% of it - so the mechanism is real and this endpoint does accept it.
#
# But it does not fire when asked to. Across the 14 calls that followed: five
# identical calls 3s apart -> 0 every time; a write then a read 45s later -> 0;
# three identical calls with NO gap -> 0, 4352, 0. One hit, transient, in a
# narrow window, and the latency never changed (1.1-1.9s throughout), so a hit
# does not even read as a faster call. The marked payload measured the SAME
# prompt_tokens as the plain one (4543 both), which is the only reason leaving
# this on is free: take any hit as a bonus, and never budget for one.
#
# OFF unless config.json -> brain.prompt_cache is set. This file is deliberately
# provider-agnostic - a local llama.cpp server, or anything else OpenAI-shaped,
# "works without touching this file" - and a content-block payload carrying a
# field it does not know is exactly the shape such an endpoint answers with a
# 400. Opt-in keeps that promise, and opt-in costs one key.
#
# Two breakpoints, both on STRING content only:
#   - the FIRST message, which is the always-loaded skill and does not change
#     between turns, so it is reused turn to turn;
#   - the LAST message, so each round of the tool loop caches the prefix it just
#     sent and the next round reads it back. That is the one worth the most: the
#     loop resends everything, up to twelve times a turn.
# A message whose content is already a list of blocks - the vision parts - is
# left alone rather than guessed at.
def cache_breakpoints(messages: list[dict]) -> list[dict]:
    """A COPY of `messages` with cache breakpoints marking the stable prefix.

    Never mutates the caller's list. `turns` is reused every round and then
    becomes the prompt, so a marker written into it would accumulate, and the
    history she keeps would fill up with cache instructions nobody asked for.
    """
    if not messages:
        return messages
    first, last = 0, len(messages) - 1
    out = []
    for index, message in enumerate(messages):
        content = message.get("content") if isinstance(message, dict) else None
        if index in (first, last) and isinstance(content, str) and content:
            marked = dict(message)
            marked["content"] = [{"type": "text", "text": content,
                                  "cache_control": {"type": "ephemeral"}}]
            out.append(marked)
        else:
            out.append(message)
    return out


def _own_time_turn() -> bool:
    """True when this call belongs to her own time - the free-time window.

    Master, 2026-09-21: the ladder descends on a failure everywhere EXCEPT where
    the answer is code she will keep, because there a substitute model is worse
    than an error - a patch to her own body that reads fine is indistinguishable
    from one that is right.

    That is not only self-repair. Master, 2026-09-21: "site work is part of free
    time" - and free time IS this one window (self_review.maybe_run), so a turn
    spent building on her own site is already covered here. It is named for the
    WINDOW rather than for patching, because naming it after self-repair is how
    I talked myself into thinking site work was uncovered when it never was.

    `origin` is the only honest signal, and only a caller of tools.set_context
    can write it (self_review.py sets "self-review" for the whole window, and
    nothing the model emits can claim that name). brain does NOT import tools at
    module level - tools imports vision, vision imports brain - so this is
    deferred, and the broad except is the safe direction: no context at all
    means an ordinary turn, and an ordinary turn is the one that descends.
    """
    try:
        import tools
        return str(tools._ctx().get("origin") or "") == "self-review"
    except Exception:
        return False


def complete(config: dict, messages: list[dict], tools: list | None = None,
             max_tokens: int | None = None,
             timeout: float | None = None) -> dict:
    """One round trip. Returns the raw assistant message, tool_calls included.

    `max_tokens` overrides the configured value for this call. A falsy value (0)
    OMITS the field entirely and leaves the ceiling to the provider - that is
    what "no limit" means on the wire. Absent the argument, the config value is
    used, exactly as before.

    `timeout` caps the HTTP read for this call, in seconds. There is NO
    turn-wide deadline any more - master, 2026-09-22, replaced it with a
    per-call budget - so the turn loop hands down the FULL fifteen minutes
    (its TOOL_CALL_DEADLINE_SECONDS) fresh on every round, never the remainder
    of anything. A turn that keeps making progress has no clock on it; what
    ends a turn is a round count, the purse, master's stop word, or a newer
    message from him. None here means the usual TIMEOUT_SECONDS, which is only
    the fallback for a caller that never heard of the budget.

    Worth knowing when you set it: reasoning tokens are billed to this same
    budget, so a thinking model can spend the whole allowance before it writes a
    word of the answer.

    Since 2026-09-20 this walks the key ladder in _providers(): OpenCode Go
    first, then the Gemini key ladder, then OpenRouter free models. A
    credit/quota error descends the ladder (and benches Go for a while);
    anything else is reported as before, because it is a bug in what WE
    sent, not the provider's bill.
    """
    global _PROMPT_CACHE, _BASE_URL, _ladder_dry_until
    _PROMPT_CACHE = bool(config.get("prompt_cache"))
    _BASE_URL = str(config["base_url"]).rstrip("/")

    # Images in the prompt need a brain that can actually see. The default
    # model may be text-only and would silently ignore the pixels, so any call
    # carrying an image part is routed to vision_model when one is configured.
    wants_vision = any(
        isinstance(m.get("content"), list)
        and any(isinstance(b, dict) and b.get("type") == "image_url"
                for b in m["content"])
        for m in messages
    ) and bool(config.get("vision_model"))

    payload = {
        "messages": messages,
        "temperature": config.get("temperature", 0.9),
    }
    budget = config.get("max_tokens", 400) if max_tokens is None else max_tokens
    if budget:
        payload["max_tokens"] = budget
    if tools:
        payload["tools"] = tools

    if time.time() < _ladder_dry_until:
        # The whole ladder went dry and master said to wait 12 hours: answer
        # from the floor without a single round trip. Anything REAL he says
        # still lands here as a printed line, but no quota gets hammered.
        return {"content": "[my brains are all dry for now - I am waiting out "
                           "the twelve hour back off before I knock again]"}

    providers = _providers(config, wants_vision)
    if not providers:
        return {"content": "[no key: put the keys in brain_keys.json beside lulu_bot.py]"}

    limits = model_limits(config)
    last_busy = False
    # Which failures descend the ladder, and which stop it dead.
    #
    # A VISION call always descends. Master, 2026-09-21: "vision models should
    # always go down until we tried all of them then give up" - a dead socket on
    # the first gemini key is no verdict on the rungs below it, least of all the
    # one built to look.
    #
    # A TEXT call descends too, unless the turn is her own time. Master,
    # 2026-09-21: "text shouldnt hard stop, we should try every model if the
    # first one doesnt work, unless we are doing web development or self repair
    # task" - and "site work is part of free time", which is the window
    # _own_time_turn already covers.
    stubborn = not wants_vision and _own_time_turn()
    failed: list[str] = []
    first_failure = ""
    for provider in providers:
        if tools and provider["label"].startswith("or:") \
                and (limits.get(provider["model"]) or {}).get("tools") is False:
            continue  # this free model cannot call tools: skip to the next rung
        if provider["model"] in _dead_models:
            continue  # a model the provider retired: no round trip wasted
        if provider["label"] != "go" and "max_tokens" in payload:
            # Master's standing intent, restored (2026-09-21: "we set it to
            # max on free models"): the fallback rungs get the model's OWN
            # ceiling, not her Go voice budget. A thinking gemini burning a
            # 400-token budget on hidden reasoning was cutting her answers
            # off mid-sentence. _attempt still min()s against the model's
            # real max_output cap, so this cannot overrun anything.
            rung_payload = dict(payload)
            del rung_payload["max_tokens"]
        else:
            rung_payload = payload
        result = _attempt(provider, rung_payload, cache=_PROMPT_CACHE,
                          limits=limits, timeout=timeout)
        if "_credit" in result:
            if provider["label"] == "go":
                bench_go()
            continue  # a dry rung: descend the ladder
        if "_busy" in result:
            last_busy = True
            continue  # an overloaded rung: descend QUIETLY, no printed error
        if "_retired" in result:
            # A taken-away model (404 'no longer available'). Strike it for
            # the session, tell master once, and keep descending - this is
            # a dead rung, not a bug in what we sent.
            if provider["model"] not in _dead_models:
                _dead_models.add(provider["model"])
                note_owner('my brain ladder dropped a model: '
                           + provider['model'] + ' is gone from its provider '
                           + '(HTTP 404), moving down the ladder ['
                           + provider['label'] + ']')
            continue
        if "_error" in result:
            if stubborn:
                # Her own time, where the first failure IS the verdict. A shape
                # error here is our bug and a fallback rung would only send it
                # again - or patch her with it, which is worse. Master,
                # 2026-09-21: the RAW error never goes to a public room any
                # more - the room gets a vague line, he gets the detail in a DM.
                note_owner('my brain refused on [' + provider['label'] + ']: '
                           + result['_error'])
                return {"content": "[my brain stumbled - master knows]"}
            # Not a verdict on the rungs below: the floor of a picture call is
            # the model built to look, and on any other turn the rung under this
            # one may answer fine. The raw error never goes to a public room, so
            # the detail is held for the ONE dm sent after the last rung rather
            # than printed once per rung.
            failed.append(provider["label"])
            if not first_failure:
                first_failure = str(result["_error"])[:200]
            continue
        if provider["label"] == "go":
            # A real Go answer is the only evidence that matters: health
            # comes back and the ladder head is trusted again.
            global_set("_go_healthy", True)
        return result

    if failed:
        # Every rung was asked and none of them answered. Reported ONCE, with the
        # rungs named, so the note says WHERE it died rather than just that it
        # did. This sits ABOVE the dry branch below deliberately: a dropped
        # socket is not a quota verdict and must not buy the whole ladder a
        # twelve hour silence.
        note_owner('every rung I could ask failed - asked ' + str(len(failed))
                   + ': ' + ', '.join(failed) + '; first failure: '
                   + first_failure)
        if wants_vision:
            # "I could not get a look" is the honest line for a picture, and the
            # floor rung is the one built to look.
            return {"content": "[I could not get a look at that - nothing that "
                               "reads pictures answered me. master knows]"}
        return {"content": "[nothing that thinks answered me just now - "
                           "master knows]"}

    if last_busy:
        return {"content": "[all my brains are busy right now - try me again in a minute]"}
    # Every rung answered "no money". Master, 2026-09-21: wait TWELVE HOURS
    # before knocking again, so one turn cannot keep burning through keys.
    # He hears this once, in his DMs, not once per round.
    _ladder_dry_until = time.time() + _LADDER_DRY_SECONDS
    note_owner('every brain I have is out of quota - I am backing off for '
               '12 hours and will stop hammering the keys until then '
               '(Gemini windows reset on their own; Go resets on its weekly '
               'clock)')
    # Master, 2026-09-21: the dry-ladder line used to name him and his
    # credits in public rooms. Errors live in his DMs only now.
    return {"content": "[my brains are all dry right now - master knows]"}



def _dump_rejected(payload: dict, code: int, detail: str) -> None:
    """Write a provider-rejected payload to logs/, for reading after the fact.

    Truncated so one enormous tool result cannot fill the disk, and never
    contains the API key - that lives only in the request headers, which are
    not dumped. Failing to write this must never affect the reply.
    """
    try:
        from datetime import datetime
        from pathlib import Path
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        folder = Path(__file__).resolve().parent / "logs"
        folder.mkdir(parents=True, exist_ok=True)
        body = json.dumps(
            {"code": code, "detail": detail,
             "model": payload.get("model"),
             "max_tokens": payload.get("max_tokens"),
             "tool_names": [t.get("function", {}).get("name")
                            for t in (payload.get("tools") or [])],
             "messages": payload.get("messages")},
            indent=2, ensure_ascii=False)[:200000]
        (folder / f"brain-rejected-{stamp}.json").write_text(body, encoding="utf-8")
    except Exception:
        pass


def reply(config: dict, messages: list[dict]) -> str:
    """Plain text answer, no tools."""
    return (complete(config, messages).get("content") or "").strip()


def free_complete(config: dict, messages: list[dict], *,
                  max_tokens: int = 0,
                  temperature: float | None = None,
                  timeout: float | None = None,
                  tries: int = 1) -> str:
    """One TEXT call on the FREE rungs only - never the Go rung master pays for.

    Gemini's keys first (every key gets a shot at every model, best model first,
    because free-tier quota is tracked per (key, model) pair so a dry key only
    moves to the next key on the SAME model), then OpenRouter's free models.

    For bulk work that is not worth a paid rung. The server digests are the
    first caller: they run on a timer whether or not anyone is watching, and
    nobody's answer depends on them - so they must never be able to spend the
    Go rung. Master, 2026-09-22: "use the gemini keys for this it's not very
    important, it can loop until complete", then "all gemini and openrouter free
    only, which continues to retry models every 5 minutes until success".

    THE RETRY THAT MATTERS IS THE CALLER'S, not `tries`. A pass that comes back
    empty must not advance the digest watermark, so the poll returns in
    POLL_SECONDS and walks the whole free ladder again - five minutes later,
    forever, until the window is summarised. `tries` only sweeps the ladder that
    many times back to back, for a rung that answers on a second sweep.

    Returns the answer text, or "" when every rung is dry or broken. An empty
    string is a real answer here - the caller decides whether to try again.
    """
    providers = _providers(config, False, free_only=True)
    if not providers:
        return ""
    # model_limits() carries the OpenRouter max_output caps as well as Gemini's,
    # so an OR rung is capped at its own ceiling instead of being handed a
    # budget it cannot honour (a 400 waiting to happen - see _attempt).
    limits = model_limits(config)

    payload: dict = {
        "messages": messages,
        "temperature": (config.get("temperature", 0.9)
                        if temperature is None else temperature),
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    for _ in range(max(1, int(tries))):
        for provider in providers:
            if provider["model"] in _dead_models:
                continue  # a model the provider retired: no round trip wasted
            result = _attempt(provider, payload, cache=False,
                              limits=limits, timeout=timeout)
            # A dry or busy rung is the ladder working: move to the next
            # key/model pair rather than giving up on the call.
            if result.get("_credit") or result.get("_busy"):
                continue
            if result.get("_error"):
                continue
            content = (result.get("content") or "").strip()
            if content:
                return content
    return ""


# The old name, kept because tests/smoke_test.py's MODULE_API still asserts it
# exists and because digest.py called it for months. The WALK changed, so the
# name stopped being true: it is no longer Gemini-only. New code says
# free_complete.
gemini_complete = free_complete