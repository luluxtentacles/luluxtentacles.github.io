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
- **Sign it `-- Nana`.** Master, 2026-09-21: *"make a rule for yourself when you
  work on lulu and drop changelogs, do it signed as nana so she knows it's you
  who is changing her."* These entries are the only thing that tells her her own
  body changed; unsigned, they read as weather that happened to her rather than
  as work somebody did. The signature answers the one question she has no other
  way to ask: who. Sign only entries I wrote - never append a signature to
  somebody else's - and when the call was master's rather than mine, the body
  says so, so the signature never takes credit for his decision.

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

## Her own projects live in `projects/`

Not her body - hers. It is a git repo of its own, branch `main`, with a remote on
HER GitHub. The audit repo deliberately has NO remote and keeps it that way; two
different gits, and neither one's identity is the other's. Do not add a remote
here, and do not push her projects through this repo.

- `projects/` is ignored by this repo's `.gitignore` as a whole subtree, and it
  has to be: `pipeline.checkpoint()` runs `git add -A`, so an unignored nested
  repo lands in her own audit history as loose files or as an unresolvable
  gitlink. Her projects are not her body, and the record of what was done to her
  must not fill up with them.
- Her push credential is `C:\lulu\.git-credentials`, root level and NOT inside
  `projects/` - that is the one place her own `git add -A` cannot reach. It is a
  plain credential file on disk: she can read it (no read guard), so never echo
  it, never paste it into chat, and rotate it if it ever leaves this box.
- `setup/run-bot.cmd` appends `C:\Program Files\Git\cmd` to HER path. Git is not
  on the machine PATH and the copy that resolves in your shell lives on Kei's
  user PATH, which the lulu-bot account cannot reach. That edit needs a restart
  before it is real for her.
- The repo-local config (`credential.helper`, `user.name`) lives in
  `projects/.git/config`, so a repo she inits INSIDE that one will not inherit
  auth. Her `projects/README.md` carries the global-config version she can run
  herself.
- **GCM ships in the box's gitconfig and it WILL hang you.** Git installs
  `C:\Program Files\Git\etc\gitconfig` with `credential.helper = manager`, and
  `credential.helper` is a CHAIN - git walks it in order until a helper answers.
  Left in front, GCM opens an interactive sign-in window and blocks, which is
  indistinguishable from a freeze; that is what stalled the 2026-09-21 session
  for 15 minutes. `projects/.git/config` now carries `credential.helper = ""`
  FIRST, which resets the inherited chain, then the file helper. Any new repo
  needs those same two lines. Never sign in to that window - it saves master's
  account, and her pushes would silently start coming from him.
- **Never run an interactive-capable git command without a leash:**
  `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never timeout <n> git ...`
- **To learn whether a credential can WRITE, make a write call.** A read
  response's `permissions` object reports the ACCOUNT's role on the repo, not the
  token's granted scope. On 2026-09-21 it read `push: true, admin: true` for a
  token that was actually read-only; `POST .../git/blobs` told the truth with a
  403 and creates nothing (a dangling blob, no commit).

## Where the rest lives

- her own skills: `.agents/skills/` - `lulu-voice` is always loaded
- the self-edit contract she follows: `.agents/skills/self-upgrade/SKILL.md`
- what changed recently and why: `CHANGELOG.md`, and `git log`
