# Restart Lulu. Needs an ADMIN shell - her task runs as the boxed `lulu-bot`
# account, so neither stopping the task nor killing her process is permitted to
# a normal user.
#
#   powershell -ExecutionPolicy Bypass -File finish-setup.ps1
#   powershell -ExecutionPolicy Bypass -File finish-setup.ps1 -Check
#
# WHY THIS FILE WAS REWRITTEN
# ---------------------------
# It used to stop and start the scheduled task, then check "is there a
# lulu_bot.py process?" and report `restarted - pid N`. That check finds the OLD
# process, so it printed a successful restart that had never happened. Master
# ran it and believed her restarted when nothing had changed.
#
# Three separate faults, all real:
#   1. Stop-ScheduledTask stops the TASK, not her python. If her process is an
#      orphan - which it was, its parent already dead - it survives untouched.
#   2. A surviving copy makes the NEW instance hit her own single-instance lock
#      (memory/bot.pid), see a live pid, and exit with "refusing to stack".
#      So the restart is silently a no-op.
#   3. The verification checked EXISTENCE, never IDENTITY.
#
# The rule now: kill her process, WAIT until it is actually gone, then start, and
# only report success when a pid appears that was NOT there before.
[CmdletBinding()]
param([switch]$Check)

$ErrorActionPreference = "Stop"
$luluTask = "LuluDiscordBot"

function Assert-Admin {
    $elevated = ([Security.Principal.WindowsPrincipal] `
                 [Security.Principal.WindowsIdentity]::GetCurrent()
                ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $elevated) {
        # Critical: unelevated, CommandLine of another user's process reads empty,
        # so the process search below would find NOTHING and conclude she is down.
        # That is how a second instance gets started. Fail closed instead.
        Write-Host "This needs an ADMIN shell."
        Write-Host "Her process belongs to the lulu-bot account: unelevated, its"
        Write-Host "command line reads blank, so she cannot even be seen - let alone stopped."
        exit 1
    }
}

function Show-Task($name) {
    $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $t) { Write-Host ("  {0,-16} (not readable here)" -f $name); return }
    $a = $t.Actions | Select-Object -First 1
    $i = $t | Get-ScheduledTaskInfo
    Write-Host ("  {0,-16} state={1} user={2}" -f $name, $t.State, $t.Principal.UserId)
    Write-Host ("  {0,-16} lastRun={1} lastResult={2}" -f "", $i.LastRunTime, $i.LastTaskResult)
}

function Get-LuluProcs {
    # Her own process only, matched on the script name. Never a wildcard on
    # python.exe - other python processes on this box are none of our business.
    @(
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*lulu_bot.py*" }
    )
}

function Stop-Lulu {
    <#
      Returns $true when nothing of hers is left running.
      Kills the tree: her process first, then anything parented to it.
    #>
    $procs = Get-LuluProcs
    if (-not $procs) { Write-Host "  nothing running"; return $true }

    foreach ($p in $procs) {
        Write-Host ("  stopping pid {0}" -f $p.ProcessId)
        # /T takes children too. A stray child holding her files would break the
        # next start - the same trap the Nyan launcher hit.
        & "$env:SystemRoot\System32\taskkill.exe" /PID $p.ProcessId /T /F 2>&1 |
            ForEach-Object { Write-Host ("    " + $_) }
    }

    # Wait for it to actually die rather than assuming the kill landed.
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Get-LuluProcs)) { return $true }
    }
    return $false
}

Assert-Admin

Write-Host "=== before ==="
Show-Task $luluTask
Get-LuluProcs | ForEach-Object { Write-Host ("  running: pid {0}" -f $_.ProcessId) }

if ($Check) { Write-Host "`n-check given: nothing was written."; exit 0 }

# Fail with a sentence a human can act on. Start-ScheduledTask on a task that
# does not exist throws a raw red error and nothing else - which is exactly what
# a missing task looked like from the outside: "restart says error".
if (-not (Get-ScheduledTask -TaskName $luluTask -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "  FAILED: no scheduled task named '$luluTask'."
    Write-Host "  Nothing can start her until it exists. Register it first:"
    Write-Host "    cd C:\lulu\setup"
    Write-Host "    .\register-task.ps1"
    exit 1
}

$oldIds = @(Get-LuluProcs | ForEach-Object { $_.ProcessId })
Write-Host "`nrestarting ..."

# The task wrapper may own her, so stop that too - but never rely on it alone.
try { Stop-ScheduledTask -TaskName $luluTask -ErrorAction Stop } catch { }
Start-Sleep -Seconds 1

if (-not (Stop-Lulu)) {
    Write-Host "`n  FAILED: her process would not stop."
    Write-Host "  Refusing to start - a second copy would stop her single-instance"
    Write-Host "  lock from clearing, and she would not run at all."
    exit 1
}
Write-Host "  stopped cleanly"

# A stale memory/bot.pid is fine: she checks the pid, finds it dead, and takes
# the lock over. Deleting it here would mask a genuine still-running process.
Start-ScheduledTask -TaskName $luluTask
Write-Host "  task started, waiting for her ..."

$new = $null
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 750
    # IDENTITY, not existence: a pid that was not there before is the only proof.
    $new = Get-LuluProcs | Where-Object { $oldIds -notcontains $_.ProcessId }
    if ($new) { break }
    if (Get-LuluProcs) { Write-Host "  ...a process is up but it is the old one" }
    if ($i -eq 39) { break }
}

if ($new) {
    foreach ($p in $new) { Write-Host ("  restarted - NEW pid {0}" -f $p.ProcessId) }
    Write-Host "`nShe loads her code at startup. Give her a few seconds to reach Discord,"
    Write-Host "then check the journal:  Get-Content 'C:\Lulu\logs\bot.log' -Tail 5"
} else {
    Write-Host "`n  FAILED: she did not come back."
    Write-Host "  No new process appeared. Look at the end of her log:"
    Write-Host "    Get-Content 'C:\Lulu\logs\bot.log' -Tail 20"
    Write-Host "  A line saying 'refusing to stack' means an old copy is still alive."
    exit 1
}

Write-Host "`n=== after ==="
Show-Task $luluTask
Get-LuluProcs | ForEach-Object { Write-Host ("  running: pid {0}" -f $_.ProcessId) }
