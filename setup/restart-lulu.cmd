@echo off
REM Restart Lulu. Self-elevates, because her task runs as the boxed `lulu-bot`
REM account and stopping/starting it is Access denied to a normal user.
REM
REM   restart-lulu.cmd          stop her, start her again, verify (asks for admin)
REM   restart-lulu.cmd --check  report her state, change nothing (no admin needed)
REM
REM Stops and starts the SCHEDULED TASK, not her process: the task owns the
REM lulu-bot credential, and only it can start her.
REM
REM Why she may need this: with a small amount of free RAM her working set gets
REM paged out and the shard falls behind ("Can't keep up"). A restart is the fix.

setlocal
set "SETUP=%~dp0"

REM --check reads and writes nothing, so it does NOT need elevation - skip the
REM self-elevation for it and let her state be read from any shell. Everything
REM else still elevates, because stopping her task and killing her process are
REM Access denied to a normal user.
if "%~1"=="--check" goto :run

net session >nul 2>&1
if errorlevel 1 (
    set "ELEVATED=0"
) else (
    set "ELEVATED=1"
)

if "%ELEVATED%"=="0" (
    echo Not elevated - asking for administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

:run
if "%1"=="--check" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SETUP%finish-setup.ps1" -Check
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%SETUP%finish-setup.ps1"
)

echo.
pause
