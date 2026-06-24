#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整的ComfyUI和WebUI集成管理器
确保所有组件都使用同一个虚拟环境
"""

import os
import sys
import subprocess
import shutil
import time
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import threading
import webbrowser

class ComfyUIWebUIIntegration:
    """ComfyUI和WebUI完整集成管理器"""
    
    def __init__(self, venv_path: Optional[str] = None):
        """初始化集成管理器"""
        self.project_root = Path(__file__).parent.parent.absolute()
        self.venv_path = Path(venv_path) if venv_path else self.project_root / "venv_aigc"
        self.comfyui_path = self.project_root / "ComfyUI"
        self.webui_path = self.project_root / "stable-diffusion-webui"
        self.comfyui_process = None
        self.webui_process = None
        self.comfyui_status = 'stopped'
        self.webui_status = 'stopped'
        
        print(f"🔗 ComfyUI和WebUI集成管理器初始化...")
        print(f"📍 项目根目录: {self.project_root}")
        print(f"🐍 虚拟环境路径: {self.venv_path}")
        print(f"🎨 ComfyUI路径: {self.comfyui_path}")
        print(f"🌐 WebUI路径: {self.webui_path}")
    
    def get_python_exe(self) -> str:
        """获取虚拟环境中的Python可执行文件"""
        if os.name == 'nt':  # Windows
            return str(self.venv_path / "Scripts" / "python.exe")
        else:  # Unix/Linux/macOS
            return str(self.venv_path / "bin" / "python")
    
    def get_pip_exe(self) -> str:
        """获取虚拟环境中的pip可执行文件"""
        if os.name == 'nt':  # Windows
            return str(self.venv_path / "Scripts" / "pip.exe")
        else:  # Unix/Linux/macOS
            return str(self.venv_path / "bin" / "pip")
    
    def check_venv_exists(self) -> bool:
        """检查虚拟环境是否存在"""
        return self.venv_path.exists() and (self.venv_path / "pyvenv.cfg").exists()
    
    def ensure_venv(self) -> bool:
        """确保虚拟环境存在"""
        if not self.check_venv_exists():
            print("❌ 虚拟环境不存在，请先运行虚拟环境管理器")
            return False
        return True
    
    def install_comfyui(self, force_reinstall: bool = False) -> bool:
        """安装ComfyUI"""
        try:
            print("📥 开始安装ComfyUI...")
            
            if not self.ensure_venv():
                return False
            
            # 检查是否已安装
            if self.comfyui_path.exists() and not force_reinstall:
                print(f"⚠️ ComfyUI已存在于: {self.comfyui_path}")
                return self._setup_comfyui_config()
            
            # 创建ComfyUI目录
            self.comfyui_path.mkdir(parents=True, exist_ok=True)
            
            print(f"🔧 从Git克隆ComfyUI...")
            if not self._clone_comfyui():
                return False
            
            print(f"📦 在虚拟环境中安装ComfyUI依赖...")
            if not self._install_comfyui_dependencies():
                return False
            
            print(f"✅ ComfyUI安装完成!")
            return self._setup_comfyui_config()
            
        except Exception as e:
            print(f"❌ ComfyUI安装失败: {e}")
            return False
    
    def _clone_comfyui(self) -> bool:
        """从Git克隆ComfyUI"""
        try:
            python_exe = self.get_python_exe()
            
            # 使用git clone（如果可用）或直接下载
            git_check = subprocess.run(['git', '--version'], capture_output=True)
            if git_check.returncode == 0:
                print("  📋 使用Git克隆...")
                result = subprocess.run([
                    'git', 'clone', 'https://github.com/comfyanonymous/ComfyUI.git', 
                    str(self.comfyui_path)
                ], capture_output=True, text=True)
                return result.returncode == 0
            else:
                print("  ⚠️ Git不可用，请手动下载ComfyUI源码")
                # 这里可以添加手动下载逻辑
                return False
                
        except Exception as e:
            print(f"  ❌ Git克隆失败: {e}")
            return False
    
    def _install_comfyui_dependencies(self) -> bool:
        """安装ComfyUI依赖"""
        try:
            pip_exe = self.get_pip_exe()
            requirements_file = self.comfyui_path / "requirements.txt"
            
            if not requirements_file.exists():
                print("  ⚠️ ComfyUI requirements.txt 不存在，创建基础requirements...")
                # 创建基础的requirements.txt
                basic_requirements = [
                    "torch>=2.0.0",
                    "torchvision>=0.15.0", 
                    "torchaudio>=2.0.0",
                    "accelerate>=0.20.0",
                    "transformers>=4.25.0",
                    "diffusers>=0.21.0",
                    "xformers>=0.0.20",
                    "pillow>=9.0.0",
                    "numpy>=1.21.0",
                    "scipy>=1.9.0",
                    "scikit-image>=0.19.0",
                    "opencv-python>=4.5.0",
                    "matplotlib>=3.4.0",
                    "tqdm>=4.62.0",
                    "requests>=2.25.0",
                    "safetensors>=0.3.0",
                    "onnx>=1.12.0",
                    "onnxruntime>=1.12.0"
                ]
                
                with open(requirements_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(basic_requirements))
            
            # 安装依赖
            result = subprocess.run([
                str(pip_exe), 'install', '-r', str(requirements_file)
            ], capture_output=True, text=True)
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"  ❌ 依赖安装失败: {e}")
            return False
    
    def _setup_comfyui_config(self) -> bool:
        """设置ComfyUI配置"""
        try:
            # 创建ComfyUI配置文件
            config_dir = self.comfyui_path / "config"
            config_dir.mkdir(exist_ok=True)
            
            config_file = config_dir / "comfyui_config.json"
            config_data = {
                "port": 8188,
                "listen": True,
                "enable_cors": True,
                "model_path": str(self.project_root / "models"),
                "custom_nodes_path": str(self.comfyui_path / "custom_nodes")
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ ComfyUI配置已设置")
            return True
            
        except Exception as e:
            print(f"❌ ComfyUI配置设置失败: {e}")
            return False
    
    def install_webui(self, force_reinstall: bool = False) -> bool:
        """安装WebUI (AUTOMATIC1111)"""
        try:
            print("📥 开始安装WebUI...")
            
            if not self.ensure_venv():
                return False
            
            # 检查是否已安装
            if self.webui_path.exists() and not force_reinstall:
                print(f"⚠️ WebUI已存在于: {self.webui_path}")
                return self._setup_webui_config()
            
            # 创建WebUI目录
            self.webui_path.mkdir(parents=True, exist_ok=True)
            
            print(f"🔧 从Git克隆WebUI...")
            if not self._clone_webui():
                return False
            
            print(f"📦 在虚拟环境中安装WebUI依赖...")
            if not self._install_webui_dependencies():
                return False
            
            print(f"✅ WebUI安装完成!")
            return self._setup_webui_config()
            
        except Exception as e:
            print(f"❌ WebUI安装失败: {e}")
            return False
    
    def _clone_webui(self) -> bool:
        """从Git克隆WebUI"""
        try:
            git_check = subprocess.run(['git', '--version'], capture_output=True)
            if git_check.returncode == 0:
                print("  📋 使用Git克隆...")
                result = subprocess.run([
                    'git', 'clone', 'https://github.com/AUTOMATIC1111/stable-diffusion-webui.git',
                    str(self.webui_path)
                ], capture_output=True, text=True)
                return result.returncode == 0
            else:
                print("  ⚠️ Git不可用，请手动下载WebUI源码")
                return False
                
        except Exception as e:
            print(f"  ❌ Git克隆失败: {e}")
            return False
    
    def _install_webui_dependencies(self) -> bool:
        """安装WebUI依赖"""
        try:
            pip_exe = self.get_pip_exe()
            requirements_file = self.webui_path / "requirements.txt"
            
            if not requirements_file.exists():
                print("  ⚠️ WebUI requirements.txt 不存在，创建基础requirements...")
                # 创建基础的requirements.txt
                basic_requirements = [
                    "torch>=2.0.0",
                    "torchvision>=0.15.0",
                    "torchaudio>=2.0.0", 
                    "accelerate>=0.20.0",
                    "transformers>=4.25.0",
                    "diffusers>=0.21.0",
                    "xformers>=0.0.20",
                    "pillow>=9.0.0",
                    "numpy>=1.21.0",
                    "scipy>=1.9.0",
                    "scikit-image>=0.19.0",
                    "opencv-python>=4.5.0",
                    "matplotlib>=3.4.0",
                    "tqdm>=4.62.0",
                    "requests>=2.25.0",
                    "safetensors>=0.3.0",
                    "onnx>=1.12.0",
                    "onnxruntime>=1.12.0",
                    "gfpgan>=1.3.8",
                    " realesrgan>=0.3.0"
                ]
                
                with open(requirements_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(basic_requirements))
            
            # 安装依赖
            result = subprocess.run([
                str(pip_exe), 'install', '-r', str(requirements_file)
            ], capture_output=True, text=True)
            
            return result.returncode == 0
            
        except Exception as e:
            print(f"  ❌ 依赖安装失败: {e}")
            return False
    
    def _setup_webui_config(self) -> bool:
        """设置WebUI配置"""
        try:
            # 创建WebUI配置文件
            config_dir = self.webui_path / "config"
            config_dir.mkdir(exist_ok=True)
            
            config_file = config_dir / "webui_config.json"
            config_data = {
                "listen": True,
                "port": 7860,
                "model_path": str(self.project_root / "models"),
                "enable_cors": True,
                "enable_mathjax": True
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            print(f"✅ WebUI配置已设置")
            return True
            
        except Exception as e:
            print(f"❌ WebUI配置设置失败: {e}")
            return False
    
    def start_comfyui(self, auto_open: bool = True) -> bool:
        """启动ComfyUI"""
        try:
            if not self.comfyui_path.exists():
                print("❌ ComfyUI未安装，请先运行install_comfyui()")
                return False
            
            print("🚀 启动ComfyUI...")
            
            # 使用项目根目录的run_comfyui.py脚本
            comfyui_runner = self.project_root / "run_comfyui.py"
            
            if not comfyui_runner.exists():
                print("❌ ComfyUI启动脚本不存在")
                return False
            
            python_exe = self.get_python_exe()
            
            # 使用虚拟环境Python启动脚本
            self.comfyui_process = subprocess.Popen([
                str(python_exe), str(comfyui_runner)
            ], cwd=str(self.project_root))
            
            self.comfyui_status = 'starting'
            
            # 等待启动
            print("⏳ 等待ComfyUI启动...")
            time.sleep(5)
            
            if self.comfyui_process.poll() is None:
                self.comfyui_status = 'running'
                print("✅ ComfyUI启动成功! 端口: 8188")
                
                if auto_open:
                    webbrowser.open("http://localhost:8188")
                
                return True
            else:
                self.comfyui_status = 'failed'
                print("❌ ComfyUI启动失败")
                return False
                
        except Exception as e:
            print(f"❌ ComfyUI启动失败: {e}")
            self.comfyui_status = 'failed'
            return False
    
    def start_webui(self, auto_open: bool = True) -> bool:
        """启动WebUI"""
        try:
            if not self.webui_path.exists():
                print("❌ WebUI未安装，请先运行install_webui()")
                return False
            
            print("🚀 启动WebUI...")
            
            # 使用项目根目录的run_webui.py脚本
            webui_runner = self.project_root / "run_webui.py"
            
            if not webui_runner.exists():
                print("❌ WebUI启动脚本不存在")
                return False
            
            python_exe = self.get_python_exe()
            
            # 使用虚拟环境Python启动脚本
            self.webui_process = subprocess.Popen([
                str(python_exe), str(webui_runner)
            ], cwd=str(self.project_root))
            
            self.webui_status = 'starting'
            
            # 等待启动
            print("⏳ 等待WebUI启动...")
            time.sleep(5)
            
            if self.webui_process.poll() is None:
                self.webui_status = 'running'
                print("✅ WebUI启动成功! 端口: 7860")
                
                if auto_open:
                    webbrowser.open("http://localhost:7860")
                
                return True
            else:
                self.webui_status = 'failed'
                print("❌ WebUI启动失败")
                return False
                
        except Exception as e:
            print(f"❌ WebUI启动失败: {e}")
            self.webui_status = 'failed'
            return False
    
    def stop_comfyui(self) -> bool:
        """停止ComfyUI"""
        try:
            if self.comfyui_process and self.comfyui_process.poll() is None:
                self.comfyui_process.terminate()
                self.comfyui_process.wait(timeout=10)
                self.comfyui_process = None
            
            self.comfyui_status = 'stopped'
            print("🛑 ComfyUI已停止")
            return True
            
        except Exception as e:
            print(f"❌ 停止ComfyUI失败: {e}")
            return False
    
    def stop_webui(self) -> bool:
        """停止WebUI"""
        try:
            if self.webui_process and self.webui_process.poll() is None:
                self.webui_process.terminate()
                self.webui_process.wait(timeout=10)
                self.webui_process = None
            
            self.webui_status = 'stopped'
            print("🛑 WebUI已停止")
            return True
            
        except Exception as e:
            print(f"❌ 停止WebUI失败: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取ComfyUI和WebUI状态"""
        return {
            'comfyui': {
                'status': self.comfyui_status,
                'path': str(self.comfyui_path),
                'running': self.comfyui_process and self.comfyui_process.poll() is None
            },
            'webui': {
                'status': self.webui_status,
                'path': str(self.webui_path),
                'running': self.webui_process and self.webui_process.poll() is None
            },
            'venv_path': str(self.venv_path),
            'project_root': str(self.project_root)
        }
    
    def setup_all(self) -> bool:
        """一键设置所有组件（虚拟环境 + ComfyUI + WebUI）"""
        print("🔧 开始一键设置所有组件...")
        
        # 这里可以实现完整的设置流程
        # 1. 创建/检查虚拟环境
        # 2. 安装ComfyUI
        # 3. 安装WebUI
        # 4. 设置配置文件
        
        return True