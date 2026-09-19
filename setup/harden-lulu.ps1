# Harden Lulu's trusted base at the OS level.
#
#   powershell -ExecutionPolicy Bypass -File harden-lulu.ps1           # CHECK (default, changes nothing)
#   powershell -ExecutionPolicy Bypass -File harden-lulu.ps1 -Apply    # write the ACLs
#   powershell -ExecutionPolicy Bypass -File harden-lulu.ps1 -Undo     # put it back
#
# CHECK IS THE DEFAULT on purpose. A script that rewrites filesystem ACLs on a
# live service account should not do it because somebody pressed Enter.
#
# ---------------------------------------------------------------------------
# WHY THERE IS A SECOND LAYER AT ALL
# ---------------------------------------------------------------------------
# paths.py already seals these files against TOOL CALLS: SEALED_NAMES and
# SEALED_DIRS, consulted by assert_writable, assert_proposable, and - since the
# pipeline fix - pipeline.apply() as well. So a write_file or a proposed patch
# cannot reach them.
#
# That seal is in-process, and paths.py says so itself: "this is an in-process
# guard, not an OS jail. Code that imports open() directly could bypass it."
# tools.py is proposable, so a patch to tools.py runs in her process, and code
# in her process can call open() directly. Against THAT, a Python guard is a
# speed bump. The account boundary is not: she runs as lulu-bot, so an ACL that
# gives lulu-bot read-only on these files stops a bare write even when the
# Python guard is bypassed entirely.
#
# This is the layer that makes "the supervisor cannot be changed" true rather
# than merely intended - she cannot patch the thing that restores her, and she
# cannot edit the net that judges her, so whatever else she does to herself,
# supervisor.py plus tests/smoke_test.py can still revert her and bring her up.
#
# ---------------------------------------------------------------------------
# WHAT IS *NOT* IN THIS LIST, AND WHY THAT MATTERS MORE THAN WHAT IS
# ---------------------------------------------------------------------------
# The tool seal and this ACL MUST differ. The seal governs TOOL CALLS; this
# governs her whole PROCESS, and her process legitimately writes things the
# tools are forbidden from touching. Sealing any of these would break her:
#
#   memory\        her RUNTIME STATE - bot.pid, health.marker, her ledgers and
#                  journals. She takes her own pidlock and writes her own health
#                  marker. Read-only here and she cannot start, and the
#                  supervisor reads a missing marker as "never came up".
#   logs\          the launcher redirects her stdout into logs\bot.log. Sealed,
#                  she starts mute and the audit trail stops.
#   .git\          the pipeline's checkpoint runs git add and git commit. Sealed,
#                  every self-edit stops being revertible - the net loses its net.
#   pending\       the staging area the pipeline itself writes.
#   node_cache\    npx downloads into it.
#   her own .py    tools.py, lulu_bot.py and friends are PROPOSABLE BY DESIGN:
#                  the pipeline has to be able to write them, or she could never
#                  change herself. Guarding them here would delete the feature.
#
# So this list is the code that RUNS her, the credentials, and the net - nothing
# she needs to write while alive.
#
# ---------------------------------------------------------------------------
# HONEST LIMIT
# ---------------------------------------------------------------------------
# This blocks OVERWRITE of those files, which is the realistic self-edit path.
# It does NOT block their DELETION: deleting a file needs FILE_DELETE_CHILD on
# the containing folder, and C:\lulu grants lulu-bot Modify there - which she
# needs for everything that is not protected. Deleting one of these is
# therefore still possible and is recoverable with `git checkout`; it is a
# denial-of-service, not a takeover. Tightening it further means per-folder
# DELETE_CHILD surgery, which is doable but is a bigger change than this one.
[CmdletBinding()]
param(
    [string]$BotRoot = "C:\Lulu",
    [string]$Account = "lulu-bot",
    [switch]$Apply,
    [switch]$Undo
)

$ErrorActionPreference = "Stop"

# The code that runs her, the keys, the net, and the launcher chain.
$Protected = @(
    # the wall, the judge, the restarter
    "paths.py", "supervisor.py", "pipeline.py",
    # credentials and the config naming them
    "config.json", "config.example.json", "brain_key.txt", ".gitignore",
    "mcp_secrets.json", "mcp_secrets.example.json",
    # the net that judges every self-edit
    "tests\smoke_test.py",
    # what actually runs at startup, and the scripts that repair it
    "setup\run-bot.cmd", "setup\watch-console.cmd", "setup\restart-lulu.cmd",
    "setup\register-task.ps1", "setup\create-bot-account.ps1",
    "setup\finish-setup.ps1", "setup\make-shortcuts.ps1"
)

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "This needs an ADMIN shell - the apply step rewrites ACLs on C:\Lulu."
        Write-Host "Right-click PowerShell -> Run as administrator, then re-run."
        Write-Host "(The plain -Check read needs no elevation: run it as you are.)"
        exit 1
    }
}

