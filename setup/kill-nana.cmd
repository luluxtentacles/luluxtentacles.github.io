@echo off
REM Stop Nana - her supervisor AND her bot - so Lulu can be edited without a
REM live bot fighting over the same files.
REM
REM   kill-nana.cmd           stop her, then verify
REM   kill-nana.cmd -Check    report her state, change nothing
REM   kill-nana.cmd -Force    run even if a patch is staged
REM
REM Self-elevates. She runs as the boxed `nana-bot` account and her scheduled
REM task is ACL-restricted, so stopping either one is "Access is denied" to a
REM normal user - and her command line is unreadable, so we cannot even be sure
REM which python is hers without admin.
REM
REM Stopping the TASK matters as much as killing the processes. supervisor.py
REM restarts her within 2 seconds of the child dying, so a bare taskkill just
REM makes her come back. The task is -AtStartup only: once it is stopped and the
REM supervisor is dead, nothing respawns either of them. A reboot, or
REM restart-nana.cmd, is how she comes back.

setlocal
set "SETUP=%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo Not elevated - asking for administrator rights...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%SETUP%kill-nana.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (echo Result: she is down.) else (echo Result: exit code %RC% - read the lines above.)
pause
exit /b %RC%
