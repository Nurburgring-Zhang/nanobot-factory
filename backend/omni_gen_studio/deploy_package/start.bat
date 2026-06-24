@echo off
chcp 65001 >nul
echo ================================
echo  General AIGC Enhanced - 本地化部署
echo  Version: 1.0.0
echo ================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到Python，请先安装Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [信息] 检测到Python环境
python --version
echo.

REM 检查pip是否可用
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] pip不可用，请检查Python安装
    pause
    exit /b 1
)

echo [信息] 检查Python依赖...
cd /d "%~dp0backend"

REM 安装Python依赖
echo [步骤1/4] 安装Python后端依赖...
pip install -r requirements_windows.txt
if %errorlevel% neq 0 (
    echo [错误] Python依赖安装失败
    pause
    exit /b 1
)

REM 启动FastAPI后端服务
echo.
echo [步骤2/4] 启动FastAPI后端服务...
start "FastAPI Backend" cmd /k "python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

REM 等待后端服务启动
echo [信息] 等待后端服务启动...
timeout /t 10 /nobreak >nul

REM 启动Web服务器服务前端
echo [步骤3/4] 启动Web服务器...
cd /d "%~dp0frontend"

REM 检查是否有Python内置的http.server
echo [步骤4/4] 启动前端Web服务...
start "Frontend Server" cmd /k "python -m http.server 3000"

REM 打开浏览器
echo.
echo [完成] 服务启动完成！
echo.
echo 前端地址: http://localhost:3000
echo 后端API: http://localhost:8000
echo API文档: http://localhost:8000/docs
echo.
echo 按任意键打开浏览器...
pause >nul
start http://localhost:3000

echo.
echo 后端服务正在后台运行，关闭窗口即可停止服务
pause