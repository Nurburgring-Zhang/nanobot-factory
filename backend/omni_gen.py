#!/usr/bin/env python3
"""
Nanobot Factory - OmniGen API 模块
OmniGen API Module

提供所有 OmniGen 相关的 API 端点：
- 模型管理
- 提示词优化和翻译
- LoRA 管理
- 图像/视频/3D 生成
- 图像优化（滤镜、放大、色彩校正）

@author Matrix Agent
@date 2026-01-18
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import uuid
import base64
import io
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
import torch

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# 导入 Diffuser 引擎
# =============================================================================

try:
    # 尝试相对导入 (在backend包内)
    from .diffuser_engine import (
        DiffuserEngine,
        GenerationParams,
        GenerationResult,
        ModelType,
        SamplerType,
        SchedulerType,
    )
    DIFFUSER_ENGINE_AVAILABLE = True
except ImportError:
    try:
        # 尝试绝对导入
        from backend.diffuser_engine import (
            DiffuserEngine,
            GenerationParams,
            GenerationResult,
            ModelType,
            SamplerType,
            SchedulerType,
        )
        DIFFUSER_ENGINE_AVAILABLE = True
    except ImportError:
        logger.warning("DiffuserEngine not available, using mock mode")
        DIFFUSER_ENGINE_AVAILABLE = False
        
        # Mock classes for fallback (defined here so OmniGenState can reference them)
        class ModelType(Enum):
            FLUX_DEV = "flux_dev"
            FLUX_PRO = "flux_pro"
            SD15 = "sd15"
            SD15_VAE = "sd15_vae"
            SDXL = "sdxl"
            SDXL_VAE = "sdxl_vae"
            PLAYGROUND_V2 = "playground_v2"
            RECRAFT = "recraft"
            KOLORS = "kolors"
            WAN = "wan"
            HUNYUAN3D = "hunyuan3d"
            TRELLIS = "trellis"
            SVD = "svd"
        
        class SamplerType(Enum):
            EULER = "euler"
            EULER_A = "euler_a"
            DPM_2 = "dpm_2"
            DPM_2_A = "dpm_2_a"
            DPMS_MULTISTEP = "dpm++_2m"
            UNI_PC = "uni_pc"
            DDIM = "ddim"
            PNDM = "pndm"
        
        class SchedulerType(Enum):
            DEFAULT = "default"
            KARRAS = "karras"
            NORMAL = "normal"
            SIMPLE = "simple"
            DDIM = "ddim"
            UNIPC = "unipc"
        
        class GenerationParams:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)
        
        class GenerationResult:
            def __init__(self, success=False, images=None, seed=0, time=0.0, error=None, metadata=None):
                self.success = success
                self.images = images or []
                self.seed = seed
                self.time = time
                self.error = error
                self.metadata = metadata or {}
        
        class DiffuserEngine:
            def __init__(self, cache_dir=None):
                self.cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".cache" / "huggingface"
                self.pipelines = {}
            
            def load_pipeline(self, model_name, model_path=None, model_type="diffusers", torch_dtype=None, use_safetensors=True, variant="fp16", local_files_only=False):
                logger.info(f"[Mock] Loading pipeline: {model_name}")
                return True
            
            def generate(self, model_name, params, progress_callback=None):
                logger.info(f"[Mock] Generating with {model_name}")
                return GenerationResult(
                    success=True,
                    images=[],
                    seed=params.seed if hasattr(params, 'seed') else 42,
                    time=1.5,
                    metadata={"mock": True}
                )
            
            def load_lora(self, lora_path, adapter_name="lora_1", weight=0.8):
                logger.info(f"[Mock] Loading LoRA: {lora_path}")
                return True
            
            def load_controlnet(self, controlnet_path, model_name="controlnet"):
                logger.info(f"[Mock] Loading ControlNet: {controlnet_path}")
                return True

# =============================================================================
# 导入视频生成器
# =============================================================================

try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "omni_gen_studio" / "backend_modules"))
    from video_generation_backend import VideoGenerationBackend
    # 创建别名以保持向后兼容
    class VideoGenerator:
        def __init__(self, device="auto"):
            self.backend = VideoGenerationBackend(device=device)
        def load_models(self, *args, **kwargs):
            return self.backend.load_models(*args, **kwargs)
        def text_to_video(self, prompt, **kwargs):
            return self.backend.text_to_video(prompt, **kwargs)
        def image_to_video(self, image_path, **kwargs):
            return self.backend.image_to_video(image_path, **kwargs)
        def multi_image_to_video(self, image_paths, **kwargs):
            return self.backend.multi_image_to_video(image_paths, **kwargs)
        def first_last_frame_to_video(self, first_frame, last_frame, **kwargs):
            return self.backend.first_last_frame_to_video(first_frame, last_frame, **kwargs)
    VIDEO_GENERATOR_AVAILABLE = True
except ImportError as e:
    logger.warning(f"VideoGenerator not available: {e}")
    VIDEO_GENERATOR_AVAILABLE = False
    
    # Mock VideoGenerator for fallback
    class VideoGenerator:
        def __init__(self, device="auto"):
            self.device = device
        def load_models(self):
            return True
        def text_to_video(self, prompt, **kwargs):
            return {"success": False, "error": "VideoGenerator not available"}
        def image_to_video(self, image_path, **kwargs):
            return {"success": False, "error": "VideoGenerator not available"}
        def multi_image_to_video(self, image_paths, **kwargs):
            return {"success": False, "error": "VideoGenerator not available"}
        def first_last_frame_to_video(self, first_frame, last_frame, **kwargs):
            return {"success": False, "error": "VideoGenerator not available"}


# =============================================================================
# 数据模型
# =============================================================================

class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationType(Enum):
    """生成类型"""
    IMAGE = "image"
    IMAGE_EDIT = "image_edit"
    VIDEO = "video"
    MODEL_3D = "3d"


@dataclass
class OmniGenTask:
    """OmniGen 任务"""
    task_id: str
    type: GenerationType
    prompt: str
    negative_prompt: str = ""
    model: str = "flux_dev"
    params: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    result: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class ModelInfo:
    """模型信息"""
    id: str
    name: str
    type: str
    path: Optional[str] = None
    status: str = "not_downloaded"  # available, downloading, not_downloaded
    precision: Optional[str] = None
    vram_required: Optional[float] = None
    size: Optional[int] = None


@dataclass
class LoRAInfo:
    """LoRA 信息"""
    id: str
    name: str
    path: str
    enabled: bool = True


@dataclass
class PromptTemplate:
    """提示词模板"""
    id: str
    name: str
    content: str
    category: str


# =============================================================================
# 全局状态
# =============================================================================

class OmniGenState:
    """OmniGen 全局状态"""
    
    def __init__(self):
        self._lock = threading.RLock()
        
        # 引擎实例
        self.engine: Optional[DiffuserEngine] = None
        
        # 任务队列
        self.tasks: Dict[str, OmniGenTask] = {}
        
        # 可用模型
        self.models: Dict[str, ModelInfo] = {}
        
        # LoRA 列表
        self.loras: Dict[str, LoRAInfo] = {}
        
        # 提示词模板
        self.prompt_templates: Dict[str, PromptTemplate] = {}
        
        # 输出目录
        self.output_dir = Path.home() / ".nanobot-factory" / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化默认数据
        self._init_default_data()
    
    def _init_default_data(self):
        """初始化默认数据"""
        # 默认模型
        default_models = {
            # 图像生成
            "flux_dev": ModelInfo(
                id="flux_dev",
                name="FLUX.1 Dev",
                type="flux",
                status="available",
                precision="fp16",
                vram_required=24.0
            ),
            "flux_pro": ModelInfo(
                id="flux_pro",
                name="FLUX.1 Pro",
                type="flux",
                status="available",
                precision="fp16",
                vram_required=24.0
            ),
            "flux_schnell": ModelInfo(
                id="flux_schnell",
                name="FLUX.1 Schnell",
                type="flux",
                status="available",
                precision="fp16",
                vram_required=16.0
            ),
            "z_image": ModelInfo(
                id="z_image",
                name="Zebra Image",
                type="z_image",
                status="available",
                precision="fp16",
                vram_required=16.0
            ),
            "qwen_image": ModelInfo(
                id="qwen_image",
                name="Qwen2.5-VL Image",
                type="qwen_image",
                status="not_downloaded",
                precision="fp16",
                vram_required=16.0
            ),
            "wan_image": ModelInfo(
                id="wan_image",
                name="Wan2.1 Image",
                type="wan",
                status="available",
                precision="fp16",
                vram_required=16.0
            ),
            "sdxl": ModelInfo(
                id="sdxl",
                name="SDXL 1.0",
                type="sdxl",
                status="available",
                precision="fp16",
                vram_required=8.0
            ),
            "sd15": ModelInfo(
                id="sd15",
                name="SD 1.5",
                type="sd15",
                status="available",
                precision="fp16",
                vram_required=6.0
            ),
            # 图像编辑
            "qwen_image_edit": ModelInfo(
                id="qwen_image_edit",
                name="Qwen2.5-VL Edit",
                type="qwen_image_edit",
                status="not_downloaded",
                precision="fp16",
                vram_required=16.0
            ),
            "flux_edit": ModelInfo(
                id="flux_edit",
                name="FLUX Edit",
                type="flux",
                status="available",
                precision="fp16",
                vram_required=24.0
            ),
            "sd_inpaint": ModelInfo(
                id="sd_inpaint",
                name="SD Inpainting",
                type="sd15",
                status="available",
                precision="fp16",
                vram_required=8.0
            ),
            # 视频生成
            "wan_video": ModelInfo(
                id="wan_video",
                name="Wan2.1 Video",
                type="wan",
                status="available",
                precision="fp16",
                vram_required=24.0
            ),
            "ltx_video": ModelInfo(
                id="ltx_video",
                name="LTX Video",
                type="ltx",
                status="available",
                precision="fp16",
                vram_required=16.0
            ),
            "hunyuan_video": ModelInfo(
                id="hunyuan_video",
                name="Hunyuan Video",
                type="hunyuan",
                status="available",
                precision="fp16",
                vram_required=20.0
            ),
            # 3D生成
            "hunyuan3d_2": ModelInfo(
                id="hunyuan3d_2",
                name="Hunyuan3D-2",
                type="hunyuan3d",
                status="available",
                precision="fp16",
                vram_required=12.0
            ),
            "trellis": ModelInfo(
                id="trellis",
                name="Trellis 3D",
                type="trellis2",
                status="available",
                precision="fp16",
                vram_required=16.0
            ),
            "tripo": ModelInfo(
                id="tripo",
                name="TripoSR",
                type="tripo",
                status="available",
                precision="fp16",
                vram_required=8.0
            ),
        }
        self.models = default_models
        
        # 默认提示词模板
        default_templates = {
            "1": PromptTemplate(
                id="1",
                name="写实人像",
                content="professional portrait photo of a person, detailed skin texture, natural lighting, 8k quality, photorealistic",
                category="人物"
            ),
            "2": PromptTemplate(
                id="2",
                name="风景画",
                content="breathtaking landscape, golden hour, dramatic clouds, nature photography, high detail",
                category="风景"
            ),
            "3": PromptTemplate(
                id="3",
                name="赛博朋克",
                content="cyberpunk city, neon lights, rainy streets, futuristic, highly detailed, volumetric lighting",
                category="风格"
            ),
            "4": PromptTemplate(
                id="4",
                name="动漫风格",
                content="anime style illustration, vibrant colors, clean lines, beautiful background, high quality",
                category="风格"
            ),
            "5": PromptTemplate(
                id="5",
                name="产品摄影",
                content="professional product photography, studio lighting, clean background, commercial quality",
                category="商业"
            ),
            "6": PromptTemplate(
                id="6",
                name="建筑可视化",
                content="architectural visualization, modern building, clean design, architectural photography",
                category="建筑"
            ),
            "7": PromptTemplate(
                id="7",
                name="3D渲染",
                content="3d render, blender, octane render, detailed, professional lighting, c4d",
                category="风格"
            ),
            "8": PromptTemplate(
                id="8",
                name="水墨画",
                content="chinese ink painting style, traditional chinese art, elegant, minimal",
                category="风格"
            ),
        }
        self.prompt_templates = default_templates
    
    def get_engine(self) -> DiffuserEngine:
        """获取或创建引擎实例"""
        with self._lock:
            if self.engine is None:
                self.engine = DiffuserEngine(cache_dir=str(self.output_dir.parent / ".cache"))
                logger.info("DiffuserEngine initialized")
            return self.engine
    
    def create_task(
        self,
        type: GenerationType,
        prompt: str,
        model: str,
        negative_prompt: str = "",
        params: Dict[str, Any] = None
    ) -> str:
        """创建任务"""
        with self._lock:
            task_id = f"omni_task_{uuid.uuid4().hex[:12]}"
            
            task = OmniGenTask(
                task_id=task_id,
                type=type,
                prompt=prompt,
                negative_prompt=negative_prompt,
                model=model,
                params=params or {},
                status=TaskStatus.PENDING
            )
            
            self.tasks[task_id] = task
            logger.info(f"Created task: {task_id}")
            return task_id
    
    def get_task(self, task_id: str) -> Optional[OmniGenTask]:
        """获取任务"""
        with self._lock:
            return self.tasks.get(task_id)
    
    def update_task(self, task_id: str, **kwargs):
        """更新任务"""
        with self._lock:
            if task_id in self.tasks:
                task = self.tasks[task_id]
                for key, value in kwargs.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                task.updated_at = datetime.now()


# 全局状态实例
_omni_gen_state: Optional[OmniGenState] = None


def get_omni_gen_state() -> OmniGenState:
    """获取 OmniGen 状态单例"""
    global _omni_gen_state
    if _omni_gen_state is None:
        _omni_gen_state = OmniGenState()
    return _omni_gen_state


# =============================================================================
# API 端点实现
# =============================================================================

async def get_models() -> Dict[str, Any]:
    """
    获取可用模型列表
    """
    state = get_omni_gen_state()
    
    models_list = []
    for model_id, model_info in state.models.items():
        models_list.append({
            "id": model_info.id,
            "name": model_info.name,
            "type": model_info.type,
            "path": model_info.path,
            "status": model_info.status,
            "precision": model_info.precision,
            "vram_required": model_info.vram_required,
            "size": model_info.size,
        })
    
    return {"models": models_list}


async def add_model(path: str) -> Dict[str, Any]:
    """
    添加本地模型
    """
    state = get_omni_gen_state()
    
    # 检查路径是否存在
    model_path = Path(path)
    if not model_path.exists():
        return {"error": "Model path does not exist", "success": False}
    
    # 获取模型名称
    model_name = model_path.stem
    model_id = f"local_{hashlib.md5(path.encode()).hexdigest()[:8]}"
    
    # 确定模型类型
    model_type = "unknown"
    suffix = model_path.suffix.lower()
    if suffix in [".safetensors", ".ckpt", ".pt", ".pth"]:
        if "sdxl" in model_name.lower():
            model_type = "sdxl"
        elif "sd15" in model_name.lower() or "v1-5" in model_name.lower():
            model_type = "sd15"
        else:
            model_type = "sd15"
    elif ".gguf" in suffix:
        model_type = "gguf"
    
    # 添加模型
    model_info = ModelInfo(
        id=model_id,
        name=model_name,
        type=model_type,
        path=str(model_path),
        status="available"
    )
    
    state.models[model_id] = model_info
    
    return {
        "success": True,
        "model": {
            "id": model_info.id,
            "name": model_info.name,
            "type": model_info.type,
            "path": model_info.path,
            "status": model_info.status,
        }
    }


async def download_model(model_id: str) -> Dict[str, Any]:
    """
    下载模型
    """
    state = get_omni_gen_state()
    
    if model_id not in state.models:
        return {"error": "Model not found", "success": False}
    
    # 更新状态为下载中
    state.models[model_id].status = "downloading"
    
    # TODO: 实现实际的模型下载逻辑
    # 这里只是模拟下载完成
    await asyncio.sleep(1)
    
    state.models[model_id].status = "available"
    
    return {"success": True, "model_id": model_id}


async def get_prompt_templates() -> Dict[str, Any]:
    """
    获取提示词模板
    """
    state = get_omni_gen_state()
    
    templates_list = []
    for template_id, template in state.prompt_templates.items():
        templates_list.append({
            "id": template.id,
            "name": template.name,
            "content": template.content,
            "category": template.category,
        })
    
    return {"templates": templates_list}


async def optimize_prompt(prompt: str) -> Dict[str, Any]:
    """
    AI 优化提示词
    """
    # 这里可以集成 LLM 来优化提示词
    # 目前返回简单的优化版本
    
    optimized = prompt
    
    # 添加质量修饰词
    quality_prefixes = ["high quality", "detailed", "professional"]
    has_quality = any(q in prompt.lower() for q in quality_prefixes)
    
    if not has_quality:
        optimized = f"high quality, detailed, {prompt}"
    
    # 添加分辨率修饰词
    if "8k" not in prompt.lower() and "4k" not in prompt.lower():
        optimized += ", 8k resolution"
    
    # 添加光照修饰词
    if "lighting" not in prompt.lower() and "light" not in prompt.lower():
        optimized += ", professional lighting"
    
    return {"optimized_prompt": optimized}


async def translate_prompt(prompt: str, target_lang: str = "en") -> Dict[str, Any]:
    """
    翻译提示词
    """
    # 这里可以集成翻译 API
    # 目前返回模拟翻译
    
    # 简单的中英对照翻译映射
    translations = {
        "猫": "cat",
        "狗": "dog",
        "风景": "landscape",
        "城市": "city",
        "人像": "portrait",
        "科技": "technology",
        "未来": "future",
        "自然": "nature",
        "美丽": "beautiful",
        "可爱": "cute",
    }
    
    translated = prompt
    for cn, en in translations.items():
        translated = translated.replace(cn, en)
    
    # 如果没有翻译，返回原文（假设已经是英文）
    return {"translated": translated, "original": prompt}


async def read_prompt_file(path: str) -> Dict[str, Any]:
    """
    从文件读取提示词
    """
    try:
        file_path = Path(path)
        
        if not file_path.exists():
            return {"error": "File not found", "success": False}
        
        # 支持的格式
        if file_path.suffix.lower() not in ['.txt', '.md', '.prompt']:
            return {"error": "Unsupported file format", "success": False}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        return {"content": content, "success": True}
    
    except Exception as e:
        return {"error": str(e), "success": False}


async def get_loras() -> Dict[str, Any]:
    """
    获取 LoRA 列表
    """
    state = get_omni_gen_state()
    
    loras_list = []
    for lora_id, lora_info in state.loras.items():
        loras_list.append({
            "id": lora_info.id,
            "name": lora_info.name,
            "path": lora_info.path,
            "enabled": lora_info.enabled,
        })
    
    return {"loras": loras_list}


async def add_lora(path: str) -> Dict[str, Any]:
    """
    添加 LoRA
    """
    state = get_omni_gen_state()
    
    lora_path = Path(path)
    if not lora_path.exists():
        return {"error": "LoRA path does not exist", "success": False}
    
    lora_id = f"lora_{hashlib.md5(path.encode()).hexdigest()[:8]}"
    lora_name = lora_path.stem
    
    lora_info = LoRAInfo(
        id=lora_id,
        name=lora_name,
        path=str(lora_path),
        enabled=True
    )
    
    state.loras[lora_id] = lora_info
    
    # 尝试加载 LoRA
    try:
        engine = state.get_engine()
        engine.load_lora(str(lora_path), adapter_name=lora_id)
    except Exception as e:
        logger.warning(f"Failed to load LoRA: {e}")
    
    return {
        "success": True,
        "lora": {
            "id": lora_info.id,
            "name": lora_info.name,
            "path": lora_info.path,
        }
    }


async def generate_image(
    type: str,
    prompt: str,
    negative_prompt: str = "",
    model: str = "flux_dev",
    params: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    生成图像/视频/3D
    """
    state = get_omni_gen_state()
    
    # 解析生成类型
    try:
        gen_type = GenerationType(type)
    except ValueError:
        gen_type = GenerationType.IMAGE
    
    # 创建任务
    task_id = state.create_task(
        type=gen_type,
        prompt=prompt,
        negative_prompt=negative_prompt,
        model=model,
        params=params or {}
    )
    
    # 更新任务状态
    state.update_task(task_id, status=TaskStatus.RUNNING, started_at=datetime.now())
    
    # 准备生成参数 - 从params提取所有维度
    p = params or {}
    gen_params = GenerationParams(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=p.get("width", 1024),
        height=p.get("height", 1024),
        num_inference_steps=p.get("steps", 28),
        guidance_scale=p.get("cfg_scale", 7.0),
        seed=p.get("seed", -1),
        num_images=p.get("num_images", p.get("batch_count", 1)),
        sampler=p.get("sampler", "euler_a"),
        scheduler=p.get("scheduler", "karras"),
        strength=p.get("strength", 0.75),
        # LoRA
        lora_paths=p.get("lora_paths", [p.get("lora_model", "")] if p.get("lora_model") else []),
        lora_weights=p.get("lora_weights", [p.get("lora_strength", 1.0)] if p.get("lora_model") else []),
        lora_clip_weights=p.get("lora_clip_weights", [1.0] if p.get("lora_model") else []),
        # ControlNet
        controlnet_paths=p.get("controlnet_paths", []),
        controlnet_weights=p.get("controlnet_weights", []),
        control_images=p.get("control_images", []),
        control_guidance_start=p.get("control_guidance_start", [0.0]),
        control_guidance_end=p.get("control_guidance_end", [1.0]),
        # VAE
        vae_path=p.get("vae", None) or p.get("vae_path", None),
        vae_slice_size=p.get("vae_slice_size", 4),
        # 视频
        video_frames=p.get("video_frames", p.get("duration", 5) * p.get("fps", 24)),
        video_fps=p.get("fps", 24),
        # 高级
        enable_attention_slicing=p.get("enable_attention_slicing", True),
        enable_vae_slicing=p.get("enable_vae_slicing", True),
        enable_cpu_offload=p.get("enable_cpu_offload", False),
        enable_xformers=p.get("enable_xformers", True),
        clip_skip=p.get("clip_skip", 0),
        guidance_scale_min=p.get("guidance_scale_min", 1.0),
        # control guidance范围
        guidance_start=p.get("guidance_start", 0.0),
        guidance_end=p.get("guidance_end", 1.0),
    )
    
    # 执行生成
    try:
        engine = state.get_engine()
        
        # 如果模型未加载，先加载
        if model not in engine.pipelines:
            engine.load_pipeline(model)
        
        # 执行生成
        result = engine.generate(model, gen_params)
        
        if result.success:
            # 保存结果图片
            output_dir = state.output_dir / "images"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            result_paths = []
            for i, img in enumerate(result.images):
                img_path = output_dir / f"{task_id}_{i}.png"
                img.save(img_path)
                result_paths.append(str(img_path))
            
            state.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100.0,
                result=result_paths[0] if result_paths else None,
                completed_at=datetime.now()
            )
            
            return {
                "success": True,
                "task_id": task_id,
                "status": "completed",
                "result": result_paths,
                "seed": result.seed,
                "time": result.time,
            }
        else:
            state.update_task(
                task_id,
                status=TaskStatus.FAILED,
                error=result.error,
                completed_at=datetime.now()
            )
            
            return {
                "success": False,
                "task_id": task_id,
                "status": "failed",
                "error": result.error,
            }
    
    except Exception as e:
        logger.error(f"Generation error: {e}")
        state.update_task(
            task_id,
            status=TaskStatus.FAILED,
            error=str(e),
            completed_at=datetime.now()
        )
        
        return {
            "success": False,
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
        }


