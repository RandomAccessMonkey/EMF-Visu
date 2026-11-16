# Stop the EMF-Visu local preview (Windows). Saved projects are kept.
#   powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
# Equivalent plain command: docker compose down
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Write-Host 'Docker is not installed; nothing to stop.'; exit 0 }
docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Host 'Docker is not running; the application is already stopped.'; exit 0 }
docker compose down
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host ''
Write-Host "EMF-Visu stopped. Saved projects are kept in the Docker volume 'emf-visu_pgdata'."
Write-Host 'Start again with: powershell -ExecutionPolicy Bypass -File scripts\start.ps1'
