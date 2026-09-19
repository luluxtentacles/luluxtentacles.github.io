# Confine Lulu's FILE ACCESS to her own folder, with deny ACEs.
#
#   powershell -ExecutionPolicy Bypass -File confine-lulu.ps1          # CHECK (default, changes nothing)
#   powershell -ExecutionPolicy Bypass -File confine-lulu.ps1 -Apply   # write the deny ACEs
#   powershell -ExecutionPolicy Bypass -File confine-lulu.ps1 -Undo    # remove them again
#
# CHECK IS THE DEFAULT. ACL surgery on a live box should not happen because
# somebody pressed Enter.
#
# ---------------------------------------------------------------------------
# WHY DENY ACEs AND NOT GROUP POLICY
# ---------------------------------------------------------------------------
# Master asked for this "windows active directory style". This box is a
# WORKGROUP machine - no domain, no DC - so the only AD-shaped thing available is
# LOCAL policy (gpedit / secpol). Two mechanisms live there and they answer two
# different questions:
#
#   WHO MAY RUN WHAT   -> Software Restriction Policies, or AppLocker.
#   WHO MAY READ WHAT  -> ACLs. This file.
#
# The first is a WHITELIST. Allowing only C:\lulu would stop cmd.exe,
# powershell.exe, npm.cmd and npx.cmd dead - npm spawns node, runs postinstall
# scripts out of Temp, and python needs System32 DLLs. Applying it would undo the
# general shell master asked for. Execution confinement and "run anything in her
# own folder" cannot both be true; that is the mechanism, not a tuning problem.
# So this file does NOT touch execution.
#
#   On AppLocker specifically: Microsoft documents it for Enterprise and
#   Education. This is Windows 11 Pro on a workgroup. Do not build on it here.
#
# A DENY ACE is how Windows locks a path down, and it is the right tool because
# DENY BEATS ALLOW, including inherited allows. Her reach into these folders comes
# from inherited grants to `Users` / `Authenticated Users`, which she is a member
# of - she has no ACE of her own on C:\Users\Kei at all. So "just don't grant her
# anything" would not have closed it; an explicit deny is what does.
#
# ---------------------------------------------------------------------------
# NO EXCEPTIONS, AND THAT IS THE RESULT OF CHECKING RATHER THAN ASSUMING
# ---------------------------------------------------------------------------
# An earlier cut of this script carved exceptions, because Lulu's code names two
# files outside her folder. Both turned out to be unnecessary, and master was
# right to push back on it - carving holes in the sandbox to preserve access to
# ANOTHER bot's files is the opposite of the point. Evidence, measured on the
# live tree rather than reasoned about:
#
#   C:\Python\DiscordBotN5\memory\facts.json      (people.NYAN_LEDGER)
#       people.py:207 reads it ONLY as a fallback when Nyan's drop is unusable.
#       The drop lands inside her own wall at memory/nyan/latest.json and fully
#       replaces it. Proved by pointing NYAN_LEDGER at an unreachable path:
#       the ledger still loaded, 169 people, source latest.json. No exception
#       needed.
#
#   C:\Python\DiscordBotN5\json_data\user_info.json   (people.CARDS)
#       `_read_cards()`, the only function that reads it, HAS NO CALL SITES
#       anywhere in her code. Verified repo-wide. It is dead code. Denying it
#       changes nothing today.
#
# So the deny list is total. If the dead card path is ever revived, the revive
# needs a drop field first - her code's own docstring already says the drop alone
# must resolve, "because the cards file belongs to another bot: if it moves, the
# drop alone still resolves". Do that, don't widen this script.
#
# Her python is C:\lulu\Python311, inside her own folder, so C:\Python is not
# hers and denying it touches nothing she runs.
[CmdletBinding()]
param(
    [string]$Account = "lulu-bot",
    [switch]$Apply,
    [switch]$Undo
)

$ErrorActionPreference = "Stop"