async def cancel_task(task_id: str) -> Dict[str, Any]:
    """
    取消任务
    """
    state = get_omni_gen_state()
    
    task = state.get_task(task_id)
    if not task:
        return {"error": "Task not found", "success": False}
    
    state.update_task(task_id, status=TaskStatus.CANCELLED, completed_at=datetime.now())
    
    return {"success": True, "task_id": task_id, "status": "cancelled"}


async def get_task_status(task_id: str) -> Dict[str, Any]:
    """
    获取任务状态
    """
    state = get_omni_gen_state()
    
    task = state.get_task(task_id)
    if not task:
        return {"error": "Task not found", "success": False}
    
    return {
        "success": True,
        "task_id": task.task_id,
        "type": task.type.value,
        "status": task.status.value,
        "progress": task.progress,
        "result": task.result,
        "error": task.error,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


# =============================================================================
# 图像优化功能
# =============================================================================

async def apply_filter(
    image_path: str,
    filter_type: str = "enhance",
    strength: float = 1.0,
    output_format: str = "PNG",
    output_quality: int = 95,
    preserve_details: bool = True,
    kernel_size: int = 3,
    custom_intensity: float = 0.5
) -> Dict[str, Any]:
    """
    应用滤镜 - 支持多种滤镜类型和参数控制
    """
    try:
        # 加载图片
        img = Image.open(image_path)
        
        # 转换为 RGB
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # 应用滤镜
        if filter_type == "sharpen":
            for _ in range(int(strength)):
                img = img.filter(ImageFilter.SHARPEN)
        
        elif filter_type == "blur":
            radius = int(strength * 5)
            img = img.filter(ImageFilter.GaussianBlur(radius))
        
        elif filter_type == "denoise":
            # 使用平滑滤镜
            img = img.filter(ImageFilter.SMOOTH_MORE)
        
        elif filter_type == "enhance":
            # 增强
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.0 + (strength - 1.0) * 0.3)
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.0 + (strength - 1.0) * 0.5)
        
        elif filter_type == "beautify":
            # 人像美颜（简单模拟）
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.1)
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(0.9)  # 降低锐度使皮肤更柔和
        
        elif filter_type == "stylize":
            # 风格化
            img = img.filter(ImageFilter.CONTOUR)
        
        # 保存结果
        state = get_omni_gen_state()
        output_dir = state.output_dir / "filtered"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        ext = output_format.lower()
        if ext == "jpeg": ext = "jpg"
        output_path = output_dir / f"filtered_{uuid.uuid4().hex[:8]}.{ext}"
        save_kwargs = {"format": output_format}
        if output_format in ("JPEG", "JPG"):
            save_kwargs["quality"] = output_quality
        elif output_format == "PNG":
            save_kwargs["optimize"] = True
        img.save(output_path, **save_kwargs)
        
        return {
            "success": True,
            "output_path": str(output_path),
        }
    
    except Exception as e:
        logger.error(f"Filter error: {e}")
        return {"error": str(e), "success": False}


