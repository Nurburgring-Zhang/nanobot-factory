# Start all 12 microservices + 1 gateway for load testing.
# Each service runs on its dedicated port (8001-8012), gateway on 8000.
# Logs: tests/load/services/<name>.log
param(
    [int]$GatewayPort = 8000
)

$ErrorActionPreference = 'Stop'
$Root = "D:\Hermes\生产平台\nanobot-factory"
Set-Location $Root

$LogDir = Join-Path $Root "tests\load\services"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force -Path $LogDir | Out-Null }

$Py = "D:\ComfyUI\.ext\python.exe"

# Env: must be set for every child process
$Env:PYTHONPATH = Join-Path $Root "backend"
$Env:JWT_SECRET = "KFWonsp6d8L4zUg-UyMwFw9sIGF7yOQmBeiXWT47OCo"
$Env:IMDF_TEST_MODE = "1"
$Env:UVICORN_LOG_LEVEL = "warning"
$Env:RATE_LIMIT_ENABLED = "false"
$Env:GATEWAY_LOG_LEVEL = "warning"
$Env:IMDF_WEB_PORT = "$GatewayPort"

# Service map: name -> (port, importable app)
$Services = @(
    @{name="gateway";     port=8000; module="gateway.main:app"},
    @{name="user";        port=8001; module="services.user_service.main:app"},
    @{name="asset";       port=8002; module="services.asset_service.main:app"},
    @{name="annotation";  port=8003; module="services.annotation_service.main:app"},
    @{name="cleaning";    port=8004; module="services.cleaning_service.main:app"},
    @{name="scoring";     port=8005; module="services.scoring_service.main:app"},
    @{name="dataset";     port=8006; module="services.dataset_service.main:app"},
    @{name="evaluation";  port=8007; module="services.evaluation_service.main:app"},
    @{name="agent";       port=8008; module="services.agent_service.main:app"},
    @{name="workflow";    port=8009; module="services.workflow_service.main:app"},
    @{name="notification";port=8010; module="services.notification_service.main:app"},
    @{name="search";      port=8011; module="services.search_service.main:app"},
    @{name="collection";  port=8012; module="services.collection_service.main:app"}
)

# 1) Kill anything on the target ports
foreach ($svc in $Services) {
    $existing = Get-NetTCPConnection -LocalPort $svc.port -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        foreach ($c in $existing) {
            $pid2 = $c.OwningProcess
            try { Stop-Process -Id $pid2 -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}
Start-Sleep -Seconds 2

# 2) Launch each service detached
foreach ($svc in $Services) {
    $logFile = Join-Path $LogDir "$($svc.name).log"
    $errFile = Join-Path $LogDir "$($svc.name).err"
    $Args = @(
        "-u"
        "-m"
        "uvicorn"
        $svc.module
        "--host", "127.0.0.1"
        "--port", "$($svc.port)"
        "--log-level", "warning"
        "--no-access-log"
    )
    Write-Host "Starting $($svc.name) on port $($svc.port)..."
    $proc = Start-Process -FilePath $Py `
        -ArgumentList $Args `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError $errFile `
        -PassThru -WindowStyle Hidden
    Write-Host "  PID: $($proc.Id), log: $logFile"
}

# 3) Wait for all services to come up
Write-Host ""
Write-Host "Waiting for services to respond on /healthz..."
$Ready = @{}
$Deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $Deadline) {
    $allReady = $true
    foreach ($svc in $Services) {
        if ($Ready[$svc.name]) { continue }
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$($svc.port)/healthz" -UseBasicParsing -TimeoutSec 2
            if ($r.StatusCode -eq 200) {
                $Ready[$svc.name] = $true
                Write-Host "  [OK] $($svc.name) ($($svc.port))"
            } else {
                $allReady = $false
            }
        } catch {
            $allReady = $false
        }
    }
    if ($allReady) { break }
    Start-Sleep -Seconds 1
}

$readyCount = ($Ready.Values | Where-Object { $_ }).Count
Write-Host ""
Write-Host "Ready: $readyCount / $($Services.Count) services"
if ($readyCount -ne $Services.Count) {
    Write-Host ""
    Write-Host "Services that did NOT come up within 60s:"
    foreach ($svc in $Services) {
        if (-not $Ready[$svc.name]) {
            Write-Host "  [FAIL] $($svc.name) ($($svc.port))"
            $errFile = Join-Path $LogDir "$($svc.name).err"
            if (Test-Path $errFile) {
                Write-Host "    --- last 10 lines of $($svc.name).err ---"
                Get-Content $errFile -Tail 10 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" }
            }
        }
    }
    Write-Host ""
    Write-Host "Continuing with $readyCount services ready."
}

Write-Host ""
Write-Host "=== Stack ready. Gateway on http://127.0.0.1:$GatewayPort ==="
Write-Host "Logs: $LogDir"
exit 0
