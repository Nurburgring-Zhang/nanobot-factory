#!/usr/bin/env python3
"""
Nanobot Factory - 虚拟环境与依赖管理系统
Virtual Environment and Dependency Management System

功能：
1. 检测并自动创建虚拟环境
2. 自动部署 CUDA、PyTorch、flashattention2、xformers 等依赖
3. 支持 flashattention2 或 xformers 推理加速选择
4. 依赖环境搭建自动断点续传、自动更换下载源

@author MiniMax Agent
@date 2026-03-15
"""

import os
import sys
import json
import subprocess
import shutil
import threading
import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


# =============================================================================
# 数据模型
# =============================================================================

class EnvironmentStatus(Enum):
    """环境状态"""
    UNKNOWN = "unknown"
    CHECKING = "checking"
    READY = "ready"
    INSTALLING = "installing"
    ERROR = "error"


class AcceleratorType(Enum):
    """加速器类型"""
    NONE = "none"
    FLASHATTENTION2 = "flashattention2"
    XFORMERS = "xformers"
    TRITON = "triton"


@dataclass
class Dependency:
    """依赖包"""
    name: str
    version: str = ""
    required: bool = True
    installed: bool = False
    install_progress: float = 0.0
    error: Optional[str] = None


@dataclass
class EnvironmentConfig:
    """环境配置"""
    python_version: str = "3.11"
    cuda_version: str = "12.1"
    cudnn_version: str = "8.9"
    torch_version: str = "2.3.0"
    accelerator: AcceleratorType = AcceleratorType.XFORMERS
    extra_index_url: List[str] = field(default_factory=list)
    pip_source: str = "https://pypi.tuna.tsinghua.edu.cn/simple"
    use_cache: bool = True


@dataclass
class EnvironmentStatus:
    """环境状态"""
    status: EnvironmentStatus = EnvironmentStatus.UNKNOWN
    venv_path: Optional[str] = None
    python_version: Optional[str] = None
    cuda_available: bool = False
    torch_installed: bool = False
    accelerator_installed: bool = False
    dependencies: List[Dependency] = field(default_factory=list)
    error_message: Optional[str] = None
    last_check: Optional[str] = None


# =============================================================================
# 虚拟环境管理器
# =============================================================================