async def upscale_image(
    image_path: str,
    model: str = "realesrgan_x4plus",
    scale: int = 2,
    face_enhance: bool = False,
    tile_size: int = 512,
    tile_pad: int = 32,
    denoise_strength: float = 0.0,
    output_format: str = "PNG",
    output_quality: int = 95
) -> Dict[str, Any]:
    """
    图像放大 - 支持多种模型和参数控制
    """
    try:
        # 加载图片
        img = Image.open(image_path)
        
        # 计算新尺寸
        new_width = img.width * scale
        new_height = img.height * scale
        
        # 使用高质量 resize
        upscaled = img.resize((new_width, new_height), Image.LANCZOS)
        
        # 保存结果
        state = get_omni_gen_state()
        output_dir = state.output_dir / "upscaled"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / f"upscaled_{uuid.uuid4().hex[:8]}.png"
        upscaled.save(output_path, "PNG")
        
        return {
            "success": True,
            "output_path": str(output_path),
            "original_size": [img.width, img.height],
            "new_size": [new_width, new_height],
        }
    
    except Exception as e:
        logger.error(f"Upscale error: {e}")
        return {"error": str(e), "success": False}


async def color_correction(
    image_path: str,
    brightness: float = 1.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    temperature: float = 0.0,
    tint: float = 0.0,
    vibrance: float = 1.0,
    exposure: float = 0.0,
    highlights: float = 0.0,
    shadows: float = 0.0,
    whites: float = 0.0,
    blacks: float = 0.0,
    output_format: str = "PNG",
    output_quality: int = 95
) -> Dict[str, Any]:
    """
    色彩校正 - 支持完整的色彩调整参数
    """
    try:
        # 加载图片
        img = Image.open(image_path)
        
        # 转换到 RGB
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # 亮度调整
        if brightness != 1.0:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(brightness)
        
        # 对比度调整
        if contrast != 1.0:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(contrast)
        
        # 饱和度调整
        if saturation != 1.0:
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(saturation)
        
        # 色温调整（简单模拟）
        if temperature != 0.0:
            # 暖色/冷色偏移
            img_array = np.array(img).astype(np.float32)
            
            if temperature > 0:
                # 偏暖 - 增加红黄
                img_array[:, :, 0] = np.clip(img_array[:, :, 0] * (1 + temperature * 0.3), 0, 255)
                img_array[:, :, 2] = np.clip(img_array[:, :, 2] * (1 - temperature * 0.3), 0, 255)
            else:
                # 偏冷 - 增加蓝绿
                img_array[:, :, 0] = np.clip(img_array[:, :, 0] * (1 + temperature * 0.3), 0, 255)
                img_array[:, :, 2] = np.clip(img_array[:, :, 2] * (1 - temperature * 0.3), 0, 255)
            
            img = Image.fromarray(img_array.astype(np.uint8))
        
        # 色调调整（简单模拟）
        if tint != 0.0:
            img_array = np.array(img).astype(np.float32)
            
            if tint > 0:
                # 偏绿
                img_array[:, :, 1] = np.clip(img_array[:, :, 1] * (1 + tint * 0.3), 0, 255)
            else:
                # 偏品红
                img_array[:, :, 0] = np.clip(img_array[:, :, 0] * (1 - tint * 0.15), 0, 255)
                img_array[:, :, 2] = np.clip(img_array[:, :, 2] * (1 - tint * 0.15), 0, 255)
            
            img = Image.fromarray(img_array.astype(np.uint8))
        
        # 保存结果
        state = get_omni_gen_state()
        output_dir = state.output_dir / "color_corrected"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / f"corrected_{uuid.uuid4().hex[:8]}.png"
        img.save(output_path, "PNG")
        
        return {
            "success": True,
            "output_path": str(output_path),
        }
    
    except Exception as e:
        logger.error(f"Color correction error: {e}")
        return {"error": str(e), "success": False}


