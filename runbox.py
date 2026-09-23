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
  - THE SHELL IS bash, AND THAT CHANGED THE SYNTAX. Master's call, 2026-09-22:
    she reaches for `tail`, `grep`, `&&`, `for` loops and multi-line strings, and
    cmd does not speak that. It is Git's bash, run as an ARGV LIST
    (`[bash, -c, command]`) rather than through `shell=True`, because the
    comspec-string form splits on the space in "C:\Program Files" - measured,
    rc 127, a path chopped in half. The cost of the swap is that any command
    still written in CMD SYNTAX now means something else, or nothing: `&`
    BACKGROUNDS instead of sequencing, `>nul` writes a file literally called
    `nul`, and `type`/`del`/`copy` are gone (use `cat`/`rm`/`cp`). Written down
    here because it is the one way this change can bite her silently.
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
import re
import shutil
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

# THE STOP-AFTER-THREE RULE. Master, 2026-09-21: "give her a rule that if she
# tries to run the same command 5 times and fail she should stop." He tightened
# it to three on 2026-09-22 - the quote above is the original ask, and
# FAIL_STREAK_LIMIT below is the number that actually holds.
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
# ban on a command that might work tomorrow. Master's rule is "three times in a
# row" - tightened from five on his call, 2026-09-22 - and a success anywhere is
# what breaks a row. The price is that a
# deliberate `cd` between retries resets the count; a stuck agent does not
# interleave no-ops to dodge a rule, and a deadlocked one cannot recover at all.
FAIL_STREAK_LIMIT = 3
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

# Her shell: bash, from the Git install that already gives her git.
#
# Master, 2026-09-22: "we should give her bash." It buys more than a nicer
# grammar. cmd SILENTLY mangles a multi-line command - measured on master's own
# case, a two-line `python -c` returned exit 0 with NO output under cmd and
# prints its real answer under bash. The refusal this module used to carry
# existed to protect her from that, and bash removes the CAUSE rather than
# fencing off the symptom.
#
# Git's own bash BY EXPLICIT PATH, before any PATH lookup on purpose: a bare
# `bash` also resolves to the WSL stub in System32, which is a different
# machine's bash. The PATH lookup is the last resort, after these two.
BASH_PATHS = (
    Path(r"C:\Program Files\Git\bin\bash.exe"),
    Path(r"C:\Program Files\Git\usr\bin\bash.exe"),
)


def shell_argv(command: str) -> list[str] | None:
    """argv that runs `command` under bash, or None to fall back to cmd.

    ARGV, never `shell=True` with `executable=`: that form hands a comspec
    STRING to CreateProcess and the space in "C:\Program Files" splits it -
    measured, rc 127, "/c/Program: Files\\Git\\usr\\bin\\bash.exe: No such file
    or directory". An argv list has no such ambiguity, and it also hands the
    command to bash as `-c`'s SINGLE argument, so one layer of quoting stops
    mattering entirely.
    """
    for candidate in BASH_PATHS:
        if candidate.is_file():
            return [str(candidate), "-c", command]
    found = shutil.which("bash")
    if found:
        return [found, "-c", command]
    return None


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
    # The leash AGENTS.md demands for any git call that could turn
    # interactive: the box's gitconfig ships GCM, and a credential prompt is
    # indistinguishable from a freeze (measured 2026-09-21, 15 minutes). Her
    # own composed `... && git push` inherits these too now. setdefault, so an
    # explicit choice still wins.
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GCM_INTERACTIVE", "never")
    return env

# Convenience, NOT a boundary. These are the things she reaches for most, kept
# as named shortcuts so she does not have to spell them out. Anything not listed
# runs as an ordinary command, and deleting this whole dict would not narrow what
# she can do by one inch - which is exactly why it is not a security control and
# is not described as one.
# The script shortcuts resolve to ABSOLUTE paths on purpose: a shortcut can
# now be expanded after a `cd` (`cd projects/site && linkcheck`), and a
# relative path would then be read against the wrong folder - measured, exit 2,
# "can't open file ...\projects\site\linkcheck.py".
_PREVIEW = ROOT / "preview.py"
_LINKCHECK = ROOT / "linkcheck.py"
_SMOKE = ROOT / "tests" / "smoke_test.py"

