<#
Registers LuluDiscordBot, repairs the two things that stop a task from running,
and starts it.

What went wrong before, recorded so it is not repeated:

  1. A stored-password task logs on as a BATCH job. The default Windows user
     rights do not include SeBatchLogonRight for ordinary accounts, so the
     task sat at Ready and never started - LastTaskResult 0x41303, which means
     "has not run", not "crashed".
  2. An earlier check here accepted an INTERACTIVE logon as good enough. It is
     not: the task needs the batch logon specifically. That bug registered a
     task that could never run.

So this script now:
  - grants SeBatchLogonRight to the account, checking first and only changing
    policy when the right is genuinely missing
  - proves the credential with a real BATCH logon before registering anything
  - refuses to register on an unverified credential

MUST RUN ELEVATED.

  Elevated PowerShell:
    .\register-task.ps1                 # grant right, verify, register, start
    .\register-task.ps1 -SkipCredential # S4U: no password stored at all
    .\register-task.ps1 -Undo           # remove the task

  If the batch test still fails after the grant, run 'gpupdate /force' or
  reboot: user-rights changes are read by LSASS on its own schedule.
#>
[CmdletBinding()]
param(
    [string]$Account = "lulu-bot",
    [string]$BotRoot = "C:\Lulu",
    [string]$TaskName = "LuluDiscordBot",
    [string]$PythonRoot = "C:\Lulu\Python311",
    [int]$WatchdogMinutes = 5,
    [switch]$SkipCredential,
    [switch]$Undo
)

$ErrorActionPreference = "Stop"

function Assert-Elevated {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this elevated: right-click PowerShell -> Run as administrator."
    }
}

# Single report, single encoding. The earlier mixed Set-Content/Add-Content
# produced a file that decoded as garbage.
$Report = @()
function Say($line) {
    $script:Report += [string]$line
    Write-Host $line
}
function Save-Report {
    $path = Join-Path (Join-Path $BotRoot "logs") "task-check.txt"
    New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null
    Set-Content -Path $path -Value $script:Report -Encoding ASCII
    Write-Host "report: $path"
}

Add-Type -Namespace LuluSetup -Name LogonProbe -MemberDefinition @'
[DllImport("advapi32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
public static extern bool LogonUser(string user, string domain, string password,
                                    int logonType, int provider, out IntPtr token);
[DllImport("kernel32.dll", SetLastError=true)]
public static extern bool CloseHandle(IntPtr handle);
'@

function Test-Logon([string]$user, [string]$password, [int]$type, [string]$label) {
    $token = [IntPtr]::Zero
    # LogonUser with type 4 is a batch logon: the same kind a stored-password
    # scheduled task performs. If this works, the task can start.
    $ok = [LuluSetup.LogonProbe]::LogonUser($user, $env:COMPUTERNAME, $password, $type, 0, [ref]$token)
    if ($ok) {
        [LuluSetup.LogonProbe]::CloseHandle($token) | Out-Null
        Say ("   {0,-22} OK" -f $label)
        return 0
    }
    $code = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
    $msg = switch ($code) {
        1326 { "wrong password" }
        1385 { "account lacks this logon right" }
        1907 { "password must be changed at next logon" }
        1331 { "account is disabled" }
        default { "win32 error $code" }
    }
    Say ("   {0,-22} FAILED: {1}" -f $label, $msg)
    return $code
}

function Get-AccountSid([string]$name) {
    (New-Object System.Security.Principal.NTAccount($name)).Translate(
        [System.Security.Principal.SecurityIdentifier]).Value
}

function Get-BatchRight([string]$sid) {
    # Returns $true / $false / $null when the policy cannot be read.
    $inf = Join-Path $env:TEMP ("lulu_pol_{0}.inf" -f $PID)
    secedit /export /cfg $inf /areas USER_RIGHTS | Out-Null
    if (-not (Test-Path $inf)) { return $null }
    $line = (Select-String -Path $inf -Pattern '^SeBatchLogonRight' -ErrorAction SilentlyContinue |
             Select-Object -First 1).Line
    Remove-Item $inf -ErrorAction SilentlyContinue
    if (-not $line) { return $false }
    return [bool]($line -match [regex]::Escape($sid))
}

function Grant-BatchRight([string]$sid) {
    $inf = Join-Path $env:TEMP ("lulu_pol_{0}.inf" -f $PID)
    $db = Join-Path $env:TEMP ("lulu_pol_{0}.sdb" -f $PID)
    secedit /export /cfg $inf /areas USER_RIGHTS | Out-Null
    $lines = New-Object System.Collections.ArrayList
    Get-Content $inf | ForEach-Object { [void]$lines.Add($_) }

    $placed = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^SeBatchLogonRight') {
            if ($lines[$i] -notmatch [regex]::Escape($sid)) {
                $lines[$i] = $lines[$i].TrimEnd() + ",*$sid"
            }
            $placed = $true
            break
        }
    }
    if (-not $placed) {
        # Append under the section header if the line is absent entirely.
        $header = -1
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i].Trim() -eq '[Privilege Rights]') { $header = $i; break }
        }
        if ($header -ge 0) { $lines.Insert($header + 1, "SeBatchLogonRight = *$sid") }
        else { [void]$lines.Add("SeBatchLogonRight = *$sid") }
    }

    # The INF must stay UTF-16 with a BOM or secedit rejects it.
    Set-Content -Path $inf -Value $lines -Encoding Unicode
    secedit /configure /db $db /cfg $inf /areas USER_RIGHTS | Out-Null
    Remove-Item $inf, $db -ErrorAction SilentlyContinue
}