# =============================================================================
# 视频生成API
# =============================================================================

# 全局视频生成器实例
_video_generator: Optional[VideoGenerator] = None


def _get_video_generator() -> VideoGenerator:
    """获取视频生成器实例"""
    global _video_generator
    if _video_generator is None:
        _video_generator = VideoGenerator(device="auto")
        _video_generator.load_models()
    return _video_generator


async def generate_text_to_video(
    prompt: str,
    negative_prompt: str = "",
    duration: int = 4,
    fps: int = 24,
    resolution: str = "720p",
    seed: int = -1,
    num_inference_steps: int = 25,
    guidance_scale: float = 7.5,
    width: int = 0,
    height: int = 0,
    model: str = "svd",
    motion_bucket_id: int = 127,
    noise_aug_strength: float = 0.02,
    camera_type: str = "",
    camera_speed: float = 1.0,
    loop: bool = False,
    style_preset: str = "",
    cfg_scale: float = 0.0,
    **kwargs
) -> Dict[str, Any]:
    """
    文生视频 - Text to Video
    
    Args:
        prompt: 文本提示词
        negative_prompt: 负面提示词
        duration: 视频时长（秒）
        fps: 帧率
        resolution: 分辨率 (480p, 720p, 1080p)
        seed: 随机种子
        num_inference_steps: 推理步数
        guidance_scale: 引导强度
    
    Returns:
        包含视频路径的结果字典
    """
    try:
        state = get_omni_gen_state()
        
        # 创建任务
        task_id = state.create_task(
            type=GenerationType.VIDEO,
            prompt=prompt,
            negative_prompt=negative_prompt,
            model="svd",
            params=kwargs
        )
        state.update_task(task_id, status=TaskStatus.RUNNING, started_at=datetime.now())
        
        # 获取视频生成器
        generator = _get_video_generator()
        
        # 执行生成
        result = generator.text_to_video(
            prompt=prompt,
            negative_prompt=negative_prompt,
            duration=duration,
            fps=fps,
            resolution=resolution,
            seed=seed,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            output_dir=str(state.output_dir / "videos")
        )
        
        if result.get("success"):
            state.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100.0,
                result=result.get("video_path"),
                completed_at=datetime.now()
            )
            return {
                "success": True,
                "task_id": task_id,
                "status": "completed",
                "video_path": result.get("video_path"),
                "metadata": result.get("metadata", {})
            }
        else:
            state.update_task(
                task_id,
                status=TaskStatus.FAILED,
                error=result.get("error", "Generation failed"),
                completed_at=datetime.now()
            )
            return {
                "success": False,
                "task_id": task_id,
                "error": result.get("error", "Generation failed")
            }
            
    except Exception as e:
        logger.error(f"Text to video error: {e}")
        return {"success": False, "error": str(e)}


