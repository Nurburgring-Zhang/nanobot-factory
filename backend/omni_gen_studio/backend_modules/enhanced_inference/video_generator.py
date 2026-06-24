#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OmniGen Studio - 视频生成模块
支持Wan2.2、LTX-Video等视频生成
"""

import os
import torch
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


class VideoGenerator:
    """视频生成器"""

    def __init__(self, device: str = "auto"):
        self.device = self._get_device(device)
        self.pipeline = None
        self.model_loaded = False
        self.current_model = None

    def _get_device(self, device: str) -> str:
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            return "cpu"
        return device

    def load_model(self, model_type: str = "wan", model_path: Optional[str] = None) -> bool:
        """加载视频生成模型"""
        try:
            logger.info(f"📥 加载视频生成模型: {model_type}")

            if model_type == "wan":
                return self._load_wan_model(model_path)
            elif model_type == "ltx":
                return self._load_ltx_model(model_path)
            elif model_type == "svd":
                return self._load_svd_model(model_path)
            else:
                logger.error(f"❌ 不支持的模型: {model_type}")
                return False

        except Exception as e:
            logger.error(f"❌ 模型加载失败: {e}")
            return False

    def _load_wan_model(self, model_path: Optional[str]) -> bool:
        """加载Wan模型"""
        try:
            from diffusers import WanVideoPipeline

            if model_path and os.path.exists(model_path):
                self.pipeline = WanVideoPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                )
            else:
                # 使用默认模型（如果可用）
                logger.warning("⚠️ Wan模型路径无效")
                return False

            self.pipeline.to(self.device)
            self.model_loaded = True
            self.current_model = "wan"
            logger.info("✅ Wan模型加载成功")
            return True

        except Exception as e:
            logger.error(f"❌ Wan模型加载失败: {e}")
            return False

    def _load_ltx_model(self, model_path: Optional[str]) -> bool:
        """加载LTX-Video模型"""
        try:
            from diffusers import LTXVideoPipeline

            if model_path and os.path.exists(model_path):
                self.pipeline = LTXVideoPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                )
            else:
                logger.warning("⚠️ LTX模型路径无效")
                return False

            self.pipeline.to(self.device)
            self.model_loaded = True
            self.current_model = "ltx"
            logger.info("✅ LTX模型加载成功")
            return True

        except Exception as e:
            logger.error(f"❌ LTX模型加载失败: {e}")
            return False

    def _load_svd_model(self, model_path: Optional[str]) -> bool:
        """加载SVD模型"""
        try:
            from diffusers import StableVideoDiffusionPipeline

            if model_path and os.path.exists(model_path):
                self.pipeline = StableVideoDiffusionPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                )
            else:
                self.pipeline = StableVideoDiffusionPipeline.from_pretrained(
                    "stabilityai/stable-video-diffusion",
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                )

            self.pipeline.to(self.device)
            self.model_loaded = True
            self.current_model = "svd"
            logger.info("✅ SVD模型加载成功")
            return True

        except Exception as e:
            logger.error(f"❌ SVD模型加载失败: {e}")
            return False

    def generate(self, prompt: str, negative_prompt: str = "",
                num_frames: int = 24, fps: int = 8,
                width: int = 512, height: int = 512,
                num_inference_steps: int = 30,
                guidance_scale: float = 7.0,
                seed: int = -1,
                first_frame: Optional[Image.Image] = None,
                last_frame: Optional[Image.Image] = None) -> List[Image.Image]:
        """生成视频"""
        try:
            if not self.model_loaded or not self.pipeline:
                logger.error("❌ 模型未加载")
                return self._generate_placeholder(num_frames)

            # 设置生成器
            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            logger.info(f"🎬 正在生成视频: {num_frames}帧, {fps}fps")

            with torch.autocast(self.device):
                if first_frame is not None and last_frame is not None:
                    # 首尾帧引导
                    result = self.pipeline(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        num_frames=num_frames,
                        num_inference_steps=num_inference_steps,
                        guidance_scale=guidance_scale,
                        first_frame=first_frame,
                        last_frame=last_frame,
                        generator=generator
                    )
                elif first_frame is not None:
                    # 首帧引导
                    result = self.pipeline(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        num_frames=num_frames,
                        num_inference_steps=num_inference_steps,
                        guidance_scale=guidance_scale,
                        first_frame=first_frame,
                        generator=generator
                    )
                else:
                    # 文生视频
                    result = self.pipeline(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        num_frames=num_frames,
                        width=width,
                        height=height,
                        num_inference_steps=num_inference_steps,
                        guidance_scale=guidance_scale,
                        generator=generator
                    )

            if hasattr(result, 'frames'):
                frames = result.frames[0] if result.frames else []
            else:
                frames = [result.images[0]] if hasattr(result, 'images') else []

            logger.info(f"✅ 视频生成完成，{len(frames)}帧")
            return frames

        except Exception as e:
            logger.error(f"❌ 视频生成失败: {e}")
            return self._generate_placeholder(num_frames)

    def _generate_placeholder(self, num_frames: int) -> List[Image.Image]:
        """生成一张错误提示图片（不是假视频）"""
        from PIL import ImageDraw
        img = Image.new('RGB', (512, 512), color=(40, 40, 60))
        draw = ImageDraw.Draw(img)
        draw.text((80, 240), "Video generation failed:", fill=(255, 100, 100))
        draw.text((80, 270), "Model not loaded/not available", fill=(200, 200, 200))
        return [img]

    def save_video(self, frames: List[Image.Image], output_path: str,
                  fps: int = 8, format: str = "mp4") -> bool:
        """保存视频"""
        try:
            import cv2

            if not frames:
                logger.error("❌ 没有帧可保存")
                return False

            # 获取尺寸
            width, height = frames[0].size

            # 编码器
            if format == "mp4":
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            elif format == "avi":
                fourcc = cv2.VideoWriter_fourcc(*'XVID')
            else:
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')

            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            for frame in frames:
                frame_rgb = cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR)
                out.write(frame_rgb)

            out.release()
            logger.info(f"✅ 视频保存成功: {output_path}")
            return True

        except Exception as e:
            logger.error(f"❌ 视频保存失败: {e}")
            # 尝试保存为GIF
            return self._save_as_gif(frames, output_path.replace('.mp4', '.gif'))

    def _save_as_gif(self, frames: List[Image.Image], output_path: str) -> bool:
        """保存为GIF"""
        try:
            if frames:
                frames[0].save(
                    output_path,
                    save_all=True,
                    append_images=frames[1:],
                    duration=int(1000 / 8),
                    loop=0
                )
                logger.info(f"✅ GIF保存成功: {output_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ GIF保存失败: {e}")
            return False

    def upscale_video(self, frames: List[Image.Image], scale: float = 2.0) -> List[Image.Image]:
        """视频放大"""
        try:
            logger.info(f"🖼️ 正在放大视频: {scale}x")
            upscaled = []
            for frame in frames:
                new_size = (int(frame.width * scale), int(frame.height * scale))
                upscaled.append(frame.resize(new_size, Image.LANCZOS))
            return upscaled
        except Exception as e:
            logger.error(f"❌ 视频放大失败: {e}")
            return frames
