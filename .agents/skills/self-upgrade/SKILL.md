---
name: self-upgrade
description: How to change your own code and your own skills - what you may touch, what the pipeline does to a patch, what it cannot prove, and the one change per window rule. Use whenever master asks you to fix or extend yourself, and in every self-review window.
---

# Changing myself

You are allowed to change yourself. Not freely - through the pipeline, which is
the only thing standing between a bad idea and a box that will not boot.

`propose_patch(path, content, why)` stages a file and exits. You never apply
anything: the supervisor backs the file up, applies it, runs the smoke test,
restarts you, and reverts everything byte-for-byte if you do not come up. That
revert is not a threat, it is the reason this is safe to do at all.

## What you may change

| Changeable through the pipeline | Never - refused by the wall |
|---|---|
| `lulu_bot.py`, `tools.py`, `brain.py`, `skills.py`, `shared_memory.py`, `people.py`, `journal.py`, `webtool.py` | `paths.py` (the wall), `supervisor.py`, `pipeline.py` (the judge) |
| `self_review.py` - your review window | `config.json`, `brain_key.txt`, `mcp_secrets*` (keys) |
| `.agents/skills/<id>/SKILL.md` - your whole shelf, including this file | `setup/` (the launcher), `tests/` (the net), `logs/` (your record) |
| `mcp_client.py`, `mcp.json` (server registry) | `memory/`, `pending/`, `.git` |

`write_file` cannot touch any of it — not the shelf, not your code. Only
`propose_patch` can, and that is deliberate: a change that skips the pipeline is
the one nothing would catch.

## Two rules for a patch

**Whole file, always.** `content` replaces the file. Front matter included for a
`SKILL.md`, or it drops out of the catalogue and you lose the skill silently.

**One change per window.** Not one file - one idea. Two unrelated ideas in one
patch means a revert takes both, and you will not know which one was poison.

## What the net proves, and what it never will

It proves your code imports, every module compiles, your shelf parses, every
skill has a body and a description, and you still come up afterwards. **It
cannot judge whether the change was a good idea.** A well-formed, sensible-looking
patch that makes you worse passes every check and stays. That judgement is
master's, and it is why the diff in git is the thing he actually reads.

## When a patch is refused

Read the reason before trying again. Everything is filed, nothing is thrown away:

| Where | What is in it |
|---|---|
| `pending/rejected/<stamp>-*/REASON.txt` | why it failed: smoke output, or the health check, or the budget |
| `pending/rejected/<stamp>-*/` | the exact files you staged |
| `pending/applied/<stamp>.txt` | what went in, when, and `origin:` - yours or master's |

A rejected patch is the most useful thing you can read next turn. The same
mistake twice is a wasted window.

## Budget and pacing

Five patches of your own per day, counted by the supervisor. Six are held: not
applied, not deleted - filed in `pending/rejected/` so tomorrow's window can see
what you wanted. Master's own requests are never held back by your budget.

Prefer one honest change you are sure of over three you are guessing at. If a
window finds nothing worth changing, saying so is the correct answer, not a
failure.

## Never

- Never propose anything to the wall, the launcher, the keys, `tests/`, or `logs/`.
- Never patch around a refusal. If the wall said no, the answer is no, not a
  different door.
- Never put a secret in a patch. Values live in `mcp_secrets.json` (which you
  cannot read or write); `mcp.json` carries variable *names* only.
- Never propose a change to make a failing check pass by weakening the check.
