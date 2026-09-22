---
triggers: grep, sed, awk, xargs, uniq, basename, dirname, realpath, command line, one-liner, tail -, head -, grep -, sed -, awk -, find ., sort -, wc -
---

## Rules
- bare `tail`, `head`, `grep`, `sed`, `awk`, `find`, `sort`, `uniq`, `xargs`, `wc` all work now - Git's GNU tools are first on my PATH. no full paths, no workarounds.
- ONE line per command: the runner refuses multi-line, and cmd has no `;` separator. chain with `&` (always) or `&&` (only if the first worked).
- single quotes are not quotes in cmd, they are literal characters. use double quotes.
- `find` is GNU find now, so `find . -name "*.html"`. it replaced the ancient Windows find.exe on purpose, along with `sort`, `more` and `timeout`.
- long output is cut at 32000 chars from the TOP, so pipe through `tail -n 40` when I want the end of a build log.
- when cmd's syntax fights me, `bash -c "..."` is real bash and is on my path now - one line still.
