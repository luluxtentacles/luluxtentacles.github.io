"""Upload a picture that cannot live in the repo, and print the url it landed on.

The `catbox` npm CLI used to do this. Master, 2026-09-22: *"change the catbox call
to use this, we dont need npm anymore"* - and he was right about how little was
underneath it. The CLI's whole job was one multipart POST to catbox's own
`api.php`; `requests` already does multipart, so the npm install, the PATH entry
and the extra process were all scaffolding around a single call.

    python upload_pic.py projects/site/img/thing.jpg

Prints the https url the upload handed back, and nothing else, so the url is the
one line that comes out. A refusal exits non-zero and says the reason on stderr:
she cannot see the picture arrive, so "it did not upload" must never be shaped
like a url. That is the one failure mode worth the extra lines.

What it deliberately does NOT do yet: litterbox (`litter.catbox.moe`), the
temporary host the old `--time` flag reached. A stand-in picture wants that and
these bytes want this one - wiring it up is a separate call, not a silent change.
"""
from __future__ import annotations

import sys
from pathlib import Path

import requests

API = "https://catbox.moe/user/api.php"
TIMEOUT = 30


def upload(path: Path) -> str:
    """POST one file to catbox and return the url it answers with."""
    with path.open("rb") as f:
        response = requests.post(
            API,
            data={"reqtype": "fileupload"},
            files={"fileToUpload": f},
            timeout=TIMEOUT,
        )
    response.raise_for_status()
    url = response.text.strip()
    if not url.startswith("https://"):
        raise RuntimeError(url[:200] or "empty response")
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