function Get-BotAce([string]$path) {
    # What icacls says about this account on this file, in icacls' own words.
    $out = icacls $path 2>&1 | Out-String
    @($out -split "`r?`n" | Where-Object { $_ -match [regex]::Escape($Account) })
}

function Test-BotWritable([string]$path) {
    $aces = Get-BotAce $path
    if ($aces.Count -eq 0) { return $false }   # no ACE: nothing to write with
    return [bool](($aces -join " ") -match '\((M|W|F)\)')
}

function Show-Protected {
    param([string]$Label)
    Write-Host "`n=== $Label ==="
    foreach ($rel in $Protected) {
        $full = Join-Path $BotRoot $rel
        if (-not (Test-Path -LiteralPath $full)) {
            Write-Host ("  {0,-34} MISSING (skipped)" -f $rel)
            continue
        }
        $writable = Test-BotWritable $full
        $mark = if ($writable) { "WRITABLE" } else { "read-only" }
        Write-Host ("  {0,-34} {1}" -f $rel, $mark)
        foreach ($ace in (Get-BotAce $full)) { Write-Host ("      " + $ace.Trim()) }
    }
}

$me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
Write-Host "=== harden-lulu ==="
Write-Host "root    : $BotRoot"
Write-Host "account : $Account"
Write-Host "running : $me"

$mode = if ($Undo) { 'undo' } elseif ($Apply) { 'apply' } else { 'check' }
Write-Host "mode    : $mode"

Show-Protected $(if ($mode -eq 'check') { 'current state (nothing written)' } else { 'before' })

if ($mode -eq 'check') {
    Write-Host "`n-check is the default: nothing was written. Re-run with -Apply to harden."
    exit 0
}

# Elevation is only needed to WRITE. Check is a read - icacls and Test-Path work
# unelevated - so the gate sits here rather than at the top: you can preview the
# state before committing to anything, from an ordinary shell, and the part that
# changes nothing stays runnable by anyone. It also means this file's read path
# can be verified without admin, which is how it was tested.
Assert-Admin

if ($mode -eq 'undo') {
    Write-Host "`nresetting to inherited permissions ..."
    foreach ($rel in $Protected) {
        $full = Join-Path $BotRoot $rel
        if (-not (Test-Path -LiteralPath $full)) { continue }
        icacls $full /reset | Out-Null
        Write-Host "  reset $rel"
    }
    Show-Protected 'after reset'
    Write-Host "`nUndone. The files are back to inheriting from $BotRoot."
    exit 0
}

# -- apply ------------------------------------------------------------------
# /inheritance:r drops every inherited ACE first, and that is the whole point:
# lulu-bot's write access does NOT come from its own entry, it comes from
# 'Authenticated Users:(M)' inherited off C:\lulu. Replacing only the lulu-bot
# entry would leave that inherit intact and change nothing. So: strip, then
# grant explicitly - full control to the humans and SYSTEM, read to the bot.
Write-Host "`nhardening ..."
$failed = @()
foreach ($rel in $Protected) {
    $full = Join-Path $BotRoot $rel
    if (-not (Test-Path -LiteralPath $full)) {
        Write-Host "  skipped (missing): $rel"
        continue
    }
    icacls $full /inheritance:r `
        /grant:r "Administrators:(F)" `
        /grant:r "SYSTEM:(F)" `
        /grant:r "${me}:(F)" `
        /grant:r "${Account}:(R)" | Out-Null
    if (Test-BotWritable $full) {
        Write-Host "  FAILED  $rel  - still writable"
        $failed += $rel
    } else {
        Write-Host "  ok      $rel  - read-only for $Account"
    }
}

Show-Protected 'after'

if ($failed.Count) {
    Write-Host "`nFAILED: $($failed.Count) file(s) are still writable by $Account."
    Write-Host "  " + ($failed -join ", ")
    Write-Host "Undo with -Undo if anything looks wrong."
    exit 1
}

Write-Host "`nHarden complete. supervisor.py, pipeline.py, paths.py and the smoke test"
Write-Host "are now read-only to $Account, so a bare write from her process is denied"
Write-Host "by Windows rather than merely discouraged by paths.py."
Write-Host ""
Write-Host "Her next start is unaffected: read and execute were never taken away."
Write-Host "If she ever fails to come back, restore everything with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File $($MyInvocation.MyCommand.Path) -Undo"
