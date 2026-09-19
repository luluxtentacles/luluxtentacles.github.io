@echo off
rem Runs Lulu's Discord bot. Started by the LuluDiscordBot scheduled task.
cd /d "C:\Lulu"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
if not exist "logs" mkdir "logs"
rem Den python, not the per-user install under Kei's profile: the bot runs as
rem lulu-bot, so it must not depend on a path inside a human's account.
set PYTHON="C:\Lulu\Python311\python.exe"
if not exist %PYTHON% (
    echo no python at %PYTHON% >> "logs\bot.log"
    exit /b 1
)
rem Supervised, not direct. She cannot restart herself - killing her own process
rem is the last thing she can do - so supervisor.py owns her process and applies
rem any staged self-edit behind git, the smoke test and a health check.
rem run-bot.cmd stays the entry point, so the scheduled task needed no change.
%PYTHON% supervisor.py >> "logs\bot.log" 2>&1
