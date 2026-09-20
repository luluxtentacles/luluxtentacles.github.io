"""A filtering forward proxy, so the browser has ONE door out.

Why this exists at all
----------------------
`web_fetch` enforces a public-address rule in code: `webtool._assert_public`
resolves a host and refuses anything on this machine or the local network. The
BROWSER has no such rule and cannot be given one - it is a separate process that
makes its own connections, and the two flags that look like the answer are not.
From `@playwright/mcp --help`, on BOTH `--allowed-origins` and
`--blocked-origins`:

    Important: *does not* serve as a security boundary and *does not* affect
    redirects.

So a page that 302s to `http://127.0.0.1:445/` sails through them. Windows
Firewall cannot close that either, and this is measured rather than assumed:
`127.0.0.0/8` and `::1/128` are refused at RULE-CREATION time -

    An unspecified, multicast, broadcast, or loopback IPv6 address was specified

- because the WFP layer does not filter the loopback interface. That is why the
account-wide firewall rule covers the LAN and nothing else, and why loopback is
handled HERE instead, at the application layer, where chromium can be made to
obey.

    127.0.0.1:445 (SMB) and 127.0.0.1:135 (RPC) were both measured OPEN on this
    box. That is the surface this file closes.

How it works
------------
Chromium is launched with `--proxy-server`, which it genuinely honours for
HTTP(S). Every request therefore arrives here FIRST, as a request line naming a
host - and this is the one place where a host can be checked before any packet
is sent to it. A refusal is answered with 403 and never dialled.

Both proxy shapes are handled, and they fail differently, so both are checked:
  - plain HTTP   `GET http://host/path HTTP/1.1` - the absolute URL is in the
                 request line, so the host is read from it
  - HTTPS        `CONNECT host:443 HTTP/1.1` - the host is in the request line
                 and everything after it is an opaque tunnel, which means THIS
                 CHECK IS THE ONLY ONE THERE WILL EVER BE for that connection.
                 A tunnel that gets established is not re-inspected.

What this is NOT
----------------
It is a real boundary for page loads and it is not a jail for the browser
process. Chromium's own DNS, preconnect, and WebRTC paths do not go through a
proxy, so a determined page still has side channels this cannot see. What it
removes is the easy one - navigation to a local address, whether typed,
redirected to, or fetched from a page - and it makes that refusal happen before
a socket opens rather than after.

Bound to loopback only, and it is deliberately NOT a general-purpose proxy: it
has no cache, no auth, no PAC, and it forwards nothing it has not checked.
"""
from __future__ import annotations

import ipaddress
import selectors
import socket
import threading

import webtool

# Where chromium will be told to send everything. Loopback ONLY: a proxy that
# listened on 0.0.0.0 would be an open relay for the whole network, which is a
# far bigger hole than the one this file exists to close.
BIND_HOST = "127.0.0.1"
# A fixed, unremarkable high port. Not 8080 - that is the first thing anything
# scans, and this does not need to be guessable by anything but the browser we
# launch ourselves.
DEFAULT_PORT = 38123

# How long a single request may take end to end, and how long a CONNECT tunnel
# may sit idle. A browser keeps connections alive, so the idle bound is generous
# and the request bound is not.
REQUEST_TIMEOUT = 30.0
TUNNEL_IDLE_TIMEOUT = 120.0
BUFFER = 65536

# A request line longer than this is not a request we are willing to parse.
# Unbounded header reading is how a proxy is turned into a memory problem.
MAX_REQUEST_LINE = 8192


class Refused(Exception):
    """The destination is not one this proxy will open."""


def check_destination(host: str, port: int) -> None:
    """Refuse anything on this machine or the local network.

    Deliberately a thin call into webtool's own rule rather than a second copy
    of it. The whole point of this file is that the browser obeys the SAME
    address policy `web_fetch` already enforces, and two implementations of one
    policy is two places for it to drift - the fetch path would keep refusing
    while the browser quietly stopped.
    """
    webtool._assert_public(host, port)


def _parse_authority(authority: str, default_port: int) -> tuple[str, int]:
    """`host:port` or `host` into a pair. Bracketed IPv6 is handled."""
    authority = authority.strip()
    if not authority:
        raise Refused("no host")
    if authority.startswith("["):
        end = authority.find("]")
        if end == -1:
            raise Refused(f"unbalanced bracket in {authority!r}")
        host = authority[1:end]
        rest = authority[end + 1:]
        if rest.startswith(":"):
            return host, _port(rest[1:], default_port)
        return host, default_port
    if authority.count(":") == 1:
        host, _, raw_port = authority.partition(":")
        return host, _port(raw_port, default_port)
    # Bare IPv6, or a host with no port.
    return authority, default_port


