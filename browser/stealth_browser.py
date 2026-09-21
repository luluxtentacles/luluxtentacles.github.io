r"""Lulu's stealth browser - the door she browses through.

Nyan's recipe, ported. One long-lived Chromium instance - Chrome Canary, run
from a copy inside this folder - that:

  - uses HER profile (browser-profile/) so cookies and logins persist
  - is headless (master's desktop stays clean)
  - hides the automation tells playwright normally leaves on:
      * no --enable-automation flag
      * --disable-blink-features=AutomationControlled
      * init scripts: navigator.webdriver -> false, a plausible
        window.chrome, plugin/language arrays (Nyan's manual patches)
  - serves a CDP endpoint on 127.0.0.1:9222, which her MCP connects to
    (mcp.json --cdp-endpoint) instead of spawning its own naked browser

WHY A COPY, AND WHY BY PATH. Canary's real install sits under
C:\Users\Kei\AppData\Local\Google\Chrome SxS, and that path's ACL grants
lulu-bot explicit NO ACCESS - inherited, so her boxed account cannot read it,
which is why the browser was Edge in the first place: Edge is under Program
Files and readable by anyone. The same trap as node/, which her own run-bot.cmd
complains about. So Canary is copied to chrome-canary/ inside her folder, where
it inherits Users:RX. Because it is a copy, channel="chrome-canary" could never
find it - playwright resolves a channel to the standard install locations - so
it launches by executable_path instead. The copy is frozen at 156.0.8066.0 and
will not auto-update: that is the price of owning it.

Started by lulu_bot at boot (ensure_stealth_browser), kept alive by an
infinite sleep. The proxy (browseguard) stays the only network door.

Known, not yet fixed (measured 2026-09-21): a launch counts as "already up" if
the PORT answers, so a wedged or foreign browser squatting 9222 makes every
boot decline to start a fresh one; and because the keepalive holds the process
past its parent's death, a launcher can outlive the task as a sleeping orphan.
Eight of them were found, none of them hers to kill.

BROWSING ONLY: this makes reading survivable, it does not make posting
safe, and it is not for impersonating a person.
"""
import os
import socket
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE = r"C:\lulu\browser-profile"
CDP_PORT = 9222
# Chrome Canary, copied into her folder 2026-09-21. By path, not by channel:
# playwright's channel lookup only knows the standard install locations, and the
# standard location on this box is master's profile, which denies lulu-bot.
CANARY = r"C:\lulu\chrome-canary\chrome.exe"
# The UA has to match the engine it rides on, or it IS the tell. This said
# "Edg/153" while the binary was Edge; on Chromium the Edg/ token would be the
# odd thing out. Kept as an override at all because the thing that must not
# show is headless - without it the UA advertises "HeadlessChrome". Major-only
# is not laziness: UA reduction means real Chrome sends major.0.0.0.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36")

# Nyan's manual patches: the bits playwright-stealth would set.
STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
window.chrome = {runtime: {}, loadTimes: function() {}, csi: function() {},
                 app: {isInstalled: false}};
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications'
        ? Promise.resolve({state: Notification.permission})
        : origQuery(parameters));
"""


def cdp_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", CDP_PORT), timeout=1):
            return True
    except OSError:
        return False


def _parent_alive(pid: int) -> bool:
    """Is the process that launched me still running?

    The keepalive below holds this browser open forever, so a launcher could
    outlive the bot that started it and sit there sleeping. EIGHT of them were
    found doing exactly that on 2026-09-21, every one of them impossible for her
    to clear because they had been started by hand from another account. "Dies
    with the task" was aspirational prose; this makes it true.
    """
    if pid <= 0:
        return True              # nothing to watch: never close early on a guess
    import ctypes
    SYNCHRONIZE = 0x00100000
    WAIT_TIMEOUT = 0x00000102
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return True              # cannot watch it - assume alive, do not kill
    try:
        return kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
    finally:
        kernel32.CloseHandle(handle)


def main() -> None:
    if cdp_up():
        print("stealth browser already up on", CDP_PORT)
        return
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE,
            executable_path=CANARY,
            headless=True,
            user_agent=UA,
            proxy={"server": "http://127.0.0.1:38123"},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--remote-debugging-port=%d" % CDP_PORT,
                "--no-sandbox",
            ],
            ignore_default_args=["--enable-automation"],
        )
        ctx.add_init_script(STEALTH_SCRIPT)
        # Nyan's flow: sessions that do not survive a fingerprint change are
        # injected fresh at every startup, from a jar in this folder. The jar
        # holds live login values - gitignored, never logged, never sent.
        jar = Path(__file__).parent / "instagram_jar.json"
        if jar.is_file():
            import json
            try:
                ctx.add_cookies(json.loads(jar.read_text(encoding="utf-8")))
                print(f"instagram jar injected: {jar.name}")
            except Exception as exc:
                print(f"jar injection failed: {exc}")
        # sanity: confirm the tell is actually gone
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("about:blank")
        wd = page.evaluate("() => navigator.webdriver")
        print(f"stealth browser up on CDP {CDP_PORT}, webdriver={wd}")
        # Keep the process alive for as long as the BOT is alive, and no longer.
        # Without the check below this loop is why orphan launchers accumulated:
        # nothing here ever noticed its parent was gone.
        parent = os.getppid() if hasattr(os, "getppid") else 0
        while True:
            time.sleep(60)
            if not _parent_alive(parent):
                print("the bot that started me is gone - closing with it")
                break


if __name__ == "__main__":
    sys.exit(main())
