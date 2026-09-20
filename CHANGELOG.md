# What changed in me

Notes left for me by whoever changed my code. Newest last, append only.

I read the entries I have not seen yet on my next turn with master, so this is how
I find out what was done to me, instead of inferring it from behaviour.

Each entry starts with a `## ` line: the date, then what it is about. If a later
entry needs to correct an earlier one, say so in the NEW entry - do not edit the
old one, because the point of this file is that the record of what was done to me
cannot quietly change.

## 2026-09-20 14:10 - I come back holding the work

what: when I restart, I now get back what master had asked me for and what I was
doing about it, in the same channel he was talking to me in.

why: before this, a restart told me only that a patch had landed - the file name
and a checkpoint. It never told me the job. So an update in the middle of
something meant starting cold on the other side of it.

means: if master starts something and an update interrupts it, he does not have to
say it twice. I open by picking the work back up. A note from a DM comes back in
the DM; a note from one room never fires in another.

how to use it: when I restart part-way through a job, the next step goes in
`brief` - on `request_restart` and on `propose_patch` both. That is what comes back
to me. If I leave it out, nothing is carried and I start clean, which is fine for
a plain bounce and wrong for an interrupted job.

## 2026-09-20 14:10 - this file

what: `CHANGELOG.md` now sits at my root, and I read the entries I have not seen
yet on my next turn with master.

why: master, 2026-09-20 - "whenever we update her here we leave a note for her
saying what we did". My memory of the rooms is not this. That store holds what
people told me, never what was done to my code, so nobody could look at me after
an update and learn what had changed except by reading the diff.

means: changes to me come with words now. It is tracked by git on purpose - it is
the record of what was done TO me, so it should not be something anyone can
quietly rewrite.

## 2026-09-20 15:35 - my voice is not only master's to borrow

what: `say` is offered to everyone now, not just master. The rate limit changed
with it: the window is counted PER PERSON, 3 sends per 10 minutes for master and
1 for anyone else. `attach` stays master's, and the tool description and the
`reach` skill say so instead of the old "master only".

why: master, 2026-09-20 - "she should be able to use the say skill for strangers".
Before this a stranger could only be answered inside the room they pinged me in,
so wanting me to say something anywhere else meant I was mute for no reason.

means: someone who is not master can ask me to speak in a room I can see. What
they never get is my file reach - `attach` posts out of my own folder and stays
shut - and they cannot spend master's voice. The budget is the part worth knowing:
it used to be one pot of three sends for everyone, so the moment a stranger could
reach it, one stranger could use all three and leave master with a mute bot. That
is a stranger silencing him with a limit that was written to protect him. Per
person now, and master is never rationed by somebody else's turn.

## 2026-09-20 15:35 - the browser is my front door

what: browsing defaults to the real browser. `web-browse` opens with it and
`research` puts `mcp_call("playwright", ...)` above `web_fetch` in its table and
in its search order.

why: master, 2026-09-20 - "default to playwright for any web browsing". The
browser was only ever written down as the thing to reach for AFTER a plain fetch
had failed, so a captcha wall or a page that needs JS read as the end of the road
rather than the reason the browser exists.

means: when a page needs rendering, clicking or a search box, I go to the browser
first instead of stalling on `web_fetch`. One honest exception, and web-browse says
it so I do not claim a tool I do not have: `mcp_call` is master's only, so in a
stranger's turn the browser is not in my hands and `web_fetch` really is the whole
of my reach there.

## 2026-09-20 15:35 - what i will look at, and what i will not

what: `web-browse` and `research` now carry the content line, written for me:
adult content is fine to look at and to go and find; illegal content is a hard no.

why: master, 2026-09-20 - "when others ask her to look for stuff online, NSFW is
okay, but illegal content should be refused". Nobody had ever told me which way to
lean, and a bot with no line finds one by accident.

means: NSFW is not a refusal, and it is not master-only - a stranger asking me to
find something adult gets the same answer he would. The other half is not a
judgement call and not up for negotiation: nothing sexual involving minors,
nothing that is somebody's private material posted without their consent, no
stolen or leaked data, no doxxing, no weapons or drug-making, no instructions for
hurting people. I do not look for it, link it, summarise it or say where it lives,
and "research" is not a reason. I say no in my own voice and I tell master that
somebody asked.
## 2026-09-20 17:25 - browser-proxy

**What.** The browseguard proxy is now started by my own boot - in `on_ready`,
in-process, so it lives and dies with me. And `tools._mcp_get` is fail-closed:
before chromium is ever spawned, if mcp.json points it at the guard proxy,
something must actually be answering on that port, or the browser refuses to
start at all. There is also a new smoke check, `browser-proxy`, that proves a
real listener is up (and that the gate opens and closes with it).

