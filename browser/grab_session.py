"""Re-jar her logins from the profile master actually signed her in on.

Why this exists
---------------
Her logins reach the bot through JARS, not through her profile. That is not a
preference - it is forced by Windows. A Chromium profile's cookie key is wrapped
by DPAPI for the ACCOUNT that owns the profile, so a browser started as a
different account cannot unwrap it: it regenerates the key and every stored
cookie is orphaned. Measured 2026-09-21, and it cost her the whole profile -
121 cookies down to 11. A jar holds its values in the clear, so it crosses that
account boundary intact. That is the entire reason jars exist.

The half that kept biting her is subtler than "wrong owner", and I had it
backwards until I measured it on 2026-09-23. `browser-profile/` is OWNED (ACL)
by master's account, but its cookie key is wrapped for HER account:
`CryptUnprotectData` refuses it for master's account and succeeds for hers.
Those are two different questions - the ACL decides who may TOUCH the files,
DPAPI decides who may READ them. So her own bot reads her own profile fine, and
it is MASTER opening that profile that breaks it: a browser run as another
account regenerates the key, and every cookie the bot had written is orphaned.
Measured 2026-09-21 - 121 cookies down to 11. That, not an unreadable profile,
is the logout she keeps hitting.

So the flow is:

    1. master opens HER canary on a SEPARATE staging profile and signs in.
       NOT on `browser-profile/` - opening that as master orphans whatever her
       bot put there, and her bot's next launch discards his in turn.
    2. this runs as the account that did the sign-in, reading that profile.
    3. fresh cookies are diffed into browser/*_jar.json.          (here)
    4. her browser injects every jar at launch, as it already does.

Step 2 is not a detail you can skip: run this as the wrong account and the
decrypt fails on the first cookie, which this reports as such rather than as an
empty harvest.

What it will not do
-------------------
- It never prints a cookie value, and it never writes one to a log.
- It will not clobber a working jar with a logged-out one: a domain is only
  refreshed when the profile actually holds a session cookie for it. Signed out
  of reddit means the old reddit cookies stay exactly where they are, and it
  says so - not that the jar quietly empties.
- It leaves a jar it cannot improve alone, so running it twice changes nothing
  the second time.

Usage
-----
    :: sign in FIRST, on a staging profile of your own - never on hers
    "C:\lulu\chrome-canary\chrome.exe" --user-data-dir=C:\lulu\browser-signin
    python browser/grab_session.py --profile C:\lulu\browser-signin
    python browser/grab_session.py --dry-run          # say what WOULD change
    python browser/grab_session.py --domain github.com   # force one in
"""
from __future__ import annotations

import argparse
import base64
import ctypes
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSER = Path(__file__).resolve().parent

# Same override the browser itself honours, so the two can never disagree about
# which profile this is talking about.
PROFILE = Path(os.environ.get("LULU_BROWSER_PROFILE")
               or r"C:\lulu\browser-profile")

COOKIE_DB = Path("Default") / "Network" / "Cookies"

# A name containing any of these, or matching one exactly, means "this domain is
# signed in". Deliberately generous - a missed domain is silent, the failure this
# whole file exists to stop - and paired with a count fallback below, because a
# site that names its session cookie something clever is still a site she is
# signed in to.
SESSION_HINTS = ("session", "token", "auth", "sid", "login", "sso", "jwt",
                 "remember", "oauth")
SESSION_EXACT = {"ct0", "twid", "dses", "li_at", "c_user", "xs", "gaps",
                 "csrftoken", "ds_user_id"}

# Labels that are not registrable on their own, so a grouping split must take
# three labels instead of the usual two. A heuristic, not a public suffix list -
# it only has to be right about the sites she is actually signed in to.
TWO_PART_TLDS = {"co.uk", "org.uk", "ac.uk", "com.au", "net.au", "co.jp",
                 "co.nz", "com.br", "co.za", "com.mx"}

# jar entries, in the order the existing jars already use, so a refreshed jar
# reads like the one it replaced instead of looking churned.
ORDER = ["name", "value", "domain", "path", "secure", "httpOnly", "sameSite",
         "expires"]

# Chromium stores sameSite as a small int; playwright wants the word.
SAMESITE = {0: "None", 1: "Lax", 2: "Strict"}


