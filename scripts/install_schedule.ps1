# Huoke Radar - register a daily Windows scheduled task
# ------------------------------------------------------
# NOTE: intentionally written in pure ASCII (English) to avoid the classic
# Windows PowerShell 5.1 UTF-8 -> ANSI mojibake issue with CJK characters.
#
# Usage (run as the normal user, Administrator NOT required for per-user task):
#   powershell -ExecutionPolicy Bypass -File install_schedule.ps1
#   powershell -ExecutionPolicy Bypass -File install_schedule.ps1 -Time 08:45 -Push
#   powershell -ExecutionPolicy Bypass -File install_schedule.ps1 -Remove
#
# Default behaviour: collect at 09:30 every day, save CSV locally, DO NOT push
# to the cloud (an Open Platform token only lives 30 minutes, so a scheduled
# task cannot hold a valid one). Use the WorkBuddy automation if you want the
# daily run to also write into the database.

param(
    [string]$Time = "09:30",
    [string]$TaskName = "HuokeRadarDaily",
    [string]$PythonPath = "",
    [switch]$Push,
    [switch]$Remove
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($Remove) {
    schtasks /Delete /TN $TaskName /F 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Host "[OK] Task removed: $TaskName" }
    else { Write-Host "[--] Task not found: $TaskName" }
    exit 0
}

# --- locate python ---
if (-not $PythonPath) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $PythonPath = $cmd.Source }
}
if (-not $PythonPath -or -not (Test-Path $PythonPath)) {
    Write-Host "[X] python not found. Pass it explicitly: -PythonPath 'C:\Path\python.exe'"
    exit 1
}

$script = Join-Path $here "daily_run.py"
if (-not (Test-Path $script)) {
    Write-Host "[X] daily_run.py not found next to this script."
    exit 1
}

# --- verify playwright is importable ---
& $PythonPath -c "import playwright" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[!] playwright is NOT installed for: $PythonPath"
    Write-Host "    Run:  `"$PythonPath`" -m pip install playwright"
    Write-Host "    Then rerun this script."
    exit 1
}

# --- build the command line ---
$argLine = "`"$script`" --headless"
if (-not $Push) { $argLine = $argLine + " --no-push" }
$tr = "`"$PythonPath`" $argLine"

Write-Host "Task name : $TaskName"
Write-Host "Schedule  : every day at $Time"
Write-Host "Command   : $tr"

schtasks /Create /TN $TaskName /TR $tr /SC DAILY /ST $Time /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Failed to create the task. Try running this in an elevated PowerShell."
    exit 1
}

Write-Host ""
Write-Host "[OK] Daily task created."
Write-Host "     Check   : schtasks /Query /TN $TaskName"
Write-Host "     Run now : schtasks /Run /TN $TaskName"
Write-Host "     Remove  : powershell -ExecutionPolicy Bypass -File install_schedule.ps1 -Remove"
Write-Host ""
Write-Host "Logs: $here\logs\daily_YYYYMMDD.log"
Write-Host "CSV : $here\data\"
if (-not $Push) {
    Write-Host ""
    Write-Host "Note: --no-push mode only saves CSV locally. To also write into the"
    Write-Host "      online database every day, use a WorkBuddy automation instead"
    Write-Host "      (it can fetch a fresh token on each run)."
}
