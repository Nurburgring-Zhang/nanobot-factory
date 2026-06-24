#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC批处理工具 v5.4 环境检查和快速启动
检查Python版本、依赖包、虚拟环境状态
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """检查Python版本"""
    print("🐍 检查Python版本...")
    version = sys.version_info
    print(f"   当前版本: {version.major}.{version.minor}.{version.micro}")
    
    if version >= (3, 8):
        print("   ✅ Python版本符合要求 (3.8+)")
        return True
    else:
        print("   ❌ Python版本过低，需要3.8+")
        return False

def check_virtual_env():
    """检查虚拟环境"""
    print("\n🏠 检查虚拟环境...")
    project_root = Path(__file__).parent
    venv_path = project_root / "venv_aigc"
    
    if venv_path.exists():
        print(f"   ✅ 虚拟环境存在: {venv_path}")
        
        # 检查Python可执行文件
        if os.name == 'nt':
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            python_exe = venv_path / "bin" / "python"
        
        if python_exe.exists():
            print("   ✅ Python解释器存在")
            
            # 检查pip
            try:
                result = subprocess.run([
                    str(python_exe), "-m", "pip", "--version"
                ], capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    print("   ✅ pip可用")
                    print(f"   版本: {result.stdout.strip()}")
                    return True
                else:
                    print("   ❌ pip不可用")
                    return False
            except Exception as e:
                print(f"   ❌ pip检查失败: {e}")
                return False
        else:
            print("   ❌ Python解释器不存在")
            return False
    else:
        print("   ❌ 虚拟环境不存在")
        return False

def check_key_packages():
    """检查关键依赖包"""
    print("\n📦 检查关键依赖包...")
    
    project_root = Path(__file__).parent
    venv_path = project_root / "venv_aigc"
    
    if not venv_path.exists():
        print("   ❌ 虚拟环境不存在，请先创建虚拟环境")
        return False
    
    if os.name == 'nt':
        python_exe = venv_path / "Scripts" / "python.exe"
    else:
        python_exe = venv_path / "bin" / "python"
    
    # 关键包列表
    key_packages = [
        "PIL",  # Pillow
        "numpy", 
        "pandas",
        "torch",
        "tkinter",  # 通常内置
    ]
    
    missing_packages = []
    
    for package in key_packages:
        try:
            result = subprocess.run([
                str(python_exe), "-c", f"import {package}; print('OK')"
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                print(f"   ✅ {package}")
            else:
                print(f"   ❌ {package}")
                missing_packages.append(package)
        except Exception as e:
            print(f"   ❌ {package} (检查失败: {e})")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n⚠️  缺失 {len(missing_packages)} 个关键包: {', '.join(missing_packages)}")
        print("   建议运行: python manage_venv.py setup-all")
        return False
    else:
        print("\n✅ 所有关键依赖包已安装")
        return True

def check_project_files():
    """检查项目文件"""
    print("\n📁 检查项目文件...")
    
    project_root = Path(__file__).parent
    
    required_files = [
        "main.py",
        "manage_venv.py",
        "requirements_windows.txt",
        "启动工具.bat",
        "backend_modules"
    ]
    
    optional_files = [
        "ComfyUI",
        "stable-diffusion-webui",
        "run_comfyui.py",
        "run_webui.py",
        "install_comfyui_webui.py"
    ]
    
    all_good = True
    
    # 检查必需文件
    for file_name in required_files:
        file_path = project_root / file_name
        if file_path.exists():
            print(f"   ✅ {file_name}")
        else:
            print(f"   ❌ {file_name} (必需)")
            all_good = False
    
    # 检查可选文件
    for file_name in optional_files:
        file_path = project_root / file_name
        if file_path.exists():
            print(f"   ✅ {file_name}")
        else:
            print(f"   ⚠️  {file_name} (可选)")
    
    return all_good

def create_quick_start_script():
    """创建快速启动脚本"""
    print("\n🔧 创建快速启动脚本...")
    
    script_content = """@echo off
chcp 65001 >nul
title AIGC批处理工具 v5.4 - 快速启动

echo ========================================
echo   AIGC批处理工具 v5.4 快速启动
echo ========================================
echo.

REM 激活虚拟环境
call venv_aigc\\Scripts\\activate.bat

REM 检查Python
python -c "import sys; print(f'Python {sys.version}')"

REM 检查关键包
echo 检查关键依赖...
python -c "import PIL, numpy, pandas; print('✅ 关键依赖正常')"

echo.
echo 🚀 启动主程序...
python main.py

pause
"""
    
    script_path = Path(__file__).parent / "快速启动.bat"
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print(f"   ✅ 创建快速启动脚本: {script_path}")

def main():
    """主函数"""
    print("🔍 AIGC批处理工具 v5.4 环境检查")
    print("=" * 50)
    
    # 检查Python版本
    python_ok = check_python_version()
    
    # 检查虚拟环境
    venv_ok = check_virtual_env()
    
    # 检查项目文件
    files_ok = check_project_files()
    
    # 检查依赖包
    if venv_ok:
        packages_ok = check_key_packages()
    else:
        packages_ok = False
    
    print("\n" + "=" * 50)
    print("📋 检查结果:")
    print(f"Python版本: {'✅' if python_ok else '❌'}")
    print(f"虚拟环境: {'✅' if venv_ok else '❌'}")
    print(f"项目文件: {'✅' if files_ok else '❌'}")
    print(f"依赖包: {'✅' if packages_ok else '❌'}")
    
    if python_ok and files_ok:
        print("\n✅ 环境检查基本通过！")
        
        if not venv_ok:
            print("\n🔧 建议操作:")
            print("1. 运行: python manage_venv.py setup-all")
        elif not packages_ok:
            print("\n📦 建议操作:")
            print("1. 运行: python manage_venv.py setup-all")
        
        # 创建快速启动脚本
        create_quick_start_script()
        
    else:
        print("\n❌ 环境检查未通过，请先解决上述问题")
        print("\n🔧 建议操作:")
        print("1. 确保Python 3.8+已安装")
        print("2. 运行: python manage_venv.py setup-all")
    
    print("\n👋 检查完成")

if __name__ == "__main__":
    main()