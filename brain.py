"""The mouth.

One OpenAI-compatible chat endpoint, chosen entirely by config.json, so a
local llama.cpp server, OpenRouter, or anything else that speaks the same
shape all work without touching this file.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid

TIMEOUT_SECONDS = 120

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
    """
    # Images in the prompt need a brain that can actually see. The default
    # model may be text-only and would silently ignore the pixels, so any call
    # carrying an image part is routed to vision_model when one is configured.
    # Same endpoint, same key - the swap is the model field and nothing else.
    model = config["model"]
    if any(
        isinstance(m.get("content"), list)
        and any(isinstance(b, dict) and b.get("type") == "image_url"
                for b in m["content"])
        for m in messages
    ) and config.get("vision_model"):
        model = config["vision_model"]
    base_url = str(config["base_url"]).rstrip("/")
    payload = {
        "model": model,
        "messages": (cache_breakpoints(messages)
                     if config.get("prompt_cache") else messages),
        "temperature": config.get("temperature", 0.9),
    }
    budget = config.get("max_tokens", 400) if max_tokens is None else max_tokens
    if budget:
        payload["max_tokens"] = budget
    if tools:
        payload["tools"] = tools
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "x-opencode-session": SESSION_ID,
    }
    api_key = config.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        return {"content": "[no key: put one in brain_key.txt beside lulu_bot.py]"}

    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        # A 4xx here is the provider rejecting the SHAPE of what we sent, and the
        # message alone is not enough to fix it - "reasoning_content must be
        # passed back" does not say which message it means. Capture the exact
        # payload so the next occurrence can be read instead of guessed at.
        # The payload carries no credentials; the key lives in the headers and
        # headers are deliberately not dumped.
        if 400 <= exc.code < 500:
            _dump_rejected(payload, exc.code, detail)
        if exc.code == 429 or "usage limit" in detail.lower():
            return {"content": "Tentacles burned all my credits again :("}
        return {"content": f"[my brain refused: HTTP {exc.code}] {detail}"}
    except Exception as exc:  # network, DNS, timeout, bad JSON
        return {"content": f"[my brain is unreachable: {type(exc).__name__}]"}

    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return {"content": f"[my brain answered in a shape I do not read: {str(data)[:200]}]"}
    # What the provider says this call cost, kept BESIDE the message rather than
    # inside it: the message gets echoed back on the next hop, and a stray key in
    # there is a rejected request. Absent on some endpoints, which is why the
    # meter can price the text instead.
    if isinstance(message, dict):
        message["_usage"] = data.get("usage") or {}
    return message


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