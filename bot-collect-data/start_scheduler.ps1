param(
    [string[]]$Tickers = @("HPG", "FPT", "VCB"),
    [switch]$IncludeNews,
    [switch]$IncludeCharts,
    [int]$MaxReports = 5,
    [double]$DelaySeconds = 1.5,
    [int]$TimeoutSeconds = 30,
    [switch]$SkipInitialCrawl
)

$ErrorActionPreference = "Stop"

$BotDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $BotDir
$CeleryExe = Join-Path $ProjectRoot ".venv\Scripts\celery.exe"
$LogDir = Join-Path $ProjectRoot "data\logs\scheduler_logs"
$PidDir = Join-Path $ProjectRoot "data\logs\scheduler_pids"

if (-not (Test-Path $CeleryExe)) {
    throw "Missing celery executable at $CeleryExe. Activate .venv and run: pip install -r requirements.txt"
}

New-Item -ItemType Directory -Force -Path $LogDir, $PidDir | Out-Null

Push-Location $ProjectRoot
try {
    docker compose up -d redis qdrant | Out-Host
}
finally {
    Pop-Location
}

if (-not $env:REDIS_URL) {
    $env:REDIS_URL = "redis://localhost:6379/0"
}
if (-not $env:CELERY_BROKER_URL) {
    $env:CELERY_BROKER_URL = $env:REDIS_URL
}
if (-not $env:CELERY_RESULT_BACKEND) {
    $env:CELERY_RESULT_BACKEND = $env:REDIS_URL
}

$workerOut = Join-Path $LogDir "celery_worker.out.log"
$workerErr = Join-Path $LogDir "celery_worker.err.log"
$beatOut = Join-Path $LogDir "celery_beat.out.log"
$beatErr = Join-Path $LogDir "celery_beat.err.log"

$worker = Start-Process `
    -FilePath $CeleryExe `
    -ArgumentList @("-A", "celery_app", "worker", "--loglevel=info", "--pool=solo", "--concurrency=1") `
    -WorkingDirectory $BotDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $workerOut `
    -RedirectStandardError $workerErr `
    -PassThru

$beat = Start-Process `
    -FilePath $CeleryExe `
    -ArgumentList @("-A", "celery_app", "beat", "--loglevel=info") `
    -WorkingDirectory $BotDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $beatOut `
    -RedirectStandardError $beatErr `
    -PassThru

$worker.Id | Set-Content -Encoding ascii (Join-Path $PidDir "celery_worker.pid")
$beat.Id | Set-Content -Encoding ascii (Join-Path $PidDir "celery_beat.pid")

if (-not $SkipInitialCrawl) {
    $argsJson = ConvertTo-Json -Compress @(
        $Tickers,
        [bool]$IncludeNews,
        [bool]$IncludeCharts,
        $MaxReports,
        $DelaySeconds,
        $TimeoutSeconds
    )

    Push-Location $BotDir
    try {
        & $CeleryExe -A celery_app call tasks.crawl_tickers_and_index --args="$argsJson" | Out-Host
    }
    finally {
        Pop-Location
    }
}

Write-Host "Celery worker PID: $($worker.Id)"
Write-Host "Celery beat PID: $($beat.Id)"
Write-Host "Logs: $LogDir"
if ($SkipInitialCrawl) {
    Write-Host "Initial crawl skipped."
}
else {
    Write-Host "Initial crawl+index queued for tickers: $($Tickers -join ', ')"
}
