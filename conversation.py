"""The running conversation inside one long job.

A window of her own time and a long task are the SAME shape of problem: a job
that takes several turns, driven one turn at a time, each turn handed a fresh
message list. Master, 2026-09-23: *"like how you take multiple turns to do
something it should be the same for her."*

So both keep a THREAD - the conversation so far - carried from turn to turn and
stored with the job, so it survives a restart. This module is the one home for
reading it and bounding it, because two copies of that rule is how two versions
of it start.

**What is deliberately NOT in the thread: tool calls and tool output.** Only what
was SAID goes back in - the brief, the openers, her own answers. Two reasons, and
both matter. The thread stays about the job instead of filling up with raw
output it would then carry forever; and a caller that reads the turn list to see
whether she actually worked (`taskmode._tools_used`, which the "am I circling?"
stop depends on) cannot be fooled by what she did hours ago.
"""
from __future__ import annotations

# The thread rides into the model on every remaining turn of the job, so it
# cannot grow without a limit. Bounding is by whole exchanges: the oldest go
# first, so an old turn fades out while the opening brief - which is message[0],
# and where the rules live - stays.
MAX_CHARS = 120_000

# Only these reach a provider. Anything else in the stored thread is garbage
# from a half-written state file and is dropped rather than sent.
_ROLES = ("system", "user", "assistant")


def read(holder) -> list[dict]:
    """The thread inside `holder`, as far as it can be trusted.

    Garbage counts as NO thread, deliberately: a job that cannot read its own
    thread opens with a fresh brief rather than half a conversation. A missing
    thread and a corrupt one have the same safe answer.
    """
    raw = holder.get("thread") if isinstance(holder, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if item.get("role") not in _ROLES:
            continue
        if not isinstance(item.get("content"), str):
            continue
        out.append({"role": item["role"], "content": item["content"]})
    return out


def trim(thread: list[dict], max_chars: int = MAX_CHARS) -> list[dict]:
    """Keep the opening brief and the most recent exchanges.

    message[0] is the brief the job opened with and is NEVER dropped - that is
    where the rules were given. The oldest exchanges go first. What is left
    always resumes on a USER turn, so the thread can never begin with an answer
    to a question that is no longer there.
    """
    total = sum(len(m["content"]) for m in thread)
    while total > max_chars and len(thread) > 2:
        total -= len(thread.pop(1)["content"])
    while len(thread) > 1 and thread[1]["role"] != "user":
        thread.pop(1)
    return thread
