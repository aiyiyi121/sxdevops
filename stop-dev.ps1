$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$logDir = Join-Path $root '.runlogs'
$backendPidFile = Join-Path $logDir 'backend.pid'
$frontendPidFile = Join-Path $logDir 'frontend.pid'

function Get-PortProcess {
    param([int]$Port)

    $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if (!$connection) {
        return $null
    }

    return Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
}

function Stop-PortProcess {
    param(
        [int]$Port,
        [string]$Name,
        [string[]]$AllowedNames
    )

    $process = Get-PortProcess -Port $Port
    if (!$process) {
        return
    }

    if ($AllowedNames -contains $process.ProcessName) {
        Stop-Process -Id $process.Id -Force
        Write-Host "$Name stopped by port $Port (PID: $($process.Id))"
    }
}

function Stop-TrackedProcess {
    param(
        [string]$PidFile,
        [string]$Name
    )

    if (!(Test-Path $PidFile)) {
        Write-Host "$Name is not tracked."
        return
    }

    $pidText = (Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $targetPid = 0
    if (![int]::TryParse($pidText, [ref]$targetPid)) {
        Remove-Item $PidFile -ErrorAction SilentlyContinue
        Write-Host "$Name pid file was invalid and has been removed."
        return
    }

    $process = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $targetPid -Force
        Write-Host "$Name stopped (PID: $targetPid)"
    } else {
        Write-Host "$Name process not found, removing stale pid file."
    }

    Remove-Item $PidFile -ErrorAction SilentlyContinue
}

Stop-TrackedProcess -PidFile $frontendPidFile -Name 'Frontend'
Stop-TrackedProcess -PidFile $backendPidFile -Name 'Backend'
Stop-PortProcess -Port 3000 -Name 'Frontend' -AllowedNames @('node')
Stop-PortProcess -Port 8000 -Name 'Backend' -AllowedNames @('python', 'python3')