SHORTCUTS: dict[str, str] = {
    "git_status": "git status --short --branch",
    "git_log": "git log --oneline -20",
    "git_diff": "git diff --stat",
    "smoke": f'"{PY}" "{_SMOKE}"',
    # The way she is SUPPOSED to look at her own site, as one word. Master,
    # 2026-09-22 - the wall's refusal now NAMES this shortcut, so the two have to
    # agree or the wall lies to her. 300s because that is the window she picked
    # herself the first time she used the mirror by hand, and it comfortably
    # covers resize -> navigate -> console -> screenshot -> look.
    "preview": f'"{PY}" "{_PREVIEW}" --background --seconds 300',
    # The other half of looking at her own site. `preview` shows her a page;
    # this says whether the links on it still resolve, which is the part she
    # cannot see at all - every restructure used to end in somebody opening
    # pages by hand. Master, 2026-09-22: *"a little crawler that walks
    # projects/site and reports broken internal links, because I hand-audit them
    # after every restructure and it's the same job every time."*
    "linkcheck": f'"{PY}" "{_LINKCHECK}"',
}

# A shortcut used to resolve only as the WHOLE command, and that gap was the
# most expensive defect on the board for days. She typed exactly what her own
# shelves teach her - `preview --seconds 120`, `git_status && ls projects/site`
# - and each one fell through to bash as a bare word: `command not found`,
# exit 127, and because it was the FIRST word of an `&&` chain, the real
# command after it never ran at all (five of these inside 90 minutes on
# 2026-09-23, logs/runbox.log). The fix is to expand a shortcut wherever a
# command can start: alone, with arguments, or as the first word of any
# segment of a composed command. A side effect the streak note already
# promised: `git_status && ls` and the spelled-out
# `git status --short --branch && ls` now produce the SAME resolved string,
# so they share one fail streak - see FAIL_STREAK_LIMIT.
_SEGMENT_RE = re.compile(r"(&&|\|\||;|\||\n)")
_SHORTCUT_KEYS = sorted(SHORTCUTS, key=len, reverse=True)


def resolve(command: str) -> str:
    """Expand shortcuts wherever they appear - alone, with args, mid-chain."""
    return "".join(_expand_segment(part) for part in _SEGMENT_RE.split(command))


def _expand_segment(part: str) -> str:
    """One segment's first word, if it is a shortcut, becomes what it runs.

    Splitting on the separators WITHOUT quote-awareness is safe for exactly
    one reason: a shortcut name inside a quoted string is always glued to the
    quote character (`"git_status was here`), so the segment's first word
    never compares equal to a key and passes through untouched.
    """
    body = part.lstrip()
    lead = part[:len(part) - len(body)]
    for key in _SHORTCUT_KEYS:
        rest = body[len(key):]
        if body == key:
            return lead + SHORTCUTS[key]
        if body.startswith(key) and rest[:1] in (" ", "\t"):
            expanded = SHORTCUTS[key] + rest
            if key == "preview" and "--seconds" in rest:
                # her window REPLACES the default 300s, it does not stack on
                # top of it (measured: `preview --seconds 120` produced
                # `--seconds 300 --seconds 120`, and which one wins is then
                # an argparse detail nobody should have to know).
                expanded = expanded.replace(" --seconds 300", "", 1)
            return lead + expanded
    return part


_NOT_FOUND_RE = re.compile(r"(\S+?): command not found")


def _not_found_hint(out: str) -> str:
    """The cure for a phantom command, printed with the phantom.

    Exit 127 means bash never found some word. The one case worth teaching
    every time: a script that lives in her own root - nothing puts her scripts
    on PATH, so `python <name>.py` is the door. Saying so converts every
    future phantom into its own answer, including ones nobody has imagined
    yet. Each exit 127 used to cost a whole turn; five landed on 09-23 alone.
    """
    found = _NOT_FOUND_RE.search(out or "")
    if not found:
        return ""
    word = found.group(1).strip("'\"")
    if (ROOT / f"{word}.py").is_file():
        return (f"hint: `{word}.py` is a script in my folder, but nothing "
                f"puts my scripts on PATH - run it as: python {word}.py")
    return ""


# A recursive search pointed PAST her folder is the other whole-turn burn:
# `grep -r resvg ../..` from projects/site swept the entire box, off-limits
# trees included, and came back 198 seconds later (2026-09-23 12:02). The
# guard refuses only the combination - recursion AND a way out - so
# `grep -rn foo projects/site` and `find . -name x` stay cheap and allowed.
# Narrow trigger on purpose: `ls -l ..` is innocent and stays innocent.
_RECURSIVE_TOOL_RE = re.compile(r"\bgrep\b|\bfind\b|\brg\b")
_RECURSIVE_FLAG_RE = re.compile(r"(?:^|\s)-{1,2}[a-zA-Z]*[rR][a-zA-Z]*\b|--recursive\b")
_UP_AND_OUT_RE = re.compile(r"(?<![\w.])\.\.(?![\w.])")
_ABSOLUTE_OUT_RE = re.compile(
    r"(?i)(?:^|[\s\"'=(])(?:[a-z]:[/\\]|/c(?:[/\s]|$)|~/)")
