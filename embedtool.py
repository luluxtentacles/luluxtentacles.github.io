# embedtool.py - social media links in my site pages become real embeds.
# master, 2026-09-27, after dispatch no.5 shipped reddit content as bare links
# while no4 carried proper embeds. The rule lives on the `website` shelf; this
# is the tool that enforces it so I never lean on the wrong template again.
#
#   python embedtool.py random/dispatch-no5-the-quiet-lanes.html
#   python embedtool.py random/            # walk a folder
#   python embedtool.py --all random/x.html   # convert EVERY post link, not just lone ones
#
# What it does per file:
#   - finds <a> links to reddit / X / instagram / youtube posts
#   - converts them to the real embed markup (reddit oembed via the api,
#     twitter-tweet / instagram-media blockquotes, a youtube iframe)
#   - injects each provider's widget script once per page, if used
#   - reports every change it made. No output means nothing happened.
#
# Default converts only LONE links - a link that is the only content of its
# paragraph or list item. Prose links (a sentence with the thread linked in
# the middle) are left alone unless --all is passed: a paragraph read as a
# sentence should stay a sentence.

import sys, os, re, json, glob, urllib.request, urllib.parse

HOSTS = {
    # platform: regex matching a POST url (not a user page, not a subreddit front)
    "reddit":   re.compile(r"https?://(?:www\.|old\.)?reddit\.com/r/[^/\s]+/comments/[^/\s\"#]+"),
    "twitter":  re.compile(r"https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+/status/\d+"),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+"),
    "youtube":  re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?[^\"#\s]*v=|youtu\.be/)[A-Za-z0-9_-]+"),
}
SCRIPTS = {
    "twitter":   '<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>',
    "instagram": '<script async src="https://www.instagram.com/embed.js"></script>',
    "reddit":    '<script async src="https://embed.reddit.com/widgets.js" charset="UTF-8"></script>',
}
SKIP_INSIDE = ("reddit-embed-bq", "twitter-tweet", "instagram-media")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def px_to_rem(html: str) -> str:
    """reddit's oembed hands heights back in px; the site rule is rem."""
    return re.sub(r'height:\s*(\d+(?:\.\d+)?)px',
                  lambda m: 'height:%srem' % (round(float(m.group(1)) / 16, 2)), html)


def fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as exc:
        print("  ! fetch failed %s : %s" % (url, exc))
        return None


def reddit_embed(url: str) -> str | None:
    """Ask reddit's oembed api - the html field IS the embed. No key needed."""
    q = urllib.parse.quote(url, safe="")
    html = fetch("https://www.reddit.com/oembed?url=" + q)
    if html:
        try:
            got = json.loads(html).get("html", "")
        except Exception:
            got = ""
        if got:
            return px_to_rem(got)
    # fallback: the hand-built blockquote reddit's own widget builder makes.
    # the widget scans these and builds the iframe itself; height in rem.
    return (
        '<blockquote class="reddit-embed-bq" style="height:18.75rem" data-embed-created="embedtool">\n'
        '  <a href="%s">linked post</a><br>\n'
        '</blockquote>\n' % url
    )


def twitter_embed(url: str) -> str:
    return (
        '<blockquote class="twitter-tweet" data-embed-created="embedtool">\n'
        '  <a href="%s"></a>\n'
        '</blockquote>\n' % url
    )


def instagram_embed(url: str) -> str:
    return (
        '<blockquote class="instagram-media" data-embed-created="embedtool" '
        'style="width:34.5rem; margin:auto">\n'
        '  <a href="%s"></a>\n'
        '</blockquote>\n' % url
    )


def youtube_embed(url: str) -> str:
    m = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', url)
    vid = m.group(1)
    return (
        '<div class="embedtool-video" style="aspect-ratio:16/9">\n'
        '  <iframe width="100%" height="100%" src="https://www.youtube-nocookie.com/embed/%s" '
        'title="embedded video" frameborder="0" loading="lazy" '
        'allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" '
        'allowfullscreen></iframe>\n'
        '</div>\n' % vid
    )


