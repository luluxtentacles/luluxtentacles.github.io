<#
Creates a dedicated local Windows account for the Discord half of Lulu, and
grants it access to exactly what it needs - nothing else.

MUST RUN ELEVATED. It creates a user and rewrites ACLs; neither is possible
otherwise. It is additive by default: nothing is taken away from you unless you
pass -Strict.

  Elevated PowerShell:
    .\create-bot-account.ps1 -Password '<something-long>' -PythonRoot 'C:\Users\Kei\AppData\Local\Programs\Python\Python311'

  Add -Strict to also seal C:\Lulu against every other local account.

Undo:  .\create-bot-account.ps1 -Undo
#>
[CmdletBinding()]
param(
    [string]$Account = "lulu-bot",
    [string]$Password,
    [string]$BotRoot = "C:\Lulu",
    # The real path, which is what config.json token_source and lulu_bot.py
    # TOKEN_SOURCE both expect. It used to point at C:\Lulu_token.txt, which
    # never existed - so the grant silently did nothing.
    [string]$TokenFile = "C:\Lulu\discord_token.txt",
    # The bot's own python, which lives inside BotRoot since the tree was
    # flattened. Defaulted rather than left empty: an empty value makes the
    # generated launcher call bare `python.exe`, which does not resolve for an
    # account with no user profile.
    [string]$PythonRoot = "C:\lulu-apps\Python311",
    [switch]$Strict,
    [switch]$Undo
)

$ErrorActionPreference = "Stop"

function Assert-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $isAdmin = (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw "This script must run elevated. Right-click PowerShell -> Run as administrator."
    }
}

function Grant($path, $rights) {
    if (-not (Test-Path $path)) { Write-Warning "skipped (missing): $path"; return }
    # /grant:r replaces our own entry, so re-running is idempotent.
    icacls $path /grant:r "${Account}:(OI)(CI)$rights" /T /C | Out-Null
    Write-Host ("  granted {0,-6} {1}" -f $rights, $path)
}

Assert-Elevated

if ($Undo) {
    Write-Host "Removing scheduled task and account..."
    Unregister-ScheduledTask -TaskName "LuluDiscordBot" -Confirm:$false -ErrorAction SilentlyContinue
    if (Get-LocalUser -Name $Account -ErrorAction SilentlyContinue) {
        Remove-LocalUser -Name $Account
        Write-Host "  removed account: $Account"
    }
    Write-Host "Undone. Files under $BotRoot were not touched."
    return
}

if (-not $Password) {
    # Prompt instead of taking it on the command line, so the password never
    # lands in shell history, a transcript, or this conversation.
    $secureInput = Read-Host -Prompt "Password for the $Account account" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureInput)
    try {
        $Password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    if (-not $Password) { throw "No password given." }
}

Write-Host "1. account"
if (Get-LocalUser -Name $Account -ErrorAction SilentlyContinue) {
    Write-Host "  already exists: $Account"
} else {
    $secure = ConvertTo-SecureString $Password -AsPlainText -Force
    New-LocalUser -Name $Account -Password $secure `
        -FullName "Lulu (Discord)" -Description "Runs Lulu's Discord bot. No admin." `
        -PasswordNeverExpires | Out-Null
    Write-Host "  created: $Account"
}

# A standard user is the whole point: no admin, so no UAC prompt can ever be
# answered by the bot, so nothing can install or escalate.
if ((Get-LocalGroupMember -Group Administrators).Name -match "\\$Account$") {
    Remove-LocalGroupMember -Group Administrators -Member $Account
    Write-Host "  removed from Administrators"
}

