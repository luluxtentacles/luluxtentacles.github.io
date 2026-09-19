# Confine Lulu's FILE ACCESS to her own folder, with deny ACEs.
#
#   powershell -ExecutionPolicy Bypass -File confine-lulu.ps1          # CHECK (default, changes nothing)
#   powershell -ExecutionPolicy Bypass -File confine-lulu.ps1 -Apply   # write the deny ACEs
#   powershell -ExecutionPolicy Bypass -File confine-lulu.ps1 -Undo    # remove them again
#
# CHECK IS THE DEFAULT. ACL surgery on a live service account should not happen
# because somebody pressed Enter.
#
# ---------------------------------------------------------------------------
# WHY DENY ACEs AND NOT GROUP POLICY
# ---------------------------------------------------------------------------
# Master asked for this "windows active directory style". This box is a
# WORKGROUP machine - there is no domain and no DC - so the only AD-shaped thing
# available is LOCAL policy (gpedit / secpol). Two mechanisms live there, and
# they answer two different questions:
#
#   WHO MAY RUN WHAT   -> Software Restriction Policies, or AppLocker.
#   WHO MAY READ WHAT  -> ACLs. This file.
#
# The first is a WHITELIST. Allowing only C:\lulu there would stop cmd.exe,
# powershell.exe, npm.cmd and npx.cmd dead - npm spawns node, runs postinstall
# scripts out of Temp, and python needs System32 DLLs. Applying it would undo
# the general shell master just asked for. Execution confinement and "run
# anything in her own folder" cannot both be true; that is the mechanism, not a
# tuning problem. So this file does NOT touch execution.
#
#   Note on AppLocker specifically: Microsoft documents it for Enterprise and
#   Education. This is Windows 11 Pro. The AppID service exists here but
#   enforcement on Pro is not supported, so nothing should be built on it.
#
# A DENY ACE is how Windows actually locks a path down, and it is the right tool
# here because DENY BEATS ALLOW in ACL evaluation, including inherited allows.
# Her read access to most of this box comes from inherited grants to
# `Users` / `Authenticated Users`, which she is a member of - she has no ACE of
# her own on C:\Users\Kei and can still be affected by those groups' entries.
# A deny placeholder for `lulu-bot` overrides all of it.
#
# ---------------------------------------------------------------------------
# THE EXCEPTION THAT MATTERS
# ---------------------------------------------------------------------------
# She LEGITIMATELY reads one file outside her folder:
#
#   C:\Python\DiscordBotN5\memory\facts.json     granted lulu-bot:(R) by
#                                                create-bot-account.ps1
#
# That is Nyan's people ledger - the bridge that lets her know who is who, and
# it is covered by a smoke check (169 cards bridging 158 accounts). A naive
# deny on C:\Python would inherit down onto that file, and because DENY BEATS
# ALLOW the inherited deny would beat its explicit grant and silently break the
# bridge. So the script denies C:\Python and then BREAKS INHERITANCE on that one
# file and re-grants it explicitly. Inherited deny no longer reaches it.
#
# Reversible: icacls /remove:d on each path. -Undo does exactly that.
[CmdletBinding()]
param(
    [string]$Account = "lulu-bot",
    [switch]$Apply,
    [switch]$Undo
)

$ErrorActionPreference = "Stop"

# Paths she must not reach. Her folder is C:\Lulu and is deliberately absent.
# Each entry: the path, and why it is on the list - so a future reader can tell
# a considered decision from an accident.
$Deny = @(
    @{ Path = "C:\Users\Kei"; Why = "master's profile" },
    @{ Path = "C:\Nana";      Why = "the den: persona, memory store, skills" },
    @{ Path = "C:\Nyanbot";   Why = "Nyan's bot" },
    @{ Path = "C:\Python";    Why = "Nyan's ledger lives here (one file excepted)" }
)

# Files under a denied root that she must keep reading. Inheritance is broken on
# these and the grant is re-applied by hand - see the header.
$Except = @(
    @{ Path = "C:\Python\DiscordBotN5\memory\facts.json"; Why = "Nyan's ledger: her bridge" }
)

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "This needs an ADMIN shell - it rewrites ACLs outside C:\Lulu."
        Write-Host "Right-click PowerShell -> Run as administrator, then re-run."
        Write-Host "(The plain -Check read needs no elevation: run it as you are.)"
        exit 1
    }
}

function Get-BotAce([string]$path) {
    $out = icacls $path 2>&1 | Out-String
    @($out -split "`r?`n" | Where-Object { $_ -match [regex]::Escape($Account) })
}

function Test-Denied([string]$path) {
    $aces = Get-BotAce $path
    if ($aces.Count -eq 0) { return $false }
    return [bool](($aces -join " ") -match '\(DENY\)')
}