Assert-Elevated

Say "=== register-task $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
Say "elevated as : $([Security.Principal.WindowsIdentity]::GetCurrent().Name)"

try {

if ($Undo) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Say "removed task: $TaskName"
    Save-Report
    return
}

if (-not (Get-LocalUser -Name $Account -ErrorAction SilentlyContinue)) {
    throw "no account named $Account - run create-bot-account.ps1 first"
}

$launcher = Join-Path $BotRoot "setup\run-bot.cmd"
if (-not (Test-Path $launcher)) { throw "no launcher at $launcher" }
if (-not (Test-Path (Join-Path $PythonRoot "python.exe"))) {
    throw "no python at $PythonRoot"
}

# --- permissions --------------------------------------------------------
Say ""
Say "1. file permissions"
$profileDir = $env:USERPROFILE
if ($PythonRoot -like "$profileDir*") {
    icacls $profileDir /grant:r "${Account}:(CI)(X)" | Out-Null
    Say "   X on $profileDir (traverse, containers only)"
}
$Ledger = "C:\Python\DiscordBotN5\memory\facts.json"
if (Test-Path $Ledger) {
    icacls $Ledger /grant:r "${Account}:R" | Out-Null
    Say "   R on Nyan's ledger"
}

# --- batch logon right --------------------------------------------------
Say ""
Say "2. batch logon right"
$sid = Get-AccountSid $Account
Say "   sid: $sid"
$has = Get-BatchRight $sid
if ($has -eq $true) {
    Say "   SeBatchLogonRight already granted"
} elseif ($has -eq $false) {
    Say "   SeBatchLogonRight MISSING - this is what stopped the task running"
    Say "   granting it now"
    Grant-BatchRight $sid
    $after = Get-BatchRight $sid
    Say "   after grant: $(if ($after) { 'granted' } else { 'STILL MISSING - investigate' })"
} else {
    Say "   could not read policy; skipping"
}

# --- credential ---------------------------------------------------------
Say ""
Say "3. credential"
$credentialOk = $false
$Password = $null

