"""MCP stdio client for Lulu.

Speaks JSON-RPC 2.0 over stdio with an MCP server subprocess.
Framing: one JSON message per line (newline-delimited), per the MCP stdio transport.

Lifecycle:
    c = McpClient(command, args, env)
    c.start()          # spawn + initialize handshake
    c.list_tools()     # tools/list, follows pagination cursors
    c.call_tool(name, arguments)  # tools/call
    c.shutdown()       # notifications/initialized already sent; close politely

Two error shapes to handle:
    - JSON-RPC error object in the response (message/code)
    - tool-level error: result.isError == True, real info in result.content
"""

import base64
import json
import os
import queue
import subprocess
import sys
import threading
import time

import paths

# 2025-06-18, not 2024-11-05. The server negotiates down happily either way, but
# the newer version is what the spec and my own mcp-client skill describe, and
# speaking the version you actually implement is the honest default.
PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "lulu", "version": "1.0.0"}
# Per tool call. Generous on purpose: a real browser action can legitimately take
# a while, and a timeout that fires on working code is worse than a slow answer.
REQUEST_TIMEOUT = 60.0
# The first initialize only. A COLD npx has to download the package before the
# server can answer anything at all, and that takes far longer than any tool
# call. This is the case a short timeout turns into a mystery.
START_TIMEOUT = 300.0
# Where a spawned server's dying words go. This used to be DEVNULL, which is why
# a failing server was invisible: the process died and said nothing anywhere, and
# all anyone got was "crashed or exited".
STDERR_LOG = "logs/mcp-stderr.log"


class McpError(Exception):
    pass


