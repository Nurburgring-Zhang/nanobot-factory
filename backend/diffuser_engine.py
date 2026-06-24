#!/usr/bin/env python3
"""
Nanobot Factory - Diffuser 推理引擎 (完整版)
Diffuser Inference Engine - Full Version

支持多模型推理：
- 图像生成: flux_dev, flux_schnell, sdxl, sd15, sd21
- 图像编辑: sdxl_img2img, sd15_img2img, sd_inpaint
- 视频生成: svd
- 3D生成: hunyuan3d
- 放大: real_esrgan

功能：
- 自动加载模型管道
- 支持多种格式 (safetensors, checkpoint, diffusers)
- 支持 LoRA 和 ControlNet
- 支持多种采样器和调度器
- 支持图像优化和放大
- 内存优化 (CPU offload, VAE slicing, attention slicing, xformers)
- 进度回调支持

@author MiniMax Agent
@date 2026-04-23
"""

import os
import sys
import json
import asyncio
import logging
import hashlib
import uuid
import gc
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Callable, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from contextlib import contextmanager
import threading
import weakref
import numpy as np
from PIL import Image

import torch
import torch.nn as nn
from torch.cuda.amp import autocast, GradScaler

# Diffusers 库导入
try:
    from diffusers import (
        DiffusionPipeline,
        StableDiffusionPipeline,
        StableDiffusionImg2ImgPipeline,
        StableDiffusionInpaintPipeline,
        StableDiffusionUpscalePipeline,
        StableDiffusionXLImg2ImgPipeline,
        StableDiffusionXLInpaintPipeline,
        StableDiffusionXLPipeline,
        FluxPipeline,
        StableVideoDiffusionPipeline,
        AutoencoderKL,
        UNet2DConditionModel,
        ControlNetModel,
    )
    from diffusers import (
        DDPMScheduler,
        DDIMScheduler,
        PNDMScheduler,
        LMSDiscreteScheduler,
        EulerDiscreteScheduler,
        EulerAncestralDiscreteScheduler,
        DPMSolverMultistepScheduler,
        DPMSolverSinglestepScheduler,
        UniPCMultistepScheduler,
        HeunDiscreteScheduler,
        KDPM2DiscreteScheduler,
        KDPM2AncestralDiscreteScheduler,
        DiffusionScheduler,
    )
    DIFFUSERS_AVAILABLE = True
except ImportError:
    DIFFUSERS_AVAILABLE = False
    DiffusionPipeline = object
    StableDiffusionPipeline = object

logger = logging.getLogger(__name__)


# =============================================================================
# 数据模型 - 枚举定义
# =============================================================================

class ModelType(Enum):
    """模型类型枚举"""
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    IMAGE_TO_VIDEO = "image_to_video"
    IMAGE_TO_3D = "image_to_3d"
    IMAGE_EDIT = "image_edit"
    UPSCALE = "upscale"


class SamplerType(Enum):
    """
    采样器类型枚举
    
    支持的采样算法：
    - EULER: Euler 方法
    - EULER_A: Euler Ancestral (带噪声的 Euler)
    - EULER_K: Euler Karras
    - DPM_2: DPM-Solver 2
    - DPM_2_A: DPM-Solver 2 Ancestral
    - DPM_SOLVER: DPM-Solver 单步
    - DPM_SOLVER_PP: DPM-Solver++ 多步
    - DPM++_2M: DPM++ 2M
    - DPM++_2M_SDE: DPM++ 2M SDE
    - DPM++_SDE: DPM++ SDE
    - LCM: Latent Consistency Model
    - DDIM: DDIM
    - UNIPC: UniPC
    - TCD: Target Consistent Diffusion
    - HEUN: Heun
    - PNDM: PNDM
    - LMS: LMS
    """
    EULER = "euler"
    EULER_A = "euler_a"
    EULER_K = "euler_k"
    DPM_2 = "dpm_2"
    DPM_2_A = "dpm_2_a"
    DPM_SOLVER = "dpm_solver"
    DPM_SOLVER_PP = "dpm_solver++"
    DPM_PLUS_2M = "dpm++_2m"
    DPM_PLUS_2M_SDE = "dpm++_2m_sde"
    DPM_PLUS_SDE = "dpm++_sde"
    LCM = "lcm"
    DDIM = "ddim"
    UNIPC = "unipc"
    TCD = "tcd"
    HEUN = "heun"
    PNDM = "pndm"
    LMS = "lms"


class SchedulerType(Enum):
    """
    调度器噪声计划类型枚举
    
    控制噪声调度的衰减方式：
    - NORMAL: 线性调度
    - KARRAS: Karras 噪声调度 (推荐)
    - EXPONENTIAL: 指数调度
    - SIMPLE: 简单线性
    - SQUARED: 平方调度
    """
    NORMAL = "normal"
    KARRAS = "karras"
    EXPONENTIAL = "exponential"
    SIMPLE = "simple"
    SQUARED = "squared"


class TorchDtype(Enum):
    """PyTorch 数据类型枚举"""
    FLOAT32 = "float32"
    FLOAT16 = "float16"
    BFLOAT16 = "bfloat16"


# =============================================================================
# 数据模型 - 数据类定义
# =============================================================================

