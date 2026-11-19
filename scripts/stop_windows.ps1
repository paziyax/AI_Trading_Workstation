<#
.SYNOPSIS
    Stop and remove the FinAlly container. The data volume is never removed.

.EXAMPLE
    .\scripts\stop_windows.ps1
#>
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$ContainerName = "finally"
$VolumeName = "finally-data"

function Test-DockerDaemon {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    & docker info *> $null
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
    Write-Host "Docker was not found on PATH; nothing to stop."
    exit 0
}

if (-not (Test-DockerDaemon)) {
    Write-Host "Docker is installed but the daemon is not responding; nothing to stop."
    exit 0
}

if (Test-ContainerExists $ContainerName) {
    Write-Host "Stopping $ContainerName ..."
    & docker stop $ContainerName | Out-Null
    & docker rm $ContainerName | Out-Null
    Write-Host "FinAlly stopped."
} else {
    Write-Host "FinAlly is not running (no container named $ContainerName)."
}

Write-Host "Data volume '$VolumeName' was kept."
Write-Host "To delete all portfolio data: docker volume rm $VolumeName"
