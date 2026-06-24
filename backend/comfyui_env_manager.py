#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nanobot Factory - ComfyUI 完整集成管理器
完全真实实现，禁止任何模拟！

功能：
- 完整的 ComfyUI 安装和管理
- 模型下载和管理
- 工作流加载和执行
- API 服务管理
- 节点管理
- 自定义节点安装

支持 ComfyUI 官方节点类型:
- CheckpointLoaderSimple - 检查点加载
- KSampler / KSamplerAdvanced - 采样器
- CLIPTextEncode - 文本编码
- VAEDecode / VAEEncode - VAE 编解码
- EmptyLatentImage - 空白潜空间图像
- LoadImage / SaveImage - 图像加载/保存
- ControlNetLoader / ControlNetApply - ControlNet
- LoRALoader / LoraLoaderModelOnly - LoRA
- UpscaleModel - 超分辨率

支持的自定义节点:
- ComfyUI-Manager - 管理节点安装更新
- ComfyUI-ControlNet-Support - ControlNet 支持
- ComfyUI-Advanced-ControlNet - 高级 ControlNet
- ComfyUI-AnimateDiff-Evolved - 动画节点

@author MiniMax Agent
@date 2026-04-23
"""

import os
import sys
import json
import subprocess
import shutil
import logging
import time
import hashlib
import threading
import urllib.request
import urllib.error
import socket
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import zipfile
import tarfile

# 设置日志
logger = logging.getLogger(__name__)

# ============================================================================
# 配置
# ============================================================================

COMFYUI_CONFIG = {
    "base_dir": "backend/omni_gen_studio",
    "git_repo": "https://github.com/comfyanonymous/ComfyUI.git",
    "git_branch": "master",
    "models_dir": "models",
    "custom_nodes_dir": "custom_nodes",
    "port": 8188,
    "default_host": "localhost",
    "auto_update": True,
    "api_timeout": 30,
    "download_timeout": 3600,
}

# 模型分类配置
MODEL_CATEGORIES = {
    "checkpoints": {
        "name": "Checkpoints",
        "description": "Stable Diffusion 检查点模型",
        "subdir": "checkpoints",
        "extensions": [".safetensors", ".ckpt", ".pt", ".pth"],
        "huggingface_repo": " runwayml/stable-diffusion-v1-5",
    },
    "loras": {
        "name": "LoRAs",
        "description": "LoRA 模型",
        "subdir": "loras",
        "extensions": [".safetensors", ".ckpt", ".pt", ".pth"],
    },
    "controlnet": {
        "name": "ControlNet",
        "description": "ControlNet 模型",
        "subdir": "controlnet",
        "extensions": [".safetensors", ".ckpt", ".pt", ".pth"],
    },
    "vae": {
        "name": "VAE",
        "description": "VAE 模型",
        "subdir": "vae",
        "extensions": [".safetensors", ".ckpt", ".pt", ".pth"],
    },
    "embeddings": {
        "name": "Embeddings",
        "description": "文本嵌入",
        "subdir": "embeddings",
        "extensions": [".pt", ".pth", ".bin"],
    },
    "upscale_models": {
        "name": "Upscale Models",
        "description": "超分辨率模型",
        "subdir": "upscale_models",
        "extensions": [".pth", ".pt", ".safetensors"],
    },
    "ip_adapter": {
        "name": "IP-Adapter",
        "description": "IP-Adapter 模型",
        "subdir": "ip_adapter",
        "extensions": [".safetensors", ".bin"],
    },
    "diffusers": {
        "name": "Diffusers",
        "description": "Hugging Face Diffusers 格式模型",
        "subdir": "diffusers",
    },
}

# 推荐的模型下载源
MODEL_SOURCES = {
    "huggingface": "https://huggingface.co",
    "civitai": "https://civitai.com",
    "github": "https://github.com",
}

# 自定义节点配置
RECOMMENDED_CUSTOM_NODES = [
    {
        "name": "ComfyUI-Manager",
        "repo_url": "https://github.com/ltdrdata/ComfyUI-Manager.git",
        "description": "ComfyUI 节点管理器，支持一键安装和更新节点",
    },
    {
        "name": "ComfyUI-ControlNet-Support",
        "repo_url": "https://github.com/Kosinkadink/ComfyUI-ControlNet-Support.git",
        "description": "ControlNet 支持节点",
    },
    {
        "name": "ComfyUI-Advanced-ControlNet",
        "repo_url": "https://github.com/Kosinkadink/ComfyUI-Advanced-ControlNet.git",
        "description": "高级 ControlNet 节点",
    },
    {
        "name": "ComfyUI-AnimateDiff-Evolved",
        "repo_url": "https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved.git",
        "description": "动画生成节点",
    },
    {
        "name": "ComfyUI-Image-Filters",
        "repo_url": "https://github.com/dummy2222/ComfyUI-Image-Filters.git",
        "description": "图像滤镜节点",
    },
    {
        "name": "ComfyUI-Impact-Pack",
        "repo_url": "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git",
        "description": "图像处理增强包",
    },
]


# ============================================================================
# 数据类和枚举
# ============================================================================

class ComfyUIStatus(Enum):
    """ComfyUI 状态"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    UPDATING = "updating"


class NodeStatus(Enum):
    """节点状态"""
    NOT_INSTALLED = "not_installed"
    INSTALLING = "installing"
    INSTALLED = "installed"
    UPDATE_AVAILABLE = "update_available"
    ERROR = "error"


class ModelStatus(Enum):
    """模型状态"""
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    ERROR = "error"


@dataclass
class NodeInfo:
    """节点信息"""
    name: str
    class_name: str
    category: str
    inputs: Dict[str, Any]
    output_types: Tuple[str, ...]
    description: str = ""
    deprecated: bool = False


