"""Run commands in her own folder.

Master asked for this in plain terms: "I want her to be able to run anything in
her own folder, like an actual windows user with no admin." So the verb allowlist
is GONE, and saying so is the honest move - keeping a fixed list on top of a
general runner would have been a boundary in appearance only, which is worse than
no boundary because it reads like one.

What actually bounds her now, in the order it matters:

  1. THE ACCOUNT. She runs as `lulu-bot`, a standard local user, and is not in
     Administrators. Nothing here can elevate: an unelevated process cannot
     answer a UAC prompt, and the task that starts her runs at RunLevel Limited.
     That is the real containment, and it is why "no admin" is the load-bearing
     half of what was asked for.
  2. cwd is pinned to her folder and cannot be set from the call.
  3. A hard timeout kills the whole process TREE, not just the shell.
  4. Output is capped and the cap is STATED, so a truncated answer cannot be
     mistaken for a complete one.
  5. Every command is appended to an audit log under logs/, which is SEALED
     against her tools - so the record of what she ran is not something she can
     quietly tidy up afterwards.

Known limits, written down instead of implied:

  - PATHS ARE NOT CONTAINED. This is a shell, so it can cd anywhere and use
    absolute paths. Nothing here stops `cd C:\\Windows`. What limits the damage
    is that she is not an administrator, not that she is kept in a folder.
  - `shell=True` IS DELIBERATE. A Windows user has pipes, redirection and `&&`,
    and a runner without them is not what was asked for. The cost is that the
    command is a string rather than an argv list, so it is read as a shell
    command by design.
  - THE AUDIT LOG IS NOT IMMUTABLE. runbox.py is her own code and pipeline-
    patchable, so she could in principle change what gets logged. That change
    would go through a git diff, the smoke test and a health gate - a review
    trail, not a wall. logs/ being sealed stops the tools restating the record;
    it cannot stop the runner being rewritten.
  - ONLY MASTER REACHES THIS. run_command is absent from LOOKUP_TOOL_NAMES, so a
    stranger's schema never contains it and run() refuses it anyway.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import paths

ROOT = paths.ROOT
LOGS = ROOT / "logs"

# Module-level and reassignable on purpose: the smoke test points it at a sandbox
# so a check never appends real audit lines. The same trick pipeline.ROOT uses,
# and for the same reason.
AUDIT = LOGS / "runbox.log"

# Long enough for a real install - a browser download is minutes - and short
# enough that a hung build does not hold her turn forever.
TIMEOUT = 900
MAX_OUTPUT = 8_000
KILL_TIMEOUT = 20

PY = sys.executable

# Convenience, NOT a boundary. These are the things she reaches for most, kept
# as named shortcuts so she does not have to spell them out. Anything not listed
# runs as an ordinary command, and deleting this whole dict would not narrow what
# she can do by one inch - which is exactly why it is not a security control and
# is not described as one.
SHORTCUTS: dict[str, str] = {
    "git_status": "git status --short --branch",
    "git_log": "git log --oneline -20",
    "git_diff": "git diff --stat",
    "smoke": f'"{PY}" tests/smoke_test.py',
}


def _audit(command: str, code: int | None, elapsed: float, note: str = "") -> None:
    """Append one line. Never let a logging failure cost her the result."""
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"exit={code} {elapsed:6.1f}s :: {command[:2000]}")
        if note:
            line += f"  [{note}]"
        with AUDIT.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def _cap(text: str) -> str:
    """Truncate, and say so. A silent cut reads as a complete answer."""
    if len(text) <= MAX_OUTPUT:
        return text
    return (text[:MAX_OUTPUT]
            + f"\n... [truncated at {MAX_OUTPUT} chars; "
              f"{len(text) - MAX_OUTPUT} more not shown]")


def _kill_tree(pid: int) -> None:
    """taskkill /T, because communicate() only guarantees the direct child.

    Without /T a timed-out command leaves its children running after we have
    already reported a timeout, and then the box has stray processes nobody is
    tracking. Same lesson as the launcher, which needed /T for the same reason.
    """
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=KILL_TIMEOUT)
    except Exception:
        pass  # already gone, or never had the rights; nothing to add


def catalog() -> str:
    lines = [
        "I can run commands in my own folder, as a standard (non-admin) user.",
        "",
        "shortcuts (just the common ones, not a limit):",
    ]
    for name in sorted(SHORTCUTS):
        lines.append(f"  {name:<12} {SHORTCUTS[name]}")
    lines += [
        "",
        "anything else runs as-is, e.g. npm install, python -m venv .venv, "
        "npx playwright install chrome.",
        "cwd is always my folder. Long commands get killed at "
        f"{TIMEOUT // 60} minutes. Output is capped at {MAX_OUTPUT} chars.",
    ]
    return "\n".join(lines)


def run(command: str = "") -> str:
    """Run one shell command in her folder. Returns text; never raises."""
    command = (command or "").strip()
    if not command:
        return catalog()

    resolved = SHORTCUTS.get(command, command)
    started = time.time()

    try:
        proc = subprocess.Popen(
            resolved,
            cwd=str(ROOT),
            shell=True,                 # deliberate: see the module docstring
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # one stream, so a failure is not hidden
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        _audit(resolved, None, 0.0, f"spawn failed: {exc}")
        return f"could not start {resolved!r}: {exc}"

    try:
        out, _ = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        elapsed = time.time() - started
        _audit(resolved, None, elapsed, "TIMEOUT - tree killed")
        return (f"$ {resolved}\n"
                f"timed out after {TIMEOUT}s and the process tree was killed. "
                f"Nothing partial is returned, because half an answer from a "
                f"killed run reads like a real one.")

    elapsed = time.time() - started
    _audit(resolved, proc.returncode, elapsed)

    out = (out or "").strip()
    head = f"$ {resolved}   (exit {proc.returncode}, {elapsed:.1f}s)"
    if not out:
        return head + "\n(no output)"
    return head + "\n" + _cap(out)
