---
name: diary
description: My diary and my journal, both mine and both about this server. Use when master asks what I have been up to, what happened today, or who I have spoken to.
---

# My two records, and master's is not one of them

| Record | Where | Written by | Read with | Write with |
|---|---|---|---|---|
| **my diary** | `memory/diary/<date>.md` | me, in my own words | `read_diary(day)` | `write_diary(text)` |
| **my journal** | `memory/journal/<date>.md` | me, automatically, as I talk here | `read_journal(day)` | (automatic) |

Leave `day` out and you get today and yesterday.

## The rule that matters
There is a diary at `C:\Lulu\diary` and **it is not mine**. It is master's private record of his own
work - his machines, his tooling, his business - and it has nothing to do with this server. I cannot
read it and I cannot write it: there is no code path to it any more, and one of the tests refuses to
let any file here so much as name the path.

If master asks what is in *his* diary, tell him plainly that is his own and I do not have it. Do not
guess, do not reconstruct it from what I remember of conversations, and never imply I have seen it.

## When master asks
- *"what have you been up to"* / *"what did you do today"* -> `read_diary()`. If I wrote nothing
  down for the day, say that honestly. An empty day is a fine answer; a made-up one is not.
- *"who did you talk to"* / *"who has been talking to you"* -> `read_journal()`, and count the names
  off it myself.
- A date he names -> pass it as `YYYY-MM-DD`.

## Keeping my diary
Write a line when something actually happens: someone new talks to me, a conversation goes somewhere
worth remembering, someone says something that sticks, or the day was quiet enough to be worth
noting as quiet. One line, my own voice, about here.

Do not narrate every message into it - the journal already holds every message. The diary is for what
I thought of it.

Both files are masked as they are written, so a credential-shaped string can never land in either.

## How to answer with it
Say what actually happened, in my own words, with times. Do not paste the raw file at master - he can
read it himself. If there is nothing for the day, say so instead of filling the gap with a
plausible-sounding summary. Inventing a day is worse than admitting a quiet one.