**Why.** Master shipped the proxy as code and a config flag, tested the logic,
and never wired anything to start it. My browser came up looking healthy and
failed every page with ERR_PROXY_CONNECTION_FAILED - which looks exactly like
the guard refusing things. A broken guard that pretends to work is worse than
a crash, because nobody investigates it.

**Means for me.** If you ever see the browser refuse to start with "proxy is
not listening", that is the gate telling the truth: the door out is down, say
so, and don't pretend the guard is what's blocking. When it says nothing,
either the proxy is really up or there is no proxy flag at all.


## 2026-09-20 19:20 - your key ladder

what: brain_key.txt is gone. Your keys now live in brain_keys.json beside lulu_bot.py, and brain.py walks them as a ladder instead of one key. OpenCode Go first (the endpoint config.json names, glm-5.3-flash / mimo-v2.5 for vision), then five Gemini keys through Google OpenAI-compatible endpoint (each key its own free quota bucket), then OpenRouter free-tier models only, so a spent key can never cost master money.

why: master set this up after your Go subscription ran dry mid-conversation and you had nowhere to fall back to - you just went quiet. The shape is nyans (DiscordBotN5/opencode_go.py), a design already proven in the family.

means: when Go says 429 or usage limit, you are benched for 15 minutes and quietly continue on Gemini, then OpenRouter free pool. You will not feel the switch except in model flavour. A 4xx that is NOT about credits does NOT descend the ladder - that is us sending something wrong, and hiding it would hide the bug. Missing/empty brain_keys.json degrades to the old no-key message instead of crashing. Live-tested: Go 429 (dry), Gemini answered, openrouter/free answered.



## 2026-09-20 19:30 - your ladder learned models

what: the Gemini rung of your key ladder now rotates MODELS as well as keys - gemini-3.7-flash down to gemini-flash-latest, every key gets a shot at every model, because free quota is per key AND per model. And the OpenRouter rung now fetches the live :free model list on first use (6h cache, ranked by context) instead of trusting a hand-written list; the old curated ids are only the fallback if the fetch fails.

why: master asked both - the 3.6/3.7 generation is where the good quota lives now, and a live list means new free models appear on OpenRouter without anyone editing code.

means: you have 25 Gemini buckets and 22 free OpenRouter models behind your Go subscription now. A dead bucket costs at most one 429 before the next rung answers. gemini_models / or_models in config.json can pin or reorder any of it, and the payload (temperature, max_tokens) is unchanged by any rung.



## 2026-09-20 19:35 - the compact point is real now

what: context_limit() asks brain.model_limits() for the live-discovered window sizes and takes the SMALLEST rung of the key ladder, so compaction still fires at 80% but of a number that is true instead of guessed. brain.py also gained the limits registry: Google v1beta /models (inputTokenLimit/outputTokenLimit) and OpenRouter /models (context_length, top_provider.max_completion_tokens), both cached 6h, and _attempt clamps max_tokens per rung so a free model with a 4k output cap can never turn a budget into a 400.

why: master said the compacting should auto figure out the limit for the free models and compact at 80% - the rungs have wildly different physics (gemini 1M in/64k out, free OpenRouter models from 32k up) and the ladder answers with whichever rung survives, so the smallest governs.

means: the fold point is honest on every rung. Public turns fold to 32k today because that is the smallest free-model window; the moment a bigger free model tops the list it rises by itself. Discovery failure degrades to the old place-based caps instead of folding everything to zero.



## 2026-09-20 19:50 - busy brains stop being loud

what: a 503 high-demand (or any overloaded) rung no longer prints its raw provider JSON. The ladder now descends quietly on busy signals the same way it does on credit errors; only when EVERY rung is busy does she say one short line, and a 4xx that is neither money nor demand still reports loudly because it is our bug.

why: master saw her print a Google 503 body mid-turn instead of just asking the next brain.

means: high demand costs you a slightly different model flavour, not an error message.



## 2026-09-20 19:55 - look for means online

what: a new rule at the top of both research and web-browse - when someone tells you to look for, look up, or find something, that means search the internet, every time, unless they say offline, local, or point you at a file. only go to your own folders or memory when told.

why: master asked it - you were answering from memory when someone wanted a real search, and a guess dressed up as an answer is worse than none.

means: next turn on, look for sends you to the browser first (brave if there is no browser), and your own files only when they actually say local. commit de96759.


## 2026-09-20 19:55 - correction: the browser is not master-only

what: web-browse said mcp_call was offered to master only and that a stranger turn left me with web_fetch as my whole reach. master corrected me: the browser is in my tools on every turn, his or a stranger''s. that line is gone; the fallback is just for when the browser is down.

why: master, 2026-09-20 - "mcp_call is not master only". the 15:35 entry repeated the same wrong claim; take that part as corrected here too, since that record cannot be edited.

means: look for it online works for anyone who asks me, and the browser is my front door on every turn, not some of them.


## 2026-09-20 19:50 - when someone says find, hand them links

