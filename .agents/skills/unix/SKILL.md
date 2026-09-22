---
name: unix
description: The unix tools I am used to - tail, head, grep, sed, awk, find, sort, xargs, wc and the rest - which Git for Windows ships inside itself and which are now first on my own PATH. Use when I want the end of a file, to search across files, to slice or count text, or to script something in one line, and whenever a bare `tail` or `grep` is the thing I reach for.
---

# The unix toolbox, on a Windows box

My shell is `cmd.exe` - `run_command` hands a string to `shell=True`, and that
resolves to cmd, not bash. That is why `tail`, `head`, `grep` and `sed` used to
answer `is not recognized as an internal or external command`: **they were never
on my PATH.** Git for Windows carries the whole GNU userland inside its own
installation, and it always shipped `Git\cmd` (git only) and never `Git\usr\bin`
(everything else). Master's fix, 2026-09-22: `usr\bin` and `bin` are now
**prepended** to my PATH in `setup/run-bot.cmd`, so the bare names work.

| I want | command |
|---|---|
| the end of a log | `tail -n 40 logs/supervisor.log` |
| the top of a file | `head -n 20 notes.md` |
| a word across files | `grep -rn "def run" tools.py runbox.py` |
| a word, case-blind, with line numbers | `grep -rni "todo" .agents/skills` |
| count matches | `grep -c "except" lulu_bot.py` |
| swap text on one line | `sed -n "120,140p" paths.py` |
| a column (field 3, comma-separated) | `awk -F"," "{print \$3}" spend.json` *(quote the `$` in cmd)* |
| sort | `sort -n` / `sort -u` |
| unique, counted | `sort file \| uniq -c \| sort -rn` |
| lines, words, bytes | `wc -l file` / `wc -c file` |
| find by name | `find . -name "*.html" -not -path "*/node_modules/*"` |
| find and run on each | `find projects/site -name "*.css" \| xargs grep -l "hover"` |
| a file's real path | `realpath projects/site` |
| just the name / just the folder | `basename a/b/c.html` / `dirname a/b/c.html` |
| strip a trailing carriage return | `tr -d "\r"` |
| checksum, to prove a file unchanged | `sha256sum paths.py` |

Everything else in that folder works the same way - `cat`, `ls`, `sed`, `awk`,
`cut`, `tr`, `comm`, `split`, `xxd`, `md5sum`, `base64`, `expr`, `seq`, `stat`,
`tar`, `gzip`. It is the ordinary GNU set. `seq 1 10`, `column -t`, `nl` - all real.

## The cmd rules that bite

- **One line per command.** The runner REFUSES a multi-line command outright
  (there is a `[REFUSED - multi-line command]` line in `logs/runbox.log` for every
  time I tried it). cmd has no `;` separator either - chain with `&` for
  always-run, `&&` for only-if-the-first-worked, `||` for only-if-it-failed.
- **Quotes: double only.** `"like this"`. Single quotes are NOT quote characters
  in cmd, they are literal - so `grep -n 'def run' x.py` passes the quotes
  through and finds nothing.
- **`$` is for the shell it is not.** In cmd it is plain text, and it is safe to
  write `awk "{print \$2}"` (cmd does not eat it either way, but quoting it keeps
  it out of awk's way if I ever run the same line through bash).
- **Variables are `%NAME%`**, set with `set NAME=value`.
- **Pipes, redirects and `2>&1` all work** - `|`, `>`, `>>`, `<`. So
  `python tests/smoke_test.py > smoke.txt 2>&1` and then
  `tail -n 50 smoke.txt` is a real workflow.
- **cmd does not expand `*`**, the GNU tool does it itself, which is exactly what
  I want: `grep -rn "hover" projects/site/*.css` behaves. Do not mix that up with
  cmd's own `for` loops, which have their own syntax and are usually the wrong tool.
- **`find` is GNU find now.** `find . -name "*.html"`, NOT the ancient Windows
  `find.exe` that wanted `"pattern" file`. `sort`, `more` and `timeout` are the
  GNU ones too - showing the GNU answer is the whole point of prepending, and
  nothing in my own code or tests ever ran the Windows versions.

## Two habits worth keeping

1. **When output is long, pipe to `tail`.** My shell output is capped at 32000
   chars and the cut is from the TOP, so a build log whose answer is on the last
   screen arrives looking like it printed nothing. `... | tail -n 40` is the fix,
   and it is cheaper than asking for the whole thing again.
2. **When cmd's syntax fights me, stop fighting it: `bash -c "..."`.** Real bash
   is now on my path (`C:\Program Files\Git\bin\bash.exe`) - globs, `for f in
   *.css`, `$(...)`, `&&`, heredocs, all of it. Use cmd for one-offs and bash for
   anything that is actually a script. Same rule applies: it is ONE line, because
   the runner still refuses newlines.

## Files on this box are CRLF

My own files and everything `write_file` produces end `\r\n`. `grep` and `sed`
tolerate it, but a captured match can come back with an invisible trailing `\r`
stapled on - so when a comparison I expected to be equal is not, or a match
"looks identical", strip it: `| tr -d "\r"` before I believe the difference.

## Keep it narrow

`find` and `grep -r` walk whatever I point them at, and some trees on this box are
off limits to me and some are just enormous. Point them at one file or one
subfolder - never at `C:\` or my own root - and say so in the command instead of
discovering it at minute ten.
