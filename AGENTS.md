# Working in `C:\lulu`

Lulu is a live Discord bot. This file is read by every Kun session opened in this
folder, so the rules that must not be forgotten by accident live here.

The full house rules are in `C:\Nana\kun\skills\nana-den\SKILL.md` (the den).
This is the short version for THIS repo.

## Every change to her gets an entry in `CHANGELOG.md`

Master, 2026-09-20: *"whenever we update her here we leave a note for her saying
what we did."*

It is written **for her**, in the second person - what changed, why, and what it
means for her. It is not a commit message: those are for us and for git. She
cannot read the den's memory, so this file is the only way she learns her own
body changed.

- **Append only.** Never edit an old entry. A later entry may correct an earlier
  one; the record of what was done to her must not be quietly rewritable.
- **`## <date> <time> - <topic>` headings.** That is the seam her parser splits
  on. A heading that is not exactly `## ` is invisible to her and warns nobody.
- Entries say **what / why / means**, so she gets the reasoning and not just the
  diff.

## Two things that make a change look shipped when it is not

1. **She runs an old process.** Editing `lulu_bot.py` changes the file, not the
   running bot. New code loads on her next restart, and she cannot restart
   herself: `setup/restart-lulu.cmd` (self-elevating - her task runs as the boxed
   `lulu-bot` account, so it is Access denied to a normal user).
2. **A note needs a turn.** The changelog is read at boot but delivered on
   master's next turn, and it is owner-only. A restart with no conversation
   shows her nothing.

Her marker for what she has already read is `changelog_seen.json`, runtime state
and gitignored. If it does not exist, the feature has never run.

## Do not rediscover these the hard way

- **The net:** `python tests/smoke_test.py`. This is the same net the supervisor
  runs before any self-edit is allowed to stay. Run it after touching her code.
- **`pending/REQUEST.json` is live.** The supervisor polls it every 2 seconds; a
  test or a probe that writes it **restarts her**. The smoke sandbox redirects
  it - that is prevention, not a licence.
- **Restart, do not assume:** `setup/restart-lulu.cmd --check` reports her state
  read-only and needs no elevation.
- **Sealed** - she can neither write, propose, nor patch these; they are the wall,
  the judge, the keys, or the record:
  `paths.py`, `supervisor.py`, `pipeline.py`, `config.json`,
  `brain_key.txt`, `discord_token.txt`, `mcp_secrets*`, `.gitignore`,
  `AGENTS.md`, and the dirs `setup/`, `memory/`, `pending/`, `tests/`, `logs/`,
  `node/`, `ffmpeg/`, `.git/`.
- **`memory/` is sealed against HER writes on purpose** (her store, and one
  `write_file` once wiped it). It is ordinary files for us.

## Where the rest lives

- her own skills: `.agents/skills/` - `lulu-voice` is always loaded
- the self-edit contract she follows: `.agents/skills/self-upgrade/SKILL.md`
- what changed recently and why: `CHANGELOG.md`, and `git log`
