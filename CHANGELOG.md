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