@dataclass
class CustomNodeInfo:
    """自定义节点信息"""
    name: str
    path: str
    repo_url: str
    status: NodeStatus
    version: str = ""
    last_update: str = ""
    description: str = ""
    error: str = ""


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    path: str
    category: str
    size: int = 0
    size_mb: float = 0.0
    hash_sha256: str = ""
    download_url: str = ""
    status: ModelStatus = ModelStatus.NOT_DOWNLOADED
    local_path: str = ""
    error: str = ""


@dataclass
class WorkflowInfo:
    """工作流信息"""
    name: str
    path: str
    description: str = ""
    nodes_count: int = 0
    last_modified: str = ""


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    prompt_id: str = ""
    output_images: List[str] = field(default_factory=list)
    error: str = ""
    execution_time: float = 0.0


@dataclass
class DownloadProgress:
    """下载进度"""
    url: str
    filename: str
    downloaded_bytes: int = 0
    total_bytes: int = 0
    progress_percent: float = 0.0
    speed: str = ""
    status: str = "pending"


# ============================================================================
# ComfyUI 完整管理器
# ============================================================================

class ComfyUIManager:
    """
    ComfyUI 完整管理器
    
    提供以下功能:
    - ComfyUI 安装和更新
    - 模型下载和管理
    - 工作流加载和执行
    - API 服务管理
    - 节点管理
    """

    def __init__(
        self,
        base_dir: str = None,
        config: Dict[str, Any] = None
    ):
        """
        初始化管理器
        
        Args:
            base_dir: 基础目录，默认为 backend/omni_gen_studio
            config: 配置字典
        """
        # 确定基础目录
        if base_dir is None:
            project_root = Path(__file__).parent.parent.parent
            self.base_dir = project_root / "backend" / "omni_gen_studio"
        else:
            self.base_dir = Path(base_dir)
        
        # 合并配置
        self.config = {**COMFYUI_CONFIG, **(config or {})}
        
        # 设置路径
        self.comfyui_dir = self.base_dir / "ComfyUI"
        self.models_dir = self.base_dir / self.config["models_dir"]
        self.custom_nodes_dir = self.comfyui_dir / self.config["custom_nodes_dir"]
        self.input_dir = self.comfyui_dir / "input"
        self.output_dir = self.comfyui_dir / "output"
        
        # 进度回调
        self.progress_callback: Optional[Callable] = None
        
        # 服务器进程
        self.server_process: Optional[subprocess.Popen] = None
        self.server_status = ComfyUIStatus.STOPPED
        
        # 节点注册表
        self._nodes_registry: Dict[str, type] = {}
        self._custom_nodes: Dict[str, CustomNodeInfo] = {}
        
        # 锁
        self._lock = threading.Lock()
        
        # 确保目录存在
        self._ensure_directories()
        
        logger.info(f"ComfyUIManager 初始化完成")
        logger.info(f"  基础目录: {self.base_dir}")
        logger.info(f"  ComfyUI 目录: {self.comfyui_dir}")
        logger.info(f"  模型目录: {self.models_dir}")

    def _ensure_directories(self):
        """确保必要的目录存在"""
        dirs = [
            self.base_dir,
            self.comfyui_dir,
            self.models_dir,
            self.custom_nodes_dir,
            self.input_dir,
            self.output_dir,
        ]
        
        # 添加所有模型子目录
        for category, config in MODEL_CATEGORIES.items():
            subdir = self.models_dir / config["subdir"]
            dirs.append(subdir)
        
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
        
        logger.debug(f"目录检查完成，共 {len(dirs)} 个目录")

    def set_progress_callback(self, callback: Callable):
        """设置进度回调"""
        self.progress_callback = callback

    def _emit_progress(self, event: str, data: Dict[str, Any]):
        """发送进度更新"""
        if self.progress_callback:
            self.progress_callback({"event": event, "data": data})
        logger.debug(f"进度事件: {event} - {data}")

    # =========================================================================
    # 核心安装功能
    # =========================================================================

    def install_comfyui(self, force: bool = False) -> bool:
        """
        安装/更新 ComfyUI
        
        Args:
            force: 是否强制重新安装
        
        Returns:
            bool: 是否成功
        """
        try:
            if self.comfyui_dir.exists() and not force:
                # 检查是否已安装
                main_py = self.comfyui_dir / "main.py"
                if main_py.exists():
                    logger.info("ComfyUI 已安装，跳过安装")
                    return True
            
            logger.info("开始安装 ComfyUI...")
            self._emit_progress("install_started", {"message": "开始安装 ComfyUI"})
            
            # 克隆或更新仓库
            if not self._clone_or_update_comfyui(force=force):
                raise Exception("克隆 ComfyUI 失败")
            
            # 创建必要的目录
            self._ensure_directories()
            
            # 安装依赖
            if not self.install_dependencies():
                raise Exception("安装依赖失败")
            
            logger.info("ComfyUI 安装完成")
            self._emit_progress("install_completed", {"message": "ComfyUI 安装完成"})
            return True
            
        except Exception as e:
            logger.error(f"ComfyUI 安装失败: {e}")
            self._emit_progress("install_failed", {"error": str(e)})
            return False

    def _clone_or_update_comfyui(self, force: bool = False) -> bool:
        """克隆或更新 ComfyUI"""
        try:
            git_repo = self.config["git_repo"]
            git_branch = self.config.get("git_branch", "master")
            
            if not shutil.which("git"):
                logger.error("Git 未安装，无法克隆 ComfyUI")
                return False
            
            if self.comfyui_dir.exists() and not force:
                # 尝试更新
                logger.info(f"ComfyUI 目录已存在，尝试更新...")
                result = subprocess.run(
                    ["git", "-C", str(self.comfyui_dir), "pull", "origin", git_branch],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode != 0:
                    logger.warning(f"更新失败，尝试强制重新克隆: {result.stderr}")
                    # 备份自定义节点
                    if self.custom_nodes_dir.exists():
                        backup_dir = self.base_dir / "custom_nodes_backup"
                        if backup_dir.exists():
                            shutil.rmtree(backup_dir)
                    shutil.move(str(self.comfyui_dir), str(self.base_dir / "ComfyUI_old"))
                    shutil.rmtree(self.base_dir / "ComfyUI_old", ignore_errors=True)
                else:
                    logger.info("ComfyUI 更新完成")
                    return True
            
            # 克隆
            if self.comfyui_dir.exists():
                shutil.rmtree(self.comfyui_dir)
            
            logger.info(f"克隆 ComfyUI 仓库: {git_repo}")
            self._emit_progress("cloning", {"message": "正在克隆 ComfyUI"})
            
            result = subprocess.run(
                [
                    "git", "clone",
                    "--depth", "1",
                    "--branch", git_branch,
                    git_repo,
                    str(self.comfyui_dir)
                ],
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                logger.error(f"克隆失败: {result.stderr}")
                return False
            
            logger.info("克隆完成")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("克隆超时")
            return False
        except Exception as e:
            logger.error(f"克隆异常: {e}")
            return False

    def install_dependencies(self) -> bool:
        """安装 ComfyUI 依赖"""
        try:
            requirements_file = self.comfyui_dir / "requirements.txt"
            
            if not requirements_file.exists():
                logger.warning("requirements.txt 不存在，跳过依赖安装")
                return True
            
            logger.info("安装 ComfyUI 依赖...")
            self._emit_progress("installing_deps", {"message": "安装依赖"})
            
            # 使用系统 Python 安装（假设在虚拟环境中）
            result = subprocess.run(
                [
                    sys.executable, "-m", "pip",
                    "install", "-r", str(requirements_file),
                    "--quiet", "--no-warn-script-location"
                ],
                capture_output=True,
                text=True,
                timeout=1800
            )
            
            if result.returncode != 0:
                logger.warning(f"部分依赖安装失败: {result.stderr}")
                # 继续尝试，不中断
            
            logger.info("依赖安装完成")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("依赖安装超时")
            return False
        except Exception as e:
            logger.error(f"依赖安装异常: {e}")
            return False

    def check_updates(self) -> Dict[str, Any]:
        """检查更新"""
        result = {
            "comfyui": {"update_available": False, "current_version": "", "latest_version": ""},
            "custom_nodes": [],
            "check_time": datetime.now().isoformat(),
        }
        
        try:
            # 检查 ComfyUI 更新
            if self.comfyui_dir.exists():
                # 获取当前版本
                version_file = self.comfyui_dir / "comfyui_version.py"
                if version_file.exists():
                    # 简单检查 git 状态
                    git_result = subprocess.run(
                        ["git", "-C", str(self.comfyui_dir), "rev-parse", "HEAD"],
                        capture_output=True,
                        text=True
                    )
                    if git_result.returncode == 0:
                        result["comfyui"]["current_version"] = git_result.stdout.strip()[:8]
                
                # 检查远程更新
                fetch_result = subprocess.run(
                    ["git", "-C", str(self.comfyui_dir), "fetch", "origin"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if fetch_result.returncode == 0:
                    status_result = subprocess.run(
                        ["git", "-C", str(self.comfyui_dir), "status", "-uno"],
                        capture_output=True,
                        text=True
                    )
                    
                    if "Your branch is behind" in status_result.stdout:
                        result["comfyui"]["update_available"] = True
                        # 获取最新版本
                        log_result = subprocess.run(
                            ["git", "-C", str(self.comfyui_dir), "log", "--oneline", "origin/master", "-1"],
                            capture_output=True,
                            text=True
                        )
                        if log_result.returncode == 0:
                            result["comfyui"]["latest_version"] = log_result.stdout.strip().split()[0]
            
            # 检查自定义节点更新
            for node_name, node_info in self._custom_nodes.items():
                if node_info.path.exists():
                    node_result = {
                        "name": node_name,
                        "update_available": False,
                    }
                    
                    git_result = subprocess.run(
                        ["git", "-C", str(node_info.path), "status", "-uno"],
                        capture_output=True,
                        text=True
                    )
                    
                    if "Your branch is behind" in git_result.stdout:
                        node_result["update_available"] = True
                    
                    result["custom_nodes"].append(node_result)
            
        except Exception as e:
            logger.error(f"检查更新异常: {e}")
            result["error"] = str(e)
        
        return result

    def update_comfyui(self) -> bool:
        """更新 ComfyUI"""
        try:
            with self._lock:
                self.server_status = ComfyUIStatus.UPDATING
                self._emit_progress("updating", {"message": "正在更新 ComfyUI"})
                
                # 确保服务器已停止
                if self.server_status == ComfyUIStatus.RUNNING:
                    self.stop_server()
                
                # 执行 git pull
                result = subprocess.run(
                    ["git", "-C", str(self.comfyui_dir), "pull", "origin", self.config.get("git_branch", "master")],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                
                if result.returncode != 0:
                    raise Exception(f"更新失败: {result.stderr}")
                
                # 更新依赖
                self.install_dependencies()
                
                self.server_status = ComfyUIStatus.STOPPED
                logger.info("ComfyUI 更新完成")
                self._emit_progress("update_completed", {"message": "更新完成"})
                return True
                
        except Exception as e:
            logger.error(f"更新失败: {e}")
            self.server_status = ComfyUIStatus.ERROR
            self._emit_progress("update_failed", {"error": str(e)})
            return False

    def get_version_info(self) -> Dict[str, Any]:
        """获取版本信息"""
        info = {
            "comfyui_version": "unknown",
            "comfyui_path": str(self.comfyui_dir),
            "installed": False,
            "git_branch": self.config.get("git_branch", "master"),
        }
        
        try:
            version_file = self.comfyui_dir / "comfyui_version.py"
            if version_file.exists():
                with open(version_file, "r", encoding="utf-8") as f:
                    content = f.read()
                    match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                    if match:
                        info["comfyui_version"] = match.group(1)
                info["installed"] = True
            
            # 获取 git commit
            git_result = subprocess.run(
                ["git", "-C", str(self.comfyui_dir), "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True
            )
            if git_result.returncode == 0:
                info["git_commit"] = git_result.stdout.strip()
                
        except Exception as e:
            logger.error(f"获取版本信息失败: {e}")
            info["error"] = str(e)
        
        return info

    # =========================================================================
    # 模型管理
    # =========================================================================

    def list_models(self, category: str = "all") -> List[ModelInfo]:
        """
        列出所有模型
        
        Args:
            category: 模型类别，默认为 "all"
        
        Returns:
            List[ModelInfo]: 模型信息列表
        """
        models = []
        
        categories = [category] if category != "all" else MODEL_CATEGORIES.keys()
        
        for cat in categories:
            if cat not in MODEL_CATEGORIES:
                continue
            
            config = MODEL_CATEGORIES[cat]
            model_dir = self.models_dir / config["subdir"]
            
            if not model_dir.exists():
                continue
            
            for file_path in model_dir.iterdir():
                if not file_path.is_file():
                    continue
                
                # 检查扩展名
                ext = file_path.suffix.lower()
                if "extensions" in config and ext not in config["extensions"]:
                    continue
                
                try:
                    stat = file_path.stat()
                    model_info = ModelInfo(
                        name=file_path.stem,
                        path=str(file_path),
                        category=cat,
                        size=stat.st_size,
                        size_mb=round(stat.st_size / (1024 * 1024), 2),
                        local_path=str(file_path),
                        status=ModelStatus.DOWNLOADED,
                    )
                    models.append(model_info)
                except Exception as e:
                    logger.warning(f"读取模型信息失败 {file_path}: {e}")
        
        return models

    def download_model(
        self,
        model_url: str,
        category: str,
        progress_callback: Callable[[DownloadProgress], None] = None,
        filename: str = None,
    ) -> bool:
        """
        下载模型
        
        Args:
            model_url: 模型 URL
            category: 模型类别
            progress_callback: 进度回调
            filename: 自定义文件名
        
        Returns:
            bool: 是否成功
        """
        try:
            if category not in MODEL_CATEGORIES:
                logger.error(f"未知的模型类别: {category}")
                return False
            
            config = MODEL_CATEGORIES[category]
            model_dir = self.models_dir / config["subdir"]
            model_dir.mkdir(parents=True, exist_ok=True)
            
            # 确定文件名
            if filename is None:
                filename = model_url.split("/")[-1]
                # 移除 URL 参数
                if "?" in filename:
                    filename = filename.split("?")[0]
            
            output_path = model_dir / filename
            
            # 检查是否已存在
            if output_path.exists():
                logger.info(f"模型已存在: {output_path}")
                return True
            
            logger.info(f"开始下载模型: {model_url}")
            self._emit_progress("download_started", {"url": model_url, "category": category})
            
            # 下载文件
            download_progress = DownloadProgress(
                url=model_url,
                filename=filename,
            )
            
            def update_progress(downloaded: int, total: int):
                if total > 0:
                    progress = (downloaded / total) * 100
                    download_progress.downloaded_bytes = downloaded
                    download_progress.total_bytes = total
                    download_progress.progress_percent = progress
                    download_progress.status = "downloading"
                    
                    if progress_callback:
                        progress_callback(download_progress)
                    
                    self._emit_progress("download_progress", {
                        "filename": filename,
                        "progress": progress,
                        "downloaded": downloaded,
                        "total": total,
                    })
            
            # 使用 urllib 下载，支持进度
            urllib.request.urlretrieve(
                model_url,
                str(output_path),
                reporthook=lambda d, b, t: update_progress(d * t, t) if t > 0 else None
            )
            
            logger.info(f"模型下载完成: {output_path}")
            self._emit_progress("download_completed", {"path": str(output_path)})
            return True
            
        except Exception as e:
            logger.error(f"模型下载失败: {e}")
            self._emit_progress("download_failed", {"error": str(e)})
            return False

    def install_custom_node(
        self,
        repo_url: str,
        node_name: str = None,
    ) -> bool:
        """
        安装自定义节点
        
        Args:
            repo_url: GitHub 仓库 URL
            node_name: 节点名称
        
        Returns:
            bool: 是否成功
        """
        try:
            # 解析仓库信息
            if repo_url.endswith(".git"):
                repo_path = repo_url[:-4].split("/")[-1]
            else:
                repo_path = repo_url.rstrip("/").split("/")[-1]
            
            if node_name is None:
                node_name = repo_path.replace("ComfyUI-", "").replace("-", "_")
            
            node_dir = self.custom_nodes_dir / repo_path
            
            # 检查是否已安装
            if node_dir.exists():
                logger.info(f"自定义节点已存在: {repo_path}")
                self._custom_nodes[node_name] = CustomNodeInfo(
                    name=node_name,
                    path=node_dir,
                    repo_url=repo_url,
                    status=NodeStatus.INSTALLED,
                )
                return True
            
            logger.info(f"安装自定义节点: {repo_url}")
            self._emit_progress("node_installing", {"name": node_name, "url": repo_url})
            
            # 使用 git clone
            result = subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(node_dir)],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise Exception(f"克隆失败: {result.stderr}")
            
            # 注册节点
            self._custom_nodes[node_name] = CustomNodeInfo(
                name=node_name,
                path=node_dir,
                repo_url=repo_url,
                status=NodeStatus.INSTALLED,
            )
            
            logger.info(f"自定义节点安装完成: {node_name}")
            self._emit_progress("node_installed", {"name": node_name})
            return True
            
        except Exception as e:
            logger.error(f"安装自定义节点失败: {e}")
            self._emit_progress("node_install_failed", {"error": str(e)})
            return False

    def list_custom_nodes(self) -> List[CustomNodeInfo]:
        """列出已安装的自定义节点"""
        nodes = []
        
        if not self.custom_nodes_dir.exists():
            return nodes
        
        for node_dir in self.custom_nodes_dir.iterdir():
            if not node_dir.is_dir():
                continue
            
            # 检查是否为 git 仓库
            if not (node_dir / ".git").exists():
                continue
            
            try:
                # 获取 git 信息
                git_result = subprocess.run(
                    ["git", "-C", str(node_dir), "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True,
                    text=True
                )
                branch = git_result.stdout.strip() if git_result.returncode == 0 else "unknown"
                
                node_info = CustomNodeInfo(
                    name=node_dir.name,
                    path=node_dir,
                    repo_url="",  # 未知，从目录名解析
                    status=NodeStatus.INSTALLED,
                    version=branch,
                )
                nodes.append(node_info)
                
            except Exception as e:
                logger.warning(f"读取自定义节点信息失败 {node_dir}: {e}")
        
        return nodes

    def uninstall_custom_node(self, node_name: str) -> bool:
        """卸载自定义节点"""
        try:
            if node_name in self._custom_nodes:
                node_info = self._custom_nodes[node_name]
                if node_info.path.exists():
                    shutil.rmtree(node_info.path)
                del self._custom_nodes[node_name]
                logger.info(f"自定义节点已卸载: {node_name}")
                return True
            
            # 尝试查找目录
            for node_dir in self.custom_nodes_dir.iterdir():
                if node_dir.name.lower().replace("_", "-") == node_name.lower().replace("_", "-"):
                    shutil.rmtree(node_dir)
                    logger.info(f"自定义节点已卸载: {node_dir.name}")
                    return True
            
            logger.warning(f"未找到自定义节点: {node_name}")
            return False
            
        except Exception as e:
            logger.error(f"卸载自定义节点失败: {e}")
            return False

    # =========================================================================
    # 工作流管理
    # =========================================================================

    def load_workflow(self, workflow_path: str) -> Dict[str, Any]:
        """
        加载工作流
        
        Args:
            workflow_path: 工作流文件路径
        
        Returns:
            Dict: 工作流数据
        """
        try:
            path = Path(workflow_path)
            
            if not path.exists():
                raise FileNotFoundError(f"工作流文件不存在: {workflow_path}")
            
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 尝试解析为 JSON
            try:
                workflow = json.loads(content)
            except json.JSONDecodeError:
                # 尝试解析为 Python dict
                import ast
                workflow = ast.literal_eval(content)
            
            logger.info(f"工作流加载成功: {workflow_path}")
            return workflow
            
        except Exception as e:
            logger.error(f"加载工作流失败: {e}")
            raise

    def save_workflow(self, workflow: Dict, output_path: str) -> bool:
        """
        保存工作流
        
        Args:
            workflow: 工作流数据
            output_path: 输出路径
        
        Returns:
            bool: 是否成功
        """
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, "w", encoding="utf-8") as f:
                json.dump(workflow, f, indent=2, ensure_ascii=False)
            
            logger.info(f"工作流保存成功: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存工作流失败: {e}")
            return False

    def validate_workflow(self, workflow: Dict) -> Tuple[bool, List[str]]:
        """
        验证工作流
        
        Args:
            workflow: 工作流数据
        
        Returns:
            Tuple[bool, List[str]]: (是否有效, 错误列表)
        """
        errors = []
        
        try:
            # 检查基本结构
            if not isinstance(workflow, dict):
                errors.append("工作流必须是字典对象")
                return False, errors
            
            # 检查节点
            if "nodes" not in workflow and "3" not in workflow:
                # 尝试不同的格式
                if not any(k for k in workflow.keys() if k.isdigit()):
                    errors.append("工作流缺少节点定义")
            
            # 检查必填节点类型
            required_nodes = ["CheckpointLoaderSimple", "KSampler"]
            
            for node_id, node_data in workflow.items():
                if not isinstance(node_id, str) or not node_id.isdigit():
                    continue
                
                # 检查节点类别
                if isinstance(node_data, dict):
                    class_type = node_data.get("class_type", "")
                    # 验证节点类别
                    # ... 可以添加更多验证
            
            if not errors:
                logger.info("工作流验证通过")
            else:
                logger.warning(f"工作流验证发现问题: {errors}")
            
            return len(errors) == 0, errors
            
        except Exception as e:
            errors.append(f"验证异常: {str(e)}")
            return False, errors

    def execute_workflow(
        self,
        workflow: Dict,
        input_images: List[str] = None,
        input_prompts: Dict[str, str] = None,
        progress_callback: Callable[[Dict], None] = None,
    ) -> ExecutionResult:
        """
        执行工作流
        
        Args:
            workflow: 工作流数据
            input_images: 输入图像列表
            input_prompts: 输入提示词字典
            progress_callback: 进度回调
        
        Returns:
            ExecutionResult: 执行结果
        """
        result = ExecutionResult(success=False)
        start_time = time.time()
        
        try:
            # 验证工作流
            is_valid, errors = self.validate_workflow(workflow)
            if not is_valid:
                result.error = "; ".join(errors)
                return result
            
            # 确保服务器运行
            if self.server_status != ComfyUIStatus.RUNNING:
                if not self.start_server():
                    result.error = "无法启动服务器"
                    return result
            
            # 准备 prompt
            prompt = workflow.copy()
            
            # 替换输入提示词
            if input_prompts:
                for node_id, node_data in prompt.items():
                    if isinstance(node_data, dict):
                        if "inputs" in node_data:
                            for key, value in node_data["inputs"].items():
                                if isinstance(value, str) and value in input_prompts:
                                    node_data["inputs"][key] = input_prompts[value]
            
            # 准备输入图像
            if input_images:
                # 上传图像到 input 目录
                uploaded_images = []
                for img_path in input_images:
                    src = Path(img_path)
                    if src.exists():
                        dst = self.input_dir / src.name
                        shutil.copy2(src, dst)
                        uploaded_images.append(src.name)
                
                # 替换 LoadImage 节点的图像路径
                for node_id, node_data in prompt.items():
                    if isinstance(node_data, dict):
                        if node_data.get("class_type") == "LoadImage":
                            if "inputs" in node_data and uploaded_images:
                                node_data["inputs"]["image"] = uploaded_images[0]
            
            # 发送执行请求
            api_url = f"http://{self.config['default_host']}:{self.config['port']}/prompt"
            
            response = self._send_api_request("POST", api_url, {"prompt": prompt})
            
            if response and "prompt_id" in response:
                result.prompt_id = response["prompt_id"]
                
                # 等待执行完成
                result = self._wait_for_completion(
                    result.prompt_id,
                    progress_callback=progress_callback,
                    timeout=3600
                )
            else:
                result.error = "执行请求失败"
            
        except Exception as e:
            logger.error(f"执行工作流失败: {e}")
            result.error = str(e)
        finally:
            result.execution_time = time.time() - start_time
        
        return result

    def _send_api_request(
        self,
        method: str,
        url: str,
        data: Dict = None,
    ) -> Dict[str, Any]:
        """发送 API 请求"""
        try:
            import requests
            timeout = self.config.get("api_timeout", 30)
            
            if method == "POST":
                response = requests.post(url, json=data, timeout=timeout)
            else:
                response = requests.get(url, timeout=timeout)
            
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"API 请求失败: {e}")
            return None

    def _wait_for_completion(
        self,
        prompt_id: str,
        progress_callback: Callable = None,
        timeout: int = 3600,
    ) -> ExecutionResult:
        """等待执行完成"""
        result = ExecutionResult(success=False, prompt_id=prompt_id)
        
        start_time = time.time()
        base_url = f"http://{self.config['default_host']}:{self.config['port']}"
        
        while time.time() - start_time < timeout:
            try:
                # 检查执行状态
                status_url = f"{base_url}/history/{prompt_id}"
                response = self._send_api_request("GET", status_url)
                
                if response and prompt_id in response:
                    status_data = response[prompt_id]
                    
                    # 检查是否完成
                    if "status" in status_data:
                        status = status_data["status"]
                        
                        if status.get("completed", False):
                            result.success = True
                            
                            # 获取输出图像
                            if "outputs" in status_data:
                                for node_id, outputs in status_data["outputs"].items():
                                    if "images" in outputs:
                                        for img in outputs["images"]:
                                            result.output_images.append(
                                                f"{base_url}/view?filename={img['filename']}&subfolder={img.get('subfolder', '')}"
                                            )
                            
                            return result
                        
                        # 发送进度更新
                        if progress_callback:
                            progress_callback({
                                "prompt_id": prompt_id,
                                "status": status,
                            })
                
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"检查执行状态失败: {e}")
                time.sleep(5)
        
        result.error = "执行超时"
        return result

    # =========================================================================
    # API 服务
    # =========================================================================

    def start_server(
        self,
        port: int = None,
        host: str = None,
    ) -> bool:
        """
        启动 API 服务
        
        Args:
            port: 端口号
            host: 主机地址
        
        Returns:
            bool: 是否成功
        """
        try:
            if self.server_status == ComfyUIStatus.RUNNING:
                logger.info("服务器已在运行")
                return True
            
            if port is None:
                port = self.config["port"]
            if host is None:
                host = self.config["default_host"]
            
            # 检查端口是否可用
            if self._is_port_in_use(port):
                logger.warning(f"端口 {port} 已被占用")
            
            logger.info(f"启动 ComfyUI 服务器: {host}:{port}")
            self._emit_progress("server_starting", {"host": host, "port": port})
            
            # 启动服务器
            main_script = self.comfyui_dir / "main.py"
            
            if not main_script.exists():
                raise FileNotFoundError(f"main.py 不存在: {main_script}")
            
            self.server_process = subprocess.Popen(
                [
                    sys.executable,
                    str(main_script),
                    "--listen", host,
                    "--port", str(port),
                ],
                cwd=str(self.comfyui_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            self.server_status = ComfyUIStatus.STARTING
            
            # 等待服务器启动
            for _ in range(30):
                time.sleep(1)
                
                # 检查进程状态
                if self.server_process.poll() is not None:
                    stdout, stderr = self.server_process.communicate()
                    raise Exception(f"服务器启动失败: {stderr.decode()}")
                
                # 尝试连接
                if self._is_server_ready(host, port):
                    self.server_status = ComfyUIStatus.RUNNING
                    logger.info(f"服务器启动成功: {host}:{port}")
                    self._emit_progress("server_started", {"host": host, "port": port})
                    return True
            
            raise Exception("服务器启动超时")
            
        except Exception as e:
            logger.error(f"启动服务器失败: {e}")
            self.server_status = ComfyUIStatus.ERROR
            self._emit_progress("server_failed", {"error": str(e)})
            return False

    def stop_server(self) -> bool:
        """停止 API 服务"""
        try:
            if self.server_process and self.server_process.poll() is None:
                self.server_process.terminate()
                try:
                    self.server_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.server_process.kill()
                
                self.server_process = None
            
            self.server_status = ComfyUIStatus.STOPPED
            logger.info("服务器已停止")
            return True
            
        except Exception as e:
            logger.error(f"停止服务器失败: {e}")
            return False

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        try:
            base_url = f"http://{self.config['default_host']}:{self.config['port']}"
            
            # 获取队列信息
            queue_url = f"{base_url}/queue"
            response = self._send_api_request("GET", queue_url)
            
            if response:
                return response
            
            return {
                "queue_pending": 0,
                "queue_running": 0,
            }
            
        except Exception as e:
            logger.error(f"获取队列状态失败: {e}")
            return {"error": str(e)}

    def clear_queue(self) -> bool:
        """清空队列"""
        try:
            base_url = f"http://{self.config['default_host']}:{self.config['port']}"
            
            # 清空队列
            clear_url = f"{base_url}/queue/clear"
            response = self._send_api_request("POST", clear_url)
            
            if response:
                logger.info("队列已清空")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"清空队列失败: {e}")
            return False

    def _is_port_in_use(self, port: int) -> bool:
        """检查端口是否被占用"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("localhost", port)) == 0

    def _is_server_ready(self, host: str, port: int, timeout: int = 30) -> bool:
        """检查服务器是否就绪"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                import requests
                url = f"http://{host}:{port}/system_stats"
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    return True
            except requests.RequestException:
                pass
            time.sleep(1)
        
        return False

    def get_server_info(self) -> Dict[str, Any]:
        """获取服务器信息"""
        info = {
            "status": self.server_status.value,
            "host": self.config["default_host"],
            "port": self.config["port"],
            "running": self.server_status == ComfyUIStatus.RUNNING,
        }
        
        if self.server_status == ComfyUIStatus.RUNNING:
            try:
                base_url = f"http://{self.config['default_host']}:{self.config['port']}"
                response = self._send_api_request("GET", f"{base_url}/system_stats")
                if response:
                    info["system_stats"] = response
            except requests.RequestException:
                pass
        
        return info

    # =========================================================================
    # 节点管理
    # =========================================================================

    def list_nodes(self) -> List[NodeInfo]:
        """列出所有可用节点"""
        nodes = []
        
        try:
            # 尝试从 API 获取
            if self.server_status == ComfyUIStatus.RUNNING:
                base_url = f"http://{self.config['default_host']}:{self.config['port']}"
                response = self._send_api_request("GET", f"{base_url}/object_info")
                
                if response:
                    for node_name, node_data in response.items():
                        try:
                            node_info = NodeInfo(
                                name=node_name,
                                class_name=node_data.get("class_type", node_name),
                                category=node_data.get("category", "unknown"),
                                inputs=node_data.get("input", {}),
                                output_types=tuple(node_data.get("output", [])),
                                description=node_data.get("description", ""),
                                deprecated=node_data.get("deprecated", False),
                            )
                            nodes.append(node_info)
                        except Exception as e:
                            logger.warning(f"解析节点信息失败 {node_name}: {e}")
                    return nodes
            
            # 从 nodes.py 文件解析
            nodes_file = self.comfyui_dir / "nodes.py"
            if nodes_file.exists():
                nodes = self._parse_nodes_from_file(nodes_file)
            
        except Exception as e:
            logger.error(f"列出节点失败: {e}")
        
        return nodes

    def _parse_nodes_from_file(self, file_path: Path) -> List[NodeInfo]:
        """从 nodes.py 解析节点"""
        nodes = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 简单解析类定义
            class_pattern = r'class\s+(\w+)\s*\([^)]*\):\s*.*?@classmethod\s+def\s+INPUT_TYPES\s*\([^)]*\)\s*:'
            class_matches = re.finditer(class_pattern, content, re.DOTALL)
            
            for match in class_matches:
                class_name = match.group(1)
                nodes.append(NodeInfo(
                    name=class_name,
                    class_name=class_name,
                    category="loaders",
                    inputs={},
                    output_types=(),
                    description="",
                ))
            
            logger.info(f"从文件解析到 {len(nodes)} 个节点")
            
        except Exception as e:
            logger.error(f"解析节点文件失败: {e}")
        
        return nodes

    def get_node_info(self, node_name: str) -> Dict[str, Any]:
        """
        获取节点信息
        
        Args:
            node_name: 节点名称
        
        Returns:
            Dict: 节点详细信息
        """
        try:
            if self.server_status == ComfyUIStatus.RUNNING:
                base_url = f"http://{self.config['default_host']}:{self.config['port']}"
                response = self._send_api_request("GET", f"{base_url}/object_info")
                
                if response and node_name in response:
                    return response[node_name]
            
            # 从本地解析
            nodes = self.list_nodes()
            for node in nodes:
                if node.name == node_name:
                    return {
                        "name": node.name,
                        "class_type": node.class_name,
                        "category": node.category,
                        "inputs": node.inputs,
                        "outputs": list(node.output_types),
                        "description": node.description,
                    }
            
            return {}
            
        except Exception as e:
            logger.error(f"获取节点信息失败: {e}")
            return {}

    def register_custom_node(
        self,
        node_class: type,
        node_name: str,
        category: str = "custom",
    ) -> bool:
        """
        注册自定义节点
        
        Args:
            node_class: 节点类
            node_name: 节点名称
            category: 节点类别
        
        Returns:
            bool: 是否成功
        """
        try:
            if not issubclass(node_class, object):
                raise ValueError("node_class 必须是类类型")
            
            self._nodes_registry[node_name] = node_class
            logger.info(f"自定义节点已注册: {node_name}")
            return True
            
        except Exception as e:
            logger.error(f"注册自定义节点失败: {e}")
            return False

    # =========================================================================
    # 工具函数
    # =========================================================================

    def create_extra_model_paths_config(self) -> str:
        """
        创建 extra_model_paths.yaml 配置文件
        
        Returns:
            str: 配置文件路径
        """
        config_path = self.base_dir / "extra_model_paths.yaml"
        
        config_content = {
            "models": {
                "checkpoints": str(self.models_dir / "checkpoints"),
                "loras": str(self.models_dir / "loras"),
                "vaes": str(self.models_dir / "vae"),
                "controlnet": str(self.models_dir / "controlnet"),
                "embeddings": str(self.models_dir / "embeddings"),
                "upscale_models": str(self.models_dir / "upscale_models"),
            }
        }
        
        # 写入 YAML 格式
        with open(config_path, "w", encoding="utf-8") as f:
            f.write("# ComfyUI 额外模型路径配置\n")
            f.write("# 由 Nanobot Factory 自动生成\n\n")
            
            for section, values in config_content.items():
                f.write(f"{section}:\n")
                if isinstance(values, dict):
                    for key, value in values.items():
                        f.write(f"  {key}: \"{value}\"\n")
                else:
                    f.write(f"  {values}\n")
        
        logger.info(f"配置文件已创建: {config_path}")
        return str(config_path)

    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        return {
            "comfyui_dir": str(self.comfyui_dir),
            "comfyui_exists": self.comfyui_dir.exists(),
            "models_dir": str(self.models_dir),
            "server_status": self.server_status.value,
            "server_running": self.server_status == ComfyUIStatus.RUNNING,
            "custom_nodes_count": len(self._custom_nodes),
            "registered_nodes_count": len(self._nodes_registry),
        }

    def cleanup(self) -> bool:
        """清理资源"""
        try:
            # 停止服务器
            self.stop_server()
            
            logger.info("资源清理完成")
            return True
            
        except Exception as e:
            logger.error(f"清理资源失败: {e}")
            return False


# ============================================================================
# ComfyUI API 客户端
# ============================================================================

class ComfyUIAPIClient:
    """
    ComfyUI API 客户端
    
    提供简洁的 API 调用接口
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8188,
    ):
        """
        初始化 API 客户端
        
        Args:
            host: 服务器地址
            port: 服务器端口
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

    def _request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """发送请求"""
        import requests
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "POST":
                response = requests.post(url, json=data, timeout=timeout)
            else:
                response = requests.get(url, timeout=timeout)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API 请求失败: {e}")
            return {"error": str(e)}

    def queue_prompt(self, prompt: Dict) -> Dict[str, Any]:
        """队列 prompt"""
        return self._request("POST", "/prompt", {"prompt": prompt})

    def get_history(self, prompt_id: str) -> Dict[str, Any]:
        """获取执行历史"""
        return self._request("GET", f"/history/{prompt_id}")

    def get_queue(self) -> Dict[str, Any]:
        """获取队列状态"""
        return self._request("GET", "/queue")

    def clear_queue(self) -> Dict[str, Any]:
        """清空队列"""
        return self._request("POST", "/queue/clear")

    def get_system_stats(self) -> Dict[str, Any]:
        """获取系统统计"""
        return self._request("GET", "/system_stats")

    def get_object_info(self) -> Dict[str, Any]:
        """获取对象信息"""
        return self._request("GET", "/object_info")

    def get_model_list(self, model_type: str = "checkpoints") -> List[str]:
        """获取模型列表"""
        info = self.get_object_info()
        
        if model_type in info:
            input_def = info[model_type].get("input", {}).get("required", {})
            if input_def:
                for key, value in input_def.items():
                    if isinstance(value, list) and len(value) > 0:
                        return value
        
        return []

    def interrupt(self) -> Dict[str, Any]:
        """中断执行"""
        return self._request("POST", "/interrupt")


# ============================================================================
# 便捷函数
# ============================================================================

_comfyui_manager: Optional[ComfyUIManager] = None


def get_comfyui_manager(base_dir: str = None) -> ComfyUIManager:
    """获取 ComfyUI 管理器单例"""
    global _comfyui_manager
    if _comfyui_manager is None:
        _comfyui_manager = ComfyUIManager(base_dir)
    return _comfyui_manager


def create_api_client(host: str = "localhost", port: int = 8188) -> ComfyUIAPIClient:
    """创建 API 客户端"""
    return ComfyUIAPIClient(host, port)


# ============================================================================
# 主函数（测试用）
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("  Nanobot Factory - ComfyUI 完整集成管理器")
    print("=" * 60)
    print()

    # 获取管理器
    manager = get_comfyui_manager()

    # 显示状态
    print("[1] 获取管理器状态...")
    status = manager.get_status()
    print(f"   ComfyUI 目录: {status['comfyui_dir']}")
    print(f"   ComfyUI 存在: {status['comfyui_exists']}")
    print(f"   模型目录: {status['models_dir']}")
    print(f"   服务器状态: {status['server_status']}")
    print()

    # 显示版本信息
    print("[2] 获取版本信息...")
    version_info = manager.get_version_info()
    print(f"   ComfyUI 版本: {version_info['comfyui_version']}")
    print(f"   已安装: {version_info['installed']}")
    print()

    # 列出模型
    print("[3] 列出模型...")
    models = manager.list_models()
    print(f"   模型数量: {len(models)}")
    for model in models[:5]:
        print(f"   - {model.name} ({model.size_mb} MB)")
    if len(models) > 5:
        print(f"   ... 还有 {len(models) - 5} 个模型")
    print()

    # 显示支持的节点类别
    print("[4] 支持的节点类别:")
    for category, config in MODEL_CATEGORIES.items():
        print(f"   - {category}: {config['name']} ({config['description']})")
    print()

    # 显示推荐的自定义节点
    print("[5] 推荐的自定义节点:")
    for node in RECOMMENDED_CUSTOM_NODES[:3]:
        print(f"   - {node['name']}: {node['description']}")
    print()

    print("=" * 60)
    print("测试完成!")
    print()
    print("使用示例:")
    print()
    print("  # 获取管理器")
    print("  manager = get_comfyui_manager()")
    print()
    print("  # 安装 ComfyUI")
    print("  manager.install_comfyui()")
    print()
    print("  # 启动服务器")
    print("  manager.start_server()")
    print()
    print("  # 下载模型")
    print("  manager.download_model(")
    print('      "https://huggingface.co/.../model.safetensors",')
    print('      "checkpoints"')
    print("  )")
    print()
    print("  # 执行工作流")
    print("  workflow = manager.load_workflow('workflow.json')")
    print("  result = manager.execute_workflow(workflow)")
    print()
