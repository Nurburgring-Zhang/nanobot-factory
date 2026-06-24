#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OmniGen Studio - 增强启动器
整合所有功能的一键启动脚本
在Windows平台的虚拟环境中运行
"""

import os
import sys
import subprocess
import platform

def get_venv_python():
    """获取虚拟环境中的Python"""
    if platform.system() == "Windows":
        venv_python = "venv_aigc\\Scripts\\python.exe"
    else:
        venv_python = "venv_aigc/bin/python"

    if os.path.exists(venv_python):
        return venv_python
    return sys.executable

def check_venv():
    """检查虚拟环境"""
    venv_name = "venv_aigc"
    if platform.system() == "Windows":
        venv_path = os.path.join(venv_name, "Scripts", "python.exe")
    else:
        venv_path = os.path.join(venv_name, "bin", "python")

    if os.path.exists(venv_path):
        print(f"✅ 找到虚拟环境: {venv_name}")
        return True
    else:
        print(f"⚠️ 未找到虚拟环境: {venv_name}")
        print("正在尝试使用系统Python...")
        return False

def run_main():
    """运行主程序"""
    print("=" * 60)
    print("  OmniGen Studio - AIGC全能工具")
    print("=" * 60)
    print()

    # 检查虚拟环境
    check_venv()

    # 获取Python解释器
    python_exe = get_venv_python()
    print(f"使用Python: {python_exe}")

    # 检查torch是否可用
    try:
        result = subprocess.run([python_exe, "-c", "import torch; print(f'PyTorch: {torch.__version__}')"],
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"✅ {result.stdout.strip()}")
        else:
            print(f"⚠️ PyTorch未安装: {result.stderr.strip()}")
            print("请先运行 setup.bat 或 setup_environment.sh")
    except Exception as e:
        print(f"⚠️ 无法检查PyTorch: {e}")

    print()
    print("正在启动主程序...")
    print("-" * 60)

    # 运行主程序
    try:
        subprocess.run([python_exe, "main.py"])
    except KeyboardInterrupt:
        print("\n用户中断程序")
    except Exception as e:
        print(f"❌ 运行失败: {e}")

def run_comfyui():
    """启动ComfyUI"""
    python_exe = get_venv_python()
    comfyui_dir = "ComfyUI"

    if not os.path.exists(comfyui_dir):
        print("❌ ComfyUI目录不存在")
        return

    main_py = os.path.join(comfyui_dir, "main.py")
    if not os.path.exists(main_py):
        print("❌ ComfyUI/main.py 不存在")
        return

    print("启动ComfyUI...")
    try:
        subprocess.Popen([python_exe, main_py], cwd=comfyui_dir)
        print(f"✅ ComfyUI已启动: http://localhost:8188")
    except Exception as e:
        print(f"❌ ComfyUI启动失败: {e}")

def run_webui():
    """启动WebUI"""
    python_exe = get_venv_python()
    webui_dir = "stable-diffusion-webui"

    if not os.path.exists(webui_dir):
        print("❌ WebUI目录不存在")
        return

    if platform.system() == "Windows":
        launch_script = os.path.join(webui_dir, "webui.bat")
    else:
        launch_script = os.path.join(webui_dir, "webui.sh")

    if not os.path.exists(launch_script):
        print(f"❌ 启动脚本不存在: {launch_script}")
        return

    print("启动WebUI...")
    try:
        subprocess.Popen([launch_script], cwd=webui_dir, shell=True)
        print(f"✅ WebUI已启动: http://localhost:7860")
    except Exception as e:
        print(f"❌ WebUI启动失败: {e}")

def setup_environment():
    """设置环境"""
    print("开始设置运行环境...")

    python_exe = get_venv_python()

    # 安装依赖
    print("安装依赖...")
    try:
        subprocess.run([python_exe, "-m", "pip", "install", "-r", "requirements_windows.txt"],
                      timeout=600)
        print("✅ 依赖安装完成")
    except Exception as e:
        print(f"❌ 依赖安装失败: {e}")

def main():
    """主函数"""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == "--comfyui":
            run_comfyui()
        elif command == "--webui":
            run_webui()
        elif command == "--setup":
            setup_environment()
        elif command == "--help":
            print("""
OmniGen Studio 启动选项:
  python start_omnigen.py          启动主程序
  python start_omnigen.py --comfyui  启动ComfyUI
  python start_omnigen.py --webui    启动WebUI
  python start_omnigen.py --setup     设置环境
  python start_omnigen.py --all       启动所有服务
            """)
        elif command == "--all":
            print("启动所有服务...")
            run_comfyui()
            run_webui()
        else:
            print(f"未知命令: {command}")
            print("使用 --help 查看帮助")
    else:
        run_main()

if __name__ == "__main__":
    main()
