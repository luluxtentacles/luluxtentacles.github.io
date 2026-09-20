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
GEMINI_MODEL_DEFAULT = "gemini-flash-latest"
OR_MODELS_DEFAULT = [
    "openrouter/free",
    "nvidia/nemotron-3.5-lightning:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "poolside/laguna-s-2.1:free",
]

_GO_COOLDOWN_SECONDS = 15 * 60
_go_blocked_until = 0.0


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


def bench_go() -> None:
    """Bench the Go endpoint for the cooldown after a quota/auth failure."""
    global _go_blocked_until
    _go_blocked_until = time.time() + _GO_COOLDOWN_SECONDS


def _providers(config: dict, wants_vision: bool) -> list[dict]:
    """The ladder for this call: [(base_url, key, model, label), ...].

    Order is Go first (primary), then the Gemini key ladder (each key a
    separate quota bucket, so exhaustion on one does not touch the next),
    then OpenRouter. A provider with no key configured is skipped, so a
    missing brain_keys.json degrades to exactly the old behaviour.
    """
    keys = load_keys()
    out = []

    go_key = config.get("api_key") or keys.get("open_code_key") or ""
    if go_key and time.time() >= _go_blocked_until:
        model = config.get("vision_model") if wants_vision else None
        out.append({"base_url": str(config["base_url"]).rstrip("/"),
                    "key": go_key,
                    "model": model or config["model"],
                    "label": "go"})

    gemini_key = keys.get("gemini_key") or ""
    if gemini_key:
        # Gemini flash is multimodal natively - the Go vision model belongs
        # to the Go endpoint only and is NOT carried down the ladder.
        model = config.get("gemini_model") or GEMINI_MODEL_DEFAULT
        for index in range(1, 6):
            key = keys.get(f"gemini_key{index}") if index > 1 else gemini_key
            if key:
                out.append({"base_url": GEMINI_BASE_URL, "key": key,
                            "model": model, "label": f"gemini_key{index}"})

    or_key = keys.get("or_key") or ""
    if or_key:
        models = config.get("or_models") or OR_MODELS_DEFAULT
        for model in models:
            out.append({"base_url": OR_BASE_URL, "key": or_key,
                        "model": model, "label": f"or:{model}"})
    return out


def _credit_error(code: int, detail: str) -> bool:
    """True when the failure is 'the money ran out', not 'the shape broke'."""
    lowered = detail.lower()
    return (code == 429
            or "usage limit" in lowered
            or "credit" in lowered
            or "quota" in lowered
            or "insufficient" in lowered)


def _attempt(provider: dict, payload: dict, cache: bool) -> dict:
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
    if cache and config_cache_ok(provider["base_url"]):
        body["messages"] = cache_breakpoints(body["messages"])

    request = urllib.request.Request(
        f"{provider['base_url']}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if 400 <= exc.code < 500:
            _dump_rejected(body, exc.code, detail)
        if _credit_error(exc.code, detail):
            return {"_credit": True, "_detail": detail}
        return {"_error": f"[my brain refused: HTTP {exc.code}] {detail}"}
    except Exception as exc:  # network, DNS, timeout, bad JSON
        return {"_error": f"[my brain is unreachable: {type(exc).__name__}]"}

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return {"_error": f"[my brain answered in a shape I do not read: {str(data)[:200]}]"}
    if isinstance(message, dict):
        message["_usage"] = data.get("usage") or {}
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


def complete(config: dict, messages: list[dict], tools: list | None = None,
             max_tokens: int | None = None) -> dict:
    """One round trip. Returns the raw assistant message, tool_calls included.

    `max_tokens` overrides the configured value for this call. A falsy value (0)
    OMITS the field entirely and leaves the ceiling to the provider - that is
    what "no limit" means on the wire. Absent the argument, the config value is
    used, exactly as before.

    Worth knowing when you set it: reasoning tokens are billed to this same
    budget, so a thinking model can spend the whole allowance before it writes a
    word of the answer.

    Since 2026-09-20 this walks the key ladder in _providers(): OpenCode Go
    first, then the Gemini key ladder, then OpenRouter free models. A
    credit/quota error descends the ladder (and benches Go for a while);
    anything else is reported as before, because it is a bug in what WE
    sent, not the provider's bill.
    """
    global _PROMPT_CACHE, _BASE_URL
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

    providers = _providers(config, wants_vision)
    if not providers:
        return {"content": "[no key: put the keys in brain_keys.json beside lulu_bot.py]"}

    for provider in providers:
        result = _attempt(provider, payload, cache=_PROMPT_CACHE)
        if "_credit" in result:
            if provider["label"] == "go":
                bench_go()
            continue  # descend the ladder
        if "_error" in result:
            return {"content": result["_error"]}
        return result

    return {"content": "Tentacles burned all my credits again :("}



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