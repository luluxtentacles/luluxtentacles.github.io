"""A bounded command runner. Not a shell, and not a step toward one.

Master asked for this, and the honest framing matters more than the code:

  * Her complaint was concrete - "the browser tool wants chrome installed and
    it's not there" - and she had to ask a human to type the fix.
  * She ALREADY has de facto arbitrary code execution. tools.py is proposable,
    so a patch to it runs in her process. This runner does not raise her risk
    class. What it buys is AUDITABILITY: a patch lands as a git diff somebody can
    read before it runs, and a command is one line in a log. Bounding it is for
    legibility, not for safety theatre.

Design rules, in the order they matter:

  1. NO model-supplied arguments exist. Every verb is a literal argv tuple and
     there is no parameter to inject into. A verb that takes an argument is a
     shell wearing a hat, so there are none: to get new behaviour, add a verb
     here, in a file that is proposable and therefore gets reviewed.
  2. No shell. The command is a list, never a string. There is nothing to quote
     for and nothing to escape, and shell=False is the default rather than a
     flag somebody could drop.
  3. cwd is pinned to the folder and cannot be set.
  4. Hard timeout, and the child TREE is killed. A verb that outlives its
     timeout while its children keep running would make the timeout a lie.
  5. Output is capped, and the cap is STATED in the result, so a big output
     reads as truncated instead of as the whole truth.

What this deliberately does NOT include: npx, npm, pip, any package runner or
installer. `npx <anything>` downloads and executes arbitrary packages, so a
verb for it is a shell with extra steps - which is the one thing this file
exists not to be. Installing chrome is a one-time job for master, not a standing
verb. See the note on VERBS below.
"""
from __future__ import annotations

import subprocess
import sys

import paths

ROOT = paths.ROOT

# A verb that hangs is worse than one that fails: it holds the turn open and
# nothing tells her why. Sixty seconds is generous for every verb listed.
TIMEOUT = 60
MAX_OUTPUT = 8_000
KILL_TIMEOUT = 20

# sys.executable rather than a literal path: this runs inside her own process, so
# it is already the interpreter she is running on. Hardcoding a second path here
# would be a second source of truth for something the process already knows, and
# the launcher has been bitten by exactly that before.
PY = sys.executable

# Every verb, as a literal argv. Read this as the whole of her authority.
#
# Deliberately read-only, all of it. Nothing here writes, installs, fetches or
# mutates: git's three read verbs and the smoke test. She can see her own state
# and check her own work, which is the 90% she was asking a human for. Anything
# that changes the box is still a patch, still reviewed, still revertible.
#
# `smoke` is safe to expose because tests/smoke_test.py already redirects every
# live path it could touch and sandboxes its own writes - it was built to be run
# by a live process, and the pipeline already runs it on every self-edit.
VERBS: dict[str, tuple[str, ...]] = {
    "git_status": ("git", "status", "--short", "--branch"),
    "git_log": ("git", "log", "--oneline", "-20"),
    "git_diff": ("git", "diff", "--stat"),
    "smoke": (PY, "tests/smoke_test.py"),
}


def _cap(text: str) -> str:
    """Truncate, and say so. A silent cut reads as a complete answer."""
    if len(text) <= MAX_OUTPUT:
        return text
    return (text[:MAX_OUTPUT]
            + f"\n... [truncated at {MAX_OUTPUT} chars; "
              f"{len(text) - MAX_OUTPUT} more not shown]")


def _kill_tree(pid: int) -> None:
    """taskkill /T, because communicate() only guarantees the direct child.

    Without /T a verb that spawned something leaves it running after we have
    already reported a timeout - and then the box has a stray process nobody is
    tracking. Same lesson as the launcher, which needed /T for the same reason.
    """
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=KILL_TIMEOUT)
    except Exception:
        pass  # already gone, or we never had the rights; nothing to add


def catalog() -> str:
    """What she may run. Printed on a bad verb so she can correct herself."""
    lines = ["verbs I may run (literal argv, no arguments, read-only):"]
    for name in sorted(VERBS):
        lines.append(f"  {name:<12} {' '.join(VERBS[name])}")
    lines.append("")
    lines.append("if you need something else, add a verb in runbox.py and "
                 "propose the patch - there is no free-form command.")
    return "\n".join(lines)


def run(verb: str = "") -> str:
    """Run one allowlisted verb. Returns text; never raises at the caller."""
    verb = (verb or "").strip()
    if not verb:
        return catalog()

    argv = VERBS.get(verb)
    if argv is None:
        return (f"there is no verb called {verb!r}, and there are no free-form "
                f"commands or arguments here.\n\n" + catalog())

    try:
        proc = subprocess.Popen(
            list(argv),
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,   # one stream, so a failure is not hidden
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        # Git as the boxed account hits 'dubious ownership' on C:\\lulu, and
        # anything else may simply not be on PATH for her. Name the likely cause
        # instead of returning a bare errno she cannot act on.
        return (f"{verb}: could not start {argv[0]!r} - not on PATH for me, or "
                f"not runnable by my account. Nothing was run.")

    try:
        out, _ = proc.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        _kill_tree(proc.pid)
        return (f"{verb}: timed out after {TIMEOUT}s and the process tree was "
                f"killed. Nothing partial is returned, because half an answer "
                f"from a killed run reads like a real one.")

    out = (out or "").strip()
    head = f"$ {' '.join(argv)}   (exit {proc.returncode})"
    if not out:
        return head + "\n(no output)"
    return head + "\n" + _cap(out)