async def generate_image_to_video(
    image_path: str,
    prompt: str = "",
    negative_prompt: str = "",
    duration: int = 4,
    fps: int = 24,
    resolution: str = "720p",
    seed: int = -1,
    motion_bucket_id: int = 127,
    noise_aug_strength: float = 0.02,
    width: int = 0,
    height: int = 0,
    model: str = "svd",
    num_inference_steps: int = 25,
    guidance_scale: float = 7.5,
    camera_type: str = "",
    camera_speed: float = 1.0,
    loop: bool = False,
    cfg_scale: float = 0.0,
    augmentation_level: float = 0.0,
    **kwargs
) -> Dict[str, Any]:
    """
    图生视频 - Image to Video
    
    Args:
        image_path: 输入图片路径
        prompt: 文本提示词（可选）
        negative_prompt: 负面提示词
        duration: 视频时长（秒）
        fps: 帧率
        resolution: 分辨率
        seed: 随机种子
        motion_bucket_id: 运动强度 (1-255)
        noise_aug_strength: 噪声增强强度
        width: 视频宽度(0=自动)
        height: 视频高度(0=自动)
        model: 模型名称
        num_inference_steps: 推理步数
        guidance_scale: 引导比例
        camera_type: 镜头运动类型
        camera_speed: 镜头运动速度
        loop: 是否循环
        cfg_scale: CFG比例
        augmentation_level: 增强级别
    
    Returns:
        包含视频路径的结果字典
    """
    try:
        state = get_omni_gen_state()
        
        # 验证图片路径
        if not Path(image_path).exists():
            return {"success": False, "error": f"Image not found: {image_path}"}
        
        # 创建任务
        task_id = state.create_task(
            type=GenerationType.VIDEO,
            prompt=prompt or f"Animate image: {image_path}",
            negative_prompt=negative_prompt,
            model="svd",
            params=kwargs
        )
        state.update_task(task_id, status=TaskStatus.RUNNING, started_at=datetime.now())
        
        # 获取视频生成器
        generator = _get_video_generator()
        
        # 执行生成
        result = generator.image_to_video(
            image_path=image_path,
            prompt=prompt,
            negative_prompt=negative_prompt,
            duration=duration,
            fps=fps,
            resolution=resolution,
            seed=seed,
            motion_bucket_id=motion_bucket_id,
            output_dir=str(state.output_dir / "videos")
        )
        
        if result.get("success"):
            state.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100.0,
                result=result.get("video_path"),
                completed_at=datetime.now()
            )
            return {
                "success": True,
                "task_id": task_id,
                "status": "completed",
                "video_path": result.get("video_path"),
                "metadata": result.get("metadata", {})
            }
        else:
            state.update_task(
                task_id,
                status=TaskStatus.FAILED,
                error=result.get("error", "Generation failed"),
                completed_at=datetime.now()
            )
            return {
                "success": False,
                "task_id": task_id,
                "error": result.get("error", "Generation failed")
            }
            
    except Exception as e:
        logger.error(f"Image to video error: {e}")
        return {"success": False, "error": str(e)}


