# Start the EMF-Visu local preview (Windows PowerShell 5.1 or PowerShell 7).
#
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -NoBuild
#
# Equivalent plain command: docker compose up -d --build
param([switch]$NoBuild)
$ErrorActionPreference = 'Continue'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Fail([string]$Message, [string[]]$Hints) {
    Write-Host ''
    Write-Host "ERROR: $Message" -ForegroundColor Red
    foreach ($h in $Hints) { Write-Host "  $h" }
    exit 1
}

# Port settings as docker compose resolves them: environment first, then .env, then default.
function Get-Setting([string]$Name, [string]$Default) {
    $value = [Environment]::GetEnvironmentVariable($Name)
    if (-not $value -and (Test-Path '.env')) {
        $line = Get-Content '.env' | Where-Object { $_ -match "^$Name=" } | Select-Object -Last 1
        if ($line) { $value = ($line -split '=', 2)[1].Trim().Trim('"').Trim("'") }
    }
    if ($value) { return $value }
    return $Default
}
$frontendPort = [int](Get-Setting 'FRONTEND_PORT' '8080')
$apiPort = [int](Get-Setting 'API_PORT' '8000')
$url = "http://localhost:$frontendPort"

# 1. Docker present, running, with Compose v2.
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail 'Docker is not installed.' @('Install Docker Desktop for Windows (WSL 2 backend):',
        'https://docs.docker.com/desktop/setup/install/windows-install/')
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Fail 'Docker Desktop is installed but not running.' @(
        'Start Docker Desktop from the Start menu, wait until it shows "Engine running",',
        'then run this script again.')
}
docker compose version *> $null
if ($LASTEXITCODE -ne 0) { Fail "'docker compose' is not available." @('Update Docker Desktop; it includes Compose v2.') }

# 2. Ports free (unless our own containers already hold them).
function Test-PortBusy([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $Port); return $true } catch { return $false } finally { $client.Dispose() }
}
function Test-OursRunning([string]$Service) {
    $id = docker compose ps -q --status running $Service 2>$null
    return [bool]$id
}
foreach ($p in @(@('frontend', $frontendPort, 'FRONTEND_PORT'), @('api', $apiPort, 'API_PORT'))) {
    if (-not (Test-OursRunning $p[0]) -and (Test-PortBusy $p[1])) {
        Fail "Port $($p[1]) is already in use by another program." @(
            'Stop that program, or create a file named .env next to docker-compose.yml containing',
            "  $($p[2])=$($p[1] + 1)",
            '(any free port) and run this script again.')
    }
}

function Get-Health([string]$Service) {
    $id = docker compose ps -a -q $Service 2>$null | Select-Object -First 1
    if (-not $id) { return 'missing' }
    return (docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $id 2>$null)
}

function Show-Diagnosis {
    Write-Host ''
    Write-Host 'Service status:'
    docker compose ps -a
    foreach ($svc in @('postgres', 'redis', 'api', 'worker-analytical', 'frontend')) {
        $state = Get-Health $svc
        if (@('healthy', 'starting', 'running') -notcontains $state) {
            Write-Host ''
            Write-Host "--- last 30 log lines of '$svc' ($state) ---"
            docker compose logs --tail 30 $svc
        }
    }
}

# 3. Build (first time) and start.
Write-Host 'Starting EMF-Visu. The first start builds the images, which can take 5-10 minutes.'
if ($NoBuild) { docker compose up -d } else { docker compose up -d --build }
if ($LASTEXITCODE -ne 0) {
    Show-Diagnosis
    Fail 'docker compose could not start the application (details above).' @(
        'Common causes: no internet access during the first build, Docker Hub rate limits,',
        'too little disk space. See docs\local-preview.md, section Troubleshooting.')
}

# 4. Wait until the API and the web frontend report healthy.
Write-Host 'Waiting for the services to become healthy...'
$deadline = (Get-Date).AddSeconds(240)
while ($true) {
    $api = Get-Health 'api'
    $frontend = Get-Health 'frontend'
    if ($api -eq 'healthy' -and $frontend -eq 'healthy') { break }
    if (@('unhealthy', 'exited') -contains $api -or @('unhealthy', 'exited') -contains $frontend -or (Get-Date) -gt $deadline) {
        Show-Diagnosis
        Fail "The application did not become healthy (api: $api, frontend: $frontend)." @(
            'See the log lines above and docs\local-preview.md, section Troubleshooting.')
    }
    Start-Sleep -Seconds 3
}

# 5. End-to-end check through the frontend, as the browser will use it.
try {
    $health = Invoke-RestMethod -Uri "$url/api/v1/health" -TimeoutSec 5
    if ($health.status -ne 'ok') { Write-Host "Warning: the API reports a degraded state: $($health | ConvertTo-Json -Compress)" -ForegroundColor Yellow }
} catch {
    Fail "The frontend is up, but $url/api/v1/health does not answer." @('Run scripts\status.ps1 and see docs\local-preview.md, section Troubleshooting.')
}

$worker = Get-Health 'worker-analytical'
Write-Host ''
Write-Host "EMF-Visu is running:  $url" -ForegroundColor Green
Write-Host "API documentation:    http://localhost:$apiPort/docs"
if ($worker -eq 'healthy') { Write-Host 'Solver worker:        healthy' }
elseif ($worker -eq 'starting') { Write-Host 'Solver worker:        starting (only needed for high-resolution solves)' }
else { Write-Host "Solver worker:        $worker - high-resolution solves will not run; see scripts\status.ps1" -ForegroundColor Yellow }
Write-Host 'Stop with:            powershell -ExecutionPolicy Bypass -File scripts\stop.ps1   (saved projects are kept)'
