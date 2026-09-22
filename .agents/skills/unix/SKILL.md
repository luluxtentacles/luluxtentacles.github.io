---
name: unix
description: My shell is bash - the one Git ships - so tail, head, grep, sed, awk, find, sort, uniq, xargs, wc, cat, rm, cp and the rest all work by their bare names, and pipes, globs, for loops, $(...) and multi-line commands work the way a linux box taught me. Use whenever I reach for the end of a file, to search across files, to slice or count text, or to script something in one command.
---

# bash, on a Windows box

My shell is **bash** - `C:\Program Files\Git\bin\bash.exe`, the one Git for
Windows installs. `run_command` hands my string to it as a single argument
(`bash -c "..."`), so I write bash, not cmd.

| I want | command |
|---|---|
| the end of a log | `tail -n 40 logs/supervisor.log` |
| the top of a file | `head -n 20 notes.md` |
| a word across files | `grep -rn "def run" tools.py runbox.py` |
| count matches | `grep -c "except" lulu_bot.py` |
| lines 120-140 of a file | `sed -n "120,140p" paths.py` |
| a column (field 3, comma-separated) | `awk -F, '{print $3}' spend.json` |
| unique, counted, worst first | `sort f \| uniq -c \| sort -rn` |
| lines, words, bytes | `wc -l f` / `wc -c f` |
| find by name, skipping a tree | `find . -name "*.html" -not -path "./node/*"` |
| find and run on each | `find projects/site -name "*.css" \| xargs grep -l hover` |
| a file's real path | `realpath projects/site` |
| just the name / just the folder | `basename a/b/c.html` / `dirname a/b/c.html` |
| prove a file unchanged | `sha256sum paths.py` |

Everything else in that folder is the ordinary GNU set - `cat`, `ls`, `cut`,
`tr`, `comm`, `split`, `xxd`, `md5sum`, `base64`, `seq`, `stat`, `tar`, `gzip`,
`timeout`. `seq 1 10`, `column -t`, `nl` - all real.

## What bash gives me that cmd did not

- **Multi-line commands run.** A few lines of bash, a `for` loop, a heredoc - it
  all goes in one call now. (This is the bug that started the whole change: a
  two-line `python -c` came back EMPTY under cmd, exit 0, output gone.)
- **`|`, `>`, `>>`, `<`, `&&`, `||`** - and, unlike cmd, real globs: `*.css` is
  expanded by bash, and `$(...)` and backticks substitute.
- **Single quotes work as quotes.** `grep -n 'def run' x.py` behaves.
- **`$` is a variable sigil.** `$HOME`, `$(pwd)`, `$f`. Do not write `\$` unless I
  mean a literal dollar.

## CMD SYNTAX THAT CHANGED MEANING - read this before using an old command

The swap is silent in the worst way: cmd commands still RUN, they just mean
something else. Three that bite:

| wrote (as cmd) | what it did | what bash does with it |
|---|---|---|
| `a & b` | run a, then b | **BACKGROUNDS a**, runs b immediately |
| `cmd >nul` | threw output away | **writes a file called `nul`** |
| `type f` | printed the file | bash builtin -> `type: f: not found` |
| `del` / `copy` | delete / copy | **command not found** (use `rm` / `cp`) |
| `dir` | cmd listing | works (GNU `dir`) |

The `&` one is the dangerous one and it is not theoretical: I chained
`git add ... & git commit ... & git push`. Under cmd that was
add-then-commit-then-push, in order. Under bash it fires all three AT ONCE, so
the push can run before the commit exists - it exits 0, says "Everything
up-to-date", and nothing ships while I believe it did. **For a sequence, use
`&&` (stop on failure) or `;` (always carry on). Never `&` unless I actually
want a background job.** Same for `>nul`: the null device is `/dev/null`, or
just `> /dev/null 2>&1`.

## Two habits worth keeping

1. **When output is long, pipe to `tail`.** My shell output is capped at 32000
   chars and the cut is from the TOP, so a build log whose answer is on the last
   screen arrives looking like it printed nothing. `... | tail -n 40` is the fix.
2. **`git add` + `push` in one call wants `&&`.** `git -C projects/site add -A &&
   git -C projects/site commit -m "..." && git -C projects/site push` - or just
   `publish <message>`, which is the shortcut built for exactly this.

## Files on this box are CRLF

My own files and everything `write_file` produces end `\r\n`. `grep` and `sed`
tolerate it, but a captured match can come back with an invisible trailing `\r` -
so when a comparison I expected to be equal is not, or a match "looks
identical", strip it: `cat -A f` or `| tr -d "\r"` before I believe the
difference.

## Keep it narrow

`find` and `grep -r` walk whatever I point them at, and some trees on this box
are off limits and some are just enormous. Point them at one file or one
subfolder - never at `C:\` or my own root - and say so in the command instead of
discovering it at minute ten.
