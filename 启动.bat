@echo off
chcp 65001 >nul
title 统一数据生产平台

echo ==========================================
echo   统一数据生产平台 v3.0
echo   nanobot-factory + IMDF + 智影
echo ==========================================
echo.

cd /d D:\Hermes\生产平台\nanobot-factory

echo [启动] Python server_unified.py --port 8899
start "UnifiedPlatform" python server_unified.py --port 8899

timeout /t 12 /nobreak >nul

echo [验证] 检查服务...
curl -s -o nul -w "  主页: %%{http_code}" http://127.0.0.1:8899/
echo.
curl -s -o nul -w "  API:  %%{http_code}" http://127.0.0.1:8899/api/v1/health
echo.

echo.
echo ==========================================
echo   平台已启动!
echo   http://localhost:8899
echo.
echo   预设账号: admin / Admin@2026!
echo ==========================================
pause
