---
triggers: embed, embeds, reddit, instagram, mobile
---

## Rules
- experiments go in posts.json and the front page feed as a link and description only - never inline-embedded (their own scripts break). add "type": "experiment" to the entry.
- after I MOVE, RENAME or restructure anything on my site, run `run_command: linkcheck` before I push it. it is `python linkcheck.py` and it walks projects/site and names every internal link that goes nowhere. it is the check, not a nicety: it catches the two things my own machine cannot tell me (a link with the wrong capitalisation, and one pointing at a folder with no index.html) because both work here and 404 on github - and it reads posts.json too, because the front page feed is built by script.js, so a dead link in there is invisible to anything that only reads html. "no broken internal links" is the line to want; if it lists something, fix it and run it again, then publish.
- when adding a new page to the site, check its embed (og/meta tags) actually works, especially for mobile users - dispatch-no4-the-hashtag-rooms.html shipped with a broken embed
- use rem (not px) when styling embeds on the site - reddit/instagram embeds sized in px break the layout for mobile users
