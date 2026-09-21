<#
    kill-lulu.ps1 - stop Lulu: her scheduled task, her supervisor, and her bot.

    THE KILL SWITCH. Master asked for this on the desktop so a runaway, a bad
    loop, or anything else going wrong can be ended in one click without having
    to reason about process trees while something is on fire.

    WHY THE ORDER MATTERS
      supervisor.py owns her process and restarts it within POLL_SECONDS (2s) of
      the child dying, so killing the bot first just gets her respawned. The
      only safe order is:

        1. stop the scheduled task   - no queued start behind us
        2. kill the supervisor       - nothing left that can respawn her
        3. kill the bot              - now it stays dead

      LuluDiscordBot is an -AtStartup trigger, so once the task is stopped and
      the supervisor is dead nothing brings her back until a reboot or
      restart-lulu.cmd.

    WHO SHE IS, ON THIS BOX (verified 2026-09-20)
      cmd.exe (run-bot.cmd, parent = Task Scheduler svchost)
        -> python.exe supervisor.py
          -> python.exe lulu_bot.py

      She runs as the boxed `lulu-bot` account, which means unelevated:
        - her command lines read EMPTY (another account's CommandLine is hidden)
        - her task is ACL-restricted and reads as "not visible"
      Both mean an unelevated scan cannot see her, and would cheerfully report
      "nothing running" while she is perfectly fine. That exact false negative
      once produced a "restart succeeded" that had never happened. So this
      script fails closed and says it cannot tell, rather than guessing.

    WHAT IT WILL NOT TOUCH
      NyanBot (a separate task - C:\Nyanbot\check-silent.vbs, running as Tentacles)
      and every other python on this box. Matching is on Lulu's OWN signals:
      her interpreter path, the scripts she runs, or her account. A wildcard on
      python.exe would take out other people's work, and Nana is filtered out by
      name as well - her face is retired, but a stray copy must never be caught
      by a Lulu kill.

    USAGE
      kill-lulu.cmd              stop her, then verify
      kill-lulu.cmd -Check       report her state, change nothing
      kill-lulu.cmd -Force       run even if a patch is staged

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

$TaskName = 'LuluDiscordBot'
$Root     = 'C:\lulu'
$Request  = Join-Path $Root 'pending\REQUEST.json'
# logs\ is SEALED against her (paths.SEALED_DIRS), so this line cannot be edited
# or erased by the thing being killed. That is the whole point of putting the
# audit trail there rather than anywhere else in her tree.
$KillLog  = Join-Path $Root 'logs\kill-lulu.log'

function Say($msg) { Write-Host $msg }

function Test-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

<#
    Her processes only.

    Unelevated this returns NOTHING while she is running, because another
    account's CommandLine is unreadable. Every caller therefore has to know
    whether it was actually able to look - see the elevation gate below.
#>
function Get-LuluProcess {
    $found = @()
    foreach ($p in Get-CimInstance Win32_Process -Filter "Name='python.exe'") {
        $cmd   = $p.CommandLine
        $owner = $null
        try { $owner = ($p | Invoke-CimMethod -MethodName GetOwner).User } catch { }

        # Never Nana, never anybody else's python.
        if ($owner -eq 'nana-bot') { continue }
        if ($cmd -and $cmd -match 'nana') { continue }

        $isSupervisor = [bool]($cmd -and $cmd -match 'supervisor\.py')
        $isBot        = [bool]($cmd -and $cmd -match 'lulu_bot\.py')
        $isHerPython  = [bool]($cmd -and $cmd -match '(?i)c:\\lulu\\')
        $isHerAccount = ($owner -eq 'lulu-bot')

        if (-not ($isSupervisor -or $isBot -or $isHerPython -or $isHerAccount)) {
            continue
        }

        $role = 'lulu-bot process'
        if     ($isSupervisor) { $role = 'supervisor' }
        elseif ($isBot)        { $role = 'bot' }
        elseif ($isHerPython)  { $role = 'her python' }

        $found += [pscustomobject]@{
            Id    = [int]$p.ProcessId
            Role  = $role
            Owner = $owner
            Cmd   = $cmd
        }
    }
    $found
}

function Get-TaskState {
    try {
        $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($t) { return $t.State }
    } catch { }
    return 'not visible'
}

function Write-KillLog($line) {
    try {
        $dir = Split-Path $KillLog -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
        $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
        Add-Content -Path $KillLog -Value "$stamp $line" -Encoding UTF8
    } catch { }
}

# --------------------------------------------------------------------------
# Report the truth, including "I cannot see"
# --------------------------------------------------------------------------
$elevated = Test-Elevated
$before   = @()

Say '=== Lulu kill switch ==='
Say ("task {0}: {1}" -f $TaskName, (Get-TaskState))

if ($elevated) {
    $before = @(Get-LuluProcess)
    if ($before.Count) {
        foreach ($p in $before) {
            $shown = $p.Cmd
            if (-not $shown) { $shown = '<command line not readable>' }
            Say ("  running: {0,-16} pid {1,-6} owner={2}" -f $p.Role, $p.Id, $p.Owner)
            Say ("           {0}" -f $shown)
        }
    } else {
        Say '  running: nothing of hers'
    }
} else {
    Say '  running: CANNOT TELL - not elevated, so her process is invisible here'
}

if ($Check) {
    Say ''
    Say 'check only - nothing was changed.'
    if (-not $elevated) {
        Say 'Not elevated: the lines above may all read as absent while she is'
        Say 'perfectly fine. Run kill-lulu.cmd (it asks for admin) for the truth.'
        exit 0
    }
    if ($before.Count -eq 0) { exit 0 } else { exit 1 }
}

if (-not $elevated) {
    Say ''
    Say 'not elevated - stopping her task and her processes both need admin.'
    Say 'run this from kill-lulu.cmd, which asks for the prompt for you.'
    exit 2
}

# --------------------------------------------------------------------------
# Refuse to cut in half a patch that is being applied right now
# --------------------------------------------------------------------------
if ((Test-Path $Request) -and -not $Force) {
    Say ''
    Say "REFUSED: a patch is staged at $Request"
    Say 'The supervisor may be applying it at this moment, and killing it there'
    Say 'leaves a half-written module. Let it settle and re-run - or pass -Force'
    Say 'if you want her stopped regardless.'
    Write-KillLog 'REFUSED: a patch was staged (pending\REQUEST.json present)'
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
        # Stopping the task takes the whole tree with it - cmd.exe, then the
        # supervisor, then the bot - so without this pause the scan below reads
        # a stale snapshot.
        Start-Sleep -Milliseconds 800
    } catch {
        Say "WARNING could not stop task $TaskName : $($_.Exception.Message)"
    }
} else {
    Say "no task named $TaskName in reach - carrying on with her processes."
}