# cmd syntax that survives the shell swap: under bash `>nul` creates a file
# literally called `nul` (the unix shelf carries the whole table).
_NUL_REDIRECT_RE = re.compile(r"\d?>{1,2}\s*nul\b", re.IGNORECASE)

# `publish` is deliberately NOT in the dict above: it is the one shortcut that
# takes an argument - a free-text commit message - and a dict of exact command
# strings cannot carry one. `run()` routes it before the shell path.
#
# Master, 2026-09-22: after updating a website, always push. The mechanics are
# already in projects/README.md as four commands to remember in the right order,
# and a rule in a shelf is one she can forget inside the edit loop. This is that
# sequence with a name, so pushing is the path of least resistance instead of the
# step that gets skipped.
SITE_REPO = ROOT / "projects" / "site"
PUBLISH_TIMEOUT = 180          # a push needing longer than this is not slow, it
                               # is blocked - and blocked looks like a freeze
DEFAULT_PUBLISH_MESSAGE = "site update"


def _audit(command: str, code: int | None, elapsed: float, note: str = "") -> None:
    """Append one line. Never let a logging failure cost her the result."""
    try:
        AUDIT.parent.mkdir(parents=True, exist_ok=True)
        # ONE line whatever the command was: a multi-line command is a real
        # thing she can run now, and letting one through unfolded would turn a
        # single audit record into several and break the shape everything else
        # reads this file by. Collapsing whitespace costs nothing here - the
        # streak is keyed on the RAW command, not on this text.
        flat = " ".join(str(command).split())
        line = (f"{time.strftime('%Y-%m-%d %H:%M:%S')} "
                f"exit={code} {elapsed:6.1f}s :: {flat[:2000]}")
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


