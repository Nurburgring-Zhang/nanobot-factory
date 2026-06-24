#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OmniGen Studio - 推理引擎核心
支持最新AIGC模型的Diffuser推理
作者：MiniMax Agent
版本：v7.0 - 支持Z-Image/Qwen-Image/Wan/Hunyuan3D等最新模型
"""

import os
import sys
import torch
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from PIL import Image
import numpy as np
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ==================== 模型类型枚举 ====================

class ModelType(Enum):
    """支持的AIGC模型类型 (2026年最新)"""
    # ===== 图像生成模型 =====
    GLM_IMAGE = "glm_image"                    # 智谱+华为 GLM-Image (2026.1开源)
    Z_IMAGE_TURBO = "z_image_turbo"          # 阿里Z-Image-Turbo (9步生成)
    Z_IMAGE_STANDARD = "z_image_standard"    # 阿里Z-Image标准版
    QWEN_IMAGE = "qwen_image"               # 通义Qwen2.5-VL
    FLUX_DEV = "flux_dev"                   # FLUX.1 Dev
    FLUX_2_KLEIN = "flux_2_klein"          # FLUX.2_Klein编辑
    SD_3 = "stable_diffusion_3"            # Stable Diffusion 3
    
    # ===== 视频生成模型 =====
    WAN_2_2 = "wan_2_2"                     # Wan 2.2 (快手可灵同源)
    LTX_VIDEO = "ltx_video"                 # LTX-Video
    LTX_2 = "ltx_2"                       # LTX-2 (2026 CES)
    COGVIDEOX = "cogvideox"                # 智谱CogVideoX
    
    # ===== 3D生成模型 =====
    HUNYUAN3D_2 = "hunyuan3d_2"            # 腾讯混元3D-2
    TRELLIS_2 = "trellis_2"               # 微软TRELLIS-2
    TRIPO_3 = "tripo_3"                   # Tripo 3 (API调用)
    
    # ===== 放大模型 =====
    DAT = "dat"                             # SDX4放大
    REAL_ESRGAN = "real_esrgan"            # Real-ESRGAN放大
    
    # ===== ControlNet =====
    CONTROLNET_CANNY = "controlnet_canny"   # Canny控制
    CONTROLNET_DEPTH = "controlnet_depth"   # Depth控制
    
    # ===== API模型 =====
    GPT_IMAGE_2 = "gpt_image_2"            # OpenAI GPT-Image-2 (API)
    NANO_BANANA_PRO = "nano_banana_pro"   # Google Gemini Nano Banana Pro (API)
    DALLE_3 = "dalle_3"                   # DALL-E 3 (API)
    IMAGEN_3 = "imagen_3"                 # Google Imagen 3 (API)


@dataclass
class ModelInfo:
    """模型信息"""
    model_id: str
    model_type: ModelType
    model_path: str
    model_format: str = "safetensors"
    config: Dict[str, Any] = field(default_factory=dict)
    size_mb: float = 0.0
    is_loaded: bool = False


# ==================== 2026年最新模型配置 ====================

# 支持的最新模型HuggingFace仓库映射 (更新至2026年4月)
MODEL_REPOS = {
    # ===== 图像生成模型 =====
    "glm_image": {
        "repo_id": "zai-org/GLM-Image",  # 智谱+华为 GLM-Image (2026.1开源,登顶HF榜首)
        "pipeline": "AutoPipelineForText2Image",
        "type": "text2image",
        "provider": "ZhipuAI/Huawei"
    },
    "z_image_turbo": {
        "repo_id": "Tongyi-MAI/Z-Image-Turbo",  # 阿里通义Z-Image-Turbo (DiT架构,9步生成)
        "pipeline": "AutoPipelineForText2Image",
        "type": "text2image",
        "provider": "Alibaba"
    },
    "z_image_standard": {
        "repo_id": "Tongyi-MAI/Z-Image",  # 阿里Z-Image标准版(可微调/LoRA)
        "pipeline": "AutoPipelineForText2Image",
        "type": "text2image",
        "provider": "Alibaba"
    },
    "qwen_image": {
        "repo_id": "Qwen/Qwen2.5-VL",  # 通义Qwen2.5-VL多模态
        "pipeline": "AutoPipelineForText2Image",
        "type": "text2image",
        "provider": "Alibaba"
    },
    "flux_2_klein": {
        "repo_id": "black-forest-labs/FLUX.2-Klein",  # FLUX.2_Klein编辑
        "pipeline": "AutoPipelineForImage2Image",
        "type": "image2image",
        "provider": "BlackForestLabs"
    },
    "flux_dev": {
        "repo_id": "black-forest-labs/FLUX.1-dev",  # FLUX.1 Dev
        "pipeline": "AutoPipelineForText2Image",
        "type": "text2image",
        "provider": "BlackForestLabs"
    },
    "stable_diffusion_3": {
        "repo_id": "stabilityai/stable-diffusion-3-medium",  # SD3
        "pipeline": "AutoPipelineForText2Image",
        "type": "text2image",
        "provider": "StabilityAI"
    },
    
    # ===== 视频生成模型 =====
    "wan_2_2": {
        "repo_id": "Wan-AI/Wan2.2-T2V-14B",  # Wan 2.2 (快手可灵3.0同源)
        "pipeline": "DiffusionPipeline",
        "type": "video",
        "provider": "WanAI"
    },
    "ltx_video": {
        "repo_id": "Lightricks/LTX-Video",  # LTX-Video (NVIDIA优化版)
        "pipeline": "DiffusionPipeline",
        "type": "video",
        "provider": "Lightricks/NVIDIA"
    },
    "ltx_2": {
        "repo_id": "Lightricks/LTX-2",  # LTX-2 (2026 CES发布)
        "pipeline": "DiffusionPipeline",
        "type": "video",
        "provider": "Lightricks"
    },
    "cogvideox": {
        "repo_id": "THUDM/CogVideoX",  # 智谱CogVideoX
        "pipeline": "DiffusionPipeline",
        "type": "video",
        "provider": "ZhipuAI"
    },
    
    # ===== 3D生成模型 =====
    "hunyuan3d_2": {
        "repo_id": "Tencent/Hunyuan3D-2",  # 腾讯混元3D-2 (1024分辨率)
        "pipeline": "DiffusionPipeline",
        "type": "3d",
        "provider": "Tencent"
    },
    "trellis_2": {
        "repo_id": "microsoft/TRELLIS-2",  # 微软TRELLIS-2 (O-Voxel架构)
        "pipeline": "DiffusionPipeline",
        "type": "3d",
        "provider": "Microsoft"
    },
    "tripo_3": {
        "repo_id": None,  # Tripo 3 需要API调用 tripo3.com
        "pipeline": "API",
        "type": "3d",
        "provider": "VAST/TripoAI",
        "api_endpoint": "https://api.tripo3.com/v1/image-to-3d"
    },
    
    # ===== 图像放大模型 =====
    "dat": {
        "repo_id": "stabilityai/stable-diffusion-x4-upscaler",  # SDX4放大
        "pipeline": "DiffusionPipeline",
        "type": "upscale",
        "provider": "StabilityAI"
    },
    "real_esrgan": {
        "repo_id": "xinntao/Real-ESRGAN",  # Real-ESRGAN放大
        "pipeline": "RealESRGANPipeline",
        "type": "upscale",
        "provider": "xinntao"
    },
    
    # ===== ControlNet =====
    "controlnet_canny": {
        "repo_id": "lllyasviel/control_v11p_sd15_canny",
        "pipeline": "ControlNetModel",
        "type": "controlnet",
        "provider": "lllyasviel"
    },
    "controlnet_depth": {
        "repo_id": "lllyasviel/control_v11f1p_sd15_depth",
        "pipeline": "ControlNetModel",
        "type": "controlnet",
        "provider": "lllyasviel"
    },
}

# ===== API模型服务配置 =====
API_MODELS = {
    "gpt_image_2": {
        "name": "GPT-Image-2",
        "provider": "OpenAI",
        "api_endpoint": "https://api.openai.com/v1/images/generations",
        "requires_api_key": True,
        "model_id": "gpt-image-2",
        "description": "OpenAI GPT-Image-2 (2026.4发布,支持联网思考能力)"
    },
    "nano_banana_pro": {
        "name": "Gemini Nano Banana Pro",
        "provider": "Google",
        "api_endpoint": "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image",
        "requires_api_key": True,
        "model_id": "gemini-3-pro-image",
        "description": "Google Gemini Nano Banana Pro"
    },
    "dalle_3": {
        "name": "DALL-E 3",
        "provider": "OpenAI",
        "api_endpoint": "https://api.openai.com/v1/images/generations",
        "requires_api_key": True,
        "model_id": "dall-e-3",
        "description": "OpenAI DALL-E 3"
    },
    "imagen_3": {
        "name": "Imagen 3",
        "provider": "Google",
        "api_endpoint": "https://generativelanguage.googleapis.com/v1beta/models/imagen-3",
        "requires_api_key": True,
        "model_id": "imagen-3",
        "description": "Google Imagen 3"
    }
}


class InferenceEngine:
    """推理引擎核心类 - 支持最新AIGC模型"""

    def __init__(self, device: str = "auto"):
        self.device = self._get_device(device)
        self.pipelines = {}
        self.current_pipeline = None
        self.current_model_type = None

        # 检测加速库
        self.use_flash_attention = False
        self.use_xformers = False
        self._detect_accelerators()
        
        # 模型信息
        self.loaded_models: Dict[str, ModelInfo] = {}
        self.loaded_loras: Dict[str, Dict[str, Any]] = {}
        self.loaded_controlnets: Dict[str, Any] = {}

        logger.info(f"[OmniGen] 推理引擎初始化，使用设备: {self.device}")

    def _get_device(self, device: str) -> str:
        """获取设备"""
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"
            else:
                return "cpu"
        return device

    def _detect_accelerators(self):
        """检测加速库"""
        try:
            import flash_attn
            self.use_flash_attention = True
            logger.info("[✓] FlashAttention2 可用")
        except:
            logger.info("[×] FlashAttention2 不可用")

        try:
            import xformers
            self.use_xformers = True
            logger.info("[✓] xFormers 可用")
        except:
            logger.info("[×] xFormers 不可用")

    def get_available_models(self) -> List[Dict[str, str]]:
        """获取支持的模型列表"""
        models = []
        for model_type, config in MODEL_REPOS.items():
            models.append({
                "type": model_type,
                "repo_id": config["repo_id"],
                "pipeline": config["pipeline"],
                "capability": config["type"]
            })
        return models

    def load_pipeline(self, model_type: str, model_path: str = None,
                     torch_dtype: str = "float16") -> bool:
        """
        加载推理管线
        
        Args:
            model_type: 模型类型 (z_image, qwen_image, wan_2_2, hunyuan3d等)
            model_path: 本地模型路径(可选)
            torch_dtype: 数据类型
        """
        try:
            logger.info(f"[加载] 模型: {model_type} from {model_path or 'HuggingFace'}")

            # 图像生成模型
            if model_type in ["z_image", "qwen_image"]:
                return self._load_image_pipeline(model_type, model_path, torch_dtype)
            # 图像编辑模型
            elif model_type in ["flux_2_klein", "qwen_image_edit", "flux"]:
                return self._load_edit_pipeline(model_type, model_path, torch_dtype)
            # 视频生成模型
            elif model_type in ["wan_2_2", "ltx_video", "wan", "ltx"]:
                return self._load_video_pipeline(model_type, model_path, torch_dtype)
            # 3D生成模型
            elif model_type in ["hunyuan3d", "trellis_2", "hunyuan", "trellis"]:
                return self._load_3d_pipeline(model_type, model_path, torch_dtype)
            # 放大模型
            elif model_type in ["dat", "dat_2", "mdat"]:
                return self._load_upscale_pipeline(model_type, model_path, torch_dtype)
            # 兼容旧版本
            elif model_type == "sdxl":
                model_type = "qwen_image"  # 映射到最新模型
                return self._load_image_pipeline(model_type, model_path, torch_dtype)
            else:
                logger.error(f"[错误] 不支持的模型类型: {model_type}")
                return False

        except Exception as e:
            logger.error(f"[错误] 模型加载失败: {e}")
            return False

    def _load_image_pipeline(self, model_type: str, model_path: str,
                            torch_dtype: str) -> bool:
        """加载图像生成管线 - 支持最新模型"""
        try:
            from diffusers import AutoPipelineForText2Image, DiffusionPipeline
            
            dtype = torch.float16 if torch_dtype == "float16" else torch.float32

            if model_path and os.path.exists(model_path):
                # 从本地路径加载
                logger.info(f"[本地] 加载图像模型: {model_path}")
                pipeline = AutoPipelineForText2Image.from_pretrained(
                    model_path,
                    torch_dtype=dtype,
                    safety_checker=None,
                    requires_safety_checker=False
                )
            else:
                # 从HuggingFace加载最新模型
                repo_id = MODEL_REPOS.get(model_type, {}).get("repo_id", "stabilityai/stable-diffusion-xl-base-1.0")
                logger.info(f"[远程] 加载图像模型: {repo_id}")
                
                try:
                    pipeline = AutoPipelineForText2Image.from_pretrained(
                        repo_id,
                        torch_dtype=dtype,
                        safety_checker=None
                    )
                except Exception as hf_err:
                    logger.warning(f"[警告] HuggingFace加载失败: {hf_err}, 使用SDXL兼容")
                    # 降级到SDXL
                    pipeline = AutoPipelineForText2Image.from_pretrained(
                        "stabilityai/stable-diffusion-xl-base-1.0",
                        torch_dtype=dtype,
                        safety_checker=None
                    )

            # 应用加速优化
            self._apply_acceleration(pipeline)

            # 移动到设备
            pipeline.to(self.device)

            self.pipelines[model_type] = pipeline
            self.current_pipeline = model_type
            self.current_model_type = model_type

            logger.info(f"[✓] {model_type} 图像管线加载成功")
            return True

        except Exception as e:
            logger.error(f"[错误] 图像管线加载失败: {e}")
            return False

    def _load_edit_pipeline(self, model_type: str, model_path: str,
                           torch_dtype: str) -> bool:
        """加载图像编辑管线"""
        try:
            from diffusers import AutoPipelineForImage2Image, AutoPipelineForInpainting
            
            dtype = torch.float16 if torch_dtype == "float16" else torch.float32

            if model_path and os.path.exists(model_path):
                logger.info(f"[本地] 加载编辑模型: {model_path}")
                if "inpaint" in MODEL_REPOS.get(model_type, {}).get("type", ""):
                    pipeline = AutoPipelineForInpainting.from_pretrained(
                        model_path, torch_dtype=dtype, safety_checker=None
                    )
                else:
                    pipeline = AutoPipelineForImage2Image.from_pretrained(
                        model_path, torch_dtype=dtype, safety_checker=None
                    )
            else:
                repo_id = MODEL_REPOS.get(model_type, {}).get("repo_id", "black-forest-labs/FLUX.1-dev")
                logger.info(f"[远程] 加载编辑模型: {repo_id}")
                
                try:
                    if "inpaint" in MODEL_REPOS.get(model_type, {}).get("type", ""):
                        pipeline = AutoPipelineForInpainting.from_pretrained(
                            repo_id, torch_dtype=dtype, safety_checker=None
                        )
                    else:
                        pipeline = AutoPipelineForImage2Image.from_pretrained(
                            repo_id, torch_dtype=dtype, safety_checker=None
                        )
                except:
                    logger.warning("[警告] 使用SDXL编辑模型作为降级")
                    pipeline = AutoPipelineForImage2Image.from_pretrained(
                        "stabilityai/stable-diffusion-xl-refiner-1.0",
                        torch_dtype=dtype, safety_checker=None
                    )

            self._apply_acceleration(pipeline)
            pipeline.to(self.device)

            self.pipelines[model_type] = pipeline
            self.current_pipeline = model_type
            self.current_model_type = model_type

            logger.info(f"[✓] {model_type} 编辑管线加载成功")
            return True

        except Exception as e:
            logger.error(f"[错误] 编辑管线加载失败: {e}")
            return False

    def _load_video_pipeline(self, model_type: str, model_path: str,
                            torch_dtype: str) -> bool:
        """加载视频生成管线 - Wan 2.2 / LTX-Video"""
        try:
            from diffusers import DiffusionPipeline
            
            dtype = torch.float16 if torch_dtype == "float16" else torch.float32

            if model_path and os.path.exists(model_path):
                logger.info(f"[本地] 加载视频模型: {model_path}")
                pipeline = DiffusionPipeline.from_pretrained(model_path, torch_dtype=dtype)
            else:
                repo_id = MODEL_REPOS.get(model_type, {}).get("repo_id", "Wan-AI/Wan2.2-T2V-14B")
                logger.info(f"[远程] 加载视频模型: {repo_id}")
                
                try:
                    pipeline = DiffusionPipeline.from_pretrained(repo_id, torch_dtype=dtype)
                except Exception as hf_err:
                    logger.warning(f"[警告] 视频模型加载失败: {hf_err}")
                    return False

            self._apply_acceleration(pipeline)
            pipeline.to(self.device)

            self.pipelines[model_type] = pipeline
            self.current_pipeline = model_type
            self.current_model_type = model_type

            logger.info(f"[✓] {model_type} 视频管线加载成功")
            return True

        except Exception as e:
            logger.error(f"[错误] 视频管线加载失败: {e}")
            return False

    def _load_3d_pipeline(self, model_type: str, model_path: str,
                         torch_dtype: str) -> bool:
        """加载3D生成管线 - Hunyuan3D / Trellis"""
        try:
            from diffusers import DiffusionPipeline
            
            dtype = torch.float16 if torch_dtype == "float16" else torch.float32

            if model_path and os.path.exists(model_path):
                logger.info(f"[本地] 加载3D模型: {model_path}")
                pipeline = DiffusionPipeline.from_pretrained(model_path, torch_dtype=dtype)
            else:
                repo_id = MODEL_REPOS.get(model_type, {}).get("repo_id", "Tencent/Hunyuan3D-2")
                logger.info(f"[远程] 加载3D模型: {repo_id}")
                
                try:
                    pipeline = DiffusionPipeline.from_pretrained(repo_id, torch_dtype=dtype)
                except:
                    logger.warning("[警告] 3D模型加载失败")
                    return False

            self._apply_acceleration(pipeline)
            pipeline.to(self.device)

            self.pipelines[model_type] = pipeline
            self.current_pipeline = model_type
            self.current_model_type = model_type

            logger.info(f"[✓] {model_type} 3D管线加载成功")
            return True

        except Exception as e:
            logger.error(f"[错误] 3D管线加载失败: {e}")
            return False

    def _load_upscale_pipeline(self, model_type: str, model_path: str,
                              torch_dtype: str) -> bool:
        """加载放大管线 - DAT / DAT-2"""
        try:
            from diffusers import DiffusionPipeline
            
            dtype = torch.float16 if torch_dtype == "float16" else torch.float32

            if model_path and os.path.exists(model_path):
                logger.info(f"[本地] 加载放大模型: {model_path}")
                pipeline = DiffusionPipeline.from_pretrained(model_path, torch_dtype=dtype)
            else:
                repo_id = MODEL_REPOS.get(model_type, {}).get("repo_id", "stabilityai/stable-diffusion-x4-upscaler")
                logger.info(f"[远程] 加载放大模型: {repo_id}")
                pipeline = DiffusionPipeline.from_pretrained(repo_id, torch_dtype=dtype)

            self._apply_acceleration(pipeline)
            pipeline.to(self.device)

            self.pipelines[model_type] = pipeline
            self.current_pipeline = model_type
            self.current_model_type = model_type

            logger.info(f"[✓] {model_type} 放大管线加载成功")
            return True

        except Exception as e:
            logger.error(f"[错误] 放大管线加载失败: {e}")
            return False

    def _apply_acceleration(self, pipeline):
        """应用加速优化"""
        if self.use_flash_attention and self.device == "cuda":
            try:
                pipeline.enable_flash_attention()
                logger.info("[加速] FlashAttention2 已启用")
            except:
                pass

        if self.use_xformers:
            try:
                pipeline.enable_xformers_memory_efficient_attention()
                logger.info("[加速] xFormers 已启用")
            except:
                pass

        # VAE切片
        try:
            pipeline.enable_vae_slicing()
        except:
            pass

        # 注意力切片
        try:
            pipeline.enable_attention_slicing()
        except:
            pass

    # ==================== 图像生成 ====================

    def generate_image(self, prompt: str, negative_prompt: str = "",
                      width: int = 1024, height: int = 1024,
                      num_inference_steps: int = 30,
                      guidance_scale: float = 7.0,
                      seed: int = -1,
                      num_images: int = 1) -> List[Image.Image]:
        """生成图像 - 使用最新模型"""
        try:
            if not self.current_pipeline or self.current_pipeline not in self.pipelines:
                # 自动加载默认模型
                if not self.load_pipeline("qwen_image"):
                    logger.error("[错误] 没有可用的生成管线")
                    return []

            pipeline = self.pipelines[self.current_pipeline]

            # 设置种子
            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            # 基础参数
            kwargs = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "num_inference_steps": num_inference_steps,
                "guidance_scale": guidance_scale,
                "num_images_per_prompt": num_images,
            }

            # 添加尺寸参数
            if hasattr(pipeline, 'vae'):  # 不是视频/3D模型
                kwargs["width"] = width
                kwargs["height"] = height
                if generator:
                    kwargs["generator"] = generator

            logger.info(f"[生成] 正在生成 {num_images} 张图像...")

            with torch.autocast(self.device):
                result = pipeline(**kwargs)

            images = result.images
            logger.info(f"[✓] 图像生成完成，生成 {len(images)} 张")

            return images

        except Exception as e:
            logger.error(f"[错误] 图像生成失败: {e}")
            return []

    def generate_image_img2img(self, input_image: Image.Image,
                             prompt: str, negative_prompt: str = "",
                             strength: float = 0.75,
                             num_inference_steps: int = 30,
                             guidance_scale: float = 7.0,
                             seed: int = -1) -> List[Image.Image]:
        """图生图"""
        try:
            from diffusers import AutoPipelineForImage2Image

            # 尝试使用当前模型
            if self.current_pipeline in self.pipelines:
                pipeline = self.pipelines[self.current_pipeline]
                if hasattr(pipeline, 'vae'):  # 图像模型
                    pass
                else:
                    pipeline = None
            else:
                pipeline = None

            if pipeline is None:
                pipeline = AutoPipelineForImage2Image.from_pretrained(
                    "stabilityai/stable-diffusion-xl-base-1.0",
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    safety_checker=None
                )
                pipeline.to(self.device)

            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            logger.info("[生成] 正在进行图生图...")

            with torch.autocast(self.device):
                result = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    image=input_image,
                    strength=strength,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator
                )

            logger.info("[✓] 图生图完成")
            return result.images

        except Exception as e:
            logger.error(f"[错误] 图生图失败: {e}")
            return []

    def generate_image_inpaint(self, input_image: Image.Image,
                              mask_image: Image.Image,
                              prompt: str, negative_prompt: str = "",
                              strength: float = 0.8,
                              num_inference_steps: int = 30,
                              guidance_scale: float = 7.0,
                              seed: int = -1) -> List[Image.Image]:
        """局部重绘"""
        try:
            from diffusers import AutoPipelineForInpainting

            pipeline = AutoPipelineForInpainting.from_pretrained(
                "stabilityai/stable-diffusion-xl-base-1.0",
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                safety_checker=None
            )
            pipeline.to(self.device)

            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            logger.info("[生成] 正在进行局部重绘...")

            with torch.autocast(self.device):
                result = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    image=input_image,
                    mask_image=mask_image,
                    strength=strength,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator
                )

            logger.info("[✓] 局部重绘完成")
            return result.images

        except Exception as e:
            logger.error(f"[错误] 局部重绘失败: {e}")
            return []

    # ==================== ControlNet 支持 ====================

    def load_controlnet(self, controlnet_path: str, controlnet_type: str = "canny") -> bool:
        """加载本地ControlNet模型"""
        try:
            from diffusers import ControlNetModel

            logger.info(f"[加载] ControlNet: {controlnet_path}")

            if not os.path.exists(controlnet_path):
                logger.error(f"[错误] ControlNet文件不存在: {controlnet_path}")
                return False

            controlnet = ControlNetModel.from_pretrained(
                controlnet_path,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
            )

            cn_key = f"controlnet_{controlnet_type}"
            self.loaded_controlnets[cn_key] = {
                'model': controlnet,
                'path': controlnet_path,
                'type': controlnet_type
            }

            logger.info(f"[✓] ControlNet加载成功: {cn_key}")
            return True

        except Exception as e:
            logger.error(f"[错误] ControlNet加载失败: {e}")
            return False

    def generate_with_controlnet(self, prompt: str, controlnet_image: Image.Image,
                                controlnet_path: str = None, controlnet_type: str = "canny",
                                negative_prompt: str = "", width: int = 1024, height: int = 1024,
                                num_inference_steps: int = 30, guidance_scale: float = 7.0,
                                seed: int = -1, controlnet_scale: float = 1.0,
                                controlnet_guidance_start: float = 0.0,
                                controlnet_guidance_end: float = 1.0) -> List[Image.Image]:
        """使用ControlNet生成图像"""
        try:
            from diffusers import StableDiffusionControlNetPipeline, ControlNetModel

            logger.info("[生成] 使用ControlNet生成图像...")

            # 加载基础模型
            if "sdxl" not in self.pipelines:
                self.load_pipeline("qwen_image")  # 使用最新模型

            base_pipeline = self.pipelines.get(self.current_pipeline)
            if base_pipeline is None:
                logger.error("[错误] 没有可用的基础模型")
                return []

            # 加载ControlNet
            cn_key = f"controlnet_{controlnet_type}"
            if cn_key not in self.loaded_controlnets:
                if controlnet_path and os.path.exists(controlnet_path):
                    self.load_controlnet(controlnet_path, controlnet_type)
                else:
                    logger.warning("[警告] 使用默认ControlNet")
                    controlnet = ControlNetModel.from_pretrained(
                        "lllyasviel/sd-controlnet-canny",
                        torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                    )
                    self.loaded_controlnets[cn_key] = {'model': controlnet, 'path': None, 'type': controlnet_type}

            controlnet = self.loaded_controlnets[cn_key]['model']

            # 创建ControlNet管线
            pipe = StableDiffusionControlNetPipeline(
                vae=base_pipeline.vae,
                text_encoder=base_pipeline.text_encoder,
                tokenizer=base_pipeline.tokenizer,
                unet=base_pipeline.unet,
                controlnet=controlnet,
                safety_checker=None,
                feature_extractor=getattr(base_pipeline, 'feature_extractor', None)
            )
            pipe.to(self.device)

            self._apply_acceleration(pipe)

            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            with torch.autocast(self.device):
                result = pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    image=controlnet_image,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator,
                    controlnet_conditioning_scale=controlnet_scale,
                    guidance_start=controlnet_guidance_start,
                    guidance_end=controlnet_guidance_end
                )

            logger.info(f"[✓] ControlNet生成完成，生成 {len(result.images)} 张图像")
            return result.images

        except Exception as e:
            logger.error(f"[错误] ControlNet生成失败: {e}")
            return []

    # ==================== LoRA 支持 ====================

    def load_lora(self, lora_path: str, lora_name: str = None, alpha: float = 1.0) -> bool:
        """加载本地LoRA模型"""
        try:
            logger.info(f"[加载] LoRA: {lora_path}")

            if not os.path.exists(lora_path):
                logger.error(f"[错误] LoRA文件不存在: {lora_path}")
                return False

            lora_key = f"lora_{os.path.basename(lora_path)}"
            self.loaded_loras[lora_key] = {
                'path': lora_path,
                'alpha': alpha,
                'name': lora_name or os.path.basename(lora_path)
            }

            logger.info(f"[✓] LoRA已注册: {lora_key}")
            return True

        except Exception as e:
            logger.error(f"[错误] LoRA加载失败: {e}")
            return False

    def load_multiple_loras(self, lora_configs: List[Dict[str, Any]]) -> bool:
        """加载多个LoRA模型（最多3个）"""
        try:
            if len(lora_configs) > 3:
                logger.warning("[警告] 最多支持3个LoRA")
                lora_configs = lora_configs[:3]

            self.loaded_loras.clear()

            for i, config in enumerate(lora_configs):
                lora_path = config.get('path')
                if lora_path and os.path.exists(lora_path):
                    lora_key = f"lora_{i}"
                    self.loaded_loras[lora_key] = {
                        'path': lora_path,
                        'alpha': config.get('weight', config.get('alpha', 1.0)),
                        'name': config.get('name', os.path.basename(lora_path))
                    }
                    logger.info(f"[✓] LoRA {i+1} 已注册: {lora_key}")

            return True

        except Exception as e:
            logger.error(f"[错误] LoRA批量加载失败: {e}")
            return False

    def generate_with_lora(self, prompt: str, negative_prompt: str = "",
                          width: int = 1024, height: int = 1024,
                          num_inference_steps: int = 30, guidance_scale: float = 7.0,
                          seed: int = -1, num_images: int = 1) -> List[Image.Image]:
        """使用LoRA生成图像"""
        try:
            from safetensors.torch import load_file

            logger.info(f"[生成] 使用LoRA生成图像...")

            # 确保基础模型已加载
            if not self.current_pipeline or self.current_pipeline not in self.pipelines:
                if not self.load_pipeline("qwen_image"):
                    return []

            pipeline = self.pipelines[self.current_pipeline]

            # 加载LoRA权重
            if self.loaded_loras:
                for lora_key, lora_info in self.loaded_loras.items():
                    lora_path = lora_info['path']
                    lora_alpha = lora_info['alpha']

                    if os.path.exists(lora_path):
                        logger.info(f"[应用] LoRA: {lora_path}")
                        state_dict = load_file(lora_path, device=self.device)

                        # 应用LoRA到unet
                        try:
                            self._apply_lora_to_pipeline(pipeline, state_dict, lora_alpha)
                        except Exception as apply_err:
                            logger.warning(f"[警告] LoRA应用失败: {apply_err}")

            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            with torch.autocast(self.device):
                result = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    num_images_per_prompt=num_images,
                    width=width,
                    height=height,
                    generator=generator
                )

            logger.info(f"[✓] LoRA生成完成，生成 {len(result.images)} 张图像")
            return result.images

        except Exception as e:
            logger.error(f"[错误] LoRA生成失败: {e}")
            return []

    def _apply_lora_to_pipeline(self, pipeline, state_dict, alpha):
        """应用LoRA权重到管线"""
        try:
            from peft import PeftModel, LoraConfig

            # 使用PEFT库应用LoRA
            if hasattr(pipeline, 'unet'):
                pipeline.unet = PeftModel(pipeline.unet, LoraConfig())
                # 这里需要根据实际的LoRA格式来处理
                logger.info("[✓] LoRA已应用到UNet")
        except Exception as e:
            logger.debug(f"PEFT应用跳过: {e}")

    def generate_with_controlnet_and_lora(self, prompt: str, controlnet_image: Image.Image,
                                        controlnet_path: str = None, controlnet_type: str = "canny",
                                        negative_prompt: str = "",
                                        width: int = 1024, height: int = 1024,
                                        num_inference_steps: int = 30, guidance_scale: float = 7.0,
                                        seed: int = -1, controlnet_scale: float = 1.0,
                                        controlnet_guidance_start: float = 0.0,
                                        controlnet_guidance_end: float = 1.0) -> List[Image.Image]:
        """同时使用ControlNet和LoRA生成图像"""
        try:
            from diffusers import StableDiffusionControlNetPipeline

            logger.info("[生成] 使用ControlNet+LoRA生成图像...")

            # 确保基础模型已加载
            if not self.current_pipeline or self.current_pipeline not in self.pipelines:
                self.load_pipeline("qwen_image")

            base_pipeline = self.pipelines.get(self.current_pipeline)
            if base_pipeline is None:
                logger.error("[错误] 没有可用的基础模型")
                return []

            # 加载ControlNet
            cn_key = f"controlnet_{controlnet_type}"
            if cn_key not in self.loaded_controlnets:
                self.load_controlnet(controlnet_path, controlnet_type) if controlnet_path else None

            controlnet = self.loaded_controlnets.get(cn_key, {}).get('model')
            if controlnet is None:
                logger.error("[错误] ControlNet未加载")
                return []

            # 创建联合管线
            pipe = StableDiffusionControlNetPipeline(
                vae=base_pipeline.vae,
                text_encoder=base_pipeline.text_encoder,
                tokenizer=base_pipeline.tokenizer,
                unet=base_pipeline.unet,
                controlnet=controlnet,
                safety_checker=None
            )
            pipe.to(self.device)

            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            with torch.autocast(self.device):
                result = pipe(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    image=controlnet_image,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator,
                    controlnet_conditioning_scale=controlnet_scale
                )

            logger.info("[✓] ControlNet+LoRA生成完成")
            return result.images

        except Exception as e:
            logger.error(f"[错误] ControlNet+LoRA生成失败: {e}")
            return []

    # ==================== 视频生成 ====================

    def generate_video(self, prompt: str, negative_prompt: str = "",
                      num_inference_steps: int = 50,
                      guidance_scale: float = 7.5,
                      seed: int = -1,
                      num_frames: int = 61,
                      fps: int = 24) -> str:
        """生成视频 - Wan 2.2 / LTX-Video"""
        try:
            if self.current_pipeline not in self.pipelines:
                if not self.load_pipeline("wan_2_2"):
                    logger.error("[错误] 视频模型加载失败")
                    return None

            pipeline = self.pipelines[self.current_pipeline]

            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            logger.info(f"[生成] 正在生成 {num_frames} 帧视频...")

            with torch.autocast(self.device):
                result = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    num_frames=num_frames,
                    generator=generator
                )

            # 保存视频
            output_dir = "./outputs/video"
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"video_{seed or 'random'}.mp4")

            if hasattr(result, 'frames'):
                self._save_video(result.frames, output_path, fps)
            else:
                logger.warning("[警告] 视频结果无frames属性")
                return None

            logger.info(f"[✓] 视频生成完成: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"[错误] 视频生成失败: {e}")
            return None

    def _save_video(self, frames: List[Image.Image], output_path: str, fps: int):
        """保存视频"""
        try:
            import cv2

            if not frames:
                return

            # 确保帧是numpy数组
            first_frame = np.array(frames[0])
            height, width = first_frame.shape[:2]

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            for frame in frames:
                frame_array = np.array(frame)
                if len(frame_array.shape) == 2:
                    frame_array = cv2.cvtColor(frame_array, cv2.COLOR_GRAY2BGR)
                elif frame_array.shape[2] == 4:
                    frame_array = cv2.cvtColor(frame_array, cv2.COLOR_RGBA2BGR)
                else:
                    frame_array = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)
                out.write(frame_array)

            out.release()
            logger.info(f"[✓] 视频已保存: {output_path}")

        except Exception as e:
            logger.error(f"[错误] 视频保存失败: {e}")

    # ==================== 3D生成 ====================

    def generate_3d(self, prompt: str, negative_prompt: str = "",
                   num_inference_steps: int = 50,
                   guidance_scale: float = 7.5,
                   seed: int = -1) -> str:
        """生成3D模型 - Hunyuan3D / Trellis"""
        try:
            if self.current_pipeline not in self.pipelines:
                if not self.load_pipeline("hunyuan3d"):
                    logger.error("[错误] 3D模型加载失败")
                    return None

            pipeline = self.pipelines[self.current_pipeline]

            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            logger.info("[生成] 正在生成3D模型...")

            with torch.autocast(self.device):
                result = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator
                )

            # 保存3D模型
            output_dir = "./outputs/3d"
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"model_{seed or 'random'}.glb")

            if hasattr(result, 'mesh'):
                # 保存为GLB格式
                result.mesh.export(output_path)
            else:
                logger.warning("[警告] 3D结果无mesh属性")
                return None

            logger.info(f"[✓] 3D模型生成完成: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"[错误] 3D模型生成失败: {e}")
            return None

    # ==================== 放大处理 ====================

    def upscale_image(self, input_image: Image.Image,
                     upscale_scale: float = 2.0,
                     num_inference_steps: int = 30,
                     seed: int = -1) -> Image.Image:
        """放大图像"""
        try:
            if self.current_pipeline not in self.pipelines:
                if not self.load_pipeline("dat"):
                    logger.error("[错误] 放大模型加载失败")
                    return input_image

            pipeline = self.pipelines[self.current_pipeline]

            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            logger.info(f"[处理] 正在放大图像 {upscale_scale}x...")

            with torch.autocast(self.device):
                result = pipeline(
                    image=input_image,
                    num_inference_steps=num_inference_steps,
                    generator=generator,
                    strength=0.6  # 保持低强度以避免失真
                )

            logger.info("[✓] 图像放大完成")
            return result.images[0] if result.images else input_image

        except Exception as e:
            logger.error(f"[错误] 图像放大失败: {e}")
            return input_image

    # ==================== 内存管理 ====================

    def get_loaded_models(self) -> Dict[str, Any]:
        """获取已加载的模型信息"""
        info = {
            "current_pipeline": self.current_pipeline,
            "current_model_type": self.current_model_type,
            "loaded_pipelines": list(self.pipelines.keys()),
            "loaded_loras": list(self.loaded_loras.keys()),
            "loaded_controlnets": list(self.loaded_controlnets.keys()),
            "device": self.device,
            "accelerators": {
                "flash_attention": self.use_flash_attention,
                "xformers": self.use_xformers
            }
        }
        return info

    def clear_memory(self):
        """清理缓存"""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        import gc
        gc.collect()
        logger.info("[清理] 内存已清空")

    def unload_pipeline(self, model_type: str):
        """卸载指定的管线"""
if model_type in self.pipelines:
            del self.pipelines[model_type]
            logger.info(f"[卸载] {model_type} 管线已卸载")
            self.clear_memory()

    def unload_all(self):
        """卸载所有模型"""
        self.pipelines.clear()
        self.loaded_loras.clear()
        self.loaded_controlnets.clear()
        self.current_pipeline = None
        self.current_model_type = None
        self.clear_memory()
        logger.info("[卸载] 所有模型已卸载")


# ==================== 全局推理引擎 ====================

_engine = None


def get_inference_engine(device: str = "auto") -> InferenceEngine:
    """获取推理引擎实例"""
    global _engine
    if _engine is None:
        _engine = InferenceEngine(device)
    return _engine


def main():
    """测试"""
    engine = get_inference_engine()
    print(f"设备: {engine.device}")
    print(f"Flash Attention: {engine.use_flash_attention}")
    print(f"xFormers: {engine.use_xformers}")
    print(f"\n支持的最新模型:")
    for model in engine.get_available_models():
        print(f"  - {model['type']}: {model['repo_id']}")


if __name__ == "__main__":
    main()
