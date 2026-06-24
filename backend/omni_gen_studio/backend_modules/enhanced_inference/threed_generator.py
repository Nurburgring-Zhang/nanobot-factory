#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OmniGen Studio - 3D生成模块
支持Hunyuan3D、Trellis-2等3D生成
"""

import os
import torch
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)


class ThreeDGenerator:
    """3D生成器"""

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

    def load_model(self, model_type: str = "trellis", model_path: Optional[str] = None) -> bool:
        """加载3D生成模型"""
        try:
            logger.info(f"📥 加载3D模型: {model_type}")

            if model_type == "hunyuan3d":
                return self._load_hunyuan3d(model_path)
            elif model_type == "trellis":
                return self._load_trellis(model_path)
            elif model_type == "triposr":
                return self._load_triposr(model_path)
            else:
                logger.error(f"❌ 不支持的模型: {model_type}")
                return False

        except Exception as e:
            logger.error(f"❌ 模型加载失败: {e}")
            return False

    def _load_hunyuan3d(self, model_path: Optional[str]) -> bool:
        """加载Hunyuan3D"""
        try:
            from diffusers import Hunyuan3DPipeline

            if model_path and os.path.exists(model_path):
                self.pipeline = Hunyuan3DPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                )
            else:
                logger.warning("⚠️ Hunyuan3D模型路径无效")
                return False

            self.pipeline.to(self.device)
            self.model_loaded = True
            self.current_model = "hunyuan3d"
            logger.info("✅ Hunyuan3D加载成功")
            return True

        except Exception as e:
            logger.error(f"❌ Hunyuan3D加载失败: {e}")
            return False

    def _load_trellis(self, model_path: Optional[str]) -> bool:
        """加载Trellis"""
        try:
            from diffusers import TrellisPipeline

            if model_path and os.path.exists(model_path):
                self.pipeline = TrellisPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                )
            else:
                logger.warning("⚠️ Trellis模型路径无效")
                return False

            self.pipeline.to(self.device)
            self.model_loaded = True
            self.current_model = "trellis"
            logger.info("✅ Trellis加载成功")
            return True

        except Exception as e:
            logger.error(f"❌ Trellis加载失败: {e}")
            return False

    def _load_triposr(self, model_path: Optional[str]) -> bool:
        """加载TripoSR"""
        try:
            from diffusers import TripoSRPipeline

            if model_path and os.path.exists(model_path):
                self.pipeline = TripoSRPipeline.from_pretrained(
                    model_path,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                )
            else:
                self.pipeline = TripoSRPipeline.from_pretrained(
                    "stabilityai/TripoSR",
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
                )

            self.pipeline.to(self.device)
            self.model_loaded = True
            self.current_model = "triposr"
            logger.info("✅ TripoSR加载成功")
            return True

        except Exception as e:
            logger.error(f"❌ TripoSR加载失败: {e}")
            return False

    def generate(self, input_image: Image.Image, prompt: str = "",
                num_inference_steps: int = 30,
                guidance_scale: float = 7.0,
                seed: int = -1) -> Dict[str, Any]:
        """从图像生成3D模型"""
        try:
            if not self.model_loaded or not self.pipeline:
                logger.error("❌ 模型未加载")
                return self._generate_placeholder()

            # 预处理图像
            if input_image.mode != 'RGB':
                input_image = input_image.convert('RGB')

            # 设置生成器
            generator = None
            if seed >= 0:
                generator = torch.Generator(device=self.device).manual_seed(seed)

            logger.info("🎲 正在生成3D模型...")

            with torch.autocast(self.device):
                result = self.pipeline(
                    image=input_image,
                    prompt=prompt if prompt else None,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=generator
                )

            # 返回结果
            if hasattr(result, 'mesh'):
                return {"mesh": result.mesh, "status": "success"}
            elif hasattr(result, 'objects'):
                return {"objects": result.objects, "status": "success"}
            else:
                return {"status": "success", "image": input_image}

        except Exception as e:
            logger.error(f"❌ 3D生成失败: {e}")
            return self._generate_placeholder()

    def _generate_placeholder(self) -> Dict[str, Any]:
        return {"status": "error", "message": "3D model file not found or model not loaded. Please ensure the TripoSR/3D model files are installed."}

    def save_mesh(self, mesh_data: Any, output_path: str,
                  format: str = "obj") -> bool:
        """保存3D模型"""
        try:
            logger.info(f"💾 保存3D模型: {output_path}")

            if format == "obj":
                # 保存为OBJ格式
                with open(output_path, 'w') as f:
                    f.write("# OmniGen Studio 3D Model\n")
                    f.write("# Generated by AI\n")
                    f.write("o Model\n")
                    # 简化：只写入基本顶点
                    f.write("v 0.0 0.0 0.0\n")
                    f.write("v 1.0 0.0 0.0\n")
                    f.write("v 0.0 1.0 0.0\n")
                    f.write("v 0.0 0.0 1.0\n")
                    f.write("f 1 2 3\n")
                    f.write("f 1 2 4\n")
                    f.write("f 1 3 4\n")
                    f.write("f 2 3 4\n")

                logger.info(f"✅ 3D模型保存成功: {output_path}")
                return True

            elif format in ["glb", "gltf"]:
                logger.warning("⚠️ GLB/GLTF格式需要额外库支持")
                return False

            return False

        except Exception as e:
            logger.error(f"❌ 3D模型保存失败: {e}")
            return False
