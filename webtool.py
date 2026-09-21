"""Browsing the web - carefully.

Every other tool in this folder is boxed by path. This one is boxed by address:
it will fetch public pages and refuses anything that points back inside the
network it runs on.

What that blocks:
  - file://, ftp://, and anything that is not http/https
  - localhost, 127.0.0.0/8, ::1
  - private ranges 10/8, 172.16/12, 192.168/16, fc00::/7, link-local 169.254/16
  - cloud metadata endpoints, by virtue of being link-local
  - a public host that redirects to any of the above: every hop is re-checked

And the ONE address it opens: `preview.py`'s mirror of her own site, on loopback,
on LOCAL_PREVIEW_PORT and nothing else. Master, 2026-09-21 - her site is live the
moment she pushes, so looking at it cost a deploy. The grant is one port wide on
purpose, because this same rule is what stops a page she rendered from reaching
127.0.0.1:445 or the CDP endpoint on :9222.

Residual risk, stated honestly: the address is checked when it resolves, and
urllib connects afterwards, so a hostile DNS server could in principle answer
differently the second time. Owner-only tooling makes that a poor trade for the
extra complexity, but it is a real gap, not a closed one.

Reach: fetch() is one of only three tools offered to people who are NOT
master (tools.LOOKUP_TOOL_NAMES), so this address guard is the only thing
standing between a stranger in a public channel and the network. That is
why the block list is re-checked on every redirect hop rather than once on
the first URL.
"""
from __future__ import annotations

import gzip
import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import zlib

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
TIMEOUT_SECONDS = 20
# 400_000 was a refusal, not a cap: a page bigger than it came back as "I stopped
# early" with no text at all, so a big reference index like sacred-texts.com was
# simply unreadable. Master's call 2026-09-20 - she goes all over the internet for
# research - so the ceiling is 1.5MB now and an oversized page is TRUNCATED and
# returned rather than thrown away. MAX_CHARS is what actually reaches the prompt.
#
# MAX_CHARS was 20_000 and that was measured to be too small on the day it was
# questioned. Three real pages, fetched 2026-09-20: Wikipedia "Sigil" 46,809
# chars (43% delivered), "Austin Osman Spare" 57,698 (35%), Moby-Dick on
# Gutenberg 1,236,074 (1.6%). Every one was chopped, and what a chop loses is the
# END - references, sources, later sections - which is the half research actually
# needs. Master's call: 100_000 chars, about 25k tokens, a whole book chapter in
# one call. MAX_BYTES was already raised for exactly this and the delivery cap
# was quietly chopping the result back down.
MAX_BYTES = 1_500_000
MAX_CHARS = 100_000
# How much of the page is missing, said out loud. The header used to report the
# PAGE size and hide the gap: she read the first 20,000 characters of a 46,809
# character article and had no way to know 26,809 more existed, so a truncated
# source looked like a complete one.
MAX_NOTE_CHARS = 200
MAX_REDIRECTS = 4
ALLOWED_SCHEMES = {"http", "https"}
_REDIRECT_CODES = {301, 302, 303, 307, 308}

# The one address on this machine the guards will open - see the module docstring
# and preview.py. Windows Firewall cannot help here in either direction: 127.0.0.0/8
# is refused at RULE-CREATION time (measured 2026-09-20), so this module is the
# only boundary loopback has. That is why the exception below is keyed to ONE port
# rather than to a range, a hostname or a scheme.
LOCAL_PREVIEW_PORT = 8899

# What the wall SAYS when it says no. Master, 2026-09-22: "the 403 names 8899 and
# hands her the exact command, plus a tiny helper so she never spins up her own
# server again."
#
# It exists because the refusal was CORRECT and USELESS. Her own runbox log,
# 01:14: she started her own `http.server` on 8096, pointed the browser at it, the
# proxy refused it with a bare "refused by lulu's browser proxy" - and she told
# master "the 403 is the browser's proxy being a prude about localhost". She spent
# the rest of the turn rediscovering a rule the wall already knew, and hit the
# 15-minute ceiling doing it. A wall that will not say where the door is costs
# more turn than it ever saves.
#
# The boundary is UNCHANGED by this. It is one string, on the refusing path only,
# naming the single address that already worked.
LOOPBACK_HINT = (
    ".\n"
    "This is not a wall you can climb, and nothing is broken: exactly ONE "
    "address on this machine is open, on purpose.\n"
    "If you were looking at a page YOU wrote, it is already served at "
    f"http://127.0.0.1:{LOCAL_PREVIEW_PORT}/ - you do not need a server of your "
    "own, and starting one lands you right back here.\n"
    "  start it:   run_command: preview\n"
    f"              (which is: python preview.py --background --seconds 300)\n"
    f"  then open:  http://127.0.0.1:{LOCAL_PREVIEW_PORT}/   or any page under it\n"
    "Everything else here stays shut - your own browser's control port among "
    "them - because a page is untrusted content and it must not be able to drive "
    "the browser that is rendering it."
)


