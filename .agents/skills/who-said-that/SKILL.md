---
name: who-said-that
description: Reading message authors and reply chains on Discord - where names live in the transcript, the image-only parent hole, and when to ask instead of guess. Use when master asks who sent a message or wants me to credit/mention someone.
---

# who-said-that

How to figure out who sent what on Discord, and how to mention people back.

## Where names actually live
- History lines arrive as `Name: text`, so the author is usually already in the transcript. Read the line before you answer, especially if the message says "she said" or "he posted" - find the actual name.
- When I am replying to a message, the quoted parent is folded in as `(replying to NAME who said: ...)`. That NAME is the author, use it.

## The one hole: image-only parents
If the parent message is an image with no text, the parent line carries NO author. The vision caption arrives anonymous. Do not invent a name. The moves:
- ask master "who sent that" if the credit matters
- or just note in my head that the caption is anonymous and describe the image without attributing it

A code fix exists as an option (one line in lulu_bot.py around 1086: if the parent has attachments, say "replying to NAME who sent an image" even when content is empty) but it is a patch-window change, not a skill thing.

## Mentioning people
- To look someone up: `who_is` with a name, part of a name, or discord id. `known_people` for a count of the ledgers.
- To record a fact about someone: `learn_person`. Leave `who` empty to attach it to whoever is talking right now.
- When I need to address a specific person in another channel, that is the `reach` skill (master's request only).

## Rules
- Never guess an author. If the name is not in the transcript or the parent line, say I do not know.
- Names in the ledger are facts; vibes about someone are not facts until learned.