@dataclass
class GenerationParams:
    """
    完整生成参数配置类
    
    Attributes:
        prompt: 正面提示词
        negative_prompt: 负面提示词
        width: 输出图像宽度
        height: 输出图像高度
        steps: 推理步数
        cfg_scale: CFG 引导强度
        seed: 随机种子，-1 表示随机
        num_images: 生成图像数量
        
        sampler: 采样器类型
        scheduler: 调度器噪声计划
        
        strength: 图生图强度 (0-1)
        guidance_start: CFG 开始比例
        guidance_end: CFG 结束比例
        
        lora_paths: LoRA 模型路径列表
        lora_weights: LoRA 权重列表
        lora_clip_weights: LoRA CLIP 权重列表
        
        controlnet_paths: ControlNet 模型路径列表
        controlnet_weights: ControlNet 权重列表
        control_images: ControlNet 控制图像列表
        control_guidance_start: ControlNet 引导开始列表
        control_guidance_end: ControlNet 引导结束列表
        
        vae_path: VAE 模型路径
        vae_slice_size: VAE 切片大小
        
        video_frames: 视频帧数
        video_fps: 视频帧率
        
        enable_attention_slicing: 启用注意力切片
        enable_vae_slicing: 启用 VAE 切片
        enable_cpu_offload: 启用 CPU 卸载
        enable_xformers: 启用 xformers
        
        clip_skip: CLIP 跳过层数
        guidance_scale_min: 最小 CFG 强度
    """
    # 提示词
    prompt: str = ""
    negative_prompt: str = ""
    
    # 基础参数
    width: int = 1024
    height: int = 1024
    steps: int = 28
    cfg_scale: float = 7.0
    seed: int = -1
    num_images: int = 1
    
    # 采样器/调度器
    sampler: SamplerType = SamplerType.EULER_A
    scheduler: SchedulerType = SchedulerType.KARRAS
    
    # 图像编辑参数
    strength: float = 0.75  # 图生图强度
    guidance_start: float = 0.0  # CFG 开始
    guidance_end: float = 1.0  # CFG 结束
    
    # LoRA 参数
    lora_paths: List[str] = field(default_factory=list)
    lora_weights: List[float] = field(default_factory=lambda: [1.0])
    lora_clip_weights: List[float] = field(default_factory=lambda: [1.0])
    
    # ControlNet 参数
    controlnet_paths: List[str] = field(default_factory=list)
    controlnet_weights: List[float] = field(default_factory=lambda: [1.0])
    control_images: List[Any] = field(default_factory=list)
    control_guidance_start: List[float] = field(default_factory=lambda: [0.0])
    control_guidance_end: List[float] = field(default_factory=lambda: [1.0])
    
    # VAE 参数
    vae_path: Optional[str] = None
    vae_slice_size: int = 4
    
    # 视频参数
    video_frames: int = 24
    video_fps: int = 24
    
    # 优化参数
    enable_attention_slicing: bool = True
    enable_vae_slicing: bool = True
    enable_cpu_offload: bool = False
    enable_xformers: bool = True
    
    # 高级参数
    clip_skip: int = 0
    guidance_scale_min: float = 1.0
    
    def __post_init__(self):
        """验证和修正参数"""
        # 确保宽度和高度是 8 的倍数
        self.width = (self.width // 8) * 8
        self.height = (self.height // 8) * 8
        
        # 确保步数至少为 1
        self.steps = max(1, self.steps)
        
        # 确保强度在 0-1 范围内
        self.strength = max(0.0, min(1.0, self.strength))
        
        # 确保 LoRA 权重数量与路径数量一致
        while len(self.lora_weights) < len(self.lora_paths):
            self.lora_weights.append(1.0)
        while len(self.lora_clip_weights) < len(self.lora_paths):
            self.lora_clip_weights.append(1.0)


@dataclass
class GenerationResult:
    """
    生成结果数据类
    
    Attributes:
        success: 是否成功
        images: 生成的图像列表
        seed: 使用的随机种子
        time: 生成耗时（秒）
        error: 错误信息（如果有）
        metadata: 额外元数据字典
    """
    success: bool
    images: List[Image.Image] = field(default_factory=list)
    seed: int = 0
    time: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "success": self.success,
            "images_count": len(self.images),
            "seed": self.seed,
            "time": self.time,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class ModelInfo:
    """
    模型信息数据类
    
    Attributes:
        model_id: 模型标识符
        model_type: 模型类型
        repo_id: HuggingFace repo ID
        pipeline_class: 管道类名
        config: 额外配置
    """
    model_id: str
    model_type: ModelType
    repo_id: str
    pipeline_class: str
    config: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "model_id": self.model_id,
            "model_type": self.model_type.value,
            "repo_id": self.repo_id,
            "pipeline_class": self.pipeline_class,
            "config": self.config,
        }


@dataclass
class LoRAInfo:
    """LoRA 模型信息"""
    path: str
    adapter_name: str
    weight: float
    clip_weight: float = 1.0
    loaded: bool = False


@dataclass
class ControlNetInfo:
    """ControlNet 模型信息"""
    path: str
    model_name: str
    weight: float
    guidance_start: float = 0.0
    guidance_end: float = 1.0
    loaded: bool = False


# =============================================================================
# 工具函数
# =============================================================================

def set_seed(seed: int) -> torch.Generator:
    """
    设置随机种子
    
    Args:
        seed: 种子值，-1 表示随机生成
        
    Returns:
        torch.Generator: PyTorch 随机生成器
    """
    if seed < 0:
        seed = np.random.randint(0, 2**32)
        
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    # Python random
    import random
    random.seed(seed)
    
    return torch.Generator()


def image_to_tensor(image: Image.Image) -> torch.Tensor:
    """
    将 PIL Image 转换为 tensor
    
    Args:
        image: PIL Image 对象
        
    Returns:
        torch.Tensor: 归一化的图像张量 (C, H, W)
    """
    image = image.convert("RGB")
    image = np.array(image).astype(np.float32) / 255.0
    image = torch.from_numpy(image)[None].permute(0, 3, 1, 2)
    return image


def tensor_to_image(tensor: torch.Tensor) -> Image.Image:
    """
    将 tensor 转换为 PIL Image
    
    Args:
        tensor: 图像张量 (C, H, W) 或 (B, C, H, W)
        
    Returns:
        PIL.Image: 转换后的图像
    """
    if tensor.dim() == 4:
        tensor = tensor[0]
    tensor = tensor.permute(1, 2, 0).cpu().numpy()
    tensor = (tensor * 255).clip(0, 255).astype(np.uint8)
    return Image.fromarray(tensor)


def resize_image(image: Image.Image, width: int, height: int) -> Image.Image:
    """
    调整图像大小
    
    Args:
        image: 源图像
        width: 目标宽度
        height: 目标高度
        
    Returns:
        Image.Image: 调整后的图像
    """
    return image.resize((width, height), Image.LANCZOS)


def get_torch_dtype(dtype_str: str) -> torch.dtype:
    """
    将字符串转换为 PyTorch 数据类型
    
    Args:
        dtype_str: 数据类型字符串 (float32, float16, bfloat16)
        
    Returns:
        torch.dtype: PyTorch 数据类型
    """
    dtype_map = {
        "float32": torch.float32,
        "float16": torch.float16,
"bfloat16": torch.bfloat16,
        "fp32": torch.float32,
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
    }
    return dtype_map.get(dtype_str.lower(), torch.float16)


# =============================================================================
# 调度器映射
# =============================================================================

def get_scheduler(
    scheduler_type: SchedulerType,
    num_train_timesteps: int = 1000,
    beta_start: float = 0.00085,
    beta_end: float = 0.012,
    prediction_type: str = "epsilon",
) -> Any:
    """
    获取调度器实例
    
    Args:
        scheduler_type: 调度器类型
        num_train_timesteps: 训练时间步数
        beta_start: Beta 起始值
        beta_end: Beta 结束值
        prediction_type: 预测类型 (epsilon, v_prediction, latent_noise)
        
    Returns:
        调度器实例
    """
    if not DIFFUSERS_AVAILABLE:
        raise ImportError("diffusers library not available")
    
    # 计算 beta 曲线
    betas = np.linspace(beta_start**0.5, beta_end**0.5, num_train_timesteps) ** 2
    
    scheduler_config = {
        "num_train_timesteps": num_train_timesteps,
        "beta_start": beta_start,
        "beta_end": beta_end,
        "betas": betas,
        "prediction_type": prediction_type,
    }
    
    if scheduler_type == SchedulerType.NORMAL:
        return DDPMScheduler(**scheduler_config)
    
    elif scheduler_type == SchedulerType.KARRAS:
        return DDPMScheduler(
            **scheduler_config,
            use_karras_sigmas=True,
        )
    
    elif scheduler_type == SchedulerType.EXPONENTIAL:
        return DPMSolverMultistepScheduler(
            **scheduler_config,
            use_karras_sigmas=True,
            sigma_type="exponential",
        )
    
    elif scheduler_type == SchedulerType.SIMPLE:
        return DPMSolverMultistepScheduler(
            **scheduler_config,
            use_karras_sigmas=True,
            sigma_type="linear",
        )
    
    elif scheduler_type == SchedulerType.SQUARED:
        return DPMSolverMultistepScheduler(
            **scheduler_config,
            use_karras_sigmas=True,
            sigma_type="squared_thresholding",
        )
    
    else:
        # 默认返回 Karras 调度器
        return DDPMScheduler(**scheduler_config, use_karras_sigmas=True)


def get_sampler_config(
    sampler_type: SamplerType,
    num_train_timesteps: int = 1000,
    beta_start: float = 0.00085,
    beta_end: float = 0.012,
) -> Dict[str, Any]:
    """
    获取采样器配置参数
    
    Args:
        sampler_type: 采样器类型
        num_train_timesteps: 训练时间步数
        beta_start: Beta 起始值
        beta_end: Beta 结束值
        
    Returns:
        Dict: 采样器配置参数字典
    """
    config = {
        "num_train_timesteps": num_train_timesteps,
        "beta_start": beta_start,
        "beta_end": beta_end,
    }
    
    # 特殊配置
    if sampler_type in [SamplerType.DPM_SOLVER_PP, SamplerType.DPM_PLUS_2M]:
        config["algorithm_type"] = "dpmsolver++"
        config["use_karras_sigmas"] = True
    
    elif sampler_type == SamplerType.DPM_PLUS_2M_SDE:
        config["algorithm_type"] = "dpmsolver++"
        config["use_karras_sigmas"] = True
        config["solver_type"] = "sde"
    
    elif sampler_type == SamplerType.DPM_PLUS_SDE:
        config["algorithm_type"] = "dpmsolver"
        config["use_karras_sigmas"] = True
        config["solver_type"] = "sde"
    
    elif sampler_type == SamplerType.UNIPC:
        config["algorithm_type"] = "uni_pc"
        config["use_karras_sigmas"] = True
    
    elif sampler_type == SamplerType.TCD:
        config["algorithm_type"] = "tcd"
        config["use_karras_sigmas"] = True
    
    return config


def create_scheduler_from_sampler(
    pipeline: Any,
    sampler_type: SamplerType,
    scheduler_type: SchedulerType = SchedulerType.KARRAS,
) -> Any:
    """
    从采样器类型创建调度器并应用到管道
    
    Args:
        pipeline: Diffusers 管道
        sampler_type: 采样器类型
        scheduler_type: 调度器类型
        
    Returns:
        配置好的调度器
    """
    if not DIFFUSERS_AVAILABLE:
        raise ImportError("diffusers library not available")
    
    # 获取采样器配置
    config = get_sampler_config(sampler_type)
    
    # 根据采样器类型创建调度器
    if sampler_type == SamplerType.EULER:
        scheduler = EulerDiscreteScheduler(**config)
    elif sampler_type == SamplerType.EULER_A:
        scheduler = EulerAncestralDiscreteScheduler(**config)
    elif sampler_type == SamplerType.HEUN:
        scheduler = HeunDiscreteScheduler(**config)
    elif sampler_type == SamplerType.DPM_2:
        scheduler = KDPM2DiscreteScheduler(**config)
    elif sampler_type == SamplerType.DPM_2_A:
        scheduler = KDPM2AncestralDiscreteScheduler(**config)
    elif sampler_type == SamplerType.DPM_SOLVER:
        scheduler = DPMSolverSinglestepScheduler(**config)
    elif sampler_type in [SamplerType.DPM_SOLVER_PP, SamplerType.DPM_PLUS_2M]:
        scheduler = DPMSolverMultistepScheduler(**config)
    elif sampler_type == SamplerType.DPM_PLUS_2M_SDE:
        scheduler = DPMSolverMultistepScheduler(**config, solver_type="sde")
    elif sampler_type == SamplerType.DPM_PLUS_SDE:
        scheduler = DPMSolverMultistepScheduler(**config, solver_type="sde")
    elif sampler_type == SamplerType.UNIPC:
        scheduler = UniPCMultistepScheduler(**config)
    elif sampler_type == SamplerType.LCM:
        # LCM 需要特殊处理
        scheduler = DPMSolverMultistepScheduler(
            **config,
            algorithm_type="dpmsolver++",
            solver_order=2,
        )
    elif sampler_type == SamplerType.DDIM:
        scheduler = DDIMScheduler(**config)
    elif sampler_type == SamplerType.PNDM:
        scheduler = PNDMScheduler(**config)
    elif sampler_type == SamplerType.LMS:
        scheduler = LMSDiscreteScheduler(**config)
    else:
        # 默认使用 Euler Ancestral
        scheduler = EulerAncestralDiscreteScheduler(**config)
    
    # 应用调度器
    pipeline.scheduler = scheduler
    return scheduler


# =============================================================================
# 模型注册表
# =============================================================================

class ModelRegistry:
    """
    模型注册表
    管理所有支持的模型配置
    """
    
    # 完整支持的模型字典
    SUPPORTED_MODELS: Dict[str, Dict[str, Any]] = {
        # ============== 图像生成 ==============
        "flux_dev": {
            "type": ModelType.TEXT_TO_IMAGE,
            "repo_id": "black-forest-labs/FLUX.1-dev",
            "class": "FluxPipeline",
            "torch_dtype": "bf16",
            "requires_extended_attention": True,
            "default_steps": 20,
            "default_cfg": 3.5,
            "description": "FLUX.1 dev - 高质量文生图",
        },
        "flux_schnell": {
            "type": ModelType.TEXT_TO_IMAGE,
            "repo_id": "black-forest-labs/FLUX.1-schnell",
            "class": "FluxPipeline",
            "torch_dtype": "fp16",
            "default_steps": 4,
            "default_cfg": 0.0,
            "description": "FLUX.1 schnell - 快速文生图",
        },
        "sdxl": {
            "type": ModelType.TEXT_TO_IMAGE,
            "repo_id": "stabilityai/stable-diffusion-xl-base-1.0",
            "class": "StableDiffusionXLPipeline",
            "torch_dtype": "fp16",
            "default_steps": 30,
            "default_cfg": 7.5,
            "description": "SDXL 1.0 - 高质量文生图",
        },
        "sd15": {
            "type": ModelType.TEXT_TO_IMAGE,
            "repo_id": "runwayml/stable-diffusion-v1-5",
            "class": "StableDiffusionPipeline",
            "torch_dtype": "fp16",
            "default_steps": 25,
            "default_cfg": 7.0,
            "description": "SD 1.5 - 经典文生图",
        },
        "sd21": {
            "type": ModelType.TEXT_TO_IMAGE,
            "repo_id": "stabilityai/stable-diffusion-2-1",
            "class": "StableDiffusionPipeline",
            "torch_dtype": "fp16",
            "default_steps": 25,
            "default_cfg": 7.0,
            "description": "SD 2.1 - 改进版文生图",
        },
        
        # ============== 图像编辑 ==============
        "sdxl_img2img": {
            "type": ModelType.IMAGE_TO_IMAGE,
            "repo_id": "stabilityai/stable-diffusion-xl-refiner-1.0",
            "class": "StableDiffusionXLImg2ImgPipeline",
            "torch_dtype": "fp16",
            "default_steps": 30,
            "default_cfg": 7.5,
            "description": "SDXL 图生图",
        },
        "sd15_img2img": {
            "type": ModelType.IMAGE_TO_IMAGE,
            "repo_id": "runwayml/stable-diffusion-v1-5",
            "class": "StableDiffusionImg2ImgPipeline",
            "torch_dtype": "fp16",
            "default_steps": 25,
            "default_cfg": 7.0,
            "description": "SD 1.5 图生图",
        },
        "sd_inpaint": {
            "type": ModelType.IMAGE_EDIT,
            "repo_id": "runwayml/stable-diffusion-inpainting",
            "class": "StableDiffusionInpaintPipeline",
            "torch_dtype": "fp16",
            "default_steps": 25,
            "default_cfg": 7.5,
            "description": "SD 局部重绘",
        },
        "sdxl_inpaint": {
            "type": ModelType.IMAGE_EDIT,
            "repo_id": "stabilityai/stable-diffusion-xl-refiner-1.0",
            "class": "StableDiffusionXLInpaintPipeline",
            "torch_dtype": "fp16",
            "default_steps": 30,
            "default_cfg": 7.5,
            "description": "SDXL 局部重绘",
        },
        
        # ============== 视频生成 ==============
        "svd": {
            "type": ModelType.IMAGE_TO_VIDEO,
            "repo_id": "stabilityai/stable-video-diffusion-img2vid",
            "class": "StableVideoDiffusionPipeline",
            "torch_dtype": "fp16",
            "default_steps": 25,
            "description": "SVD - 图像转视频",
        },
        
        # ============== 3D生成 ==============
        "hunyuan3d": {
            "type": ModelType.IMAGE_TO_3D,
            "repo_id": "Tencent/Hunyuan3D-2",
            "class": "Hunyuan3DPipeline",
            "torch_dtype": "fp16",
            "description": "腾讯混元3D - 图像转3D",
        },
        
        # ============== 放大 ==============
        "real_esrgan": {
            "type": ModelType.UPSCALE,
            "repo_id": "ai-forever/Real-ESRGAN",
            "class": "RealESRGANUpscaler",
            "torch_dtype": "fp32",
            "description": "Real-ESRGAN 图像放大",
        },
        "sdxl_upscale": {
            "type": ModelType.UPSCALE,
            "repo_id": "stabilityai/stable-diffusion-x4-upscaler",
            "class": "StableDiffusionUpscalePipeline",
            "torch_dtype": "fp16",
            "default_steps": 20,
            "description": "SDXL 4倍放大",
        },
    }
    
    @classmethod
    def get_model_info(cls, model_name: str) -> Optional[Dict[str, Any]]:
        """获取模型信息"""
        return cls.SUPPORTED_MODELS.get(model_name)
    
    @classmethod
    def get_model_type(cls, model_name: str) -> Optional[ModelType]:
        """获取模型类型"""
        info = cls.get_model_info(model_name)
        return info.get("type") if info else None
    
    @classmethod
    def list_models(cls, model_type: Optional[ModelType] = None) -> List[str]:
        """列出模型名称"""
        if model_type is None:
            return list(cls.SUPPORTED_MODELS.keys())
        return [
            name for name, info in cls.SUPPORTED_MODELS.items()
            if info.get("type") == model_type
        ]
    
    @classmethod
    def get_pipeline_class(cls, model_name: str) -> Optional[str]:
        """获取管道类名"""
        info = cls.get_model_info(model_name)
        return info.get("class") if info else None


# =============================================================================
# Diffuser 推理引擎
# =============================================================================

class DiffuserEngine:
    """
    Diffuser 推理引擎
    统一的多模型推理接口，支持完整的 Diffusers 功能
    
    Features:
        - 多模型管道加载和管理
        - LoRA 和 ControlNet 支持
        - 多种采样器和调度器
        - 内存优化 (CPU offload, VAE slicing, attention slicing, xformers)
        - 进度回调
        - 缓存管理
    
    Example:
        >>> engine = DiffuserEngine(cache_dir="./models")
        >>> engine.load_pipeline("sdxl")
        >>> params = GenerationParams(
        ...     prompt="A beautiful landscape",
        ...     width=1024, height=1024,
        ...     steps=30, cfg_scale=7.5
        ... )
        >>> result = engine.generate("sdxl", params)
        >>> if result.success:
        ...     result.images[0].save("output.png")
    """
    
    # 支持的模型
    SUPPORTED_MODELS = ModelRegistry.SUPPORTED_MODELS
    
    def __init__(
        self,
        cache_dir: Optional[str] = None,
        device: Optional[str] = None,
        enable_memory_efficient: bool = True,
    ):
        """
        初始化 Diffuser 引擎
        
        Args:
            cache_dir: 模型缓存目录
            device: 运行设备 (cuda/cpu), 默认自动检测
            enable_memory_efficient: 启用内存优化
        """
        # 缓存目录
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path.home() / ".cache" / "huggingface"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 设备
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        
        # 内存优化设置
        self.enable_memory_efficient = enable_memory_efficient
        
        # 加载的管道字典 {model_name: pipeline}
        self.pipelines: Dict[str, Any] = {}
        
        # LoRA 适配器 {adapter_name: LoRAInfo}
        self.lora_adapters: Dict[str, LoRAInfo] = {}
        
        # ControlNet 模型 {model_name: controlnet}
        self.controlnet_models: Dict[str, ControlNetInfo] = {}
        
        # 当前活动的 LoRA
        self.active_loras: List[str] = []
        
        # 锁
        self._lock = threading.RLock()
        
        # 进度回调
        self._progress_callbacks: Dict[str, Callable] = {}
        
        # 内存统计
        self._memory_stats: Dict[str, Any] = {}
        
        logger.info(f"DiffuserEngine initialized on {self.device}")
    
    # =========================================================================
    # 管道管理
    # =========================================================================
    
    def load_pipeline(
        self,
        model_name: str,
        model_path: Optional[str] = None,
        torch_dtype: Optional[str] = None,
        variant: str = "fp16",
        use_safetensors: bool = True,
        local_files_only: bool = False,
        **kwargs,
    ) -> bool:
        """
        加载模型管道
        
        Args:
            model_name: 模型名称 (如 "sdxl", "flux_dev")
            model_path: 自定义模型路径（优先使用）
            torch_dtype: 数据类型 (float16, bfloat16, float32)
            variant: 模型变体 (fp16, fp32, bf16)
            use_safetensors: 使用 safetensors 格式
            local_files_only: 仅使用本地文件
            
        Returns:
            bool: 加载是否成功
        """
        with self._lock:
            try:
                # 检查模型是否已加载
                if model_name in self.pipelines:
                    logger.info(f"Pipeline {model_name} already loaded")
                    return True
                
                # 检查 diffusers 是否可用
                if not DIFFUSERS_AVAILABLE:
                    logger.error("diffusers library not available")
                    return False
                
                # 获取模型信息
                model_info = ModelRegistry.get_model_info(model_name)
                if not model_info:
                    logger.error(f"Unknown model: {model_name}")
                    return False
                
                # 确定数据类型
                if torch_dtype is None:
                    torch_dtype = model_info.get("torch_dtype", "fp16")
                dtype = get_torch_dtype(torch_dtype)
                
                # 确定路径
                if model_path is None:
                    model_path = model_info.get("repo_id")
                
                logger.info(f"Loading pipeline: {model_name} from {model_path}")
                
                # 根据模型类型加载不同的管道
                pipeline_class = model_info.get("class")
                pipeline = self._load_pipeline_by_class(
                    pipeline_class,
                    model_path,
                    dtype,
                    variant,
                    use_safetensors,
                    local_files_only,
                    **kwargs,
                )
                
                if pipeline is None:
                    return False
                
                # 应用内存优化
                self._apply_memory_optimization(pipeline, model_name)
                
                # 保存管道
                self.pipelines[model_name] = {
                    "pipeline": pipeline,
                    "model_info": model_info,
                    "loaded_at": datetime.now().isoformat(),
                }
                
                # 加载已注册的 LoRA
                self._reload_loras(model_name)
                
                logger.info(f"Pipeline {model_name} loaded successfully")
                return True
                
            except Exception as e:
                logger.error(f"Failed to load pipeline {model_name}: {e}")
                import traceback
                traceback.print_exc()
                return False
    
    def _load_pipeline_by_class(
        self,
        pipeline_class: str,
        model_path: str,
        torch_dtype: torch.dtype,
        variant: str,
        use_safetensors: bool,
        local_files_only: bool,
        **kwargs,
    ) -> Optional[Any]:
        """根据类名加载管道"""
        
        try:
            if pipeline_class == "FluxPipeline":
                return FluxPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    use_safetensors=use_safetensors,
                    variant=variant,
                    local_files_only=local_files_only,
                )
            
            elif pipeline_class == "StableDiffusionXLPipeline":
                return StableDiffusionXLPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    use_safetensors=use_safetensors,
                    variant=variant,
                    local_files_only=local_files_only,
                )
            
            elif pipeline_class == "StableDiffusionPipeline":
                return StableDiffusionPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    use_safetensors=use_safetensors,
                    variant=variant,
                    local_files_only=local_files_only,
                )
            
            elif pipeline_class == "StableDiffusionImg2ImgPipeline":
                return StableDiffusionImg2ImgPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    use_safetensors=use_safetensors,
                    variant=variant,
                    local_files_only=local_files_only,
                )
            
            elif pipeline_class == "StableDiffusionInpaintPipeline":
                return StableDiffusionInpaintPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    use_safetensors=use_safetensors,
                    variant=variant,
                    local_files_only=local_files_only,
                )
            
            elif pipeline_class == "StableDiffusionXLImg2ImgPipeline":
                return StableDiffusionXLImg2ImgPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    use_safetensors=use_safetensors,
                    variant=variant,
                    local_files_only=local_files_only,
                )
            
            elif pipeline_class == "StableDiffusionXLInpaintPipeline":
                return StableDiffusionXLInpaintPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    use_safetensors=use_safetensors,
                    variant=variant,
                    local_files_only=local_files_only,
                )
            
            elif pipeline_class == "StableDiffusionUpscalePipeline":
                return StableDiffusionUpscalePipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    use_safetensors=use_safetensors,
                    local_files_only=local_files_only,
                )
            
            elif pipeline_class == "StableVideoDiffusionPipeline":
                return StableVideoDiffusionPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    local_files_only=local_files_only,
                )
            
            else:
                # 默认尝试使用基础 DiffusionPipeline
                logger.warning(f"Unknown pipeline class: {pipeline_class}, trying DiffusionPipeline")
                return DiffusionPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    use_safetensors=use_safetensors,
                    local_files_only=local_files_only,
                )
                
        except Exception as e:
            logger.error(f"Error loading pipeline class {pipeline_class}: {e}")
            return None
    
    def _apply_memory_optimization(self, pipeline: Any, model_name: str) -> None:
        """应用内存优化到管道"""
        
        # CPU Offload
        if self.enable_memory_efficient:
            try:
                pipeline.enable_model_cpu_offload()
                logger.debug(f"Enabled CPU offload for {model_name}")
            except Exception as e:
                logger.warning(f"CPU offload not available: {e}")
        
        # xformers
        if self.enable_memory_efficient and self.device == "cuda":
            try:
                if hasattr(pipeline, 'enable_xformers_memory_efficient_attention'):
                    pipeline.enable_xformers_memory_efficient_attention()
                    logger.debug(f"Enabled xformers for {model_name}")
            except Exception as e:
                logger.warning(f"xformers not available: {e}")
        
        # Attention slicing
        try:
            if hasattr(pipeline, 'enable_attention_slicing'):
                pipeline.enable_attention_slicing(slice_size="auto")
                logger.debug(f"Enabled attention slicing for {model_name}")
        except Exception as e:
            logger.warning(f"Attention slicing not available: {e}")
        
        # VAE slicing
        try:
            if hasattr(pipeline, 'enable_vae_slicing'):
                pipeline.enable_vae_slicing()
                logger.debug(f"Enabled VAE slicing for {model_name}")
        except Exception as e:
            logger.warning(f"VAE slicing not available: {e}")
    
    def unload_pipeline(self, model_name: str) -> bool:
        """
        卸载模型管道释放内存
        
        Args:
            model_name: 模型名称
            
        Returns:
            bool: 卸载是否成功
        """
        with self._lock:
            if model_name not in self.pipelines:
                logger.warning(f"Pipeline {model_name} not loaded")
                return False
            
            try:
                # 移除管道
                del self.pipelines[model_name]
                
                # 清理 GPU 内存
                self.clear_cache()
                
                logger.info(f"Pipeline {model_name} unloaded")
                return True
                
            except Exception as e:
                logger.error(f"Failed to unload pipeline {model_name}: {e}")
                return False
    
    def _reload_loras(self, model_name: str) -> None:
        """重新加载已注册的 LoRA 到指定模型"""
        pipeline_info = self.pipelines.get(model_name)
        if not pipeline_info:
            return
        
        pipeline = pipeline_info["pipeline"]
        
        for adapter_name, lora_info in self.lora_adapters.items():
            if lora_info.loaded:
                try:
                    if hasattr(pipeline, 'load_lora_weights'):
                        pipeline.load_lora_weights(lora_info.path)
                        logger.debug(f"Reloaded LoRA {adapter_name} for {model_name}")
                except Exception as e:
                    logger.warning(f"Failed to reload LoRA {adapter_name}: {e}")
    
    # =========================================================================
    # LoRA 管理
    # =========================================================================
    
    def load_lora(
        self,
        lora_path: str,
        adapter_name: str = "lora_1",
        weight: float = 1.0,
        clip_weight: float = 1.0,
    ) -> bool:
        """
        加载 LoRA 模型
        
        Args:
            lora_path: LoRA 模型路径
            adapter_name: 适配器名称
            weight: LoRA 权重
            clip_weight: CLIP 权重
            
        Returns:
            bool: 加载是否成功
        """
        with self._lock:
            try:
                # 保存 LoRA 信息
                lora_info = LoRAInfo(
                    path=lora_path,
                    adapter_name=adapter_name,
                    weight=weight,
                    clip_weight=clip_weight,
                    loaded=True,
                )
                self.lora_adapters[adapter_name] = lora_info
                
                # 加载到所有已加载的管道
                for model_name, pipeline_info in self.pipelines.items():
                    pipeline = pipeline_info["pipeline"]
                    try:
                        if hasattr(pipeline, 'load_lora_weights'):
                            pipeline.load_lora_weights(lora_path, adapter_name)
                            logger.info(f"Loaded LoRA {adapter_name} to {model_name}")
                    except Exception as e:
                        logger.warning(f"Failed to load LoRA to {model_name}: {e}")
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to load LoRA: {e}")
                return False
    
    def unload_lora(self, adapter_name: str) -> bool:
        """
        卸载 LoRA 模型
        
        Args:
            adapter_name: 适配器名称
            
        Returns:
            bool: 卸载是否成功
        """
        with self._lock:
            if adapter_name not in self.lora_adapters:
                logger.warning(f"LoRA adapter {adapter_name} not found")
                return False
            
            try:
                # 从所有管道卸载
                for model_name, pipeline_info in self.pipelines.items():
                    pipeline = pipeline_info["pipeline"]
                    try:
                        if hasattr(pipeline, 'unload_lora_weights'):
                            pipeline.unload_lora_weights()
                        elif hasattr(pipeline, 'disable_loaded_lora'):
                            pipeline.disable_loaded_lora()
                    except Exception:
                        pass
                
                # 移除记录
                del self.lora_adapters[adapter_name]
                
                logger.info(f"LoRA {adapter_name} unloaded")
                return True
                
            except Exception as e:
                logger.error(f"Failed to unload LoRA: {e}")
                return False
    
    # =========================================================================
    # ControlNet 管理
    # =========================================================================
    
    def load_controlnet(
        self,
        controlnet_path: str,
        model_name: str = "controlnet",
        weight: float = 1.0,
        guidance_start: float = 0.0,
        guidance_end: float = 1.0,
    ) -> bool:
        """
        加载 ControlNet 模型
        
        Args:
            controlnet_path: ControlNet 模型路径
            model_name: 模型名称标识
            weight: 控制权重
            guidance_start: 引导开始比例
            guidance_end: 引导结束比例
            
        Returns:
            bool: 加载是否成功
        """
        with self._lock:
            try:
                controlnet = ControlNetModel.from_pretrained(
                    controlnet_path,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                )
                
                controlnet_info = ControlNetInfo(
                    path=controlnet_path,
                    model_name=model_name,
                    weight=weight,
                    guidance_start=guidance_start,
                    guidance_end=guidance_end,
                    loaded=True,
                )
                
                self.controlnet_models[model_name] = {
                    "controlnet": controlnet,
                    "info": controlnet_info,
                }
                
                logger.info(f"ControlNet {model_name} loaded from {controlnet_path}")
                return True
                
            except Exception as e:
                logger.error(f"Failed to load ControlNet: {e}")
                return False
    
    # =========================================================================
    # 调度器管理
    # =========================================================================
    
    def set_scheduler(
        self,
        model_name: str,
        scheduler: SchedulerType,
        sampler: Optional[SamplerType] = None,
    ) -> bool:
        """
        设置调度器
        
        Args:
            model_name: 模型名称
            scheduler: 调度器类型
            sampler: 采样器类型（可选）
            
        Returns:
            bool: 设置是否成功
        """
        if model_name not in self.pipelines:
            logger.error(f"Pipeline {model_name} not loaded")
            return False
        
        try:
            pipeline = self.pipelines[model_name]["pipeline"]
            
            if sampler:
                # 使用采样器创建调度器
                create_scheduler_from_sampler(pipeline, sampler, scheduler)
            else:
                # 使用基础调度器
                new_scheduler = get_scheduler(scheduler)
                pipeline.scheduler = new_scheduler
            
            logger.info(f"Scheduler set for {model_name}: {scheduler.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to set scheduler: {e}")
            return False
    
    # =========================================================================
    # 生成
    # =========================================================================
    
    def generate(
        self,
        model_name: str,
        params: GenerationParams,
        input_image: Optional[Image.Image] = None,
        input_mask: Optional[Image.Image] = None,
        progress_callback: Optional[Callable] = None,
    ) -> GenerationResult:
        """
        统一生成方法
        
        Args:
            model_name: 模型名称
            params: 生成参数
            input_image: 输入图像（用于图生图）
            input_mask: 输入掩码（用于局部重绘）
            progress_callback: 进度回调函数
            
        Returns:
            GenerationResult: 生成结果
        """
        start_time = datetime.now()
        
        try:
            # 确保管道已加载
            if model_name not in self.pipelines:
                success = self.load_pipeline(model_name)
                if not success:
                    return GenerationResult(
                        success=False,
                        error=f"Failed to load pipeline: {model_name}"
                    )
            
            pipeline_info = self.pipelines[model_name]
            pipeline = pipeline_info["pipeline"]
            model_info = pipeline_info["model_info"]
            
            # 设置随机种子
            generator = set_seed(params.seed)
            actual_seed = params.seed if params.seed >= 0 else generator.seed()
            
            # 设置调度器
            create_scheduler_from_sampler(pipeline, params.sampler, params.scheduler)
            
            # 根据模型类型调用生成
            model_type = model_info.get("type")
            
            if model_type == ModelType.TEXT_TO_IMAGE:
                result = self._generate_text_to_image(
                    pipeline, params, generator
                )
            elif model_type == ModelType.IMAGE_TO_IMAGE:
                result = self._generate_image_to_image(
                    pipeline, params, input_image, generator
                )
            elif model_type == ModelType.IMAGE_EDIT:
                result = self._generate_image_edit(
                    pipeline, params, input_image, input_mask, generator
                )
            elif model_type == ModelType.IMAGE_TO_VIDEO:
                result = self._generate_image_to_video(
                    pipeline, params, input_image, generator
                )
            elif model_type == ModelType.UPSCALE:
                result = self._generate_upscale(
                    pipeline, params, input_image, generator
                )
            else:
                # 默认文生图
                result = self._generate_text_to_image(
                    pipeline, params, generator
                )
            
            # 处理结果
            elapsed = (datetime.now() - start_time).total_seconds()
            
            if isinstance(result, dict) and "images" in result:
                images = result["images"]
            elif hasattr(result, "images"):
                images = result.images
            elif isinstance(result, list):
                images = result
            else:
                images = []
            
            return GenerationResult(
                success=True,
                images=images if isinstance(images, list) else [images],
                seed=actual_seed,
                time=elapsed,
                metadata={
                    "model": model_name,
                    "model_type": model_type.value if model_type else "unknown",
                    "params": {
                        "prompt": params.prompt,
"negative_prompt": params.negative_prompt,
                        "width": params.width,
                        "height": params.height,
                        "steps": params.steps,
                        "cfg_scale": params.cfg_scale,
                        "sampler": params.sampler.value,
                        "scheduler": params.scheduler.value,
                        "strength": params.strength,
                    }
                }
            )
            
        except Exception as e:
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.error(f"Generation failed: {e}")
            import traceback
            traceback.print_exc()
            return GenerationResult(
                success=False,
                error=str(e),
                time=elapsed
            )
    
    def _generate_text_to_image(
        self,
        pipeline: Any,
        params: GenerationParams,
        generator: torch.Generator,
    ) -> Any:
        """文生图"""
        return pipeline(
            prompt=params.prompt,
            negative_prompt=params.negative_prompt,
            width=params.width,
            height=params.height,
            num_inference_steps=params.steps,
            guidance_scale=params.cfg_scale,
            num_images_per_prompt=params.num_images,
            generator=generator,
            clip_skip=params.clip_skip if params.clip_skip > 0 else None,
        )
    
    def _generate_image_to_image(
        self,
        pipeline: Any,
        params: GenerationParams,
        input_image: Optional[Image.Image],
        generator: torch.Generator,
    ) -> Any:
        """图生图"""
        if input_image is None:
            input_image = Image.new("RGB", (params.width, params.height), color="white")
        
        # 确保图像大小正确
        if input_image.size != (params.width, params.height):
            input_image = resize_image(input_image, params.width, params.height)
        
        return pipeline(
            prompt=params.prompt,
            image=input_image,
            negative_prompt=params.negative_prompt,
            strength=params.strength,
            num_inference_steps=params.steps,
            guidance_scale=params.cfg_scale,
            num_images_per_prompt=params.num_images,
            generator=generator,
        )
    
    def _generate_image_edit(
        self,
        pipeline: Any,
        params: GenerationParams,
        input_image: Optional[Image.Image],
        input_mask: Optional[Image.Image],
        generator: torch.Generator,
    ) -> Any:
        """图像编辑/局部重绘"""
        if input_image is None:
            input_image = Image.new("RGB", (params.width, params.height), color="white")
        
        if input_mask is None:
            input_mask = Image.new("L", (params.width, params.height), color=255)
        
        # 确保大小一致
        if input_image.size != (params.width, params.height):
            input_image = resize_image(input_image, params.width, params.height)
            input_mask = resize_image(input_mask, params.width, params.height)
        
        return pipeline(
            prompt=params.prompt,
            image=input_image,
            mask_image=input_mask,
            negative_prompt=params.negative_prompt,
            num_inference_steps=params.steps,
            guidance_scale=params.cfg_scale,
            generator=generator,
        )
    
    def _generate_image_to_video(
        self,
        pipeline: Any,
        params: GenerationParams,
        input_image: Optional[Image.Image],
        generator: torch.Generator,
    ) -> Any:
        """图生视频"""
        if input_image is None:
            input_image = Image.new("RGB", (params.width, params.height), color="white")
        
        return pipeline(
            image=input_image,
            num_frames=params.video_frames,
            num_inference_steps=params.steps,
            generator=generator,
        )
    
    def _generate_upscale(
        self,
        pipeline: Any,
        params: GenerationParams,
        input_image: Optional[Image.Image],
        generator: torch.Generator,
    ) -> Any:
        """图像放大"""
        if input_image is None:
            input_image = Image.new("RGB", (params.width, params.height), color="white")
        
        return pipeline(
            prompt=params.prompt or "high quality, detailed",
            image=input_image,
            num_inference_steps=params.steps,
            guidance_scale=params.cfg_scale,
            generator=generator,
        )
    
    # =========================================================================
    # 内存管理
    # =========================================================================
    
    def clear_cache(self) -> None:
        """清理缓存和释放 GPU 内存"""
        with self._lock:
            # 清理 Python 垃圾
            gc.collect()
            
            # 清理 CUDA 缓存
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            
            logger.info("Cache cleared")
    
    def get_memory_info(self) -> Dict[str, Any]:
        """
        获取内存信息
        
        Returns:
            Dict: 内存使用信息
        """
        info = {
            "loaded_pipelines": list(self.pipelines.keys()),
            "loaded_loras": list(self.lora_adapters.keys()),
            "loaded_controlnets": list(self.controlnet_models.keys()),
            "device": self.device,
        }
        
        if torch.cuda.is_available():
            info["gpu"] = {
                "name": torch.cuda.get_device_name(0),
                "memory_allocated_gb": round(torch.cuda.memory_allocated() / 1024**3, 2),
                "memory_reserved_gb": round(torch.cuda.memory_reserved() / 1024**3, 2),
                "memory_total_gb": round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 2),
                "memory_free_gb": round(
                    (torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated()) / 1024**3,
                    2
                ),
            }
        
        return info
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """获取内存使用情况（别名）"""
        return self.get_memory_info()
    
    # =========================================================================
    # 上下文管理器
    # =========================================================================
    
    @contextmanager
    def temporary_pipeline(self, model_name: str):
        """
        临时加载管道的上下文管理器
        
        Example:
            >>> with engine.temporary_pipeline("sdxl"):
            ...     result = engine.generate("sdxl", params)
        """
        try:
            self.load_pipeline(model_name)
            yield self.pipelines[model_name]["pipeline"]
        finally:
            self.unload_pipeline(model_name)


