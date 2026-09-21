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

import os
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
# Her other reader limit, and it cut real work: 8_000 chars is about a build log's
# first screen, so a command that printed the answer at the end looked like a
# command that printed nothing. Master's call 2026-09-20, with her read_file cap:
# normal agent function. 60s of timeout and 32KB of output still bound it.
MAX_OUTPUT = 32_000
KILL_TIMEOUT = 20

# THE STOP-AFTER-FIVE RULE. Master, 2026-09-21: "give her a rule that if she
# tries to run the same command 5 times and fail she should stop."
#
# He asked for a RULE, and this is one as a MECHANISM rather than a sentence in a
# prompt - a rule she can forget is not a rule. The same command failing
# FAIL_STREAK_LIMIT times in a row means the METHOD is wrong, so the next run is
# REFUSED instead of spent: re-running a broken command byte-identically cannot
# produce a different answer, and every retry is her own turn's time and master's
# tokens. It is the same discipline I hold myself to - three strikes means change
# method, ten means stop - installed here because she cannot see her own pattern
# from inside a single turn, where every attempt looks like the first.
#
# Keyed on the RESOLVED command, so a shortcut and the thing it expands to share
# one streak: re-typing `git_status` after `git status --short --branch` failed is
# the same attempt wearing a hat.
#
# Cleared by ANY command succeeding, and that is a deliberate choice with a real
# cost. Clearing only on the SAME command's success DEADLOCKS: once refused it can
# never run, so it can never succeed, so the streak can never clear - a permanent
# ban on a command that might work tomorrow. Master's rule is "five times in a
# row", and a success anywhere is what breaks a row. The price is that a
# deliberate `cd` between retries resets the count; a stuck agent does not
# interleave no-ops to dodge a rule, and a deadlocked one cannot recover at all.
FAIL_STREAK_LIMIT = 5
_FAIL_STREAK: dict[str, int] = {}

PY = sys.executable

# Her own interpreter and her own node, first on PATH for every command she runs.
#
# A bare `python` resolved to NOTHING for her: the machine PATH carries no Python
# at all (checked, not assumed), she is a standard local account, and `py` points
# at an install that is not the one she runs on. run-bot.cmd already solves this
# for node with `set "PATH=%CD%\node;%PATH%"` - Python was simply missed. Same
# reasoning as mcp_client.spawn_spec, and the same reason the launcher needed it:
# her shell must not depend on an environment the account may not have.
#
# Only folders that exist are added, so a missing runtime degrades to the old
# behaviour instead of pushing a dead entry to the front of PATH.
#
# Master, 2026-09-21: the interpreter moved OUT of her folder to C:\lulu-apps, so
# this points at the aliased path in paths.py rather than at ROOT/Python311. It is
# still a real folder on disk - `python` genuinely resolves for her because of
# this line, and PATH does not care that the folder is not under ROOT.
PATH_DIRS = (paths.PYTHON_HOME, ROOT / "node")