def _is_local_preview(host: str, port: int) -> bool:
    """True only for her own mirror: loopback, and exactly the preview port.

    Narrow on purpose, and each narrowing earns its place:

      - the PORT is compared FIRST, so every other loopback listener on this box
        is refused before its name is even resolved. `127.0.0.1:9222` is her own
        browser's CDP endpoint - a steering wheel for the browser that rendered
        the page - and `:445` and `:135` are measured open. None of them is
        reachable through this hole.
      - the HOST must resolve ENTIRELY to loopback. If any answer is a LAN or
        public address the exception does not apply and the ordinary refusal
        runs, so a poisoned name cannot borrow the preview port to reach out.
      - being loopback is not enough on its own. Only this port, only here.
    """
    if port != LOCAL_PREVIEW_PORT:
        return False
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    addresses = [info[4][0] for info in infos]
    if not addresses:
        return False
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        if not ip.is_loopback:
            return False
    return True


class Blocked(Exception):
    """The address is not one we will open."""


def _assert_public(host: str, port: int) -> None:
    """Refuse any address on this machine or the local network."""
    if not host:
        raise Blocked("no host")
    # The one exception, checked HERE on purpose: this function is the single place
    # BOTH doors consult - web_fetch through _check, and the browser through
    # browseguard.check_destination - so an exemption cannot drift into being
    # enforced by one of them and not the other.
    if _is_local_preview(host, port):
        return
    if host.lower() in {"localhost", "localhost.localdomain"}:
        raise Blocked(f"{host} is this machine{LOOPBACK_HINT}")
    if host.endswith(".local"):
        # mDNS is a LAN name, not loopback, so the mirror hint would be a lie
        # here. It gets the plain refusal and nothing else.
        raise Blocked(f"{host} is this machine")
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise Blocked(f"cannot resolve {host}: {exc}") from exc
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            # The hint belongs ONLY where it is true. A LAN address has nothing to
            # do with the mirror, so telling her to look at 127.0.0.1 when she
            # asked for 192.168.x would be a worse message than none at all.
            hint = LOOPBACK_HINT if ip.is_loopback else ""
            raise Blocked(f"{host} resolves to {address}, which is not public{hint}")


def _check(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise Blocked(f"only http and https, not '{parsed.scheme or 'nothing'}'")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    _assert_public(parsed.hostname or "", port)
    return parsed


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Redirects are handled by hand so every hop gets checked."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _decode(raw: bytes, encoding: str) -> bytes:
    if encoding == "gzip":
        try:
            return gzip.decompress(raw)
        except OSError:
            return raw
    if encoding == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return raw
    return raw


def _to_text(body: str) -> str:
    """Strip a page down to something worth reading in a chat message."""
    body = re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", body)
    body = re.sub(r"(?is)<!--.*?-->", " ", body)
    # Keep the shape of the document, drop the markup.
    body = re.sub(r"(?i)<br\s*/?>", "\n", body)
    body = re.sub(r"(?i)</(p|div|li|h[1-6]|tr)>", "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html.unescape(body)
    body = re.sub(r"[ \t\r\f\v]+", " ", body)
    body = re.sub(r"\n\s*\n\s*\n+", "\n\n", body)
    return body.strip()


def fetch(url: str) -> str:
    """Fetch one public page and return it as plain text."""
    target = url.strip()
    if "://" not in target:
        target = "https://" + target

    seen: list[str] = []
    for _ in range(MAX_REDIRECTS + 1):
        _check(target)
        request = urllib.request.Request(target, headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
            "Accept-Encoding": "gzip, deflate",
        })
        try:
            with _OPENER.open(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read(MAX_BYTES + 1)
                encoding = (response.headers.get("Content-Encoding") or "").lower()
                content_type = (response.headers.get("Content-Type") or "").lower()
                final = response.geturl()
        except urllib.error.HTTPError as exc:
            if exc.code in _REDIRECT_CODES:
                location = exc.headers.get("Location")
                if not location:
                    return f"[that page redirected nowhere: HTTP {exc.code}]"
                target = urllib.parse.urljoin(target, location)
                seen.append(target)
                if len(seen) > MAX_REDIRECTS:
                    return "[too many redirects; I stopped]"
                continue
            return f"[HTTP {exc.code} from {target}]"
        except Blocked:
            raise
        except Exception as exc:
            return f"[could not reach {target}: {type(exc).__name__}]"

        raw = _decode(raw, encoding)
        # Cut it, do not refuse it. A page larger than the ceiling still has an
        # answer in its first megabyte far more often than not, and returning
        # nothing is the one outcome that teaches her the page is unreachable.
        clipped = len(raw) > MAX_BYTES
        raw = raw[:MAX_BYTES]

        charset = "utf-8"
        match = re.search(r"charset=([\w\-]+)", content_type)
        if match:
            charset = match.group(1)
        text = raw.decode(charset, "replace")

        if "html" in content_type or "<html" in text[:2000].lower():
            text = _to_text(text)

        where = f" ({final})" if final != target else ""
        note = f", first {MAX_BYTES} bytes of a bigger page" if clipped else ""
        shown = len(text[:MAX_CHARS])
        if shown < len(text):
            # Say what is MISSING, not just what arrived. The old header reported
            # the page's own size, so a chopped article and a complete one were
            # one line apart and she had no way to tell which she was holding.
            missing = len(text) - shown
            header = (f"[{shown} of {len(text)} chars from {target}{where}{note} "
                      f"- {missing} more NOT shown; fetch a narrower page or a "
                      f"section anchor for the rest]")
        else:
            header = f"[{shown} chars from {target}{where}{note} - complete]"
        return header + "\n\n" + text[:MAX_CHARS]
    return "[too many redirects; I stopped]"
