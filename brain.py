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
    base_url = str(config["base_url"]).rstrip("/")
    payload = {
        "model": config["model"],
        "messages": messages,
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
        "x-opencode-session": str(uuid.uuid4()),
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