class McpClient:
    def __init__(self, command, args=None, env=None):
        self.command = command
        self.args = args or []
        self.env = env
        self.proc = None
        self._next_id = 1
        self.server_info = None
        self._lines = None

    # -- plumbing ---------------------------------------------------------

    def _read_line(self, timeout=None):
        """One JSON message, or a real failure.

        Bounded, because a bare readline() has no timeout and cannot be selected
        on over a Windows pipe: a server that starts and then says nothing - a
        cold download is the usual reason - would hang here forever instead of
        failing with something readable.

        Non-JSON lines are skipped rather than fatal. The spec forbids them on
        stdout but bundled servers are noisy, and one stray log line should not
        read as a broken server.
        """
        budget = REQUEST_TIMEOUT if timeout is None else timeout
        deadline = time.monotonic() + budget
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise McpError(
                    f"server said nothing for {budget:.0f}s - it may still be "
                    f"downloading, or it may be wedged")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                raise McpError(f"server said nothing for {budget:.0f}s") from None
            if line is None:
                raise McpError("server closed stdout (crashed or exited)")
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                print(f"[mcp] non-JSON on stdout: {line[:200]}", file=sys.stderr)
                continue

    def _pump_stdout(self, pipe) -> None:
        """Feed stdout onto a queue so reads can be deadlined."""
        try:
            for line in pipe:
                self._lines.put(line)
        except Exception:
            pass
        finally:
            self._lines.put(None)  # sentinel: the pipe closed

    def _request(self, method, params=None, timeout=None):
        rid = self._next_id
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

        # responses come back interleaved with notifications; skip those
        while True:
            resp = self._read_line(timeout)
            if resp.get("id") == rid:
                break

        if "error" in resp:
            e = resp["error"]
            raise McpError("rpc error %s: %s" % (e.get("code"), e.get("message")))
        return resp.get("result", {})

    def _notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def _send(self, msg):
        assert self.proc and self.proc.stdin
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    # -- lifecycle --------------------------------------------------------

    def spawn_spec(self):
        """The command, environment and cwd to spawn with.

        Factored out of start() so the resolution can be asserted without
        actually launching a process - this is the part that was wrong, and the
        failure looked like a dead server rather than a misconfigured spawn.

        Two things matter here and neither was right before:

        1. The command resolves against the bot's own folder, not against
           wherever this process happens to be standing. mcp.json says
           "node/node.exe" on purpose - an absolute path in a committed config
           would pin the den to one machine - so the resolution has to happen
           here, deterministically, once.

        2. That folder goes on PATH. npx downloads the package and then hands
           off to a BARE `node` to run it, which is a PATH lookup and not an
           absolute path. Searching PATH does not find a runtime that lives
           inside her own folder, so the server died with '"node" is not
           recognized' immediately AFTER a successful download - a 97MB cache
           sat there complete while the spawn looked like a crash.

           Prepending the directory is deliberately not a system PATH edit: it
           does not depend on anything being set up for the lulu-bot account,
           for the same reason run-bot.cmd pins PYTHON instead of trusting it.
        """
        env = os.environ.copy()
        if self.env:
            env.update(self.env)
        command = self.command
        if os.path.isabs(command):
            # An ABSOLUTE command used to be taken at face value, and that was a
            # hole. mcp.json is pipeline-patchable, so a patch could point a
            # "server" at ANY executable on the box - and because start()
            # spawns BEFORE it handshakes, the process would RUN and only then
            # fail to speak MCP: a real side effect wearing a confusing error.
            #
            # So an MCP command must resolve inside her own folder. That keeps
            # the surface auditable (the diff shows a path under her root) and
            # makes the obvious abuse - naming a system binary - impossible.
            #
            # Honest limit: this does NOT stop `node -e "..."`, because node is
            # a general interpreter and running one is the point of having it.
            # The rule constrains WHERE the binary comes from, not what a
            # permitted interpreter can be told to do.
            root = os.path.realpath(str(paths.ROOT))
            resolved = os.path.realpath(command)
            try:
                inside = os.path.commonpath([root, resolved]) == root
            except ValueError:
                # Different drives - commonpath raises rather than answering.
                inside = False
            if not inside:
                raise paths.SandboxError(
                    f"mcp.json names a command outside my folder: {command}. "
                    f"An MCP server has to run from inside {root} - put the "
                    f"binary there and use a relative path like "
                    f"\"node/node.exe\".")
            command = resolved
        else:
            # Relative goes through the wall, which also gives existence a real
            # error instead of a Popen FileNotFoundError at the last moment.
            command = str(paths.resolve(command, must_exist=True))
        binary_dir = os.path.dirname(command)
        if binary_dir:
            env["PATH"] = binary_dir + os.pathsep + env.get("PATH", "")
        return command, env, str(paths.ROOT)

    def start(self):
        command, env, cwd = self.spawn_spec()
        try:
            stderr_path = paths.ROOT / STDERR_LOG
            stderr_path.parent.mkdir(parents=True, exist_ok=True)
            stderr = open(stderr_path, "a", encoding="utf-8", errors="replace")
        except OSError:
            stderr = subprocess.DEVNULL
        self.proc = subprocess.Popen(
            [command] + self.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            text=True,
            # Explicit utf-8: the default is the locale encoding, and on Windows
            # that is cp1252, which dies on the first stray emoji a browser page
            # hands back.
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=cwd,
        )
        self._lines = queue.Queue()
        threading.Thread(target=self._pump_stdout, args=(self.proc.stdout,),
                         daemon=True).start()
        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
            timeout=START_TIMEOUT,
        )
        self.server_info = result.get("serverInfo")
        self._notify("notifications/initialized")
        return result

    def shutdown(self):
        if not self.proc:
            return
        try:
            self._request("shutdown", timeout_hint=None) if False else None
        except Exception:
            pass
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    # -- api ---------------------------------------------------------------

    def list_tools(self, cursor=None):
        """Returns the full tools list, following pagination automatically."""
        tools = []
        while True:
            params = {}
            if cursor:
                params["cursor"] = cursor
            result = self._request("tools/list", params or None)
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools

    def call_tool(self, name, arguments=None):
        """Returns the result dict. Raises McpError on tool-level errors."""
        result = self._request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        if result.get("isError"):
            text = _content_to_text(result.get("content", []))
            raise McpError("tool '%s' failed: %s" % (name, text))
        return result

    def ping(self):
        self._request("ping")


