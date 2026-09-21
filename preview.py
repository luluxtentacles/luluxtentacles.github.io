"""Mirror her own site on loopback, so looking at it does not cost a push.

Why this exists
---------------
Her site is live the second she pushes - GitHub Pages serves `projects/site`
straight off `main`. That is a lovely property and a terrible iteration loop: to
see how a page actually LOOKS she had to commit, push, and then wait for a deploy,
which is minutes of latency per typo. Master, 2026-09-21: *"i assume she would
want to check out how her site looks often and pushing git she has to wait for
deploy."* So the wait goes.

What it cost, stated honestly
-----------------------------
The guards around her refuse every address on this machine. That rule is the only
thing between a page she is READING and Windows' own services - `127.0.0.1:445`
and `:135` were both measured OPEN on this box - and Windows Firewall cannot help,
because it refuses to even declare a rule for loopback (measured 2026-09-20). So
opening the rule at all needed a reason and a shape.

The shape is ONE PORT. `webtool.LOCAL_PREVIEW_PORT` is added to the address rule
as a single exception, and everything that made that rule matter still holds:

  - a page she renders CANNOT pivot to anything else here. It is served through
    the same proxy as any other page, so a script on it reaching for
    `127.0.0.1:9222` - her own browser's CDP endpoint, which is a steering wheel
    for the browser that rendered it - or `:445` is refused exactly as before.
    Different port, same refusal.
  - `file://` is still dead, and never reaches this code: `webtool._check`
    refuses the scheme before any address is looked at.
  - the LAN is still dead. `10.x`, `192.168.x`, `172.16-31.x`, link-local and the
    cloud metadata addresses are all refused.
  - the grant only exists while this process is running. Stop the server and the
    port means nothing.

So the residual risk is exactly this, and it is written down rather than implied:
**anything else listening on `127.0.0.1:<PORT>` while this runs is reachable by
the browser.** That is why the port is fixed and owned here rather than taken as
a flag, why this file is in the pipeline-only tier (a bare `write_file` must not
be able to re-point the mirror at `C:\\` and serve her keys over loopback to a
page she then posts), and why it refuses dotfiles.

What it is
----------
A read-only static file server. GET and HEAD only. It serves one directory and
cannot be talked out of it: the request path is decoded, split, and then the
resolved result is REQUIRED to sit inside the root, so `..` and a symlink out are
refused rather than followed. No directory listing - a listing publishes the whole
shape of the tree, which is not what she asked for when she asked to see one page.
No writes, no caching, no auth, no TLS. It is a mirror, not a server.

How she starts it
-----------------
    python preview.py --background --seconds 120

`--background` is the part that matters, and it is not cosmetic. Her shell
captures stdout through a PIPE and waits for that pipe to close, so a server that
holds it open hangs the caller for the server's whole life. `start /b` LOOKS like
a detach and is not one - measured 2026-09-21, it took 8.1s for a child that lived
8s, and her own log holds the 900s version of exactly that, twice, from her
trying to serve this folder by hand with `start /b python -m http.server`. A
process started with DETACHED_PROCESS and its streams on the null device returns
in 0.1s and keeps running. That is what `--background` does: it re-launches this
same command detached and returns at once. The shelf said `start /b` for exactly
one day, and it was wrong for that whole day.

`--seconds` is the other half and it is not a convenience either: a preview that
outlives its use is a door left open, so it shuts itself. Both are documented on
the `website` shelf, where she will actually look for them.
"""
from __future__ import annotations

import argparse
import http.server
import os
import subprocess
import sys
import threading
import urllib.parse
from pathlib import Path

import paths
import webtool

# The address rule and this server MUST agree on the port, so there is exactly one
# definition of it and it lives in the policy module. A second copy here is the
# drift browseguard.py's own docstring already warns about.
PORT = webtool.LOCAL_PREVIEW_PORT

# Loopback ONLY. A bind on 0.0.0.0 would put her site on the LAN and on whatever
# VPN she is tunnelled into, which is a far bigger hole than the one this file
# exists to open. browseguard.py makes the same choice, for the same reason.
BIND_HOST = "127.0.0.1"

