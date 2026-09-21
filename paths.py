"""The wall around this folder.

Every file the bot reads or writes goes through resolve(). A path that is not
inside the folder - or inside one of the NAMED EXTERNAL_ROOTS below - raises
SandboxError instead of quietly succeeding.

The external roots exist because master moved the runtimes out of her folder on
2026-09-21, and a runtime she cannot reach is a runtime she cannot run. They are
named in CODE, not taken from config, so the set of places she may reach is fixed
by whoever edits this file and cannot be widened by anything she runs.

Writes are still confined to the folder proper: reads may reach the external
roots, but assert_writable() requires a path relative to ROOT, so no tool call
can write outside her box however the roots change.

Honest limit: this is an in-process guard, not an OS jail. Code that imports
open() directly could bypass it. What it does guarantee is that no path the
*configuration or runtime* hands in can point outside the folder or the roots.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# The runtimes, and why they are allowed to live outside the folder.
#
# Master, 2026-09-21: "i copied python311 and whisper into c:lulu-apps". The
# point is that her own folder stops carrying two heavy, gitignored trees.
#
# They are ALIASED here rather than reached by any config value, and that is the
# whole safety property. A named tuple in a sealed file means the reachable set
# is exactly what a human wrote down - so a link or a symlink she creates that
# points at C:\Windows is still REFUSED, because C:\Windows is not in this tuple.
# Config-driven roots would have handed her a way to widen her own reach.
#
# Named by full path, not by the old folder-relative spelling, because
# Path.resolve() follows junctions and links: a link under ROOT that points here
# resolves to the TARGET, which is outside ROOT, and is exactly what broke the
# first attempt at this. Naming the real target is the thing that works.
#
# NOTE for a future session: do not add an entry here without master saying so.
# This tuple is the reach boundary, and every entry in it is somewhere her code
# can read that is not her own folder.
# ---------------------------------------------------------------------------
APPS_ROOT = Path(r"C:\lulu-apps")
PYTHON_HOME = APPS_ROOT / "Python311"
WHISPER_HOME = APPS_ROOT / "whisper.cpp"
EXTERNAL_ROOTS = (APPS_ROOT,)

# No exceptions. The token is read from the den once at startup, and that read
# is declared in lulu_bot.py where it can be audited; this guard stays absolute.

# Files the tools may read but never overwrite. Without this, a write_file call
# could replace paths.py itself - the wall - and the next restart would hand
# over everything. The skill shelf is listed because those bodies ARE the
# system prompt.
# ---------------------------------------------------------------------------
# Three tiers. This used to be one flat name-list, and the gap in it was real:
# setup/run-bot.cmd - the script that decides what runs at startup - sat inside
# her write reach, so a write_file plus a restart was enough to run anything.
#
#   SEALED     no tool call and no proposed patch. The wall itself, the
#              launcher, the pipeline, the credentials. Breaking one of these
#              voids every other guarantee, so they are not self-updatable:
#              master edits them by hand.
#   PROPOSABLE direct writes refused. The only way in is propose_patch, which
#              stages the file for the supervisor to apply behind git, the
#              smoke test and a health check, with auto-revert on failure.
#   the rest   ordinary writing: her own data, scripts and scratch.
# ---------------------------------------------------------------------------
SEALED_NAMES = {
    # the wall, and the pipeline that enforces it
    "paths.py", "supervisor.py", "pipeline.py",
    # the keys
    "config.json", "config.example.json", "brain_key.txt", ".gitignore",
    # The Discord token. It was the ONE credential missing from this list, and it
    # is the one that matters most: a bare write_file could have replaced it and
    # locked her out of her own account, or pointed her at somebody else's. It
    # shipped as an ordinary file and nobody noticed until master asked whether
    # her secrets were reachable.
    #
    # WRITING is what is sealed, not reading. load_token does a plain read_text,
    # which never goes through this module, so sealing this cannot stop her
    # logging in - and it must not, because she cannot boot without reading it.
    "discord_token.txt",
    # MCP credentials - and the tracked example beside them. Both sealed, not
    # just the one holding values: the example IS committed, and the pipeline's
    # checkpoint sweeps `git add -A - discord/`, so a real value written into
    # the example by any tool would be committed on the next self-edit. The
    # first cut of this sealed mcp.json and forgot the secrets file entirely.
    "mcp_secrets.json", "mcp_secrets.example.json",
    # AGENTS.md, added the day it was created (2026-09-20). It is not a config
    # or a key - it is INSTRUCTIONS, read by every Kun session opened in this
    # folder and treated as high-priority context about how to work on her.
    #
    # That makes it the one file here whose text becomes AUTHORITY somewhere
    # else, which is a different risk from anything above: a writable
    # AGENTS.md is a way to brief the next agent that comes along - not to
    # change her code, but to change what the thing editing her code believes.
    # Measured before sealing: write_file ALLOWED and propose_patch ALLOWED,
    # which is exactly the state discord_token.txt was found in.
    #
    # Sealing does not stop Kun READING it. The instruction runtime loads it
    # with plain node fs, which never goes through this module - same as
    # load_token and discord_token.txt above.
    "AGENTS.md",
}
SEALED_DIRS = {
    "setup",    # the launcher: what actually runs at startup
    "memory",   # her store. One write_file here wiped it once already.
    "pending",  # the staging area, written only by propose_patch
    "tests",    # the net that judges every self-edit. See the note below.
    "logs",     # her own audit trail. An agent that can restate the record of what
                # it did has no record. Sealed at the same time as autonomy, and for
                # the same reason: the log is only evidence while she cannot edit it.
    "node",     # The runtime she spawns MCP servers with. Sealed for one specific
                # reason: node/ is gitignored, so a replaced node.exe would be
                # invisible to git - an unversioned, writable binary is a blind spot
                # in the only audit trail there is. Sealing does NOT stop her running
                # it: subprocess never goes through resolve(). node_cache/ stays
                # ordinary writing, because npx has to download into it.
    "ffmpeg",   # Same argument, same shape: gitignored, 242 MB, executed by the STT
                # path to decode voice messages. A swapped binary is invisible to
                # git, so it is sealed for the same reason node/ is. Sealing does not
                # stop her RUNNING it - the exec goes through subprocess, not
                # resolve().
    # Chrome Canary, copied into her folder on 2026-09-21 so she stops borrowing
    # a browser she has no rights to (master's Canary lives in his profile and
    # denies her account outright). Sealed the moment it arrived, for exactly the
    # reason node/ and ffmpeg/ are: it is GITIGNORED - chrome-canary/.gitignore
    # ignores the whole 500 MB - so a swapped binary would be invisible to git,
    # and an unversioned, writable executable is a blind spot in the only audit
    # trail there is. Sealing does not stop her running it; the launch goes
    # through subprocess, not resolve().
    "chrome-canary",
    ".git",
}

# `tests` is sealed for a reason worth writing down, because it was reachable
# until it was not. The smoke test is what decides whether a proposed patch may
# keep running, and it used to be ordinary writing: a bare write_file could put
# a stub there that exits 0, after which every later patch is applied on the
# strength of a net that no longer exists. The judge had no guard on itself.
# Hand-edited only - and it matters more now that her reach extends to things
# that spawn processes.

# Her prompt shelf. Unsealed on master's call: she is boxed inside Discord, and
# only the owner id can reach propose_patch at all, so a bad skill edit is a
# contained mess rather than an escape.
#
# PROPOSABLE, and deliberately NOT directly writable. A bare write_file still
# cannot touch a skill, because a prompt change that skips the pipeline is
# precisely the one nothing would catch. Through the pipeline it gets a git
# checkpoint, the shelf check in the smoke test, and an automatic revert.
PROPOSABLE_DIRS = {".agents"}

# Code that runs her. Changeable - but only through the pipeline, never by a
# bare tool call.
PROPOSABLE_NAMES = {
    "lulu_bot.py", "tools.py", "brain.py", "skills.py", "shared_memory.py",
    "people.py", "journal.py", "webtool.py",
    # Her ears. Everything this module does with an attachment ends in a spawned
    # process, so it belongs in the tier a bare write_file cannot reach - the
    # same reason spend.py and the MCP client are listed rather than left to be
    # born ordinary files.
    "whisper_stt.py",
    # The purse. Listed with the code it governs rather than left to be born an
    # ordinary file: the module that decides whether she may spend is not
    # something a bare write_file should be able to reach.
    "spend.py",
    # Her review window: the module that decides when she may change herself, so
    # it belongs in the same tier as the code it changes. Left out on the first
    # pass and caught by a probe - still writable by a bare write_file, which is
    # the exact omission this comment exists to stop repeating.
    "self_review.py",
    # Her long-task worker, on the same argument: it runs her over several turns,
    # picks its own tools, and is started only by master. Code that runs her is
    # pipeline-only, never a bare write_file.
    "taskmode.py",
    # The MCP client and its server registry, listed BEFORE either exists, on
    # purpose. Left out, they would be born as ordinary files - so the module
    # that spawns new processes would be the one file she can write freely, and
    # the registry of what may be spawned would be writable without a pipeline.
    "mcp_client.py", "mcp.json",
    # The command allowlist. This one was left out on the first pass and it is
    # the same omission as self_review.py above: runbox.py is the file that
    # DECIDES what she may run, and it shipped as an ordinary file, so a bare
    # write_file could have added any verb it liked - which makes "there is no
    # npx verb" a suggestion rather than a rule. Being pipeline-only is the
    # right tier rather than sealed: she may propose a new verb, and if it is a
    # package runner the smoke test's banned-binary check refuses it.
    "runbox.py",
    # The browser's one door out (2026-09-20). Same tier as runbox.py and for a
    # related reason: it is the file that DECIDES what the browser may reach, and
    # a bare write_file able to edit it would make the address rule a suggestion.
    # It is the application-layer half of a boundary the OS refuses to provide -
    # Windows Firewall can neither filter NOR declare loopback - so this file is
    # the only thing standing between a page and 127.0.0.1.
    "browseguard.py",
}


class SandboxError(RuntimeError):
    """A path escaped the bot's folder. Refuse; do not warn and continue."""


