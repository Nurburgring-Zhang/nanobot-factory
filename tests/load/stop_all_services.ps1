# Stop all 12 services + gateway (started via start_all_services.ps1)
param()

$Root = "D:\Hermes\生产平台\nanobot-factory"
$Ports = @(8000, 8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009, 8010, 8011, 8012)

foreach ($p in $Ports) {
    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        $pid2 = $c.OwningProcess
        Write-Host "Killing PID $pid2 on port $p"
        try { Stop-Process -Id $pid2 -Force -ErrorAction SilentlyContinue } catch {}
    }
}

# Also kill any lingering uvicorn processes by name pattern
Get-Process python -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -like '*ComfyUI\.ext\python.exe*' -and
    ($_.CommandLine -like '*uvicorn*' -or $_.MainWindowTitle -like '*uvicorn*')
} | ForEach-Object {
    Write-Host "Killing uvicorn python PID $($_.Id) ($($_.CommandLine.Substring(0, [Math]::Min(80, $_.CommandLine.Length))))"
    try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
}

Write-Host "Done."
