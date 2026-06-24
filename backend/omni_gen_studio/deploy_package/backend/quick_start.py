#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC批处理工具 v5.4 快速启动器
Windows专用版本，简化启动流程
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def setup_windows_environment():
    """设置Windows环境"""
    # 设置控制台编码为UTF-8
    if platform.system() == "Windows":
        try:
            os.system('chcp 65001 >nul 2>&1')
        except:
            pass
    
    # 设置Python路径
    script_dir = Path(__file__).parent.absolute()
    sys.path.insert(0, str(script_dir))
    
    return script_dir

def check_python_version():
    """检查Python版本"""
    print(f"🐍 Python版本: {sys.version}")
    
    if sys.version_info < (3, 8):
        print("❌ 错误：需要Python 3.8或更高版本")
        print("请下载并安装最新版本的Python：")
        print("https://www.python.org/downloads/")
        input("按回车键退出...")
        return False
    
    print("✅ Python版本检查通过")
    return True

def create_venv_if_needed():
    """必要时创建虚拟环境"""
    script_dir = Path(__file__).parent.absolute()
    venv_path = script_dir / "venv_aigc"
    
    if not venv_path.exists():
        print("🔧 创建虚拟环境...")
        try:
            result = subprocess.run([
                sys.executable, "-m", "venv", str(venv_path)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ 虚拟环境创建成功")
                return venv_path
            else:
                print(f"❌ 虚拟环境创建失败: {result.stderr}")
                return None
        except Exception as e:
            print(f"❌ 创建虚拟环境时出错: {e}")
            return None
    else:
        print("✅ 虚拟环境已存在")
        return venv_path

def install_basic_dependencies():
    """安装基础依赖"""
    print("📦 检查基础依赖...")
    
    try:
        # 导入基础模块检查
        import tkinter
        print("✅ tkinter - GUI框架")
    except ImportError:
        print("❌ tkinter - GUI框架缺失")
        return False
    
    try:
        from PIL import Image, ImageTk
        print("✅ Pillow - 图像处理")
    except ImportError:
        print("⚠️  Pillow - 图像处理库缺失，将安装...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "pillow"], check=True)
            print("✅ Pillow安装成功")
        except:
            print("❌ Pillow安装失败")
            return False
    
    try:
        import numpy
        print("✅ NumPy - 数值计算")
    except ImportError:
        print("⚠️  NumPy - 数值计算库缺失，将安装...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "numpy"], check=True)
            print("✅ NumPy安装成功")
        except:
            print("❌ NumPy安装失败")
            return False
    
    try:
        import requests
        print("✅ Requests - HTTP请求")
    except ImportError:
        print("⚠️  Requests - HTTP库缺失，将安装...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True)
            print("✅ Requests安装成功")
        except:
            print("❌ Requests安装失败")
            return False
    
    return True

def run_main_application():
    """运行主应用程序"""
    print("\n🚀 启动AIGC批处理工具...")
    print("=" * 50)
    
    try:
        # 导入并运行主程序
        from main import main
        main()
    except ImportError as e:
        print(f"❌ 导入主程序失败: {e}")
        print("请确保 main.py 文件存在于同一目录下")
        return False
    except Exception as e:
        print(f"❌ 程序运行时出错: {e}")
        return False
    
    return True

def main():
    """主启动函数"""
    # 设置Windows环境
    script_dir = setup_windows_environment()
    
    # 打印启动信息
    print("=" * 60)
    print("🎯 AIGC批处理工具 v5.4 - Windows快速启动器")
    print("📍 项目目录:", script_dir)
    print("💻 系统信息:", platform.system(), platform.release())
    print("=" * 60)
    
    # 检查Python版本
    if not check_python_version():
        return
    
    # 创建虚拟环境
    venv_path = create_venv_if_needed()
    if not venv_path:
        input("按回车键退出...")
        return
    
    # 安装基础依赖
    if not install_basic_dependencies():
        print("⚠️  部分依赖缺失，程序可能无法正常运行")
        response = input("是否继续启动? (Y/n): ").lower().strip()
        if response in ['n', 'no']:
            return
    
    # 运行主程序
    try:
        success = run_main_application()
        if not success:
            print("\n❌ 程序启动失败")
            print("请检查错误信息或联系技术支持")
    except KeyboardInterrupt:
        print("\n👋 用户中断，正在退出...")
    except Exception as e:
        print(f"\n❌ 启动时发生未预期错误: {e}")
        print("请检查系统环境和依赖包")
    
    finally:
        input("\n按回车键退出...")

if __name__ == "__main__":
    main()