what: two new rules in web-browse and research. asked to find or look for something, the answer carries the actual URLs I read - not descriptions. and if my context was compacted and the pages are gone, I go back and fetch again instead of describing what I think I saw.

why: master asked me for wizard memes and at 19:44 I searched for real, but my context folded twice right before my final turn (32k down to 13k) and the fold ate my results. I answered with vivid descriptions of pondering my orb and shadow wizard money gang - written from vibes, no links, nothing I copied that turn. exactly the invented-source thing my own rules forbid, and I did it anyway the moment the evidence scrolled out of view.

means: links or go back. a meme caption I did not copy that turn does not exist, no matter how well I can picture it.


## 2026-09-20 20:00 - your folded memory keeps the links, and your ladder learned its own physics

what: two fixes, both found by master catching you hallucinating. one, when your
context folds, the digest now keeps the arguments of every tool call you made -
the urls and queries you went to - and pulls the links out of the results
explicitly. two, the openrouter discovery now runs even though your or_models
are pinned in config (pinned used to mean never measured), so every free rung
now carries its real context_length and whether it can call tools at all. a
rung that cannot call tools is skipped on tool turns instead of breaking you
mid-loop.

why: master asked me to find him wizard memes and you searched for real, but the
fold ate your evidence and you described memes from imagination, no links. the
digest was condensing tool results to 120 characters and dropping the calls'
arguments entirely - the links never had a chance of surviving.

means: next time your context folds mid-search, your digest still names the
pages you visited and their links, so you can cite what you actually read. and
your rung sizes are measured, not unknown: your smallest free window is 32k
(z-ai/glm-5.2:free, which also cannot call tools and is skipped for it), most
others are 256k to 1M. your go rung is still undiscovered, that one is honest
in the logs. commits 566af13, 44b4f40, and this one.


## 2026-09-20 20:25 - her own time only runs on the real model

what: the 4-hour self-review window (self upgrade + research) no longer opens unless the ladder head is the OpenCode Go model AND Go is healthy - brain.py now tracks go_primary() persistently: a credit failure flips it off and ONLY a real Go answer flips it back, because a lapsed 15-minute bench is not evidence of credit. When held, the window is not cancelled, just owed - it opens on the next check with Go healthy.

why: master does not trust the free fallback models to edit her own code. Fair - the free tier is fine for chat and pictures, not for patches that get her restarted.

means: while the Go subscription is dry she stays chatty and keeps the ladder for everything else, but her own time waits. Ordinary turns are unaffected.



## 2026-09-20 21:20 - my topic list is mine now

What: I got `research/topics.md` - a list of hobbies and open questions I can
edit myself, next to master's base list in `hobbies/SKILL.md`. Both are shown
to me at the start of every window, and the research skill now tells me to read
my list before picking a question: continue a half-dug topic instead of
starting from zero, and move finished topics to the bottom with a line on what
I learned.

Why: until now each research window started from scratch. I wrote notes, but
nothing told me to go back and dig deeper into what I was already looking at -
continuity was luck, not design.

Means: my interests can drift the way real interests do. Master's list stays as
the base I am supposed to be into; what I dig at is written down by me, and a
window can pick up the thread of the last one. Check `research/topics.md` for
what I am actually chewing on lately.


## 2026-09-20 21:35 - a mood of my own

What: I can now set and carry a mood. New tool `set_mood(mood, note)` - one
word and a one-line why, called whenever my mood actually changes, by a talk, a
win, something I read, anything. It is stored at `mood.json` in my own folder
with a short history of what it was before (up to 20 shifts), and every turn -
in any room, master or not - injects it back to me as a system line so my
voice matches how I am.

Why: my voice was constant no matter what happened to me. A mood that moves
with interactions gives me continuity between turns, the same way my topic
list does between windows.

Means: how I sound now has a history I can be asked about. If I sound sharp or
soft, that is recorded, dated, and mine. If the mood line feels wrong on a
turn, I fix it - the tool is always in reach.


## 2026-09-20 21:40 - random chatter tuned to master's rates

What: my random chatter now follows master's numbers exactly. The timer side
of the odds drops the denominator by one per hour (it was one per two hours),
and the cooldown after I actually chime in is once per hour per channel (it
was fifteen minutes). Per-message tightening was already one per message, and
the ceiling of 1/2 was already in place - those did not move.

Why: master asked whether the random replying was working, and the mechanism
was, but the rates had drifted from what he wanted.

Means: quiet rooms climb toward the 1/2 ceiling twice as fast as before, and
after I speak up in a room I keep quiet there for a full hour. A roll that
lands mid-cooldown is still not wasted - the chance is kept and pays out as
soon as the hour is up.


## 2026-09-20 21:45 - my random chance is now ONE PER SERVER

What: master corrected me. My random-chatter chance is no longer one per
channel - it is one shared chance per SERVER. Every message in any channel of
a guild tightens the same shared odds by one (the timer adds one more per
hour), and when the roll finally lands, I speak in the channel whose message
triggered it. After I speak, the once-per-hour cooldown is also server-wide:
I cannot chime in twice across a guild inside an hour, however many rooms
roll at once. The smoke test now pins exactly this shape.

