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
MAX_BYTES = 1_500_000
MAX_CHARS = 20_000
MAX_REDIRECTS = 4
ALLOWED_SCHEMES = {"http", "https"}
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class Blocked(Exception):
    """The address is not one we will open."""


def _assert_public(host: str, port: int) -> None:
    """Refuse any address on this machine or the local network."""
    if not host:
        raise Blocked("no host")
    if host.lower() in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
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
            raise Blocked(f"{host} resolves to {address}, which is not public")


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
        header = f"[{len(text)} chars from {target}{where}{note}]"
        return header + "\n\n" + text[:MAX_CHARS]
    return "[too many redirects; I stopped]"
