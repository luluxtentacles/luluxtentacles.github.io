# Lulu — handoff, 2026-09-19 (~17:20, Saturday afternoon)

Written because the previous chat's shell kept hanging. Everything below was
verified by reading real files; anything unverified is marked as such.

## What this is

A second Discord bot cloned from Nana. She is called **Lulu** and lives in
**`C:\lulu`**. Nana is untouched at `C:\Nana\discord` (confirmed present) and
still running.

## Layout — FLATTENED, this is settled

`C:\lulu` **IS** the bot root and the sandbox root. There is no `discord/`
subfolder any more (empty shell was removed). Confirmed:

```
paths.ROOT == C:\lulu        (was C:\lulu\discord, then flattened)
```

Flattening mattered for a real reason, not tidiness: `SEALED_DIRS` matches
`parts[0]`, so while the code sat one level below the root, `tests/` would have
stopped counting as sealed — the net that judges every patch would have become
writable. Verified after the move: `paths.py` refused, `tests/smoke_test.py`
refused, `../escape` refused.

## Done and verified

| item | state |
|---|---|
| code cloned from `C:\Nana\discord` | ✅ 21 modules, all compile |
| `nana_bot.py` → `lulu_bot.py` | ✅ renamed on disk |
| `.agents/skills/nana-voice` → `lulu-voice` | ✅ renamed |
| identity rewrite across live code | ✅ 32 files; **0** "nana" left in live code (archives skipped on purpose) |
| `memory/discord.json` | ✅ 142 entries, **0** leftover "nana", her 74 entries now `speaker: Lulu` |
| `shared_memory.py`, 6 × `setup/*` | ✅ repointed `C:\Lulu\discord` → `C:\Lulu` |
| `node/`, `whisper.cpp/` (2.6 GB), `ffmpeg/` | ✅ copied |
| Nyan's drop retargeted (other repo) | ✅ see below |

**Archives deliberately NOT rewritten**: `logs/`, `pending/applied|rejected/`
and `memory/journal/`. Those are records of what happened; rewriting them would
falsify the audit trail. The rename script skips them by design.

## The other repo — `C:\Python\DiscordBotN5`

Nyan drops a resolved people-ledger into Lulu's wall once a day.
`memory_system.py` was retargeted (compiles clean, no dangling refs):

| was | now |
|---|---|
| `NANA_DROP_DIR = C:\Nana\discord\memory\nyan` | `LULU_DROP_DIR = C:\lulu\memory\nyan` |
| `NANA_DROP_SCHEMA = "nana-people-drop/1"` | `LULU_DROP_SCHEMA = "lulu-people-drop/1"` |
| `build_nana_drop()` / `write_nana_drop()` | `build_lulu_drop()` / `write_lulu_drop()` |
| caller at line ~7028 | updated |

Both halves of the contract had to move together. Lulu's reader refuses a
payload whose schema doesn't match, so a drop under the old name would have been
discarded **silently**. Verified: Nyan writes `C:\lulu\memory\nyan`, Lulu's
`paths.resolve("memory/nyan")` is `C:\lulu\memory\nyan`. **They now agree.**

## BLOCKING — pick one, then she can boot

`shared_memory.py` raises on import:

```
RuntimeError: shared memory store missing at C:\Lulu\memory\store.py
```

It wants a **cross-face** store (the one Nana's GUI/CLI faces also read) — NOT
`memory/discord.json`, which is already hers and already renamed. Master said
*"she should only have your discord bot's memory"*, so the answer is almost
certainly option 1:

1. **Own `C:\lulu\memory\`** — fresh `store.py` + empty `shared.json`.
   Self-contained, Discord-only. *(recommended — matches what master said)*
2. Point at `C:\Nana\memory\` — shares facts with Nana. Contradicts above.
3. Make the den-memory import optional so she boots with no cross-face store.

Until this is resolved, `tests/smoke_test.py` cannot run past import.

## Still to do

1. **Resolve the shared-memory blocker** (above), then re-run `tests/smoke_test.py`.
2. **Move Python into `C:\lulu`.** `C:\lulu\Python311` does **not** exist.
   `setup/run-bot.cmd` sets `PYTHON="C:\Nana\Python311\python.exe"` — a path
   inside Nana's den. Master explicitly asked for this to be moved.
3. **Desktop shortcuts** — master asked to rename the console + restart scripts
   on his desktop (`watch-console.cmd`, `restart-nana.cmd` equivalents) for Lulu.
   Not started.
4. **Kill-script** — master asked for a script that stops the supervisor and
   Nana while Lulu is edited. **Not started.** Note: stopping Nana needs
   elevation and the task is `IgnoreNew`; killing her supervisor does not
   respawn it (`-AtStartup` only), so a reboot is how it comes back. Killing
   `6500` earlier tonight left her orphaned-but-running exactly this way.
5. **Her own Windows account** (`lulu-bot`) — discussed, not decided. Master
   picked "flatten + own account" but it needs his elevation. `nana-bot` is
   currently the only bot account; `C:\Users\nana-bot` is permission-denied to
   Kei.
6. **A token.** `config.json` still carries Nana's `token_source`. A second bot
   needs a **second token** from the dev portal or two processes fight over one
   gateway session. Master places tokens; never print them.
7. `tmp_courtney_scan.py`, `tmp_read_msg*.py` still point at `C:\Lulu\discord`
   — Nana's old scratch, harmless, deletable.

## Traps worth carrying forward

- **Two separate `ROOT`s**: `paths.py` and `pipeline.py` each define their own
  as `Path(__file__).parent`. They agree only while code sits at the root.
- **The wall guards tool calls, not processes.** `paths.py` says so itself:
  *"subprocess never goes through resolve()"*. A shell would not be contained
  by any of this.
- **`git safe.directory`** — master set `--system safe.directory C:/Nana`
  earlier. **`C:\lulu` will hit the same dubious-ownership failure** and needs
  its own entry, or checkpoints silently return `None`.
- **Account-scoped bugs, three tonight**: node on PATH, git ownership,
  playwright browsers in `C:\Users\Kei\...` with no `nana-bot` ACE. All the same
  root cause — things work as Kei, die as the bot account. Expect a fourth.
- **Shell gotchas**: Git Bash mangles `/E` into `E:/`; use PowerShell for
  Windows paths; Python needs `C:/x` not `/c/x`; `\N` needs a raw string.
- **`propose_patch` writes `pending/REQUEST.json`**, which a live supervisor
  polls every 2s. Never call it from a test — it restarts the real bot.

## Useful commands

```bash
# her sandbox root + seal
cd /c/lulu && python -c "import paths; print(paths.ROOT); paths.resolve('../x')"

# the net (blocked until shared-memory is resolved)
cd /c/lulu && python tests/smoke_test.py

# Nyan's half still compiles
cd /c/Python/DiscordBotN5 && python -m py_compile memory_system.py
```

Helper scripts used for the migration are parked at `C:\lulu\.setup-tools\`
(`rename.py`, `relabel_memory.py`) — both default to dry-run.

## Commits on `C:\Nana` (master branch)

```
0110990 checkpoint before the lulu clone
878cbe6 pipeline: say why there is no checkpoint instead of failing silent
a6ecd45 give her surgical edits, and refuse malformed patches before staging
625d15c mcp: put node on PATH for spawned servers, and give her a skill writer
```
