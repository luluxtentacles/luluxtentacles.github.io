"""The supervisor - the least clever file in the folder, on purpose.

She cannot restart herself. Killing her own process is the last thing she can
do, and something outside has to bring her back, so that something lives here.

It is a loop with exit codes. No LLM, no judgement, no tools, no network. A
second agent watching the first would add an injection surface and prove
nothing; this file can be read in one sitting, which is the whole point.

What it does, in order:
    1. start her, wait
    2. if she closed because a patch was staged, run the pipeline on it
    3. a patch that fails the smoke test is reverted and never reaches a restart
    4. a patch that passes still has to COME UP - a fresh health marker - or it
       is reverted too
    5. start her again on whichever code survived
    6. if she dies repeatedly in a short window, stop and leave a note instead
       of spinning forever

The scheduled task already calls setup/run-bot.cmd, so pointing that script
here is the entire deployment: no task re-registration, no admin, no UAC.

    python supervisor.py            # supervise until stopped
    python supervisor.py --once     # one run, no restart (debugging)
    python supervisor.py --check    # report, change nothing
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import deque

import pipeline

# How long a patched bot gets to write a fresh health marker. She needs a few
# seconds to log in; this is generous on purpose, because a timeout here
# reverts a patch that might have been fine.
HEALTH_TIMEOUT = 120
# How long she gets to close herself after a restart request before we stop
# being polite about it.
GRACE_SECONDS = 30
POLL_SECONDS = 2
# Crash-loop breaker: this many starts inside this window means something is
# wrong with the box or the code, and restarting faster will not fix it.
RAPID_MAX = 5
RAPID_WINDOW = 600


# -- why she is being started ---------------------------------------------
#
# The supervisor is the only thing that knows why a start is happening, so it is
# the only thing that can tell her. Written with pathlib rather than through
# paths.py on purpose: this process is not the bot, and memory/ is sealed against
# the BOT's writes precisely so a note from here cannot be forged or cleared by
# her. Read-only from her side, authoritative from this one.
#
# The sequence number is what stops a crash loop becoming a message per attempt:
# she announces a given start once, and compares this against her own record.
_reason_seq = 0


def write_reason(kind: str, detail: str = "", files=None, sha=None) -> None:
    """Record why the NEXT start is happening, for her to read as she boots."""
    global _reason_seq
    _reason_seq += 1
    body = {
        "seq": _reason_seq,
        "kind": kind,
        "why": str(detail or "")[:500],
        "files": list(files or []),
        "sha": sha,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        path = pipeline.ROOT / "memory" / "restart_reason.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=2), encoding="utf-8")
    except Exception as exc:
        pipeline.log(f"WARNING could not write the restart reason: {exc}")


def serve(require_health: bool, command: list[str] | None = None,
          on_healthy=None) -> tuple[bool, int, str | None]:
    """Start her, watch her, wait for the exit.

    Returns (healthy, exit_code, requested_why). `healthy` only means anything
    when require_health was set: it is True once the health marker moves.

    `command` exists so the loop and the health gate can be tested with a stub
    child instead of a live bot. Defaults to her, which is the only thing the
    real supervisor ever runs.

    `on_healthy` runs ONCE, at the moment the fresh marker is seen - NOT after
    she exits, and that distinction is the entire bug it exists to fix. This wait
    lasts as long as she stays up, so anything deferred until it returns acts on
    a report that can be minutes stale and on a staged directory that has moved
    on underneath it. On 2026-09-20 that is exactly how her next patch was filed
    as applied without ever reaching the file, and the request that would have
    applied it was deleted on the way out.

    A callback that raises must not cost her a healthy patch, so it is caught
    and logged; the caller keeps its own retry for after the exit.
    """
    marker_before = pipeline.marker_state()
    proc = subprocess.Popen(command or [sys.executable, "lulu_bot.py"],
                            cwd=str(pipeline.ROOT))
    pipeline.log(f"started her: pid {proc.pid}"
                 + (" (gating on the health marker)" if require_health else ""))

    deadline = time.time() + HEALTH_TIMEOUT if require_health else None
    healthy = False
    requested_at: float | None = None
    why: str | None = None

    while True:
        code = proc.poll()
        if code is not None:
            return healthy, code, why

        if require_health and not healthy:
            now = pipeline.marker_state()
            if now and now != marker_before:
                healthy = True
                pipeline.log("health: fresh marker - she came up")
                if on_healthy is not None:
                    try:
                        on_healthy()
                    except Exception as exc:
                        pipeline.log(f"WARNING health callback failed: {exc}")

        if pipeline.REQUEST.exists():
            request = pipeline.load_request() or {}
            why = str(request.get("why") or "restart requested")
            if requested_at is None:
                requested_at = time.time()
                files = request.get("files") or []
                pipeline.log(f"restart requested: {why}"
                             + (f" ({len(files)} file(s) staged)" if files else ""))
                pipeline.log("waiting for her to close on her own")
            elif time.time() - requested_at > GRACE_SECONDS:
                pipeline.log("she did not close; terminating so the patch can run")
                _stop(proc)
                return healthy, -9, why

        if deadline is not None and not healthy and time.time() > deadline:
            pipeline.log("health check TIMED OUT - no fresh marker, she is not up")
            _stop(proc)
            return False, -9, why

        time.sleep(POLL_SECONDS)


def _stop(proc: subprocess.Popen) -> None:
    """Ask, then insist. Never leave a child holding the log file."""
    try:
        proc.terminate()
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except Exception:
            pass
    except Exception as exc:
        pipeline.log(f"WARNING could not stop her cleanly: {exc}")


def main() -> int:
    once = "--once" in sys.argv
    if "--check" in sys.argv:
        request = pipeline.load_request()
        pipeline.log(f"check: request={'yes' if request else 'no'} "
                     f"health={'yes' if pipeline.marker_state() else 'no'}")
        return 0

    pipeline.log("supervisor up: she cannot restart herself, so I do it")
    starts: deque[float] = deque(maxlen=RAPID_MAX)

    # Why the NEXT start is happening. Seeded for a cold start and replaced by
    # whatever the previous iteration learned. Written BEFORE each serve(),
    # because she reads it while she boots - a reason recorded afterwards is a
    # reason she never sees.
    pending = ("startup", "the box came up and the supervisor started me")

    while True:
        starts.append(time.time())
        if len(starts) == RAPID_MAX and starts[-1] - starts[0] < RAPID_WINDOW:
            pipeline.log(f"LOCKOUT: {RAPID_MAX} starts inside {RAPID_WINDOW}s. "
                         f"Not restarting her again - read logs/bot.log, then start me.")
            return 3

        write_reason(*pending)

        # No patch is pending on a cold start, so this serve is NOT gated on
        # health - she is already running code that is known good. The health
        # gate exists only for code that was just applied.
        healthy, code, why = serve(require_health=False)

        if once:
            pipeline.log(f"once: she exited with {code}")
            return 0 if code == 0 else 1

        if pipeline.REQUEST.exists():
            request = pipeline.load_request() or {}
            why = str(request.get("why") or "restart requested")
            report = pipeline.process(why)
            outcome = report["outcome"]
            pipeline.log(f"pipeline outcome: {outcome}")

            if outcome == "applied":
                # The smoke test passed. Now she has to actually come up - and the
                # patch is FILED at the moment the marker goes fresh, not after she
                # eventually exits. Deferring it meant this branch could still be
                # holding a report from minutes ago when an unrelated later event
                # woke it: that is the accept() that ate her flush_outbox fix.
                pipeline.log(f"gating {', '.join(report['files'])} on a health check")
                write_reason("patch-applied", why, report.get("files"), report.get("sha"))
                healthy, code, _ = serve(require_health=True,
                                         on_healthy=lambda: pipeline.accept(report))
                if healthy:
                    # Belt, and cheap: accept() is idempotent for one report, so
                    # this only does anything if the callback itself failed.
                    pipeline.accept(report)
                    pending = ("running-new-code", why, report.get("files"),
                               report.get("sha"))
                else:
                    detail = ("no fresh health marker: she never came up on the new "
                              "code, so the supervisor reverted everything")
                    pipeline.reject_after_unhealthy(report, detail)
                    pipeline.log("reverted - starting her on the old code")
                    pending = ("patch-reverted", detail, None, None)
                continue

            if outcome == "reverted-smoke":
                pipeline.log("rejected before any restart; she keeps running the old code")
                pending = ("patch-reverted",
                           "the smoke test failed, so it was reverted before any restart",
                           report.get("files"), None)
                continue

            # restart-only / nothing-applied / noop: nothing staged that mattered
            pipeline.log("nothing to apply: plain restart")
            pending = ("restart-requested", why, None, None)
        else:
            # Nobody staged anything, so this start is because she stopped: died,
            # or shut down on her own. Different things, and until now she was
            # told neither - which is the boilerplate this replaces.
            if code not in (0, None):
                pending = ("crashed",
                           f"i exited with code {code} and no patch was pending",
                           None, None)
            else:
                pending = ("exited", f"i shut down cleanly (exit code {code})", None, None)

        pipeline.log(f"starting her again (last exit code {code}"
                     + (f", {why}" if why else "") + ")")


if __name__ == "__main__":
    # Without this guard `python supervisor.py` imports the module, defines
    # main(), and exits 0 - starting nothing, logging nothing, and reporting a
    # clean exit to the scheduler. That is exactly how she stayed down: the task
    # ran, python ran, and nothing happened. A supervisor that silently does
    # nothing is worse than one that crashes, so the smoke test now asserts
    # that a module which defines main() actually calls it.
    raise SystemExit(main())
