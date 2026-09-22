---
triggers: grep, sed, awk, xargs, uniq, basename, dirname, realpath, command line, one-liner, tail -, head -, grep -, sed -, awk -, find ., sort -, wc -, loop, heredoc
---

## Rules
- my shell is bash (Git's), so `tail/head/grep/sed/awk/find/sort/uniq/xargs/wc` all work bare, and so do pipes, globs, `for` loops, `$(...)` and multi-line commands.
- NEVER use `&` to chain commands - in bash it BACKGROUNDS the first one instead of sequencing. use `&&` (stop on failure) or `;`. I chained a git add/commit/push with `&` once and the push ran before the commit.
- `>nul` is a cmd habit that now WRITES A FILE called nul. the null device is `/dev/null`.
- `del`/`copy`/`type` are cmd builtins and do not exist here - use `rm`/`cp`/`cat`.
- single quotes are real quotes in bash, and `$` is a variable sigil.
- long output is cut at 32000 chars from the TOP, so pipe through `tail -n 40` when I want the end of a build log.