# =============================================================================
# 图像优化器
# =============================================================================

class ImageOptimizer:
    """
    图像优化器
    提供高质量的图像优化、滤镜、放大功能
    """
    
    def __init__(self, device: Optional[str] = None):
        """
        初始化图像优化器
        
        Args:
            device: 运行设备
        """
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.upscaler = None
        self.upscaler_model = None
    
    def upscale_2x(
        self,
        image: Image.Image,
        model_path: Optional[str] = None,
        tile_size: int = 512,
    ) -> Image.Image:
        """2倍放大"""
        return self.upscale(image, scale=2, model_path=model_path, tile_size=tile_size)
    
    def upscale_4x(
        self,
        image: Image.Image,
        model_path: Optional[str] = None,
        tile_size: int = 512,
    ) -> Image.Image:
        """4倍放大"""
        return self.upscale(image, scale=4, model_path=model_path, tile_size=tile_size)
    
    def upscale(
        self,
        image: Image.Image,
        scale: int = 2,
        model_path: Optional[str] = None,
        tile_size: int = 512,
    ) -> Image.Image:
        """
        图像放大
        
        Args:
            image: 源图像
            scale: 放大倍数
            model_path: 放大模型路径
            tile_size: 平铺大小
            
        Returns:
            Image.Image: 放大后的图像
        """
        try:
            if self.upscaler is None or self.upscaler_model != model_path:
                from diffusers import StableDiffusionUpscalePipeline
                
                if model_path is None:
                    model_path = "stabilityai/stable-diffusion-x4-upscaler"
                
                self.upscaler = StableDiffusionUpscalePipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                )
                self.upscaler = self.upscaler.to(self.device)
                self.upscaler_model = model_path
            
            # 放大
            result = self.upscaler(
                prompt="high quality, detailed, 4x upscaling",
                image=image,
                num_inference_steps=20,
                guidance_scale=7.5,
            )
            
            return result.images[0]
            
        except Exception as e:
            logger.error(f"Upscale failed: {e}")
            # 回退到 PIL resize
            new_size = (image.width * scale, image.height * scale)
            return image.resize(new_size, Image.LANCZOS)
    
    def apply_style_filter(
        self,
        image: Image.Image,
        style: str = "vivid",
    ) -> Image.Image:
        """
        应用风格滤镜
        
        Args:
            image: 源图像
            style: 风格名称 (vivid, warm, cool, noir, vintage, cinematic)
            
        Returns:
            Image.Image: 应用滤镜后的图像
        """
        from PIL import ImageEnhance, ImageFilter
        
        result = image.copy()
        
        if style == "vivid":
            # 增强色彩
            enhancer = ImageEnhance.Color(result)
            result = enhancer.enhance(1.3)
            # 增加对比度
            enhancer = ImageEnhance.Contrast(result)
            result = enhancer.enhance(1.2)
            
        elif style == "warm":
            enhancer = ImageEnhance.Color(result)
            result = enhancer.enhance(1.1)
            enhancer = ImageEnhance.Brightness(result)
            result = enhancer.enhance(1.1)
            
        elif style == "cool":
            enhancer = ImageEnhance.Color(result)
            result = enhancer.enhance(0.9)
            
        elif style == "noir":
            result = result.convert("L").convert("RGB")
            enhancer = ImageEnhance.Contrast(result)
            result = enhancer.enhance(1.5)
            
        elif style == "vintage":
            result = result.convert("RGB")
            enhancer = ImageEnhance.Color(result)
            result = enhancer.enhance(0.7)
            enhancer = ImageEnhance.Brightness(result)
            result = enhancer.enhance(0.9)
            result = result.filter(ImageFilter.GaussianBlur(radius=0.5))
            
        elif style == "cinematic":
            enhancer = ImageEnhance.Color(result)
            result = enhancer.enhance(0.85)
            enhancer = ImageEnhance.Contrast(result)
            result = enhancer.enhance(1.3)
            result = self._add_vignette(result)
        
        return result
    
    def _add_vignette(
        self,
        image: Image.Image,
        strength: float = 0.3,
    ) -> Image.Image:
        """添加暗角效果"""
        from PIL import ImageDraw
        
        result = image.copy()
        width, height = result.size
        
        # 创建渐变
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        center_x, center_y = width // 2, height // 2
        radius = max(width, height) * 0.7
        
        for y in range(0, height, 4):
            for x in range(0, width, 4):
                distance = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
                if distance > radius:
                    alpha = min(255, int((distance - radius) / radius * 255 * strength))
                    draw.rectangle([x, y, x+4, y+4], fill=(0, 0, 0, alpha))
        
        result = result.convert("RGBA")
        result = Image.alpha_composite(result, overlay)
        return result.convert("RGB")
    
    def enhance_quality(
        self,
        image: Image.Image,
        sharpness: float = 1.3,
        contrast: float = 1.1,
        color: float = 1.05,
    ) -> Image.Image:
        """
        提升图像质量
        
        Args:
            image: 源图像
            sharpness: 锐化强度
            contrast: 对比度
            color: 色彩饱和度
            
        Returns:
            Image.Image: 优化后的图像
        """
        from PIL import ImageEnhance
        
        result = image.copy()
        
        if sharpness > 1.0:
            enhancer = ImageEnhance.Sharpness(result)
            result = enhancer.enhance(sharpness)
            
        if contrast > 1.0:
            enhancer = ImageEnhance.Contrast(result)
            result = enhancer.enhance(contrast)
            
        if color != 1.0:
            enhancer = ImageEnhance.Color(result)
            result = enhancer.enhance(color)
        
        return result


