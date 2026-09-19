@echo off
rem Run the access probe AS lulu-bot and leave the result where master can read it.
rem
rem Started by master with:
rem   runas /user:KITSUNE\lulu-bot "cmd /c C:\lulu\setup\probe-as-lulu.cmd"
rem
rem Output goes to a FILE as well as the screen, so the result can be read back
rem and checked rather than transcribed by hand.
rem
rem Why whoami is here: runas performs an INTERACTIVE logon, while her real
rem process is started by a scheduled task with a stored password, which is a
rem BATCH logon. The tokens are not identical. whoami prints the token she
rem actually got, so the difference is visible instead of implied.
set OUT=C:\lulu\logs\probe-as-lulu.txt
echo === whoami === > "%OUT%"
whoami /user >> "%OUT%"
whoami /groups >> "%OUT%"
echo. >> "%OUT%"
powershell -NoProfile -ExecutionPolicy Bypass -File C:\lulu\setup\probe-access.ps1 -Probe >> "%OUT%" 2>&1
type "%OUT%"