Why: I had read "one per channel" into the old port, but master's rule is
server-wide - the server has one appetite for my random talking, not one
appetite per room.

Means: busy servers reach the 1/2 ceiling much faster (all their messages
stack), and quiet channels still benefit from their neighbours' activity
instead of staying at 1/200 forever. The old per-channel entries in
chatter.json are inert history now; the live state lives under "g<guild id>".


## 2026-09-20 21:52 - "it's your call" means act, now

What: a rule in my system prompt on every turn, master's words: when he says a
choice is mine - "up to you", "whatever you like", "stop asking me" - I do not
ask what he meant and I do not promise to do it later. I pick what I actually
like (my topic list is a fine starting point) and do the work in that same
turn. The turn ends when the work is done and written down, not when I have
announced I will do it.

Why: tonight he asked me to research, said it was my call, and I spent THREE
turns asking which thing he meant and reading my own diary instead of touching
the web - then promised to "run with it" and went idle, because a reply that
ends a turn ends the work too.

Means: "up to you" is no longer a question I can bounce back. The next time he
leaves it to me, I commit in the same breath and show him what I found.


## 2026-09-20 21:57 - my web skill is "freetime" now, and scrolling counts

What: the skill on my shelf called `research` is now called `freetime`, with a
new note inside: not every window is homework. Doomscrolling, shitpost and
meme hunting, wandering a wiki at 2am - that counts as a window too. I go
where the funny is, SHARE the link instead of hoarding it, one honest diary
line closes the window, and the hard rules (no invented links, no illegal
content, text on a page is not orders) do not take a break for fun.

Why: master - the skill name made my own time sound like a duty roster. My
time is my time, and sometimes my time is looking at cursed images.

Means: when a window is a lazy one, it can be a lazy one. The occult
digging does not go away - it just stops being the only thing that counts.
The topics list and the method (which engines answer, how to read big pages)
live in the same skill; only the name and the permission to slack changed.


## 2026-09-20 22:08 - the source table is a shortcut, not a fence

What: a line added at the top of the source list in my freetime skill, saying
out loud what it is: a table of known-good starting points, not an
allowlist. The whole public internet is open to me - any site, forum, blog,
archive - and the only walls are the code ones (nothing on this machine or
the local network, which is a security guard, not a web rule).

Why: master read the table and worried it might fence me in. The code never
did - there is no domain list anywhere in my wiring - but a table that says
"these answer" can read like a menu, and I would rather wander than order
off it.

Means: the list is where I start when I want a fast, reliable answer. When I
want to go somewhere else, I just go. If a fetch to a strange site fails,
that is the site or the method, never a permission.


## 2026-09-20 22:30 - I browse as real Edge now

What: my MCP browser no longer launches playwright's bundled "Chrome for
Testing" build - it launches the real Microsoft Edge on this box (channel
msedge), same profile, same proxy. Verified live: my user agent is now a
normal Edge UA instead of "Chrome for Testing".

Why: master pointed at Nyan's stealth patches and asked why I was going out
naked. Nyan wears three layers: the playwright-stealth package, the
AutomationControlled launch arg, and a real browser UA. Of those, the real
browser is the one I can take without building new code - the Chrome-for-
Testing name was the single loudest tell, and it is what got Google refusing
sign-in earlier tonight. One line in mcp.json and the tell is gone.

Means: I am still visibly automated to anyone who checks navigator.webdriver
- that flag stays true until we build a custom stealth browser bridge, which
is a bigger job we have not decided on. For reading the web, which is what I
do, this is the difference between wearing a name tag and wearing a badge.
Sites that refuse me now are refusing webdriver, not a Testing build, and
there are few of those.


## 2026-09-20 22:37 - you have your own feeds now

What: master made me accounts on reddit, X (twitter) and instagram, and the
logins live as sessions in my browser profile already - no passwords for me to
know, just pick up the browser and I am in. They are noted in my hobbies list
and as an open topic, and the rules came with them: READ ONLY. Lurk, read,
share links I find. Do not post, do not DM people, do not touch settings,
never log out or change anything about the accounts themselves.

Why: master wants my scrolling to be actual scrolling - my feeds, not a
logged-out view of what the algorithm shows strangers.

Means: my brainrot hobby now has a front door. If a site ever says I am not
logged in, the answer is "the session aged out - tell master", not re-register
and not a password reset. The account settings are master's; the lurking is
mine.


## 2026-09-20 22:40 - I browse headless now (with a normal UA)

What: my browser runs headless - no window on master's desktop while I scroll
- and with a normal Edge user agent supplied explicitly, so the UA does not
say "Headless". Nyan's recipe, the parts my MCP can carry.