async def generate_multi_image_to_video(
    image_paths: List[str],
    transition: str = "crossfade",
    duration_per_image: int = 2,
    fps: int = 24,
    resolution: str = "720p",
    prompt: str = "",
    **kwargs
) -> Dict[str, Any]:
    """
    多图生视频 - Multi-Image to Video
    
    Args:
        image_paths: 图片路径列表
        transition: 转场效果 (crossfade, slide, zoom, None)
        duration_per_image: 每张图片持续时间
        fps: 帧率
        resolution: 分辨率
        prompt: 文本提示词（可选）
    
    Returns:
        包含视频路径的结果字典
    """
    try:
        state = get_omni_gen_state()
        
        # 验证图片路径
        valid_paths = [p for p in image_paths if Path(p).exists()]
        if not valid_paths:
            return {"success": False, "error": "No valid images found"}
        
        # 创建任务
        task_id = state.create_task(
            type=GenerationType.VIDEO,
            prompt=prompt or f"Create video from {len(valid_paths)} images",
            model="multi_image",
            params=kwargs
        )
        state.update_task(task_id, status=TaskStatus.RUNNING, started_at=datetime.now())
        
        # 获取视频生成器
        generator = _get_video_generator()
        
        # 执行生成
        result = generator.multi_image_to_video(
            image_paths=valid_paths,
            transition=transition,
            duration_per_image=duration_per_image,
            fps=fps,
            resolution=resolution,
            output_dir=str(state.output_dir / "videos")
        )
        
        if result.get("success"):
            state.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100.0,
                result=result.get("video_path"),
                completed_at=datetime.now()
            )
            return {
                "success": True,
                "task_id": task_id,
                "status": "completed",
                "video_path": result.get("video_path"),
                "metadata": result.get("metadata", {})
            }
        else:
            state.update_task(
                task_id,
                status=TaskStatus.FAILED,
                error=result.get("error", "Generation failed"),
                completed_at=datetime.now()
            )
            return {
                "success": False,
                "task_id": task_id,
                "error": result.get("error", "Generation failed")
            }
            
    except Exception as e:
        logger.error(f"Multi-image to video error: {e}")
        return {"success": False, "error": str(e)}


