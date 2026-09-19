# Non-blocking tail of a log file. Safe to leave running.
#
#   powershell -File tail-file.ps1 -Path "C:\some\log.txt" [-Tail 40]
#
# WHY THIS EXISTS
# ---------------
# `Get-Content -Wait` keeps the file open in a way that stops other processes
# writing to it. A watcher built that way locks out the very process it is
# watching: the bot cannot append its own log and dies. This opens with
# FileShare.ReadWrite and RELEASES the handle between polls, so watching can
# never interfere with the writer.

param(
    [Parameter(Mandatory = $true)][string]$Path,
    [int]$Tail = 40,
    [int]$PollMs = 800
)

function Read-Shared([string]$p, [long]$from) {
    $fs = [System.IO.File]::Open($p,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite)
    try {
        [void]$fs.Seek($from, [System.IO.SeekOrigin]::Begin)
        $buf = New-Object System.IO.MemoryStream
        $fs.CopyTo($buf)
        return @{
            Text = [System.Text.Encoding]::UTF8.GetString($buf.ToArray())
            End  = $fs.Length
        }
    } finally {
        $fs.Dispose()
    }
}

if (-not (Test-Path $Path)) {
    Write-Host "no log at $Path yet."
    exit 1
}

Write-Host "Watching $Path"
Write-Host "Closing this window only stops the watching."
Write-Host ""

$first = Read-Shared $Path 0
($first.Text -split "`r?`n" | Select-Object -Last $Tail) | ForEach-Object { Write-Host $_ }
$pos = $first.End

while ($true) {
    Start-Sleep -Milliseconds $PollMs
    try {
        $r = Read-Shared $Path $pos
        if ($r.Text) { Write-Host -NoNewline $r.Text; $pos = $r.End }
    } catch {
        # A momentary failure must not kill the watcher.
    }
}
