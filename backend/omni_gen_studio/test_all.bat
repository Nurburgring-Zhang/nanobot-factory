@echo off
chcp 65001 >nul
echo ================================
echo  General AIGC Enhanced 功能测试
echo ================================
echo.

echo [步骤1/4] 检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo [错误] Python未安装
    pause
    exit /b 1
)

echo [步骤2/4] 运行功能验证...
python 功能验证脚本.py

echo [步骤3/4] 运行增强启动...
python enhanced_startup.py

echo [步骤4/4] 测试完成
echo 按任意键退出...
pause >nul
