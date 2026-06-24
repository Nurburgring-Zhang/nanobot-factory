#!/usr/bin/env python3
"""
Nanobot Factory - Unified Production Workbench Backend
统一生产工作台后端 - 支持多种生成服务

支持的生成服务：
1. Omni Gen Studio 本地 ComfyUI
2. 外部 ComfyUI（本地/云端）
3. 第三方 API（Seedream5, Seedance2, Kling, GPT等）

@author MiniMax Agent
@date 2026-02-26
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


# =============================================================================
# Provider Types
# =============================================================================

class ProviderType(Enum):
    """生成服务提供商类型 - 支持最新AIGC模型"""
    # 本地服务
    OMNI_GEN_LOCAL = "omni_gen_local"      # Omni Gen Studio 本地
    COMFYUI_LOCAL = "comfyui_local"        # 本地 ComfyUI
    COMFYUI_CLOUD = "comfyui_cloud"        # 云端 ComfyUI

    # 图像生成 (2025-2026年最新模型)
    Z_IMAGE = "z_image"                    # Z Image (字节跳动)
    QWEN_IMAGE = "qwen_image"              # Qwen Image (阿里)
    SEEDREAM5 = "seedream5"               # Seedream 5.0
    NANOBANANA = "nanobanana"              # Nano Banana 2
    NANOBANANA_PRO = "nanobanana_pro"      # Nano Banana Pro
    FLUX2_KLEIN = "flux2_klein"            # Flux 2 Klein (Black Forest Labs)

    # 视频生成 (2025-2026年最新模型)
    WAN2_X = "wan2_x"                      # Wan 2.x (字节跳动)
    LTVX_2 = "ltvx_2"                      # LTVX-2
    SEEDANCE2 = "seedance2"                # Seedance 2.0
    VOE3_1 = "voe3_1"                      # Voe 3.1
    KLING = "kling"                        # 可灵 1.6/2.0

    # 图像编辑 (2025-2026年最新模型)
    QWEN_IMAGE_EDIT = "qwen_image_edit"    # Qwen Image Edit (阿里)
    IMAGE_EDIT = "image_edit"              # 通用图像编辑
    IMAGE_UPSCALE = "image_upscale"        # 图片放大

    # 3D生成 (2025-2026年最新模型)
    TRELLIS = "trellis"                    # TRELLIS (Microsoft)
    HUNYUAN3D = "hunyuan3d"                # Hunyuan-3D (腾讯)
    TRIPOSR = "triposr"                   # TripoSR 3D生成
    LGM = "lgm"                           # LGM 3D生成
    SV3D = "sv3d"                         # Stable Video 3D

    # 传统API
    GPT = "gpt"                           # GPT (DALL-E)
    STABLE_DIFFUSION = "stable_diffusion"  # Stable Diffusion API
    MIDJOURNEY = "midjourney"             # Midjourney


class GenerationType(Enum):
    """生成类型"""
    IMAGE = "image"
    VIDEO = "video"
    IMAGE_EDIT = "image_edit"
    IMAGE_UPSCALE = "image_upscale"
    IMAGE_VARIATION = "image_variation"
    IMAGE_TO_3D = "image_to_3d"
    TEXT_TO_3D = "text_to_3D"
    IMAGE_TO_VIDEO = "image_to_video"


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class ProviderConfig:
    """提供商配置"""
    provider_type: ProviderType
    name: str
    enabled: bool = True
    # ComfyUI 配置
    comfyui_url: str = ""
    comfyui_port: int = 8188
    comfyui_workflow: str = ""
    # API 配置
    api_key: str = ""
    api_endpoint: str = ""
    # 自定义配置
    extra_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationRequest:
    """生成请求"""
    request_id: str
    provider_type: ProviderType
    generation_type: GenerationType
    prompt: str
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 20
    cfg_scale: float = 7.0
    seed: int = -1
    sampler: str = "euler"
    scheduler: str = "normal"
    # 模型配置
    model: str = ""
    # LoRA 配置
    lora_configs: List[Dict[str, Any]] = field(default_factory=list)
    # ControlNet 配置
    controlnet_configs: List[Dict[str, Any]] = field(default_factory=list)
    # 图像上传
    input_images: List[str] = field(default_factory=list)
    # 批量生成
    batch_count: int = 1
    # 视频参数
    duration: int = 5
    fps: int = 24
    video_frames: int = 0
    first_frame: str = ""
    last_frame: str = ""
    reference_images: List[str] = field(default_factory=list)
    # 编辑参数
    edit_type: str = ""
    source_image: str = ""
    mask_image: str = ""
    strength: float = 0.75
    # 高级
    clip_skip: int = 0
    eta: float = 0.0
    vae: str = ""
    style_preset: str = ""
    # 放大
    upscale_model: str = "realesrgan_x4plus"
    upscale_scale: int = 2
    face_enhance: bool = False
    tile_size: int = 512
    # 视频高级
    camera_type: str = ""
    loop: bool = False
    motion_bucket_id: int = 127
    # 3D
    export_format: str = "glb"
    texture_resolution: int = 2048
    remove_background: bool = True
    # 后处理
    filter_type: str = ""
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    temperature: float = 0.0
    tint: float = 0.0
    # 额外参数
    extra_params: Dict[str, Any] = field(default_factory=dict)
    # Nanobot 上下文
    nanobot_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationResult:
    """生成结果"""
    request_id: str
    status: str  # pending, processing, completed, failed
    provider: str
    progress: float = 0.0
    images: List[str] = field(default_factory=list)
    videos: List[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    completed_at: Optional[str] = None


@dataclass
class WorkflowTemplate:
    """工作流模板"""
    template_id: str
    name: str
    description: str
    provider_type: ProviderType
    workflow_json: Dict[str, Any]
    is_default: bool = False


# =============================================================================
# Base Provider
# =============================================================================

class BaseProvider:
    """生成服务提供商基类"""

    def __init__(self, config: ProviderConfig):
        self.config = config
        self.name = config.name

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """执行生成"""
        raise NotImplementedError

    async def get_status(self, request_id: str) -> GenerationResult:
        """获取生成状态"""
        raise NotImplementedError

    async def cancel(self, request_id: str) -> bool:
        """取消生成"""
        raise NotImplementedError

    async def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型"""
        raise NotImplementedError

    def validate_request(self, request: GenerationRequest) -> tuple[bool, Optional[str]]:
        """验证请求"""
        if not request.prompt:
            return False, "Prompt cannot be empty"
        return True, None


# =============================================================================
# ComfyUI Provider
# =============================================================================

class ComfyUIProvider(BaseProvider):
    """ComfyUI 提供商"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.base_url = config.comfyui_url or f"http://localhost:{config.comfyui_port}"
        # 禁用演示模式 - 强制使用真实API
        self._demo_mode = False

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """通过 ComfyUI 生成"""
        # 构建 prompt
        prompt_data = self._build_prompt(request)

        try:
            # 发送到 ComfyUI
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # 队列请求
                async with session.post(
                    f"{self.base_url}/prompt",
                    json={"prompt": prompt_data}
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            created_at=datetime.now().isoformat()
                        )
                    else:
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"ComfyUI error: {resp.status}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            # ComfyUI不可用时抛出真实错误，而不是返回模拟结果
            logger.error(f"ComfyUI not available: {e}")
            raise ConnectionError(
                f"ComfyUI service is not available at {self.base_url}. "
                f"Please ensure ComfyUI is running or configure the correct endpoint. "
                f"Original error: {str(e)}"
            )

    def _build_prompt(self, request: GenerationRequest) -> Dict[str, Any]:
        """构建 ComfyUI prompt"""
        # 这里简化处理，实际需要根据 workflow_json 构建
        return {
            "3": {
                "inputs": {
                    "seed": request.seed if request.seed > 0 else int(datetime.now().timestamp()),
                    "steps": request.steps,
                    "cfg": request.cfg_scale,
                    "sampler_name": request.sampler,
                    "scheduler": request.scheduler,
                    "positive": request.prompt,
                    "negative": request.negative_prompt,
                    "width": request.width,
                    "height": request.height,
                    "model": [" модели ", 0],
                },
                "class_type": "KSampler"
            }
        }

    async def get_status(self, request_id: str) -> GenerationResult:
        """获取状态 - 需要实现历史记录查询"""
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        """取消生成"""
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型"""
        return []


# =============================================================================
# Third-party API Providers
# =============================================================================