Write-Host "2. permissions"
Grant $BotRoot "M"                                    # her own folder: read/write
if (Test-Path $TokenFile) {
    icacls $TokenFile /grant:r "${Account}:R" | Out-Null
    Write-Host "  granted R      $TokenFile"
}
if ($PythonRoot) { Grant $PythonRoot "RX" }           # run python
# Deliberately NO read-only grant on memory\. Once the tree was flattened,
# C:\Lulu\memory IS her runtime state - bot.pid, health.marker, her ledgers
# and her journal - so sealing it read-only stops her taking her own pidlock
# and fails her health check, which the supervisor then reads as "never came
# up". The "read the shared store, never write it" rule is enforced in
# shared_memory.py, which can tell the two files apart; a folder ACL cannot.

if ($Strict) {
    Write-Host "3. strict mode: sealing C:\Lulu against other local accounts"
    $den = Split-Path $BotRoot -Parent
    # Grant you full control FIRST, because your current write access on the den
    # comes from 'Authenticated Users', which we are about to remove.
    icacls $den /grant:r "${env:USERNAME}:(OI)(CI)F" | Out-Null
    icacls $den /inheritance:r `
        /grant "Administrators:(OI)(CI)F" `
        /grant "SYSTEM:(OI)(CI)F" | Out-Null
    Write-Host "  sealed $den (only you, Administrators, SYSTEM, and $Account)"
}

Write-Host "4. launcher"
$python = if ($PythonRoot) { Join-Path $PythonRoot "python.exe" } else { "python.exe" }
$launcher = Join-Path $BotRoot "setup\run-bot.cmd"
$body = @"
@echo off
rem Runs Lulu's Discord bot. Started by the LuluDiscordBot scheduled task.
cd /d "$BotRoot"
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8
if not exist "logs" mkdir "logs"
if not exist "$python" (
    echo no python at $python >> "logs\bot.log"
    exit /b 1
)
rem Supervised, not direct. She cannot restart herself - killing her own
rem process is the last thing she can do - so supervisor.py owns her process,
rem and applies any staged self-edit behind git, the smoke test and a health
rem check. Going straight to lulu_bot.py here would bypass all of that.
"$python" supervisor.py >> "logs\bot.log" 2>&1
"@
New-Item -ItemType Directory -Force -Path (Split-Path $launcher) | Out-Null
Set-Content -Path $launcher -Value $body -Encoding ASCII
Write-Host "  wrote $launcher"
Write-Host "  python: $python"

Write-Host "5. scheduled task"
# NOT registered here, on purpose. This block used to call
#
#     New-ScheduledTaskPrincipal ... | Register-ScheduledTask -Principal ... -User ... -Password ...
#
# which are MUTUALLY EXCLUSIVE parameter sets. Windows refuses the whole call
# with "Parameter set cannot be resolved using the specified named parameters"
# (FullyQualifiedErrorId AmbiguousParameterSet), and because $ErrorActionPreference
# is Stop the script died there - after creating the account and rewriting ACLs,
# leaving the job half done and looking like a failure.
#
# The param set was not the real problem though. Registering with -LogonType
# Password needs SeBatchLogonRight, which an ordinary account does NOT have - the
# documented cause of a task that registers fine and then never starts
# (LastTaskResult 0x41303). Registration done here would silently repeat that bug.
#
# register-task.ps1 exists for exactly this: it grants the batch right, proves the
# credential with a real BATCH logon, refuses to register on an unverified one,
# adds the 5-minute watchdog, starts her, and writes logs\task-check.txt. Two
# places doing this is how they drift apart - so this script stops before it.
Write-Host "  not registered here - register-task.ps1 owns that, and it must run second"
Write-Host ""
Write-Host "Done with what this script does. Next, in this SAME elevated shell:"
Write-Host ""
Write-Host "    .\register-task.ps1"
Write-Host ""
Write-Host "  It will ask for the $Account password again (it has to prove the batch"
Write-Host "  logon, and a task with an unverified credential registers fine and then"
Write-Host "  never runs). If the batch right cannot be granted, fall back to:"
Write-Host ""
Write-Host "    .\register-task.ps1 -SkipCredential"
Write-Host ""
Write-Host "Watch her with:  Get-Content '$BotRoot\logs\bot.log' -Wait"
