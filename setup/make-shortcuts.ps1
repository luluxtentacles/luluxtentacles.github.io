# Rebuild the shortcuts for Lulu, retiring the ones that pointed at Nana's
# Discord face (which is retired and now an archive).
#
# Run as the desktop's owner - no elevation needed. It writes his own Desktop
# and his own Startup folder, and nothing else.
#
# Lives in setup\ rather than .setup-tools\ on purpose: .setup-tools\ is
# GITIGNORED, so a script that lives there has no history and no net under it.
# Its siblings here (register-task.ps1, create-bot-account.ps1, finish-setup.ps1,
# restart-lulu.cmd, run-bot.cmd) are all tracked. Rebuilding shortcuts is ongoing
# capability - the Desktop and the Startup folder both get reset eventually - not
# one-time migration, so this belongs with the rest.
#
# Why a script and not a one-liner: the shortcuts are a set, their targets and
# icons are easy to get subtly wrong, and it is re-runnable if either folder is
# ever reset.

$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject WScript.Shell
$desk = [Environment]::GetFolderPath('Desktop')
# The per-USER Startup folder: what runs when Kei logs on.
$startup = [Environment]::GetFolderPath('Startup')

# Place / Name / Target / Work / Icon / Desc / Window
#
# Window is the shortcut's own WindowStyle: 1 = normal, 3 = maximized,
# 7 = MINIMIZED. The console appears in both places on purpose - one he opens,
# one already open when he sits down - and they differ in exactly this: the one
# he asks for opens normally and takes focus, the one that opens ITSELF at logon
# comes up minimised so it never steals focus from whatever he is doing at
# logon. Both point at the same watch-console.cmd, so there is no second target
# to keep in sync.
#
# The Startup folder - not a scheduled task - is the honest home for the console.
# It needs a DESKTOP to draw a window on, and it belongs to Kei, not to lulu-bot.
# A task would need elevation to register, would run in a session with no
# display, and "console" would then mean a process with nowhere to draw. Lulu
# herself still starts at BOOT via LuluDiscordBot, which is a different thing
# entirely and is not touched by this script.
$new = @(
    @{
        Place  = 'Desktop'
        Name   = 'Lulu Console.lnk'
        Target = 'C:\lulu\setup\watch-console.cmd'
        Work   = 'C:\lulu\setup'
        Icon   = '%SystemRoot%\System32\shell32.dll,137'
        Desc   = "Watch Lulu's Discord bot console live"
        Window = 1
    },
    @{
        Place  = 'Desktop'
        Name   = 'Restart Lulu.lnk'
        Target = 'C:\lulu\setup\restart-lulu.cmd'
        Work   = 'C:\lulu\setup'
        Icon   = '%SystemRoot%\System32\shell32.dll,25'
        Desc   = 'Restart Lulu (asks for admin - she runs as the boxed lulu-bot account)'
        Window = 1
    },
    # The panic button. Master asked for it so a runaway, a bad loop, or anything
    # else on fire can be ended in one click without reasoning about process
    # trees mid-incident. Icon 131 is the red X: it should not look like the
    # restart button next to it.
    @{
        Place  = 'Desktop'
        Name   = 'Kill Lulu.lnk'
        Target = 'C:\lulu\setup\kill-lulu.cmd'
        Work   = 'C:\lulu\setup'
        Icon   = '%SystemRoot%\System32\shell32.dll,131'
        Desc   = 'STOP Lulu now - task, supervisor and bot (asks for admin). Right-click, Run as administrator if the prompt is refused.'
        Window = 1
    },
    @{
        Place  = 'Startup'
        Name   = 'Lulu Console.lnk'
        Target = 'C:\lulu\setup\watch-console.cmd'
        Work   = 'C:\lulu\setup'
        Icon   = '%SystemRoot%\System32\shell32.dll,137'
        Desc   = "Watch Lulu's Discord bot console live - opens minimised at logon"
        Window = 7
    }
)

foreach ($s in $new) {
    if (-not (Test-Path $s.Target)) {
        throw "target does not exist, refusing to make a dead shortcut: $($s.Target)"
    }
    $dir = if ($s.Place -eq 'Startup') { $startup } else { $desk }
    $path = Join-Path $dir $s.Name
    $lnk = $w.CreateShortcut($path)
    $lnk.TargetPath       = $s.Target
    $lnk.WorkingDirectory = $s.Work
    $lnk.IconLocation     = $s.Icon
    $lnk.Description      = $s.Desc
    $lnk.WindowStyle      = $s.Window
    $lnk.Save()
    Write-Host ("created : {0,-7} {1}  ->  {2}  (window {3})" -f $s.Place, $s.Name, $s.Target, $s.Window)
}

# Only remove the old ones AFTER the new ones exist and point at real files.
# Both folders are swept: a stale Nana console left in Startup would tail the
# same log with a second watcher, and two of them is not twice as useful.
$old = @('Nana Console.lnk', 'Restart Nana.lnk')
foreach ($name in $old) {
    $found = $false
    foreach ($dir in @($desk, $startup)) {
        $path = Join-Path $dir $name
        if (Test-Path $path) {
            Remove-Item $path -Force
            Write-Host "removed : $name  (from $dir)"
            $found = $true
        }
    }
    if (-not $found) { Write-Host "absent  : $name (nothing to remove)" }
}

# Read every shortcut BACK and report what is actually on disk. CreateShortcut
# happily writes a broken .lnk and reports success, so creating is not evidence.
Write-Host ''
Write-Host '--- read back ---'
$bad = 0
foreach ($s in $new) {
    $dir = if ($s.Place -eq 'Startup') { $startup } else { $desk }
    $path = Join-Path $dir $s.Name
    if (-not (Test-Path $path)) {
        Write-Host ("  MISSING  {0,-7} {1}" -f $s.Place, $s.Name)
        $bad++
        continue
    }
    $rb = $w.CreateShortcut($path)
    $ok = Test-Path $rb.TargetPath
    if (-not $ok) { $bad++ }
    Write-Host ("  {0} {1,-7} {2}" -f $(if ($ok) { 'ok     ' } else { 'DANGLING' }), $s.Place, $s.Name)
    Write-Host ("           -> {0}  (window {1})" -f $rb.TargetPath, $rb.WindowStyle)
}
Write-Host ''
Write-Host 'Nyan Console.lnk / Restart Nyan.lnk left alone - NyanBot is a separate bot.'
Write-Host 'Lulu starts at BOOT (LuluDiscordBot task); the console opens at LOGON.'
if ($bad -gt 0) { exit 1 }