def _port(raw: str, default_port: int) -> int:
    raw = raw.strip()
    if not raw:
        return default_port
    try:
        port = int(raw)
    except ValueError:
        raise Refused(f"{raw!r} is not a port")
    if not (1 <= port <= 65535):
        raise Refused(f"port {port} is out of range")
    return port


def parse_request_line(line: str) -> tuple[str, str, str, int]:
    """`(method, target, host, port)` out of a proxy request line, or Refused.

    Both shapes land here because both name their destination in the request
    line - which is exactly why a proxy can make this check and a browser
    cannot.
    """
    parts = line.split()
    if len(parts) != 3:
        raise Refused(f"malformed request line: {line[:120]!r}")
    method, target, _version = parts
    method = method.upper()

    if method == "CONNECT":
        host, port = _parse_authority(target, 443)
        return method, target, host, port

    # Absolute-form: http://host:port/path. If it is not absolute we cannot
    # know where it is going, so we refuse rather than guess at a Host header.
    lowered = target.lower()
    if not lowered.startswith(("http://", "https://")):
        raise Refused(f"not an absolute URL: {target[:120]!r}")
    scheme, _, rest = target.partition("://")
    authority = rest.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    default_port = 443 if scheme.lower() == "https" else 80
    host, port = _parse_authority(authority, default_port)
    return method, target, host, port


def _read_line(sock: socket.socket, limit: int = MAX_REQUEST_LINE) -> str | None:
    """One CRLF-terminated line, bounded.

    Returns the line WITHOUT its terminator, so a blank line comes back as `""`
    and is a real answer. `None` means the peer went away - a distinction that
    has to exist, because the first cut returned `""` for BOTH and the header
    reader therefore could not tell "headers are over" from "the client left".
    That collapsed into a reset instead of a clean refusal, which is exactly
    what the live socket probe caught.
    """
    buf = bytearray()
    while len(buf) < limit:
        try:
            chunk = sock.recv(1)
        except (ConnectionResetError, OSError):
            return None
        if not chunk:
            return None
        if chunk == b"\n":
            return buf.decode("latin-1").rstrip("\r")
        buf += chunk
    raise Refused(f"request line over {limit} bytes")


def _read_headers(sock: socket.socket) -> list[str]:
    """Headers up to the blank line, bounded, kept verbatim for forwarding.

    The blank line is the terminator, so an empty line ends the loop. `None`
    (peer gone) and an oversized block both raise rather than returning a
    half-read request that would then be forwarded as though it were whole.
    """
    headers: list[str] = []
    total = 0
    while True:
        line = _read_line(sock)
        if line is None:
            raise Refused("client closed mid-headers")
        if not line:
            return headers
        total += len(line)
        if total > MAX_REQUEST_LINE * 4:
            raise Refused("headers too large")
        headers.append(line)


def _pump(src: socket.socket, dst: socket.socket, timeout: float) -> None:
    """One direction of a tunnel, until either end closes or idles out."""
    src.setblocking(False)
    dst.setblocking(False)
    sel = selectors.DefaultSelector()
    sel.register(src, selectors.EVENT_READ)
    try:
        while True:
            if not sel.select(timeout=timeout):
                return
            try:
                data = src.recv(BUFFER)
            except (BlockingIOError, InterruptedError):
                continue
            except OSError:
                return
            if not data:
                return
            try:
                dst.sendall(data)
            except OSError:
                return
    finally:
        sel.close()


