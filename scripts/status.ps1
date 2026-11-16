# Show the state of the EMF-Visu local preview (Windows).
#   powershell -ExecutionPolicy Bypass -File scripts\status.ps1
Set-Location (Split-Path -Parent $PSScriptRoot)
$port = $env:FRONTEND_PORT
if (-not $port -and (Test-Path '.env')) {
    $line = Get-Content '.env' | Where-Object { $_ -match '^FRONTEND_PORT=' } | Select-Object -Last 1
    if ($line) { $port = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'") }
}
if (-not $port) { $port = '8080' }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Host 'Docker is not running.'; exit 1 }
Write-Host 'Containers (STATUS shows the health check result):'
docker compose ps -a
Write-Host ''
Write-Host "Application health (http://localhost:$port/api/v1/health):"
try { Invoke-RestMethod -Uri "http://localhost:$port/api/v1/health" -TimeoutSec 5 | ConvertTo-Json -Depth 4 }
catch { Write-Host '  not reachable' }
Write-Host ''
Write-Host 'Logs of one service:  docker compose logs --tail 50 api'
Write-Host '                      (or frontend, worker-analytical, postgres, redis)'
