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
    [string]$TokenFile = "C:\Lulu_token.txt",
    [string]$SharedMemory = "C:\Lulu\memory",
    # Python is installed per-user under your profile, which the new account
    # cannot read. Grant read+execute on the install folder only - ACLs are
    # per-object, so this does not expose the rest of your profile.
    [string]$PythonRoot = "",
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
Grant $SharedMemory "R"                               # read our memory, never write it
if ($PythonRoot) { Grant $PythonRoot "RX" }           # run python

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
"$python" lulu_bot.py >> "logs\bot.log" 2>&1
"@
New-Item -ItemType Directory -Force -Path (Split-Path $launcher) | Out-Null
Set-Content -Path $launcher -Value $body -Encoding ASCII
Write-Host "  wrote $launcher"
Write-Host "  python: $python"

Write-Host "5. scheduled task"
Unregister-ScheduledTask -TaskName "LuluDiscordBot" -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"$launcher`"" -WorkingDirectory $BotRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId $Account -LogonType Password -RunLevel Limited
Register-ScheduledTask -TaskName "LuluDiscordBot" -Action $action -Trigger $trigger `
    -Principal $principal -User $Account -Password $Password | Out-Null
Write-Host "  registered LuluDiscordBot (runs as $Account at startup)"
Write-Host ""
Write-Host "Done. Start it now with:  Start-ScheduledTask -TaskName LuluDiscordBot"
Write-Host "Watch it with:            Get-Content '$BotRoot\logs\bot.log' -Wait"
