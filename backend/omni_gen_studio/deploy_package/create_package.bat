@echo off
chcp 65001 >nul
echo ================================
echo  创建 General AIGC Enhanced 部署包
echo ================================
echo.

set PACKAGE_NAME=General_AIGC_Enhanced_v1.0.0_Windows
set CURRENT_DIR=%CD%

echo [步骤1/3] 清理旧文件...
if exist "%PACKAGE_NAME%.zip" (
    del "%PACKAGE_NAME%.zip"
    echo 已清理旧压缩包
)
echo.

echo [步骤2/3] 创建压缩包...
echo 正在创建 %PACKAGE_NAME%.zip ...

REM 使用PowerShell创建ZIP文件
powershell -Command "Compress-Archive -Path '*' -DestinationPath '%PACKAGE_NAME%.zip' -Force"

if %errorlevel% equ 0 (
    echo [成功] 压缩包创建成功: %PACKAGE_NAME%.zip
) else (
    echo [错误] 压缩包创建失败
    echo 请手动将当前目录打包为ZIP文件
)
echo.

echo [步骤3/3] 显示文件信息...
dir "%PACKAGE_NAME%.zip" 2>nul
if %errorlevel% equ 0 (
    echo.
    echo [完成] 部署包创建完成！
    echo 文件名: %PACKAGE_NAME%.zip
    echo 大小: 
    powershell -Command "Get-Item '%PACKAGE_NAME%.zip' | Select-Object -ExpandProperty Length"
    echo.
    echo 可以将此文件分发给用户使用
) else (
    echo [完成] 请手动打包目录为ZIP文件
)

echo.
pause