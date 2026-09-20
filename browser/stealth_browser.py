"""Lulu's stealth browser - the door she browses through.

Nyan's recipe, ported. One long-lived Edge instance that:

  - uses HER profile (browser-profile/) so cookies and logins persist
  - is headless (master's desktop stays clean)
  - hides the automation tells playwright normally leaves on:
      * no --enable-automation flag
      * --disable-blink-features=AutomationControlled
      * init scripts: navigator.webdriver -> false, a plausible
        window.chrome, plugin/language arrays (Nyan's manual patches)
  - serves a CDP endpoint on 127.0.0.1:9222, which her MCP connects to
    (mcp.json --cdp-endpoint) instead of spawning its own naked browser

Started by lulu_bot at boot (ensure_stealth_browser), kept alive by an
infinite sleep; if her bot dies, this dies with the task, and the next boot
relaunches it. The proxy (browseguard) stays the only network door.

BROWSING ONLY: this makes reading survivable, it does not make posting
safe, and it is not for impersonating a person.
"""
import socket
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE = r"C:\lulu\browser-profile"
CDP_PORT = 9222
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36 Edg/153.0.0.0")

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


def main() -> None:
    if cdp_up():
        print("stealth browser already up on", CDP_PORT)
        return
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE,
            channel="msedge",
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
        # sanity: confirm the tell is actually gone
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("about:blank")
        wd = page.evaluate("() => navigator.webdriver")
        print(f"stealth browser up on CDP {CDP_PORT}, webdriver={wd}")
        while True:                      # keepalive; dies with the task
            time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
