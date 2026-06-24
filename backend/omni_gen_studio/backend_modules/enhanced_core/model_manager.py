#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OmniGen Studio - 模型扫描与管理器
支持多种模型格式的扫描、识别和管理
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import torch

logger = logging.getLogger(__name__)


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    path: str
    type: str  # sd15, sdxl, flux, wan, ltx, svd, hunyuan3d, trellis, triposr
    format: str  # safetensors, ckpt, pt, gguf
    size: float  # MB
    architecture: str  # unet, clip, vae, t5, aio
    is_local: bool
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class ModelScanner:
    """模型扫描器"""

    # 支持的模型格式
    SUPPORTED_IMAGE_FORMATS = {
        '.safetensors': 'safetensors',
        '.ckpt': 'ckpt',
        '.pt': 'pt',
        '.pth': 'pth',
        '.bin': 'bin',
        '.gguf': 'gguf'
    }

    # 模型类型关键词
    MODEL_TYPE_KEYWORDS = {
        'sd15': ['sd15', 'stable-diffusion-v1-5', 'v1-5', 'v1.5'],
        'sdxl': ['sdxl', 'stable-diffusion-xl', 'sd-xl', 'sd_xl'],
        'sd3': ['sd3', 'stable-diffusion-3'],
        'flux': ['flux', 'flux1', 'black-forest'],
        'wan': ['wan', 'wan2', 'wan2.2'],
        'ltx': ['ltx', 'ltx-video'],
        'svd': ['svd', 'stable-video', 'video-diffusion'],
        'hunyuan3d': ['hunyuan', 'hunyuan3d'],
        'trellis': ['trellis', 'triposr'],
        'triposr': ['triposr', 'tripo']
    }

    # 架构类型关键词
    ARCHITECTURE_KEYWORDS = {
        'unet': ['unet', 'U-Net'],
        'clip': ['clip', 'text_encoder', 'text-encoder'],
        'vae': ['vae', 'autoencoder'],
        't5': ['t5', 'text_encoder_2'],
        'aio': ['aio', 'all-in-one', 'full']
    }

    def __init__(self, model_dirs: List[str] = None):
        self.model_dirs = model_dirs or []
        self.scanned_models: List[ModelInfo] = []
        self.model_cache_file = Path.home() / ".omnigen_studio" / "model_cache.json"

    def add_model_dir(self, model_dir: str):
        """添加模型目录"""
        if model_dir not in self.model_dirs:
            self.model_dirs.append(model_dir)

    def scan_directory(self, directory: str, recursive: bool = True) -> List[ModelInfo]:
        """扫描目录获取模型"""
        models = []
        directory = Path(directory)

        if not directory.exists():
            logger.warning(f"目录不存在: {directory}")
            return models

        # 确定扫描模式
        if recursive:
            pattern = "**/*"
        else:
            pattern = "*"

        # 扫描所有文件
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                model_info = self._identify_model(file_path)
                if model_info:
                    models.append(model_info)

        logger.info(f"在 {directory} 扫描到 {len(models)} 个模型")
        return models

    def scan_all_directories(self) -> List[ModelInfo]:
        """扫描所有模型目录"""
        all_models = []

        for model_dir in self.model_dirs:
            models = self.scan_directory(model_dir)
            all_models.extend(models)

        # 去重
        seen = set()
        unique_models = []
        for model in all_models:
            if model.path not in seen:
                seen.add(model.path)
                unique_models.append(model)

        self.scanned_models = unique_models
        return unique_models

    def _identify_model(self, file_path: Path) -> Optional[ModelInfo]:
        """识别模型文件"""
        # 检查扩展名
        ext = file_path.suffix.lower()
        if ext not in self.SUPPORTED_IMAGE_FORMATS:
            return None

        format_type = self.SUPPORTED_IMAGE_FORMATS[ext]

        # 获取文件大小
        try:
            size_mb = file_path.stat().st_size / (1024 * 1024)
        except:
            size_mb = 0

        # 获取文件名（不含扩展名）
        name = file_path.stem

        # 识别模型类型
        model_type = self._identify_model_type(name, file_path)

        # 识别架构类型
        architecture = self._identify_architecture(name, file_path)

        return ModelInfo(
            name=name,
            path=str(file_path),
            type=model_type,
            format=format_type,
            size=size_mb,
            architecture=architecture,
            is_local=True,
            metadata={
                "extension": ext,
                "scanned_at": str(Path(__file__).stat().st_mtime)
            }
        )

    def _identify_model_type(self, name: str, file_path: Path = None) -> str:
        """识别模型类型"""
        name_lower = name.lower()

        # 检查文件名
        for model_type, keywords in self.MODEL_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in name_lower:
                    return model_type

        # 检查文件大小（ heuristics）
        if file_path:
            try:
                size_mb = file_path.stat().st_size / (1024 * 1024)
                # 大于2GB可能是SDXL或更大的模型
                if size_mb > 2000:
                    return "sdxl"
                elif size_mb > 500:
                    return "sd15"
            except:
                pass

        return "unknown"

    def _identify_architecture(self, name: str, file_path: Path = None) -> str:
        """识别架构类型"""
        name_lower = name.lower()

        # 检查文件名
        for arch, keywords in self.ARCHITECTURE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in name_lower:
                    return arch

        # 默认返回aio
        return "aio"

    def get_models_by_type(self, model_type: str) -> List[ModelInfo]:
        """获取指定类型的模型"""
        return [m for m in self.scanned_models if m.type == model_type]

    def get_models_by_architecture(self, architecture: str) -> List[ModelInfo]:
        """获取指定架构的模型"""
        return [m for m in self.scanned_models if m.architecture == architecture]

    def save_cache(self):
        """保存模型缓存"""
        try:
            self.model_cache_file.parent.mkdir(parents=True, exist_ok=True)

            cache_data = {
                "model_dirs": self.model_dirs,
                "models": [
                    {
                        "name": m.name,
                        "path": m.path,
                        "type": m.type,
                        "format": m.format,
                        "size": m.size,
                        "architecture": m.architecture,
                        "is_local": m.is_local,
                        "metadata": m.metadata
                    }
                    for m in self.scanned_models
                ]
            }

            with open(self.model_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)

            logger.info(f"模型缓存已保存: {self.model_cache_file}")

        except Exception as e:
            logger.error(f"保存模型缓存失败: {e}")

    def load_cache(self) -> bool:
        """加载模型缓存"""
        try:
            if not self.model_cache_file.exists():
                return False

            with open(self.model_cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            self.model_dirs = cache_data.get("model_dirs", [])
            self.scanned_models = [
                ModelInfo(
                    name=m["name"],
                    path=m["path"],
                    type=m["type"],
                    format=m["format"],
                    size=m["size"],
                    architecture=m["architecture"],
                    is_local=m["is_local"],
                    metadata=m.get("metadata", {})
                )
                for m in cache_data.get("models", [])
            ]

            logger.info(f"模型缓存已加载: {len(self.scanned_models)} 个模型")
            return True

        except Exception as e:
            logger.error(f"加载模型缓存失败: {e}")
            return False


class ModelDownloader:
    """模型下载器"""

    # 默认源
    DEFAULT_SOURCES = {
        "huggingface": "https://huggingface.co",
        "modelscope": "https://modelscope.cn"
    }

    # 国内镜像
    MIRRORS = {
        "hf_mirror": "https://hf-mirror.com",
        "modelscope": "https://modelscope.cn"
    }

    def __init__(self, default_source: str = "huggingface"):
        self.default_source = default_source
        self.current_mirror = None
        self.download_progress = {}

    def set_mirror(self, mirror_name: str) -> bool:
        """设置下载镜像"""
        if mirror_name in self.MIRRORS:
            self.current_mirror = mirror_name
            logger.info(f"已切换到镜像: {mirror_name}")
            return True
        return False

    def download_model(self, model_id: str, output_dir: str,
                      format: str = "safetensors",
                      resume: bool = True) -> Optional[str]:
        """下载模型"""
        try:
            from huggingface_hub import hf_hub_download, snapshot_download
            import time

            logger.info(f"开始下载模型: {model_id}")

            # 确定下载源
            if self.current_mirror:
                # 使用镜像（需要设置环境变量）
                os.environ["HF_ENDPOINT"] = self.MIRRORS[self.current_mirror]

            # 尝试断点续传
            cache_dir = Path(output_dir) / ".cache"
            cache_dir.mkdir(parents=True, exist_ok=True)

            # 下载模型文件
            if "/" in model_id:
                # 是完整的repo_id
                try:
                    file_path = hf_hub_download(
                        repo_id=model_id,
                        filename=f"model.{format}",
                        cache_dir=str(cache_dir),
                        resume_download=resume
                    )
                    logger.info(f"模型下载完成: {file_path}")
                    return file_path
                except Exception as e:
                    logger.warning(f"单个文件下载失败，尝试下载整个仓库: {e}")
                    try:
                        repo_path = snapshot_download(
                            repo_id=model_id,
                            cache_dir=str(cache_dir),
                            resume_download=resume
                        )
                        logger.info(f"仓库下载完成: {repo_path}")
                        return repo_path
                    except Exception as e2:
                        logger.error(f"下载失败: {e2}")
                        return None
            else:
                logger.error("无效的model_id格式")
                return None

        except ImportError:
            logger.error("请安装 huggingface_hub: pip install huggingface_hub")
            return None
        except Exception as e:
            logger.error(f"模型下载失败: {e}")
            return None

    def get_download_url(self, model_id: str, filename: str) -> str:
        """获取下载链接"""
        if self.current_mirror and self.current_mirror in self.MIRRORS:
            base_url = self.MIRRORS[self.current_mirror]
        else:
            base_url = self.DEFAULT_SOURCES.get(self.default_source, "https://huggingface.co")

        return f"{base_url}/{model_id}/resolve/main/{filename}"


class ModelManager:
    """模型管理器 - 统一管理扫描和下载"""

    def __init__(self, model_dirs: List[str] = None):
        self.scanner = ModelScanner(model_dirs)
        self.downloader = ModelDownloader()

        # 默认模型目录
        self.default_dirs = [
            "./models",
            "./models/checkpoints",
            "./models/sd15",
            "./models/sdxl",
            "./models/flux",
            "./",
            "./models/vae",
           models/loras str(Path.home() / "models" / "stable-diffusion"),
            str(Path.home() / ".cache" / "huggingface" / "hub")
        ]

    def setup_default_directories(self):
        """设置默认目录"""
        for dir_path in self.default_dirs:
            if os.path.exists(dir_path):
                self.scanner.add_model_dir(dir_path)

    def scan_and_cache(self, force: bool = False) -> List[ModelInfo]:
        """扫描并缓存模型"""
        # 尝试加载缓存
        if not force and self.scanner.load_cache():
            return self.scanner.scanned_models

        # 扫描模型
        self.setup_default_directories()
        models = self.scanner.scan_all_directories()

        # 保存缓存
        self.scanner.save_cache()

        return models

    def get_model_by_name(self, name: str) -> Optional[ModelInfo]:
        """根据名称查找模型"""
        for model in self.scanner.scanned_models:
            if model.name.lower() == name.lower():
                return model
        return None

    def download_and_cache(self, model_id: str, output_dir: str) -> Optional[str]:
        """下载并缓存模型"""
        file_path = self.downloader.download_model(model_id, output_dir)

        if file_path:
            # 重新扫描
            self.scan_and_cache(force=True)

        return file_path


# 全局模型管理器
_model_manager = None


def get_model_manager() -> ModelManager:
    """获取模型管理器实例"""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager
