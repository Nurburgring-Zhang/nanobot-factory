# Stop the IMDF load-test server (started via start_server.ps1)
param(
    [int]$Port = 8000
)

Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    $pid = $_.OwningProcess
    Write-Host "Killing PID $pid on port $Port"
    try { Stop-Process -Id $pid -Force } catch {}
}
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.Path -like '*ComfyUI\.ext\python.exe*' -and $_.CommandLine -like '*uvicorn*canvas_web*' } | ForEach-Object {
    Write-Host "Killing uvicorn canvas_web PID $($_.Id)"
    try { Stop-Process -Id $_.Id -Force } catch {}
}
Write-Host "Done."