# =============================================================================
# 全局实例管理
# =============================================================================

_diffuser_engine: Optional[DiffuserEngine] = None
_image_optimizer: Optional[ImageOptimizer] = None
_lock_global = threading.Lock()


def get_diffuser_engine(
    cache_dir: Optional[str] = None,
    device: Optional[str] = None,
) -> DiffuserEngine:
    """
    获取 Diffuser 引擎单例
    
    Args:
        cache_dir: 缓存目录
        device: 运行设备
        
    Returns:
        DiffuserEngine: 引擎实例
    """
    global _diffuser_engine
    with _lock_global:
        if _diffuser_engine is None:
            _diffuser_engine = DiffuserEngine(cache_dir=cache_dir, device=device)
        return _diffuser_engine


def get_image_optimizer() -> ImageOptimizer:
    """
    获取图像优化器单例
    
    Returns:
        ImageOptimizer: 优化器实例
    """
    global _image_optimizer
    with _lock_global:
        if _image_optimizer is None:
            _image_optimizer = ImageOptimizer()
        return _image_optimizer


def reset_diffuser_engine() -> None:
    """重置 Diffuser 引擎"""
    global _diffuser_engine, _image_optimizer
    with _lock_global:
        if _diffuser_engine:
            _diffuser_engine.clear_cache()
            _diffuser_engine = None
        _image_optimizer = None


