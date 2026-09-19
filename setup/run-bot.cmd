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
if not exist "logs" mkdir "logs"
if not exist "C:\Lulu\Python311\python.exe" (
    echo no python at C:\Lulu\Python311\python.exe >> "logs\bot.log"
    exit /b 1
)
rem Supervised, not direct. She cannot restart herself - killing her own
rem process is the last thing she can do - so supervisor.py owns her process,
rem and applies any staged self-edit behind git, the smoke test and a health
rem check. Going straight to lulu_bot.py here would bypass all of that.
"C:\Lulu\Python311\python.exe" supervisor.py >> "logs\bot.log" 2>&1
