<#
    kill-nana.ps1 - stop Nana's Discord bot and her supervisor, so Lulu can be
    edited without a live bot fighting for the same files (and, later, the same
    gateway session).

    WHY THE ORDER MATTERS
      supervisor.py owns her process. If the child dies the supervisor restarts
      her within POLL_SECONDS (2s), so killing the bot first just gets her
      respawned. The only safe order is:

        1. stop the scheduled task   - no queued start behind us
        2. kill the supervisor       - nothing left that can respawn her
        3. kill the bot              - now it stays dead

      The task is -AtStartup only, so once the supervisor is gone nothing
      brings it back. A reboot is how she comes back, and restart-nana.cmd is
      how you start her by hand.

    WHO SHE IS, ON THIS BOX (verified 2026-09-19)
      cmd.exe (run-bot.cmd, parent = Task Scheduler svchost)
        -> python.exe supervisor.py
          -> python.exe nana_bot.py

      Both python processes run as the boxed `nana-bot` account and their
      command lines are unreadable to a normal user. That is why this needs
      elevation, and why we match on several signals instead of one.

    USAGE
      kill-nana.cmd              stop her, then verify
      kill-nana.cmd -Check       report her state, change nothing
      kill-nana.cmd -Force       run even if a patch is staged

    EXIT CODES
      0  she is down (or -Check found nothing)
      1  something survived
      2  not elevated
      3  refused: a patch is staged in pending\REQUEST.json
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$TaskName  = 'NanaDiscordBot'
$DenRoot   = 'C:\Nana\discord'
$Request   = Join-Path $DenRoot 'pending\REQUEST.json'

function Say($msg) { Write-Host $msg }

function Test-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

<#
    Find her processes.

    Three signals, any of which is enough, because none of them is reliable on
    its own: the command line names the script it is running, C:\Nana\Python311
    is the den interpreter run-bot.cmd pins, and `nana-bot` is her account.
    Lulu is filtered out explicitly - she will run the same supervisor.py out of
    C:\lulu one day, and killing her by accident is the whole failure this
    script exists to avoid.
#>
function Get-NanaProcess {
    $found = @()
    foreach ($p in Get-CimInstance Win32_Process -Filter "Name='python.exe'") {
        $cmd   = $p.CommandLine
        $owner = $null
        try { $owner = ($p | Invoke-CimMethod -MethodName GetOwner).User } catch { }

        if ($cmd -and ($cmd -match 'lulu')) { continue }

        $isSupervisor = [bool]($cmd -and ($cmd -match 'supervisor\.py'))
        $isBot        = [bool]($cmd -and ($cmd -match 'nana_bot\.py'))
        $isDenPython  = [bool]($cmd -and $cmd.Contains('C:\Nana\Python311'))
        $isHerAccount = ($owner -eq 'nana-bot')

        if (-not ($isSupervisor -or $isBot -or $isDenPython -or $isHerAccount)) {
            continue
        }

        $role = 'nana-bot account'
        if ($isSupervisor)    { $role = 'supervisor' }
        elseif ($isBot)       { $role = 'bot' }
        elseif ($isDenPython) { $role = 'den python' }

        $found += [pscustomobject]@{
            Pid   = [int]$p.ProcessId
            Role  = $role
            Owner = $owner
            Cmd   = $cmd
        }
    }
    $found
}

function Get-TaskInfo {
    $t = $null
    try { $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch { }
    if ($t) { return "state $($t.State)" }
    # Not visible: either it is not registered, or its ACL hides it from an
    # unelevated caller. Both are only knowable by trying to touch it.
    return 'not visible'
}

# --------------------------------------------------------------------------
# Elevation gate
# --------------------------------------------------------------------------
if (-not (Test-Elevated)) {
    Say 'not elevated - stopping her task and her processes both need admin.'
    Say 'run this from kill-nana.cmd, which asks for the prompt for you.'
    exit 2
}

Say "task $TaskName`: $(Get-TaskInfo)"
$before = @(Get-NanaProcess)
Say "processes found: $($before.Count)"
foreach ($p in $before) {
    $cmd = $p.Cmd
    if (-not $cmd) { $cmd = '<command line not readable>' }
    Say ("  {0,-15} pid {1,-6} owner={2}" -f $p.Role, $p.Pid, $p.Owner)
    Say ("                  {0}" -f $cmd)
}

if ($Check) {
    Say ''
    Say 'check only - nothing changed.'
    if ($before.Count -eq 0) { exit 0 } else { exit 1 }
}

# --------------------------------------------------------------------------
# Refuse to interrupt a patch mid-flight
# --------------------------------------------------------------------------
if ((Test-Path $Request) -and -not $Force) {
    Say ''
    Say "REFUSED: a patch is staged at $Request"
    Say 'The supervisor may be applying it right now - killing it there leaves a'
    Say 'half-applied edit. Let it settle, then re-run, or use -Force.'
    exit 3
}

# --------------------------------------------------------------------------
# 1. the scheduled task
# --------------------------------------------------------------------------
Say ''
$task = $null
try { $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch { }
if ($task) {
    try {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        Say "stopped task $TaskName (was $($task.State))"
        # Stopping the task kills the whole tree - cmd.exe, then the supervisor,
        # then the bot - so the processes below are usually already gone by the
        # time we look. Without this pause the scan reads a stale snapshot.
        Start-Sleep -Milliseconds 800
    } catch {
        Say "WARNING could not stop task $TaskName`: $($_.Exception.Message)"
    }
} else {
    Say "no task named $TaskName in reach - starting from a manual run?"
    Say 'carrying on with her processes.'
}

# --------------------------------------------------------------------------
# 2 + 3. supervisor before bot, then sweep
# --------------------------------------------------------------------------
$attempt = 0
while ($attempt -lt 5) {
    $attempt++
    $live = @(Get-NanaProcess)
    if ($live.Count -eq 0) { break }

    # Supervisor strictly first: it is the only thing that can start her again.
    $ordered = @($live | Where-Object { $_.Role -eq 'supervisor' }) +
               @($live | Where-Object { $_.Role -ne 'supervisor' })

    foreach ($p in $ordered) {
        # Already gone is a SUCCESS, not a failure: the task stop above took the
        # whole tree with it. Reporting that as FAILED read like the kill had
        # not worked when there was simply nothing left to kill.
        if (-not (Get-Process -Id $p.Pid -ErrorAction SilentlyContinue)) {
            Say "already gone: $($p.Role) pid $($p.Pid)"
            continue
        }
        try {
            Stop-Process -Id $p.Pid -Force -ErrorAction Stop
            Say "killed $($p.Role) pid $($p.Pid)"
        } catch {
            if (-not (Get-Process -Id $p.Pid -ErrorAction SilentlyContinue)) {
                Say "already gone: $($p.Role) pid $($p.Pid)"
            } else {
                Say "FAILED $($p.Role) pid $($p.Pid): $($_.Exception.Message)"
            }
        }
    }
    Start-Sleep -Milliseconds 1200
}

# --------------------------------------------------------------------------
# Verify
# --------------------------------------------------------------------------
Say ''
$after = @(Get-NanaProcess)
if ($after.Count -eq 0) {
    Say "VERIFIED: no $($TaskName) task running, no supervisor, no bot."
    Say 'She is offline. restart-nana.cmd starts her again.'
    exit 0
}

Say "STILL UP: $($after.Count) process(es) survived after 5 sweeps."
foreach ($p in $after) {
    Say ("  {0,-15} pid {1,-6} owner={2}" -f $p.Role, $p.Pid, $p.Owner)
}
exit 1