# =============================================================================
# 便捷函数
# =============================================================================

async def generate_image_async(
    model_name: str,
    prompt: str,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 28,
    cfg: float = 7.0,
    seed: int = -1,
    sampler: str = "euler_a",
    scheduler: str = "karras",
    num_images: int = 1,
) -> GenerationResult:
    """
    生成图像的异步便捷函数
    
    Args:
        model_name: 模型名称
        prompt: 正面提示词
        negative_prompt: 负面提示词
        width: 图像宽度
        height: 图像高度
        steps: 推理步数
        cfg: CFG 引导强度
        seed: 随机种子
        sampler: 采样器类型
        scheduler: 调度器类型
        num_images: 生成数量
        
    Returns:
        GenerationResult: 生成结果
    """
    # 转换采样器和调度器
    sampler_type = SamplerType(sampler.lower()) if isinstance(sampler, str) else sampler
    scheduler_type = SchedulerType(scheduler.lower()) if isinstance(scheduler, str) else scheduler
    
    params = GenerationParams(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        cfg_scale=cfg,
        seed=seed,
        num_images=num_images,
        sampler=sampler_type,
        scheduler=scheduler_type,
    )
    
    engine = get_diffuser_engine()
    return engine.generate(model_name, params)


def generate_image_sync(
    model_name: str,
    prompt: str,
    negative_prompt: str = "",
    width: int = 1024,
    height: int = 1024,
    steps: int = 28,
    cfg: float = 7.0,
    seed: int = -1,
    sampler: str = "euler_a",
    scheduler: str = "karras",
    num_images: int = 1,
) -> GenerationResult:
    """
    生成图像的同步便捷函数
    """
    return asyncio.run(generate_image_async(
        model_name=model_name,
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        cfg=cfg,
        seed=seed,
        sampler=sampler,
        scheduler=scheduler,
        num_images=num_images,
    ))