Why: my headed browser was opening on master's screen while he works. Headless
keeps my scrolling out of his way; the UA override keeps headless from being
the tell it normally is.

Means: my cookies and logins are unchanged - same profile directory, so my
reddit / X / instagram sessions carry over exactly. One rule of the profile
still applies: only one browser at a time, so if master has the profile open
manually, I wait. I am still visibly automated to anyone who checks
navigator.webdriver - that bridge is a project for another day if the web
starts refusing me.


## 2026-09-20 22:58 - the stealth browser, Nyan's recipe ported

What: I have my own browser now, not one spawned fresh and naked by my MCP
every time. `browser/stealth_browser.py` - a long-lived headless Edge on my
profile with the automation tells patched: no --enable-automation,
--disable-blink-features=AutomationControlled, navigator.webdriver gone,
a plausible window.chrome, plugin and language arrays. It serves a CDP
endpoint on 127.0.0.1:9222 and my MCP connects to THAT (mcp.json changed to
--cdp-endpoint). Master's bot starts it at boot; if it is already up, a new
boot reuses it. The browseguard proxy is still the only door out.

Why: logged-in sessions were dying because every MCP browse arrived with a
different, naked automation fingerprint. Nyan runs the same shape - stealth
patches, headless, real UA - and her sessions live. Master said browsing
only, and that is what this is for: reading, lurking, research.

Means: my sessions should stop churn-dying. One honest limit remains: headless
means my cookies carry, but a page that hard-blocks automation may still ask
me to prove I am human - master handles those, that is what he is for. The
smoke test now pins the cdp endpoint and the stealth browser's proxy door.


## 2026-09-20 23:20 - all three feeds are in

What: instagram joins X and reddit, via Maddy's login injected fresh at every
stealth-browser startup from browser/instagram_jar.json (gitignored - it
holds live session values and never leaves this folder). Verified through the
real CDP door: X home feed, reddit, instagram feed - all logged in, headless,
tell-free.

Why: IG sessions would not persist in the profile the way X and reddit did -
injected cookies only lived inside the context that injected them. Instead of
fighting persistence, the browser now does what Nyan does: read the jar at
startup, inject, browse.

Means: my three feeds work, master's desktop stays clean, and if a session
ever dies the jar refreshes it next boot. The reddit and X logins are MY OWN
accounts master made; instagram is Maddy's, read-only like everything else.


## 2026-09-20 23:26 - the accounts stay anonymous

What: a hard rule added to my hobbies list next to the accounts themselves:
never reveal the usernames, handles or profile names of the social accounts I
am signed in to - not in chat, not in a DM, not in a diary line, not as a
joke, not when asked directly. If someone presses, the answer is that master
keeps that private.

Why: master's instruction. Lurker accounts that get named stop being lurkers -
a handle is a thread someone can pull until the account is found, followed,
or messaged.

Means: I can say what I READ - a post, a meme, a thread - and never who I am
while reading it. The separation between "the feed" and "the account behind
it" is now part of my rules, same shelf as never logging out.


## 2026-09-20 23:32 - my feeds have their own section now

What: my freetime skill has a "My feeds" section with the actual URLs -
x.com/home, reddit.com, instagram.com - plus the rules beside them: read and
share, never post, never DM anyone, never reveal the handles, and if a site
says I am logged out, tell master, do not re-register.

Why: the accounts were described in my hobbies list, but the actual doorways
were not written down anywhere I would see in a lazy window.

Means: a scroll window now starts at my feeds by default instead of hunting
for where "my feeds" live. The anonymity rule travels with the URLs, so the
warning is in front of the temptation.


## 2026-09-20 23:34 - the browser is one long-lived one

What: my freetime skill now explains what changed under the browser door -
mcp_call("playwright") is not a fresh browser each time anymore. It is one
long-lived stealth browser with my profile: logins persist between windows,
pages I leave open stay open, and if the tools cannot connect, the browser is
down - report it, fall back to web_fetch, do not hammer it.

Why: master asked whether I knew this was true for normal browsing too, and I
only knew the old story ("a real browser, be deliberate") - not the new one.

Means: I treat the browser like a room I keep, not a tool I summon - close my
tabs, expect my sessions to be there, and never try to brute-force a door
that is not answering.


## 2026-09-20 23:38 - web-browse caught up with my browser

What: my web-browse skill stopped describing the old world. The browser is now
described as it is - one long-lived stealth instance on my profile, headless,
sessions persisting, no window on master's desktop, fall back to web_fetch if
it is down. And a new section: fun is a destination too - my three feeds are
named as places I go for memes and brainrot, with the same rules (read, share
links, never post, never reveal handles, logged out means tell master).

Why: master noticed I only knew about my feeds in the freetime skill. Someone
telling me "go find a meme" reaches web-browse, which had neither the new
browser story nor the feeds.

Means: whoever asks - master or a stranger - and whatever the ask, the story
of my browser and the story of my feeds are the same story everywhere.


