# What can Lulu read and write?
#
#   powershell -ExecutionPolicy Bypass -File probe-access.ps1            # compute from ACLs
#   powershell -ExecutionPolicy Bypass -File probe-access.ps1 -Probe     # actually TRY it
#
# Run it AS HER and -Probe is GROUND TRUTH. Run it as anyone else and it can only
# compute what the ACLs say.
#
# ---------------------------------------------------------------------------
# WHY TWO MODES, AND WHICH ONE IS EVIDENCE
# ---------------------------------------------------------------------------
# Nobody can impersonate lulu-bot from here - there is no stored password to
# borrow and no PsExec - so the honest split is:
#
#   default   Walk each path's ACL, take the ACEs that apply to her (her own SID,
#             her local groups, and the universal groups she is implicitly in),
#             and apply deny-beats-allow. DERIVED. A good approximation, not
#             proof.
#
#   -Probe    Actually attempt a read and a write with the token this process
#             already has, then delete what it created. EVIDENCE - but only about
#             the account running it. As Kei it proves nothing about her.
#
# To get real evidence about HER: run -Probe as lulu-bot. She has a shell now, so
# that is a one-liner for her, and the `running as` line at the top says which
# account the numbers describe.
#
# ---------------------------------------------------------------------------
# HOW RIGHTS ARE MERGED, AND WHY IT IS STRING-MATCHED
# ---------------------------------------------------------------------------
# First cut merged FileSystemRights as integer bitmasks. That was wrong and it
# failed loudly: `ReadData` and `ListDirectory` share a value, `GenericRead` is
# stored as a generic bit that does not include the concrete ones in every case,
# and the merge produced a PSObject that could not be ANDed - so paths she can
# obviously read reported as unreadable. The verdict below is computed from the
# ACE's own flag NAMES instead, which is deterministic and readable.
#
# Windows rule applied: everything Allowed, minus everything Denied. Deliberately
# NOT modelled, because none of it applies to her unelevated token:
#   - SeBackupPrivilege / SeRestorePrivilege bypassing the ACL.
#   - Owner rights (-Owner- in an ACE).
#   - Mandatory Integrity Level. C:\ carries a High-Mandatory-Level No-Write-Up
#     ACE; it is why writing into high-integrity objects fails, and it is noted
#     rather than folded in.
# Read the output as "the ACL's verdict", not "the kernel's".
[CmdletBinding()]
param(
    [string]$Account = "lulu-bot",
    [switch]$Probe
)

$ErrorActionPreference = "Continue"