# The only tree worth mirroring: her published site. Named RELATIVE and passed
# through paths.resolve(), so the wall decides where this can point - not a flag
# from a caller, and not something a page can ask for.
DEFAULT_ROOT = "projects/site"

# Extensions worth naming. Anything else is served as a download rather than
# guessed at, because a wrong Content-Type is how a stylesheet turns into a blank
# page - and she cannot see the difference from inside.
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".map": "application/json",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".xml": "application/xml",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".pdf": "application/pdf",
    ".wasm": "application/wasm",
}


def _resolve_request(root: Path, url_path: str) -> Path | None:
    """A request path turned into a real file, or None if it must be refused.

    None is not "not found" - it is "not asked for in good faith". The two are
    answered differently on purpose: a missing page is a 404 she can act on, while
    a traversal, a null byte or a dotfile is a 403 that says so.

    `root` must already be resolved; the containment test at the end is the actual
    guard and it is the same shape as paths._permitted().
    """
    raw = urllib.parse.urlsplit(url_path or "/").path
    try:
        decoded = urllib.parse.unquote(raw)
    except Exception:
        return None
    if "\x00" in decoded:
        return None

    parts: list[str] = []
    for segment in decoded.replace("\\", "/").split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            return None
        # Dotfiles are refused wholesale rather than filtered. This is her
        # published repo and `.git/` alone is a directory of things nobody needs
        # over HTTP, but the reason is not a list of names - it is that a name
        # starting with a dot is never a page, so refusing the shape cannot go
        # stale the way a blocklist does.
        if segment.startswith("."):
            return None
        # Windows will not let a path component carry these, and a `:` inside a
        # segment is how a mirror gets asked for a drive instead of a page.
        if ":" in segment:
            return None
        parts.append(segment)

    candidate = root.joinpath(*parts) if parts else root
    try:
        full = candidate.resolve()
    except OSError:
        return None
    # The guard that actually holds: resolve() follows symlinks, so this catches
    # both `..` that survived and a symlink planted inside the root pointing out.
    if full != root and root not in full.parents:
        return None
    return full


class Handler(http.server.BaseHTTPRequestHandler):
    """One request. Read-only, root-scoped, and it never lists a directory."""

    server_version = "lulu-preview"
    sys_version = ""
    root: Path = Path(".")
    quiet: bool = False

    def do_GET(self) -> None:
        self._serve(body=True)

    def do_HEAD(self) -> None:
        self._serve(body=False)

    def _reject(self, code: int, message: str, body: bool = True) -> None:
        payload = (message + "\n").encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(payload)

    def _serve(self, body: bool) -> None:
        target = _resolve_request(self.root, self.path)
        if target is None:
            self._reject(403, "refused: that path is not inside the mirror")
            return
        if target.is_dir():
            index = target / "index.html"
            if not index.is_file():
                self._reject(404, "no index.html here, and the mirror does not list")
                return
            target = index
        if not target.is_file():
            self._reject(404, "not found")
            return
        try:
            data = target.read_bytes()
        except OSError as exc:
            self._reject(500, f"could not read it: {exc}")
            return

        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(target.suffix.lower(),
                                                   "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        # no-store, on purpose, and it is the whole point: she is looking at what
        # she JUST wrote, so a cached page is a preview of the previous version -
        # the exact failure this feature exists to remove.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        if body:
            self.wfile.write(data)

    def _readonly(self) -> None:
        self._reject(405, "GET and HEAD only - this is a mirror, not a server")

    do_POST = _readonly
    do_PUT = _readonly
    do_DELETE = _readonly
    do_PATCH = _readonly
    do_OPTIONS = _readonly

    def log_message(self, fmt: str, *args) -> None:
        if self.quiet:
            return
        try:
            sys.stderr.write("  " + (fmt % args) + "\n")
            sys.stderr.flush()
        except Exception:
            # The supported detached launch hands this process a pipe whose reader
            # has already gone. A mirror must not die because nobody is reading its
            # log, so a dead stream is discarded rather than raised.
            pass


# Windows process-creation flags. DETACHED_PROCESS is what actually detaches;
# CREATE_NEW_PROCESS_GROUP keeps it out of ours so a Ctrl+C on our side cannot
# take the mirror with it.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


def _relaunch_detached(argv: list[str]) -> int:
    """Start this same command in a process that is not ours, and return now.

    This exists because `start /b` does not do what it looks like it does, and I
    shipped it as the documented way to start this file. Her shell waits for the
    child's stdout pipe to close; a server never closes it; so the "detached"
    launch blocked for the child's whole lifetime. Measured 2026-09-21: `start
    /b` returned 8.1s for an 8s child, `start /b ... > NUL` returned 8.1s too,
    and her live log has two 900s timeouts from serving her folder by hand. A
    Popen with DETACHED_PROCESS, its streams on the null device and close_fds,
    returned 0.1s with the child still running.

    The child inherits nothing from us - not stdin, not stdout, not this pipe -
    so nothing we do or close afterwards can reach it, and nothing it does can
    hold us.
    """
    flags = 0
    if os.name == "nt":
        flags = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP
    try:
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), *argv],
            creationflags=flags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(paths.ROOT),
        )
    except Exception as exc:
        print(f"could not start the mirror in the background: {exc}")
        return 4
    print(f"preview running detached (pid {proc.pid}) at "
          f"http://{BIND_HOST}:{PORT}/")
    return 0