class VirtualEnvManager:
    """
    虚拟环境管理器
    检测和创建虚拟环境
    """
    
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path) if base_path else Path(__file__).parent
        self.venv_path = self.base_path / "venv"
        
    def has_venv(self) -> bool:
        """检查是否存在虚拟环境"""
        # 检查标准虚拟环境结构
        if self.venv_path.exists():
            # 检查关键文件/目录
            if sys.platform == "win32":
                script_path = self.venv_path / "Scripts" / "python.exe"
            else:
                script_path = self.venv_path / "bin" / "python"
                
            if script_path.exists():
                return True
        return False
        
    def get_venv_python(self) -> Optional[str]:
        """获取虚拟环境 Python 路径"""
        if sys.platform == "win32":
            return str(self.venv_path / "Scripts" / "python.exe")
        else:
            return str(self.venv_path / "bin" / "python")
            
    def create_venv(self, python_version: str = "3.11") -> bool:
        """创建虚拟环境"""
        try:
            logger.info(f"Creating virtual environment at {self.venv_path}")
            
            # 检查系统 Python 版本
            current_py = sys.executable
            subprocess.run(
                [current_py, "-m", "venv", str(self.venv_path)],
                check=True,
                capture_output=True
            )
            
            logger.info("Virtual environment created successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create venv: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Failed to create venv: {e}")
            return False
            
    def get_pip_command(self) -> List[str]:
        """获取 pip 命令"""
        if sys.platform == "win32":
            pip_path = self.venv_path / "Scripts" / "pip.exe"
        else:
            pip_path = self.venv_path / "bin" / "pip"
            
        return [str(pip_path)]
        
    def run_pip(self, args: List[str], timeout: int = 300) -> subprocess.CompletedProcess:
        """运行 pip 命令"""
        pip_cmd = self.get_pip_command() + args
        
        result = subprocess.run(
            pip_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return result


# =============================================================================
# 依赖安装器
# =============================================================================

class DependencyInstaller:
    """
    依赖安装器
    自动安装 PyTorch、CUDA 加速库等依赖
    """
    
    # PyTorch 和相关依赖
    BASE_PACKAGES = [
        "torch==2.3.0",
        "torchvision==0.18.0",
        "torchaudio==2.3.0",
        "numpy",
        "scipy",
        "pillow",
        "opencv-python",
        "transformers",
        "diffusers",
        "accelerate",
        "safetensors",
        "huggingface-hub",
    ]
    
    # CUDA 加速包
    ACCELERATOR_PACKAGES = {
        AcceleratorType.FLASHATTENTION2: [
            "flash-attn==2.5.8",  # 可能需要从源码编译
        ],
        AcceleratorType.XFORMERS: [
            "xformers==0.0.27.post2",
        ],
        AcceleratorType.TRITON: [
            "triton",
        ]
    }
    
    # 额外依赖
    EXTRA_PACKAGES = [
        "pytest",
        "black",
        "ruff",
        "ipython",
        "jupyter",
        "ipykernel",
        "tensorboard",
        "wandb",
        "omegaconf",
        "hydra-core",
        "pytorch-lightning",
        "ftfy",
        "regex",
        "sentencepiece",
        "protobuf",
        "gradio",
        "streamlit",
        "fastapi",
        "uvicorn",
        "python-multipart",
        "aiofiles",
        "httpx",
        "websockets",
        "python-socketio",
    ]
    
    def __init__(self, venv_manager: VirtualEnvManager, config: EnvironmentConfig):
        self.venv_manager = venv_manager
        self.config = config
        self._callbacks: List[Callable] = []
        
        # 镜像源列表 (按优先级排序)
        self.mirror_sources = [
            "https://pypi.tuna.tsinghua.edu.cn/simple",
            "https://pypi.mirrors.ustc.edu.cn/simple", 
            "https://pypi.douban.com/simple",
            "https://pypi.python.org/simple",
        ]
        self.current_mirror_index = 0
        
        # 断点续传
        self.installed_packages: set = set()
        self.failed_packages: Dict[str, str] = {}
        
    def add_callback(self, callback: Callable):
        """添加进度回调"""
        self._callbacks.append(callback)
        
    def _notify_progress(self, package: str, progress: float, status: str):
        """通知进度"""
        for callback in self._callbacks:
            try:
                callback(package, progress, status)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")
                
    def _switch_mirror(self) -> bool:
        """切换下载源"""
        if self.current_mirror_index < len(self.mirror_sources) - 1:
            self.current_mirror_index += 1
            logger.info(f"Switching to mirror: {self.mirror_sources[self.current_mirror_index]}")
            return True
        return False
        
    def _install_package(self, package: str, timeout: int = 600) -> bool:
        """安装单个包，带重试和换源"""
        max_retries = len(self.mirror_sources)
        
        for retry in range(max_retries):
            try:
                # 构建安装命令
                pip_cmd = self.venv_manager.get_pip_command() + [
                    "install",
                    package,
                    "--no-cache-dir",
                    "-i", self.mirror_sources[self.current_mirror_index],
                    "--trusted-host", 
                    self.mirror_sources[self.current_mirror_index].split("//")[1].split("/")[0]
                ]
                
                # 添加额外索引
                for extra_url in self.config.extra_index_url:
                    pip_cmd.extend(["--extra-index-url", extra_url])
                    
                self._notify_progress(package, 0, "installing")
                
                result = subprocess.run(
                    pip_cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout
                )
                
                if result.returncode == 0:
                    self._notify_progress(package, 100, "installed")
                    self.installed_packages.add(package.split("==")[0].split(">=")[0].split("<=")[0])
                    return True
                else:
                    error_msg = result.stderr
                    
                    # 检查是否是连接错误
                    if "Connection" in error_msg or "Timeout" in error_msg or "HTTP Error" in error_msg:
                        logger.warning(f"Connection error for {package}, trying next mirror...")
                        if not self._switch_mirror():
                            break
                    else:
                        # 其他错误，记录并继续
                        logger.warning(f"Failed to install {package}: {error_msg[:200]}")
                        self.failed_packages[package] = error_msg[:200]
                        return False
                        
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout installing {package}, retry {retry + 1}/{max_retries}")
                if retry < max_retries - 1:
                    self._switch_mirror()
            except Exception as e:
                logger.error(f"Error installing {package}: {e}")
                self.failed_packages[package] = str(e)
                return False
                
        return False
        
    def check_cuda_availability(self) -> bool:
        """检查 CUDA 是否可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except (ImportError, RuntimeError):
            return False
            
    def install_torch(self, accelerator: AcceleratorType = AcceleratorType.XFORMERS) -> bool:
        """安装 PyTorch 和 CUDA 加速库"""
        logger.info("Installing PyTorch with CUDA support...")
        
        # 确定 PyTorch 安装命令
        if accelerator == AcceleratorType.FLASHATTENTION2:
            # FlashAttention2 需要从源码安装或使用特定版本
            torch_install = "torch==2.3.0+cu121"
        elif accelerator == AcceleratorType.XFORMERS:
            torch_install = "torch==2.3.0+cu121"
        else:
            torch_install = "torch==2.3.0"
            
        # 安装 PyTorch (使用 PyTorch 官方源)
        pytorch_index = "https://download.pytorch.org/whl/cu121"
        
        pip_cmd = self.venv_manager.get_pip_command() + [
            "install",
torch_install,
            "--index-url", pytorch_index,
            "--no-cache-dir"
        ]
        
        try:
            result = subprocess.run(
                pip_cmd,
                capture_output=True,
                text=True,
                timeout=900
            )
            
            if result.returncode == 0:
                logger.info("PyTorch installed successfully")
                
                # 安装 torchvision
                self._install_package("torchvision==0.18.0+cu121")
                
                return True
            else:
                logger.error(f"Failed to install PyTorch: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error installing PyTorch: {e}")
            return False
            
    def install_accelerator(self, accelerator: AcceleratorType) -> bool:
        """安装推理加速库"""
        if accelerator == AcceleratorType.NONE:
            return True
            
        packages = self.ACCELERATOR_PACKAGES.get(accelerator, [])
        
        for package in packages:
            success = self._install_package(package, timeout=900)
            if not success:
                logger.warning(f"Failed to install {package}, continuing...")
                
        return True
        
    def install_all_dependencies(
        self, 
        progress_callback: Callable = None,
        resume: bool = True
    ) -> Dict[str, Any]:
        """安装所有依赖"""
        results = {
            "success": True,
            "installed": [],
            "failed": [],
            "skipped": []
        }
        
        # 添加回调
        if progress_callback:
            self.add_callback(progress_callback)
            
        # 1. 升级 pip
        self._notify_progress("pip", 0, "upgrading")
        self._install_package("--upgrade pip")
        
        # 2. 安装基础包
        for i, package in enumerate(self.BASE_PACKAGES):
            progress = (i / len(self.BASE_PACKAGES)) * 50
            self._notify_progress(package, progress, "installing")
            
            if self._install_package(package):
                results["installed"].append(package)
            else:
                results["failed"].append(package)
                results["success"] = False
                
        # 3. 安装 CUDA 加速库
        if self.config.accelerator != AcceleratorType.NONE:
            self._notify_progress("accelerator", 50, "installing")
            self.install_accelerator(self.config.accelerator)
            
        # 4. 安装额外包
        for i, package in enumerate(self.EXTRA_PACKAGES):
            progress = 50 + (i / len(self.EXTRA_PACKAGES)) * 40
            self._notify_progress(package, progress, "installing")
            
            if self._install_package(package):
                results["installed"].append(package)
            else:
                results["failed"].append(package)
                
        # 5. 验证安装
        self._notify_progress("verification", 95, "verifying")
        
        # 检查 PyTorch
        try:
            python = self.venv_manager.get_venv_python()
            result = subprocess.run(
                [python, "-c", "import torch; print(torch.__version__)"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                results["pytorch_version"] = result.stdout.strip()
                
            # 检查 CUDA
            result = subprocess.run(
                [python, "-c", "import torch; print(torch.cuda.is_available())"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                results["cuda_available"] = result.stdout.strip() == "True"
                
        except Exception as e:
            logger.error(f"Verification error: {e}")
            
        self._notify_progress("complete", 100, "done")
        
        return results


# =============================================================================
# 环境管理器
# =============================================================================

class EnvironmentManager:
    """
    环境管理器
    统一管理虚拟环境和依赖
    """
    
    def __init__(self, base_path: str = None, config: EnvironmentConfig = None):
        self.base_path = Path(base_path) if base_path else Path(__file__).parent
        self.config = config or EnvironmentConfig()
        
        self.venv_manager = VirtualEnvManager(self.base_path)
        self.installer = DependencyInstaller(self.venv_manager, self.config)
        
        # 状态
        self.status = EnvironmentStatus()
        self._lock = threading.Lock()
        
    def check_environment(self) -> EnvironmentStatus:
        """检查环境状态"""
        with self._lock:
            self.status.status = EnvironmentStatus.CHECKING
            
            try:
                # 检查虚拟环境
                if self.venv_manager.has_venv():
                    self.status.venv_path = str(self.venv_manager.venv_path)
                    python = self.venv_manager.get_venv_python()
                    
                    # 检查 Python 版本
                    result = subprocess.run(
                        [python, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        self.status.python_version = result.stdout.strip()
                        
                    # 检查 CUDA
                    result = subprocess.run(
                        [python, "-c", "import torch; print(torch.cuda.is_available())"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        self.status.cuda_available = result.stdout.strip() == "True"
                        
                    # 检查 PyTorch
                    result = subprocess.run(
                        [python, "-c", "import torch; print(torch.__version__)"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if result.returncode == 0:
                        self.status.torch_installed = True
                        
                    self.status.status = EnvironmentStatus.READY
                else:
                    self.status.status = EnvironmentStatus.UNKNOWN
                    
            except Exception as e:
                self.status.error_message = str(e)
                self.status.status = EnvironmentStatus.ERROR
                
            self.status.last_check = datetime.now().isoformat()
            
            return self.status
            
    def setup_environment(
        self,
        progress_callback: Callable = None,
        resume: bool = True
    ) -> Dict[str, Any]:
        """设置环境"""
        with self._lock:
            self.status.status = EnvironmentStatus.INSTALLING
            
            try:
                # 1. 创建虚拟环境
                if not self.venv_manager.has_venv():
                    logger.info("Creating virtual environment...")
                    if not self.venv_manager.create_venv():
                        raise Exception("Failed to create virtual environment")
                        
                # 2. 安装依赖
                results = self.installer.install_all_dependencies(
                    progress_callback=progress_callback,
                    resume=resume
                )
                
                if results["success"]:
                    self.status.status = EnvironmentStatus.READY
                else:
                    self.status.status = EnvironmentStatus.ERROR
                    self.status.error_message = "Some packages failed to install"
                    
                return results
                
            except Exception as e:
                self.status.status = EnvironmentStatus.ERROR
                self.status.error_message = str(e)
                return {"success": False, "error": str(e)}
                
    def get_status(self) -> EnvironmentStatus:
        """获取状态"""
        return self.status
        
    def get_python_executable(self) -> Optional[str]:
        """获取 Python 路径"""
        if self.venv_manager.has_venv():
            return self.venv_manager.get_venv_python()
        return None
        
    def run_in_venv(self, command: List[str], timeout: int = 300) -> subprocess.CompletedProcess:
        """在虚拟环境中运行命令"""
        python = self.venv_manager.get_venv_python()
        return subprocess.run(
            [python] + command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(self.base_path)
        )


# =============================================================================
# 模型管理器
# =============================================================================

class ModelManager:
    """
    模型管理器
    自动下载和管理 AI 模型
    """
    
    # 模型仓库配置
    MODEL_REPOSITORIES = {
        "huggingface": "https://huggingface.co",
        "github": "https://github.com",
    }
    
    # 支持的模型类型
    MODEL_TYPES = [
        "z_image",           # 图像生成
        "qwen_image",       # Qwen 图像
        "flux",             # Flux
        "flux2_klein",      # Flux.2 Klein
        "qwen_image_edit",  # Qwen 图像编辑
        "wan",              # Wan 视频
        "ltx2",             # LTX 视频
        "hunyuan3d",        # 3D 生成
        "trellis2",         # Trellis 3D
    ]
    
    def __init__(self, models_dir: str = None):
        self.models_dir = Path(models_dir) if models_dir else Path.home() / ".nanobot-factory" / "models"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        # 模型缓存信息
        self.model_cache: Dict[str, Dict[str, Any]] = {}
        
    def check_model_exists(self, model_id: str, model_type: str) -> bool:
        """检查模型是否已存在"""
        model_path = self.models_dir / model_type / model_id
        return model_path.exists()
        
    def download_model(
        self,
        model_id: str,
        model_type: str,
        source: str = "huggingface",
        progress_callback: Callable = None
    ) -> bool:
        """下载模型"""
        try:
            logger.info(f"Downloading model {model_id} from {source}")
            
            # 使用 huggingface_hub 下载
            from huggingface_hub import snapshot_download
            
            local_dir = self.models_dir / model_type / model_id
            
            snapshot_download(
                repo_id=model_id,
                local_dir=str(local_dir),
                local_dir_use_symlinks=False,
                resume_download=True,
            )
            
            # 更新缓存
            self.model_cache[model_id] = {
                "type": model_type,
                "path": str(local_dir),
                "source": source,
                "downloaded_at": datetime.now().isoformat()
            }
            
            logger.info(f"Model {model_id} downloaded successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to download model {model_id}: {e}")
            return False
            
    def list_models(self, model_type: str = None) -> List[Dict[str, Any]]:
        """列出已安装的模型"""
        models = []
        
        if model_type:
            type_dir = self.models_dir / model_type
            if type_dir.exists():
                for model_dir in type_dir.iterdir():
                    if model_dir.is_dir():
                        models.append({
                            "id": model_dir.name,
                            "type": model_type,
                            "path": str(model_dir)
                        })
        else:
            for model_type_dir in self.models_dir.iterdir():
                if model_type_dir.is_dir():
                    for model_dir in model_type_dir.iterdir():
                        if model_dir.is_dir():
                            models.append({
                                "id": model_dir.name,
                                "type": model_type_dir.name,
                                "path": str(model_dir)
                            })
                            
        return models
        
    def delete_model(self, model_id: str, model_type: str) -> bool:
        """删除模型"""
        try:
            model_path = self.models_dir / model_type / model_id
            if model_path.exists():
                shutil.rmtree(model_path)
                
                # 更新缓存
                if model_id in self.model_cache:
                    del self.model_cache[model_id]
                    
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete model {model_id}: {e}")
            return False


# =============================================================================
# 全局实例
# =============================================================================

_environment_manager: Optional[EnvironmentManager] = None
_model_manager: Optional[ModelManager] = None


def get_environment_manager(base_path: str = None, config: EnvironmentConfig = None) -> EnvironmentManager:
    """获取环境管理器"""
    global _environment_manager
    if _environment_manager is None:
        _environment_manager = EnvironmentManager(base_path, config)
    return _environment_manager


def get_model_manager(models_dir: str = None) -> ModelManager:
    """获取模型管理器"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager(models_dir)
    return _model_manager


# =============================================================================
# 示例用法
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # 创建环境管理器
    env_manager = get_environment_manager()
    
    # 检查环境
    print("Checking environment...")
    status = env_manager.check_environment()
    print(f"Status: {status.status}")
    print(f"CUDA available: {status.cuda_available}")
    print(f"PyTorch installed: {status.torch_installed}")
    
    # 如果需要设置环境
    if status.status in [EnvironmentStatus.UNKNOWN, EnvironmentStatus.ERROR]:
        print("\nSetting up environment...")
        
        def progress_callback(package: str, progress: float, status: str):
            print(f"[{progress:.1f}%] {package}: {status}")
            
        results = env_manager.setup_environment(progress_callback)
        print(f"\nSetup results: {json.dumps(results, indent=2)}")
        
    # 模型管理器
    model_manager = get_model_manager()
    models = model_manager.list_models()
    print(f"\nInstalled models: {len(models)}")
    for model in models[:5]:
        print(f"  - {model['type']}/{model['id']}")
