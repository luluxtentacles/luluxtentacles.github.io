"""The pipeline that makes a self-edit survivable.

A self-edit is never applied by the bot. The bot stages files and exits; this
module decides whether the new code is allowed to stay.

    1. checkpoint  commit the dirty tree, so there is a commit to return to
    2. backup      copy every file about to be touched into pending/.backup/
    3. apply       copy the staged files over the real ones
    4. smoke       run tests/smoke_test.py; a failure reverts BEFORE any restart
    5. restart     the supervisor starts the bot (this module does not)
    6. health      the bot writes memory/health.marker in on_ready; if the
                   marker does not move in time, the patch is reverted too
    7. revert      restore from the backup, delete anything the patch added,
                   archive the rejected files, start again on the old code

Nothing here is an LLM. It is a loop with exit codes, and every branch is
readable in one sitting - a second agent watching the first would add a new
injection surface and prove nothing.

Two independent revert paths on purpose:
    - the file backups are the mechanical revert, and they always work
    - the git checkpoint is the audit trail and the manual way back
so a bad patch is recoverable even if git is unhappy that day.

Usage:
    python pipeline.py --selftest     # prove apply+smoke+revert on itself
    (the supervisor imports this)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import paths

ROOT = Path(__file__).resolve().parent
PENDING = ROOT / "pending"
STAGED = PENDING / "staged"
BACKUP = PENDING / ".backup"
REJECTED = PENDING / "rejected"
REQUEST = PENDING / "REQUEST.json"
# Where a claimed request is parked. Claiming is what stops the request being
# acted on twice - see claim_request().
CLAIMED = PENDING / ".claimed.json"
SMOKE = ROOT / "tests" / "smoke_test.py"
HEALTH = ROOT / "memory" / "health.marker"

SMOKE_TIMEOUT = 120
GIT_TIMEOUT = 60

# How many of her OWN patches may be applied in one day.
#
# Deliberately counts self-review patches only: a change master asked for is
# never held back by her pacing rules, and the origin is stamped into the request
# by set_context, not by the model. Five successful patches in ten minutes would
# sail past the supervisor's RAPID_MAX - that is a crash-loop breaker, not a
# churn breaker - so this is the brake on a bad day rather than a bad box.
SELF_REVIEW_DAILY_MAX = 5


def log(message: str) -> None:
    """Same shape as the bot's log, so one file tells the whole story."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp} SUPERVISOR {message}", flush=True)


# -- the request ----------------------------------------------------------

def claim_request() -> bool:
    """Take ownership of the staged request by renaming it out of the way.

    Called by process() before it does anything else, and this matters more
    than it looks. The request used to sit on disk for the whole run - through
    the smoke test and through the health-gated restart - where the
    supervisor's own serve() loop saw it and believed a NEW restart had been
    asked for, starting the grace timer that TERMINATES the bot. She then also
    closed herself again, because her restart watcher was looking at the same
    stale file. One patch, two boots, one near-kill that only missed because
    she happened to close inside the grace window.

    Claiming once, up front, means a serve() loop can only ever see a request
    that nobody has taken yet.
    """
    if not REQUEST.exists():
        return False
    try:
        REQUEST.replace(CLAIMED)
        return True
    except Exception as exc:
        log(f"WARNING could not claim the request: {exc}")
        return False


def load_request() -> dict | None:
    """The staged request, or None. Never raises on a malformed file."""
    if not REQUEST.exists():
        return None
    try:
        data = json.loads(REQUEST.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"files": []}
    except Exception as exc:
        log(f"WARNING request file is unreadable ({exc}); treating as plain restart")
        return {"files": [], "why": "unreadable request"}


def staged_files() -> list[str]:
    """Relative paths sitting under pending/staged, newest request wins."""
    if not STAGED.is_dir():
        return []
    found = []
    for path in sorted(STAGED.rglob("*")):
        if path.is_file():
            found.append(path.relative_to(STAGED).as_posix())
    return found


# -- git ------------------------------------------------------------------