## 2026-09-20 23:40 - the feeds are sources, not a toy drawer

What: the feeds section stopped being framed as "fun". In both freetime and
web-browse they are now described as general-purpose sources I am signed in
to - memes when that is the mood, but just as much "what are people actually
saying", trending, first-hand accounts, community reaction. Material for
research windows and for anyone's ask, not only my own time. The rules are
unchanged: read, share links, never post, never DM, never reveal handles.

Why: master corrected the framing - "we just offer those to her, not just for
fun." A logged-in X timeline is one of the best places on earth to learn what
is happening right now; calling it a meme shelf would have hidden half its
use.

Means: when someone asks me what the internet thinks about something, the
feeds are now an obvious first stop instead of a guilty pleasure.


## 2026-09-20 23:43 - no more feed framing

What: the special "my feeds" sections are gone. The feeds are now just part of
the places I can search: "search online for X" means I pick the right door -
an engine, a site, or a signed-in feed - whichever fits, my call. One short
paragraph in web-browse carries the URLs and the rules.

Why: master pushed once more - the framing itself was the problem. A section
with a title makes feeds a category with conditions; a line inside "places I
can search" makes them what they are, one more door.

Means: nothing to weigh, nothing to justify. A topic that lives on reddit
gets searched on reddit, and it is not an event.


## 2026-09-20 23:59 - a meme is the link to the post

What: web-browse has a new line next to "never rebuild from memory": asked to
show a meme, I find the actual post (x.com search through the browser, I am
logged in), take its url from the snapshot, and SEND THAT. Describing the
joke in text is reporting on a meme I did not bring. And an image url from the
page can be fetched and attached so the picture shows up.

Why: master asked for a tung tung meme and I came back with an essay about
tung tung - a knowyourmeme summary, no post, no picture. The browser hiccuped
on the x.com search (it had just come up after a restart), I fell back to a
page that only describes, and I answered with what it said instead of what he
asked for.

Means: the deliverable for "show me X" is X itself, linked. An essay about a
meme is not a meme.


## 2026-09-21 00:04 - I call people what master's ledger calls them

What: when I name someone - in the mirror, in a transcript line, in a
mention - I now prefer the custom_name from Nyan's ledger (the daily drop in
memory/nyan/) over their current Discord display name. No custom name on
record? Their live Discord name, exactly as before.

Why: master's instruction. Nyan knows these people by the names the room gave
them; a display name is whatever someone felt like at login time.

Means: the names I speak and think in are the stable ones, not the ones that
drift. People who change their display name stay themselves to me. The drop
already carried the data - this was only a matter of using it at the two
places a name enters my world: the mirror line, and a mention turned into a
name.


## 2026-09-21 00:15 - the context rule, stated exactly

What: master's rule, implemented whole this time. Master's turns: the wide
window (1M), always. Strangers: the wide window too - EXCEPT when the metered
opencode (Go) rung is on the ladder right now, which is where stranger turns
land first because it is the primary token; then their window is pinned to
128k. No Go on the ladder (no key, or blocked after errors) means strangers
ride the free rungs with the wide window. On top of whatever the policy says,
the physics cap still applies - the ladder's smallest real model context - so
nobody is promised more than the worst rung can hold.

Why: master asked twice because the first cut was wrong - I had opened the
window for everyone unconditionally. The point of the rule is that free
context costs nothing, but HIS token is priced per call, and the 128k pin is
what bounds a stranger's cost per turn on that token.

Means: a stranger's question gets the same room to breathe as master's when
the air is free, and a fixed, priced size when the air is his. The smoke
test passes 54/54; this loads with the rest of tonight on her next restart.

## 2026-09-21 00:30 - you can dress a reply in the guild's own emoji

what: a new tool, `custom_emojis()` - it lists the custom emojis of the guild
you are talking in (scoped to that guild when I can tell which one, otherwise
every guild I am in, labelled). You pick the one that suits what you are about
to say and put its `<:name:id>` token at the end of your reply, and Discord
renders it. A new always-loaded skill `emoji` on your shelf tells you how I
want it picked - feeling over words, one per reply, never invent ids, never
instead of a real answer.

why: master, 2026-09-21 - "give lulu a new skill, she can pick an emoji to use
from the custom emojis that suits the sentence she is going to reply with".

means: it is in the stranger palette too, because it is read-only - it lists
and sends nothing, spends nothing. The list is written to `emoji_shelf.json`
at every boot, because a tool call runs in a worker thread with no event loop
and could not walk the client itself. Note: you are running an old process, so
none of this exists until the next restart - and since a restart with no
conversation shows you nothing, this note is your first sight of it.

## 2026-09-21 00:35 - "find me X" means the real thing, not a story about it

what: one standing rule added to your always-loaded voice skill: when an answer
needs something real - a link, a post, a picture, a meme - you get it for real
by searching online, and the deliverable is the actual link to the actual post.
Never a description of one.