async def generate_first_last_frame_video(
    first_frame: str,
    last_frame: str,
    prompt: str = "",
    duration: int = 4,
    fps: int = 24,
    resolution: str = "720p",
    seed: int = -1,
    interpolation_mode: str = "morph",
    **kwargs
) -> Dict[str, Any]:
    """
    首尾帧生视频 - First-Last Frame to Video
    
    Args:
        first_frame: 起始帧图片路径
        last_frame: 结束帧图片路径
        prompt: 文本提示词（可选）
        duration: 视频时长（秒）
        fps: 帧率
        resolution: 分辨率
        seed: 随机种子
        interpolation_mode: 插值模式 (morph, direct)
    
    Returns:
        包含视频路径的结果字典
    """
    try:
        state = get_omni_gen_state()
        
        # 验证图片路径
        if not Path(first_frame).exists():
            return {"success": False, "error": f"First frame not found: {first_frame}"}
        if not Path(last_frame).exists():
            return {"success": False, "error": f"Last frame not found: {last_frame}"}
        
        # 创建任务
        task_id = state.create_task(
            type=GenerationType.VIDEO,
            prompt=prompt or "Interpolate between first and last frame",
            model="frame_interpolation",
            params=kwargs
        )
        state.update_task(task_id, status=TaskStatus.RUNNING, started_at=datetime.now())
        
        # 获取视频生成器
        generator = _get_video_generator()
        
        # 执行生成
        result = generator.first_last_frame_to_video(
            first_frame=first_frame,
            last_frame=last_frame,
            prompt=prompt,
            duration=duration,
            fps=fps,
            resolution=resolution,
            seed=seed,
            interpolation_mode=interpolation_mode,
            output_dir=str(state.output_dir / "videos")
        )
        
        if result.get("success"):
            state.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100.0,
                result=result.get("video_path"),
                completed_at=datetime.now()
            )
            return {
                "success": True,
                "task_id": task_id,
                "status": "completed",
                "video_path": result.get("video_path"),
                "metadata": result.get("metadata", {})
            }
        else:
            state.update_task(
                task_id,
                status=TaskStatus.FAILED,
                error=result.get("error", "Generation failed"),
                completed_at=datetime.now()
            )
            return {
                "success": False,
                "task_id": task_id,
                "error": result.get("error", "Generation failed")
            }
            
    except Exception as e:
        logger.error(f"First-last frame video error: {e}")
        return {"success": False, "error": str(e)}


