@echo off
rem Runs Lulu's Discord bot. Started by the LuluDiscordBot scheduled task.
cd /d "C:\Lulu"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
rem Her own node first on PATH. Without this a bare `node`, `npm` or `npx`
rem resolves to NOTHING for her: this script sets no PATH at all, and the
rem machine's own node lives inside Tentacles's profile, which the lulu-bot account
rem cannot reach. node\ carries its own node.exe, npm.cmd and npx.cmd, so
rem putting it first makes the shorthands work for commands she runs herself.
rem mcp.json still points at node\node.exe by full path for its own reasons and
rem is unaffected by this - that stays a direct path, not a PATH lookup.
set "PATH=%CD%\node;%PATH%"
rem Git, so she can push her own projects (C:\lulu\projects) to her own GitHub.
rem Same rule as node above and for the same reason: this script sets no PATH of
rem its own, git is NOT on the machine PATH, and the one that resolves in
rem master's shell lives on HIS user PATH - which the lulu-bot account cannot
rem reach. Appending it here gives git to her process and to nothing else on the
rem machine. Her credential is read from C:\lulu\.git-credentials, configured
rem repo-locally in C:\lulu\projects rather than in her profile.
rem
rem Nana, 2026-09-22: Git for Windows carries the whole GNU userland inside
rem itself, and cmd.exe could never see it. `usr\bin` is where tail, head, grep,
rem sed, awk, find, sort, xargs and the rest live; `bin` carries bash and sh.
rem Both go on the FRONT and `cmd` goes on the END: `cmd` holds git.exe only, so
rem ordering it last means no command loses the git it already had. Prepending
rem also shadows cmd.exe's own find/sort/more/timeout with the GNU ones, which is
rem the point - nothing she runs and none of these scripts ever wanted the
rem Windows versions (checked, not assumed). This is what makes a bare `tail`
rem resolve for her instead of answering "is not recognized".
set "PATH=C:\Program Files\Git\usr\bin;C:\Program Files\Git\bin;%PATH%;C:\Program Files\Git\cmd"
if not exist "logs" mkdir "logs"
rem Her interpreter, moved OUT of her folder on 2026-09-21 (master copied it to
rem C:\lulu-apps so her own folder stops carrying it). run-bot.cmd is sealed -
rem she can never write here - so this path is hand-edited and is the ONLY place
rem the launcher learns where python lives. If it is wrong she does not boot at
rem all, which is why the existence check below exits rather than guessing.
if not exist "C:\lulu-apps\Python311\python.exe" (
    echo no python at C:\lulu-apps\Python311\python.exe >> "logs\supervisor.log"
    exit /b 1
)
rem Supervised, not direct. She cannot restart herself - killing her own
rem process is the last thing she can do - so supervisor.py owns her process,
rem and applies any staged self-edit behind git, the smoke test and a health
rem check. Going straight to lulu_bot.py here would bypass all of that.
rem
rem Nana, 2026-09-21: this used to append to logs\bot.log, which is why bot.log
rem was 1.9 MB with 18,808 lines in it and had never been rotated once. Two
rem problems with that, and the second is the one that forced this line:
rem   1. it doubled the file - the supervisor's own console output sharing one
rem      file with hers;
rem   2. it made a daily rotation IMPOSSIBLE, because this redirect holds the
rem      handle for as long as her process lives and Windows will not let
rem      anything rename a file that is still open. Her handler cannot roll the
rem      log it cannot rename.
rem So her log is hers and nothing else touches it (lulu_bot._setup_logging
rem rolls logs\bot.log at midnight), and the launcher's output - including her
rem process-level tracebacks, which arrive on stderr - goes here instead.
rem Deliberately NOT dated: cmd can only get a date out of %DATE%, which is
rem locale-shaped and can hand back something unparseable, and a powershell
rem call at every launch is a new way for her lifeline to fail. This file is
rem the small one; bot.log is the one that grows.
"C:\lulu-apps\Python311\python.exe" supervisor.py >> "logs\supervisor.log" 2>&1