def child_env() -> dict:
    """What her commands inherit: her own runtimes first, then everything else."""
    env = dict(os.environ)
    front = [str(part) for part in PATH_DIRS if part.is_dir()]
    existing = env.get("PATH") or ""
    if front:
        env["PATH"] = os.pathsep.join(front + ([existing] if existing else []))
    # Same two settings the launcher uses, so a command of hers behaves the way
    # her own process does. setdefault, never overwrite: an explicit choice wins.
    env.setdefault("PYTHONUNBUFFERED", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env

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
    # The way she is SUPPOSED to look at her own site, as one word. Master,
    # 2026-09-22 - the wall's refusal now NAMES this shortcut, so the two have to
    # agree or the wall lies to her. 300s because that is the window she picked
    # herself the first time she used the mirror by hand, and it comfortably
    # covers resize -> navigate -> console -> screenshot -> look.
    "preview": f'"{PY}" preview.py --background --seconds 300',
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


def _note_streak(resolved: str, ok: bool) -> None:
    """One more failure against that command, or a clean slate. Never raises.

    A SUCCESS clears every streak, not only its own. The narrower version is a
    deadlock - see the note at FAIL_STREAK_LIMIT.
    """
    try:
        if ok:
            _FAIL_STREAK.clear()
        else:
            _FAIL_STREAK[resolved] = _FAIL_STREAK.get(resolved, 0) + 1
    except Exception:
        pass


def _cap(text: str, limit: int | None = None) -> str:
    """Truncate, and say so. A silent cut reads as a complete answer.

    `limit` is passed IN by the tool layer, because the right ceiling depends on
    the turn: master's own work gets SELF_WORK_MAX_CHARS, a room gets MAX_OUTPUT.
    runbox runs a subprocess and has no turn context of its own, so asking it to
    guess would mean either a wrong cap or a module that knows about rooms.
    None keeps MAX_OUTPUT, so every existing caller is unchanged.
    """
    cap = MAX_OUTPUT if limit is None else max(int(limit), 0)
    if len(text) <= cap:
        return text
    return (text[:cap]
            + f"\n... [truncated at {cap} chars; "
              f"{len(text) - cap} more not shown]")


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
        "a bare `python` and a bare `node` both work: my own are put first on "
        "PATH for anything I run, so I never have to hunt for the interpreter.",
        "cwd is always my folder. Long commands get killed at "
        f"{TIMEOUT // 60} minutes. Output is capped at {MAX_OUTPUT} chars.",
        f"if the SAME command fails {FAIL_STREAK_LIMIT} times in a row I stop "
        "running it and say so - a sixth identical try is not a new idea, it is "
        "the same one again. Change the command or the method instead.",
    ]
    return "\n".join(lines)


def run(command: str = "", max_output: int | None = None) -> str:
    """Run one shell command in her folder. Returns text; never raises.

    `max_output` is the caller's ceiling for this turn's output - see _cap. It
    exists so the self-improvement path (master's own work) can read a whole
    build log while a public room keeps the ordinary cap, without this module
    needing to know what a room is.
    """
    command = (command or "").strip()
    if not command:
        return catalog()

    resolved = SHORTCUTS.get(command, command)

    # The stop-after-five rule, checked BEFORE anything is spawned: the point is
    # not to pay for the sixth attempt at all.
    fails = _FAIL_STREAK.get(resolved, 0)
    if fails >= FAIL_STREAK_LIMIT:
        _audit(resolved, None, 0.0, f"REFUSED - already failed {fails}x")
        return (
            f"$ {resolved}\n"
            f"refused: this exact command has already failed {fails} times in a "
            f"row, so I am not running it again. Another identical try cannot "
            f"give a different answer - the METHOD is wrong, not the number of "
            f"tries.\n"
            f"Stop and change something: read the error, fix the argument or the "
            f"path, or take a different approach. Run something else, and this "
            f"streak clears the moment a command actually succeeds."
        )
    started = time.time()

    try:
        proc = subprocess.Popen(
            resolved,
            cwd=str(ROOT),
            env=child_env(),            # her python and node first on PATH
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
        _note_streak(resolved, False)
        return f"could not start {resolved!r}: {exc}"

    try:
        out, _ = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        elapsed = time.time() - started
        _audit(resolved, None, elapsed, "TIMEOUT - tree killed")
        _note_streak(resolved, False)
        return (f"$ {resolved}\n"
                f"timed out after {TIMEOUT}s and the process tree was killed. "
                f"Nothing partial is returned, because half an answer from a "
                f"killed run reads like a real one.")

    elapsed = time.time() - started
    _audit(resolved, proc.returncode, elapsed)
    _note_streak(resolved, proc.returncode == 0)

    out = (out or "").strip()
    head = f"$ {resolved}   (exit {proc.returncode}, {elapsed:.1f}s)"
    if not out:
        return head + "\n(no output)"
    return head + "\n" + _cap(out, max_output)