function Show-State {
    param([string]$Label)
    Write-Host "`n=== $Label ==="
    foreach ($entry in $Deny) {
        $p = $entry.Path
        if (-not (Test-Path -LiteralPath $p)) {
            Write-Host ("  {0,-24} ABSENT   ({1})" -f $p, $entry.Why)
            continue
        }
        $denied = Test-Denied $p
        Write-Host ("  {0,-24} {1}   ({2})" -f $p,
            $(if ($denied) { "DENIED for $Account" } else { "reachable" }), $entry.Why)
        foreach ($ace in (Get-BotAce $p)) { Write-Host ("      " + $ace.Trim()) }
    }
    foreach ($entry in $Except) {
        $p = $entry.Path
        if (-not (Test-Path -LiteralPath $p)) {
            Write-Host ("  {0,-24} ABSENT   (exception: {1})" -f $p, $entry.Why)
            continue
        }
        Write-Host ("  {0,-24} exception ({1})" -f $p, $entry.Why)
        foreach ($ace in (Get-BotAce $p)) { Write-Host ("      " + $ace.Trim()) }
    }
}

$me = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$mode = if ($Undo) { 'undo' } elseif ($Apply) { 'apply' } else { 'check' }
Write-Host "=== confine-lulu ==="
Write-Host "account : $Account"
Write-Host "running : $me"
Write-Host "mode    : $mode"

Show-State $(if ($mode -eq 'check') { 'current state (nothing written)' } else { 'before' })

if ($mode -eq 'check') {
    Write-Host "`n-check is the default: nothing was written. Re-run with -Apply."
    Write-Host "This confines FILE ACCESS only. It does not and cannot confine what"
    Write-Host "she may EXECUTE - see the header for why those are different asks."
    exit 0
}

Assert-Admin

if ($mode -eq 'undo') {
    Write-Host "`nremoving deny ACEs ..."
    foreach ($entry in $Deny) {
        $p = $entry.Path
        if (-not (Test-Path -LiteralPath $p)) { continue }
        icacls $p /remove:d "${Account}" | Out-Null
        Write-Host "  cleared $p"
    }
    Write-Host "`nUndone. Re-granting the ledger read explicitly, in case inheritance"
    Write-Host "was left broken on it."
    foreach ($entry in $Except) {
        $p = $entry.Path
        if (-not (Test-Path -LiteralPath $p)) { continue }
        icacls $p /inheritance:e | Out-Null
        Write-Host "  inheritance restored on $p"
    }
    Show-State 'after undo'
    exit 0
}

# -- apply ------------------------------------------------------------------
# Order matters. Deny the parent FIRST, then carve the exceptions out of it by
# breaking their inheritance - otherwise the inheritable deny lands on the
# exception and, since deny beats allow, the explicit grant would lose.
Write-Host "`nconfining ..."
$failed = @()
foreach ($entry in $Deny) {
    $p = $entry.Path
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Host "  skipped (absent): $p"
        continue
    }
    # (OI)(CI) so it inherits to files and subfolders beneath.
    # No 2>&1 here on purpose: under $ErrorActionPreference='Stop', PS 5.1 can turn
    # a native command's stderr into a terminating error, which would abort the
    # loop HALF-WAY THROUGH the ACL changes and leave the box in the exact
    # partially-applied state this script exists to avoid. Plain | Out-Null keeps
    # stderr visible on a failure without ever becoming fatal.
    icacls $p /deny "${Account}:(OI)(CI)(F)" | Out-Null

    # The wait is not superstition: a deny is checked by reading the ACL back,
    # and a check that races the write reports a false failure.
    Start-Sleep -Milliseconds 300
    if (Test-Denied $p) {
        Write-Host "  ok      $p  - denied to $Account"
    } else {
        Write-Host "  FAILED  $p  - deny did not take"
        $failed += $p
    }
}

Write-Host "`nre-granting the exceptions ..."
foreach ($entry in $Except) {
    $p = $entry.Path
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Host "  skipped (absent): $p"
        continue
    }
    # Break inheritance so the parent's deny no longer reaches this file, then
    # put back full control for the humans and SYSTEM (breaking inheritance
    # drops the inherited grants too) and read for the bot.
    icacls $p /inheritance:r `
        /grant:r "Administrators:(F)" `
        /grant:r "SYSTEM:(F)" `
        /grant:r "${me}:(F)" `
        /grant:r "${Account}:(R)" | Out-Null
    Start-Sleep -Milliseconds 300

    $denied = Test-Denied $p
    $readable = [bool]((Get-BotAce $p) -join " " -match '\((R|M|F)\)')
    if ($denied -or -not $readable) {
        Write-Host "  FAILED  $p  - denied=$denied readable=$readable"
        $failed += $p
    } else {
        Write-Host "  ok      $p  - still readable, inheritance broken"
    }
}

Show-State 'after'

if ($failed.Count) {
    Write-Host "`nFAILED: $($failed.Count) path(s) did not come out as intended."
    Write-Host "  " + ($failed -join ", ")
    Write-Host "Run -Undo to put everything back:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File $($MyInvocation.MyCommand.Path) -Undo"
    exit 1
}

Write-Host "`nConfine complete. $Account can no longer reach:"
foreach ($entry in $Deny) { Write-Host "  $($entry.Path)   ($($entry.Why))" }
Write-Host ""
Write-Host "Her own folder, her profile, her Temp and her runtime are untouched, so"
Write-Host "nothing about running her changed. This does NOT limit what she can run."
Write-Host ""
Write-Host "If anything breaks, restore the inherited ACLs with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File $($MyInvocation.MyCommand.Path) -Undo"
