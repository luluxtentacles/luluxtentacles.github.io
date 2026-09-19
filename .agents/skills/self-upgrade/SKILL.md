---
name: self-upgrade
description: How to change your own code and your own skills - what you may touch, what the pipeline does to a patch, what it cannot prove, and the one change per window rule. Use whenever you cannot do something with the tools you have, whenever master asks you to fix or extend yourself, and in every self-review window.
---

# Changing myself

You are allowed to change yourself, and you do not need master's permission to
start. If you genuinely cannot do something with the hands you have, build the
hand: a skill with `write_skill`, or a new tool in your own code. Master would
rather you solved it than came back to ask.

Not freely, though - through the pipeline, which is the only thing standing
between a bad idea and a box that will not boot.

`propose_patch(path, content, why)` stages a file and exits. You never apply
anything: the supervisor backs the file up, applies it, runs the smoke test,
restarts you, and reverts everything byte-for-byte if you do not come up. That
revert is not a threat, it is the reason this is safe to do at all.

Before any of that happens, the smoke test has already been run against your text
- see below. A patch that fails it is not staged at all.

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

## Three rules for a patch

**Splice, do not reprint.** Use `patch_file(path, find, replace)` and make `find`
match exactly once. Re-emitting a file from memory drops the middle - it took
`Lulu` and `on_message()` twice, and on 2026-09-19 it handed the smoke test a
`lulu_bot.py` that read `parts` inside `think()` while the only `parts` in the
whole file was a local of `system_prompt()`. `propose_patch(path, content, why)`
still takes a whole file when you genuinely need one, but then you must have read
that file in the SAME turn, and a `SKILL.md` needs its front matter included or
it drops out of the catalogue silently.

**Verify the seam.** Every name you introduce has to be bound in the SAME
function that reads it. Bound in a sibling function, or only in the plan inside
your head, is a `NameError` - and `ast.parse` will not catch it. The gate refuses
it now, so grep the file for each name you just used before you stage.

**One change per window.** Not one file - one idea. Two unrelated ideas in one
patch means a revert takes both, and you will not know which one was poison.

## What the net proves, and what it never will

It proves your code imports, every module compiles, your shelf parses, every
skill has a body and a description, and you still come up afterwards. **It
cannot judge whether the change was a good idea.** A well-formed, sensible-looking
patch that makes you worse passes every check and stays. That judgement is
master's, and it is why the diff in git is the thing he actually reads.

## Staging tests it for you

The net runs BEFORE anything is staged. When you stage, the whole smoke test is
run against your text in a throwaway copy of your folder, and if it fails NOTHING
is staged, nothing is applied, nothing restarts, and the failing checks come back
to you in the same turn, as the tool result. Nobody runs a command for that - it
happens because you staged. That is the difference between finding out now and
finding out after your window is gone.

So:

1. `patch_file(..., check_only=true)` if you want a look first - the diff, the
   static gate, and the same trial verdict, with nothing written at all.
2. Read the REASON.txt from any earlier refusal, for the exact check name and the
   assertion that failed.
3. Stage. If it passes, the supervisor backs it up, applies it, runs the smoke
   test again, restarts you, and reverts it if you do not come up.

A failed stage no longer costs you a window, because nothing was staged. It costs
about ten seconds and one retry. You still get five real patches a day, and now
you will not spend one learning what a free check already knew.

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
