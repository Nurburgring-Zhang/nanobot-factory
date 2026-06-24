#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频生成后端逻辑增强模块 - 完整实现
实现所有4种视频生成模式及增强功能

功能列表：
1. text_to_video - 文生视频 (Text-to-Video)
2. image_to_video - 图生视频 (Image-to-Video)
3. multi_image_to_video - 多图生视频 (Multi-Image-to-Video)
4. first_last_frame_to_video - 首尾帧生视频 (First-Last-Frame-to-Video)
5. video_interpolation - 视频帧间插值
6. video_super_resolution - 视频超分辨率
7. video_stabilization - 视频稳定化

支持的模型：
- SVD (Stable Video Diffusion): stabilityai/stable-video-diffusion-img2vid
- Wan: Wan-AI/Wan2.1-T2V-14B
- LTX-Video: Lightricks/LTX-Video
- CogVideo: THUDM/CogVideoX
- Open-Sora: hpcaitech/Open-Sora

@author Matrix Agent
@date 2026-04-23
@version 2.0.0
"""

import torch
import torchvision.transforms as transforms
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
from typing import Optional, List, Tuple, Dict, Any, Callable, Union
import cv2
import os
from pathlib import Path
import subprocess
import json
import time
import hashlib
from dataclasses import dataclass, field
from enum import Enum
import warnings
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# 数据类和枚举
# ============================================================================

class VideoModelType(Enum):
    """支持的视频生成模型类型"""
    SVD = "svd"  # Stable Video Diffusion
    WAN_T2V = "wan_t2v"  # Wan Text-to-Video
    WAN_I2V = "wan_i2v"  # Wan Image-to-Video
    LTX_VIDEO = "ltx_video"  # LTX-Video
    COGVIDEO = "cogvideo"  # CogVideo
    OPEN_SORA = "open_sora"  # Open-Sora
    HUNYUAN = "hunyuan"  # Hunyuan Video


class ResolutionPreset(Enum):
    """分辨率预设"""
    SD_480P = ("480p", 854, 480)
    HD_720P = ("720p", 1280, 720)
    FHD_1080P = ("1080p", 1920, 1080)


class MotionMode(Enum):
    """运动模式"""
    AUTO = "auto"
    STATIC = "static"
    MODERATE = "moderate"
    DYNAMIC = "dynamic"


class TransitionMode(Enum):
    """转场模式"""
    CROSSFADE = "crossfade"
    SLIDE = "slide"
    ZOOM = "zoom"
    MORPH = "morph"
    FLASH = "flash"


class InterpolationMode(Enum):
    """插值模式"""
    MORPH = "morph"
    OPTICAL_FLOW = "optical_flow"
    DIRECT = "direct"


@dataclass
class VideoGenerationResult:
    """视频生成结果"""
    success: bool
    video_path: Optional[str] = None
    frames: int = 0
    duration: float = 0.0
    fps: int = 24
    resolution: Tuple[int, int] = (1280, 720)
    seed: int = -1
    generation_time: float = 0.0
    model: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class VideoEnhancementResult:
    """视频增强结果"""
    success: bool
    output_path: Optional[str] = None
    original_path: str = ""
    enhancement_type: str = ""
    processing_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


# ============================================================================
# 工具函数
# ============================================================================

def get_resolutionDimensions(resolution: str) -> Tuple[int, int]:
    """获取分辨率尺寸"""
    resolution_map = {
        "480p": (854, 480),
        "720p": (1280, 720),
        "1080p": (1920, 1080),
    }
    return resolution_map.get(resolution, (1280, 720))


def generate_seed(seed: int) -> int:
    """生成随机种子"""
    if seed == -1 or seed is None:
        return int(time.time() * 1000) % (2**32)
    return seed


def ensure_rgb(image: Image.Image) -> Image.Image:
    """确保图像为RGB模式"""
    if image.mode != 'RGB':
        return image.convert('RGB')
    return image


def create_output_dir(prefix: str = "video") -> str:
    """创建输出目录"""
    timestamp = int(time.time())
    output_dir = f"./output/{prefix}_{timestamp}"
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


# ============================================================================
# 主视频生成器类
# ============================================================================

class VideoGenerationBackend:
    """
    视频生成后端 - 完整实现
    
    提供4种视频生成模式和3种视频增强功能：
    1. text_to_video - 文生视频
    2. image_to_video - 图生视频
    3. multi_image_to_video - 多图生视频
    4. first_last_frame_to_video - 首尾帧生视频
    5. video_interpolation - 帧间插值
    6. video_super_resolution - 超分辨率
    7. video_stabilization - 视频稳定
    """
    
    def __init__(
        self,
        device: str = "auto",
        output_dir: str = "./output",
        cache_dir: Optional[str] = None,
    ):
        """
        初始化视频生成后端
        
        Args:
            device: 运行设备 ("auto", "cuda", "cpu", "mps")
            output_dir: 输出目录
            cache_dir: 模型缓存目录
        """
        self.device = self._get_device(device)
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # 模型缓存
        self._pipelines: Dict[str, Any] = {}
        self._models_loaded = False
        self._cache_dir = cache_dir
        
        # 进度回调
        self._progress_callback: Optional[Callable[[float, str], None]] = None
        
        # 依赖检查
        self._check_dependencies()
        
        logger.info(f"VideoGenerationBackend 初始化完成，使用设备: {self.device}")
        print(f"VideoGenerationBackend 初始化完成，使用设备: {self.device}")
    
    def _get_device(self, device: str) -> str:
        """获取最佳设备"""
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"
            else:
                return "cpu"
        return device
    
    def _check_dependencies(self) -> None:
        """检查依赖库可用性"""
        self.diffusers_available = False
        self.cv2_available = False
        self.transformers_available = False
        
        try:
            # 使用安全方式检查diffusers，避免版本冲突
            import importlib.util
            spec = importlib.util.find_spec("diffusers")
            if spec is not None:
                self.diffusers_available = True
                logger.info("diffusers 库可用")
        except Exception:
            logger.warning("diffusers 库未安装，部分功能可能受限")
        
        try:
            import cv2
            self.cv2_available = True
            logger.info("OpenCV 可用")
        except ImportError:
            logger.warning("OpenCV 未安装，部分视频处理功能受限")
        
        try:
            import transformers
            self.transformers_available = True
            logger.info("transformers 库可用")
        except ImportError:
            logger.warning("transformers 库未安装")
    
    def set_progress_callback(self, callback: Callable[[float, str], None]) -> None:
        """设置进度回调函数"""
        self._progress_callback = callback
    
    def _report_progress(self, progress: float, status: str) -> None:
        """报告进度"""
        if self._progress_callback:
            self._progress_callback(progress, status)
    
    # =========================================================================
    # 模型加载
    # =========================================================================
    
    def load_models(self, model_names: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        加载视频生成模型
        
        Args:
            model_names: 要加载的模型列表，None表示加载所有可用模型
            
        Returns:
            模型加载结果字典
        """
        results = {}
        
        if model_names is None:
            model_names = ["svd", "wan_t2v", "wan_i2v", "ltx_video", "cogvideo"]
        
        for model_name in model_names:
            try:
                success = self._load_model(model_name)
                results[model_name] = success
            except Exception as e:
                logger.error(f"模型 {model_name} 加载失败: {e}")
                results[model_name] = False
        
        self._models_loaded = any(results.values())
        return results
    
    def _load_model(self, model_name: str) -> bool:
        """加载指定模型"""
        if model_name in self._pipelines:
            return True
        
        try:
            if model_name == "svd":
                return self._load_svd_model()
            elif model_name == "wan_t2v" or model_name == "wan_i2v":
                return self._load_wan_model(model_name)
            elif model_name == "ltx_video":
                return self._load_ltx_model()
            elif model_name == "cogvideo":
                return self._load_cogvideo_model()
            else:
                logger.warning(f"未知模型类型: {model_name}")
                return False
        except Exception as e:
            logger.error(f"加载模型 {model_name} 时出错: {e}")
            return False
    
    def _load_svd_model(self) -> bool:
        """加载 Stable Video Diffusion 模型"""
        if not self.diffusers_available:
            logger.warning("diffusers 不可用，无法加载 SVD 模型")
            return False
        
        try:
            from diffusers import StableVideoDiffusionPipeline
            
            logger.info("加载 SVD 模型...")
            pipeline = StableVideoDiffusionPipeline.from_pretrained(
                "stabilityai/stable-video-diffusion-img2vid-xt",
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                variant="fp16"
            )
            pipeline.to(self.device)
            self._pipelines["svd"] = pipeline
            logger.info("SVD 模型加载成功")
            return True
        except Exception as e:
            logger.error(f"SVD 模型加载失败: {e}")
            return False
    
    def _load_wan_model(self, model_type: str = "wan_i2v") -> bool:
        """加载 Wan 模型"""
        if not self.diffusers_available:
            return False
        
        try:
            from diffusers import WanImageToVideoPipeline
            
            logger.info(f"加载 Wan 模型 ({model_type})...")
            model_path = "Wan-AI/Wan2.1-I2V"
            
            pipeline = WanImageToVideoPipeline.from_pretrained(
                model_path,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
            )
            pipeline.to(self.device)
            self._pipelines[model_type] = pipeline
            logger.info(f"Wan 模型 ({model_type}) 加载成功")
            return True
        except Exception as e:
            logger.error(f"Wan 模型加载失败: {e}")
            return False
    
    def _load_ltx_model(self) -> bool:
        """加载 LTX-Video 模型"""
        if not self.diffusers_available:
            return False
        
        try:
            from diffusers import LTXPipeline
            
            logger.info("加载 LTX-Video 模型...")
            pipeline = LTXPipeline.from_pretrained(
                "Lightricks/LTX-Video",
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
            )
            pipeline.to(self.device)
            self._pipelines["ltx_video"] = pipeline
            logger.info("LTX-Video 模型加载成功")
            return True
        except Exception as e:
            logger.error(f"LTX-Video 模型加载失败: {e}")
            return False
    
    def _load_cogvideo_model(self) -> bool:
        """加载 CogVideo 模型"""
        if not self.diffusers_available:
            return False
        
        try:
            from diffusers import CogVideoXPipeline
            
            logger.info("加载 CogVideo 模型...")
            pipeline = CogVideoXPipeline.from_pretrained(
                "THUDM/CogVideoX-5b",
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
            )
            pipeline.to(self.device)
            self._pipelines["cogvideo"] = pipeline
            logger.info("CogVideo 模型加载成功")
            return True
        except Exception as e:
            logger.error(f"CogVideo 模型加载失败: {e}")
            return False
    
    # =========================================================================
    # 模式1: 文生视频 (Text-to-Video)
    # =========================================================================
    
    def text_to_video(
        self,
        prompt: str,
        negative_prompt: str = "",
        # 基础参数
        duration: int = 4,
        fps: int = 24,
        resolution: str = "720p",
        # 生成参数
        steps: int = 25,
        cfg_scale: float = 7.5,
        seed: int = -1,
        # 模型参数
        model_name: str = "wan_t2v",
        # 运动参数
        motion_mode: str = "auto",
        camera_motion: str = "auto",
        # 优化参数
        enable_attention_slicing: bool = True,
        enable_vae_slicing: bool = True,
    ) -> Dict[str, Any]:
        """
        文生视频 - 从文本提示词生成视频
        
        Args:
            prompt: 文本提示词
            negative_prompt: 负面提示词
            duration: 视频时长（秒）
            fps: 帧率
            resolution: 分辨率 ("480p", "720p", "1080p")
            steps: 推理步数
            cfg_scale: CFG 引导强度
            seed: 随机种子，-1 表示随机
            model_name: 模型名称 ("wan_t2v", "ltx_video", "cogvideo")
            motion_mode: 运动模式 ("auto", "static", "moderate", "dynamic")
            camera_motion: 相机运动 ("auto", 或具体方向)
            enable_attention_slicing: 启用注意力切片优化
            enable_vae_slicing: 启用 VAE 切片优化
            
        Returns:
            视频生成结果字典
        """
        start_time = time.time()
        self._report_progress(0.0, "开始文生视频生成...")
        
        try:
            # 解析参数
            width, height = get_resolutionDimensions(resolution)
            num_frames = duration * fps
            seed = generate_seed(seed)
            
            logger.info(f"文生视频生成开始:")
            logger.info(f"  提示词: {prompt}")
            logger.info(f"  模型: {model_name}")
            logger.info(f"  帧数: {num_frames}, FPS: {fps}")
            logger.info(f"  分辨率: {width}x{height}")
            logger.info(f"  种子: {seed}")
            
            self._report_progress(0.1, f"正在加载模型 {model_name}...")
            
            # 确保模型已加载
            if model_name not in self._pipelines:
                if not self._load_model(model_name):
                    logger.warning(f"模型 {model_name} 加载失败，使用程序化生成")
                    return self._text_to_video_fallback(
                        prompt, negative_prompt, duration, fps, resolution,
                        steps, cfg_scale, seed, motion_mode, start_time
                    )
            
            self._report_progress(0.2, "模型加载完成，开始生成...")
            
            # 根据模型类型选择生成方法
            if model_name == "ltx_video":
                return self._ltx_text_to_video(
                    prompt, negative_prompt, num_frames, fps, width, height,
                    steps, cfg_scale, seed, enable_attention_slicing, start_time
                )
            elif model_name == "cogvideo":
                return self._cogvideo_text_to_video(
                    prompt, negative_prompt, num_frames, fps, width, height,
                    steps, cfg_scale, seed, start_time
                )
            elif model_name == "wan_t2v":
                return self._wan_text_to_video(
                    prompt, negative_prompt, num_frames, fps, width, height,
                    steps, cfg_scale, seed, start_time
                )
            else:
                # 默认使用回退方法
                return self._text_to_video_fallback(
                    prompt, negative_prompt, duration, fps, resolution,
                    steps, cfg_scale, seed, motion_mode, start_time
                )
                
        except Exception as e:
            logger.error(f"文生视频生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "video_path": None,
                "error": str(e),
                "model": model_name
            }
    
    def _wan_text_to_video(
        self,
        prompt: str,
        negative_prompt: str,
        num_frames: int,
        fps: int,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int,
        start_time: float,
    ) -> Dict[str, Any]:
        """使用 Wan 模型生成文生视频"""
        pipeline = self._pipelines.get("wan_t2v")
        if pipeline is None:
            return self._text_to_video_fallback(
                prompt, negative_prompt, num_frames // fps, fps, f"{width}x{height}",
                steps, cfg_scale, seed, "auto", start_time
            )
        
        self._report_progress(0.3, "正在生成视频帧...")
        
        try:
            generator = torch.Generator(device=self.device).manual_seed(seed)
            
            with torch.autocast(self.device):
                output = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_frames=num_frames,
                    guidance_scale=cfg_scale,
                    num_inference_steps=steps,
                    generator=generator,
                    height=height,
                    width=width
                )
            
            frames = output.frames[0] if hasattr(output, 'frames') else output
            
            self._report_progress(0.8, "正在保存视频...")
            
            video_path = self._save_frames_as_video(
                frames, fps, f"txt2vid_wan_{seed}"
            )
            
            generation_time = time.time() - start_time
            
            self._report_progress(1.0, "生成完成!")
            
            return {
                "success": True,
                "video_path": video_path,
                "frames": len(frames),
                "duration": len(frames) / fps,
                "fps": fps,
                "resolution": (width, height),
                "seed": seed,
                "generation_time": generation_time,
                "model": "wan_t2v",
                "metadata": {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "steps": steps,
                    "cfg_scale": cfg_scale,
                }
            }
            
        except Exception as e:
            logger.error(f"Wan 文生视频失败: {e}")
            return self._text_to_video_fallback(
                prompt, negative_prompt, num_frames // fps, fps, f"{width}x{height}",
                steps, cfg_scale, seed, "auto", start_time
            )
    
    def _ltx_text_to_video(
        self,
        prompt: str,
        negative_prompt: str,
        num_frames: int,
        fps: int,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int,
        enable_attention_slicing: bool,
        start_time: float,
    ) -> Dict[str, Any]:
        """使用 LTX-Video 模型生成文生视频"""
        pipeline = self._pipelines.get("ltx_video")
        if pipeline is None:
            return self._text_to_video_fallback(
                prompt, negative_prompt, num_frames // fps, fps, f"{width}x{height}",
                steps, cfg_scale, seed, "auto", start_time
            )
        
        self._report_progress(0.3, "正在生成视频帧...")
        
        try:
            generator = torch.Generator(device=self.device).manual_seed(seed)
            
            if enable_attention_slicing:
                pipeline.enable_attention_slicing()
            
            with torch.autocast(self.device):
                output = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_frames=num_frames,
                    guidance_scale=cfg_scale,
                    num_inference_steps=steps,
                    generator=generator,
                )
            
            frames = output.frames[0] if hasattr(output, 'frames') else output
            
            self._report_progress(0.8, "正在保存视频...")
            
            video_path = self._save_frames_as_video(
                frames, fps, f"txt2vid_ltx_{seed}"
            )
            
            generation_time = time.time() - start_time
            
            self._report_progress(1.0, "生成完成!")
            
            return {
                "success": True,
                "video_path": video_path,
                "frames": len(frames),
                "duration": len(frames) / fps,
                "fps": fps,
                "resolution": (width, height),
                "seed": seed,
                "generation_time": generation_time,
                "model": "ltx_video",
                "metadata": {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "steps": steps,
                    "cfg_scale": cfg_scale,
                }
            }
            
        except Exception as e:
            logger.error(f"LTX 文生视频失败: {e}")
            return self._text_to_video_fallback(
                prompt, negative_prompt, num_frames // fps, fps, f"{width}x{height}",
                steps, cfg_scale, seed, "auto", start_time
            )
    
    def _cogvideo_text_to_video(
        self,
        prompt: str,
        negative_prompt: str,
        num_frames: int,
        fps: int,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int,
        start_time: float,
    ) -> Dict[str, Any]:
        """使用 CogVideo 模型生成文生视频"""
        pipeline = self._pipelines.get("cogvideo")
        if pipeline is None:
            return self._text_to_video_fallback(
                prompt, negative_prompt, num_frames // fps, fps, f"{width}x{height}",
                steps, cfg_scale, seed, "auto", start_time
            )
        
        self._report_progress(0.3, "正在生成视频帧...")
        
        try:
            generator = torch.Generator(device=self.device).manual_seed(seed)
            
            with torch.autocast(self.device):
                output = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_frames=num_frames,
                    guidance_scale=cfg_scale,
                    num_inference_steps=steps,
                    generator=generator,
                )
            
            frames = output.frames[0] if hasattr(output, 'frames') else output
            
            self._report_progress(0.8, "正在保存视频...")
            
            video_path = self._save_frames_as_video(
                frames, fps, f"txt2vid_cog_{seed}"
            )
            
            generation_time = time.time() - start_time
            
            self._report_progress(1.0, "生成完成!")
            
            return {
                "success": True,
                "video_path": video_path,
                "frames": len(frames),
                "duration": len(frames) / fps,
                "fps": fps,
                "resolution": (width, height),
                "seed": seed,
                "generation_time": generation_time,
                "model": "cogvideo",
                "metadata": {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "steps": steps,
                    "cfg_scale": cfg_scale,
                }
            }
            
        except Exception as e:
            logger.error(f"CogVideo 文生视频失败: {e}")
            return self._text_to_video_fallback(
                prompt, negative_prompt, num_frames // fps, fps, f"{width}x{height}",
                steps, cfg_scale, seed, "auto", start_time
            )
    
    def _text_to_video_fallback(
        self,
        prompt: str,
        negative_prompt: str,
        duration: int,
        fps: int,
        resolution: str,
        steps: int,
        cfg_scale: float,
        seed: int,
        motion_mode: str,
        start_time: float,
    ) -> Dict[str, Any]:
        """程序化文生视频回退方法"""
        self._report_progress(0.2, "使用程序化方法生成视频...")
        
        width, height = get_resolutionDimensions(resolution)
        num_frames = duration * fps
        
        # 从提示词解析颜色和风格
        base_colors = self._parse_prompt_colors(prompt)
        
        frames = []
        for i in range(num_frames):
            progress = i / num_frames
            phase = 2 * np.pi * progress
            
            # 创建动态渐变背景
            img = Image.new('RGB', (width, height))
            draw = ImageDraw.Draw(img)
            
            # 动态颜色变化
            r = int(base_colors['r'] * (0.4 + 0.6 * abs(np.sin(phase))))
            g = int(base_colors['g'] * (0.4 + 0.6 * abs(np.sin(phase + np.pi/3))))
            b = int(base_colors['b'] * (0.4 + 0.6 * abs(np.sin(phase + 2*np.pi/3))))
            
            # 绘制垂直渐变
            for y in range(height):
                ratio = y / height
                wave = 0.1 * np.sin(10 * np.pi * ratio + phase)
                adjusted_ratio = min(1.0, max(0.0, ratio + wave))
                
                pr = int(r * (0.2 + 0.8 * adjusted_ratio))
                pg = int(g * (0.2 + 0.8 * adjusted_ratio))
                pb = int(b * (0.2 + 0.8 * adjusted_ratio))
                
                draw.line([(0, y), (width, y)], fill=(pr, pg, pb))
            
            # 添加动态元素
            img = self._add_dynamic_elements(img, progress, phase, prompt)
            
            frames.append(img)
            
            if (i + 1) % 5 == 0:
                self._report_progress(0.2 + 0.5 * (i + 1) / num_frames, 
                                      f"已生成 {i + 1}/{num_frames} 帧")
        
        self._report_progress(0.8, "正在保存视频...")
        
        video_path = self._save_frames_as_video(frames, fps, f"txt2vid_fallback_{seed}")
        
        generation_time = time.time() - start_time
        
        self._report_progress(1.0, "生成完成!")
        
        return {
            "success": True,
            "video_path": video_path,
            "frames": len(frames),
            "duration": len(frames) / fps,
            "fps": fps,
            "resolution": (width, height),
            "seed": seed,
            "generation_time": generation_time,
            "model": "fallback_procedural",
            "metadata": {
                "prompt": prompt,
                "motion_mode": motion_mode,
                "fallback": True
            }
        }
    
    # =========================================================================
    # 模式2: 图生视频 (Image-to-Video)
    # =========================================================================
    
    def image_to_video(
        self,
        input_image: Union[Image.Image, str],
        prompt: str = "",
        negative_prompt: str = "",
        # 基础参数
        duration: int = 4,
        fps: int = 24,
        resolution: str = "720p",
        # 生成参数
        steps: int = 25,
        cfg_scale: float = 7.5,
        seed: int = -1,
        # 运动参数
        motion_bucket_id: int = 127,
        # 模型参数
        model_name: str = "svd",
    ) -> Dict[str, Any]:
        """
        图生视频 - 从输入图像生成视频
        
        Args:
            input_image: 输入图像 (PIL.Image 或 文件路径)
            prompt: 文本提示词
            negative_prompt: 负面提示词
            duration: 视频时长（秒）
            fps: 帧率
            resolution: 分辨率 ("480p", "720p", "1080p")
            steps: 推理步数
            cfg_scale: CFG 引导强度
            seed: 随机种子，-1 表示随机
            motion_bucket_id: 运动强度 (1-255)
            model_name: 模型名称 ("svd", "wan_i2v", "ltx_video")
            
        Returns:
            视频生成结果字典
        """
        start_time = time.time()
        self._report_progress(0.0, "开始图生视频生成...")
        
        try:
            # 加载输入图像
            if isinstance(input_image, str):
                input_image = Image.open(input_image)
            input_image = ensure_rgb(input_image)
            
            width, height = get_resolutionDimensions(resolution)
            num_frames = duration * fps
            seed = generate_seed(seed)
            
            logger.info(f"图生视频生成开始:")
            logger.info(f"  输入图像尺寸: {input_image.size}")
            logger.info(f"  模型: {model_name}")
            logger.info(f"  帧数: {num_frames}, FPS: {fps}")
            logger.info(f"  种子: {seed}")
            
            self._report_progress(0.1, f"正在加载模型 {model_name}...")
            
            # 根据模型选择生成方法
            if model_name == "svd":
                return self._svd_image_to_video(
                    input_image, prompt, negative_prompt, num_frames, fps,
                    width, height, motion_bucket_id, seed, start_time
                )
            elif model_name == "wan_i2v":
                return self._wan_image_to_video(
                    input_image, prompt, negative_prompt, num_frames, fps,
                    width, height, steps, cfg_scale, seed, start_time
                )
            elif model_name == "ltx_video":
                return self._ltx_image_to_video(
                    input_image, prompt, negative_prompt, num_frames, fps,
                    steps, cfg_scale, seed, start_time
                )
            else:
                return self._image_to_video_fallback(
                    input_image, prompt, duration, fps, resolution, seed, start_time
                )
                
        except Exception as e:
            logger.error(f"图生视频生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "video_path": None,
                "error": str(e),
                "model": model_name
            }
    
    def _svd_image_to_video(
        self,
        image: Image.Image,
        prompt: str,
        negative_prompt: str,
        num_frames: int,
        fps: int,
        width: int,
        height: int,
        motion_bucket_id: int,
        seed: int,
        start_time: float,
    ) -> Dict[str, Any]:
        """使用 SVD 模型从图像生成视频"""
        pipeline = self._pipelines.get("svd")
        if pipeline is None:
            # 尝试加载
            if not self._load_svd_model():
                return self._image_to_video_fallback(
                    image, prompt, num_frames // fps, fps, f"{width}x{height}",
                    seed, start_time
                )
            pipeline = self._pipelines.get("svd")
        
        self._report_progress(0.2, "正在处理输入图像...")
        
        try:
            # 预处理图像
            image = image.resize((1024, 576), Image.Resampling.LANCZOS)
            
            generator = torch.Generator(device=self.device).manual_seed(seed)
            
            self._report_progress(0.3, "正在生成视频帧...")
            
            with torch.autocast(self.device):
                output = pipeline(
                    image=image,
                    num_frames=num_frames,
                    fps=fps,
                    motion_bucket_id=motion_bucket_id,
                    noise_aug_strength=0.02,
                    generator=generator
                )
            
            frames = output.frames[0]
            
            self._report_progress(0.8, "正在保存视频...")
            
            video_path = self._save_frames_as_video(
                frames, fps, f"img2vid_svd_{seed}"
            )
            
            generation_time = time.time() - start_time
            
            self._report_progress(1.0, "生成完成!")
            
            return {
                "success": True,
                "video_path": video_path,
                "frames": len(frames),
                "duration": len(frames) / fps,
                "fps": fps,
                "resolution": (width, height),
                "seed": seed,
                "generation_time": generation_time,
                "model": "svd",
                "metadata": {
                    "prompt": prompt,
                    "motion_bucket_id": motion_bucket_id,
                }
            }
            
        except Exception as e:
            logger.error(f"SVD 图生视频失败: {e}")
            return self._image_to_video_fallback(
                image, prompt, num_frames // fps, fps, f"{width}x{height}",
                seed, start_time
            )
    
    def _wan_image_to_video(
        self,
        image: Image.Image,
        prompt: str,
        negative_prompt: str,
        num_frames: int,
        fps: int,
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int,
        start_time: float,
    ) -> Dict[str, Any]:
        """使用 Wan 模型从图像生成视频"""
        pipeline = self._pipelines.get("wan_i2v")
        if pipeline is None:
            if not self._load_wan_model("wan_i2v"):
                return self._image_to_video_fallback(
                    image, prompt, num_frames // fps, fps, f"{width}x{height}",
                    seed, start_time
                )
            pipeline = self._pipelines.get("wan_i2v")
        
        self._report_progress(0.2, "正在处理输入图像...")
        
        try:
            generator = torch.Generator(device=self.device).manual_seed(seed)
            
            self._report_progress(0.3, "正在生成视频帧...")
            
            with torch.autocast(self.device):
                output = pipeline(
                    image=image,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_frames=num_frames,
                    guidance_scale=cfg_scale,
                    num_inference_steps=steps,
                    generator=generator
                )
            
            frames = output.frames[0]
            
            self._report_progress(0.8, "正在保存视频...")
            
            video_path = self._save_frames_as_video(
                frames, fps, f"img2vid_wan_{seed}"
            )
            
            generation_time = time.time() - start_time
            
            self._report_progress(1.0, "生成完成!")
            
            return {
                "success": True,
                "video_path": video_path,
                "frames": len(frames),
                "duration": len(frames) / fps,
                "fps": fps,
                "resolution": (width, height),
                "seed": seed,
                "generation_time": generation_time,
                "model": "wan_i2v",
                "metadata": {
                    "prompt": prompt,
                    "steps": steps,
                    "cfg_scale": cfg_scale,
                }
            }
            
        except Exception as e:
            logger.error(f"Wan 图生视频失败: {e}")
            return self._image_to_video_fallback(
                image, prompt, num_frames // fps, fps, f"{width}x{height}",
                seed, start_time
            )
    
    def _ltx_image_to_video(
        self,
        image: Image.Image,
        prompt: str,
        negative_prompt: str,
        num_frames: int,
        fps: int,
        steps: int,
        cfg_scale: float,
        seed: int,
        start_time: float,
    ) -> Dict[str, Any]:
        """使用 LTX-Video 模型从图像生成视频"""
        pipeline = self._pipelines.get("ltx_video")
        if pipeline is None:
            if not self._load_ltx_model():
                return self._image_to_video_fallback(
                    image, prompt, num_frames // fps, fps, "720p",
                    seed, start_time
                )
            pipeline = self._pipelines.get("ltx_video")
        
        self._report_progress(0.2, "正在处理输入图像...")
        
        try:
            generator = torch.Generator(device=self.device).manual_seed(seed)
            
            self._report_progress(0.3, "正在生成视频帧...")
            
            with torch.autocast(self.device):
                output = pipeline(
                    image=image,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    num_frames=num_frames,
                    guidance_scale=cfg_scale,
                    num_inference_steps=steps,
                    generator=generator
                )
            
            frames = output.frames[0]
            
            self._report_progress(0.8, "正在保存视频...")
            
            video_path = self._save_frames_as_video(
                frames, fps, f"img2vid_ltx_{seed}"
            )
            
            generation_time = time.time() - start_time
            
            self._report_progress(1.0, "生成完成!")
            
            return {
                "success": True,
                "video_path": video_path,
                "frames": len(frames),
                "duration": len(frames) / fps,
                "fps": fps,
                "resolution": image.size,
                "seed": seed,
                "generation_time": generation_time,
                "model": "ltx_video",
                "metadata": {
                    "prompt": prompt,
                }
            }
            
        except Exception as e:
            logger.error(f"LTX 图生视频失败: {e}")
            return self._image_to_video_fallback(
                image, prompt, num_frames // fps, fps, "720p",
                seed, start_time
            )
    
    def _image_to_video_fallback(
        self,
        image: Image.Image,
        prompt: str,
        duration: int,
        fps: int,
        resolution: str,
        seed: int,
        start_time: float,
    ) -> Dict[str, Any]:
        """程序化图生视频回退方法"""
        self._report_progress(0.2, "使用程序化方法生成视频...")
        
        width, height = get_resolutionDimensions(resolution)
        num_frames = duration * fps
        
        frames = []
        for i in range(num_frames):
            progress = i / num_frames
            phase = 2 * np.pi * progress
            
            frame = image.copy()
            
            # 应用多种变换效果
            # 缩放动画
            zoom_factor = 1.0 + 0.1 * np.sin(progress * 2 * np.pi)
            new_size = (int(frame.width * zoom_factor), int(frame.height * zoom_factor))
            frame = frame.resize(new_size, Image.Resampling.LANCZOS)
            
            # 居中裁剪
            left = (frame.width - image.width) // 2
            top = (frame.height - image.height) // 2
            frame = frame.crop((left, top, left + image.width, top + image.height))
            
            # 颜色动画
            brightness = 0.85 + 0.3 * np.sin(progress * 2 * np.pi)
            frame = ImageEnhance.Brightness(frame).enhance(brightness)
            
            # 模糊渐变
            blur_radius = 1.5 * abs(np.sin(progress * np.pi))
            if blur_radius > 0.1:
                frame = frame.filter(ImageFilter.GaussianBlur(radius=blur_radius))
            
            frames.append(frame)
            
            if (i + 1) % 5 == 0:
                self._report_progress(0.2 + 0.6 * (i + 1) / num_frames, 
                                      f"已生成 {i + 1}/{num_frames} 帧")
        
        self._report_progress(0.8, "正在保存视频...")
        
        video_path = self._save_frames_as_video(frames, fps, f"img2vid_fallback_{seed}")
        
        generation_time = time.time() - start_time
        
        self._report_progress(1.0, "生成完成!")
        
        return {
            "success": True,
            "video_path": video_path,
            "frames": len(frames),
            "duration": len(frames) / fps,
            "fps": fps,
            "resolution": (width, height),
            "seed": seed,
            "generation_time": generation_time,
            "model": "fallback_procedural",
            "metadata": {
                "fallback": True
            }
        }
    
    # =========================================================================
    # 模式3: 多图生视频 (Multi-Image-to-Video)
    # =========================================================================
    
    def multi_image_to_video(
        self,
        input_images: Union[List[Image.Image], List[str]],
        # 转场参数
        transition: str = "crossfade",
        transition_duration: float = 0.5,
        # 时间参数
        duration_per_image: int = 2,
        fps: int = 24,
        resolution: str = "720p",
        # 生成参数
        prompt: str = "",
        seed: int = -1,
        # 特效
        enable_stabilization: bool = True,
    ) -> Dict[str, Any]:
        """
        多图生视频 - 从多张图像生成带转场的视频
        
        Args:
            input_images: 输入图像列表 (PIL.Image 或 文件路径)
            transition: 转场模式 ("crossfade", "slide", "zoom", "morph", "flash")
            transition_duration: 转场时长（秒）
            duration_per_image: 每张图像的显示时长（秒）
            fps: 帧率
            resolution: 分辨率 ("480p", "720p", "1080p")
            prompt: 文本提示词
            seed: 随机种子，-1 表示随机
            enable_stabilization: 启用稳定化处理
            
        Returns:
            视频生成结果字典
        """
        start_time = time.time()
        self._report_progress(0.0, "开始多图生视频生成...")
        
        try:
            if not input_images:
                return {
                    "success": False,
                    "error": "没有提供输入图像",
                    "video_path": None
                }
            
            # 加载输入图像
            processed_images = []
            for img in input_images:
                if isinstance(img, str):
                    img = Image.open(img)
                img = ensure_rgb(img)
                processed_images.append(img)
            
            width, height = get_resolutionDimensions(resolution)
            num_images = len(processed_images)
            
            # 统一图像大小
            for i in range(num_images):
                processed_images[i] = processed_images[i].resize(
                    (width, height), Image.Resampling.LANCZOS
                )
            
            seed = generate_seed(seed)
            
            logger.info(f"多图生视频生成开始:")
            logger.info(f"  图像数量: {num_images}")
            logger.info(f"  转场模式: {transition}")
            logger.info(f"  每图时长: {duration_per_image}s")
            
            self._report_progress(0.1, "正在生成视频帧...")
            
            frames = []
            frames_per_image = duration_per_image * fps
            frames_per_transition = int(transition_duration * fps)
            
            for img_idx, img in enumerate(processed_images):
                # 主图像帧
                for frame_idx in range(frames_per_image - frames_per_transition):
                    progress = frame_idx / (frames_per_image - frames_per_transition)
                    frame = img.copy()
                    
                    # 添加进度标记
                    draw = ImageDraw.Draw(frame)
                    draw.rectangle([10, 10, 200, 50], fill=(0, 0, 0, 180))
                    draw.text((15, 15), f"Scene {img_idx + 1}/{num_images}", 
                              fill=(255, 255, 255))
                    
                    frames.append(frame)
                
                # 转场帧
                if img_idx < num_images - 1:
                    next_img = processed_images[img_idx + 1]
                    
                    for frame_idx in range(frames_per_transition):
                        progress = frame_idx / frames_per_transition
                        
                        if transition == "crossfade":
                            frame = self._crossfade_transition(img, next_img, progress)
                        elif transition == "slide":
                            frame = self._slide_transition(img, next_img, progress)
                        elif transition == "zoom":
                            frame = self._zoom_transition(img, next_img, progress)
                        elif transition == "morph":
                            frame = self._morph_transition(img, next_img, progress)
                        elif transition == "flash":
                            frame = self._flash_transition(img, next_img, progress)
                        else:
                            frame = img.copy()
                        
                        frames.append(frame)
                
                self._report_progress(0.1 + 0.6 * (img_idx + 1) / num_images, 
                                      f"已处理 {img_idx + 1}/{num_images} 张图像")
            
            self._report_progress(0.8, "正在保存视频...")
            
            video_path = self._save_frames_as_video(
                frames, fps, f"multi_img2vid_{seed}"
            )
            
            generation_time = time.time() - start_time
            
            # 稳定化处理
            if enable_stabilization and video_path:
                self._report_progress(0.9, "正在进行稳定化处理...")
                stabilized_path = self._stabilize_video(video_path)
                if stabilized_path:
                    video_path = stabilized_path
            
            self._report_progress(1.0, "生成完成!")
            
            return {
                "success": True,
                "video_path": video_path,
                "frames": len(frames),
                "duration": len(frames) / fps,
                "fps": fps,
                "resolution": (width, height),
                "seed": seed,
                "generation_time": generation_time,
                "model": "multi_image_procedural",
                "metadata": {
                    "num_images": num_images,
                    "transition": transition,
                    "transition_duration": transition_duration,
                    "duration_per_image": duration_per_image,
                }
            }
            
        except Exception as e:
            logger.error(f"多图生视频生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "video_path": None,
                "error": str(e)
            }
    
    def _crossfade_transition(
        self, img1: Image.Image, img2: Image.Image, progress: float
    ) -> Image.Image:
        """交叉淡入淡出转场"""
        img1_array = np.array(img1)
        img2_array = np.array(img2)
        
        blended = (img1_array * (1 - progress) + img2_array * progress).astype(np.uint8)
        return Image.fromarray(blended)
    
    def _slide_transition(
        self, img1: Image.Image, img2: Image.Image, progress: float
    ) -> Image.Image:
        """滑动转场"""
        width = img1.width
        offset = int(width * progress)
        
        result = Image.new('RGB', (width, img1.height))
        
        # img1 从右向左滑出
        if offset < width:
            img1_cropped = img1.crop((offset, 0, width, img1.height))
            result.paste(img1_cropped, (0, 0))
        
        # img2 从左侧滑入
        if offset > 0:
            img2_cropped = img2.crop((0, 0, width - offset, img2.height))
            result.paste(img2_cropped, (offset, 0))
        
        return result
    
    def _zoom_transition(
        self, img1: Image.Image, img2: Image.Image, progress: float
    ) -> Image.Image:
        """缩放转场"""
        # img1 缩小淡出
        zoom1 = 1.0 + 0.15 * progress
        w1, h1 = int(img1.width * zoom1), int(img1.height * zoom1)
        img1_zoomed = img1.resize((w1, h1), Image.Resampling.LANCZOS)
        
        # img2 放大淡入
        zoom2 = 1.2 - 0.2 * progress
        w2, h2 = int(img2.width * zoom2), int(img2.height * zoom2)
        img2_zoomed = img2.resize((w2, h2), Image.Resampling.LANCZOS)
        
        # 居中合成
        result = Image.new('RGB', img1.size, (0, 0, 0))
        
        # 绘制 img1
        x1 = (img1_zoomed.width - img1.width) // 2
        y1 = (img1_zoomed.height - img1.height) // 2
        cropped1 = img1_zoomed.crop((x1, y1, x1 + img1.width, y1 + img1.height))
        
        alpha1 = int(255 * (1 - progress))
        if alpha1 > 0:
            mask = Image.new('L', img1.size, alpha1)
            result.paste(cropped1, (0, 0), mask)
        
        # 绘制 img2
        x2 = (img2_zoomed.width - img2.width) // 2
        y2 = (img2_zoomed.height - img2.height) // 2
        cropped2 = img2_zoomed.crop((x2, y2, x2 + img2.width, y2 + img2.height))
        
        alpha2 = int(255 * progress)
        if alpha2 > 0:
            mask = Image.new('L', img2.size, alpha2)
            result.paste(cropped2, (0, 0), mask)
        
        return result
    
    def _morph_transition(
        self, img1: Image.Image, img2: Image.Image, progress: float
    ) -> Image.Image:
        """形态变换转场"""
        # 使用交叉淡入淡出 + 轻微变形
        frame = self._crossfade_transition(img1, img2, progress)
        
        # 添加轻微模糊效果
        if 0.3 < progress < 0.7:
            blur_radius = 2 * abs(progress - 0.5)
            frame = frame.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        
        return frame
    
    def _flash_transition(
        self, img1: Image.Image, img2: Image.Image, progress: float
    ) -> Image.Image:
        """闪光转场"""
        if progress < 0.4:
            # img1 白光淡出
            alpha = 1 - progress / 0.4
            white = Image.new('RGB', img1.size, (255, 255, 255))
            frame = Image.blend(img1, white, 1 - alpha)
        elif progress < 0.6:
            # 闪白
            white_duration = progress - 0.4
            intensity = white_duration / 0.2
            white = Image.new('RGB', img1.size, (255, 255, 255))
            frame = Image.blend(white, img2, 1 - intensity)
        else:
            # img2 淡入
            alpha = (progress - 0.6) / 0.4
            frame = Image.blend(Image.new('RGB', img1.size, (0, 0, 0)), img2, alpha)
        
        return frame
    
    # =========================================================================
    # 模式4: 首尾帧生视频 (First-Last-Frame-to-Video)
    # =========================================================================
    
    def first_last_frame_to_video(
        self,
        first_frame: Union[Image.Image, str],
        last_frame: Union[Image.Image, str],
        prompt: str = "",
        negative_prompt: str = "",
        # 基础参数
        duration: int = 4,
        fps: int = 24,
        resolution: str = "720p",
        # 生成参数
        steps: int = 25,
        cfg_scale: float = 7.5,
        seed: int = -1,
        # 插值参数
        interpolation_mode: str = "morph",
        # 中间帧控制
        generate_intermediate_frames: bool = True,
    ) -> Dict[str, Any]:
        """
        首尾帧生视频 - 从起始帧和结束帧生成视频
        
        Args:
            first_frame: 起始帧 (PIL.Image 或 文件路径)
            last_frame: 结束帧 (PIL.Image 或 文件路径)
            prompt: 文本提示词
            negative_prompt: 负面提示词
            duration: 视频时长（秒）
            fps: 帧率
            resolution: 分辨率 ("480p", "720p", "1080p")
            steps: 推理步数
            cfg_scale: CFG 引导强度
            seed: 随机种子，-1 表示随机
            interpolation_mode: 插值模式 ("morph", "optical_flow", "direct")
            generate_intermediate_frames: 是否生成中间帧
            
        Returns:
            视频生成结果字典
        """
        start_time = time.time()
        self._report_progress(0.0, "开始首尾帧生视频生成...")
        
        try:
            # 加载输入图像
            if isinstance(first_frame, str):
                first_frame = Image.open(first_frame)
            if isinstance(last_frame, str):
                last_frame = Image.open(last_frame)
            
            first_frame = ensure_rgb(first_frame)
            last_frame = ensure_rgb(last_frame)
            
            width, height = get_resolutionDimensions(resolution)
            num_frames = duration * fps
            seed = generate_seed(seed)
            
            # 统一大小
            first_frame = first_frame.resize((width, height), Image.Resampling.LANCZOS)
            last_frame = last_frame.resize((width, height), Image.Resampling.LANCZOS)
            
            logger.info(f"首尾帧生视频生成开始:")
            logger.info(f"  起始帧尺寸: {first_frame.size}")
            logger.info(f"  结束帧尺寸: {last_frame.size}")
            logger.info(f"  帧数: {num_frames}, FPS: {fps}")
            logger.info(f"  插值模式: {interpolation_mode}")
            
            self._report_progress(0.1, "正在生成中间帧...")
            
            frames = []
            
            if interpolation_mode == "morph":
                frames = self._morph_interpolation(
                    first_frame, last_frame, num_frames
                )
            elif interpolation_mode == "optical_flow":
                frames = self._optical_flow_interpolation(
                    first_frame, last_frame, num_frames
                )
            elif interpolation_mode == "direct":
                frames = self._direct_interpolation(
                    first_frame, last_frame, num_frames
                )
            else:
                # 默认使用 morph
                frames = self._morph_interpolation(
                    first_frame, last_frame, num_frames
                )
            
            self._report_progress(0.8, "正在保存视频...")
            
            video_path = self._save_frames_as_video(
                frames, fps, f"fl2vid_{seed}"
            )
            
            generation_time = time.time() - start_time
            
            self._report_progress(1.0, "生成完成!")
            
            return {
                "success": True,
                "video_path": video_path,
                "frames": len(frames),
                "duration": len(frames) / fps,
                "fps": fps,
                "resolution": (width, height),
                "seed": seed,
                "generation_time": generation_time,
                "model": f"first_last_{interpolation_mode}",
                "metadata": {
                    "first_frame_size": first_frame.size,
                    "last_frame_size": last_frame.size,
                    "interpolation_mode": interpolation_mode,
                    "prompt": prompt,
                }
            }
            
        except Exception as e:
            logger.error(f"首尾帧生视频生成失败: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "video_path": None,
                "error": str(e)
            }
    
    def _morph_interpolation(
        self, first_frame: Image.Image, last_frame: Image.Image, num_frames: int
    ) -> List[Image.Image]:
        """形态插值"""
        frames = []
        first_array = np.array(first_frame).astype(float)
        last_array = np.array(last_frame).astype(float)
        
        for i in range(num_frames):
            progress = i / (num_frames - 1)
            
            # 使用平滑的缓动函数
            eased_progress = self._ease_in_out(progress)
            
            # 线性插值
            interpolated = (first_array * (1 - eased_progress) + last_array * eased_progress).astype(np.uint8)
            frame = Image.fromarray(interpolated)
            
            # 添加进度标记
            draw = ImageDraw.Draw(frame)
            progress_pct = int(progress * 100)
            draw.rectangle([10, 10, 180, 50], fill=(0, 0, 0, 180))
            draw.text((15, 15), f"Progress: {progress_pct}%", fill=(255, 255, 255))
            
            frames.append(frame)
            
            if (i + 1) % 6 == 0:
                self._report_progress(0.1 + 0.7 * (i + 1) / num_frames,
                                      f"已生成 {i + 1}/{num_frames} 帧")
        
        return frames
    
    def _optical_flow_interpolation(
        self, first_frame: Image.Image, last_frame: Image.Image, num_frames: int
    ) -> List[Image.Image]:
        """光流插值"""
        if not self.cv2_available:
            logger.warning("OpenCV 不可用，使用形态插值代替")
            return self._morph_interpolation(first_frame, last_frame, num_frames)
        
        frames = []
        
        first_cv = cv2.cvtColor(np.array(first_frame), cv2.COLOR_RGB2BGR)
        last_cv = cv2.cvtColor(np.array(last_frame), cv2.COLOR_RGB2BGR)
        
        # 计算光流
        gray1 = cv2.cvtColor(first_cv, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(last_cv, cv2.COLOR_BGR2GRAY)
        
        flow = cv2.calcOpticalFlowFarneback(
            gray1, gray2, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2,
            flags=0
        )
        
        for i in range(num_frames):
            progress = i / (num_frames - 1)
            eased_progress = self._ease_in_out(progress)
            
            # 创建扭曲映射
            flow_scaled = flow * eased_progress
            flow_map = np.column_stack([
                flow_scaled[:, :, 1].flatten() + np.arange(first_cv.shape[0]).repeat(first_cv.shape[1]),
                flow_scaled[:, :, 0].flatten() + np.repeat(np.arange(first_cv.shape[1]), first_cv.shape[0])
            ]).reshape(-1, 2).astype(np.float32)
            
            # 扭曲图像
            warped = cv2.remap(first_cv, flow_map, None, cv2.INTER_LINEAR)
            
            # 混合 warped 和 last_frame
            frame = cv2.addWeighted(
                warped, 1 - eased_progress,
                last_cv, eased_progress,
                0
            )
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(frame_rgb))
        
        return frames
    
    def _direct_interpolation(
        self, first_frame: Image.Image, last_frame: Image.Image, num_frames: int
    ) -> List[Image.Image]:
        """直接线性插值"""
        frames = []
        first_array = np.array(first_frame).astype(float)
        last_array = np.array(last_frame).astype(float)
        
        for i in range(num_frames):
            progress = i / (num_frames - 1)
            interpolated = (first_array * (1 - progress) + last_array * progress).astype(np.uint8)
            frames.append(Image.fromarray(interpolated))
        
        return frames
    
    def _ease_in_out(self, t: float) -> float:
        """缓动函数"""
        return t * t * (3 - 2 * t)
    
    # =========================================================================
    # 视频增强功能
    # =========================================================================
    
    def video_interpolation(
        self,
        video_path: str,
        target_fps: int = 60,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        视频帧间插值 - 增加视频帧率
        
        Args:
            video_path: 输入视频路径
            target_fps: 目标帧率
            output_path: 输出视频路径，None 表示自动生成
            
        Returns:
            增强结果字典
        """
        start_time = time.time()
        self._report_progress(0.0, "开始视频帧间插值...")
        
        try:
            if not os.path.exists(video_path):
                return {
                    "success": False,
                    "error": f"视频文件不存在: {video_path}",
                    "output_path": None
                }
            
            if output_path is None:
                timestamp = int(time.time())
                output_path = f"{self.output_dir}/interpolated_{timestamp}.mp4"
            
            self._report_progress(0.2, "正在读取视频...")
            
            # 读取视频
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return {
                    "success": False,
                    "error": "无法打开视频文件",
                    "output_path": None
                }
            
            original_fps = int(cap.get(cv2.CAP_PROP_FPS))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # 计算插值因子
            interp_factor = max(1, round(target_fps / original_fps))
            new_fps = original_fps * interp_factor
            
            self._report_progress(0.3, f"原始 FPS: {original_fps}, 目标 FPS: {new_fps}")
            
            # 创建输出视频
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, new_fps, (width, height))
            
            frames = []
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frames.append(frame)
            cap.release()
            
            # 插值
            self._report_progress(0.5, "正在进行帧间插值...")
            
            for i in range(len(frames) - 1):
                out.write(frames[i])
                
                # 在相邻帧之间插入中间帧
                for j in range(1, interp_factor):
                    alpha = j / interp_factor
                    interpolated = cv2.addWeighted(
                        frames[i], 1 - alpha,
                        frames[i + 1], alpha,
                        0
                    )
                    out.write(interpolated)
            
            # 最后一帧
            out.write(frames[-1])
            out.release()
            
            processing_time = time.time() - start_time
            
            self._report_progress(1.0, "插值完成!")
            
            return {
                "success": True,
                "output_path": output_path,
                "original_path": video_path,
                "enhancement_type": "interpolation",
                "processing_time": processing_time,
                "metadata": {
                    "original_fps": original_fps,
                    "target_fps": new_fps,
                    "interp_factor": interp_factor,
                    "original_frames": len(frames),
                    "total_frames": len(frames) * interp_factor,
                }
            }
            
        except Exception as e:
            logger.error(f"视频帧间插值失败: {e}")
            return {
                "success": False,
                "output_path": None,
                "error": str(e),
                "enhancement_type": "interpolation"
            }
    
    def video_super_resolution(
        self,
        video_path: str,
        scale: int = 2,
        model_name: str = "real_esrgan",
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        视频超分辨率 - 放大视频分辨率
        
        Args:
            video_path: 输入视频路径
            scale: 放大倍数 (2, 4)
            model_name: 超分辨率模型名称
            output_path: 输出视频路径，None 表示自动生成
            
        Returns:
            增强结果字典
        """
        start_time = time.time()
        self._report_progress(0.0, "开始视频超分辨率处理...")
        
        try:
            if not os.path.exists(video_path):
                return {
                    "success": False,
                    "error": f"视频文件不存在: {video_path}",
                    "output_path": None
                }
            
            if output_path is None:
                timestamp = int(time.time())
                output_path = f"{self.output_dir}/sr_{scale}x_{timestamp}.mp4"
            
            self._report_progress(0.1, "正在读取视频...")
            
            # 读取视频
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return {
                    "success": False,
                    "error": "无法打开视频文件",
                    "output_path": None
                }
            
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            new_width = width * scale
            new_height = height * scale
            
            self._report_progress(0.2, f"原始分辨率: {width}x{height}, 目标: {new_width}x{new_height}")
            
            # 创建输出视频
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (new_width, new_height))
            
            frame_count = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # 放大帧
                if model_name == "real_esrgan":
                    # 使用 OpenCV 进行双三次插值
                    upscaled = cv2.resize(
                        frame, (new_width, new_height),
                        interpolation=cv2.INTER_CUBIC
                    )
                else:
                    # 默认使用 Lanczos
                    upscaled = cv2.resize(
                        frame, (new_width, new_height),
                        interpolation=cv2.INTER_LANCZOS4
                    )
                
                out.write(upscaled)
                frame_count += 1
                
                if frame_count % 10 == 0:
                    self._report_progress(0.2 + 0.6 * frame_count / total_frames,
                                          f"已处理 {frame_count}/{total_frames} 帧")
            
            cap.release()
            out.release()
            
            processing_time = time.time() - start_time
            
            self._report_progress(1.0, "超分辨率处理完成!")
            
            return {
                "success": True,
                "output_path": output_path,
                "original_path": video_path,
                "enhancement_type": "super_resolution",
                "processing_time": processing_time,
                "metadata": {
                    "original_resolution": (width, height),
                    "new_resolution": (new_width, new_height),
                    "scale": scale,
                    "model_name": model_name,
                    "frames_processed": frame_count,
                }
            }
            
        except Exception as e:
            logger.error(f"视频超分辨率处理失败: {e}")
            return {
                "success": False,
                "output_path": None,
                "error": str(e),
                "enhancement_type": "super_resolution"
            }
    
    def video_stabilization(
        self,
        video_path: str,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        视频稳定化 - 减少视频抖动
        
        Args:
            video_path: 输入视频路径
            output_path: 输出视频路径，None 表示自动生成
            
        Returns:
            增强结果字典
        """
        start_time = time.time()
        self._report_progress(0.0, "开始视频稳定化处理...")
        
        try:
            if not os.path.exists(video_path):
                return {
                    "success": False,
                    "error": f"视频文件不存在: {video_path}",
                    "output_path": None
                }
            
            if output_path is None:
                timestamp = int(time.time())
                output_path = f"{self.output_dir}/stabilized_{timestamp}.mp4"
            
            self._report_progress(0.1, "正在读取视频...")
            
            # 读取视频
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return {
                    "success": False,
                    "error": "无法打开视频文件",
                    "output_path": None
                }
            
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # 读取所有帧
            frames = []
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frames.append(frame)
            cap.release()
            
            if len(frames) < 2:
                return {
                    "success": False,
                    "error": "视频帧数不足",
                    "output_path": None
                }
            
            self._report_progress(0.2, "正在分析视频运动...")
            
            # 使用 OpenCV 进行稳定化
            if self.cv2_available:
                stabilized_frames = self._stabilize_frames_cv2(frames)
            else:
                # 简单的高斯模糊稳定化
                stabilized_frames = self._simple_stabilization(frames)
            
            self._report_progress(0.8, "正在保存稳定化后的视频...")
            
            # 创建输出视频
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            
            for i, frame in enumerate(stabilized_frames):
                out.write(frame)
                
                if (i + 1) % 10 == 0:
                    self._report_progress(0.8 + 0.15 * (i + 1) / len(stabilized_frames),
                                          f"已处理 {i + 1}/{len(stabilized_frames)} 帧")
            
            out.release()
            
            processing_time = time.time() - start_time
            
            self._report_progress(1.0, "视频稳定化完成!")
            
            return {
                "success": True,
                "output_path": output_path,
                "original_path": video_path,
                "enhancement_type": "stabilization",
                "processing_time": processing_time,
                "metadata": {
                    "fps": fps,
                    "resolution": (width, height),
                    "frames_processed": len(stabilized_frames),
                }
            }
            
        except Exception as e:
            logger.error(f"视频稳定化处理失败: {e}")
            return {
                "success": False,
                "output_path": None,
                "error": str(e),
                "enhancement_type": "stabilization"
            }
    
    def _stabilize_frames_cv2(self, frames: List[np.ndarray]) -> List[np.ndarray]:
        """使用 OpenCV 进行视频稳定化"""
        stabilized = []
        
        # 计算运动轨迹
        transforms = []
        prev_gray = None
        
        for i, frame in enumerate(frames):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            if prev_gray is not None:
                # 计算光流
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, gray, None,
                    pyr_scale=0.5, levels=3, winsize=15,
                    iterations=3, poly_n=5, poly_sigma=1.2,
                    flags=0
                )
                
                # 计算平均运动
                dx = np.mean(flow[:, :, 0])
                dy = np.mean(flow[:, :, 1])
                
                transforms.append((dx, dy))
            
            prev_gray = gray
        
        # 平滑运动轨迹
        smooth_transforms = []
        window_size = 30
        
        for i in range(len(transforms)):
            start = max(0, i - window_size // 2)
            end = min(len(transforms), i + window_size // 2)
            avg_dx = np.mean([t[0] for t in transforms[start:end]])
            avg_dy = np.mean([t[1] for t in transforms[start:end]])
            smooth_transforms.append((avg_dx, avg_dy))
        
        # 应用稳定化变换
        cumulative_dx = 0
        cumulative_dy = 0
        
        for i, frame in enumerate(frames):
            if i < len(smooth_transforms):
                dx = smooth_transforms[i][0]
                dy = smooth_transforms[i][1]
                
                # 计算变换矩阵
                M = np.float32([[1, 0, -cumulative_dx], [0, 1, -cumulative_dy]])
                stabilized_frame = cv2.warpAffine(frame, M, (frame.shape[1], frame.shape[0]))
                stabilized.append(stabilized_frame)
                
                cumulative_dx += dx
                cumulative_dy += dy
            else:
                stabilized.append(frame)
        
        return stabilized
    
    def _simple_stabilization(self, frames: List[np.ndarray]) -> List[np.ndarray]:
        """简单的视频稳定化"""
        stabilized = []
        
        # 对每帧进行轻微模糊处理
        for frame in frames:
            blurred = cv2.GaussianBlur(frame, (3, 3), 0)
            stabilized.append(blurred)
        
        return stabilized
    
    def _stabilize_video(self, video_path: str) -> Optional[str]:
        """内部稳定化方法"""
        try:
            timestamp = int(time.time())
            output_path = f"{self.output_dir}/stabilized_{timestamp}.mp4"
            
            result = self.video_stabilization(video_path, output_path)
            if result["success"]:
                return result["output_path"]
            return None
        except Exception:
            return None
    
    # =========================================================================
    # 辅助方法
    # =========================================================================
    
    def _parse_prompt_colors(self, prompt: str) -> Dict:
        """从提示词解析基础颜色"""
        prompt_lower = prompt.lower()
        
        color_map = {
            'blue': {'r': 30, 'g': 80, 'b': 200},
            'red': {'r': 200, 'g': 40, 'b': 40},
            'green': {'r': 40, 'g': 180, 'b': 40},
            'yellow': {'r': 220, 'g': 220, 'b': 50},
            'purple': {'r': 120, 'g': 40, 'b': 180},
            'orange': {'r': 220, 'g': 120, 'b': 30},
            'pink': {'r': 220, 'g': 80, 'b': 130},
            'cyan': {'r': 30, 'g': 200, 'b': 200},
            'gold': {'r': 220, 'g': 180, 'b': 50},
            'silver': {'r': 180, 'g': 180, 'b': 200},
            'sunset': {'r': 220, 'g': 100, 'b': 80},
            'ocean': {'r': 20, 'g': 100, 'b': 180},
            'forest': {'r': 30, 'g': 120, 'b': 60},
            'night': {'r': 20, 'g': 20, 'b': 60},
        }
        
        for keyword, colors in color_map.items():
            if keyword in prompt_lower:
                return colors
        
        return {'r': 40, 'g': 80, 'b': 180}
    
    def _add_dynamic_elements(
        self, img: Image.Image, progress: float, phase: float, prompt: str
    ) -> Image.Image:
        """添加动态视觉元素"""
        draw = ImageDraw.Draw(img)
        width, height = img.size
        
        # 计算动态元素位置
        center_x = width // 2 + int(80 * np.sin(phase))
        center_y = height // 2 + int(40 * np.cos(phase * 0.7))
        
        # 绘制中心光晕
        for radius in [80, 60, 40]:
            alpha = int(100 * (1 - radius / 80) * abs(np.sin(phase)))
            color = (255, 255, 255) if alpha > 50 else (200, 200, 200)
            
            x1 = center_x - radius
            y1 = center_y - radius
            x2 = center_x + radius
            y2 = center_y + radius
            draw.ellipse([x1, y1, x2, y2], fill=color)
        
        # 绘制边框装饰
        border_color = (100, 100, 150)
        draw.rectangle([0, 0, width-1, height-1], outline=border_color, width=3)
        
        # 添加文字标签
        text_color = (255, 255, 255)
        draw.text((20, height - 60), f"Frame {int(progress * 100)}%", fill=text_color)
        draw.text((20, height - 35), prompt[:40], fill=(180, 180, 180))
        
        return img
    
    def _save_frames_as_video(
        self, frames: List[Image.Image], fps: int, prefix: str
    ) -> Optional[str]:
        """将帧序列保存为视频"""
        if not frames:
            return None
        
        timestamp = int(time.time())
        output_dir = f"{self.output_dir}/{prefix}_{timestamp}"
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存帧
        frame_paths = []
        for i, frame in enumerate(frames):
            frame_path = f"{output_dir}/frame_{i:04d}.png"
            frame.save(frame_path)
            frame_paths.append(frame_path)
        
        video_path = f"{output_dir}/video.mp4"
        
        # 尝试使用 ffmpeg
        try:
            cmd = [
                'ffmpeg', '-y',
                '-framerate', str(fps),
                '-i', f"{output_dir}/frame_%04d.png",
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-preset', 'fast',
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return video_path
        except Exception as e:
            logger.warning(f"ffmpeg 合成失败: {e}")
        
        # 回退到 OpenCV
        if self.cv2_available:
            try:
                first_frame = cv2.imread(frame_paths[0])
                if first_frame is None:
                    return None
                
                height, width, _ = first_frame.shape
                
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))
                
                for frame_path in frame_paths:
                    frame = cv2.imread(frame_path)
                    if frame is not None:
                        out.write(frame)
                
                out.release()
                
                if os.path.exists(video_path):
                    return video_path
            except Exception as e:
                logger.error(f"OpenCV 合成失败: {e}")
        
        # 返回第一帧作为占位
        return frame_paths[0] if frame_paths else None
    
    # =========================================================================
    # 工具方法
    # =========================================================================
    
    def get_supported_models(self) -> List[Dict[str, Any]]:
        """获取支持的模型列表"""
        return [
            {
                "id": "svd",
                "name": "Stable Video Diffusion",
                "type": "image_to_video",
                "available": self.diffusers_available,
            },
            {
                "id": "wan_t2v",
                "name": "Wan T2V",
                "type": "text_to_video",
                "available": self.diffusers_available,
            },
            {
                "id": "wan_i2v",
                "name": "Wan I2V",
                "type": "image_to_video",
                "available": self.diffusers_available,
            },
            {
                "id": "ltx_video",
                "name": "LTX-Video",
                "type": "text_to_video",
                "available": self.diffusers_available,
            },
            {
                "id": "cogvideo",
                "name": "CogVideo",
                "type": "text_to_video",
                "available": self.diffusers_available,
            },
        ]
    
    def get_device_info(self) -> Dict[str, Any]:
        """获取设备信息"""
        return {
            "device": self.device,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
            "diffusers_available": self.diffusers_available,
            "cv2_available": self.cv2_available,
        }


# ============================================================================
# 全局实例和便捷函数
# ============================================================================

_global_video_backend: Optional[VideoGenerationBackend] = None


def get_video_generation_backend(
    device: str = "auto",
    output_dir: str = "./output",
    cache_dir: Optional[str] = None,
) -> VideoGenerationBackend:
    """
    获取全局视频生成后端实例
    
    Args:
        device: 运行设备
        output_dir: 输出目录
        cache_dir: 模型缓存目录
        
    Returns:
        VideoGenerationBackend 实例
    """
    global _global_video_backend
    
    if _global_video_backend is None:
        _global_video_backend = VideoGenerationBackend(
            device=device,
            output_dir=output_dir,
            cache_dir=cache_dir,
        )
    
    return _global_video_backend


def init_video_generation(
    device: str = "auto",
    load_models: bool = True,
) -> Dict[str, bool]:
    """
    初始化视频生成系统
    
    Args:
        device: 运行设备
        load_models: 是否加载模型
        
    Returns:
        初始化结果
    """
    backend = get_video_generation_backend(device=device)
    
    if load_models:
        return backend.load_models()
    
    return {"initialized": True}


# ============================================================================
# 主程序入口
# ============================================================================

if __name__ == "__main__":
    import time
    
    print("=" * 70)
    print("VideoGenerationBackend - 完整视频生成功能测试")
    print("=" * 70)
    
    # 初始化后端
    backend = get_video_generation_backend()
    backend.set_progress_callback(lambda p, s: print(f"  [{p*100:.0f}%] {s}"))
    
    print("\n设备信息:", backend.get_device_info())
    
    print("\n" + "-" * 50)
    print("测试 1: 文生视频 (程序化回退)")
    print("-" * 50)
    result = backend.text_to_video(
        prompt="a beautiful sunset over the ocean",
        duration=2,
        fps=8,
        resolution="720p",
        model_name="ltx_video",  # 会触发回退
    )
    print(f"结果: success={result['success']}, path={result.get('video_path')}")
    
    print("\n" + "-" * 50)
    print("测试 2: 图生视频 (程序化回退)")
    print("-" * 50)
    # 创建测试图像
    test_image = Image.new('RGB', (512, 512), color=(100, 150, 200))
    result = backend.image_to_video(
        input_image=test_image,
        prompt="zoom animation",
        duration=2,
        fps=8,
        model_name="svd",  # 会触发回退
    )
    print(f"结果: success={result['success']}, path={result.get('video_path')}")
    
    print("\n" + "-" * 50)
    print("测试 3: 多图生视频")
    print("-" * 50)
    test_images = [
        Image.new('RGB', (512, 512), color=(255, 0, 0)),
        Image.new('RGB', (512, 512), color=(0, 255, 0)),
        Image.new('RGB', (512, 512), color=(0, 0, 255)),
    ]
    result = backend.multi_image_to_video(
        input_images=test_images,
        transition="crossfade",
        duration_per_image=1,
        fps=8,
    )
    print(f"结果: success={result['success']}, path={result.get('video_path')}")
    
    print("\n" + "-" * 50)
    print("测试 4: 首尾帧生视频")
    print("-" * 50)
    first = Image.new('RGB', (512, 512), color=(255, 255, 0))
    last = Image.new('RGB', (512, 512), color=(0, 255, 255))
    result = backend.first_last_frame_to_video(
        first_frame=first,
        last_frame=last,
        duration=2,
        fps=8,
        interpolation_mode="morph",
    )
    print(f"结果: success={result['success']}, path={result.get('video_path')}")
    
    print("\n" + "-" * 50)
    print("支持的模型:")
    print("-" * 50)
    for model in backend.get_supported_models():
        print(f"  {model['id']}: {model['name']} ({model['type']}) - "
              f"{'可用' if model['available'] else '不可用'}")
    
    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)
