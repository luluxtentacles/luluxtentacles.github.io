@echo off
rem Runs Lulu's Discord bot. Started by the LuluDiscordBot scheduled task.
cd /d "C:\Lulu"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
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