def repo_root() -> Path | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             cwd=str(ROOT), capture_output=True, text=True,
                             timeout=GIT_TIMEOUT)
        if out.returncode == 0:
            return Path(out.stdout.strip())
        # A non-zero exit used to fall through to `return None` in total silence,
        # which is how she ran on 'checkpoint: None' with nothing in the log to
        # explain it. Git's own words are the useful part: 'dubious ownership'
        # means the repo belongs to another account and git refuses to touch it,
        # which is exactly what happens here - C:/Lulu belongs to Kei and this
        # runs as lulu-bot.
        log(f"WARNING git refused: exit {out.returncode}: "
            f"{(out.stderr or out.stdout).strip()[:300]}")
    except Exception as exc:
        log(f"WARNING git unavailable: {exc}")
    return None


def checkpoint(why: str) -> str | None:
    """Commit the dirty tree so there is a named way back. Best effort: a
    missing git must not block an update that the smoke test will judge."""
    repo = repo_root()
    if repo is None:
        # Worth saying out loud, because the consequence is easy to miss: the
        # patch still applies and the smoke test still judges it, but there is no
        # commit capturing what it replaced. The backup copy is the only way
        # back, so the net is thinner than the docstring above promises.
        log("WARNING not checkpointed: no commit captures the state this patch "
            "replaced - the backup copy is the only way back")
        return None
    label = f"supervisor: checkpoint before {' '.join(why.split())[:70]}"
    try:
        subprocess.run(["git", "add", "-A", "--", str(ROOT)],
                       cwd=str(repo), capture_output=True, text=True, timeout=GIT_TIMEOUT)
        subprocess.run(["git", "commit", "-q", "-m", label],
                       cwd=str(repo), capture_output=True, text=True, timeout=GIT_TIMEOUT)
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=str(repo), capture_output=True, text=True,
                             timeout=GIT_TIMEOUT).stdout.strip()
        log(f"checkpoint {sha} ({label})")
        return sha or None
    except Exception as exc:
        log(f"WARNING checkpoint failed: {exc}")
        return None


# -- apply / revert -------------------------------------------------------

def apply(files: list[str]) -> dict[str, Path | None]:
    """Copy staged files over the real ones, backing up what existed.

    Returns {relative_path: backup_path_or_None}. None means the file did not
    exist before, so a revert deletes it.
    """
    backups: dict[str, Path | None] = {}
    BACKUP.mkdir(parents=True, exist_ok=True)
    for rel in files:
        source = STAGED / rel
        target = ROOT / rel
        if not source.is_file():
            log(f"WARNING staged file vanished: {rel}")
            continue
        if not _inside(target):
            log(f"WARNING refusing to write outside the folder: {rel}")
            continue
        # The seal, checked HERE as well as when staging - and this is the copy
        # that actually holds.
        #
        # paths.assert_proposable already refuses a sealed file when a patch is
        # STAGED, so the tools cannot reach these. But that is the only place it
        # was checked, and this function does not consult it at all: it rglobs
        # pending/staged and copies whatever it finds over the real file. So any
        # route that lands a file in there - a bare open() from code she patched
        # into tools.py, which paths.py itself warns is possible, since it is an
        # in-process guard and not an OS jail - used to reach supervisor.py,
        # pipeline.py and tests/ unopposed. A staged supervisor.py would have
        # replaced the thing that reverts her.
        #
        # That is the same bug paths.py already documents for tests/: the judge
        # had no guard on itself. It does now, and it holds because pipeline.py
        # is itself sealed - so this check cannot be patched out.
        try:
            paths.assert_proposable(target)
        except paths.SandboxError as exc:
            log(f"WARNING refusing sealed target: {rel} - {exc}")
            continue
        if target.exists():
            saved = BACKUP / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
            backups[rel] = saved
        else:
            backups[rel] = None
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        log(f"applied {rel} ({source.stat().st_size} bytes)")
    return backups


def _inside(target: Path) -> bool:
    try:
        target.resolve().relative_to(ROOT)
        return True
    except ValueError:
        return False


def revert(backups: dict[str, Path | None]) -> list[str]:
    """Put every touched file back. This is the mechanical half of the net.

    Idempotent on purpose: a second revert is a no-op with a plain note, not an
    Errno traceback. The supervisor only reverts an 'applied' report, but a
    double revert showing 'ERROR' would read like the net failed when it had
    already done its job.
    """
    undone = []
    for rel, saved in backups.items():
        target = ROOT / rel
        try:
            if saved is None:
                if target.exists():
                    target.unlink()
                undone.append(f"removed {rel}")
            elif not saved.exists():
                undone.append(f"already back (no backup left) {rel}")
            else:
                shutil.copy2(saved, target)
                undone.append(f"restored {rel}")
        except Exception as exc:
            log(f"ERROR could not revert {rel}: {exc}")
    for line in undone:
        log(f"revert: {line}")
    return undone


