"""Walk her own site and name every internal link that goes nowhere.

Why this exists
---------------
Master, 2026-09-22: *"a little crawler that walks projects/site and reports broken
internal links, because I hand-audit them after every restructure and it's the same
job every time."*

The job is hers, the audit was his. A restructure - a page moved into its own
folder, a slug renamed, a feed entry re-pointed - breaks links in places she is
not looking, and the only thing that noticed was a human opening pages. There was
already a `tmp_linkcheck.py` in her folder doing this by hand with a hardcoded
list of ten pages: proof the job is real, and a version of it that silently stops
covering anything new the moment she adds a page.

What it checks
--------------
Every `.html` file under the root, every `.css`, and `posts.json`.

  - html: `href`, `src`, `srcset`, `poster`, `data-src`
  - css: `url(...)` - a background or font that 404s deletes itself quietly
  - `posts.json`: each entry's `url`. This one is not optional. Her front page
    feed and her ticker are BUILT by `script.js` fetching `posts.json` and
    assigning `a.href = p.url`, so a dead url there is a dead link that no amount
    of reading her HTML would ever show.

Only INTERNAL links are judged: `http(s)`, protocol-relative `//host`, `mailto:`,
`tel:`, `data:`, `javascript:` and in-page `#anchors` are skipped. There is no
network call anywhere in here - a link checker that depends on someone else's
server being up reports the internet's mood, not her site.

The half a human audit on this box CANNOT do
--------------------------------------------
**Case.** GitHub Pages serves her repo from Linux, so a link to `img/Mothman.PNG`
is a 404 there. On Windows it resolves fine, `os.path.exists()` says yes, the
mirror serves it, her browser loads it - and the page someone else opens is
broken. That is not a detail; it is the single most likely way a link that works
here dies on the live site, and it is invisible to any check built on
`os.path.exists`. So every path is walked one component at a time and compared
against the actual directory listing, byte for byte.

Two more shapes that work locally and fail live, for the same reason:

  - `/blog` when the file on disk is `blog.html` - Pages does NOT add the
    extension, it just 404s.
  - a folder with no `index.html` - Pages has nothing to serve for it.

What it deliberately does NOT check
-----------------------------------
Whether the target is committed or pushed. Mid-edit she routinely links a page she
has not published yet, and that is not a broken link, it is a link that is not
live yet - flagging it would train her to ignore the report.

How it is called
----------------
    run_command: linkcheck

That is the shortcut in `runbox.SHORTCUTS` (`python linkcheck.py`). An optional
path scopes the walk:

    python linkcheck.py projects/site/blog

Exit code 1 when something is broken, 0 when the site is clean, 2 when the path
is refused. Non-zero on findings is deliberate: it is the machine-readable half,
so the same check can later sit in front of a push. It does interact with
runbox's three-strikes rule - a report with findings counts as a failed command -
which is the honest reading: running it three times without fixing anything
cannot produce a different answer either.

Read-only. It opens files, lists directories and prints. It writes nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import paths

# Her published tree, named relative and put through paths.resolve() by main(), so
# the wall decides what can be walked rather than a flag from a caller.
DEFAULT_ROOT = "projects/site"

SKIP_DIRS = {".git"}

# `srcset` is checked separately and deliberately: `src\s*=` cannot match it (the
# next character is `s`, not `=`), so the two passes never double-count one link.
ATTR_RE = re.compile(r"""\b(?:href|src|poster|data-src)\s*=\s*["']([^"']*)["']""", re.I)
SRCSET_RE = re.compile(r"""\bsrcset\s*=\s*["']([^"']*)["']""", re.I)
CSS_URL_RE = re.compile(r"""url\(\s*["']?([^"')\s]+)["']?\s*\)""", re.I)
# The card debt. Discord's link preview (the "card") is built from the og:/twitter:
# meta tags, whose URL lives in `content=`, not `src=` - so the attribute scan
# above never saw one break. Master, 2026-09-25: "half my card debt came from
# that". Both attribute orders are real HTML; match either.
META_RE = re.compile(
    r"""<meta\s+(?=[^>]*\b(?:property|name)\s*=\s*["'][^"']*(?:og:image|twitter:image)(?![:\w-])[^"']*["'])"""
    r"""[^>]*\bcontent\s*=\s*["']([^"']*)["']""", re.I)
# Markdown: inline images and links, `![alt](path)` / `[text](path)`. The url
# stops at whitespace or `)`, so a title in the parens survives.
MD_RE = re.compile(r"""!?\[[^\]]*\]\(\s*([^)\s]+)[^)]*\)""")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")

# External by scheme or shape. `#` is in here because a bare fragment is a jump
# inside the page it is written on, not a file.
EXTERNAL_PREFIXES = ("//", "#", "mailto:", "tel:", "data:", "javascript:")

# A page whose findings run past this is a restructure that went wrong, not a
# report - the count still tells the truth, the listing just stops.
DISPLAY_LIMIT = 40


@dataclass(frozen=True)
class Finding:
    """One reference that will not resolve on the live site."""
    kind: str      # "broken", "case" or "outside"
    where: str     # the file the link is written in, relative to the site root
    target: str    # the link exactly as written, so it can be found and fixed
    detail: str    # why, in the words she needs to fix it


def _read(path: Path) -> str:
    """Decode without ever raising - a mojibake page beats an aborted crawl."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if Path(name).suffix.lower() in suffixes:
                found.append(Path(dirpath) / name)
    return sorted(found)


def _refs(text: str) -> Iterator[str]:
    """Every URL-bearing attribute value in one html file."""
    for value in ATTR_RE.findall(text):
        yield value
    for spec in SRCSET_RE.findall(text):
        # "a.jpg 1x, b.jpg 2x" - the descriptor after the url is not part of it.
        for candidate in spec.split(","):
            first = candidate.strip().split(" ")[0] if candidate.strip() else ""
            if first:
                yield first


def _internal(raw: str) -> str | None:
    """The target if it is a link to something in this site, else None."""
    value = (raw or "").strip()
    if not value:
        return None
    low = value.lower()
    if low.startswith(EXTERNAL_PREFIXES) or SCHEME_RE.match(value):
        return None
    # A query and a fragment are not part of the file on disk. `style.css?v=abc`
    # is style.css, and it is the `?v=` rule that keeps her CSS cache-busted.
    value = value.split("#", 1)[0].split("?", 1)[0]
    return value or None


def _exists_exact(root: Path, rel: str) -> tuple[str, str]:
    """Walk `rel` into `root` one component at a time, matching names exactly.

    Returns ("ok", "") | ("case", corrected-path) | ("missing", "").

    `Path.exists()` cannot answer this question, and that is the entire reason
    this function exists rather than one line. Windows folds case, so
    `img/Mothman.PNG` exists here and 404s on Pages, which is Linux. The only
    honest check is to LIST each directory and compare the real names.
    """
    parts = [p for p in rel.split("/") if p and p != "."]
    if not parts:
        return ("ok", "")
    current = root
    for index, part in enumerate(parts):
        try:
            names = {entry.name for entry in current.iterdir()}
        except OSError:
            return ("missing", "")
        if part in names:
            current = current / part
            continue
        folded = {name.lower(): name for name in names}
        if part.lower() in folded:
            real = folded[part.lower()]
            return ("case", "/".join(parts[:index] + [real]))
        return ("missing", "")
    return ("ok", "")


def _verdict(target: str, where: str, root: Path) -> tuple[str | None, str]:
    """Judge one internal link. (None, "") means it resolves."""
    # A backslash is not a folder separator on the web. Windows lets `img\x.jpg`
    # work when the page is opened from disk, and Pages serves it as a filename
    # with a backslash in it, which nothing on disk has - so it is a 404 that
    # only ever shows up live. Reported rather than quietly turned into a slash,
    # for the same reason a case mismatch is: it works here and dies there.
    if "\\" in target:
        return ("broken",
                "a backslash is not a folder separator on the web - use /")

    if target.startswith("/"):
        rel = target.lstrip("/")
    else:
        parent = posixpath.dirname(where)
        rel = f"{parent}/{target}" if parent else target
    # URL space, not filesystem space. os.path.normpath was the first cut and it
    # was WRONG on the one box this runs on: on Windows it rewrites the
    # separators to `\`, so `blog/index.html` walked a single directory entry
    # called `blog\index.html`, found nothing, and reported the whole site as
    # broken. These paths are URLs. posixpath is the module that agrees.
    rel = posixpath.normpath(rel)

    if any(part == ".." for part in rel.split("/")):
        # `../../secrets` from a nested page is not a typo, it is a link out of the
        # site. Pages would 404 it too, but say the real reason.
        return ("outside", "points outside the site folder")
    if rel in (".", ""):
        return (None, "")                    # "/" is the front page

    status, fixed = _exists_exact(root, rel)
    if status == "ok":
        if (root / rel).is_dir():
            inner_status, inner = _exists_exact(root, f"{rel}/index.html")
            if inner_status == "ok":
                return (None, "")
            if inner_status == "case":
                return ("case", f"the page inside it is {inner} - Pages is case-sensitive")
            return ("broken", "folder with no index.html - Pages has nothing to serve")
        return (None, "")
    if status == "case":
        return ("case", f"the file is {fixed} - Pages is case-sensitive")
    # Missing. One shape resolves here and dies live, so name it rather than
    # reporting a bare 404: a link written without the extension.
    if "." not in Path(rel).name:
        candidate = f"{rel}.html"
        if _exists_exact(root, candidate)[0] == "ok":
            return ("broken",
                    f"the file is {candidate} - Pages does not add .html, so this "
                    f"404s live")
    return ("broken", "no such file")


def _judge(raw: str, where: str, root: Path) -> Finding | None:
    target = _internal(raw)
    if target is None:
        return None
    kind, detail = _verdict(target, where, root)
    if kind is None:
        return None
    return Finding(kind, where, target, detail)


def crawl(root: Path) -> tuple[list[Finding], int, int]:
    """Every internal reference in the tree, and every one that goes nowhere.

    Returns (findings, pages, links). A pure read - the smoke test points it at a
    sandbox tree and reads the findings rather than the printed text.
    """
    findings: list[Finding] = []
    pages = 0
    links = 0

    for page in _files(root, (".html", ".htm")):
        pages += 1
        where = _rel(page, root)
        text = _read(page)
        for raw in _refs(text):
            links += 1
            found = _judge(raw, where, root)
            if found:
                findings.append(found)
        # The preview card. Built from meta tags, judged like any other link.
        for raw in META_RE.findall(text):
            links += 1
            found = _judge(raw, where, root)
            if found:
                findings.append(found)

    # The markdown half. Her notes and drafts are .md, and an image path that
    # breaks in a note is the same break it would be on a page. Both markdown
    # syntax and raw html inside md (ATTR_RE) are checked.
    for page in _files(root, (".md",)):
        pages += 1
        where = _rel(page, root)
        text = _read(page)
        for raw in MD_RE.findall(text):
            links += 1
            found = _judge(raw, where, root)
            if found:
                findings.append(found)
        for raw in _refs(text):
            links += 1
            found = _judge(raw, where, root)
            if found:
                findings.append(found)

    for stylesheet in _files(root, (".css",)):
        where = _rel(stylesheet, root)
        for raw in CSS_URL_RE.findall(_read(stylesheet)):
            links += 1
            found = _judge(raw, where, root)
            if found:
                findings.append(found)

    # The feed. script.js builds these links at runtime, so a dead one is
    # invisible to every check that only reads html.
    feed = root / "posts.json"
    if feed.is_file():
        try:
            entries = json.loads(_read(feed))
        except ValueError as exc:
            findings.append(Finding(
                "broken", "posts.json", "(the file itself)",
                f"it will not parse, so the front page feed renders nothing: {exc}"))
        else:
            for entry in (entries if isinstance(entries, list) else []):
                url = entry.get("url") if isinstance(entry, dict) else None
                if not isinstance(url, str) or not url.strip():
                    continue
                links += 1
                found = _judge(url, "posts.json", root)
                if found:
                    findings.append(found)

    return findings, pages, links


def render(findings: list[Finding], pages: int, links: int, label: str) -> str:
    if not findings:
        return (f"no broken internal links - {links} links checked across "
                f"{pages} pages under {label}/.")

    by_page: dict[str, list[Finding]] = {}
    for finding in findings:
        by_page.setdefault(finding.where, []).append(finding)

    lines = [f"broken internal links: {len(findings)} "
             f"(of {links} checked across {pages} pages)"]
    shown = 0
    for where in sorted(by_page):
        lines.append("")
        lines.append(where)
        for finding in sorted(by_page[where], key=lambda f: f.target):
            shown += 1
            if shown > DISPLAY_LIMIT:
                break
            lines.append(f"  {finding.target:<32} {finding.detail}")
        if shown > DISPLAY_LIMIT:
            break
    if shown > DISPLAY_LIMIT:
        lines.append("")
        lines.append(f"... {len(findings) - DISPLAY_LIMIT} more not listed")
    lines += [
        "",
        "fix these, then run linkcheck again - and the mirror first if the page",
        "itself changed (run_command: preview). Nothing here checks the live site:",
        "these are the links, not the deploy.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report every internal link in projects/site that goes nowhere.")
    parser.add_argument("path", nargs="?", default=DEFAULT_ROOT,
                        help=f"what to walk, default {DEFAULT_ROOT}")
    args = parser.parse_args(argv)

    try:
        root = paths.resolve(args.path, must_exist=True)
    except paths.SandboxError as exc:
        print(f"linkcheck: {exc}")
        return 2
    if not root.is_dir():
        print(f"linkcheck: {args.path} is a file, not a folder - nothing to walk.")
        return 2

    findings, pages, links = crawl(root)
    print(render(findings, pages, links, args.path.replace("\\", "/")))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
