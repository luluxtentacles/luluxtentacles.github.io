<#
Starts LuluDiscordBot and proves, from inside the elevated session, what the
task actually is.

Why this exists: a task whose principal is lulu-bot cannot be read reliably
without elevation, so from a normal shell it looks like it does not exist. That
made a working registration look like a failure more than once. This script
runs elevated, starts the task, reads the real trigger back, and writes
everything to a file a normal shell can read.

  Elevated PowerShell:
    .\start-bot.ps1
#>
[CmdletBinding()]
param(
    [string]$TaskName = "LuluDiscordBot",
    [string]$BotRoot = "C:\Lulu",
    [int]$WaitSeconds = 20
)

$ErrorActionPreference = "Continue"

$LogDir = Join-Path $BotRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Out = Join-Path $LogDir "start-check.txt"

"=== start-check $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Set-Content -Path $Out -Encoding UTF8

Add-Content $Out "--- task as it really is ---"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Add-Content $Out "TASK NOT FOUND"
} else {
    Add-Content $Out ("state      : " + $task.State)
    Add-Content $Out ("runs as    : " + $task.Principal.UserId)
    Add-Content $Out ("runlevel   : " + $task.Principal.RunLevel)
    Add-Content $Out ("logon      : " + $task.Principal.LogonType)
    Add-Content $Out ("multiple   : " + $task.Settings.MultipleInstances)
    Add-Content $Out ("timelimit  : [" + $task.Settings.ExecutionTimeLimit + "]")
    foreach ($tr in $task.Triggers) {
        Add-Content $Out ("trigger    : " + $tr.CimClass.CimClassName)
        # The watchdog lives or dies on these two lines. Printed because the
        # repetition is invisible from a non-elevated read.
        Add-Content $Out ("  interval : [" + $tr.Repetition.Interval + "]")
        Add-Content $Out ("  duration : [" + $tr.Repetition.Duration + "]")
    }
}

Add-Content $Out ""
Add-Content $Out "--- starting ---"
try {
    Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    Add-Content $Out "Start-ScheduledTask issued"
} catch {
    Add-Content $Out ("START FAILED: " + $_.Exception.Message)
}

Start-Sleep -Seconds $WaitSeconds

Add-Content $Out ""
Add-Content $Out "--- after ${WaitSeconds}s ---"
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
if ($info) {
    Add-Content $Out ("lastRunTime    : " + $info.LastRunTime)
    Add-Content $Out ("lastTaskResult : " + $info.LastTaskResult)
    Add-Content $Out ("nextRunTime    : " + $info.NextRunTime)
}

$bot = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*lulu_bot*' }
if ($bot) {
    foreach ($x in $bot) {
        $owner = (Invoke-CimMethod -InputObject $x -MethodName GetOwner -ErrorAction SilentlyContinue).User
        Add-Content $Out ("process        : pid=" + $x.ProcessId + " owner=" + $owner)
    }
} else {
    Add-Content $Out "process        : NOT RUNNING"
}

Add-Content $Out ""
Add-Content $Out "--- bot.log tail ---"
$botLog = Join-Path $LogDir "bot.log"
if (Test-Path $botLog) {
    Get-Content $botLog -Tail 20 | Add-Content $Out
} else {
    Add-Content $Out "no bot.log yet"
}

Write-Host "wrote $Out"
Get-Content $Out
