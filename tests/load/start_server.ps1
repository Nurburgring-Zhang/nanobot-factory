# Start IMDF canvas_web.py with uvicorn (8 workers) for load testing.
# Port: 8000 (per task spec).
# Workers: 8 (per task spec).
# Logs: tests/load/server.log
param(
    [int]$Port = 8000,
    [int]$Workers = 8
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$LogDir = Join-Path $Root "tests\load"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir "server.log"

$Env:IMDF_WEB_PORT = "$Port"
$Env:UVICORN_WORKERS = "$Workers"
$Env:UVICORN_LOG_LEVEL = "warning"  # quieter for load test
$Env:RATE_LIMIT_ENABLED = "false"   # disable slowapi during load test
$Env:JWT_SECRET = "KFWonsp6d8L4zUg-UyMwFw9sIGF7yOQmBeiXWT47OCo"

$Py = "D:\ComfyUI\.ext\python.exe"

# Kill anything on the port first
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    foreach ($c in $existing) {
        $procId = $c.OwningProcess
        try {
            Write-Host "Killing existing process $procId on port $Port..."
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        } catch {}
    }
    Start-Sleep -Seconds 2
}

$Args = @(
    "-u"
    "-m"
    "uvicorn"
    "imdf.api.canvas_web:app"
    "--host", "127.0.0.1"
    "--port", "$Port"
    "--workers", "$Workers"
    "--log-level", "warning"
    "--no-access-log"
)
Write-Host "Starting IMDF uvicorn (workers=$Workers port=$Port)..."
Write-Host "Command: $Py $($Args -join ' ')"

# Start detached, redirect output to log file
$proc = Start-Process -FilePath $Py `
    -ArgumentList $Args `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError "$LogFile.err" `
    -PassThru -WindowStyle Hidden

Write-Host "Server PID: $($proc.Id)"
Write-Host "Log file:   $LogFile"

# Wait for server to come up
Write-Host "Waiting for /healthz to respond..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/healthz" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) {
            Write-Host "Server ready after $i seconds."
            $ready = $true
            break
        }
    } catch {
        # still booting
    }
}

if (-not $ready) {
    Write-Host "Server did NOT respond within 30s. Last 30 lines of log:"
    Get-Content $LogFile -Tail 30 -ErrorAction SilentlyContinue
    exit 1
}

Write-Host "Server is up at http://127.0.0.1:$Port"
exit 0