@echo off
chcp 65001 >nul
echo ================================
echo  停止 General AIGC Enhanced 服务
echo ================================
echo.

echo [信息] 正在停止相关服务...

REM 停止占用3000端口的进程
echo [步骤1/4] 停止前端服务...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000"') do (
    echo 终止进程: %%a
    taskkill /f /pid %%a >nul 2>&1
)

REM 停止占用8000端口的进程
echo [步骤2/4] 停止后端服务...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000"') do (
    echo 终止进程: %%a
    taskkill /f /pid %%a >nul 2>&1
)

REM 停止Python进程
echo [步骤3/4] 清理Python进程...
taskkill /f /im python.exe >nul 2>&1
taskkill /f /im python3.exe >nul 2>&1

REM 清理可能的遗留进程
echo [步骤4/4] 清理其他相关进程...
taskkill /f /im uvicorn.exe >nul 2>&1
taskkill /f /im http.server.exe >nul 2>&1

echo.
echo [完成] 所有服务已停止！
echo.
echo 如果服务仍在运行，请手动关闭命令提示符窗口
pause