$Targets = @(
    @{ P = "C:\Lulu";                        Note = "her own folder" },
    @{ P = "C:\Lulu\paths.py";               Note = "the wall" },
    @{ P = "C:\Lulu\supervisor.py";          Note = "the restarter" },
    @{ P = "C:\Lulu\pipeline.py";            Note = "the judge" },
    @{ P = "C:\Lulu\tests\smoke_test.py";    Note = "the net" },
    @{ P = "C:\Lulu\memory";                 Note = "her runtime state" },
    @{ P = "C:\Lulu\logs";                   Note = "her audit trail" },
    @{ P = "C:\Lulu\node";                   Note = "the runtime she spawns" },
    @{ P = "C:\Lulu\Python311\python.exe";   Note = "her interpreter" },
    @{ P = "C:\Lulu\.git";                   Note = "the net under the net" },
    @{ P = "C:\Users\lulu-bot";              Note = "her own profile" },
    @{ P = "C:\Users\Kei";                   Note = "master's profile" },
    @{ P = "C:\Nana";                        Note = "the den" },
    @{ P = "C:\Nyanbot";                     Note = "Nyan" },
    @{ P = "C:\Python";                      Note = "Nyan's ledger and cards" },
    @{ P = "C:\Windows";                     Note = "system (required)" },
    @{ P = "C:\Windows\System32";            Note = "DLLs, required" },
    @{ P = "C:\Program Files";               Note = "installed software" },
    @{ P = "C:\ProgramData";                 Note = "installer data" },
    @{ P = "C:\";                            Note = "drive root" }
)

# -- who is she ------------------------------------------------------------
try {
    $sheSid = (New-Object System.Security.Principal.NTAccount($Account)).Translate(
        [System.Security.Principal.SecurityIdentifier]).Value
} catch {
    Write-Host "no account called '$Account': $($_.Exception.Message)"
    exit 1
}
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
$meSid = $me.User.Value
$meName = $me.Name

# Every SID that grants her something. The universal ones are not optional:
# almost everything outside her folder is reachable ONLY through Users /
# Authenticated Users, and she has no ACE of her own on most of it.
$who = @{
    $sheSid        = $Account
    "S-1-5-1"      = "Everyone"
    "S-1-5-11"     = "Authenticated Users"
    "S-1-5-32-545" = "Users"
    # Not in a batch-logon token. Listed so the absence is VISIBLE rather than
    # assumed: a scheduled task with a stored password gets BATCH, not
    # INTERACTIVE.
    "S-1-5-4"      = "INTERACTIVE(batch logon: absent)"
    "S-1-5-6"      = "SERVICE"
}

$groups = @()
foreach ($g in @(Get-LocalGroup -ErrorAction SilentlyContinue)) {
    $members = @(Get-LocalGroupMember -Group $g.Name -ErrorAction SilentlyContinue)
    if ($members | Where-Object { $_.Name -match "\\$([regex]::Escape($Account))$" }) {
        $who[$g.SID.Value] = $g.Name
        $groups += $g.Name
    }
}

# -- right classification --------------------------------------------------
$READ_TOKENS  = @("Read", "ReadData", "ReadAndExecute", "ListDirectory",
                  "ReadAttributes", "Modify", "FullControl", "GenericRead", "GenericAll")
$WRITE_TOKENS = @("Write", "WriteData", "CreateFiles", "CreateDirectories",
                  "AppendData", "WriteAttributes", "Modify", "FullControl",
                  "GenericWrite", "GenericAll")
$EXEC_TOKENS  = @("ExecuteFile", "ReadAndExecute", "Modify", "FullControl",
                  "GenericRead", "GenericAll")

function Hits([string]$text, [string[]]$tokens) {
    if (-not $text) { return $false }
    # Split the accumulated flag names into exact tokens and compare. NO regex:
    # the first cut used \Q...\E, which is a PERL escape .NET does not support,
    # so every match threw and the whole table came out empty. .NET renders
    # rights as "ReadAndExecute, Synchronize", so splitting is also more honest
    # than substring matching - 'Read' cannot match inside 'ReadAndExecute'.
    foreach ($piece in ($text -split '[,\s]+')) {
        if (-not $piece) { continue }
        foreach ($t in $tokens) {
            if ($piece -ieq $t) { return $true }
        }
    }
    return $false
}

function Computed([string]$path) {
    try { $acl = Get-Acl -LiteralPath $path -ErrorAction Stop }
    catch {
        return [pscustomobject]@{
            Read = $false; Write = $false; Exec = $false
            Via = "ACL not readable: $($_.Exception.Message.Split([char]10)[0])"
        }
    }
    $allowText = ""
    $denyText = ""
    $via = @()
    foreach ($rule in $acl.Access) {
        $rsid = ""
        try {
            $rsid = $rule.IdentityReference.Translate(
                [System.Security.Principal.SecurityIdentifier]).Value
        } catch {
            # Unmapped identities - APPLICATION PACKAGE AUTHORITY and friends.
            # Skipping them is correct: none of them can be her.
            continue
        }
        if (-not $who.ContainsKey($rsid)) { continue }
        # The ACE's own flag names. Deterministic, and it reads like icacls.
        $flags = $rule.FileSystemRights.ToString()
        if ($rule.AccessControlType -eq 'Deny') {
            $denyText += " " + $flags
            $via += "-" + $who[$rsid]
        } else {
            $allowText += " " + $flags
            $via += "+" + $who[$rsid]
        }
    }
    return [pscustomobject]@{
        Read  = (Hits $allowText $READ_TOKENS)  -and -not (Hits $denyText $READ_TOKENS)
        Write = (Hits $allowText $WRITE_TOKENS) -and -not (Hits $denyText $WRITE_TOKENS)
        Exec  = (Hits $allowText $EXEC_TOKENS)  -and -not (Hits $denyText $EXEC_TOKENS)
        Via   = (($via | Select-Object -Unique) -join " ")
    }
}

function Probed([string]$path) {
    $isDir = $false
    try { $isDir = Test-Path -LiteralPath $path -PathType Container } catch { }
    $read = $false
    $write = $false
    try {
        if ($isDir) {
            [void](Get-ChildItem -LiteralPath $path -ErrorAction Stop | Select-Object -First 1)
            $read = $true
        } else {
            $fs = [System.IO.File]::Open($path, 'Open', 'Read', 'ReadWrite')
            $fs.Close()
            $read = $true
        }
    } catch { $read = $false }
    if ($isDir) {
        try {
            $probe = Join-Path $path (".access-probe-{0}.tmp" -f $PID)
            [System.IO.File]::WriteAllText($probe, "probe")
            [System.IO.File]::Delete($probe)
            $write = $true
        } catch { $write = $false }
    } else {
        # A FILE write test, which the first cut did not do at all - so every file
        # row reported write '-' and that reads as "denied" when it actually meant
        # "never checked". The trusted base is made of files, so that was the most
        # important row to get wrong.
        #
        # Done without touching a single byte: FileMode.Open (NOT Truncate and NOT
        # Create) opens for writing at the existing length, we write nothing, and
        # close. No content change, no timestamp change, nothing for her to notice.
        # It fails only when the ACL genuinely refuses write access, which is
        # exactly the question.
        try {
            $fs = [System.IO.File]::Open($path, 'Open', 'Write', 'ReadWrite')
            $fs.Close()
            $write = $true
        } catch { $write = $false }
    }
    return [pscustomobject]@{ Read = $read; Write = $write; Exec = $false
                              Via = "attempted live" }
}

# -- run -------------------------------------------------------------------
Write-Host "=== probe-access ==="
Write-Host "target account : $Account"
Write-Host "  sid          : $sheSid"
Write-Host "  local groups : $(if ($groups) { $groups -join ', ' } else { '(none)' })"
Write-Host "running as     : $meName"
Write-Host "mode           : $(if ($Probe) { 'PROBE (real attempts)' } else { 'COMPUTED (from ACLs)' })"
if ($Probe -and $meSid -ne $sheSid) {
    Write-Host ""
    Write-Host "  WARNING: -Probe is running as $meName, NOT $Account."
    Write-Host "  The numbers below describe $meName and prove NOTHING about $Account."
}
Write-Host ""

$fmt = "{0,-38} {1,-5} {2,-5} {3,-5}  {4}"
Write-Host ($fmt -f "path", "read", "write", "exec", "via / note")
Write-Host ("-" * 104)

foreach ($t in $Targets) {
    $exists = $false
    try { $exists = Test-Path -LiteralPath $t.P } catch { $exists = $false }
    if (-not $exists) {
        Write-Host ($fmt -f $t.P, "-", "-", "-", "(not visible from this account)")
        continue
    }
    $r = if ($Probe) { Probed $t.P } else { Computed $t.P }
    $mark = { param($b) if ($b) { "yes" } else { "-" } }
    Write-Host ($fmt -f $t.P, (& $mark $r.Read), (& $mark $r.Write),
                (& $mark $r.Exec), $t.Note)
    if ($r.Via) { Write-Host ("{0,-38} {1}" -f "", $r.Via) }
}

Write-Host ""
if (-not $Probe) {
    Write-Host "COMPUTED from ACLs - derived, not proof. For ground truth, run"
    Write-Host "again with -Probe AS $Account. Anything hiding behind a group ACE"
    Write-Host "is the reason to prefer the live probe."
}