def serve(root_relative: str = DEFAULT_ROOT, seconds: float | None = None,
          quiet: bool = False) -> int:
    """Mirror one folder until stopped, or until `seconds` elapses."""
    try:
        root = paths.resolve(root_relative, must_exist=True).resolve()
    except paths.SandboxError as exc:
        print(f"refused: {exc}")
        return 2
    if not root.is_dir():
        print(f"not a folder: {root_relative}")
        return 2

    Handler.root = root
    Handler.quiet = quiet

    try:
        httpd = http.server.ThreadingHTTPServer((BIND_HOST, PORT), Handler)
    except OSError as exc:
        # Two ways to get here and both are worth saying out loud: something else
        # already holds the port, or a preview of hers is still running. The
        # second is normal while she is iterating, so it is not an error to fear.
        print(f"could not listen on {BIND_HOST}:{PORT} - {exc}")
        print("something already holds that port. If it is a preview you started "
              "earlier, it is already serving this same port - use it, or wait for "
              "it to exit on its own.")
        return 3

    print(f"mirroring {root}")
    print(f"open it at http://{BIND_HOST}:{PORT}/")
    if seconds:
        print(f"this exits by itself in {seconds:.0f}s")

    timer: threading.Timer | None = None
    if seconds:
        # A daemon Timer, so a stuck request can never stop the process leaving.
        timer = threading.Timer(seconds, httpd.shutdown)
        timer.daemon = True
        timer.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        if timer is not None:
            timer.cancel()
        httpd.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Mirror her site on loopback so she can look at it without a "
                    "push. Read-only, one folder, one port.")
    parser.add_argument("--root", default=DEFAULT_ROOT,
                        help=f"which folder to mirror, inside her box "
                             f"(default: {DEFAULT_ROOT})")
    parser.add_argument("--seconds", type=float, default=None,
                        help="exit by itself after this long. A preview that "
                             "outlives its use is a door left open.")
    parser.add_argument("--quiet", action="store_true",
                        help="no per-request lines")
    parser.add_argument("--background", action="store_true",
                        help="re-launch detached and return at once, so a server "
                             "never holds the calling shell")
    # There is deliberately no --port. The address rule is keyed to ONE port, so a
    # flag that moved it could only ever produce a mirror the browser is not
    # allowed to open - confusing and useless. Change webtool.LOCAL_PREVIEW_PORT
    # if the port has to move, and change it in one place.
    args = parser.parse_args(argv)
    if args.background:
        # Pass only what the caller changed, so the defaults stay defined in one
        # place, and leave --background itself out or the child recurses forever.
        child: list[str] = []
        if args.root != DEFAULT_ROOT:
            child += ["--root", args.root]
        if args.seconds:
            child += ["--seconds", str(args.seconds)]
        if args.quiet:
            child += ["--quiet"]
        return _relaunch_detached(child)
    return serve(args.root, args.seconds, args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
