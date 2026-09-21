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
REM
REM Nana, 2026-09-21: the log is two files now, so this watches both. See
REM run-bot.cmd - her log had to have a file to itself before it could be rotated
REM at all, so the launcher's redirect moved to supervisor.log, and her
REM process-level tracebacks ride stderr into that one. Watching only bot.log
REM would have hidden exactly the lines (the loop-thread tracebacks) this window
REM exists to show.

title Lulu console
start "Lulu supervisor log" powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Lulu\tools\tail-file.ps1" -Path "C:\Lulu\logs\supervisor.log" -Tail 15
powershell -NoProfile -ExecutionPolicy Bypass -File "C:\Lulu\tools\tail-file.ps1" -Path "C:\Lulu\logs\bot.log" -Tail 40