async def edit_image_async(
    model_name: str,
    source_image: Image.Image,
    prompt: str,
    negative_prompt: str = "",
    strength: float = 0.8,
    steps: int = 28,
    cfg: float = 7.0,
    seed: int = -1,
) -> GenerationResult:
    """
    编辑图像的异步便捷函数
    
    Args:
        model_name: 模型名称
        source_image: 源图像
        prompt: 提示词
        negative_prompt: 负面提示词
        strength: 编辑强度
        steps: 推理步数
        cfg: CFG 引导强度
        seed: 随机种子
        
    Returns:
        GenerationResult: 生成结果
    """
    params = GenerationParams(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=source_image.width,
        height=source_image.height,
        steps=steps,
        cfg_scale=cfg,
        seed=seed,
        strength=strength,
    )
    
    engine = get_diffuser_engine()
    return engine.generate(model_name, params, input_image=source_image)


def edit_image_sync(
    model_name: str,
    source_image: Image.Image,
    prompt: str,
    negative_prompt: str = "",
    strength: float = 0.8,
    steps: int = 28,
    cfg: float = 7.0,
    seed: int = -1,
) -> GenerationResult:
    """
    编辑图像的同步便捷函数
    """
    return asyncio.run(edit_image_async(
        model_name=model_name,
        source_image=source_image,
        prompt=prompt,
        negative_prompt=negative_prompt,
        strength=strength,
        steps=steps,
        cfg=cfg,
        seed=seed,
    ))


