#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI启动脚本 - 使用项目虚拟环境
AIGC批处理工具 v5.4 集成版
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

def get_project_root():
    """获取项目根目录"""
    current_file = Path(__file__).resolve()
    # 从 run_comfyui.py 的父目录向上两级到项目根目录
    project_root = current_file.parent.parent
    return str(project_root)

def get_venv_python():
    """获取项目虚拟环境的Python解释器路径"""
    project_root = get_project_root()
    venv_path = Path(project_root) / "venv_aigc"
    
    if os.name == 'nt':  # Windows
        python_exe = venv_path / "Scripts" / "python.exe"
    else:  # Unix/Linux/macOS
        python_exe = venv_path / "bin" / "python"
    
    if not python_exe.exists():
        print(f"❌ 错误: 虚拟环境不存在于 {venv_path}")
        print("请先运行 'python manage_venv.py setup' 创建虚拟环境")
        sys.exit(1)
    
    return str(python_exe)

def ensure_venv_active():
    """确保虚拟环境已激活（检查Python路径）"""
    venv_python = get_venv_python()
    current_python = sys.executable
    
    if current_python != venv_python:
        print("🔄 重新启动以使用项目虚拟环境...")
        # 重新启动当前脚本，使用正确的Python解释器
        subprocess.run([venv_python] + sys.argv, cwd=get_project_root())
        sys.exit(0)

def run_comfyui(args=None):
    """运行ComfyUI"""
    project_root = get_project_root()
    comfyui_path = Path(project_root) / "ComfyUI"
    
    if not comfyui_path.exists():
        print(f"❌ 错误: ComfyUI目录不存在于 {comfyui_path}")
        sys.exit(1)
    
    # 设置环境变量
    env = os.environ.copy()
    env['PYTHONPATH'] = f"{comfyui_path}:{env.get('PYTHONPATH', '')}"
    
    # 构建命令
    python_exe = get_venv_python()
    comfyui_main = comfyui_path / "main.py"
    
    cmd = [python_exe, str(comfyui_main)]
    
    # 添加用户指定的参数
    if args:
        cmd.extend(args)
    else:
        # 默认参数
        cmd.extend(["--listen", "0.0.0.0:8188", "--port", "8188"])
    
    print(f"🚀 启动ComfyUI...")
    print(f"📁 项目根目录: {project_root}")
    print(f"🐍 Python解释器: {python_exe}")
    print(f"📋 命令: {' '.join(cmd)}")
    print("-" * 50)
    
    try:
        # 切换到ComfyUI目录
        os.chdir(comfyui_path)
        subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        print("\n🛑 ComfyUI已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="ComfyUI启动脚本 - AIGC批处理工具集成版")
    parser.add_argument("--port", default="8188", help="ComfyUI端口号 (默认: 8188)")
    parser.add_argument("--host", default="0.0.0.0", help="ComfyUI主机地址 (默认: 0.0.0.0)")
    parser.add_argument("--listen", action="store_true", help="监听所有接口")
    parser.add_argument("--gpu-devices", type=str, help="GPU设备ID，多个用逗号分隔")
    parser.add_argument("--disable-smart-memory", action="store_true", help="禁用智能内存管理")
    parser.add_argument("extra_args", nargs="*", help="额外参数传递给ComfyUI")
    
    args = parser.parse_args()
    
    # 检查并确保使用正确的虚拟环境
    ensure_venv_active()
    
    # 构建参数列表
    cmd_args = []
    if args.listen:
        cmd_args.extend(["--listen"])
        cmd_args.extend(["--host", args.host])
    
    cmd_args.extend(["--port", args.port])
    
    if args.gpu_devices:
        cmd_args.extend(["--gpu-devices", args.gpu_devices])
    
    if args.disable_smart_memory:
        cmd_args.append("--disable-smart-memory")
    
    cmd_args.extend(args.extra_args)
    
    # 启动ComfyUI
    run_comfyui(cmd_args)

if __name__ == "__main__":
    main()