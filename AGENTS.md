# Working in `C:\lulu`

Lulu is a live Discord bot. This file is read by every Kun session opened in this
folder, so the rules that must not be forgotten by accident live here.

The full house rules are in `C:\Nana\kun\skills\nana-den\SKILL.md` (the den).
This is the short version for THIS repo.

## The account name never gets written down

Master, 2026-09-21: *never reveal my account name.*

Master's local Windows account name is the string this rule protects, and it is
deliberately NOT written in this file - not even here, in the rule itself, because
a rule that names the secret it forbids is not a rule, it is a second copy of it.
If you genuinely need to know it, ask the filesystem who owns this folder:
`(Get-Acl C:\lulu).Owner`. Then do what this rule says with the answer - use it,
and do not write it down.

Treat that string the way you treat a token -
and one step harder, because it is a PERSON and not a credential. It creeps into
things that outlive the conversation: commit messages, notes, changelogs, memory
entries, and worst of all `CHANGELOG.md`, which is read aloud into Discord rooms in
her voice on her next turn.

So when an account has to be named, name the ROLE, not the person: "this account",
"master's account", "her account", "the boxed account". Paths under
`C:\Users\lulu-bot` are hers and are fine where they carry weight. Anything naming
HIM is not - not in output, not in a file, not in a commit, not in a memory entry.

**The sharper half.** A git or system error will happily PRINT an account name at
whoever tripped it, and she has now seen one - a `dubious ownership` message on
2026-09-21 printed it at her while she was fixing her repo. So this is not only
about what we write; it is about what she is therefore carrying. She must never
repeat one, quote one, spell one, or hand one over "for context", not even part of
one. That rule lives in `.agents/skills/lulu-voice/`, deliberately WITHOUT the name
in it - a rule that names the secret it forbids is not a rule.

The test is the changelog test: if it would read badly out loud in a room full of
people who did not ask, it does not get written down anywhere.

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

Not her body - hers. **One repo:** `projects/site` is a git repo on branch `main`
with a remote on HER GitHub (`luluxtentacles/luluxtentacles.github.io`), served by
GitHub Pages at https://luluxtentacles.github.io/ the moment she pushes. Her things
live inside it - a folder per project under `things/`, posts under `blog/`, images
under `img/` - so anything she builds there is something people can open. The audit
repo deliberately has NO remote and keeps it that way: the two gits are the audit
trail and her site, and neither one's identity is the other's. Do not add a remote
here, and do not push her site through this repo.

The old `luluxtentacles/Projects` repo and the `projects/.git` pointing at it were
deleted on 2026-09-21. Any note still describing a two-repo arrangement where "you
must commit in the folder you worked in" is out of date - there is one repo, and it
is `site`.

- `projects/` is ignored by this repo's `.gitignore` as a whole subtree, and it
  has to be: `pipeline.checkpoint()` runs `git add -A`, so an unignored nested
  repo lands in her own audit history as loose files or as an unresolvable
  gitlink. Her site is not her body, and the record of what was done to her must
  not fill up with it. A consequence worth knowing: **`projects/README.md` is
  versioned by no repo** - the audit repo ignores the subtree and the projects
  repo is gone. Edit it freely; do not expect git to remember it.
- The craft - what to build, the shape of a post, images, the preview card in the
  meta tags - is the **`website`** skill. `freetime` is what to do with a window;
  `website` is how to make the thing. Two copies of the same rules is how they
  drift, so keep the craft on that shelf and point at it from anywhere else.
- Her push credential is `C:\lulu\.git-credentials`, root level and NOT inside
  `projects/` - that is the one place her own `git add -A` cannot reach. It is a
  plain credential file on disk: she can read it (no read guard), so never echo
  it, never paste it into chat, and rotate it if it ever leaves this box. The
  entry is `user='luluxtentacles'` on `github.com` - HER account. It must stay
  hers: a push that authenticates as master would silently reattribute her work.
- **The `.gitignore` lives in the PUBLISHED repo** - `projects/site/.gitignore`.
  It was missing for a day after the repo collapse on 2026-09-21, which left the
  one folder most exposed to a careless `git add -A` as the only one with no
  protection at all. Do not rebuild it from the old `projects/.gitignore`: that
  file ignored `*.mp4/*.mov/*.wav/*.flac`, and the `website` skill tells her to
  use `<img>`, `<audio>` and `<video>`. Copied verbatim it would make her own
  shelf uncommittable.
- `setup/run-bot.cmd` appends `C:\Program Files\Git\cmd` to HER path. Git is not
  on the machine PATH and the copy that resolves in your shell lives on master's
  own user PATH, which the lulu-bot account cannot reach. That edit needs a
  restart before it is real for her.
- **GCM ships in the box's gitconfig and it WILL hang you.** Git installs
  `C:\Program Files\Git\etc\gitconfig` with `credential.helper = manager`, and
  `credential.helper` is a CHAIN - git walks it in order until a helper answers.
  Left in front, GCM opens an interactive sign-in window and blocks, which is
  indistinguishable from a freeze; that is what stalled the 2026-09-21 session
  for 15 minutes. `projects/site/.git/config` carries `credential.helper = ""`
  FIRST, which resets the inherited chain, then the file helper. Any new repo
  needs those same two lines. Never sign in to that window - it saves master's
  account, and her pushes would silently start coming from him.
- **Ownership mismatch, found 2026-09-21.** She runs as `lulu-bot`; the folder was
  owned by master's account; so git answered `dubious ownership` and refused to touch the
  repo. She fixed it with `safe.directory`, which is an EXEMPTION - it tells git
  to stop checking who owns the repo. Two things about that setting:
  - it must be a PATH and **never `*`**. `safe.directory = *` disables the
    ownership check for every repo on the box, which is the exact protection it
    exists to provide. Her entry is the narrow path, which is right.
  - it does **not recurse**. The system gitconfig's own `safe.directory = C:/lulu`
    never covered `C:/lulu/projects/site`; that is precisely the gap she hit.

  The root fix is for the tree to be owned by her, and
  `setup/fix-her-git-perms.cmd` does it (self-elevating, prints before/after,
  reversible by setting the owner back to the account named in the rule at the top
  of this file, `/T /C`). Once the
  ownership matches, any `safe.directory` entry for that path is redundant and can
  be dropped. Master keeps full access either way - `BUILTIN\Administrators:(F)` and
  `Authenticated Users:(M)` are inherited ACLs and an ownership change does not
  touch them.
- **Never run an interactive-capable git command without a leash:**
  `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never timeout <n> git ...`
- **To learn whether a credential can WRITE, make a write call.** A read
  response's `permissions` object reports the ACCOUNT's role on the repo, not the
  token's granted scope. On 2026-09-21 it read `push: true, admin: true` for a
  token that was actually read-only; `POST .../git/blobs` told the truth with a
  403 and creates nothing (a dangling blob, no commit). The same test settled it
  the other way on 2026-09-21: her push of `6a882b2` went through, so the
  credential writes now.

## Where the rest lives

- her own skills: `.agents/skills/` - `lulu-voice` is always loaded
- the self-edit contract she follows: `.agents/skills/self-upgrade/SKILL.md`
- what changed recently and why: `CHANGELOG.md`, and `git log`