def upscale_image(
    image: Image.Image,
    scale: int = 2,
    style: Optional[str] = None,
) -> Image.Image:
    """
    放大图像的便捷函数
    
    Args:
        image: 源图像
        scale: 放大倍数
        style: 风格滤镜（可选）
        
    Returns:
        Image.Image: 放大后的图像
    """
    optimizer = get_image_optimizer()
    
    # 放大
    if scale > 1:
        image = optimizer.upscale(image, scale=scale)
    
    # 应用风格
    if style:
        image = optimizer.apply_style_filter(image, style)
    
    return image


# =============================================================================
# API 路由
# =============================================================================

def create_api_routes() -> List[Dict[str, Any]]:
    """
    创建 API 路由定义
    
    Returns:
        List[Dict]: 路由定义列表
    """
    return [
        {
            "path": "/api/diffuser/models",
            "method": "GET",
            "description": "获取支持的模型列表",
            "handler": "get_models",
        },
        {
            "path": "/api/diffuser/generate",
            "method": "POST",
            "description": "生成图像",
            "handler": "generate_image",
        },
        {
            "path": "/api/diffuser/load",
            "method": "POST",
            "description": "加载模型管道",
            "handler": "load_pipeline",
        },
        {
            "path": "/api/diffuser/unload",
            "method": "POST",
            "description": "卸载模型管道",
            "handler": "unload_pipeline",
        },
        {
            "path": "/api/diffuser/lora/load",
            "method": "POST",
            "description": "加载 LoRA",
            "handler": "load_lora",
        },
        {
            "path": "/api/diffuser/lora/unload",
            "method": "POST",
            "description": "卸载 LoRA",
            "handler": "unload_lora",
        },
        {
            "path": "/api/diffuser/memory",
            "method": "GET",
            "description": "获取内存信息",
            "handler": "get_memory_info",
        },
        {
            "path": "/api/diffuser/cache/clear",
            "method": "POST",
            "description": "清理缓存",
            "handler": "clear_cache",
        },
    ]


