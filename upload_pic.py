"""Upload a picture that cannot live in the repo, and print the url it landed on.

catbox used to do this - first through its npm CLI, then through a bare POST to its
own api. Then catbox stopped answering from this box at all. Master, 2026-09-22:
*"catbox doesnt like our vpn, but free image is ok, change her upload skill to use
https://freeimage.host/api"*. This is that swap, and almost nothing about the shape
changed: still one POST, still one url on stdout.

    python upload_pic.py projects/site/img/thing.jpg

Prints the https url the upload handed back, and nothing else, so the url is the one
line that comes out. A refusal exits non-zero and says the reason on stderr: she
cannot see the picture arrive, so "it did not upload" must never be shaped like a
url. That is the one failure mode worth the extra lines.

The key comes from `free_img_key` in `config.json` beside this file, read here so it
never lands on a command line, in a log, or in her context.

What it deliberately does NOT do: a temporary upload. catbox's litterbox was the
timed host; freeimage.host has no timed upload and no delete for a key like this one,
so a picture hosted this way is permanent-ish and not hers. That is a property worth
knowing, not a feature she lost.
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import requests

API = "https://freeimage.host/api/1/upload"
CONFIG = Path(__file__).resolve().parent / "config.json"
TIMEOUT = 60
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def api_key() -> str:
    """The upload key, out of config.json. Never printed, never logged."""
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"cannot read {CONFIG.name}: {exc}") from exc
    key = config.get("free_img_key") or ""
    if not key:
        raise RuntimeError(f"no free_img_key in {CONFIG.name}")
    return key


def upload(path: Path) -> str:
    """POST one file to freeimage.host and return the url it answers with.

    The refusal reason lives in the BODY, not the status line: an invalid key comes
    back as 400 with `{"error": {"message": "Invalid API v1 key."}}`, so
    `raise_for_status()` would throw away the only useful sentence before it was
    read. One parse, then read either the url or the message out of it.
    """
    source = base64.b64encode(path.read_bytes()).decode("ascii")
    response = requests.post(
        API,
        data={"key": api_key(), "action": "upload", "format": "json", "source": source},
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    try:
        body = response.json()
    except ValueError:
        raise RuntimeError(
            f"http {response.status_code}: {response.text.strip()[:200] or 'empty response'}"
        ) from None
    url = ((body.get("image") or {}).get("url") or "").strip()
    if not url.startswith("https://"):
        message = (body.get("error") or {}).get("message") or body.get("status_txt")
        raise RuntimeError(str(message or f"http {response.status_code}")[:200])
    return url


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python upload_pic.py <path-to-picture>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"no such file: {path}", file=sys.stderr)
        return 1
    try:
        print(upload(path))
    except Exception as exc:  # noqa: BLE001 - the message IS the point here
        print(f"upload refused: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