if ($SkipCredential) {
    Say "   -SkipCredential: S4U, no password stored"
    $credentialOk = $true
} else {
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $secure = Read-Host -Prompt "   Password for $Account (attempt $attempt of 3)" -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $Password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
        if (-not $Password) { Say "   nothing entered"; continue }

        # Batch only. An interactive logon proves the password but says nothing
        # about whether the task can start - that was the earlier mistake.
        $batch = Test-Logon $Account $Password 4 "BATCH"

        if ($batch -eq 0) { $credentialOk = $true; break }
        if ($batch -eq 1326) { Say "   -> wrong password, try again"; continue }
        if ($batch -eq 1385) {
            Say "   -> still lacks the batch right; 'gpupdate /force' or reboot, then retry"
            break
        }
        break
    }
}

# --- register -----------------------------------------------------------
Say ""
Say "4. register"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "cmd.exe" `
    -Argument "/c `"$launcher`"" -WorkingDirectory $BotRoot

$trigger = New-ScheduledTaskTrigger -AtStartup
try {
    $trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes $WatchdogMinutes)).Repetition
    Say "   trigger: at startup + every ${WatchdogMinutes}m"
} catch {
    Say "   WARNING: no watchdog, repetition failed: $($_.Exception.Message)"
}

$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable

if ($SkipCredential) {
    $principal = New-ScheduledTaskPrincipal -UserId $Account -LogonType S4U -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -ErrorAction Stop | Out-Null
} else {
    if (-not $credentialOk) {
        Say "   REFUSING to register with an unverified credential."
        Say "   A task with a bad credential registers fine and then never runs."
        Save-Report
        return
    }
    # -User/-Password and -Principal are mutually exclusive parameter sets;
    # the -User set carries -RunLevel, so Limited still applies.
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Settings $settings -User $Account -Password $Password -RunLevel Limited `
        -ErrorAction Stop | Out-Null
}
Say "   registered $TaskName"

# --- verify -------------------------------------------------------------
Say ""
Say "5. verify (elevated read)"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Say "   PROBLEM: registered but unreadable"
} else {
    Say "   state    : $($task.State)"
    Say "   runs as  : $($task.Principal.UserId)"
    Say "   runlevel : $($task.Principal.RunLevel)"
    Say "   logon    : $($task.Principal.LogonType)"
    Say "   multiple : $($task.Settings.MultipleInstances)"
    Say "   timelimit: [$($task.Settings.ExecutionTimeLimit)]"
    foreach ($tr in $task.Triggers) {
        Say "   trigger  : $($tr.CimClass.CimClassName) interval=[$($tr.Repetition.Interval)]"
    }
}

# --- start and watch ----------------------------------------------------
Say ""
Say "6. start and watch"
try {
    Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    Say "   start issued"
} catch {
    Say "   START FAILED: $($_.Exception.Message)"
}

$running = $false
foreach ($waited in 2,4,6,8,10,12) {
    Start-Sleep -Seconds 2
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    $proc = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*lulu_bot*' }
    Say ("   +{0,2}s result={1} running={2}" -f $waited, $info.LastTaskResult, [bool]$proc)
    if ($proc) { $running = $true; break }
}

Say ""
if ($running) {
    $proc | ForEach-Object {
        $owner = (Invoke-CimMethod -InputObject $_ -MethodName GetOwner -ErrorAction SilentlyContinue).User
        Say "   RUNNING pid=$($_.ProcessId) owner=$owner"
    }
} else {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
    Say "   NOT RUNNING after the watch window"
    Say "   lastRunTime    : $($info.LastRunTime)"
    Say "   lastTaskResult : $($info.LastTaskResult)"
    Say "   0x41303 = never started (logon still blocked)"
    Say "   0x41301 = running"
}

Say ""
Say "--- bot.log tail ---"
$botLog = Join-Path (Join-Path $BotRoot "logs") "bot.log"
if (Test-Path $botLog) { Get-Content $botLog -Tail 12 | ForEach-Object { Say "   $_" } }
else { Say "   no bot.log" }

}
catch {
    Say ""
    Say "FAILED: $($_.Exception.Message)"
    Say "type   : $($_.Exception.GetType().FullName)"
    if ($_.Exception.InnerException) { Say "inner  : $($_.Exception.InnerException.Message)" }
    Say "errorid: $($_.FullyQualifiedErrorId)"
}
finally {
    Save-Report
}