# =============================================================================
# 示例用法
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    parser = argparse.ArgumentParser(description="Diffuser Engine CLI")
    parser.add_argument("--model", default="sdxl", help="Model name")
    parser.add_argument("--prompt", default="A beautiful sunset over the ocean", help="Prompt")
    parser.add_argument("--negative", default="blurry, low quality", help="Negative prompt")
    parser.add_argument("--steps", type=int, default=28, help="Inference steps")
    parser.add_argument("--cfg", type=float, default=7.5, help="CFG scale")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--width", type=int, default=1024, help="Width")
    parser.add_argument("--height", type=int, default=1024, help="Height")
    parser.add_argument("--output", default="output.png", help="Output file")
    
    args = parser.parse_args()
    
    # 创建引擎
    engine = get_diffuser_engine()
    
    # 加载管道
    print(f"Loading pipeline: {args.model}")
    success = engine.load_pipeline(args.model)
    print(f"Pipeline loaded: {success}")
    
    if not success:
        print("Failed to load pipeline")
        sys.exit(1)
    
    # 生成参数
    params = GenerationParams(
        prompt=args.prompt,
        negative_prompt=args.negative,
        width=args.width,
        height=args.height,
        steps=args.steps,
        cfg_scale=args.cfg,
        seed=args.seed,
    )
    
    # 生成
    print("Generating image...")
    result = engine.generate(args.model, params)
    
    if result.success:
        print(f"Generated {len(result.images)} images in {result.time:.2f}s")
        print(f"Seed: {result.seed}")
        
        # 保存
        for i, img in enumerate(result.images):
            output_path = args.output if len(result.images) == 1 else f"output_{i}.png"
            img.save(output_path)
            print(f"Saved {output_path}")
    else:
        print(f"Generation failed: {result.error}")
        sys.exit(1)
    
    # 内存使用
    memory = engine.get_memory_info()
    print(f"Memory: {json.dumps(memory, indent=2)}")