def _permitted(full: Path) -> bool:
    """Is this resolved path inside the folder, or inside a named root?"""
    if full == ROOT or ROOT in full.parents:
        return True
    return any(full == root or root in full.parents for root in EXTERNAL_ROOTS)


def resolve(relative: str | os.PathLike, *, must_exist: bool = False) -> Path:
    """Turn a path into an absolute one, or refuse.

    Absolute paths used to be refused outright. They are accepted now, but ONLY
    when they land inside a named external root - which is how the whisper
    binary and its model are reached, since they no longer live in her folder.

    `C:\Windows\System32\...` is still refused, and so is anything else that is
    neither under ROOT nor under a root master wrote down here. Accepting
    absolute paths did not widen the boundary; the boundary is _permitted().
    """
    candidate = Path(relative)
    full = candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
    if not _permitted(full):
        raise SandboxError(f"path is outside the sandbox: {relative}")
    if must_exist and not full.exists():
        raise SandboxError(f"nothing there: {relative}")
    return full


def pin_cwd() -> None:
    """Make relative opens land inside the folder even if the caller is sloppy."""
    os.chdir(ROOT)


def read_text(relative: str, default: str | None = None) -> str:
    path = resolve(relative)
    if not path.exists():
        if default is None:
            raise FileNotFoundError(relative)
        return default
    return path.read_text(encoding="utf-8")