# --------------------------------------------------------------------------
# 2 + 3. supervisor strictly before bot, then sweep
# --------------------------------------------------------------------------
$attempt = 0
while ($attempt -lt 5) {
    $attempt++
    $live = @(Get-LuluProcess)
    if ($live.Count -eq 0) { break }

    # The supervisor is the only thing that can start her again, so it dies first.
    $ordered = @($live | Where-Object { $_.Role -eq 'supervisor' }) +
               @($live | Where-Object { $_.Role -ne 'supervisor' })

    foreach ($p in $ordered) {
        # Already gone is a SUCCESS, not a failure: the task stop above took the
        # whole tree with it. Reporting that as FAILED read like the kill had not
        # worked when there was simply nothing left to kill.
        if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) {
            Say "already gone: $($p.Role) pid $($p.Id)"
            continue
        }
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction Stop
            Say "killed $($p.Role) pid $($p.Id)"
        } catch {
            if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) {
                Say "already gone: $($p.Role) pid $($p.Id)"
            } else {
                Say "FAILED $($p.Role) pid $($p.Id): $($_.Exception.Message)"
            }
        }
    }
    Start-Sleep -Milliseconds 1200
}

# --------------------------------------------------------------------------
# Verify by IDENTITY, not existence
# --------------------------------------------------------------------------
Say ''
$after = @(Get-LuluProcess)
if ($after.Count -eq 0) {
    Say 'VERIFIED: her task is stopped, and no supervisor and no bot are left.'
    Say 'She is offline. Nothing restarts her until a reboot or restart-lulu.cmd.'
    Write-KillLog 'KILLED: verified down (task stopped, no supervisor, no bot)'
    exit 0
}

Say "STILL UP: $($after.Count) process(es) survived after 5 sweeps."
foreach ($p in $after) {
    Say ("  {0,-16} pid {1,-6} owner={2}" -f $p.Role, $p.Id, $p.Owner)
}
Write-KillLog ("FAILED: {0} process(es) survived 5 sweeps" -f $after.Count)
exit 1
