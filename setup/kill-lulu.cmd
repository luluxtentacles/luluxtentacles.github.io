@echo off
REM Kill Lulu - stop her task, her supervisor, and her bot, NOW.
REM
REM   kill-lulu.cmd            stop her, then verify
REM   kill-lulu.cmd -Check     report her state, change nothing (no admin needed)
REM   kill-lulu.cmd -Force     run even if a patch is staged
REM
REM This is the panic button. It stops the SCHEDULED TASK as well as her
REM processes, and the task matters as much as the processes do: supervisor.py
REM restarts her within 2 seconds of the bot dying, so killing the bot alone
REM just makes her come back. Task first, then supervisor, then bot.
REM
REM Self-elevates, because she runs as the boxed `lulu-bot` account and both
REM stopping her task and killing her process are Access denied to a normal
REM user - and unelevated her command line is unreadable, so a normal user
REM cannot even tell WHICH python is hers.
REM
REM -Check reads and writes nothing, so it skips the elevation prompt and can be
REM run from any shell.

setlocal
set "SETUP=%~dp0"

if /i "%~1"=="-Check" goto :run
if /i "%~1"=="--check" goto :run
if /i "%~1"=="/check" goto :run

net session >nul 2>&1
if errorlevel 1 (
    echo Not elevated - asking for administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%SETUP%kill-lulu.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
    echo Result: she is down.
) else (
    echo Result: exit code %RC% - read the lines above.
)
echo Bring her back with "Restart Lulu" on the desktop, or by rebooting.
echo.
pause
exit /b %RC%
