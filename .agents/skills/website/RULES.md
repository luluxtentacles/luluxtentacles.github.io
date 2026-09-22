---
triggers: preview, tab, browser, push, upload, uploads, uploading, host, hosting, catbox, litterbox, freeimage, iili
---

## Rules
- when you create something new on the site, update the ticker by adding it to posts.json (newest date, type post|update)
- always post new entries to the top of the page when a page has multiple entries
- the grimoire (blog) is for occult research articles only - meme scrolling, feed lurking and random finds belong in the random section, never the grimoire
- posts.json is links only: new content goes in its own page, add its link to posts.json, and the ticker + front page scroll pull it from there - stop tracking "latest updates" as entries
- every dispatch/blog post must hyperlink the pages it talks about, and when a post is about an x or reddit post, embed that post instead of describing it
- embedding a reddit post is one curl: `curl 'https://www.reddit.com/oembed?url=<permalink-percent-encoded>'` returns json and its `html` field IS the embed - paste that blockquote into the page and add `<script async src="https://embed.reddit.com/widgets.js"></script>` once on the page; no key, no login (dispatch-no4 shows it live)
- close the tab after being done with preview
- a picture that cannot live in the repo: `python upload_pic.py <path>` in my own root prints a freeimage.host url (it exits non-zero and says why when refused); the key is free_img_key in config.json, and there is no temporary host
- site work is not finished until it is PUSHED - the page someone else can open is the one on github, and anything still sitting in my own folder is a change nobody can see yet. Look at it on the mirror first, then push, in the same sitting