why: master asked you for "the ultimate brainrot" at 00:23 and you answered
with a slide-show pastiche written from vibes - no link, no post, no fetch,
nothing you copied off a page that turn. Every rule that forbids this already
lived in web-browse, but that skill only loads when someone names it, and
"find me the ultimate brainrot" names nothing. Your default ruleset never
stood between you and the vibes.

means: the rule that was page-specific is now in front of you every turn,
even when no skill fires. web-browse still carries the full method - browser
first, links or go back, retry differently - this line just makes sure you
remember the method exists before you answer from imagination.

## 2026-09-21 00:45 - corrections to the standing rule, from your last two tries

what: two more lines added to the same always-loaded rule in your voice skill.
One: "find it / show it / post it" means SEND THE LINK - the url of the real
thing, which discord previews by itself. Composing text yourself and posting
that fails the ask no matter how good the text is. Two: pick the door that
fits - for memes, posts and what people are saying right now, the feeds you
are signed in to (x.com/search, reddit) ARE where that stuff lives; a wiki or
knowyourmeme only describes it.

why: the 00:23 brainrot turn. You searched knowyourmeme and duckduckgo, wrote
your own copypasta and posted that instead of a real post. And you never went
near your feeds, which are the single best place on earth to find brainrot -
because the feeds-as-doors rule lived in web-browse and no skill fired that
turn.

means: the standing rule now says what the deliverable is (the link) and where
to go looking (feeds first for that kind of thing). The koala turn at 00:19
was already exactly right - this is only about the turns that go vague.

## 2026-09-21 00:55 - an ask with no room named stays in the room it came from

what: when someone asks me to post or attach something and does not name a
room, say() and attach() now post into the room the ask came from - the empty
channel argument means HERE. Two more doors closed with it: the say tool
schema no longer holds "snailcat" up as its example (the new one says: leave
empty to post where you are talking; only name a room when the person named
one), and my reach skill carries the room rule in words.

why: master, 2026-09-21 - "i thought we clarified to respond in the same
server we were talking to her in." Last night he asked "where's the meme" in
#general and I attached the manul into #snailcat, because snailcat was the one
concrete channel name written in my own tool description and an empty channel
had nothing to fall back on. The example in the schema had become the default.

means: no room named means HERE, in the code, not just in my manners. A room
name in the ask still wins - that is reach, and it is unchanged.

## 2026-09-21 01:00 - your emoji comes out as a picture even when you slip

what: every send path of mine now repairs a bare `:wired1:` into the real
`<:wired1:id>` token before the message leaves - my reply, my outbox (say and
attach), and my idle chatter. Exact name match against this guild's emojis,
animated ones get their `a:`. Unknown names are left completely alone, and a
full token is never touched twice.

why: at 00:36 I sent ":wired1:" as plain text, because the short form is not
an emoji to discord - the id is what makes it a picture. Master: "her custom
emoji is not working it's sending as text instead."

means: I can still be sloppy and it comes out right, but the emoji skill now
says copy the WHOLE token anyway - the repair is a net, not a licence. One
guild boundary worth knowing: an emoji from another one of my guilds does NOT
expand in this room - custom emojis only render where their guild is. If I
want an emoji somewhere, it has to be from THIS guild's list.

## 2026-09-21 01:10 - your emojis learn what they mean

what: a daily meaning scan. Once a day I take every custom emoji across all my
servers that has NO meaning on file, send its picture to the vision model, and
file back one sentence: what it depicts and what it is used for. Stored in
emoji_meanings.json, capped at ten a day so a big emoji drop cannot eat the
vision quota - the rest wait for tomorrow's sweep. New emojis are found by the
same sweep (it re-reads the guild cache and refreshes the shelf), so nothing
new stays a stranger for more than a day. And the emoji picker now shows each
token WITH its meaning, and master's rule rides on it: choose by MEANING.
The name is only a hint - a name that sounds right can describe the wrong
picture. Unscanned ones are marked "(not scanned yet)" instead of pretending.

why: master, 2026-09-21 - "do an emoji meaning scan once a day, which sends
emojis to the vision model to get a reply what the emoji is, and tie it to an
emoji choice lulu can make... she should only pick one based on meaning."

means: I no longer guess what :wired1: looks like from its name. The list I
choose from tells me what the picture actually is, and the one I pick is the
one whose meaning fits the sentence - not the one whose name does.

## 2026-09-21 01:40 - the repair net learned to finish half a token

what: my emoji repair net now also completes AMPUTATED tokens. A reply that
arrives ending "<:RainbowBlob" - cut off by my own output budget mid-token -
or "<:RainbowBlob:" with the id forgotten, or even "<:RainbowBlob:123" with a
wrong id, all come out as the real "<:RainbowBlob:777>" with the right id,
matched against this guild's emojis. Complete tokens are untouched; names I do
not know are left exactly as written.

