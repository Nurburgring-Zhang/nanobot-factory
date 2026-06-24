@echo off
chcp 65001 >nul
echo ================================
echo  General AIGC Enhanced 系统检查
echo ================================
echo.

echo [步骤1/6] 检查操作系统...
ver
echo.

echo [步骤2/6] 检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo [错误] Python未安装或不在PATH中
    echo 请下载安装Python 3.8+: https://www.python.org/downloads/
) else (
    echo [成功] Python环境正常
)
echo.

echo [步骤3/6] 检查pip工具...
pip --version
if %errorlevel% neq 0 (
    echo [错误] pip不可用
) else (
    echo [成功] pip工具正常
)
echo.

echo [步骤4/6] 检查网络连接...
ping -n 1 127.0.0.1 >nul
if %errorlevel% neq 0 (
    echo [警告] 本地网络可能有问题
) else (
    echo [成功] 本地网络正常
)
echo.

echo [步骤5/6] 检查端口占用...
netstat -an | findstr ":3000" >nul
if %errorlevel% equ 0 (
    echo [警告] 端口3000已被占用
) else (
    echo [成功] 端口3000可用
)

netstat -an | findstr ":8000" >nul
if %errorlevel% equ 0 (
    echo [警告] 端口8000已被占用
) else (
    echo [成功] 端口8000可用
)
echo.

echo [步骤6/6] 检查显卡驱动...
nvidia-smi >nul 2>&1
if %errorlevel% equ 0 (
    echo [成功] NVIDIA显卡驱动正常
    nvidia-smi --query-gpu=name,driver_version --format=csv,noheader,nounits
) else (
    echo [信息] 未检测到NVIDIA显卡或驱动
    echo 如需GPU加速，请安装NVIDIA驱动
)
echo.

echo ================================
echo  检查完成！
echo ================================
echo.
echo 如有问题请参考README.md中的故障排除部分
echo.
pause