class Seedream5Provider(BaseProvider):
    """Seedream5 提供商"""

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """通过 Seedream5 API 生成"""
        if not self.config.api_key:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=self.config.provider_type.value,
                error="API key not configured",
                created_at=datetime.now().isoformat()
            )

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.api_endpoint or "https://api.seedream5.com/v1/generate",
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "prompt": request.prompt,
                        "negative_prompt": request.negative_prompt,
                        "width": request.width,
                        "height": request.height,
                        "num_images": request.batch_count,
                    }
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            progress=100.0,
                            images=[result.get("image_url", "")],
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"API error: {resp.status}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=self.config.provider_type.value,
                error=str(e),
                created_at=datetime.now().isoformat()
            )

    def _generate_simulated_result(self, request: GenerationRequest) -> GenerationResult:
        """生成模拟结果用于演示"""
        images = []
        count = request.batch_count or 1

        for i in range(count):
            width = request.width or 1024
            height = request.height or 1024
            svg_content = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="#1a1a2e"/>
                <text x="50%" y="50%" font-family="Arial" font-size="48" fill="white" text-anchor="middle" dominant-baseline="middle">
                    AI Generated Image {i+1}
                </text>
                <text x="50%" y="60%" font-family="Arial" font-size="24" fill="#aaa" text-anchor="middle">
                    {request.prompt[:50]}...
                </text>
            </svg>'''
            import base64
            b64 = base64.b64encode(svg_content.encode()).decode()
            images.append(f"data:image/svg+xml;base64,{b64}")

        return GenerationResult(
            request_id=request.request_id,
            status="completed",
            provider=self.config.provider_type.value,
            images=images,
                        metadata={"simulated": True},
            created_at=datetime.now().isoformat()
        )


# =============================================================================
# OmniGen Studio Provider - 集成omni_gen_studio的ComfyUI
# =============================================================================

class OmniGenStudioProvider(BaseProvider):
    """OmniGen Studio 提供商 - 直接集成omni_gen_studio的ComfyUI

    支持的功能:
    - 图片生成 (SD/SDXL/SD3/Flux)
    - 视频生成 (wan/ltx-2)
    - 图片编辑 (局部重绘/风格转换)
    - LoRA加载 (最多3个)
    - 提示词优化
    - 多种采样器和调度器
    """

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        # omni_gen_studio的ComfyUI默认端口
        self.comfyui_port = config.comfyui_port or 8188
        self.comfyui_url = config.comfyui_url or f"http://localhost:{self.comfyui_port}"
        self.omni_gen_dir = Path(__file__).parent / "omni_gen_studio"

        # 检查omni_gen_studio是否可用
        self.omni_gen_available = self._check_omni_gen_studio()

        # 支持的模型类型
        self.supported_models = {
            "sd15": "stable-diffusion-v1-5",
            "sdxl": "stable-diffusion-xl-base-1.0",
            "sd3": "stable-diffusion-3-medium",
            "flux": "flux-schnell",
            "flux_dev": "flux-dev",
            "wan": "wan2.1",
            "ltx": "ltx-video",
            "qwen": "qwen2vl",
            "qwen_edit": "qwen2vl-edit",
        }

    def _check_omni_gen_studio(self) -> bool:
        """检查omni_gen_studio是否可用"""
        comfyui_dir = self.omni_gen_dir / "ComfyUI"
        if not comfyui_dir.exists():
            logger.warning(f"OmniGen Studio ComfyUI not found at {comfyui_dir}")
            return False

        # 检查必要的文件
        main_py = comfyui_dir / "main.py"
        if not main_py.exists():
            logger.warning("OmniGen Studio main.py not found")
            return False

        return True

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """通过 OmniGen Studio 生成"""
        # 根据生成类型选择不同的生成方法
        generation_type = request.extra_params.get("generation_type", "image") if request.extra_params else "image"

        if generation_type == "video":
            return await self._generate_video(request)
        elif generation_type == "edit":
            return await self._generate_edit(request)
        else:
            return await self._generate_image(request)

    async def _generate_image(self, request: GenerationRequest) -> GenerationResult:
        """生成图片"""
        # 首先尝试通过ComfyUI API调用
        try:
            return await self._generate_via_comfyui(request)
        except Exception as e:
            logger.warning(f"OmniGen Studio generate failed: {e}")
            # 如果失败，尝试使用omni_gen_studio的直接推理
            return await self._generate_via_omnigen(request)

    async def _generate_video(self, request: GenerationRequest) -> GenerationResult:
        """生成视频"""
        # 通过ComfyUI调用视频生成
        try:
            return await self._generate_video_via_comfyui(request)
        except Exception as e:
            logger.error(f"OmniGen Studio video generate failed: {e}")
            raise ConnectionError(
                f"Video generation service is not available. "
                f"Please ensure ComfyUI is running with video generation nodes installed. "
                f"Original error: {str(e)}"
            )

    async def _generate_edit(self, request: GenerationRequest) -> GenerationResult:
        """编辑图片"""
        # 通过ComfyUI调用图片编辑
        try:
            return await self._generate_edit_via_comfyui(request)
        except Exception as e:
            logger.error(f"OmniGen Studio edit failed: {e}")
            raise ConnectionError(
                f"Image editing service is not available. "
                f"Please ensure ComfyUI is running with editing nodes installed. "
                f"Original error: {str(e)}"
            )

    async def _generate_via_comfyui(self, request: GenerationRequest) -> GenerationResult:
        """通过ComfyUI API生成图片"""
        # 构建prompt，支持LoRA
        prompt_data = self._build_image_prompt(request)

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": prompt_data},
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            created_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        raise Exception(f"ComfyUI error {resp.status}: {error_text}")
        except Exception as e:
            raise Exception(f"ComfyUI API call failed: {e}")

    async def _generate_video_via_comfyui(self, request: GenerationRequest) -> GenerationResult:
        """通过ComfyUI API生成视频"""
        prompt_data = self._build_video_prompt(request)

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": prompt_data},
                    timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            created_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        raise Exception(f"ComfyUI video error {resp.status}: {error_text}")
        except Exception as e:
            raise Exception(f"ComfyUI video API call failed: {e}")

    async def _generate_edit_via_comfyui(self, request: GenerationRequest) -> GenerationResult:
        """通过ComfyUI API编辑图片"""
        prompt_data = self._build_edit_prompt(request)

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.comfyui_url}/prompt",
                    json={"prompt": prompt_data},
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            created_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        raise Exception(f"ComfyUI edit error {resp.status}: {error_text}")
        except Exception as e:
            raise Exception(f"ComfyUI edit API call failed: {e}")

    async def _generate_via_omnigen(self, request: GenerationRequest) -> GenerationResult:
        """通过omni_gen_studio直接推理"""
        # 尝试使用omni_gen_studio的diffuser进行推理
        try:
            result = await self._run_diffuser_inference(request)
            return result
        except Exception as e:
            logger.error(f"OmniGen Studio inference failed: {e}")
            # OmniGen不可用时抛出真实错误
            raise ConnectionError(
                f"OmniGen Studio inference failed. Please ensure the required dependencies "
                f"(torch, diffusers) are installed and the model is available. "
                f"Original error: {str(e)}"
            )

    async def _run_diffuser_inference(self, request: GenerationRequest) -> GenerationResult:
        """使用diffuser进行REAL推理"""
        try:
            import torch
            from diffusers import StableDiffusionPipeline, DiffusionPipeline
            import asyncio

            model_id = request.model or "stabilityai/stable-diffusion-2-1"
            logger.info(f"Loading Diffusers model: {model_id}")

            # 检查是否有GPU
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Using device: {device}")

            # 加载模型 (使用较小的模型以加快加载速度)
            # 实际生产中可以使用更大的模型
            try:
                pipe = StableDiffusionPipeline.from_pretrained(
                    model_id,
                    torch_dtype=torch.float16 if device == "cuda" else torch.float32,
                    safety_checker=None,
                    requires_safety_checker=False,
                )
                pipe = pipe.to(device)

                # 生成图片
                logger.info(f"Generating image with prompt: {request.prompt[:50]}...")

                # 构建生成参数
                gen_kwargs = {
                    "prompt": request.prompt,
                    "negative_prompt": request.negative_prompt or "",
                    "num_inference_steps": request.steps or 25,
                    "guidance_scale": request.guidance_scale or 7.5,
                    "height": request.height or 512,
                    "width": request.width or 512,
                }

                if request.seed > 0:
                    gen_kwargs["generator"] = torch.Generator(device).manual_seed(request.seed)

                # 执行生成
                result = pipe(**gen_kwargs)

                # 保存结果
                output_dir = Path("./outputs")
                output_dir.mkdir(exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = output_dir / f"diffuser_{timestamp}.png"

                result.images[0].save(output_path)

                logger.info(f"Image saved to: {output_path}")

                return GenerationResult(
                    success=True,
                    output_path=str(output_path),
                    output_type="image",
                    metadata={
                        "model": model_id,
                        "device": device,
                        "prompt": request.prompt,
                        "seed": request.seed or timestamp,
                        "steps": request.steps or 25,
                        "guidance_scale": request.guidance_scale or 7.5
                    }
                )

            except Exception as e:
                logger.warning(f"Failed to load model {model_id}: {e}")
                # 如果模型加载失败，尝试使用更小的模型
                raise Exception(f"Model loading failed: {str(e)}")

        except ImportError as e:
            logger.warning(f"Diffusers not available: {e}")
            raise Exception("Diffusers module not available - please install: pip install diffusers transformers")
        except Exception as e:
            logger.warning(f"Diffuser inference failed: {e}")
            raise e

    def _build_image_prompt(self, request: GenerationRequest) -> Dict[str, Any]:
        """构建ComfyUI图片生成prompt，支持LoRA"""
        seed = request.seed if request.seed > 0 else int(datetime.now().timestamp())

        # 构建LoRA节点
        lora_nodes = {}
        loras = request.extra_params.get("loras", []) if request.extra_params else []

        for i, lora in enumerate(loras[:3]):  # 最多3个LoRA
            lora_nodes[f"lora_{i}"] = {
                "inputs": {
                    "model": ["ksampler", 0],
                    "clip": ["clip", 0],
                    "lora_name": lora.get("name", ""),
                    "strength_model": lora.get("strength_model", 1.0),
                    "strength_clip": lora.get("strength_clip", 1.0),
                },
                "class_type": "LoraLoader"
            }

        # 构建基础prompt
        prompt = {
            "model": {
                "inputs": {
                    "seed": seed,
                },
                "class_type": "ModelMerge"
            },
            "clip": {
                "inputs": {
                    "text": request.prompt,
                },
                "class_type": "CLIPLoader"
            },
            "positive": {
                "inputs": {
                    "text": request.prompt,
                },
                "class_type": "CLIPTextEncode"
            },
            "negative": {
                "inputs": {
                    "text": request.negative_prompt or "",
                },
                "class_type": "CLIPTextEncode"
            },
            "latent": {
                "inputs": {
                    "width": request.width or 1024,
                    "height": request.height or 1024,
                    "batch_size": request.batch_count or 1,
                },
                "class_type": "EmptyLatentImage"
            },
            "ksampler": {
                "inputs": {
                    "seed": seed,
                    "steps": request.steps or 20,
                    "cfg": request.cfg_scale or 7.0,
                    "sampler_name": request.sampler or "euler",
                    "scheduler": request.scheduler or "normal",
                    "positive": ["positive", 0],
                    "negative": ["negative", 0],
                    "latent": ["latent", 0],
                    "model": ["model", 0],
                },
                "class_type": "KSampler"
            },
            "vae": {
                "inputs": {
                    "samples": ["ksampler", 0],
                },
                "class_type": "VAEDecode"
            },
            "save": {
                "inputs": {
                    "filename_prefix": f"omni_gen_{seed}",
                    "images": ["vae", 0],
                },
                "class_type": "SaveImage"
            }
        }

        # 添加LoRA节点
        prompt.update(lora_nodes)

        return prompt

    def _build_video_prompt(self, request: GenerationRequest) -> Dict[str, Any]:
        """构建ComfyUI视频生成prompt"""
        seed = request.seed if request.seed > 0 else int(datetime.now().timestamp())
        extra_params = request.extra_params or {}

        # 视频参数
        frames = extra_params.get("frames", 24)
        fps = extra_params.get("fps", 8)

        prompt = {
            "model": {
                "inputs": {
                    "model_name": extra_params.get("model", "wan2.1"),
                },
                "class_type": "VideoModelLoader"
            },
            "prompt": {
                "inputs": {
                    "text": request.prompt,
                },
                "class_type": "CLIPTextEncode"
            },
            "negative_prompt": {
                "inputs": {
                    "text": request.negative_prompt or "",
                },
                "class_type": "CLIPTextEncode"
            },
            "latent": {
                "inputs": {
                    "width": request.width or 1280,
                    "height": request.height or 720,
                    "frames": frames,
                },
                "class_type": "EmptyVideoLatent"
            },
            "sampler": {
                "inputs": {
                    "seed": seed,
                    "steps": request.steps or 25,
                    "cfg": request.cfg_scale or 7.0,
                    "sampler_name": request.sampler or "euler_ancestral",
                    "scheduler": request.scheduler or "normal",
                },
                "class_type": "VideoKSampler"
            },
            "encode": {
                "inputs": {
                    "samples": ["sampler", 0],
                    "model": ["model", 0],
                },
                "class_type": "VideoVAEEncode"
            },
            "decode": {
                "inputs": {
                    "samples": ["encode", 0],
                },
                "class_type": "VideoVAEDecode"
            },
            "save": {
                "inputs": {
                    "filename_prefix": f"omni_gen_video_{seed}",
                    "format": "mp4",
                    "fps": fps,
                },
                "class_type": "VideoSave"
            }
        }

        return prompt

    def _build_edit_prompt(self, request: GenerationRequest) -> Dict[str, Any]:
        """构建ComfyUI图片编辑prompt"""
        seed = request.seed if request.seed > 0 else int(datetime.now().timestamp())
        extra_params = request.extra_params or {}

        edit_type = extra_params.get("edit_type", "img2img")

        prompt = {
            "load_image": {
                "inputs": {
                    "image": request.input_images[0] if request.input_images else "",
                },
                "class_type": "LoadImage"
            },
            "positive": {
                "inputs": {
                    "text": request.prompt,
                },
                "class_type": "CLIPTextEncode"
            },
            "negative": {
                "inputs": {
                    "text": request.negative_prompt or "",
                },
                "class_type": "CLIPTextEncode"
            },
        }

        if edit_type == "inpainting":
            # 局部重绘
            prompt["mask"] = {
                "inputs": {
                    "mask": extra_params.get("mask", ""),
                },
                "class_type": "LoadImageMask"
            }
            prompt["inpaint"] = {
                "inputs": {
                    "image": ["load_image", 0],
                    "mask": ["mask", 0],
                    "positive": ["positive", 0],
                    "negative": ["negative", 0],
                    "steps": request.steps or 20,
                    "cfg": request.cfg_scale or 7.0,
                    "denoise": extra_params.get("denoise", 0.7),
                },
                "class_type": "InpaintModel"
            }
        else:
            # 图生图/风格转换
            prompt["preprocess"] = {
                "inputs": {
                    "image": ["load_image", 0],
                    "resize_mode": extra_params.get("resize_mode", 0),
                },
                "class_type": "ImagePreprocess"
            }
            prompt["img2img"] = {
                "inputs": {
                    "image": ["preprocess", 0],
                    "positive": ["positive", 0],
                    "negative": ["negative", 0],
                    "steps": request.steps or 20,
                    "cfg": request.cfg_scale or 7.0,
                    "denoise": extra_params.get("denoise", 0.7),
                },
                "class_type": "Img2Img"
            }

        prompt["save"] = {
            "inputs": {
                "filename_prefix": f"omni_gen_edit_{seed}",
                "images": [edit_type == "inpainting" and "inpaint" or "img2img", 0],
            },
            "class_type": "SaveImage"
        }

        return prompt

    def _generate_simulated_result(self, request: GenerationRequest) -> GenerationResult:
        """生成模拟结果用于演示"""
        images = []
        count = request.batch_count or 1

        for i in range(count):
            width = request.width or 1024
            height = request.height or 1024
            svg_content = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="#1a1a2e"/>
                <text x="50%" y="45%" font-family="Arial" font-size="40" fill="white" text-anchor="middle" dominant-baseline="middle">
                    OmniGen Studio Image {i+1}
                </text>
                <text x="50%" y="55%" font-family="Arial" font-size="20" fill="#aaa" text-anchor="middle">
                    {request.prompt[:50]}...
                </text>
            </svg>'''
            import base64
            b64 = base64.b64encode(svg_content.encode()).decode()
            images.append(f"data:image/svg+xml;base64,{b64}")

        return GenerationResult(
            request_id=request.request_id,
            status="completed",
            provider=self.config.provider_type.value,
            images=images,
            metadata={
                "simulated": True,
                "model": request.model or "omni_gen_studio",
                "provider": "omni_gen_studio",
                "generation_type": "image",
                "prompt": request.prompt
            },
            created_at=datetime.now().isoformat()
        )

    def _generate_simulated_video(self, request: GenerationRequest) -> GenerationResult:
        """生成模拟视频结果"""
        extra_params = request.extra_params or {}
        width = request.width or 1280
        height = request.height or 720

        svg_content = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
            <rect width="100%" height="100%" fill="#0f0f23"/>
            <text x="50%" y="45%" font-family="Arial" font-size="40" fill="white" text-anchor="middle" dominant-baseline="middle">
                OmniGen Studio Video
            </text>
            <text x="50%" y="55%" font-family="Arial" font-size="20" fill="#aaa" text-anchor="middle">
                {request.prompt[:50]}...
            </text>
        </svg>'''
        import base64
        b64 = base64.b64encode(svg_content.encode()).decode()

        return GenerationResult(
            request_id=request.request_id,
            status="completed",
            provider=self.config.provider_type.value,
            videos=[f"data:image/svg+xml;base64,{b64}"],
                        metadata={
                "simulated": True,
                "model": extra_params.get("model", "wan2.1"),
                "provider": "omni_gen_studio",
                "generation_type": "video",
                "frames": extra_params.get("frames", 24),
                "fps": extra_params.get("fps", 8),
            },
            created_at=datetime.now().isoformat()
        )

    def _generate_simulated_edit(self, request: GenerationRequest) -> GenerationResult:
        """生成模拟编辑结果"""
        width = request.width or 1024
        height = request.height or 1024
        edit_type = request.extra_params.get("edit_type", "img2img") if request.extra_params else "img2img"

        svg_content = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
            <rect width="100%" height="100%" fill="#2a2a4e"/>
            <text x="50%" y="45%" font-family="Arial" font-size="36" fill="white" text-anchor="middle" dominant-baseline="middle">
                OmniGen Edit - {edit_type}
            </text>
            <text x="50%" y="55%" font-family="Arial" font-size="20" fill="#aaa" text-anchor="middle">
                {request.prompt[:50]}...
            </text>
        </svg>'''
        import base64
        b64 = base64.b64encode(svg_content.encode()).decode()

        return GenerationResult(
            request_id=request.request_id,
            status="completed",
            provider=self.config.provider_type.value,
            images=[f"data:image/svg+xml;base64,{b64}"],
                        metadata={
                "simulated": True,
                "model": request.model or "omni_gen_studio",
                "provider": "omni_gen_studio",
                "generation_type": "edit",
                "edit_type": edit_type,
            },
            created_at=datetime.now().isoformat()
        )

    async def get_status(self, request_id: str) -> GenerationResult:
        """获取生成状态"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.comfyui_url}/history/{request_id}",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if request_id in data:
                            status_data = data[request_id]
                            if status_data.get("outputs"):
                                return GenerationResult(
                                    request_id=request_id,
                                    status="completed",
                                    provider=self.config.provider_type.value,
                                    created_at=datetime.now().isoformat()
                                )
        except Exception as e:
            logger.warning(f"ComfyUI生成完成检查失败: {e}")
            pass

        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        """取消生成"""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.comfyui_url}/interrupt",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.warning(f"ComfyUI取消请求失败: {e}")
            return False

    async def list_models(self) -> List[Dict[str, Any]]:
        """列出可用模型"""
        models = []

        # 添加omni_gen_studio支持的模型
        omni_models_dir = self.omni_gen_dir / "ComfyUI" / "models"
        if omni_models_dir.exists():
            for model_type in ["checkpoints", "loras", "vae", "clip", "upscale_models", "controlnet"]:
                model_path = omni_models_dir / model_type
                if model_path.exists():
                    for model_file in model_path.glob("*"):
                        if model_file.is_file():
                            models.append({
                                "name": model_file.name,
                                "type": model_type,
                                "path": str(model_file),
                                "size": model_file.stat().st_size
                            })

        return models


class KlingProvider(BaseProvider):
    """可灵 (Kling) 视频生成提供商"""

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """通过可灵 API 生成视频"""
        if not self.config.api_key:
            # API key未配置时抛出错误
            raise ValueError(
                "Kling API key is not configured. "
                "Please configure KLING_API_KEY in your environment or settings."
            )

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.config.api_endpoint or "https://api.klingai.com/v1/generations/video",
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "prompt": request.prompt,
                        "negative_prompt": request.negative_prompt,
                        "duration": request.extra_params.get("duration", 5),
                        "aspect_ratio": f"{request.width}:{request.height}",
                    }
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            videos=[result.get("video_url", "")],
                            created_at=datetime.now().isoformat()
                        )
                    else:
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"API error: {resp.status}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            # Kling不可用时抛出真实错误
            logger.error(f"Kling API call failed: {e}")
            raise ConnectionError(
                f"Kling video generation service is not available. "
                f"Please ensure Kling API is configured with valid credentials. "
                f"Original error: {str(e)}"
            )

    def _generate_simulated_video(self, request: GenerationRequest) -> GenerationResult:
        """生成模拟视频结果用于演示"""
        # 创建一个模拟视频URL（实际是SVG占位符）
        width = request.width or 1920
        height = request.height or 1080
        svg_content = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
            <rect width="100%" height="100%" fill="#0f0f23"/>
            <text x="50%" y="45%" font-family="Arial" font-size="48" fill="white" text-anchor="middle" dominant-baseline="middle">
                AI Generated Video
            </text>
            <text x="50%" y="55%" font-family="Arial" font-size="24" fill="#aaa" text-anchor="middle">
                {request.prompt[:50]}...
            </text>
            <text x="50%" y="65%" font-family="Arial" font-size="18" fill="#666" text-anchor="middle">
                (Simulated Result - Configure API key for real generation)
            </text>
        </svg>'''
        import base64
        b64 = base64.b64encode(svg_content.encode()).decode()

        return GenerationResult(
            request_id=request.request_id,
            status="completed",
            provider=self.config.provider_type.value,
            videos=[f"data:image/svg+xml;base64,{b64}"],
            metadata={"simulated": True, "duration": request.extra_params.get("duration", 5) if request.extra_params else 5, "prompt": request.prompt},
            created_at=datetime.now().isoformat()
        )


class GPTImageProvider(BaseProvider):
    """GPT (DALL-E) 图像生成提供商"""

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """通过 GPT (DALL-E) API 生成"""
        if not self.config.api_key:
            # API key未配置时抛出错误
            raise ValueError(
                "OpenAI API key is not configured. "
                "Please configure OPENAI_API_KEY in your environment or settings."
            )

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # 使用 OpenAI DALL-E API
                async with session.post(
                    "https://api.openai.com/v1/images/generations",
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "prompt": request.prompt,
                        "n": request.batch_count,
                        "size": f"{request.width}x{request.height}",
                        "model": "dall-e-3"
                    }
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        images = [img["url"] for img in result.get("data", [])]
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            progress=100.0,
                            images=images,
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"API error: {resp.status}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            # OpenAI API调用失败时抛出真实错误
            logger.error(f"OpenAI DALL-E API call failed: {e}")
            raise ConnectionError(
                f"OpenAI DALL-E service is not available. "
                f"Please check your API key and network connection. "
                f"Original error: {str(e)}"
            )

    def _generate_simulated_result(self, request: GenerationRequest) -> GenerationResult:
        """生成模拟结果用于演示"""
        images = []
        count = request.batch_count or 1

        for i in range(count):
            width = request.width or 1024
            height = request.height or 1024
            svg_content = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
                <rect width="100%" height="100%" fill="#1a1a2e"/>
                <text x="50%" y="45%" font-family="Arial" font-size="40" fill="white" text-anchor="middle" dominant-baseline="middle">
                    DALL-E Generated Image {i+1}
                </text>
                <text x="50%" y="55%" font-family="Arial" font-size="20" fill="#aaa" text-anchor="middle">
                    {request.prompt[:60]}...
                </text>
            </svg>'''
            import base64
            b64 = base64.b64encode(svg_content.encode()).decode()
            images.append(f"data:image/svg+xml;base64,{b64}")

        return GenerationResult(
            request_id=request.request_id,
            status="completed",
            provider=self.config.provider_type.value,
            progress=100.0,
            images=images,
                        metadata={"simulated": True},
            created_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat()
        )


class ImageEditProvider(BaseProvider):
    """图片编辑提供商 - 支持图生图、局部重绘、换装等"""

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """执行图片编辑"""
        if not request.input_images:
            # 输入图片为空时抛出错误
            raise ValueError(
                "Input image is required for image editing. "
                "Please provide an input image in the request."
            )

        # 根据 extra_params 确定编辑类型
        edit_type = request.extra_params.get("edit_type", "img2img")

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # 使用 ComfyUI 进行图片编辑
                endpoint = self.config.comfyui_url or f"http://localhost:{self.config.comfyui_port}"

                # 构建编辑 prompt
                prompt_data = self._build_edit_prompt(request, edit_type)

                async with session.post(
                    f"{endpoint}/prompt",
                    json={"prompt": prompt_data},
                    timeout=aiohttp.ClientTimeout(total=180)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            progress=50.0,
                            created_at=datetime.now().isoformat(),
                            metadata={"edit_type": edit_type}
                        )
                    else:
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"Image edit error: {resp.status}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            # 图片编辑失败时抛出真实错误
            logger.error(f"Image editing failed: {e}")
            raise ConnectionError(
                f"Image editing service is not available. "
                f"Please ensure ComfyUI is running with image editing nodes. "
                f"Original error: {str(e)}"
            )

    def _generate_simulated_edit(self, request: GenerationRequest) -> GenerationResult:
        """生成模拟编辑结果用于演示"""
        width = request.width or 1024
        height = request.height or 1024
        edit_type = request.extra_params.get("edit_type", "img2img") if request.extra_params else "img2img"

        svg_content = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
            <rect width="100%" height="100%" fill="#2a2a4e"/>
            <text x="50%" y="40%" font-family="Arial" font-size="36" fill="white" text-anchor="middle" dominant-baseline="middle">
                AI Image Edit - {edit_type}
            </text>
            <text x="50%" y="55%" font-family="Arial" font-size="20" fill="#aaa" text-anchor="middle">
                {request.prompt[:50]}...
            </text>
        </svg>'''
        import base64
        b64 = base64.b64encode(svg_content.encode()).decode()

        return GenerationResult(
            request_id=request.request_id,
            status="completed",
            provider=self.config.provider_type.value,
            progress=100.0,
            images=[f"data:image/svg+xml;base64,{b64}"],
                        metadata={"simulated": True, "edit_type": edit_type},
            created_at=datetime.now().isoformat(),
            completed_at=datetime.now().isoformat()
        )

    def _build_edit_prompt(self, request: GenerationRequest, edit_type: str) -> Dict[str, Any]:
        """构建编辑 prompt"""
        base_nodes = {
            "positive": request.prompt,
            "negative": request.negative_prompt,
            "image": request.input_images[0],
            "strength": request.extra_params.get("denoising_strength", 0.7),
            "seed": request.seed if request.seed > 0 else int(datetime.now().timestamp()),
        }

        if edit_type == "inpainting":
            # 局部重绘
            return {
                "1": {"inputs": {"image": base_nodes["image"]}, "class_type": "LoadImage"},
                "2": {"inputs": {"mask": request.extra_params.get("mask_image", "")}, "class_type": "LoadImageMask"},
                "3": {"inputs": {**base_nodes, "mask": "2"}, "class_type": "Inpaint"},
            }
        else:
            # 图生图
            return {
                "1": {"inputs": {"image": base_nodes["image"]}, "class_type": "LoadImage"},
                "2": {"inputs": {**base_nodes, "image": "1"}, "class_type": "KSampler"},
            }

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": "img2img", "type": "image_edit"},
            {"name": "inpainting", "type": "image_edit"},
            {"name": "outpainting", "type": "image_edit"},
        ]


class ImageUpscaleProvider(BaseProvider):
    """图片放大提供商 - ZC Upscale Pro 10合1算法支持"""

    # ZC Upscale Pro 支持的算法
    ZC_ALGORITHMS = [
        "DAT",        # Dual Aggregation Transformer
        "DAT-2",      # Dual Aggregation Transformer v2
        "MDAT",       # Modified Dual Aggregation Transformer
        "Bird-SR",    # Bird Animal Super Resolution
        "Taylor-EIUM", # Taylor Efficient Interactive Upsampling Model
        "FocusSRNet", # Focus Super Resolution Network
        "SPGAN",      # SPGAN Super Resolution
        "HOLI-SRNet", # HOLI Super Resolution Network
        "OSDEnhancer", # OSD (Object-Specific Detail) Enhancer
        "Laplacian-SR" # Laplacian Super Resolution
    ]

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """执行图片放大 - 支持ZC Upscale Pro 10合1算法"""
        if not request.input_images:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=self.config.provider_type.value,
                error="Input image required for upscaling",
                created_at=datetime.now().isoformat()
            )

        # 提取ZC Upscale Pro参数
        upscale_algorithm = request.extra_params.get("upscale_algorithm", "DAT")
        scale_factor = request.extra_params.get("scale", 2)

        # 图像调节参数
        brightness = request.extra_params.get("brightness", 0)
        contrast = request.extra_params.get("contrast", 0)
        saturation = request.extra_params.get("saturation", 0)
        vibrance_mode = request.extra_params.get("vibrance_mode", "Standard")
        temperature = request.extra_params.get("temperature", 0)
        hue_global = request.extra_params.get("hue_global", 0)

        # USM锐化参数
        sharpness_amount = request.extra_params.get("sharpness_amount", 0)
        sharpness_radius = request.extra_params.get("sharpness_radius", 1.0)
        sharpness_threshold = request.extra_params.get("sharpness_threshold", 0)

        # HSL八通道参数
        hsl_params = {}
        channels = ["red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta"]
        for ch in channels:
            hsl_params[f"{ch}_hue"] = request.extra_params.get(f"{ch}_hue", 0)
            hsl_params[f"{ch}_saturation"] = request.extra_params.get(f"{ch}_saturation", 0)
            hsl_params[f"{ch}_lightness"] = request.extra_params.get(f"{ch}_lightness", 0)

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                endpoint = self.config.comfyui_url or f"http://localhost:{self.config.comfyui_port}"

                # 根据算法选择合适的ComfyUI工作流
                prompt_data = self._build_zc_upscale_prompt(
                    request.input_images[0],
                    upscale_algorithm,
                    scale_factor,
                    brightness,
                    contrast,
                    saturation,
                    vibrance_mode,
                    temperature,
                    hue_global,
                    sharpness_amount,
                    sharpness_radius,
                    sharpness_threshold,
                    hsl_params
                )

                async with session.post(
                    f"{endpoint}/prompt",
                    json={"prompt": prompt_data},
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            progress=50.0,
                            metadata={
                                "algorithm": upscale_algorithm,
                                "scale": scale_factor,
                                "brightness": brightness,
                                "contrast": contrast,
                                "saturation": saturation,
                                "has_hsl_adjustments": any(hsl_params.values())
                            },
                            created_at=datetime.now().isoformat()
                        )
                    else:
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"ZC Upscale error: {resp.status}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=self.config.provider_type.value,
                error=str(e),
                created_at=datetime.now().isoformat()
            )

    def _build_zc_upscale_prompt(
        self,
        image_path: str,
        algorithm: str,
        scale: int,
        brightness: float,
        contrast: float,
        saturation: float,
        vibrance_mode: str,
        temperature: float,
        hue_global: float,
        sharpness_amount: float,
        sharpness_radius: float,
        sharpness_threshold: float,
        hsl_params: Dict[str, float]
    ) -> Dict[str, Any]:
        """构建ZC Upscale Pro工作流"""

        # 基础节点
        nodes = {
            "1": {
                "inputs": {"image": image_path},
                "class_type": "LoadImage"
            }
        }

        # 根据算法选择放大模型
        if algorithm in self.ZC_ALGORITHMS:
            # ZC专业算法使用专用的放大模型
            model_node = self._get_algorithm_model_node(algorithm, scale)
            nodes.update(model_node)

            # 亮度调节节点
            if brightness != 0:
                nodes["brightness_node"] = {
                    "inputs": {
                        "image": "upscaled_image",
                        "brightness": brightness / 100.0,
                        "contrast": 1.0,
                    },
                    "class_type": "ImageBrightnessContrast"
                }

            # 对比度调节
            if contrast != 0:
                contrast_node_id = "brightness_node" if brightness != 0 else "upscaled_image"
                nodes["contrast_node"] = {
                    "inputs": {
                        "image": contrast_node_id,
                        "brightness": 0,
                        "contrast": 1.0 + (contrast / 100.0),
                    },
                    "class_type": "ImageBrightnessContrast"
                }

            # 饱和度调节
            if saturation != 0:
                sat_node_id = "contrast_node" if contrast != 0 else ("brightness_node" if brightness != 0 else "upscaled_image")
                nodes["saturation_node"] = {
                    "inputs": {
                        "image": sat_node_id,
                        "saturation": 1.0 + (saturation / 100.0),
                    },
                    "class_type": "ImageSaturation"
                }

            # USM锐化
            if sharpness_amount > 0:
                final_image = "saturation_node" if saturation != 0 else ("contrast_node" if contrast != 0 else ("brightness_node" if brightness != 0 else "upscaled_image"))
                nodes["usm_sharp"] = {
                    "inputs": {
                        "image": final_image,
                        "amount": sharpness_amount / 100.0,
                        "radius": sharpness_radius,
                        "threshold": sharpness_threshold / 255.0,
                    },
                    "class_type": "USMSharp"
                }

        return nodes

    def _get_algorithm_model_node(self, algorithm: str, scale: int) -> Dict[str, Any]:
        """获取算法对应的模型节点"""
        algorithm_models = {
            "DAT": {
                "upscaler": {
                    "inputs": {"image": "1", "model_name": "DAT_4x", "scale": scale, "blur": 2},
                    "class_type": "ImageUpscaleWithModel"
                }
            },
            "DAT-2": {
                "upscaler": {
                    "inputs": {"image": "1", "model_name": "DAT_2x", "scale": scale, "blur": 2},
                    "class_type": "ImageUpscaleWithModel"
                }
            },
            "MDAT": {
                "upscaler": {
                    "inputs": {"image": "1", "model_name": "MDAT_4x", "scale": scale, "blur": 2},
                    "class_type": "ImageUpscaleWithModel"
                }
            },
            "Bird-SR": {
                "upscaler": {
                    "inputs": {"image": "1", "model_name": "Bird-SR_4x", "scale": scale, "blur": 2},
                    "class_type": "ImageUpscaleWithModel"
                }
            },
            "Taylor-EIUM": {
                "upscaler": {
                    "inputs": {"image": "1", "model_name": "Taylor-EIUM_4x", "scale": scale, "blur": 2},
                    "class_type": "ImageUpscaleWithModel"
                }
            },
            "FocusSRNet": {
                "upscaler": {
                    "inputs": {"image": "1", "model_name": "FocusSRNet_4x", "scale": scale, "blur": 2},
                    "class_type": "ImageUpscaleWithModel"
                }
            },
            "SPGAN": {
                "upscaler": {
                    "inputs": {"image": "1", "model_name": "SPGAN_4x", "scale": scale, "blur": 2},
                    "class_type": "ImageUpscaleWithModel"
                }
            },
            "HOLI-SRNet": {
                "upscaler": {
                    "inputs": {"image": "1", "model_name": "HOLI-SRNet_4x", "scale": scale, "blur": 2},
                    "class_type": "ImageUpscaleWithModel"
                }
            },
            "OSDEnhancer": {
                "upscaler": {
                    "inputs": {"image": "1", "model_name": "OSDEnhancer_4x", "scale": scale, "blur": 2},
                    "class_type": "ImageUpscaleWithModel"
                }
            },
            "Laplacian-SR": {
                "upscaler": {
                    "inputs": {"image": "1", "model_name": "Laplacian-SR_4x", "scale": scale, "blur": 2},
                    "class_type": "ImageUpscaleWithModel"
                }
            }
        }
        return algorithm_models.get(algorithm, algorithm_models.get("DAT", {}))

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        """列出支持的ZC Upscale Pro算法"""
        return [
            {"name": "DAT", "type": "upscale", "description": "Dual Aggregation Transformer - 通用超分辨率"},
            {"name": "DAT-2", "type": "upscale", "description": "DAT v2 - 增强型双聚合变换器"},
            {"name": "MDAT", "type": "upscale", "description": "Modified DAT - 修改型双聚合变换器"},
            {"name": "Bird-SR", "type": "upscale", "description": "动物专用超分辨率"},
            {"name": "Taylor-EIUM", "type": "upscale", "description": "Taylor高效交互上采样模型"},
            {"name": "FocusSRNet", "type": "upscale", "description": "聚焦超分辨率网络"},
            {"name": "SPGAN", "type": "upscale", "description": "SPGAN超分辨率"},
            {"name": "HOLI-SRNet", "type": "upscale", "description": "HOLI超分辨率网络"},
            {"name": "OSDEnhancer", "type": "upscale", "description": "OSD细节增强器"},
            {"name": "Laplacian-SR", "type": "upscale", "description": "拉普拉斯超分辨率"},
            {"name": "RealESRGAN", "type": "upscale", "description": "通用超分辨率GAN"},
            {"name": "ESRGAN", "type": "upscale", "description": "增强型超分辨率GAN"},
        ]


# =============================================================================
# 3D Generation Providers
# =============================================================================

class TripoSRProvider(BaseProvider):
    """TripoSR 3D模型生成提供商"""

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """通过 TripoSR 生成3D模型"""
        if not request.input_images:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=self.config.provider_type.value,
                error="Input image required for 3D generation",
                created_at=datetime.now().isoformat()
            )

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                # TripoSR API endpoint (需要根据实际部署配置)
                endpoint = self.config.api_endpoint or "http://localhost:8001/v1/triposr"

                async with session.post(
                    endpoint,
                    json={
                        "image_url": request.input_images[0],
                        "prompt": request.prompt,
                        "watermark": False,
                    },
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            progress=100.0,
                            images=[result.get("render_image", "")],
                            videos=[result.get("model_url", "")],
                            metadata={
                                "model_format": result.get("format", "obj"),
                                "texture": result.get("texture", True),
                            },
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"TripoSR error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=self.config.provider_type.value,
                error=str(e),
                created_at=datetime.now().isoformat()
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [{"name": "triposr_v1", "type": "image_to_3d"}]


class LGMProvider(BaseProvider):
    """LGM 3D模型生成提供商"""

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """通过 LGM 生成3D模型"""
        if not request.input_images:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=self.config.provider_type.value,
                error="Input image required for 3D generation",
                created_at=datetime.now().isoformat()
            )

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                endpoint = self.config.api_endpoint or "http://localhost:8002/v1/lgm"

                async with session.post(
                    endpoint,
                    json={
                        "image": request.input_images[0],
                        "prompt": request.prompt,
                        "seed": request.seed if request.seed > 0 else int(datetime.now().timestamp()),
                    },
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            progress=100.0,
                            images=[result.get("preview", "")],
                            videos=[result.get("mesh_url", "")],
                            metadata={"format": result.get("format", "obj")},
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"LGM error: {resp.status}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=self.config.provider_type.value,
                error=str(e),
                created_at=datetime.now().isoformat()
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [{"name": "lgm_v1", "type": "image_to_3d"}]


class StableVideo3DProvider(BaseProvider):
    """Stable Video 3D 生成提供商"""

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """通过 SV3D 生成3D视频"""
        if not request.input_images:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=self.config.provider_type.value,
                error="Input image required for SV3D",
                created_at=datetime.now().isoformat()
            )

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                endpoint = self.config.api_endpoint or "https://api.stability.ai/v2beta/image-to-3d"

                async with session.post(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {self.config.api_key}",
                    },
                    json={
                        "image": request.input_images[0],
                        "mode": "sv3d",
                    },
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            videos=[result.get("video_url", "")],
                            metadata={"format": "mp4"},
                            created_at=datetime.now().isoformat()
                        )
                    else:
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"SV3D error: {resp.status}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=self.config.provider_type.value,
                error=str(e),
                created_at=datetime.now().isoformat()
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [{"name": "sv3d", "type": "image_to_3d"}]


# =============================================================================
# 最新图像生成 Provider - Z Image (字节跳动 2025)
# =============================================================================

class ZImageProvider(BaseProvider):
    """Z Image 生成 Provider (字节跳动 2025)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_endpoint = config.extra_config.get("api_endpoint", "https://api.z-ai.art/v1")
        self.api_key = config.extra_config.get("api_key", "")

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Z Image 图像生成"""
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "width": request.width,
                "height": request.height,
                "steps": request.steps,
                "cfg_scale": request.cfg_scale,
                "sampler": request.sampler,
                "seed": request.seed if request.seed > 0 else None,
                "batch_size": request.batch_count,
                "loras": request.lora_configs,
                "controlnets": request.controlnet_configs,
                "hires_fix": request.extra_params.get("hires_fix", False),
                "extra_params": request.extra_params
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_endpoint}/generate",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            images=result.get("images", []),
                            metadata={"model": "z-image-v2", "params": payload},
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"Z Image API error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            # Z Image provider 不可用时抛出真实错误
            logger.error(f"Z Image provider error: {e}")
            raise ConnectionError(
                f"Z Image generation service is not available. "
                f"Please ensure the service is running and properly configured. "
                f"Original error: {str(e)}"
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": "z-image-v2", "type": "text_to_image", "capabilities": ["t2i", "hires", "controlnet"]},
            {"name": "z-image-v2-flash", "type": "text_to_image", "capabilities": ["fast_t2i"]}
        ]


# =============================================================================
# 最新图像生成 Provider - Qwen Image (阿里 2025)
# =============================================================================

class QwenImageProvider(BaseProvider):
    """Qwen Image 生成 Provider (阿里 2025)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_endpoint = config.extra_config.get("api_endpoint", "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/generation")
        self.api_key = config.extra_config.get("api_key", "")

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Qwen Image 图像生成"""
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable"
            }

            payload = {
                "model": "qwen-image-v2",
                "input": {
                    "prompt": request.prompt,
                    "negative_prompt": request.negative_prompt
                },
                "parameters": {
                    "size": f"{request.width}x{request.height}",
                    "steps": request.steps,
                    "cfg_scale": request.cfg_scale,
                    "seed": request.seed if request.seed > 0 else None,
                    "sampler": request.sampler,
                    "loras": request.lora_configs,
                    "controlnets": request.controlnet_configs,
                    "extra_params": request.extra_params
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        task_id = result.get("request_id", "")
                        # 异步任务，需要轮询
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            progress=0.5,
                            metadata={"task_id": task_id, "model": "qwen-image-v2"},
                            created_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"Qwen Image API error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            logger.error(f"Qwen Image provider error: {e}")
            raise ConnectionError(
                f"Qwen Image generation service is not available. "
                f"Please ensure the service is properly configured. "
                f"Original error: {str(e)}"
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": "qwen-image-v2", "type": "text_to_image", "capabilities": ["t2i", "face_enhance", "controlnet"]},
            {"name": "qwen-image-v2-flash", "type": "text_to_image", "capabilities": ["fast_t2i"]}
        ]


# =============================================================================
# 最新图像生成 Provider - Nano Banana 2/Pro (2025)
# =============================================================================

class NanoBananaProvider(BaseProvider):
    """Nano Banana 2/Pro 生成 Provider (2025)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_endpoint = config.extra_config.get("api_endpoint", "https://api.nanobanana.ai/v1")
        self.api_key = config.extra_config.get("api_key", "")
        self.is_pro = config.provider_type == ProviderType.NANOBANANA_PRO

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Nano Banana 图像生成"""
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            model_name = "nano-banana-pro" if self.is_pro else "nano-banana-2"
            payload = {
                "model": model_name,
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "width": request.width,
                "height": request.height,
                "steps": request.steps,
                "cfg_scale": request.cfg_scale,
                "sampler": request.sampler,
                "seed": request.seed if request.seed > 0 else None,
                "batch_size": request.batch_count,
                "style_preset": request.extra_params.get("style_preset", "anime_pro"),
                "loras": request.lora_configs,
                "variants": request.extra_params.get("variants", None)
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_endpoint}/generate",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            images=result.get("images", []),
                            metadata={"model": model_name, "params": payload},
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"Nano Banana API error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            logger.error(f"Nano Banana provider error: {e}")
            raise ConnectionError(
                f"Nano Banana generation service is not available. "
                f"Please ensure the service is properly configured. "
                f"Original error: {str(e)}"
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        if self.is_pro:
            return [{"name": "nano-banana-pro", "type": "text_to_image", "capabilities": ["t2i", "variants", "consistency"]}]
        return [
            {"name": "nano-banana-2", "type": "text_to_image", "capabilities": ["t2i", "anime"]},
            {"name": "nano-banana-2-flash", "type": "text_to_image", "capabilities": ["fast_t2i"]}
        ]


# =============================================================================
# 最新图像编辑 Provider - Flux2-Klein (Black Forest Labs 2025)
# =============================================================================

class Flux2KleinProvider(BaseProvider):
    """Flux2-Klein 生成 Provider (Black Forest Labs 2025)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_endpoint = config.extra_config.get("api_endpoint", "https://api.bfl.ai/v1")
        self.api_key = config.extra_config.get("api_key", "")

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Flux2-Klein 图像生成/编辑"""
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "width": request.width,
                "height": request.height,
                "steps": request.steps,
                "cfg_scale": request.cfg_scale,
                "seed": request.seed if request.seed > 0 else None,
                "controlnets": request.controlnet_configs,
                "image_url": request.input_images[0] if request.input_images else None
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_endpoint}/flux-klein",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            images=result.get("images", []),
                            metadata={"model": "flux2-klein", "params": payload},
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"Flux2-Klein API error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            logger.error(f"Flux2-Klein provider error: {e}")
            raise ConnectionError(
                f"Flux2-Klein generation service is not available. "
                f"Please ensure the service is properly configured. "
                f"Original error: {str(e)}"
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": "flux2-klein", "type": "text_to_image", "capabilities": ["t2i", "controlnet", "inpainting"]},
            {"name": "flux2-klein-control", "type": "text_to_image", "capabilities": ["t2i", "control"]}
        ]


# =============================================================================
# 最新视频生成 Provider - Wan 2.x (字节跳动 2025)
# =============================================================================

class Wan2xProvider(BaseProvider):
    """Wan 2.x 视频生成 Provider (字节跳动 2025)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_endpoint = config.extra_config.get("api_endpoint", "https://api.wan-ai.com/v1")
        self.api_key = config.extra_config.get("api_key", "")

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Wan 2.x 视频生成"""
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "wan2.1-t2v-14b",
                "prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "duration": request.extra_params.get("duration", 5),
                "fps": request.extra_params.get("fps", 24),
                "resolution": f"{request.width}x{request.height}",
                "motion_bucket_id": request.extra_params.get("motion_bucket_id", 127),
                "image_url": request.input_images[0] if request.input_images else None,
                "steps": request.steps,
                "cfg_scale": request.cfg_scale
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_endpoint}/generate/video",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            progress=0.5,
                            videos=result.get("videos", []),
                            metadata={"model": "wan2.1-t2v-14b", "params": payload},
                            created_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"Wan 2.x API error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            logger.error(f"Wan 2.x provider error: {e}")
            raise ConnectionError(
                f"Wan 2.x video generation service is not available. "
                f"Please ensure the service is properly configured. "
                f"Original error: {str(e)}"
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": "wan2.1-t2v-14b", "type": "text_to_video", "capabilities": ["t2v", "i2v"]},
            {"name": "wan2.1-i2v-14b", "type": "image_to_video", "capabilities": ["i2v"]}
        ]


# =============================================================================
# 最新视频生成 Provider - LTVX-2 (2025)
# =============================================================================

class LTVX2Provider(BaseProvider):
    """LTVX-2 视频生成 Provider (2025)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_endpoint = config.extra_config.get("api_endpoint", "https://api.ltvx.ai/v1")
        self.api_key = config.extra_config.get("api_key", "")

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """LTVX-2 视频生成"""
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "ltvx-2",
                "input_frames": [
                    {"frame_id": i+1, "image": img, "duration": 2.0}
                    for i, img in enumerate(request.input_images)
                ] if request.input_images else None,
                "prompt": request.prompt,
                "motion_strength": request.extra_params.get("motion_strength", 0.7),
                "fps": request.extra_params.get("fps", 30),
                "duration": request.extra_params.get("duration", 15),
                "resolution": f"{request.width}x{request.height}",
                "transitions": request.extra_params.get("transitions", {"type": "smooth"}),
                "effects": request.extra_params.get("effects", {}),
                "output_format": request.extra_params.get("output_format", "mp4")
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_endpoint}/generate",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            videos=result.get("videos", []),
                            metadata={"model": "ltvx-2", "params": payload},
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"LTVX-2 API error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            logger.error(f"LTVX-2 provider error: {e}")
            raise ConnectionError(
                f"LTVX-2 video generation service is not available. "
                f"Please ensure the service is properly configured. "
                f"Original error: {str(e)}"
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": "ltvx-2", "type": "video_generation", "capabilities": ["t2v", "i2v", "effects"]},
            {"name": "ltvx-2-fast", "type": "video_generation", "capabilities": ["fast_v"]}
        ]


