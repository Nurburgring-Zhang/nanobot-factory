#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI和WebUI一键安装和配置脚本
AIGC批处理工具 v5.4 集成版
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def get_project_root():
    """获取项目根目录"""
    current_file = Path(__file__).resolve()
    project_root = current_file.parent
    return project_root

def get_venv_python():
    """获取项目虚拟环境的Python解释器路径"""
    project_root = get_project_root()
    venv_path = project_root / "venv_aigc"
    
    if os.name == 'nt':  # Windows
        python_exe = venv_path / "Scripts" / "python.exe"
    else:  # Unix/Linux/macOS
        python_exe = venv_path / "bin" / "python"
    
    return str(python_exe) if python_exe.exists() else None

def check_requirements():
    """检查基本要求"""
    print("🔍 检查基本要求...")
    
    # 检查Python
    python_version = sys.version_info
    if python_version < (3, 8):
        print(f"❌ Python版本过低: {python_version.major}.{python_version.minor}，需要3.8+")
        return False
    
    print(f"✅ Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # 检查虚拟环境
    venv_python = get_venv_python()
    if not venv_python:
        print("❌ 虚拟环境不存在或Python解释器未找到")
        print("请先运行 'python manage_venv.py setup' 创建虚拟环境")
        return False
    
    print(f"✅ 虚拟环境Python: {venv_python}")
    
    # 检查ComfyUI和WebUI
    project_root = get_project_root()
    comfyui_path = project_root / "ComfyUI"
    webui_path = project_root / "stable-diffusion-webui"
    
    if not comfyui_path.exists():
        print("❌ ComfyUI代码不存在")
        print("请确保ComfyUI文件夹已存在于项目中")
        return False
    
    if not webui_path.exists():
        print("❌ WebUI代码不存在")
        print("请确保stable-diffusion-webui文件夹已存在于项目中")
        return False
    
    print("✅ ComfyUI代码已存在")
    print("✅ WebUI代码已存在")
    
    return True

def install_comfyui_dependencies():
    """安装ComfyUI依赖"""
    print("📦 安装ComfyUI依赖...")
    
    project_root = get_project_root()
    comfyui_path = project_root / "ComfyUI"
    venv_python = get_venv_python()
    
    try:
        # 进入ComfyUI目录
        os.chdir(comfyui_path)
        
        # 安装requirements.txt
        requirements_file = comfyui_path / "requirements.txt"
        if requirements_file.exists():
            print("📋 安装ComfyUI requirements...")
            result = subprocess.run([
                venv_python, "-m", "pip", "install", "-r", str(requirements_file)
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"❌ ComfyUI依赖安装失败:")
                print(result.stderr)
                return False
            else:
                print("✅ ComfyUI依赖安装成功")
        
        # 安装额外的依赖
        extra_deps = [
            "torch>=2.0.0",
            "torchvision>=0.15.0",
            "accelerate>=0.20.0",
            "transformers>=4.25.0",
            "diffusers>=0.21.0",
            "xformers>=0.0.20",
            "safetensors>=0.3.0"
        ]
        
        print("📦 安装额外依赖...")
        for dep in extra_deps:
            print(f"  安装: {dep}")
            result = subprocess.run([
                venv_python, "-m", "pip", "install", dep
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"  ⚠️ {dep} 安装失败: {result.stderr}")
        
        print("✅ ComfyUI依赖安装完成")
        return True
        
    except Exception as e:
        print(f"❌ ComfyUI依赖安装失败: {e}")
        return False
    finally:
        os.chdir(get_project_root())

def install_webui_dependencies():
    """安装WebUI依赖"""
    print("📦 安装WebUI依赖...")
    
    project_root = get_project_root()
    webui_path = project_root / "stable-diffusion-webui"
    venv_python = get_venv_python()
    
    try:
        # 进入WebUI目录
        os.chdir(webui_path)
        
        # 安装requirements.txt
        requirements_file = webui_path / "requirements.txt"
        if requirements_file.exists():
            print("📋 安装WebUI requirements...")
            result = subprocess.run([
                venv_python, "-m", "pip", "install", "-r", str(requirements_file)
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"❌ WebUI依赖安装失败:")
                print(result.stderr)
                return False
            else:
                print("✅ WebUI依赖安装成功")
        
        # 安装额外的依赖
        extra_deps = [
            "torch>=2.0.0",
            "torchvision>=0.15.0",
            "accelerate>=0.20.0",
            "transformers>=4.25.0",
            "diffusers>=0.21.0",
            "gfpgan>=1.3.8",
            "realesrgan>=0.3.0"
        ]
        
        print("📦 安装额外依赖...")
        for dep in extra_deps:
            print(f"  安装: {dep}")
            result = subprocess.run([
                venv_python, "-m", "pip", "install", dep
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"  ⚠️ {dep} 安装失败: {result.stderr}")
        
        print("✅ WebUI依赖安装完成")
        return True
        
    except Exception as e:
        print(f"❌ WebUI依赖安装失败: {e}")
        return False
    finally:
        os.chdir(get_project_root())

def create_config():
    """创建配置文件"""
    print("⚙️ 创建配置文件...")
    
    project_root = get_project_root()
    config_dir = project_root / "config"
    config_dir.mkdir(exist_ok=True)
    
    # 创建ComfyUI配置文件
    comfyui_config = {
        "port": 8188,
        "listen": True,
        "enable_cors": True,
        "model_path": str(project_root / "models"),
        "custom_nodes_path": str(project_root / "ComfyUI" / "custom_nodes"),
        "python_path": get_venv_python()
    }
    
    with open(config_dir / "comfyui_config.json", 'w', encoding='utf-8') as f:
        json.dump(comfyui_config, f, indent=2, ensure_ascii=False)
    
    # 创建WebUI配置文件
    webui_config = {
        "listen": True,
        "port": 7860,
        "model_path": str(project_root / "models"),
        "enable_cors": True,
        "python_path": get_venv_python()
    }
    
    with open(config_dir / "webui_config.json", 'w', encoding='utf-8') as f:
        json.dump(webui_config, f, indent=2, ensure_ascii=False)
    
    print("✅ 配置文件创建完成")

def main():
    """主函数"""
    print("🎨 AIGC批处理工具 v5.4 - ComfyUI/WebUI一键安装")
    print("=" * 60)
    
    # 检查要求
    if not check_requirements():
        sys.exit(1)
    
    # 安装依赖
    comfyui_success = install_comfyui_dependencies()
    webui_success = install_webui_dependencies()
    
    # 创建配置
    create_config()
    
    # 总结
    print("\n" + "=" * 60)
    print("📋 安装结果:")
    print(f"ComfyUI: {'✅ 成功' if comfyui_success else '❌ 失败'}")
    print(f"WebUI: {'✅ 成功' if webui_success else '❌ 失败'}")
    
    if comfyui_success and webui_success:
        print("\n🎉 ComfyUI和WebUI安装完成!")
        print("\n🚀 启动方式:")
        print("  ComfyUI: python run_comfyui.py")
        print("  WebUI: python run_webui.py")
        print("\n或使用管理脚本:")
        print("  python manage_venv.py run_comfyui")
        print("  python manage_venv.py run_webui")
    else:
        print("\n❌ 安装过程中出现问题，请检查错误信息")
        sys.exit(1)

if __name__ == "__main__":
    main()