def _tunnel(client: socket.socket, upstream: socket.socket) -> None:
    """Shuttle bytes both ways until either side stops."""
    up = threading.Thread(target=_pump,
                          args=(client, upstream, TUNNEL_IDLE_TIMEOUT),
                          daemon=True)
    up.start()
    try:
        _pump(upstream, client, TUNNEL_IDLE_TIMEOUT)
    finally:
        for sock in (client, upstream):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _handle(client: socket.socket) -> None:
    """One client connection: parse, check, then either refuse or forward.

    ORDER MATTERS, and this is the bug the live probe found twice. Windows sends
    an RST rather than a clean FIN when a socket is closed with unread data
    still in its receive buffer, and an RST DISCARDS anything already written to
    it. So a refusal issued before the request's headers were read would be sent
    successfully and then thrown away - the browser saw a connection reset
    instead of the 403.

    The fix is to drain the headers FIRST, then decide. Every path below has an
    empty receive buffer by the time it closes, which is what makes a clean
    close possible. The order is not stylistic; it is the difference between the
    browser reading "refused" and the browser reading "the proxy is broken".
    """
    try:
        client.settimeout(REQUEST_TIMEOUT)
        line = _read_line(client)
        if line is None:
            return
        if not line:
            return

        # Drain the header block BEFORE any decision. See the docstring: this is
        # what stops the RST that would eat our own refusal.
        try:
            headers = _read_headers(client)
        except Refused as exc:
            _refuse(client, f"bad headers: {exc}")
            return

        try:
            method, target, host, port = parse_request_line(line)
        except Refused as exc:
            _refuse(client, f"bad request: {exc}")
            return

        # THE CHECK. Before a single byte is dialled, and the only one a CONNECT
        # tunnel will ever get.
        try:
            check_destination(host, port)
        except webtool.Blocked as exc:
            _refuse(client, str(exc))
            return
        except Refused as exc:
            _refuse(client, str(exc))
            return

        upstream = socket.create_connection((host, port), timeout=REQUEST_TIMEOUT)

        if method == "CONNECT":
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            _tunnel(client, upstream)
            return

        # Plain HTTP: replay the request in ORIGIN form, which is what an
        # ordinary web server expects, along with the headers as received.
        path = target
        for prefix in ("http://", "https://"):
            if path.lower().startswith(prefix):
                rest = path[len(prefix):]
                slash = rest.find("/")
                path = rest[slash:] if slash >= 0 else "/"
                break
        upstream.sendall(f"{method} {path} HTTP/1.1\r\n".encode("latin-1"))
        for header in headers:
            upstream.sendall((header + "\r\n").encode("latin-1"))
        upstream.sendall(b"\r\n")
        _tunnel(client, upstream)
    except Exception:
        # A proxy must never take the browser down with it; the connection is
        # simply closed and the page reports a failure, which is the honest
        # outcome for a request that did not work.
        pass
    finally:
        try:
            client.close()
        except OSError:
            pass


def _refuse(client: socket.socket, reason: str) -> None:
    """Tell the browser no, in a shape it will render rather than retry."""
    body = (f"refused by lulu's browser proxy: {reason}\n").encode("utf-8")
    head = (
        "HTTP/1.1 403 Forbidden\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("latin-1")
    try:
        client.sendall(head + body)
        # Half-close after answering, rather than letting the caller's close() do
        # it. SHUT_WR flushes a clean FIN the browser can read to end-of-body;
        # a bare close() on this side has already been observed to arrive as an
        # RST and take the 403 with it.
        try:
            client.shutdown(socket.SHUT_WR)
        except OSError:
            pass
    except OSError:
        pass


class Proxy:
    """The listener. `start()` returns once it is accepting, not after a run."""

    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((BIND_HOST, self.port))
        sock.listen(64)
        self._sock = sock
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        """Accept forever. A bad connection must not end the listener.

        The first cut caught OSError around accept() and RETURNED - so one
        connection that failed in any way killed the whole proxy, silently, and
        every request after it got a connection reset. The live probe caught it
        as `403` on the first request and `ConnectionResetError` on the second,
        which is the exact signature: the guard dies after doing its job once.

        A closed listener socket is the ONLY reason to stop, and that is what
        `self._sock` being None means. Everything else is one connection's
        problem and stays that connection's problem.
        """
        while True:
            sock = self._sock
            if sock is None:
                return
            try:
                client, _addr = sock.accept()
            except OSError:
                # Closed by stop(), or a transient accept failure. Only the
                # former is a reason to leave.
                if self._sock is None:
                    return
                continue
            threading.Thread(target=_handle, args=(client,),
                             daemon=True).start()

    def stop(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


def proxy_url(port: int = DEFAULT_PORT) -> str:
    """What goes on chromium's command line."""
    return f"http://{BIND_HOST}:{port}"


def main() -> int:
    """Run it in the foreground. Master only, and only to watch it work."""
    proxy = Proxy()
    proxy.start()
    print(f"proxy listening on {proxy_url(proxy.port)}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        proxy.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