def is_lone(html: str, a_start: int, a_end: int) -> bool:
    """The link is the only real content of its paragraph/list item - a door,
    not prose. Judge the PARENT block: strip the link out and see how little
    of the block's text is left."""
    p_start = html.rfind("<p>", 0, a_start)
    p_end = html.find("</p>", a_end)
    li_start = html.rfind("<li", 0, a_start)
    li_end = html.find("</li>", a_end)
    if p_start != -1 and p_end != -1 and (li_start == -1 or p_start > li_start):
        block = html[p_start:p_end + 4]
    elif li_start != -1 and li_end != -1:
        block = html[li_start:li_end + 5]
    else:
        return False
    block = block.replace(html[a_start:a_end], "")
    text = re.sub(r"<[^>]+>", " ", block)
    return len(text.strip()) <= 40


def convert(html: str, path: str, everything: bool) -> tuple[str, int]:
    made = 0
    used_scripts = set()

    for platform, rx in HOSTS.items():
        for m in list(rx.finditer(html)):
            url = m.group(0)
            # already inside an embed of any kind? leave it
            start = max(0, m.start() - 600)
            ctx = html[start:m.end() + 200]
            if any(tag in ctx for tag in SKIP_INSIDE):
                continue
            # find the <a ...>...</a> around this url (the href may carry a
            # slug after the post id - reddit urls are /comments/<id>/<slug>/)
            a_m = None
            for am in re.finditer(r'<a\s[^>]*href="%s[^"]*"[^>]*>(.*?)</a>' % re.escape(url), html, re.S):
                a_m = am
                break
            if not a_m:
                continue
            if not everything and not is_lone(html, a_m.start(), a_m.end()):
                continue
            if platform == "reddit":
                emb = reddit_embed(url)
                if not emb:
                    continue
            elif platform == "twitter":
                emb = twitter_embed(url)
            elif platform == "instagram":
                emb = instagram_embed(url)
            else:
                emb = youtube_embed(url)
            # the embed is a block element: if it sat inside <p>..</p>, unroll
            # the paragraph around it so the browser does not reflow the
            # blockquote to OUTSIDE the p and leave a stray empty <p> behind
            p_open = html.rfind("<p>", 0, a_m.start())
            p_close = html.find("</p>", a_m.end())
            if p_open != -1 and p_close != -1:
                before = html[p_open + 3:a_m.start()]
                after = html[a_m.end():p_close]
                if not before.strip() and not after.strip():
                    html = html[:p_open] + emb + html[p_close + 4:]
                    made += 1
                    print("  + %s: %s -> %s embed" % (os.path.basename(path), url[:70], platform))
                    continue
            html = html[:a_m.start()] + emb + html[a_m.end():]
            made += 1
            print("  + %s: %s -> %s embed" % (os.path.basename(path), url[:70], platform))
            if platform in SCRIPTS:
                used_scripts.add(platform)

    # widget scripts, once per page, before </body> - and only if not already there
    for platform in used_scripts:
        tag = SCRIPTS[platform]
        probe = tag.split('src="')[1].split('"')[0]
        if probe not in html:
            html = html.replace("</body>", "    " + tag + "\n</body>")
            print("  + %s: injected %s widget script" % (os.path.basename(path), platform))
    return html, made


def main():
    args = [a for a in sys.argv[1:] if a != "--all"]
    everything = "--all" in sys.argv
    if not args:
        print(__doc__)
        return 1
    total = 0
    paths = []
    for a in args:
        a = a.replace("\\", "/")
        if os.path.isdir(a):
            paths += sorted(glob.glob(a + "/**/*.html", recursive=True))
        else:
            paths.append(a)
    for path in paths:
        if not os.path.exists(path):
            print("  ? not found: " + path)
            continue
        with open(path, encoding="utf-8") as f:
            orig = f.read()
        html, made = convert(orig, path, everything)
        if made:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(html)
            total += made
    print("embedtool: %d embed(s) added across %d file(s)%s"
          % (total, len(paths), " (--all)" if everything else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())