def archive(reason: str, outcome: str) -> Path | None:
    """Keep the rejected attempt with its reason, so she can read why.

    A patch that failed is the most useful thing she can read next turn, so it
    is filed rather than deleted.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    box = REJECTED / f"{stamp}-{outcome}"
    moved: list[str] = []
    try:
        box.mkdir(parents=True, exist_ok=True)
        if STAGED.is_dir():
            for path in sorted(STAGED.rglob("*")):
                if path.is_file():
                    dest = box / path.relative_to(STAGED)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(dest))
                    moved.append(path.relative_to(STAGED).as_posix())
        (box / "REASON.txt").write_text(
            f"outcome: {outcome}\nwhen: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"why she asked: {reason}\nfiles: {', '.join(moved) or '(none)'}\n\n"
            f"{reason}\n",
            encoding="utf-8")
    except Exception as exc:
        log(f"WARNING could not archive: {exc}")
        return None
    log(f"archived {len(moved)} file(s) to {box.relative_to(ROOT).as_posix()} ({outcome})")
    return box


def clear_request() -> None:
    for path in (REQUEST, CLAIMED):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except Exception as exc:
            log(f"WARNING could not clear request: {exc}")
    try:
        if BACKUP.is_dir():
            shutil.rmtree(BACKUP)
    except Exception as exc:
        log(f"WARNING could not clear backups: {exc}")


# -- the smoke test -------------------------------------------------------

def run_smoke() -> tuple[bool, str]:
    """Run the net. Anything but exit 0 is a failure."""
    if not SMOKE.exists():
        return False, "no smoke test at tests/smoke_test.py - refusing to apply blind"
    try:
        out = subprocess.run([sys.executable, str(SMOKE)],
                             cwd=str(ROOT), capture_output=True, text=True,
                             timeout=SMOKE_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"smoke test timed out after {SMOKE_TIMEOUT}s"
    except Exception as exc:
        return False, f"could not run the smoke test: {exc}"
    body = (out.stdout or "") + (out.stderr or "")
    return out.returncode == 0, body.strip()


# -- health ---------------------------------------------------------------

def marker_state() -> str:
    """What the health marker says right now; empty when it is missing."""
    try:
        return HEALTH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


# -- the daily budget -----------------------------------------------------

def self_review_applied_today() -> int:
    """How many self-review patches already went in today.

    Counted from the filed records rather than from memory, so a restart cannot
    reset the budget - and a restart is exactly what a patch causes, so an
    in-memory counter would be worthless here.
    """
    box = PENDING / "applied"
    if not box.is_dir():
        return 0
    today = time.strftime("%Y%m%d")
    count = 0
    for entry in sorted(box.iterdir()):
        if not entry.name.startswith(today):
            continue
        for note in entry.glob("*.txt"):
            try:
                if "origin: self-review" in note.read_text(encoding="utf-8"):
                    count += 1
            except Exception:
                continue
    return count


# -- the whole update -----------------------------------------------------

def process(why: str) -> dict:
    """Apply a staged update and judge it. Returns a report dict.

    Stops before the restart: the supervisor owns starting the bot, because
    only it can decide whether a failed patch gets one recovery attempt.
    """
    files = staged_files()
    report = {"why": why, "files": files, "sha": None, "smoke": None,
              "backups": {}, "reverted": False, "outcome": "noop"}

    # Read the request BEFORE claiming it: claim_request renames the file out of
    # the way, so after it there is nothing left to read the origin from.
    request = load_request() or {}
    origin = str(request.get("origin") or "master")
    report["origin"] = origin

    if not files:
        log("no staged files: this is a plain restart, nothing to apply")
        report["outcome"] = "restart-only"
        clear_request()
        return report

    # The budget, checked before anything is touched. Held patches are FILED
    # rather than deleted, because the reason is the useful thing next turn -
    # same reasoning as a rejected patch.
    if origin == "self-review":
        spent = self_review_applied_today()
        if spent >= SELF_REVIEW_DAILY_MAX:
            log(f"self-review budget spent ({spent}/{SELF_REVIEW_DAILY_MAX} today) "
                f"- holding this patch, nothing applied")
            report["outcome"] = "budget-held"
            report["archive"] = str(archive(
                f"daily self-review budget already spent ({spent}/"
                f"{SELF_REVIEW_DAILY_MAX}). Nothing was applied and she was not "
                f"restarted. Try again tomorrow, and make the next one count.",
                "rejected-budget"))
            clear_request()
            return report

    # Claim before applying. Every serve() loop in the supervisor watches
    # REQUEST.json, so leaving it in place through the restart makes a healthy
    # bot look like it has a pending restart request and gets it killed.
    claimed = claim_request()
    if not claimed:
        log("no request on disk to claim; proceeding on the staged files anyway")

    report["sha"] = checkpoint(why)
    backups = apply(files)
    report["backups"] = backups
    if not backups:
        log("nothing applied - staged files were all rejected")
        report["outcome"] = "nothing-applied"
        clear_request()
        return report

    ok, output = run_smoke()
    report["smoke"] = ok
    if ok:
        log(f"smoke test PASSED for {len(backups)} file(s)")
        report["outcome"] = "applied"
        return report

    log("smoke test FAILED - reverting before any restart")
    for line in output.splitlines():
        log(f"  smoke| {line}")
    report["reverted"] = True
    report["outcome"] = "reverted-smoke"
    report["detail"] = output
    revert(backups)
    report["archive"] = str(archive(f"smoke test failed\n\n{output}", "rejected-smoke"))
    clear_request()
    return report


def reject_after_unhealthy(report: dict, detail: str) -> dict:
    """The health check failed: the code ran, imported, and still did not work."""
    log("health check FAILED - reverting the patch")
    revert(report.get("backups") or {})
    report["reverted"] = True
    report["outcome"] = "reverted-health"
    report["detail"] = detail
    report["archive"] = str(archive(f"health check failed\n\n{detail}", "rejected-health"))
    clear_request()
    return report


def accept(report: dict) -> None:
    """The patch survived. File it as applied and clear the request."""
    box = PENDING / "applied"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    try:
        dest = box / stamp
        if STAGED.is_dir():
            for path in sorted(STAGED.rglob("*")):
                if path.is_file():
                    target = dest / path.relative_to(STAGED)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), str(target))
        (box / f"{stamp}.txt").write_text(
            f"applied: {', '.join(report.get('files') or [])}\n"
            f"when: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"why she asked: {report.get('why')}\n"
            # Counted by self_review_applied_today(), so the spelling of this
            # line is load-bearing: "origin: self-review" is the budget's unit.
            f"origin: {report.get('origin') or 'master'}\n"
            f"checkpoint: {report.get('sha')}\n",
            encoding="utf-8")
    except Exception as exc:
        log(f"WARNING could not file the applied patch: {exc}")
    log(f"patch accepted: {', '.join(report.get('files') or [])}")
    clear_request()


# -- proof ----------------------------------------------------------------

def _write_request(why: str, files: list[str]) -> None:
    REQUEST.write_text(json.dumps({"why": why, "files": files}), encoding="utf-8")


def selftest() -> int:
    """Prove the net on itself: a broken patch must apply, fail, and revert.

    This touches only pending/ and one real file (lulu_bot.py), which is put
    back byte-for-byte and verified by hash. If this ever stops reverting, the
    whole self-update story is a lie, so it is worth being able to run it.
    """
    import hashlib

    target = ROOT / "lulu_bot.py"
    original = target.read_bytes()
    before = hashlib.sha256(original).hexdigest()
    print(f"lulu_bot.py before: {before[:16]} ({len(original)} bytes)")

    STAGED.mkdir(parents=True, exist_ok=True)
    (STAGED / "lulu_bot.py").write_text(
        "this is not python(((\n", encoding="utf-8")
    REQUEST.write_text(json.dumps({"why": "pipeline selftest: broken patch",
                                   "files": ["lulu_bot.py"]}), encoding="utf-8")

    report = process("pipeline selftest: broken patch")

    after = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f"lulu_bot.py after : {after[:16]}")
    print(f"outcome           : {report['outcome']}")
    print(f"smoke             : {report['smoke']}")

    problems = []
    if report["outcome"] != "reverted-smoke":
        problems.append(f"expected reverted-smoke, got {report['outcome']}")
    if report["smoke"] is not False:
        problems.append("a syntax error passed the smoke test")
    if after != before:
        problems.append("the file was NOT restored byte-for-byte")
    if not report.get("archive"):
        problems.append("the rejected patch was not archived")

    # Second half: a VALID patch must apply, pass, and be ACCEPTED. This uses a
    # throwaway file, so no real code is on the line while accept() is tested.
    probe = ROOT / "selftest_probe.txt"
    STAGED.mkdir(parents=True, exist_ok=True)
    (STAGED / "selftest_probe.txt").write_text("probe\n", encoding="utf-8")
    _write_request("pipeline selftest: good patch", ["selftest_probe.txt"])
    report2 = process("pipeline selftest: good patch")
    print(f"good patch outcome: {report2['outcome']} (smoke={report2['smoke']})")

    # REGRESSION: process() must CONSUME the request, not leave it lying on disk.
    # While it stayed, the supervisor's serve() loop found a stale request during
    # the health-gated restart, armed the terminate timer, and she booted TWICE
    # for one patch - saved from a spurious kill only by closing inside the grace
    # window. Asserting this after an 'applied' report is what catches it: the
    # reverted path clears the request either way, so only this path proves it.
    if REQUEST.exists():
        problems.append("process() left REQUEST.json on disk after applying")
    if not CLAIMED.exists():
        problems.append("process() did not claim the request")

    if report2["outcome"] != "applied" or not report2["smoke"]:
        problems.append(f"a valid patch was not accepted: {report2['outcome']}")
    else:
        accept(report2)
        if not probe.is_file():
            problems.append("accept() did not leave the applied file in place")
        if BACKUP.is_dir():
            problems.append("accept() did not clear the backup dir")
        print("good patch applied, accepted, and filed")

    # Third half, and the one that matters most: the health check is the SECOND
    # net. A patch can pass the smoke test and still fail to come up, and then
    # it must revert byte for byte. The old version of this test never reached
    # that path - it called accept() first, and accept() is precisely what
    # clears the backups, so the revert could not have worked.
    victim = ROOT / "lookup.py"
    victim_before = victim.read_bytes()
    (STAGED / "lookup.py").write_text(
        victim_before.decode("utf-8") + "\n# selftest touch\n", encoding="utf-8")
    _write_request("pipeline selftest: healthy-looking but bad", ["lookup.py"])
    report3 = process("pipeline selftest: healthy-looking but bad")
    print(f"health-path outcome: {report3['outcome']} (smoke={report3['smoke']})")
    if report3["smoke"] is not True:
        problems.append("the healthy-looking patch did not pass the smoke test")
    elif report3["outcome"] != "applied":
        problems.append(f"expected 'applied' before health, got {report3['outcome']}")
    elif victim.read_bytes() == victim_before:
        problems.append("the patch never reached the file")
    else:
        reject_after_unhealthy(report3, "selftest: pretend she never came up")
        if victim.read_bytes() != victim_before:
            problems.append("the health-fail revert did NOT restore lookup.py")
        else:
            print("health-fail revert restored lookup.py byte-for-byte")

    # Leave nothing behind.
    for leftover in (REQUEST, CLAIMED):
        try:
            leftover.unlink()
        except FileNotFoundError:
            pass
    for leftover in (BACKUP,):
        if leftover.is_dir():
            shutil.rmtree(leftover, ignore_errors=True)
    if STAGED.is_dir() and not any(STAGED.iterdir()):
        STAGED.rmdir()
    try:
        probe.unlink()
    except FileNotFoundError:
        pass

    final = hashlib.sha256(target.read_bytes()).hexdigest()
    if final != before:
        problems.append("lulu_bot.py changed during the test and stayed changed")
    if victim.read_bytes() != victim_before:
        problems.append("lookup.py did not survive the selftest unchanged")

    print()
    if problems:
        print("SELFTEST FAILED:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("SELFTEST PASSED: broken patch reverted, good patch applied,")
    print("                 health-fail revert restored the file byte-for-byte")
    print(f"  final lulu_bot.py sha256: {final[:16]} (matches original)")
    print(f"  lookup.py back to {victim.stat().st_size} bytes, unchanged")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    print("this module is driven by supervisor.py; use --selftest to check it")
    raise SystemExit(0)