# --------------------------------------------------------------------------- #
# DPAPI - the OS key that unlocks the profile's cookie key
# --------------------------------------------------------------------------- #
class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_unprotect(blob: bytes) -> bytes:
    """Ask Windows to decrypt a DPAPI blob for THIS account. Raises on failure.

    Failure is the interesting case and the reason this is a hard error rather
    than a None: it means the profile was written by a different Windows
    account, and no amount of retrying here changes that.
    """
    if os.name != "nt":
        raise RuntimeError("DPAPI is Windows-only")
    buf = ctypes.create_string_buffer(blob, len(blob))
    pin = _BLOB(len(blob), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    pout = _BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(pin), None, None, None, None, 0, ctypes.byref(pout)):
        raise RuntimeError("CryptUnprotectData refused this blob")
    try:
        return ctypes.string_at(pout.pbData, pout.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(pout.pbData)


def _master_key(profile: Path) -> bytes:
    """The profile's cookie master key, unwrapped for this account."""
    state = profile / "Local State"
    if not state.is_file():
        raise RuntimeError(f"no Local State in {profile}")
    try:
        raw = base64.b64decode(
            json.loads(state.read_text(encoding="utf-8"))["os_crypt"]
            ["encrypted_key"])
    except Exception as exc:
        raise RuntimeError(f"could not read the cookie key: {exc}") from exc
    if raw[:5] != b"DPAPI":
        raise RuntimeError("the cookie key is not DPAPI-wrapped - unexpected")
    return _dpapi_unprotect(raw[5:])


def _strip_host_hash(raw: bytes, host: str) -> bytes:
    """Drop Chrome's 32-byte domain-hash prefix, when this plaintext has one.

    Chrome 130+ prepends SHA256(host_key) to the plaintext before encrypting, so
    a naive decrypt hands back 32 bytes of hash welded to the front of the
    token - a jar that would carry a login that half-works. MEASURED 2026-09-23
    on this box rather than taken on faith: the prefix is SHA256 of the host_key
    EXACTLY, leading dot included, and the tail behind it is the clean value.
    The match is CHECKED, not assumed, so an older cookie with no prefix passes
    through untouched instead of losing 32 real bytes of its value.
    """
    if len(raw) <= 32:
        return raw
    import hashlib
    if hashlib.sha256(host.encode("utf-8")).digest() == raw[:32]:
        return raw[32:]
    return raw


def _decrypt(master: bytes, blob: bytes) -> bytes:
    """One stored cookie value as BYTES. v10/v11 are AES-GCM; older is DPAPI.

    Bytes rather than str on purpose: the AES-GCM path can carry Chrome's
    32-byte host-hash prefix, and that can only be stripped against the row's own
    host_key, which this function does not have. read_cookies does.
    """
    if not blob:
        return b""
    if blob[:3] in (b"v10", b"v11"):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce, rest = blob[3:15], blob[15:]
        if len(rest) < 16:
            return b""
        return AESGCM(master).decrypt(nonce, rest, None)
    if blob[:5] == b"DPAPI":
        return _dpapi_unprotect(blob[5:])
    return b""


# --------------------------------------------------------------------------- #
# Grouping
# --------------------------------------------------------------------------- #
def registrable(host: str) -> str:
    """A host's registrable domain, for grouping cookies into one jar."""
    labels = host.strip().lstrip(".").lower().split(".")
    if len(labels) <= 2:
        return ".".join(labels)
    if ".".join(labels[-2:]) in TWO_PART_TLDS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def is_session(cookie: dict) -> bool:
    name = (cookie.get("name") or "").lower()
    return (name in SESSION_EXACT
            or any(hint in name for hint in SESSION_HINTS))


def jar_name(domain: str) -> str:
    return domain.split(".")[0] + "_jar.json"


def entry(row: dict) -> dict:
    """One Chromium cookie row as a jar entry, in the jars' own key order."""
    out = {
        "name": row["name"],
        "value": row["value"],
        "domain": row["domain"],
        "path": row["path"] or "/",
        "secure": bool(row["secure"]),
        "httpOnly": bool(row["httpOnly"]),
    }
    if row.get("sameSite") in SAMESITE:
        out["sameSite"] = SAMESITE[row["sameSite"]]
    if row.get("expires"):
        out["expires"] = int(row["expires"])
    return {k: out[k] for k in ORDER if k in out}


def fingerprint(entries: list[dict]) -> str:
    """What "unchanged" means. Values included: a rotated token is a change."""
    return json.dumps(sorted(entries,
                             key=lambda c: (c["domain"], c["name"], c["path"])),
                      sort_keys=True)


# --------------------------------------------------------------------------- #
# Reading the profile
# --------------------------------------------------------------------------- #
def read_cookies(profile: Path) -> list[dict]:
    """Every cookie in the profile, decrypted. Copied first, so a live browser
    writing its WAL cannot have the read fail - or read a torn row."""
    db = profile / COOKIE_DB
    if not db.is_file():
        raise RuntimeError(f"no cookie database at {db}")
    master = _master_key(profile)

    tmp = Path(tempfile.gettempdir()) / f"lulu-cookies-{os.getpid()}.sqlite"
    try:
        shutil.copy2(db, tmp)          # locked by a running browser? copy anyway
    except OSError as exc:
        raise RuntimeError(f"could not copy the cookie database: {exc}") from exc
    try:
        con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "select host_key, name, value, encrypted_value, path, "
                "expires_utc, is_secure, is_httponly, samesite from cookies"
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise RuntimeError(f"could not read the cookie table: {exc}") from exc
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass

    cookies: list[dict] = []
    for (host, name, plain, enc, path, expires, secure, http_only,
         same_site) in rows:
        if not host or not name:
            continue
        value = plain or ""
        if not value and enc:
            try:
                raw = _decrypt(master, enc)
            except Exception as exc:
                raise RuntimeError(
                    f"the cookie key does not belong to this account - "
                    f"{len(rows)} cookies could not be read ({type(exc).__name__})"
                ) from exc
            # Only the AES-GCM path carries the host-hash prefix; the DPAPI
            # branch is already the bare value.
            if enc[:3] in (b"v10", b"v11"):
                raw = _strip_host_hash(raw, host)
            value = raw.decode("utf-8", "replace")
        if not value:
            continue
        # Chromium's expires_utc is microseconds since 1601; playwright wants
        # unix seconds, and 0 means "session cookie, no expiry".
        secs = int((expires - 11644473600000000) // 1000000) if expires else 0
        cookies.append(entry({
            "name": name, "value": value, "domain": host, "path": path,
            "secure": secure, "httpOnly": http_only, "sameSite": same_site,
            "expires": secs if secs > 0 else 0,
        }))
    return cookies


# --------------------------------------------------------------------------- #
# The merge
# --------------------------------------------------------------------------- #
def load_jars() -> dict[str, list[dict]]:
    jars: dict[str, list[dict]] = {}
    for path in sorted(BROWSER.glob("*_jar.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                jars[path.name] = data
        except Exception as exc:
            print(f"  {path.name}: unreadable, left alone ({type(exc).__name__})")
    return jars


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", default=str(PROFILE))
    parser.add_argument("--dry-run", action="store_true",
                        help="say what would change, write nothing")
    parser.add_argument("--domain", action="append", default=[],
                        help="force this registrable domain in, even without a "
                             "recognised session cookie (repeatable)")
    args = parser.parse_args(argv)
    profile = Path(args.profile)

    print(f"reading {profile}")
    try:
        cookies = read_cookies(profile)
    except RuntimeError as exc:
        print(f"  could not read it: {exc}")
        print("  if that mentions the account, run this AS the account that "
              "did the sign-in - a profile is readable only by the account "
              "that wrote it.")
        return 2
    print(f"  {len(cookies)} cookies read")

    groups: dict[str, list[dict]] = {}
    for cookie in cookies:
        groups.setdefault(registrable(cookie["domain"]), []).append(cookie)

    forced = {d.strip().lower() for d in args.domain}
    jars = load_jars()
    covered = {registrable(c["domain"]) for jar in jars.values() for c in jar}

    changed = unchanged = skipped = 0

    for name, stale in sorted(jars.items()):
        domains = {registrable(c["domain"]) for c in stale}
        fresh = [c for d in domains for c in groups.get(d, [])]
        if not fresh:
            print(f"  {name}: no cookies on disk for {', '.join(sorted(domains))} "
                  f"- left as it is (signed out, not erased)")
            skipped += 1
            continue
        # The guard that matters: never replace a working jar with a logged-out
        # one. A domain is only taken if the profile still holds a session cookie
        # for it, or master asked for it by name.
        keep = [c for c in fresh if is_session(c)]
        live = {registrable(c["domain"]) for c in keep} | forced & domains
        if not live:
            print(f"  {name}: no live session in {', '.join(sorted(domains))} "
                  f"- left as it is")
            skipped += 1
            continue
        if fingerprint(fresh) == fingerprint(stale):
            print(f"  {name}: unchanged ({len(stale)} cookies)")
            unchanged += 1
            continue
        print(f"  {name}: {len(stale)} -> {len(fresh)} cookies  CHANGED")
        changed += 1
        if not args.dry_run:
            (BROWSER / name).write_text(json.dumps(fresh, indent=2),
                                        encoding="utf-8")

    for domain in sorted(groups):
        if domain in covered:
            continue
        fresh = groups[domain]
        if not (any(is_session(c) for c in fresh) or domain in forced):
            continue
        name = jar_name(domain)
        print(f"  {name}: NEW, {len(fresh)} cookies from {domain}")
        changed += 1
        if not args.dry_run:
            (BROWSER / name).write_text(json.dumps(fresh, indent=2),
                                        encoding="utf-8")

    print(f"\n{changed} changed, {unchanged} unchanged, {skipped} left alone"
          + (" (dry run - nothing written)" if args.dry_run else ""))
    if not changed:
        print("her jars already match what is signed in - nothing to do")
    return 0


if __name__ == "__main__":
    sys.exit(main())