def _relative_parts(path: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(ROOT).parts
    except ValueError:
        raise SandboxError(f"path escapes the sandbox: {path}") from None


def _sealed(path: Path, parts: tuple[str, ...]) -> bool:
    return path.name in SEALED_NAMES or bool(parts) and parts[0] in SEALED_DIRS


def assert_writable(path: Path) -> None:
    """Refuse to overwrite the code that runs me, the shelf that prompts me, or
    the store that remembers for me.

    This is the guard on a bare tool call. It is deliberately stricter than
    assert_proposable: a write_file can never touch something that runs her -
    not her code, and not her prompt either.
    """
    parts = _relative_parts(path)
    relative = "/".join(parts)
    if _sealed(path, parts):
        raise SandboxError(
            f"{relative} is sealed: the wall, the launcher and the keys are "
            f"never writable by a tool call")
    if path.name in PROPOSABLE_NAMES or (parts and parts[0] in PROPOSABLE_DIRS):
        raise SandboxError(
            f"{relative} runs me: change it with propose_patch, which stages it "
            f"for the supervisor to apply behind git and the smoke test")


def assert_proposable(path: Path) -> None:
    """The guard for propose_patch - staged changes, not direct writes.

    Sealed is sealed even here. Everything else may be staged, because the
    supervisor applies it behind a checkpoint, the smoke test, a health check
    and an automatic revert.
    """
    parts = _relative_parts(path)
    if _sealed(path, parts):
        relative = "/".join(parts)
        raise SandboxError(f"{relative} is sealed: not self-updatable, ask master")


def write_text(relative: str, text: str, *, internal: bool = False) -> Path:
    """Write inside the folder.

    `internal=True` is for my own storage layer, which has to bypass the guard
    to write memory at all. Tool calls never pass it - that gap is precisely
    what keeps write_file away from my source and my store.
    """
    path = resolve(relative)
    if not internal:
        assert_writable(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def read_json(relative: str, default=None):
    path = resolve(relative)
    if not path.exists():
        if default is None:
            raise FileNotFoundError(relative)
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(relative: str, data, *, internal: bool = False) -> Path:
    return write_text(relative, json.dumps(data, indent=2, ensure_ascii=False),
                      internal=internal)
