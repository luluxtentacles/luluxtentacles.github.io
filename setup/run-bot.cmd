@echo off
rem Runs Lulu's Discord bot. Started by the LuluDiscordBot scheduled task.
cd /d "C:\Lulu"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
rem Her own node first on PATH. Without this a bare `node`, `npm` or `npx`
rem resolves to NOTHING for her: this script sets no PATH at all, and the
rem machine's own node lives inside Kei's profile, which the lulu-bot account
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
set "PATH=%PATH%;C:\Program Files\Git\cmd"
if not exist "logs" mkdir "logs"
rem Her interpreter, moved OUT of her folder on 2026-09-21 (master copied it to
rem C:\lulu-apps so her own folder stops carrying it). run-bot.cmd is sealed -
rem she can never write here - so this path is hand-edited and is the ONLY place
rem the launcher learns where python lives. If it is wrong she does not boot at
rem all, which is why the existence check below exits rather than guessing.
if not exist "C:\lulu-apps\Python311\python.exe" (
    echo no python at C:\lulu-apps\Python311\python.exe >> "logs\bot.log"
    exit /b 1
)
rem Supervised, not direct. She cannot restart herself - killing her own
rem process is the last thing she can do - so supervisor.py owns her process,
rem and applies any staged self-edit behind git, the smoke test and a health
rem check. Going straight to lulu_bot.py here would bypass all of that.
"C:\lulu-apps\Python311\python.exe" supervisor.py >> "logs\bot.log" 2>&1