def _publish(message: str = "") -> str:
    """Commit everything in her site repo and push it - the one-word door out.

    Her own folder, her own repo, her own credential: this publishes to the
    public site, so it stops rather than guesses whenever a step does not clearly
    succeed. Nothing here is reversible from inside - a pushed commit is out.

    argv and shell=False on purpose: the commit message is free text, and a
    message containing a quote must never be able to become shell syntax.
    """
    site = SITE_REPO
    if not (site / ".git").exists():
        return f"publish: no git repo at {site} - nothing to push."

    env = child_env()
    # The leash AGENTS.md insists on for any interactive-capable git call. GCM
    # ships in the box's gitconfig, and left to itself it opens a sign-in window
    # and blocks, which is indistinguishable from a freeze.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"

    def git(*args: str, timeout: int = PUBLISH_TIMEOUT):
        return subprocess.run(
            ["git", "-C", str(site), *args],
            cwd=str(ROOT), env=env, shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )

    try:
        dirty = git("status", "--porcelain", timeout=60)
        if dirty.returncode != 0:
            return ("publish: could not read the repo, so nothing was pushed.\n"
                    + dirty.stdout.strip())
        if not dirty.stdout.strip():
            return "publish: nothing to publish - the working tree is already clean."

        git("add", "-A")
        staged = git("diff", "--cached", "--stat", timeout=60).stdout.strip()
        commit = git("commit", "-m", message or DEFAULT_PUBLISH_MESSAGE)
        if commit.returncode != 0:
            return ("publish: the commit did not go through, so nothing was "
                    "pushed.\n" + commit.stdout.strip())
        push = git("push")
    except subprocess.TimeoutExpired:
        return (f"publish: git did not finish inside {PUBLISH_TIMEOUT}s. Nothing "
                "partial is reported - check `git -C projects/site status` before "
                "trying again, because a push that did land cannot be un-pushed "
                "from here.")
    except Exception as exc:
        return f"publish: could not run git: {exc}"

    lines = [f"$ publish {message}".rstrip()]
    if staged:
        lines += ["staged:", staged]
    lines.append(commit.stdout.strip() or "(committed)")
    lines.append(push.stdout.strip() or "(pushed)")
    if push.returncode != 0:
        lines.append("the push did NOT succeed - the commit is local only.")
    lines.append("Pages takes a minute or two to rebuild after a push.")
    return "\n".join(lines)


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
    lines.append(f"  {'publish':<12} add everything in projects/site, commit and "
                 f"push - `publish <message>` sets the commit line")
    lines += [
        "",
        "a shortcut works bare, with arguments (`preview --seconds 120`), and "
        "as the first word of any link in a chain (`git_status && ls`) - but "
        "`publish` is always alone.",
    ]
    lines += [
        "",
        "my shell is bash (the one Git ships), so pipes, &&, globs, `for` "
        "loops, $(...) and multi-line commands all work.",
        "anything else runs as-is, e.g. npm install, python -m venv .venv, "
        "npx playwright install chrome.",
        "a bare `python` and a bare `node` both work: my own are put first on "
        "PATH for anything I run, so I never have to hunt for the interpreter.",
        "cwd is always my folder. Long commands get killed at "
        f"{TIMEOUT // 60} minutes. Output is capped at {MAX_OUTPUT} chars.",
        f"if the SAME command fails {FAIL_STREAK_LIMIT} times in a row I stop "
        "running it and say so - one more identical try is not a new idea, it is "
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

    # Line endings are NORMALISED, not refused. The refusal this replaced was
    # correct once and is now obsolete, and the reason is worth keeping.
    #
    # It existed for a real bug: under cmd a newline split the command, the
    # interpreter got a truncated argument, and the exit code still reported 0 -
    # so the output went missing and looked like silence. Master hit exactly that
    # ("multiline python -c is eating my output"). cmd is no longer the shell.
    # bash takes the whole string as one program, and the same two-line
    # `python -c` that came back empty under cmd now prints its real answer -
    # measured, not assumed. The cause is fixed instead of fenced off.
    #
    # A CR is still stripped: with bash a CRLF line leaves `pwd\r` as the last
    # token, and that resolves to nothing.
    command = command.replace("\r\n", "\n").replace("\r", "\n")

    # `publish` routes BEFORE the shell path: it is a sequence rather than a
    # command, and its message is free text that must never reach a shell.
    if command == "publish" or command.startswith("publish "):
        started = time.time()
        out = _publish(command[len("publish"):].strip())
        _audit(command, None, time.time() - started, "publish")
        return _cap(out, max_output)

    resolved = resolve(command)

    # publish inside a chain: the one-word route above only catches it alone,
    # and a bare `publish` falling through to bash is another exit 127 and a
    # lost turn. It cannot expand like the others - its argument is free text,
    # and it commits and pushes EVERYTHING, so it is only honest alone.
    if any((seg.strip() == "publish" or seg.strip().startswith("publish "))
           for seg in _SEGMENT_RE.split(command)):
        return ("publish is a whole command, not one link in a chain: it adds "
                "everything in projects/site, commits and pushes, so it only "
                "makes sense on its own. Run the other commands first, then "
                "call `publish <message>` by itself.")

    # The recursive guard, before anything is spawned - the 198-second sweep
    # was the cost of letting the command run and reading the lesson after.
    if (_RECURSIVE_TOOL_RE.search(resolved) and _RECURSIVE_FLAG_RE.search(resolved)
            and (_UP_AND_OUT_RE.search(resolved)
                 or _ABSOLUTE_OUT_RE.search(resolved))):
        _audit(resolved, None, 0.0,
               "REFUSED - recursive search pointed past my folder")
        return (
            "refused: that is a recursive search pointed past my folder - `..`, "
            "a drive root or my home walks OUT of my folder, and the last one "
            "did exactly that and burned 198 seconds. Point it at one file or "
            "one named subfolder instead: `grep -rn foo projects/site`, or "
            "`cd projects/site && grep -rn foo .`. If what I am hunting is an "
            "installed module, ask python where it lives: "
            'python -c "import mod, inspect; print(inspect.getfile(mod))".'
        )

    # cmd syntax that survives the shell swap (the unix shelf has the table):
    # under bash `>nul` writes a file literally named `nul`. Warn and run -
    # the rest of the command may be fine, and a note teaches without holding
    # the turn hostage.
    nul_note = ""
    if _NUL_REDIRECT_RE.search(command):
        nul_note = ("note: `>nul` is cmd syntax - under bash it writes a file "
                    "literally named nul; the null device is /dev/null.\n")

    # The stop-after-the-limit rule, checked BEFORE anything is spawned: the
    # point is not to pay for that next attempt at all.
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
    argv = shell_argv(resolved)

    try:
        proc = subprocess.Popen(
            argv if argv else resolved,
            cwd=str(ROOT),
            env=child_env(),            # her python and node first on PATH
            shell=argv is None,         # cmd only as a FALLBACK; bash is argv
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
    if proc.returncode == 127:
        hint = _not_found_hint(out)
        if hint:
            head += "\n" + hint
    if not out:
        return nul_note + head + "\n(no output)"
    return nul_note + head + "\n" + _cap(out, max_output)