# Everything she should not reach. C:\Users\lulu-bot, her Temp and C:\Lulu are
# all deliberately absent - those are hers and she needs them.
$Deny = @(
    @{ Path = "C:\Users\Kei"; Why = "master's profile" },
    @{ Path = "C:\Nana";      Why = "the den: persona, memory store, skills" },
    @{ Path = "C:\Nyanbot";   Why = "Nyan's bot" },
    @{ Path = "C:\Python";    Why = "Nyan's ledger and cards" }
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
    # Ask the ACL. Do NOT parse icacls text - the first cut grepped its output for
    # the literal '(DENY)' and that string does not exist: icacls renders a deny
    # of FullControl as '(N)', No Access, because that is what it means.
    #
    # Consequence, 2026-09-19: -Apply wrote all four denies correctly and then
    # reported every one of them as FAILED, telling master to -Undo work that had
    # succeeded. A verification that lies in the "undo your work" direction is
    # the worst kind there is, and the lesson is that a check must ask the same
    # system that made the change.
    try {
        $acl = Get-Acl -LiteralPath $path -ErrorAction Stop
    } catch {
        return @()
    }
    @($acl.Access | Where-Object {
        $_.IdentityReference -match "\\$([regex]::Escape($Account))$"
    })
}

function Test-Denied([string]$path) {
    @((Get-BotAce $path) | Where-Object { $_.AccessControlType -eq 'Deny' }).Count -gt 0
}

function Show-State {
    param([string]$Label)
    Write-Host "`n=== $Label ==="
    foreach ($entry in $Deny) {
        $p = $entry.Path
        if (-not (Test-Path -LiteralPath $p)) {
            Write-Host ("  {0,-22} ABSENT   ({1})" -f $p, $entry.Why)
            continue
        }
        $denied = Test-Denied $p
        Write-Host ("  {0,-22} {1}   ({2})" -f $p,
            $(if ($denied) { "DENIED" } else { "reachable" }), $entry.Why)
        foreach ($ace in (Get-BotAce $p)) {
            Write-Host ("      {0} {1}  ({2})" -f $ace.AccessControlType,
                        $ace.FileSystemRights, $ace.IdentityReference)
        }
    }
}

$mode = if ($Undo) { 'undo' } elseif ($Apply) { 'apply' } else { 'check' }
Write-Host "=== confine-lulu ==="
Write-Host "account : $Account"
Write-Host "running : $([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
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
        icacls $p /remove:d "$Account" | Out-Null
        Write-Host "  cleared $p"
    }
    Show-State 'after undo'
    exit 0
}

# -- apply ------------------------------------------------------------------
# No 2>&1 on the icacls calls on purpose: under $ErrorActionPreference='Stop',
# PS 5.1 can turn a native command's stderr into a TERMINATING error, which would
# abort this loop half-way through the changes and leave the box in the exact
# partially-applied state the script exists to avoid.
Write-Host "`nconfining ..."
$failed = @()
foreach ($entry in $Deny) {
    $p = $entry.Path
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Host "  skipped (absent): $p"
        continue
    }
    # (OI)(CI) so the deny inherits to files and subfolders beneath.
    icacls $p /deny "${Account}:(OI)(CI)(F)" | Out-Null

    # Not superstition: the result is read back off the ACL, and a check that
    # races the write reports a false failure.
    Start-Sleep -Milliseconds 300
    if (Test-Denied $p) {
        Write-Host "  ok      $p  - denied to $Account"
    } else {
        Write-Host "  FAILED  $p  - deny did not take"
        $failed += $p
    }
}

Show-State 'after'

if ($failed.Count) {
    Write-Host "`nFAILED: $($failed.Count) path(s) did not take the deny."
    Write-Host "  " + ($failed -join ", ")
    Write-Host "Put everything back with:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File $($MyInvocation.MyCommand.Path) -Undo"
    exit 1
}

Write-Host "`nConfine complete. $Account can no longer reach:"
foreach ($entry in $Deny) { Write-Host "  $($entry.Path)   ($($entry.Why))" }
Write-Host ""
Write-Host "Her own folder, her profile and her Temp are untouched, so nothing about"
Write-Host "running her changed. This does NOT limit what she can run."
Write-Host ""
Write-Host "If anything breaks, restore with:"
Write-Host "  powershell -ExecutionPolicy Bypass -File $($MyInvocation.MyCommand.Path) -Undo"
