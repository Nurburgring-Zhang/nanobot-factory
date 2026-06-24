#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
General AIGC Enhanced - 一键启动脚本
自动检查环境并启动程序

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import sys
import os
import subprocess
import platform
from pathlib import Path

def print_banner():
    """打印启动横幅"""
    print("=" * 70)
    print("🎉 General AIGC Enhanced - 全能AIGC生成器 v6.0")
    print("=" * 70)
    print("🚀 一键启动脚本")
    print("📅 版本: 2026-02-04")
    print("👨‍💻 作者: MiniMax Agent")
    print("=" * 70)

def check_environment():
    """检查运行环境"""
    print("🔍 检查运行环境...")
    
    # 检查Python版本
    python_version = sys.version_info
    if python_version >= (3, 8):
        print(f"✅ Python {python_version.major}.{python_version.minor}.{python_version.micro}")
    else:
        print(f"❌ Python {python_version.major}.{python_version.minor} (需要3.8+)")
        return False
    
    # 检查操作系统
    os_name = platform.system()
    print(f"✅ 操作系统: {os_name}")
    
    # 检查项目目录
    project_root = Path(__file__).parent
    if (project_root / "main.py").exists():
        print("✅ 项目目录正确")
    else:
        print("❌ 项目目录不正确")
        return False
    
    return True

def check_dependencies():
    """检查关键依赖"""
    print("\n📦 检查关键依赖...")
    
    required_deps = [
        ("tkinter", "GUI框架"),
        ("pathlib", "路径操作"),
        ("json", "JSON处理"),
        ("logging", "日志记录")
    ]
    
    missing_deps = []
    
    for dep_name, dep_desc in required_deps:
        try:
            __import__(dep_name)
            print(f"✅ {dep_desc}")
        except ImportError:
            print(f"❌ {dep_desc}")
            missing_deps.append(dep_name)
    
    if missing_deps:
        print(f"\n⚠️ 缺少依赖: {', '.join(missing_deps)}")
        return False
    
    return True

def check_virtual_env():
    """检查虚拟环境"""
    print("\n🐍 检查虚拟环境...")
    
    # 检查是否在虚拟环境中
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    
    if in_venv:
        print(f"✅ 已在虚拟环境中: {sys.prefix}")
        return True
    else:
        print("⚠️ 不在虚拟环境中")
        
        # 检查是否可以使用venv模块
        try:
            import venv
            print("✅ venv模块可用，可以自动创建虚拟环境")
            return True
        except ImportError:
            print("❌ venv模块不可用")
            return False

def auto_setup():
    """自动设置环境"""
    print("\n🔧 自动设置环境...")
    
    # 检查setup脚本
    project_root = Path(__file__).parent
    setup_script = project_root / "setup.bat" if platform.system() == "Windows" else project_root / "setup.sh"
    
    if setup_script.exists():
        print(f"✅ 找到设置脚本: {setup_script.name}")
        
        try:
            if platform.system() == "Windows":
                print("运行 setup.bat...")
                subprocess.run([str(setup_script)], check=True)
            else:
                print("运行 setup.sh...")
                subprocess.run(["bash", str(setup_script)], check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"❌ 设置脚本执行失败: {e}")
            return False
    else:
        print("⚠️ 未找到设置脚本，尝试手动安装依赖...")
        
        # 尝试安装requirements
        requirements_file = project_root / "requirements_windows.txt"
        if requirements_file.exists():
            try:
                print("安装依赖...")
                subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements_file)], check=True)
                return True
            except subprocess.CalledProcessError as e:
                print(f"❌ 依赖安装失败: {e}")
                return False
        else:
            print("❌ 未找到requirements文件")
            return False

def launch_main_program():
    """启动主程序"""
    print("\n🚀 启动主程序...")
    
    project_root = Path(__file__).parent
    main_script = project_root / "main.py"
    
    if not main_script.exists():
        print("❌ 未找到 main.py")
        return False
    
    try:
        print("正在启动 General AIGC Enhanced...")
        subprocess.run([sys.executable, str(main_script)], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 程序启动失败: {e}")
        return False
    except KeyboardInterrupt:
        print("\n👋 程序被用户中断")
        return True
    except Exception as e:
        print(f"❌ 启动异常: {e}")
        return False

def print_help():
    """打印帮助信息"""
    print("\n📚 使用说明:")
    print("1. 本脚本会自动检查环境并启动程序")
    print("2. 如果缺少依赖，会自动尝试安装")
    print("3. 如果虚拟环境不存在，会提示手动设置")
    print("4. 启动后请查看控制台输出确认运行状态")
    
    print("\n🛠️ 手动设置（如果自动设置失败）:")
    print("1. 创建虚拟环境:")
    print("   python -m venv venv_aigc")
    print("2. 激活虚拟环境:")
    print("   Windows: venv_aigc\\Scripts\\activate")
    print("   Linux/Mac: source venv_aigc/bin/activate")
    print("3. 安装依赖:")
    print("   pip install -r requirements_windows.txt")
    print("4. 启动程序:")
    print("   python main.py")

def main():
    """主函数"""
    # 打印横幅
    print_banner()
    
    try:
        # 1. 检查环境
        if not check_environment():
            print("\n❌ 环境检查失败")
            print_help()
            input("按Enter键退出...")
            return
        
        # 2. 检查依赖
        if not check_dependencies():
            print("\n❌ 依赖检查失败")
            print_help()
            input("按Enter键退出...")
            return
        
        # 3. 检查虚拟环境
        if not check_virtual_env():
            print("\n⚠️ 虚拟环境检查失败")
            print("\n请手动设置虚拟环境:")
            print("python -m venv venv_aigc")
            print("然后激活虚拟环境并重新运行此脚本")
            input("按Enter键退出...")
            return
        
        # 4. 询问是否自动设置
        response = input("\n是否自动设置环境并启动程序? (y/N): ").strip().lower()
        
        if response in ['y', 'yes', '是']:
            # 5. 自动设置
            if not auto_setup():
                print("\n❌ 自动设置失败")
                print_help()
                input("按Enter键退出...")
                return
        else:
            print("\n⏭️ 跳过自动设置")
            print("\n请手动设置环境后运行:")
            print("python main.py")
            input("按Enter键退出...")
            return
        
        # 6. 启动主程序
        launch_main_program()
        
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，退出程序")
    except Exception as e:
        print(f"\n❌ 启动过程出错: {e}")
        print_help()
        input("按Enter键退出...")

if __name__ == "__main__":
    main()
