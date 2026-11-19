<#
.SYNOPSIS
    Build (if needed) and start the FinAlly container.

.PARAMETER Build
    Rebuild the image before starting.

.EXAMPLE
    .\scripts\start_windows.ps1
    .\scripts\start_windows.ps1 -Build
#>
param(
    [switch]$Build
)

$ErrorActionPreference = "Stop"
# Native tools report failure through $LASTEXITCODE; do not turn stderr into a
# terminating error when probing Docker (PowerShell 7.3+ setting, ignored by 5.1).
$PSNativeCommandUseErrorActionPreference = $false

$ImageName = "finally:latest"
$ContainerName = "finally"
$VolumeName = "finally-data"
$HostPort = if ($env:FINALLY_PORT) { $env:FINALLY_PORT } else { "8000" }
$Url = "http://localhost:$HostPort"

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

function Test-DockerDaemon {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & docker info *> $null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $previous
    return $ok
}

function Test-ImageExists {
    param([string]$Name)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & docker image inspect $Name *> $null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $previous
    return $ok
}

function Test-ContainerExists {
    param([string]$Name)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & docker container inspect $Name *> $null
    $ok = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $previous
    return $ok
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker was not found on PATH."
    Write-Host "Install Docker Desktop (https://www.docker.com/products/docker-desktop/) and try again."
    exit 1
}

if (-not (Test-DockerDaemon)) {
    Write-Host "Docker is installed but the daemon is not responding."
    Write-Host "Start Docker Desktop (or the Docker service) and try again."
    exit 1
}

$EnvFile = Join-Path $RootDir ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "No .env found - creating one from .env.example."
    Copy-Item (Join-Path $RootDir ".env.example") $EnvFile
    Write-Host "Edit .env to set OPENROUTER_API_KEY (or LLM_MOCK=true for offline use)."
}

if ($Build -or -not (Test-ImageExists $ImageName)) {
    Write-Host "Building $ImageName ..."
    & docker build -t $ImageName .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "docker build failed."
        exit 1
    }
}

# Recreate the container so new flags/env take effect. The data volume is untouched.
if (Test-ContainerExists $ContainerName) {
    Write-Host "Removing existing container $ContainerName ..."
    & docker rm -f $ContainerName | Out-Null
}

Write-Host "Starting $ContainerName ..."
& docker run -d `
    --name $ContainerName `
    -v "${VolumeName}:/app/data" `
    -p "${HostPort}:8000" `
    --env-file $EnvFile `
    --restart unless-stopped `
    $ImageName | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Host "docker run failed."
    exit 1
}

Write-Host "FinAlly is running at $Url"
Write-Host "Logs:   docker logs -f $ContainerName"
Write-Host "Stop:   .\scripts\stop_windows.ps1"

try {
    Start-Process $Url
} catch {
    Write-Host "Open $Url in your browser."
}
