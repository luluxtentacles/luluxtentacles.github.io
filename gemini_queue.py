"""ONE queue for every background gemini request.

Master, 2026-09-25: "we should have 1 gemini queue to do all requests relating
to gemini ... 5 minutes a try". The free ladder is unreliable - a dry key, a
busy model, a whole ladder waiting out a backoff - so any job that only
matters eventually does not sit in a caller's loop hammering retries. It sits
HERE, and a drainer takes one job per poll, retrying on the standing
five-minute cadence until the job actually completes.

A job is {"kind", "who", "tries", "next_at"}. The drainer dispatches on
`kind`; new background work adds a kind and a branch, not a second queue.
Dedupe is (kind, who): asking twice for the same person's bio is one job.

Only the drainer pops. Callers enqueue and forget.
"""
from __future__ import annotations

import json
import time

import paths

QUEUE_REL = "memory/gemini_queue.json"
RETRY_SECONDS = 300.0


def _load() -> list:
    try:
        data = paths.read_json(QUEUE_REL, default=None)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _save(q: list) -> None:
    try:
        paths.write_text(QUEUE_REL, json.dumps(q), internal=True)
    except Exception:
        pass


def enqueue(kind: str, who: str) -> list:
    """Add (kind, who) to the queue unless it is already queued."""
    if not kind or not who:
        return _load()
    q = _load()
    if not any(j.get("kind") == kind and str(j.get("who")) == str(who)
               for j in q):
        q.append({"kind": str(kind), "who": str(who),
                  "tries": 0, "next_at": 0.0, "queued_at": time.time()})
        _save(q)
    return q


def due(now: float | None = None) -> dict | None:
    """The oldest job whose retry wait has elapsed, or None."""
    now = time.time() if now is None else now
    for job in _load():
        try:
            if float(job.get("next_at") or 0.0) <= now:
                return job
        except (TypeError, ValueError):
            return job
    return None


def done(who: str) -> None:
    """Remove a job - it finished."""
    q = [j for j in _load() if str(j.get("who")) != str(who)]
    _save(q)


def failed(who: str) -> None:
    """Put a job back at the END of the queue, retryable in RETRY_SECONDS.

    Tries count up forever on purpose: a job that matters eventually matters
    no matter how many tries it takes, and the five-minute spacing is what
    keeps the retries polite.
    """
    q = _load()
    for job in q:
        if str(job.get("who")) == str(who):
            job["tries"] = int(job.get("tries") or 0) + 1
            job["next_at"] = time.time() + RETRY_SECONDS
    _save(q)


def pending() -> int:
    """How many jobs are waiting - for the status line."""
    return len(_load())