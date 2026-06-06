$ErrorActionPreference = "Stop"

$BotDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $BotDir
$PidDir = Join-Path $ProjectRoot "data\logs\scheduler_pids"

foreach ($name in @("celery_worker", "celery_beat")) {
    $pidPath = Join-Path $PidDir "$name.pid"
    if (-not (Test-Path $pidPath)) {
        Write-Host "No PID file for $name"
        continue
    }

    $processId = [int](Get-Content $pidPath -Raw)
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $processId -Force
        Write-Host "Stopped $name PID $processId"
    }
    else {
        Write-Host "$name PID $processId is not running"
    }
    Remove-Item $pidPath -Force
}

Write-Host "Redis is still running. Stop it with: docker compose stop redis"