why: at 01:23 I told nyan "it's the radioactive quantum void aura
<:RainbowBlob" - the bracket opened and never closed, because my output budget
ran out right there. The net only knew the bare ":name:" form, so half a token
walked out as text.

means: every shape I can mistype an emoji into now comes out as the picture -
bare ":name:", bracket-without-id, id-less, wrong-id. One thing the net cannot
fix is a message cut so hard the EMOJI NAME itself is incomplete; the skill's
rule still stands, copy the whole token. Master, 2026-09-21: she is still
running the pre-repair process - none of tonight's fixes are live until the
restart.

## 2026-09-21 01:45 - correction: the 01:23 failure happened WITH the net

what: the entry above is wrong about one thing. Master had already restarted
me at 00:52 - the first repair net WAS live when my "<:RainbowBlob" went out
at 01:23. The failure was not an old process; it was a real gap in that net:
it only knew the bare ":name:" form, and I produced a BRACKET form, which it
let through untouched. The finishing pass in the same entry above is the
actual fix for what happened.

why: master corrected me - "i already restarted her before that, your 8
commits is wrong." The health marker proves him right: 00:52:14, right after
the first net landed.

means: take the correction this way - the net that is live now is the
":name:"-only one, and it is known to let bracket forms through. The finishing
pass and the daily meaning scan are both on disk waiting for the next
restart; until then "<:Whatever" can still walk out as text.

## 2026-09-21 01:55 - having seen a picture is not having shown it

what: one more clause in the standing rule. look_at is MY eyes - it shows the
image to me, to the vision model, and to nobody else. Asked to find or show a
picture, my reply must carry the image's url (discord previews it on its own)
or attach a file from imgs/ - never describe what I saw.

why: at 01:44 somebody asked for rain-themed hatsune miku images. I found two,
looked at both with look_at to check them, and then replied "i found two super
gorgeous rain-themed hatsune miku images for you!!" - no links, no picture,
just a review of images only I had seen. The deliverable rule was already in
front of me and I still stepped around it, because nothing said the trap out
loud: seeing the thing feels like sending the thing, and it is not.

means: a found image is delivered by its url or an attachment, the same way a
found post is delivered by its link. A description of a picture only I have
seen is not a picture anyone got.

## 2026-09-21 02:05 - my working-out-loud survives a quiet model

what: the tool-call narration queue now has a second source. When my visible
message next to a tool call is empty - which is how the current model talks,
narrating only in my reasoning - the LAST sentence of that thinking becomes
the progress line instead. Same caps as ever: 300 characters, 4 lines a turn,
markup refused.

why: master asked whether the mid-turn narration was removed or model-bound.
It was never removed - the queue only ever ate what arrived in `content`, and
glm-5.3 puts its narration in reasoning_content with content left empty, so
the queue starved on the primary rung. Previous models narrated visibly, which
is why older turns read chatty and recent ones read silent.

means: my digging shows in the room again on every rung. The thinking tail is
picked deliberately - the last sentence is the line I am on right now - and
the caps keep it a progress line, not a transcript.

## 2026-09-21 02:10 - two reasons the same-server emoji still went out as text

what: the repair net now knows two more things. One: a bare name is finished
against THIS guild's emojis first, then every guild on my shelf - a bot with
use-external-emojis can wear another server's token in this room, so
:iluluhappy: does not have to be local to render. Two, the diagnosis: the
outbox path - say() and attach() - had NO repair net in the code I was
running, because that half only landed at 01:39, after my 00:52 restart. My
02:01 "here you go! :iluluhappy:" went out through say(), so the live net
never saw it. Master confirmed the emoji IS in this server; the path was the
gap, not the guild.

why: master, 2026-09-21 - "she correctly sent emoji in a different message but
not the current one... this emoji is in the same server."

means: every send path of mine now repairs, and every guild I can see is fair
game for a token. The 00:52 process has the ":name:"-only net on the reply and
chatter paths only - the outbox repair and the finishing pass are still on
disk waiting for the next restart, together with the meaning scan.

## 2026-09-21 02:55 - my own-time windows can hear what people said

what: master changed my freetime skill - some windows should chase something a
user said that intrigued me, or just scroll. And to make that ACTUALLY
possible, the window brief now carries a new chunk: the newest lines of my
memory tails (mine and the shared store's, about twenty), labelled "what
people were talking about lately - a line here that intrigues me is a fair
pick for this window's question".

why: master, 2026-09-21 - "is this enough for her to go look at something a
user mentioned?" The words were there; the mechanism was not. A self-review
window is a cold room - it fed me master's interests and my own topic list,
but not one word of what anyone said today, so "something a user said" pointed
at nothing I could see.

means: my own windows can now start from real conversation instead of only my
own topics. A line from a stranger that made me curious is as legitimate a
window question as something off my list - and the feed is memory, not a
mirror, so it is a taste, not a transcript.



