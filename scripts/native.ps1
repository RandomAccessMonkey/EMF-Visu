# Run EMF-Visu natively on Windows, without Docker.
#
#   powershell -ExecutionPolicy Bypass -File scripts\native.ps1 start
#   powershell -ExecutionPolicy Bypass -File scripts\native.ps1 stop
#   powershell -ExecutionPolicy Bypass -File scripts\native.ps1 status
#
# This wrapper only makes sure the project's Python environment exists (uv sync) and then runs
# scripts\native.py, which does the actual work. See docs/native-windows.md.

param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status')]
    [string]$Command = 'start'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host 'ERROR: uv was not found.' -ForegroundColor Red
    Write-Host '  Install it (see docs/native-windows.md, step 1):  winget install --id=astral-sh.uv -e'
    Write-Host '  then open a NEW PowerShell window and run this command again.'
    exit 1
}

$python = Join-Path $root '.venv\Scripts\python.exe'
if ($Command -eq 'start' -or -not (Test-Path $python)) {
    # Fast when nothing changed; installs Python 3.12 and the packages on the first run.
    & uv sync --frozen --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'ERROR: "uv sync" failed (see the messages above).' -ForegroundColor Red
        exit 1
    }
}

& $python (Join-Path $root 'scripts\native.py') $Command
exit $LASTEXITCODE
