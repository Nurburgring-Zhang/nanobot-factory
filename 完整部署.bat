@echo off
chcp 65001 >nul
echo ==========================================
echo   统一数据生产平台 — 完整部署脚本
echo ==========================================
echo.
echo 项目位置: D:\Hermes\生产平台\nanobot-factory
echo.

REM 1. Python虚拟环境
echo [1/5] 设置Python环境...
cd /d D:\Hermes\生产平台\nanobot-factory\backend
if not exist venv (
    python -m venv venv
    echo   创建venv完成
)
call venv\Scripts\activate
pip install -r requirements.txt -q
echo   Python依赖安装完成

REM 2. Web前端
echo.
echo [2/5] 构建Web前端...
cd /d D:\Hermes\生产平台\nanobot-factory\web
if not exist node_modules (
    echo   安装npm依赖(首次较慢)...
    npm install --legacy-peer-deps
)
echo   构建前端dist...
npm run build
echo   Web前端构建完成

REM 3. 初始化数据库
echo.
echo [3/5] 初始化数据库和预设账号...
cd /d D:\Hermes\生产平台\nanobot-factory\backend
python scripts\init_accounts.py --reset
echo   预设账号创建完成

REM 4. 复制原项目数据
echo.
echo [4/5] 迁移原项目数据...
set SRC=D:\minimax\nanobot-factory\nanobot-factory\data
set DST=D:\Hermes\生产平台\nanobot-factory\data
if exist "%SRC%" (
    copy /Y "%SRC%\*.db" "%DST%\" 2>nul
    xcopy /E /I /Y "%SRC%\assets" "%DST%\assets" 2>nul
    xcopy /E /I /Y "%SRC%\datasets" "%DST%\datasets" 2>nul
    xcopy /E /I /Y "%SRC%\canvas" "%DST%\canvas" 2>nul
    xcopy /E /I /Y "%SRC%\video_pipeline" "%DST%\video_pipeline" 2>nul
    echo   数据迁移完成
) else (
    echo   原项目数据目录不存在,跳过
)

REM 5. ComfyUI模型(如果原项目有)
echo.
echo [5/5] 检查ComfyUI模型...
set COMFY_SRC=D:\minimax\nanobot-factory\nanobot-factory\comfyui\models
set COMFY_DST=D:\Hermes\生产平台\nanobot-factory\comfyui\models
if exist "%COMFY_SRC%" (
    if not exist "%COMFY_DST%" mkdir "%COMFY_DST%"
    xcopy /E /I /Y "%COMFY_SRC%" "%COMFY_DST%"
    echo   ComfyUI模型复制完成
) else (
    echo   ComfyUI模型需手动下载(运行时会自动下载)
)

echo.
echo ==========================================
echo   部署完成!
echo.
echo   启动方式:
echo     backend: cd backend ^&^& venv\Scripts\activate ^&^& python server.py --port 8899
echo     web:     cd web ^&^& npm run dev
echo.
echo   访问地址:
echo     主平台:  http://localhost:8899
echo     IMDF:    http://localhost:8899/imdf
echo     智影:    http://localhost:8899/zhiying
echo     API文档: http://localhost:8899/docs
echo.
echo   预设账号: admin / Admin@2026! (超级管理员)
echo ==========================================
pause
