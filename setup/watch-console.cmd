@echo off
REM Live view of Lulu's console output.
REM
REM Lulu runs as the boxed `lulu-bot` account, and a process in Session 0 has no
REM desktop to draw on - so there is no window of HERS to show. This shows you
REM the same thing without weakening anything: her log, live, read-only.
REM
REM The tail releases the file handle between polls. `Get-Content -Wait` would
REM hold the log open and stop her writing it - the watcher must never be able to
REM break the thing it watches.
REM
REM Closing this window affects nothing. She keeps running.

title Lulu console
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Lulu\tools\tail-file.ps1" -Path "C:\Lulu\logs\bot.log" -Tail 40