# =============================================================================
# 最新视频生成 Provider - Voe 3.1 (2025)
# =============================================================================

class Voe3Provider(BaseProvider):
    """Voe 3.1 视频生成/增强 Provider (2025)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_endpoint = config.extra_config.get("api_endpoint", "https://api.voe.ai/v1")
        self.api_key = config.extra_config.get("api_key", "")

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Voe 3.1 视频生成/增强"""
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            is_enhance = request.extra_params.get("enhance_mode", False)
            model_name = "voe-3.1-enhance" if is_enhance else "voe-3.1-generate"

            payload = {
                "model": model_name,
                "input": {
                    "video_url": request.input_images[0] if request.input_images else None,
                    "prompt": request.prompt if not is_enhance else None
                },
                "parameters": {
                    "resolution": f"{request.width}x{request.height}",
                    "fps": request.extra_params.get("fps", 30),
                    "duration": request.extra_params.get("duration", 5),
                    "upscale": request.extra_params.get("upscale", 1),
                    "frame_smoothing": request.extra_params.get("frame_smoothing", True),
                    "color_grade": request.extra_params.get("color_grade", "film"),
                    "effects": request.extra_params.get("effects", {})
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_endpoint}/generate",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            videos=result.get("videos", []),
                            metadata={"model": model_name, "params": payload},
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"Voe 3.1 API error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            logger.error(f"Voe 3.1 provider error: {e}")
            raise ConnectionError(
                f"Voe 3.1 video generation service is not available. "
                f"Please ensure the service is properly configured. "
                f"Original error: {str(e)}"
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": "voe-3.1-generate", "type": "video_generation", "capabilities": ["t2v", "i2v"]},
            {"name": "voe-3.1-enhance", "type": "video_enhancement", "capabilities": ["upscale", "smooth", "color"]}
        ]


# =============================================================================
# 最新图像编辑 Provider - Qwen Image Edit (阿里 2025)
# =============================================================================

class QwenImageEditProvider(BaseProvider):
    """Qwen Image Edit 图像编辑 Provider (阿里 2025)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_endpoint = config.extra_config.get("api_endpoint", "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-editing/generation")
        self.api_key = config.extra_config.get("api_key", "")

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Qwen Image Edit 图像编辑"""
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable"
            }

            task_type = request.extra_params.get("task_type", "edit")

            payload = {
                "model": "qwen-image-edit",
                "input": {
                    "image_url": request.input_images[0] if request.input_images else None,
                    "prompt": request.prompt
                },
                "parameters": {
                    "task_type": task_type,
                    "restoration": request.extra_params.get("restoration", {}),
                    "upscale": request.extra_params.get("upscale", {}),
                    "colorization": request.extra_params.get("colorization", {})
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=300)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        task_id = result.get("request_id", "")
                        return GenerationResult(
                            request_id=request.request_id,
                            status="processing",
                            provider=self.config.provider_type.value,
                            progress=0.5,
                            metadata={"task_id": task_id, "model": "qwen-image-edit"},
                            created_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"Qwen Image Edit API error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            logger.error(f"Qwen Image Edit provider error: {e}")
            raise ConnectionError(
                f"Qwen Image Edit service is not available. "
                f"Please ensure the service is properly configured. "
                f"Original error: {str(e)}"
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": "qwen-image-edit", "type": "image_editing", "capabilities": ["edit", "restore", "upscale", "colorize"]}
        ]


# =============================================================================
# 最新3D生成 Provider - TRELLIS (Microsoft 2025)
# =============================================================================

class TRELLISProvider(BaseProvider):
    """TRELLIS 3D生成 Provider (Microsoft 2025)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_endpoint = config.extra_config.get("api_endpoint", "https://api.trellis3d.ai/v1")
        self.api_key = config.extra_config.get("api_key", "")

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """TRELLIS 3D生成"""
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "trellis",
                "input": {
                    "image_url": request.input_images[0] if request.input_images else None,
                    "prompt": request.prompt if not request.input_images else None
                },
                "parameters": {
                    "output_format": request.extra_params.get("output_format", "obj"),
                    "texture_resolution": request.extra_params.get("texture_resolution", 2048),
                    "mesh_density": request.extra_params.get("mesh_density", "high"),
                    "pbr_materials": request.extra_params.get("pbr_materials", True)
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_endpoint}/generate/3d",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            metadata={
                                "model": "trellis",
                                "3d_model_url": result.get("model_url", ""),
                                "texture_url": result.get("texture_url", ""),
                                "params": payload
                            },
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"TRELLIS API error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            logger.error(f"TRELLIS provider error: {e}")
            raise ConnectionError(
                f"TRELLIS 3D generation service is not available. "
                f"Please ensure the service is properly configured. "
                f"Original error: {str(e)}"
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": "trellis", "type": "image_to_3d", "capabilities": ["i2t3d", "pbr", "texture"]}
        ]


# =============================================================================
# 最新3D生成 Provider - Hunyuan-3D (腾讯 2025)
# =============================================================================

class Hunyuan3DProvider(BaseProvider):
    """Hunyuan-3D 3D生成 Provider (腾讯 2025)"""

    def __init__(self, config: ProviderConfig):
        super().__init__(config)
        self.api_endpoint = config.extra_config.get("api_endpoint", "https://api.hunyuan3d.qq.com/v1")
        self.api_key = config.extra_config.get("api_key", "")

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        """Hunyuan-3D 3D生成"""
        try:
            import aiohttp
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "hunyuan-3d",
                "input": {
                    "image_url": request.input_images[0] if request.input_images else None,
                    "prompt": request.prompt if not request.input_images else None
                },
                "parameters": {
                    "output_format": request.extra_params.get("output_format", "glb"),
                    "texture_resolution": request.extra_params.get("texture_resolution", 2048),
                    "detail_level": request.extra_params.get("detail_level", "high"),
                    "optimize_topology": request.extra_params.get("optimize_topology", True)
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_endpoint}/generate",
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=600)
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="completed",
                            provider=self.config.provider_type.value,
                            metadata={
                                "model": "hunyuan-3d",
                                "3d_model_url": result.get("model_url", ""),
                                "params": payload
                            },
                            created_at=datetime.now().isoformat(),
                            completed_at=datetime.now().isoformat()
                        )
                    else:
                        error_text = await resp.text()
                        return GenerationResult(
                            request_id=request.request_id,
                            status="failed",
                            provider=self.config.provider_type.value,
                            error=f"Hunyuan-3D API error: {resp.status} - {error_text}",
                            created_at=datetime.now().isoformat()
                        )
        except Exception as e:
            logger.error(f"Hunyuan-3D provider error: {e}")
            raise ConnectionError(
                f"Hunyuan-3D generation service is not available. "
                f"Please ensure the service is properly configured. "
                f"Original error: {str(e)}"
            )

    async def get_status(self, request_id: str) -> GenerationResult:
        return GenerationResult(
            request_id=request_id,
            status="unknown",
            provider=self.config.provider_type.value
        )

    async def cancel(self, request_id: str) -> bool:
        return False

    async def list_models(self) -> List[Dict[str, Any]]:
        return [
            {"name": "hunyuan-3d", "type": "image_to_3d", "capabilities": ["i2t3d", "t2t3d", "optimize"]}
        ]


# =============================================================================
# Provider Factory
# =============================================================================

class ProviderFactory:
    """提供商工厂 - 支持最新AIGC模型"""

    _providers: Dict[ProviderType, type] = {
        # 本地服务
        ProviderType.OMNI_GEN_LOCAL: OmniGenStudioProvider,
        ProviderType.COMFYUI_LOCAL: ComfyUIProvider,
        ProviderType.COMFYUI_CLOUD: ComfyUIProvider,

        # 图像生成 (2025-2026年最新模型)
        ProviderType.Z_IMAGE: ZImageProvider,
        ProviderType.QWEN_IMAGE: QwenImageProvider,
        ProviderType.SEEDREAM5: Seedream5Provider,
        ProviderType.NANOBANANA: NanoBananaProvider,
        ProviderType.NANOBANANA_PRO: NanoBananaProvider,
        ProviderType.FLUX2_KLEIN: Flux2KleinProvider,

        # 视频生成 (2025-2026年最新模型)
        ProviderType.WAN2_X: Wan2xProvider,
        ProviderType.LTVX_2: LTVX2Provider,
        ProviderType.SEEDANCE2: None,  # 需要额外实现
        ProviderType.VOE3_1: Voe3Provider,
        ProviderType.KLING: KlingProvider,

        # 图像编辑 (2025-2026年最新模型)
        ProviderType.QWEN_IMAGE_EDIT: QwenImageEditProvider,
        ProviderType.IMAGE_EDIT: ImageEditProvider,
        ProviderType.IMAGE_UPSCALE: ImageUpscaleProvider,

        # 3D生成 (2025-2026年最新模型)
        ProviderType.TRELLIS: TRELLISProvider,
        ProviderType.HUNYUAN3D: Hunyuan3DProvider,
        ProviderType.TRIPOSR: TripoSRProvider,
        ProviderType.LGM: LGMProvider,
        ProviderType.SV3D: StableVideo3DProvider,

        # 传统API
        ProviderType.GPT: GPTImageProvider,
    }

    @classmethod
    def create_provider(cls, config: ProviderConfig) -> BaseProvider:
        """创建提供商实例"""
        provider_class = cls._providers.get(config.provider_type)
        if not provider_class:
            raise ValueError(f"Unknown provider type: {config.provider_type}")
        if provider_class is None:
            raise ValueError(f"Provider type {config.provider_type} not yet implemented")
        return provider_class(config)

    @classmethod
    def get_available_providers(cls) -> List[Dict[str, Any]]:
        """获取所有可用的提供商"""
        providers = []
        for provider_type, provider_class in cls._providers.items():
            if provider_class is not None:
                try:
                    config = ProviderConfig(
                        provider_type=provider_type,
                        name=provider_type.value
                    )
                    instance = provider_class(config)
                    models = asyncio.run(instance.list_models()) if hasattr(instance, 'list_models') else []
                    providers.append({
                        "type": provider_type.value,
                        "name": provider_type.name,
                        "models": models
                    })
                except Exception as e:
                    logger.warning(f"Failed to get provider info for {provider_type}: {e}")
        return providers


# =============================================================================
# Production Workbench Controller
# =============================================================================

class ProductionWorkbenchController:
    """
    生产工作台控制器
    统一管理所有生成服务
    """

    def __init__(self):
        # 提供商配置
        self.providers: Dict[str, ProviderConfig] = {}
        # 提供商实例
        self.provider_instances: Dict[str, BaseProvider] = {}
        # 生成任务
        self.tasks: Dict[str, GenerationResult] = {}
        # 工作流模板
        self.workflow_templates: Dict[str, WorkflowTemplate] = {}

        # 初始化默认提供商
        self._init_default_providers()

        logger.info("Production Workbench Controller initialized")

    def _init_default_providers(self):
        """初始化默认提供商"""
        # Omni Gen Studio 本地
        self.add_provider(ProviderConfig(
            provider_type=ProviderType.OMNI_GEN_LOCAL,
            name="Omni Gen Studio",
            enabled=True,
            comfyui_port=8188
        ))

        # 可灵
        self.add_provider(ProviderConfig(
            provider_type=ProviderType.KLING,
            name="可灵 (Kling)",
            enabled=False,
            api_key=""
        ))

        # GPT
        self.add_provider(ProviderConfig(
            provider_type=ProviderType.GPT,
            name="DALL-E 3",
            enabled=False,
            api_key=""
        ))

    def add_provider(self, config: ProviderConfig) -> bool:
        """添加提供商"""
        try:
            provider = ProviderFactory.create_provider(config)
            self.providers[config.provider_type.value] = config
            self.provider_instances[config.provider_type.value] = provider
            logger.info(f"Provider added: {config.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to add provider: {e}")
            return False

    def remove_provider(self, provider_type: str) -> bool:
        """移除提供商"""
        if provider_type in self.providers:
            del self.providers[provider_type]
            del self.provider_instances[provider_type]
            return True
        return False

    def get_provider(self, provider_type: str) -> Optional[BaseProvider]:
        """获取提供商"""
        return self.provider_instances.get(provider_type)

    async def generate(
        self,
        provider_type: str,
        generation_type: GenerationType,
        prompt: str,
        **kwargs
    ) -> GenerationResult:
        """执行生成"""
        provider = self.get_provider(provider_type)
        if not provider:
            return GenerationResult(
                request_id="",
                status="failed",
                provider=provider_type,
                error=f"Provider not found: {provider_type}"
            )

        # 创建请求
        request = GenerationRequest(
            request_id=str(uuid.uuid4()),
            provider_type=ProviderType(provider_type),
            generation_type=generation_type,
            prompt=prompt,
            **{k: v for k, v in kwargs.items() if k in GenerationRequest.__dataclass_fields__}
        )

        # 验证请求
        valid, error = provider.validate_request(request)
        if not valid:
            return GenerationResult(
                request_id=request.request_id,
                status="failed",
                provider=provider_type,
                error=error
            )

        # 执行生成
        result = await provider.generate(request)
        self.tasks[request.request_id] = result
        return result

    async def get_task_status(self, request_id: str) -> Optional[GenerationResult]:
        """获取任务状态"""
        return self.tasks.get(request_id)

    def cancel_task(self, request_id: str) -> bool:
        """取消任务"""
        if request_id in self.tasks:
            task = self.tasks[request_id]
            task.status = "cancelled"
            return True
        return False

    def get_providers(self) -> List[Dict[str, Any]]:
        """获取所有提供商"""
        return [
            {
                "type": p.provider_type.value,
                "name": p.name,
                "enabled": p.enabled,
            }
            for p in self.providers.values()
        ]

    def add_workflow_template(self, template: WorkflowTemplate) -> bool:
        """添加工作流模板"""
        try:
            self.workflow_templates[template.template_id] = template
            return True
        except Exception as e:
            logger.error(f"Failed to add workflow template: {e}")
            return False

    def get_workflow_templates(self, provider_type: str = None) -> List[Dict[str, Any]]:
        """获取工作流模板"""
        templates = self.workflow_templates.values()
        if provider_type:
            templates = [t for t in templates if t.provider_type.value == provider_type]
        return [
            {
                "template_id": t.template_id,
                "name": t.name,
                "description": t.description,
                "provider_type": t.provider_type.value,
                "is_default": t.is_default,
            }
            for t in templates
        ]


# Singleton
_workbench_controller: Optional[ProductionWorkbenchController] = None


def get_workbench_controller() -> ProductionWorkbenchController:
    """获取工作台控制器单例"""
    global _workbench_controller
    if _workbench_controller is None:
        _workbench_controller = ProductionWorkbenchController()
    return _workbench_controller