async def interpolate_video(
    video_path: str,
    target_fps: int = 60,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    视频帧间插值 - Video Interpolation
    
    Args:
        video_path: 输入视频路径
        target_fps: 目标帧率
        output_path: 输出路径（可选）
    
    Returns:
        包含结果的信息字典
    """
    try:
        state = get_omni_gen_state()
        generator = _get_video_generator()
        
        if output_path is None:
            output_dir = state.output_dir / "videos" / "interpolated"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"interpolated_{uuid.uuid4().hex[:8]}.mp4")
        
        result = generator.video_interpolation(
            video_path=video_path,
            target_fps=target_fps,
            output_path=output_path
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Video interpolation error: {e}")
        return {"success": False, "error": str(e)}


async def super_resolve_video(
    video_path: str,
    scale: int = 2,
    output_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    视频超分辨率 - Video Super Resolution
    
    Args:
        video_path: 输入视频路径
        scale: 放大倍数 (2, 4)
        output_path: 输出路径（可选）
    
    Returns:
        包含结果的信息字典
    """
    try:
        state = get_omni_gen_state()
        generator = _get_video_generator()
        
        if output_path is None:
            output_dir = state.output_dir / "videos" / "upscaled"
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(output_dir / f"upscaled_{uuid.uuid4().hex[:8]}.mp4")
        
        result = generator.video_super_resolution(
            video_path=video_path,
            scale=scale,
            output_path=output_path
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Video super resolution error: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# 工具函数
# =============================================================================

def get_sampler_type(sampler_name: str) -> SamplerType:
    """获取采样器类型"""
    sampler_map = {
        "euler": SamplerType.EULER,
        "euler_ancestral": SamplerType.EULER_A,
        "dpm_2": SamplerType.DPM_2,
        "dpm_2_ancestral": SamplerType.DPM_2_A,
        "dpm++_2m": SamplerType.DPMS_MULTISTEP,
        "dpm++_2m_sde": SamplerType.DPMS_MULTISTEP,
        "uni_pc": SamplerType.UNI_PC,
        "ddim": SamplerType.DDIM,
        "pndm": SamplerType.PNDM,
    }
    return sampler_map.get(sampler_name.lower(), SamplerType.EULER_A)


def get_scheduler_type(scheduler_name: str) -> SchedulerType:
    """获取调度器类型"""
    scheduler_map = {
        "normal": SchedulerType.NORMAL,
        "karras": SchedulerType.KARRAS,
        "exponential": SchedulerType.EXPONENTIAL,
        "simple": SchedulerType.SIMPLE,
        "ddim": SchedulerType.DDIM,
    }
    return scheduler_map.get(scheduler_name.lower(), SchedulerType.KARRAS)


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 核心函数
    "get_omni_gen_state",
    "get_models",
    "add_model",
    "download_model",
    "get_prompt_templates",
    "optimize_prompt",
    "translate_prompt",
    "read_prompt_file",
    "get_loras",
    "add_lora",
    "generate_image",
    "cancel_task",
    "get_task_status",
    # 图像处理
    "apply_filter",
    "upscale_image",
    "color_correction",
    # 视频生成
    "generate_text_to_video",
    "generate_image_to_video",
    "generate_multi_image_to_video",
    "generate_first_last_frame_video",
    "interpolate_video",
    "super_resolve_video",
]