# -- pictures that arrive as content blocks --------------------------------
# An image block is base64 inside a JSON envelope. Serialized into the text
# result - which is what this did until 2026-09-21 - it becomes tens of
# thousands of characters of noise that cost her tokens and show her NOTHING,
# because her vision never sees it. Worst shape of a failure, because it looks
# like an answer: a screenshot arrived, a call was paid for, and she learned
# nothing. Now the block goes to a file and the result names the file, which is
# something she can actually point look_at_file at.
MCP_IMAGE_DIR = "mcp_images"
MCP_IMAGE_MAX_BYTES = 8_000_000
# A stranger can reach mcp_call, and a browser screenshot comes back as one of
# these, so without a floor this is a way to fill her disk a call at a time. The
# newest are kept, the oldest dropped - the picture she is looking at now is the
# newest one by definition.
MCP_IMAGE_KEEP = 40

_IMAGE_EXT = {"image/png": ".png", "image/jpeg": ".jpg",
              "image/webp": ".webp", "image/gif": ".gif"}


def _park_image(item) -> str:
    """One image block written to disk, as a line naming where it went.

    The bytes have to PROVE they are a picture before this saves them, the same
    rule vision applies to an attachment and for the same reason: mimeType is a
    claim the server makes, not evidence. Returns a line either way, so a bad
    block costs her a sentence rather than the whole call.
    """
    import vision  # lazy: only an image block needs the magic-byte check, and
                   # this keeps a low-level client off the feature modules it
                   # would otherwise have to import at startup.
    label = (item.get("mimeType") or "?").split(";")[0].strip()
    try:
        raw = base64.b64decode(item.get("data") or "", validate=True)
    except Exception:
        return f"[an image block ({label}) I could not decode - ignored]"
    mime = vision.sniff(raw)
    if not mime:
        return (f"[a block labelled {label} that is not actually an image "
                f"({len(raw):,} bytes) - ignored]")
    if len(raw) > MCP_IMAGE_MAX_BYTES:
        return (f"[an image block bigger than "
                f"{MCP_IMAGE_MAX_BYTES // 1_000_000}MB - not saved]")
    try:
        folder = paths.resolve(MCP_IMAGE_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        name = (time.strftime("mcp-%Y%m%d-%H%M%S-")
                + os.urandom(3).hex() + _IMAGE_EXT.get(mime, ".img"))
        (folder / name).write_bytes(raw)
    except Exception as exc:
        return f"[could not save an image block: {exc}]"
    _drop_old_images(folder)
    return (f"[an image block ({mime}, {len(raw):,} bytes) saved to "
            f"{MCP_IMAGE_DIR}/{name} - see it with look_at_file]")


def _drop_old_images(folder) -> None:
    """Keep the newest MCP_IMAGE_KEEP parked pictures, delete the rest."""
    try:
        parked = sorted(folder.glob("mcp-*"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for stale in parked[:-MCP_IMAGE_KEEP]:
        try:
            stale.unlink()
        except OSError:
            continue


def _content_to_text(content):
    parts = []
    for item in content:
        kind = item.get("type")
        if kind == "text":
            parts.append(item.get("text", ""))
        elif kind == "image":
            parts.append(_park_image(item))
        else:
            parts.append(json.dumps(item))
    return "\n".join(parts)


def flatten_result(result):
    """Human-readable text out of a tools/call result."""
    return _content_to_text(result.get("content", []))


def load_config(path="mcp.json"):
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg.get("mcpServers", {})


def start_all(path="mcp.json"):
    """Start every server in mcp.json. Returns {name: McpClient}."""
    clients = {}
    for name, spec in load_config(path).items():
        c = McpClient(spec["command"], spec.get("args"), spec.get("env"))
        c.start()
        clients[name] = c
    return clients
