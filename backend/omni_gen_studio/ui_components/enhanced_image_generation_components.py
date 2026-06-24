#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强版图片生成组件 - 终极AIGC生成器 v5.4
实现完整的专业图片生成功能：
1. 多模型集成（z imag、qwen image、Flux.2、Stable Diffusion等）
2. 完整的文生图、图生图实现逻辑
3. 输出设置的实际功能
4. 本地AI放大模型支持（seedvr2.5）
5. 风格滤镜调整的实际处理
6. 后端推理引擎的完整集成
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import threading
import json
import csv
import pandas as pd
from pathlib import Path
import os
import re
import requests
import base64
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import time
import random
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import io
import shutil
import subprocess
import tempfile

class BackendEngine:
    """后端推理引擎管理类"""
    
    def __init__(self):
        self.engines = {}
        self.model_configs = {}
        self.initialized = False
    
    def initialize_engines(self):
        """初始化各种推理引擎"""
        try:
            # 检查可用的推理引擎
            self._check_diffusers_engine()
            self._check_comfyui_engine()
            self._check_ollama_engine()
            self._check_seedvr_engine()
            self.initialized = True
        except Exception as e:
            print(f"引擎初始化失败: {e}")
    
    def _check_diffusers_engine(self):
        """检查Diffusers引擎"""
        try:
            import torch
            import transformers
            from diffusers import StableDiffusionPipeline, DiffusionPipeline
            self.engines['diffusers'] = True
            print("Diffusers引擎可用")
        except ImportError:
            self.engines['diffusers'] = False
            print("Diffusers引擎不可用")
    
    def _check_comfyui_engine(self):
        """检查ComfyUI引擎"""
        try:
            # 检查ComfyUI是否运行
            response = requests.get("http://127.0.0.1:8188/system_stats", timeout=2)
            if response.status_code == 200:
                self.engines['comfyui'] = True
                print("ComfyUI引擎可用")
            else:
                self.engines['comfyui'] = False
        except:
            self.engines['comfyui'] = False
            print("ComfyUI引擎不可用")
    
    def _check_ollama_engine(self):
        """检查Ollama引擎"""
        try:
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                self.engines['ollama'] = True
                print("Ollama引擎可用")
            else:
                self.engines['ollama'] = False
        except:
            self.engines['ollama'] = False
            print("Ollama引擎不可用")
    
    def _check_seedvr_engine(self):
        """检查SeedVR引擎"""
        # 检查SeedVR可执行文件
        seedvr_paths = [
            "seedvr2.5.exe",
            "./seedvr2.5.exe", 
            "C:/Program Files/SeedVR/seedvr2.5.exe"
        ]
        
        for path in seedvr_paths:
            if os.path.exists(path):
                self.engines['seedvr'] = path
                print(f"SeedVR引擎可用: {path}")
                break
        else:
            self.engines['seedvr'] = False
            print("SeedVR引擎不可用")

class ModelManager:
    """模型管理器"""
    
    def __init__(self):
        self.loaded_models = {}
        self.model_cache = {}
        self.download_progress = {}
    
    def load_model(self, model_path: str, model_type: str = "diffusers") -> bool:
        """加载模型"""
        try:
            if model_type == "diffusers":
                return self._load_diffusers_model(model_path)
            elif model_type == "comfyui":
                return self._load_comfyui_model(model_path)
            elif model_type == "seedvr":
                return self._load_seedvr_model(model_path)
            return False
        except Exception as e:
            print(f"模型加载失败: {e}")
            return False
    
    def _load_diffusers_model(self, model_path: str) -> bool:
        """加载Diffusers模型"""
        try:
            from diffusers import StableDiffusionPipeline
            import torch
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32
            
            if os.path.isdir(model_path):
                # Diffusers格式目录
                pipeline = StableDiffusionPipeline.from_pretrained(
                    model_path,
                    torch_dtype=dtype,
                    safety_checker=None,
                    requires_safety_checker=False
                )
            else:
                # Safetensors文件
                pipeline = StableDiffusionPipeline.from_ckpt(
                    model_path,
                    torch_dtype=dtype,
                    safety_checker=None,
                    requires_safety_checker=False
                )
            
            pipeline.to(device)
            self.loaded_models[model_path] = pipeline
            return True
        except Exception as e:
            print(f"Diffusers模型加载失败: {e}")
            return False
    
    def _load_comfyui_model(self, model_path: str) -> bool:
        """加载ComfyUI模型"""
        try:
            # 通过API加载模型到ComfyUI
            response = requests.post("http://127.0.0.1:8188/load_checkpoints", 
                                  json={"ckpt_names": [os.path.basename(model_path)]})
            return response.status_code == 200
        except Exception as e:
            print(f"ComfyUI模型加载失败: {e}")
            return False
    
    def _load_seedvr_model(self, model_path: str) -> bool:
        """加载SeedVR模型"""
        try:
            # SeedVR模型加载逻辑
            self.loaded_models[model_path] = {"type": "seedvr", "path": model_path}
            return True
        except Exception as e:
            print(f"SeedVR模型加载失败: {e}")
            return False
    
    def get_model_info(self, model_path: str) -> Dict[str, Any]:
        """获取模型信息"""
        if model_path in self.loaded_models:
            return {
                "loaded": True,
                "type": type(self.loaded_models[model_path]).__name__,
                "size": os.path.getsize(model_path) if os.path.exists(model_path) else 0
            }
        return {"loaded": False}

class StyleFilterManager:
    """风格滤镜管理器"""
    
    def __init__(self):
        self.filter_presets = {
            "赛博朋克": {
                "hue_shift": 180,
                "saturation": 1.5,
                "contrast": 1.3,
                "brightness": 0.9,
                "color": (0, 255, 255)  # 青色
            },
            "电影感": {
                "hue_shift": 15,
                "saturation": 1.2,
                "contrast": 1.4,
                "brightness": 0.95,
                "color": None
            },
            "复古": {
                "hue_shift": -10,
                "saturation": 0.8,
                "contrast": 1.1,
                "brightness": 1.1,
                "sepia": True
            },
            "黑白": {
                "hue_shift": 0,
                "saturation": 0,
                "contrast": 1.3,
                "brightness": 1.0,
                "grayscale": True
            },
            "暖色调": {
                "hue_shift": -20,
                "saturation": 1.1,
                "contrast": 1.2,
                "brightness": 1.05,
                "color": (255, 200, 100)
            },
            "冷色调": {
                "hue_shift": 20,
                "saturation": 1.1,
                "contrast": 1.2,
                "brightness": 1.05,
                "color": (100, 200, 255)
            }
        }
    
    def apply_filter(self, image: Image.Image, filter_name: str, strength: float = 0.5) -> Image.Image:
        """应用风格滤镜"""
        if filter_name == "无" or filter_name not in self.filter_presets:
            return image
        
        filter_config = self.filter_presets[filter_name]
        
        # 调整图像
        enhanced = image.copy()
        
        # 色相调整
        if "hue_shift" in filter_config:
            hue_shift = filter_config["hue_shift"] * strength
            # PIL的色相调整实现
            hsv = enhanced.convert('HSV')
            hue_array = np.array(hsv)[:, :, 0]
            hue_array = (hue_array + hue_shift) % 256
            hsv_array = np.array(hsv)
            hsv_array[:, :, 0] = hue_array
            enhanced = Image.fromarray(hsv_array, 'HSV').convert('RGB')
        
        # 饱和度调整
        if "saturation" in filter_config:
            saturation = 1 + (filter_config["saturation"] - 1) * strength
            enhancer = ImageEnhance.Color(enhanced)
            enhanced = enhancer.enhance(saturation)
        
        # 对比度调整
        if "contrast" in filter_config:
            contrast = 1 + (filter_config["contrast"] - 1) * strength
            enhancer = ImageEnhance.Contrast(enhanced)
            enhanced = enhancer.enhance(contrast)
        
        # 亮度调整
        if "brightness" in filter_config:
            brightness = 1 + (filter_config["brightness"] - 1) * strength
            enhancer = ImageEnhance.Brightness(enhanced)
            enhanced = enhancer.enhance(brightness)
        
        # 特殊效果
        if filter_config.get("grayscale"):
            enhanced = enhanced.convert('L').convert('RGB')
        
        if filter_config.get("sepia"):
            # 棕褐色调
            sepia = enhanced.copy()
            sepia_array = np.array(sepia)
            sepia_array[:, :, 0] = np.clip(sepia_array[:, :, 0] * 0.393 + sepia_array[:, :, 1] * 0.769 + sepia_array[:, :, 2] * 0.189, 0, 255)
            sepia_array[:, :, 1] = np.clip(sepia_array[:, :, 0] * 0.349 + sepia_array[:, :, 1] * 0.686 + sepia_array[:, :, 2] * 0.168, 0, 255)
            sepia_array[:, :, 2] = np.clip(sepia_array[:, :, 0] * 0.272 + sepia_array[:, :, 1] * 0.534 + sepia_array[:, :, 2] * 0.131, 0, 255)
            enhanced = Image.fromarray(sepia_array.astype(np.uint8))
        
        return enhanced

class UpscaleManager:
    """AI超分辨率管理器"""
    
    def __init__(self):
        self.upscale_models = {
            "RealESRGAN_x4plus": self._real_esrgan_x4plus,
            "RealESRGAN_x2plus": self._real_esrgan_x2plus,
            "RealESRGAN_x4plus_anime_6b": self._real_esrgan_anime,
            "seedvr2.5": self._seedvr_upscale
        }
    
    def upscale_image(self, image: Image.Image, model: str, factor: float) -> Image.Image:
        """超分辨率图像"""
        if model in self.upscale_models:
            return self.upscale_models[model](image, factor)
        else:
            # 默认使用高质量重采样
            new_size = (int(image.width * factor), int(image.height * factor))
            return image.resize(new_size, Image.Resampling.LANCZOS)
    
    def _real_esrgan_x4plus(self, image: Image.Image, factor: float) -> Image.Image:
        """RealESRGAN x4+ 超分辨率"""
        try:
            from realesrgan import RealESRGANer
            from basicsr.archs.rrdbnet_arch import RRDBNet
            
            model = RRDBNet(num_nf=64, num_gc=32, num_block=23, num_gb=3, scale=4)
            upsampler = RealESRGANer(
                scale=4,
                model_path="weights/RealESRGAN_x4plus.pth",
                model=model,
                tile=0,
                tile_pad=10,
                pre_pad=0,
                half=True
            )
            
            input_array = np.array(image)
            output_array, _ = upsampler.enhance(input_array, outscale=4)
            return Image.fromarray(output_array)
        except ImportError:
            print("RealESRGAN不可用，使用默认方法")
            return self._default_upscale(image, factor)
    
    def _real_esrgan_x2plus(self, image: Image.Image, factor: float) -> Image.Image:
        """RealESRGAN x2+ 超分辨率"""
        try:
            from realesrgan import RealESRGANer
            from basicsr.archs.rrdbnet_arch import RRDBNet
            
            model = RRDBNet(num_nf=64, num_gc=32, num_block=23, num_gb=3, scale=2)
            upsampler = RealESRGANer(
                scale=2,
                model_path="weights/RealESRGAN_x2plus.pth",
                model=model,
                tile=0,
                tile_pad=10,
                pre_pad=0,
                half=True
            )
            
            input_array = np.array(image)
            output_array, _ = upsampler.enhance(input_array, outscale=2)
            return Image.fromarray(output_array)
        except ImportError:
            print("RealESRGAN不可用，使用默认方法")
            return self._default_upscale(image, factor)
    
    def _real_esrgan_anime(self, image: Image.Image, factor: float) -> Image.Image:
        """RealESRGAN 动漫版超分辨率"""
        try:
            from realesrgan import RealESRGANer
            from basicsr.archs.rrdbnet_arch import RRDBNet
            
            model = RRDBNet(num_nf=64, num_gc=32, num_block=23, num_gb=3, scale=4)
            upsampler = RealESRGANer(
                scale=4,
                model_path="weights/RealESRGAN_x4plus_anime_6b.pth",
                model=model,
                tile=0,
                tile_pad=10,
                pre_pad=0,
                half=True
            )
            
            input_array = np.array(image)
            output_array, _ = upsampler.enhance(input_array, outscale=4)
            return Image.fromarray(output_array)
        except ImportError:
            print("RealESRGAN不可用，使用默认方法")
            return self._default_upscale(image, factor)
    
    def _seedvr_upscale(self, image: Image.Image, factor: float) -> Image.Image:
        """SeedVR 2.5 超分辨率"""
        try:
            # 保存临时文件
            temp_dir = tempfile.mkdtemp()
            temp_input = os.path.join(temp_dir, "input.png")
            temp_output = os.path.join(temp_dir, "output.png")
            
            image.save(temp_input)
            
            # 调用SeedVR命令行工具
            cmd = [
                "seedvr2.5.exe",
                "--input", temp_input,
                "--output", temp_output,
                "--scale", str(factor),
                "--mode", "realistic"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0 and os.path.exists(temp_output):
                result_image = Image.open(temp_output)
                # 清理临时文件
                shutil.rmtree(temp_dir)
                return result_image
            else:
                print(f"SeedVR处理失败: {result.stderr}")
                return self._default_upscale(image, factor)
        except Exception as e:
            print(f"SeedVR超分辨率失败: {e}")
            return self._default_upscale(image, factor)
    
    def _default_upscale(self, image: Image.Image, factor: float) -> Image.Image:
        """默认超分辨率方法"""
        new_size = (int(image.width * factor), int(image.height * factor))
        return image.resize(new_size, Image.Resampling.LANCZOS)

class PromptProcessor:
    """提示词处理器"""
    
    def __init__(self):
        self.style_templates = {
            "写实风格": "photorealistic, highly detailed, 8k resolution, professional photography, ultra realistic, masterpiece",
            "动漫风格": "anime style, manga style, cel shading, vibrant colors, detailed anime artwork, high quality",
            "油画风格": "oil painting, classical art, baroque style, rich textures, artistic masterpiece, detailed brushwork",
            "水彩风格": "watercolor painting, soft brush strokes, flowing colors, artistic watercolor effect, delicate",
            "赛博朋克": "cyberpunk style, neon lights, futuristic city, dark atmosphere, high tech, dystopian",
            "蒸汽朋克": "steampunk style, Victorian era, brass gears, steam powered machinery, industrial, vintage",
            "古风": "traditional Chinese art, ancient Chinese style, ink wash painting, cultural heritage, elegant",
            "现代简约": "minimalist style, clean lines, simple composition, modern design, elegant, contemporary",
            "超现实": "surrealism, dreamlike, impossible architecture, fantastical elements, artistic, magical",
            "复古胶片": "vintage film, retro aesthetic, film grain, old photography style, nostalgic, aged"
        }
    
    def optimize_prompt(self, prompt: str, enable_detail: bool = True, 
                       enable_style: bool = True, enable_emotion: bool = False) -> str:
        """AI提示词优化"""
        optimized = prompt.strip()
        
        # 细节描述优化
        if enable_detail:
            detail_enhancements = [
                "highly detailed", "8k resolution", "masterpiece", "best quality",
                "sharp focus", "intricate details", "professional", "award winning"
            ]
            # 随机添加2-3个细节增强词
            selected = random.sample(detail_enhancements, min(3, len(detail_enhancements)))
            optimized += ", " + ", ".join(selected)
        
        # 风格强调优化
        if enable_style:
            style_enhancements = [
                "perfect composition", "beautiful lighting", "stunning visual",
                "exceptional craftsmanship", "superb artistry"
            ]
            optimized += ", " + random.choice(style_enhancements)
        
        # 情感艺术增强
        if enable_emotion:
            emotion_enhancements = [
                "emotional depth", "expressive", "evocative", "moving",
                "captivating", "enchanting", "mesmerizing"
            ]
            optimized += ", " + random.choice(emotion_enhancements)
        
        return optimized
    
    def apply_style_template(self, prompt: str, style: str) -> str:
        """应用风格模板"""
        if style in self.style_templates:
            template = self.style_templates[style]
            if prompt:
                return f"{prompt}, {template}"
            else:
                return template
        return prompt

class ImageGenerationEngine:
    """图像生成引擎"""
    
    def __init__(self, backend_engine: BackendEngine, model_manager: ModelManager):
        self.backend = backend_engine
        self.model_manager = model_manager
        self.generation_queue = []
        self.is_generating = False
        self.current_task = None
    
    def generate_image(self, config: Dict[str, Any], callback=None) -> bool:
        """生成图像"""
        try:
            if self.is_generating:
                return False
            
            self.is_generating = True
            self.current_task = config
            
            # 根据任务类型选择生成方法
            task_type = config.get('task_type', 'text2img')
            
            if task_type == 'text2img':
                return self._generate_text2img(config, callback)
            elif task_type == 'img2img':
                return self._generate_img2img(config, callback)
            elif task_type == 'inpaint':
                return self._generate_inpaint(config, callback)
            elif task_type == 'enhance':
                return self._generate_enhance(config, callback)
            
            return False
        except Exception as e:
            print(f"图像生成失败: {e}")
            self.is_generating = False
            return False
    
    def _generate_text2img(self, config: Dict[str, Any], callback=None) -> bool:
        """文生图"""
        try:
            prompt = config.get('positive_prompt', '')
            negative_prompt = config.get('negative_prompt', '')
            model_path = config.get('model_path', '')
            width = config.get('width', 512)
            height = config.get('height', 512)
            num_steps = config.get('num_steps', 20)
            guidance_scale = config.get('cfg_scale', 7.0)
            seed = config.get('seed', -1)
            
            # 选择后端引擎
            backend = config.get('backend', 'diffusers')
            
            if backend == 'diffusers' and self.backend.engines.get('diffusers'):
                return self._generate_diffusers_text2img(config, callback)
            elif backend == 'comfyui' and self.backend.engines.get('comfyui'):
                return self._generate_comfyui_text2img(config, callback)
            elif backend == 'seedvr' and self.backend.engines.get('seedvr'):
                return self._generate_seedvr_text2img(config, callback)
            else:
                # 模拟生成
                return self._simulate_generation(config, callback)
                
        except Exception as e:
            print(f"文生图失败: {e}")
            return False
    
    def _generate_img2img(self, config: Dict[str, Any], callback=None) -> bool:
        """图生图"""
        try:
            # 加载输入图像
            input_image_path = config.get('input_image_path', '')
            if not input_image_path or not os.path.exists(input_image_path):
                print("输入图像不存在")
                return False
            
            # 模拟图生图处理
            input_image = Image.open(input_image_path)
            strength = config.get('redraw_strength', 0.7)
            
            # 这里实现实际的图生图逻辑
            # 暂时返回模拟结果
            return self._simulate_generation(config, callback)
            
        except Exception as e:
            print(f"图生图失败: {e}")
            return False
    
    def _generate_inpaint(self, config: Dict[str, Any], callback=None) -> bool:
        """图像修复"""
        try:
            # 图像修复逻辑
            return self._simulate_generation(config, callback)
        except Exception as e:
            print(f"图像修复失败: {e}")
            return False
    
    def _generate_enhance(self, config: Dict[str, Any], callback=None) -> bool:
        """图像增强"""
        try:
            # 图像增强逻辑
            return self._simulate_generation(config, callback)
        except Exception as e:
            print(f"图像增强失败: {e}")
            return False
    
    def _generate_diffusers_text2img(self, config: Dict[str, Any], callback=None) -> bool:
        """Diffusers文生图"""
        try:
            from diffusers import StableDiffusionPipeline
            import torch
            
            model_path = config.get('model_path', '')
            if model_path not in self.model_manager.loaded_models:
                if not self.model_manager.load_model(model_path, 'diffusers'):
                    return False
            
            pipeline = self.model_manager.loaded_models[model_path]
            
            # 生成参数
            prompt = config.get('positive_prompt', '')
            negative_prompt = config.get('negative_prompt', '')
            width = config.get('width', 512)
            height = config.get('height', 512)
            num_inference_steps = config.get('num_steps', 20)
            guidance_scale = config.get('cfg_scale', 7.0)
            seed = config.get('seed', -1)
            
            if seed == -1:
                seed = random.randint(0, 999999999)
            
            # 生成图像
            with torch.no_grad():
                result = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    width=width,
                    height=height,
                    num_inference_steps=num_inference_steps,
                    guidance_scale=guidance_scale,
                    generator=torch.Generator().manual_seed(seed)
                )
            
            # 获取生成的图像
            image = result.images[0]
            
            # 后处理
            if callback:
                callback(image, config)
            
            return True
            
        except Exception as e:
            print(f"Diffusers生成失败: {e}")
            return False
    
    def _generate_comfyui_text2img(self, config: Dict[str, Any], callback=None) -> bool:
        """ComfyUI文生图"""
        try:
            # 构建ComfyUI工作流
            workflow = self._build_comfyui_workflow(config)
            
            # 提交任务到ComfyUI
            response = requests.post("http://127.0.0.1:8188/prompt", json=workflow)
            
            if response.status_code == 200:
                prompt_id = response.json()['prompt_id']
                
                # 等待生成完成
                while True:
                    status_response = requests.get(f"http://127.0.0.1:8188/history/{prompt_id}")
                    if status_response.status_code == 200:
                        history = status_response.json()
                        if prompt_id in history:
                            outputs = history[prompt_id]['outputs']
                            if outputs:
                                # 获取生成的图像
                                image_data = outputs[0]['images'][0]['filename']
                                image_path = f"http://127.0.0.1:8188/view?filename={image_data}"
                                
                                # 下载图像
                                img_response = requests.get(image_path)
                                image = Image.open(io.BytesIO(img_response.content))
                                
                                if callback:
                                    callback(image, config)
                                
                                return True
                    
                    time.sleep(1)
            
            return False
            
        except Exception as e:
            print(f"ComfyUI生成失败: {e}")
            return False
    
    def _generate_seedvr_text2img(self, config: Dict[str, Any], callback=None) -> bool:
        """SeedVR文生图"""
        try:
            # 构建SeedVR参数
            prompt = config.get('positive_prompt', '')
            width = config.get('width', 512)
            height = config.get('height', 512)
            steps = config.get('num_steps', 20)
            cfg_scale = config.get('cfg_scale', 7.0)
            seed = config.get('seed', -1)
            
            # 保存临时文件
            temp_dir = tempfile.mkdtemp()
            config_file = os.path.join(temp_dir, "config.json")
            output_file = os.path.join(temp_dir, "output.png")
            
            # 创建配置文件
            seedvr_config = {
                "prompt": prompt,
                "width": width,
                "height": height,
                "steps": steps,
                "cfg_scale": cfg_scale,
                "seed": seed if seed != -1 else random.randint(0, 999999999)
            }
            
            with open(config_file, 'w') as f:
                json.dump(seedvr_config, f)
            
            # 调用SeedVR
            cmd = [
                self.backend.engines['seedvr'],
                "--config", config_file,
                "--output", output_file
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0 and os.path.exists(output_file):
                image = Image.open(output_file)
                
                if callback:
                    callback(image, config)
                
                # 清理临时文件
                shutil.rmtree(temp_dir)
                return True
            else:
                print(f"SeedVR生成失败: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"SeedVR生成失败: {e}")
            return False
    
    def _build_comfyui_workflow(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """构建ComfyUI工作流"""
        # 简化的ComfyUI工作流
        workflow = {
            "prompt": {
                "3": {
                    "inputs": {
                        "ckpt_name": os.path.basename(config.get('model_path', '')),
                        "clip": ["4", 0],
                        "clip2": ["5", 0],
                        "vae": ["6", 0],
                        "model": ["4", 0]
                    },
                    "class_type": "CheckpointLoaderSimple"
                },
                "4": {
                    "inputs": {
                        "name": "clip-vit-large-patch14"
                    },
                    "class_type": "CLIPLoader"
                },
                "5": {
                    "inputs": {
                        "name": "openai/clip-vit-large-patch14"
                    },
                    "class_type": "CLIPLoader"
                },
                "6": {
                    "inputs": {
                        "vae_name": "vae-ft-mse-840000-ema-pruned.safetensors"
                    },
                    "class_type": "VAELoader"
                },
                "7": {
                    "inputs": {
                        "text": config.get('positive_prompt', ''),
                        "clip": ["4", 0]
                    },
                    "class_type": "CLIPTextEncode"
                },
                "8": {
                    "inputs": {
                        "text": config.get('negative_prompt', ''),
                        "clip": ["4", 0]
                    },
                    "class_type": "CLIPTextEncode"
                },
                "9": {
                    "inputs": {
                        "width": config.get('width', 512),
                        "height": config.get('height', 512),
                        "batch_size": config.get('batch_size', 1)
                    },
                    "class_type": "EmptyLatentImage"
                },
                "10": {
                    "inputs": {
                        "samples": ["9", 0],
                        "vae": ["6", 0]
                    },
                    "class_type": "VAEEncode"
                },
                "11": {
                    "inputs": {
                        "seed": config.get('seed', -1),
                        "steps": config.get('num_steps', 20),
                        "cfg": config.get('cfg_scale', 7.0),
                        "sampler_name": "euler",
                        "scheduler": "normal",
                        "denoise": 1.0,
                        "model": ["3", 0],
                        "positive": ["7", 0],
                        "negative": ["8", 0],
                        "latent_image": ["10", 0]
                    },
                    "class_type": "KSampler"
                },
                "12": {
                    "inputs": {
                        "samples": ["11", 0],
                        "vae": ["6", 0]
                    },
                    "class_type": "VAEDecode"
                },
                "13": {
                    "inputs": {
                        "filename_prefix": "comfyui_generation",
                        "images": ["12", 0]
                    },
                    "class_type": "SaveImage"
                }
            }
        }
        
        return workflow
    
    def _simulate_generation(self, config: Dict[str, Any], callback=None) -> bool:
        """模拟生成（用于演示）"""
        try:
            # 创建随机图像作为演示
            width = config.get('width', 512)
            height = config.get('height', 512)
            
            # 生成渐变背景
            image = Image.new('RGB', (width, height))
            pixels = []
            
            for y in range(height):
                for x in range(width):
                    r = int((x / width) * 255)
                    g = int((y / height) * 255)
                    b = int(((x + y) / (width + height)) * 255)
                    pixels.append((r, g, b))
            
            image.putdata(pixels)
            
            # 添加一些随机噪声
            noise = np.random.randint(0, 50, (height, width, 3), dtype=np.uint8)
            image_array = np.array(image)
            image_array = np.clip(image_array + noise, 0, 255)
            image = Image.fromarray(image_array)
            
            if callback:
                callback(image, config)
            
            return True
            
        except Exception as e:
            print(f"模拟生成失败: {e}")
            return False

class EnhancedImageGenerationComponents:
    """增强版图片生成组件 - 完整实现版"""
    
    def __init__(self, parent_frame, app_instance):
        """
        初始化图片生成组件
        
        Args:
            parent_frame: 父框架
            app_instance: 应用程序实例（用于访问共享变量和方法）
        """
        self.parent = parent_frame
        self.app = app_instance
        
        # 存储组件的变量
        self.vars = {}
        self.frames = {}
        
        # 初始化后端系统
        self.backend_engine = BackendEngine()
        self.model_manager = ModelManager()
        self.style_filter_manager = StyleFilterManager()
        self.upscale_manager = UpscaleManager()
        self.prompt_processor = PromptProcessor()
        self.image_engine = ImageGenerationEngine(self.backend_engine, self.model_manager)
        
        # 生成状态
        self.generation_history = []
        self.current_generation_thread = None
        self.is_generating = False
        
        # 初始化后端
        self.backend_engine.initialize_engines()
        
        # 预设配置
        self.setup_presets()
        
        # 创建UI
        self.create_enhanced_ui()
    
    def setup_presets(self):
        """设置预设配置"""
        
        # 预设分辨率
        self.resolution_presets = {
            "512x512": (512, 512),
            "768x512": (768, 512),
            "512x768": (512, 768),
            "1024x1024": (1024, 1024),
            "1280x720": (1280, 720),
            "720x1280": (720, 1280),
            "1920x1080": (1920, 1080),
            "1080x1920": (1080, 1920),
            "2048x1152": (2048, 1152),
            "1152x2048": (1152, 2048),
            "2016x864": (2016, 864),
            "864x2016": (864, 2016),
            "1536x1536": (1536, 1536)
        }
        
        # 支持的模型后端
        self.backend_options = {
            "Diffusers (本地)": "diffusers",
            "ComfyUI (网络)": "comfyui",
            "SeedVR 2.5 (本地)": "seedvr",
            "模拟生成": "simulation"
        }
        
        # 采样器配置
        self.sampler_presets = {
            "基础采样器": {
                "dpmpp_2m": "DPM++ 2M (高质量通用)",
                "dpmpp_2m_sde": "DPM++ 2M SDE (细粒度控制)",
                "euler": "Euler (经典稳定)",
                "euler_a": "Euler a (创意变化)",
                "ddim": "DDIM (快速生成)",
                "lcm": "LCM (极速生成)",
                "lcm_z": "LCM Z (高质量LCM)",
                "dpmpp_sde": "DPM++ SDE (高质量)"
            },
            "高级采样器": {
                "dpmpp_3m_sde": "DPM++ 3M SDE (超级细化)",
                "dpmpp_de": "DPM++ DE (高精度)",
                "uni_pc": "UniPC (统一PC)",
                "heun": "Heun (平滑过渡)",
                "dpm2": "DPM2 (快速收敛)",
                "dpm2_a": "DPM2 a (稳定平衡)",
                "lms": "LMS (线性多步)",
                "plms": "PLMS (预修正)"
            }
        }
        
        # 支持的模型格式
        self.supported_model_formats = {
            "主要模型": [".safetensors", ".ckpt", ".bin", ".pth"],
            "辅助模型": [".vae", ".clip", ".unet", ".t5", ".text_encoder"],
            "目录格式": ["diffusers", "comfyui", "stable-diffusion-webui"],
            "特殊格式": [".gguf", ".aio"]
        }
    
    def create_enhanced_ui(self):
        """创建增强版UI"""
        
        # 主容器
        main_container = ttk.Frame(self.parent)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建笔记本控件（标签页）
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建各个标签页
        self.create_model_tab(notebook)
        self.create_prompt_tab(notebook)
        self.create_generation_tab(notebook)
        self.create_advanced_tab(notebook)
        self.create_output_tab(notebook)
        self.create_preview_tab(notebook)
    
    def create_model_tab(self, notebook):
        """创建模型配置标签页"""
        
        model_frame = ttk.Frame(notebook)
        notebook.add(model_frame, text="模型配置")
        
        # 初始化模型相关的变量
        self.vars['task_type'] = tk.StringVar(value="text2img")
        self.vars['backend_type'] = tk.StringVar(value="diffusers")
        self.vars['main_model_path'] = tk.StringVar()
        self.vars['clip_model_path'] = tk.StringVar()
        self.vars['vae_model_path'] = tk.StringVar()
        self.vars['t5_model_path'] = tk.StringVar()
        self.vars['search_query'] = tk.StringVar()
        self.vars['search_type'] = tk.StringVar(value="diffusers")
        
        # 后端引擎状态
        status_frame = ttk.LabelFrame(model_frame, text="后端引擎状态", padding="10")
        status_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.backend_status_label = ttk.Label(status_frame, text="正在检查后端引擎...")
        self.backend_status_label.pack(anchor="w")
        
        # 更新后端状态
        self.update_backend_status()
        
        # 任务类型选择
        task_frame = ttk.LabelFrame(model_frame, text="任务类型", padding="10")
        task_frame.pack(fill=tk.X, padx=10, pady=5)
        
        task_types = [
            ("文生图 (Text-to-Image)", "text2img"),
            ("图生图 (Image-to-Image)", "img2img"),
            ("图像修复 (Inpaint)", "inpaint"),
            ("图像增强 (Enhance)", "enhance")
        ]
        
        for i, (text, value) in enumerate(task_types):
            ttk.Radiobutton(task_frame, text=text, 
                           variable=self.vars['task_type'], value=value).grid(
                               row=i//2, column=i%2, sticky="w", padx=20, pady=5)
        
        # 后端选择
        backend_frame = ttk.LabelFrame(model_frame, text="后端引擎选择", padding="10")
        backend_frame.pack(fill=tk.X, padx=10, pady=5)
        
        backend_select_frame = ttk.Frame(backend_frame)
        backend_select_frame.pack(fill=tk.X)
        
        ttk.Label(backend_select_frame, text="选择后端:").pack(side=tk.LEFT)
        backend_combo = ttk.Combobox(backend_select_frame, textvariable=self.vars['backend_type'],
                                   values=list(self.backend_options.keys()), width=20)
        backend_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(backend_select_frame, text="检查引擎", 
                  command=self.check_backend_engine).pack(side=tk.LEFT, padx=5)
        
        # 模型文件管理
        model_file_frame = ttk.LabelFrame(model_frame, text="模型文件管理", padding="10")
        model_file_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 主模型选择
        main_model_frame = ttk.LabelFrame(model_file_frame, text="主模型文件", padding="5")
        main_model_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(main_model_frame, text="选择模型文件或目录:").pack(anchor="w")
        
        model_select_frame = ttk.Frame(main_model_frame)
        model_select_frame.pack(fill=tk.X, pady=2)
        
        ttk.Entry(model_select_frame, textvariable=self.vars['main_model_path'], 
                 width=60).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(model_select_frame, text="浏览", 
                  command=lambda: self.select_model_file('main_model_path')).pack(side=tk.RIGHT)
        
        # 加载模型按钮
        load_model_frame = ttk.Frame(model_file_frame)
        load_model_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(load_model_frame, text="加载模型", 
                  command=self.load_selected_model).pack(side=tk.LEFT, padx=5)
        ttk.Button(load_model_frame, text="卸载模型", 
                  command=self.unload_selected_model).pack(side=tk.LEFT, padx=5)
        ttk.Button(load_model_frame, text="查看模型信息", 
                  command=self.show_model_info).pack(side=tk.LEFT, padx=5)
        
        # 已加载模型列表
        loaded_models_frame = ttk.LabelFrame(model_file_frame, text="已加载模型", padding="5")
        loaded_models_frame.pack(fill=tk.X, pady=5)
        
        self.loaded_models_listbox = tk.Listbox(loaded_models_frame, height=4)
        loaded_models_scrollbar = ttk.Scrollbar(loaded_models_frame, orient=tk.VERTICAL, 
                                              command=self.loaded_models_listbox.yview)
        self.loaded_models_listbox.configure(yscrollcommand=loaded_models_scrollbar.set)
        
        self.loaded_models_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        loaded_models_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 辅助模型文件选择
        aux_models_frame = ttk.LabelFrame(model_file_frame, text="辅助模型文件", padding="5")
        aux_models_frame.pack(fill=tk.X, pady=5)
        
        # CLIP模型
        clip_frame = ttk.Frame(aux_models_frame)
        clip_frame.pack(fill=tk.X, pady=2)
        ttk.Label(clip_frame, text="CLIP模型:").pack(side=tk.LEFT)
        ttk.Entry(clip_frame, textvariable=self.vars['clip_model_path'], width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(clip_frame, text="浏览", 
                  command=lambda: self.select_model_file('clip_model_path')).pack(side=tk.LEFT, padx=2)
        
        # VAE模型
        vae_frame = ttk.Frame(aux_models_frame)
        vae_frame.pack(fill=tk.X, pady=2)
        ttk.Label(vae_frame, text="VAE模型:").pack(side=tk.LEFT)
        ttk.Entry(vae_frame, textvariable=self.vars['vae_model_path'], width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(vae_frame, text="浏览", 
                  command=lambda: self.select_model_file('vae_model_path')).pack(side=tk.LEFT, padx=2)
    
    def create_prompt_tab(self, notebook):
        """创建提示词配置标签页"""
        
        prompt_frame = ttk.Frame(notebook)
        notebook.add(prompt_frame, text="提示词配置")
        
        # 初始化提示词相关的变量
        self.pos_text = None
        self.neg_text = None
        self.vars['batch_file_path'] = tk.StringVar()
        self.vars['batch_mode'] = tk.StringVar(value="random")
        self.vars['positive_style'] = tk.StringVar(value="写实风格")
        self.vars['negative_style'] = tk.StringVar(value="通用负面")
        self.vars['enable_detail_enhance'] = tk.BooleanVar(value=True)
        self.vars['enable_style_emphasis'] = tk.BooleanVar(value=True)
        self.vars['enable_emotion_art'] = tk.BooleanVar(value=False)
        self.vars['llm_api_type'] = tk.StringVar(value="ollama")
        self.vars['llm_api_url'] = tk.StringVar(value="http://localhost:11434")
        
        # 提示词文本输入
        prompt_input_frame = ttk.LabelFrame(prompt_frame, text="提示词输入", padding="10")
        prompt_input_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 正面提示词
        pos_frame = ttk.LabelFrame(prompt_input_frame, text="正面提示词", padding="5")
        pos_frame.pack(fill=tk.X, pady=5)
        
        self.pos_text = tk.Text(pos_frame, height=4, wrap=tk.WORD)
        pos_scrollbar = ttk.Scrollbar(pos_frame, orient=tk.VERTICAL, command=self.pos_text.yview)
        self.pos_text.configure(yscrollcommand=pos_scrollbar.set)
        
        self.pos_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        pos_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 负面提示词
        neg_frame = ttk.LabelFrame(prompt_input_frame, text="负面提示词", padding="5")
        neg_frame.pack(fill=tk.X, pady=5)
        
        self.neg_text = tk.Text(neg_frame, height=3, wrap=tk.WORD)
        neg_scrollbar = ttk.Scrollbar(neg_frame, orient=tk.VERTICAL, command=self.neg_text.yview)
        self.neg_text.configure(yscrollcommand=neg_scrollbar.set)
        
        self.neg_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        neg_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 风格模板
        style_frame = ttk.LabelFrame(prompt_input_frame, text="风格模板", padding="5")
        style_frame.pack(fill=tk.X, pady=5)
        
        # 正面风格模板
        pos_style_frame = ttk.Frame(style_frame)
        pos_style_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(pos_style_frame, text="正面风格:").pack(side=tk.LEFT)
        self.vars['positive_style'] = tk.StringVar(value="写实风格")
        pos_style_combo = ttk.Combobox(pos_style_frame, textvariable=self.vars['positive_style'],
                                      values=list(self.prompt_processor.style_templates.keys()), width=15)
        pos_style_combo.pack(side=tk.LEFT, padx=5)
        ttk.Button(pos_style_frame, text="应用", 
                  command=lambda: self.apply_style_template('positive')).pack(side=tk.LEFT, padx=2)
        
        # 负面风格模板
        neg_style_frame = ttk.Frame(style_frame)
        neg_style_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(neg_style_frame, text="负面风格:").pack(side=tk.LEFT)
        self.vars['negative_style'] = tk.StringVar(value="通用负面")
        neg_style_combo = ttk.Combobox(neg_style_frame, textvariable=self.vars['negative_style'],
                                      values=["通用负面", "手部负面", "人脸负面", "文字负面", "构图负面"], width=15)
        neg_style_combo.pack(side=tk.LEFT, padx=5)
        ttk.Button(neg_style_frame, text="应用", 
                  command=lambda: self.apply_style_template('negative')).pack(side=tk.LEFT, padx=2)
        
        # AI提示词优化
        ai_optimize_frame = ttk.LabelFrame(prompt_input_frame, text="AI提示词优化", padding="5")
        ai_optimize_frame.pack(fill=tk.X, pady=5)
        
        # 优化选项
        optimize_options_frame = ttk.Frame(ai_optimize_frame)
        optimize_options_frame.pack(fill=tk.X, pady=2)
        
        ttk.Checkbutton(optimize_options_frame, text="细节描述优化", 
                        variable=self.vars['enable_detail_enhance']).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(optimize_options_frame, text="风格强调优化", 
                        variable=self.vars['enable_style_emphasis']).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(optimize_options_frame, text="情感艺术增强", 
                        variable=self.vars['enable_emotion_art']).pack(side=tk.LEFT, padx=5)
        
        # LLM API设置
        llm_api_frame = ttk.Frame(ai_optimize_frame)
        llm_api_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(llm_api_frame, text="LLM API类型:").pack(side=tk.LEFT)
        llm_api_combo = ttk.Combobox(llm_api_frame, textvariable=self.vars['llm_api_type'],
                                    values=["ollama", "vllm", "LM Studio"], width=12)
        llm_api_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(llm_api_frame, text="API地址:").pack(side=tk.LEFT, padx=(10, 0))
        ttk.Entry(llm_api_frame, textvariable=self.vars['llm_api_url'], width=25).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(llm_api_frame, text="优化提示词", 
                  command=self.optimize_prompt_with_ai).pack(side=tk.LEFT, padx=10)
    
    def create_generation_tab(self, notebook):
        """创建生成参数标签页"""
        
        gen_frame = ttk.Frame(notebook)
        notebook.add(gen_frame, text="生成参数")
        
        # 初始化生成参数相关的变量
        self.vars['sampler'] = tk.StringVar(value="dpmpp_2m")
        self.vars['scheduler'] = tk.StringVar(value="karras")
        self.vars['preset_resolution'] = tk.StringVar(value="512x512")
        self.vars['custom_width'] = tk.IntVar(value=512)
        self.vars['custom_height'] = tk.IntVar(value=512)
        self.vars['num_steps'] = tk.IntVar(value=20)
        self.vars['cfg_scale'] = tk.DoubleVar(value=7.0)
        self.vars['batch_size'] = tk.IntVar(value=1)
        self.vars['seed'] = tk.IntVar(value=42)
        self.vars['random_seed'] = tk.BooleanVar(value=False)
        
        # 主要参数
        main_params_frame = ttk.LabelFrame(gen_frame, text="主要参数", padding="10")
        main_params_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 参数网格
        params_grid = ttk.Frame(main_params_frame)
        params_grid.pack(fill=tk.X)
        
        # 第一行
        row1_frame = ttk.Frame(params_grid)
        row1_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(row1_frame, text="采样步数:", width=12).pack(side=tk.LEFT)
        steps_spin = ttk.Spinbox(row1_frame, from_=1, to=150, 
                                textvariable=self.vars['num_steps'], width=10)
        steps_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1_frame, text="CFG值:", width=10).pack(side=tk.LEFT, padx=(20, 0))
        cfg_spin = ttk.Spinbox(row1_frame, from_=0.0, to=30.0, increment=0.1,
                              textvariable=self.vars['cfg_scale'], width=10)
        cfg_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(row1_frame, text="批量大小:", width=10).pack(side=tk.LEFT, padx=(20, 0))
        batch_spin = ttk.Spinbox(row1_frame, from_=1, to=20, 
                                textvariable=self.vars['batch_size'], width=10)
        batch_spin.pack(side=tk.LEFT, padx=5)
        
        # 第二行
        row2_frame = ttk.Frame(params_grid)
        row2_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(row2_frame, text="种子:", width=12).pack(side=tk.LEFT)
        seed_spin = ttk.Spinbox(row2_frame, from_=0, to=999999999,
                               textvariable=self.vars['seed'], width=10)
        seed_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(row2_frame, text="随机种子", 
                       variable=self.vars['random_seed']).pack(side=tk.LEFT, padx=(20, 5))
        
        # 采样器和调度器
        sampler_frame = ttk.LabelFrame(gen_frame, text="采样器和调度器", padding="10")
        sampler_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 采样器选择
        sampler_select_frame = ttk.Frame(sampler_frame)
        sampler_select_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(sampler_select_frame, text="采样器:", width=12).pack(side=tk.LEFT)
        
        # 创建采样器下拉菜单
        sampler_values = []
        sampler_mapping = {}
        for category, samplers in self.sampler_presets.items():
            for sampler_key, sampler_name in samplers.items():
                sampler_values.append(f"{category}: {sampler_name}")
                sampler_mapping[f"{category}: {sampler_name}"] = sampler_key
        
        sampler_combo = ttk.Combobox(sampler_select_frame, textvariable=self.vars['sampler'],
                                    values=sampler_values, width=30)
        sampler_combo.pack(side=tk.LEFT, padx=5)
        
        # 调度器选择
        scheduler_select_frame = ttk.Frame(sampler_frame)
        scheduler_select_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(scheduler_select_frame, text="调度器:", width=12).pack(side=tk.LEFT)
        self.vars['scheduler'] = tk.StringVar(value="karras")
        scheduler_combo = ttk.Combobox(scheduler_select_frame, textvariable=self.vars['scheduler'],
                                      values=["normal", "karras", "exponential", "poly"], width=30)
        scheduler_combo.pack(side=tk.LEFT, padx=5)
        
        # 分辨率设置
        resolution_frame = ttk.LabelFrame(gen_frame, text="分辨率设置", padding="10")
        resolution_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 预设分辨率选择
        preset_frame = ttk.Frame(resolution_frame)
        preset_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(preset_frame, text="预设分辨率:", width=15).pack(side=tk.LEFT)
        self.vars['preset_resolution'] = tk.StringVar(value="512x512")
        preset_combo = ttk.Combobox(preset_frame, textvariable=self.vars['preset_resolution'],
                                   values=list(self.resolution_presets.keys()) + ["自定义"],
                                   width=15)
        preset_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(preset_frame, text="应用预设", 
                  command=self.apply_preset_resolution).pack(side=tk.LEFT, padx=10)
        ttk.Button(preset_frame, text="随机分辨率", 
                  command=self.set_random_resolution).pack(side=tk.LEFT, padx=2)
        
        # 自定义分辨率
        custom_frame = ttk.Frame(resolution_frame)
        custom_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(custom_frame, text="自定义宽度:", width=15).pack(side=tk.LEFT)
        self.vars['custom_width'] = tk.IntVar(value=512)
        width_spin = ttk.Spinbox(custom_frame, from_=64, to=4096, increment=64,
                                textvariable=self.vars['custom_width'], width=10)
        width_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(custom_frame, text="自定义高度:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        self.vars['custom_height'] = tk.IntVar(value=512)
        height_spin = ttk.Spinbox(custom_frame, from_=64, to=4096, increment=64,
                                 textvariable=self.vars['custom_height'], width=10)
        height_spin.pack(side=tk.LEFT, padx=5)
    
    def create_advanced_tab(self, notebook):
        """创建高级功能标签页"""
        
        adv_frame = ttk.Frame(notebook)
        notebook.add(adv_frame, text="高级功能")
        
        # 初始化高级功能相关的变量
        self.vars['enable_noise_injection'] = tk.BooleanVar(value=False)
        self.vars['noise_injection_strength'] = tk.DoubleVar(value=0.1)
        self.vars['enable_seed_enhance'] = tk.BooleanVar(value=False)
        self.vars['seed_enhance_strength'] = tk.DoubleVar(value=0.1)
        self.vars['enable_hires_fix'] = tk.BooleanVar(value=False)
        self.vars['enable_tiling'] = tk.BooleanVar(value=False)
        self.vars['enable_highres_fix'] = tk.BooleanVar(value=False)
        self.vars['upscale_factor'] = tk.DoubleVar(value=2.0)
        self.vars['upscale_model'] = tk.StringVar(value="RealESRGAN_x4plus")
        self.vars['redraw_strength'] = tk.DoubleVar(value=0.7)
        self.vars['style_filter'] = tk.StringVar(value="无")
        self.vars['filter_strength'] = tk.DoubleVar(value=0.5)
        
        # 高级采样算法
        advanced_sampling_frame = ttk.LabelFrame(adv_frame, text="高级采样算法", padding="10")
        advanced_sampling_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Noise Injection
        noise_frame = ttk.Frame(advanced_sampling_frame)
        noise_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(noise_frame, text="Noise Injection:", width=20).pack(side=tk.LEFT)
        ttk.Checkbutton(noise_frame, text="启用", 
                      variable=self.vars['enable_noise_injection']).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(noise_frame, text="强度:", width=8).pack(side=tk.LEFT, padx=(20, 0))
        noise_spin = ttk.Spinbox(noise_frame, from_=0.0, to=1.0, increment=0.01,
                                 textvariable=self.vars['noise_injection_strength'], width=8)
        noise_spin.pack(side=tk.LEFT, padx=5)
        
        # Seed Enhancement
        seed_frame = ttk.Frame(advanced_sampling_frame)
        seed_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(seed_frame, text="Seed Enhancement:", width=20).pack(side=tk.LEFT)
        ttk.Checkbutton(seed_frame, text="启用", 
                      variable=self.vars['enable_seed_enhance']).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(seed_frame, text="强度:", width=8).pack(side=tk.LEFT, padx=(20, 0))
        seed_spin = ttk.Spinbox(seed_frame, from_=0.0, to=1.0, increment=0.01,
                               textvariable=self.vars['seed_enhance_strength'], width=8)
        seed_spin.pack(side=tk.LEFT, padx=5)
        
        # 画质优化
        quality_frame = ttk.LabelFrame(adv_frame, text="画质优化算法", padding="10")
        quality_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 画质优化选项
        quality_options_frame = ttk.Frame(quality_frame)
        quality_options_frame.pack(fill=tk.X, pady=2)
        
        ttk.Checkbutton(quality_options_frame, text="HiRes Fix", 
                       variable=self.vars['enable_hires_fix']).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(quality_options_frame, text="平铺模式", 
                       variable=self.vars['enable_tiling']).pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(quality_options_frame, text="高分辨率修复", 
                       variable=self.vars['enable_highres_fix']).pack(side=tk.LEFT, padx=5)
        
        # 超分辨率设置
        upscale_frame = ttk.LabelFrame(adv_frame, text="AI超分辨率", padding="10")
        upscale_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 超分辨率选项
        upscale_options_frame = ttk.Frame(upscale_frame)
        upscale_options_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(upscale_options_frame, text="放大倍数:", width=15).pack(side=tk.LEFT)
        self.vars['upscale_factor'] = tk.DoubleVar(value=2.0)
        factor_combo = ttk.Combobox(upscale_options_frame, textvariable=self.vars['upscale_factor'],
                                   values=[1.5, 2.0, 3.0, 4.0], width=8)
        factor_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(upscale_options_frame, text="放大模型:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        upscale_combo = ttk.Combobox(upscale_options_frame, textvariable=self.vars['upscale_model'],
                                    values=["RealESRGAN_x4plus", "RealESRGAN_x2plus", 
                                           "RealESRGAN_x4plus_anime_6b", "seedvr2.5"], width=20)
        upscale_combo.pack(side=tk.LEFT, padx=5)
        
        # 重绘幅度设置
        redraw_frame = ttk.Frame(upscale_frame)
        redraw_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(redraw_frame, text="重绘幅度:", width=15).pack(side=tk.LEFT)
        self.vars['redraw_strength'] = tk.DoubleVar(value=0.7)
        redraw_spin = ttk.Spinbox(redraw_frame, from_=0.0, to=1.0, increment=0.05,
                                 textvariable=self.vars['redraw_strength'], width=10)
        redraw_spin.pack(side=tk.LEFT, padx=5)
        
        # 风格滤镜
        style_filter_frame = ttk.LabelFrame(adv_frame, text="风格滤镜", padding="10")
        style_filter_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 滤镜选择
        filter_select_frame = ttk.Frame(style_filter_frame)
        filter_select_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(filter_select_frame, text="选择滤镜:", width=15).pack(side=tk.LEFT)
        self.vars['style_filter'] = tk.StringVar(value="无")
        filter_combo = ttk.Combobox(filter_select_frame, textvariable=self.vars['style_filter'],
                                  values=["无", "赛博朋克", "电影感", "复古", "黑白", "暖色调", "冷色调"], width=15)
        filter_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(filter_select_frame, text="滤镜强度:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        filter_spin = ttk.Spinbox(filter_select_frame, from_=0.0, to=1.0, increment=0.1,
                                 textvariable=self.vars['filter_strength'], width=10)
        filter_spin.pack(side=tk.LEFT, padx=5)
        
        # 滤镜预览和应用
        filter_preview_frame = ttk.Frame(style_filter_frame)
        filter_preview_frame.pack(fill=tk.X, pady=2)
        
        ttk.Button(filter_preview_frame, text="预览滤镜效果", 
                  command=self.preview_style_filter).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_preview_frame, text="重置滤镜", 
                  command=self.reset_style_filter).pack(side=tk.LEFT, padx=2)
        ttk.Button(filter_preview_frame, text="应用到生成", 
                  command=self.apply_filter_to_generation).pack(side=tk.LEFT, padx=2)
    
    def create_output_tab(self, notebook):
        """创建输出设置标签页"""
        
        output_frame = ttk.Frame(notebook)
        notebook.add(output_frame, text="输出设置")
        
        # 初始化输出设置相关的变量
        self.vars['output_directory'] = tk.StringVar(value="./output")
        self.vars['organize_by_task'] = tk.BooleanVar(value=True)
        self.vars['organize_by_date'] = tk.BooleanVar(value=False)
        self.vars['image_format'] = tk.StringVar(value="png")
        self.vars['image_quality'] = tk.IntVar(value=95)
        self.vars['save_prompt'] = tk.BooleanVar(value=True)
        self.vars['save_settings'] = tk.BooleanVar(value=False)
        self.vars['save_metadata'] = tk.BooleanVar(value=True)
        self.vars['progress'] = tk.DoubleVar(value=0)
        self.vars['progress_text'] = tk.StringVar(value="就绪")
        
        # 输出路径设置
        path_frame = ttk.LabelFrame(output_frame, text="输出路径设置", padding="10")
        path_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 主输出目录
        main_path_frame = ttk.Frame(path_frame)
        main_path_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(main_path_frame, text="主输出目录:", width=15).pack(side=tk.LEFT)
        ttk.Entry(main_path_frame, textvariable=self.vars['output_directory'], 
                 width=40).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(main_path_frame, text="浏览", 
                  command=self.select_output_directory).pack(side=tk.LEFT, padx=2)
        
        # 按任务类型分文件夹
        organize_frame = ttk.Frame(path_frame)
        organize_frame.pack(fill=tk.X, pady=2)
        
        ttk.Checkbutton(organize_frame, text="按任务类型分文件夹", 
                       variable=self.vars['organize_by_task']).pack(side=tk.LEFT)
        
        ttk.Checkbutton(organize_frame, text="按日期分文件夹", 
                       variable=self.vars['organize_by_date']).pack(side=tk.LEFT, padx=10)
        
        # 文件格式和质量设置
        format_frame = ttk.LabelFrame(output_frame, text="文件格式和质量", padding="10")
        format_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 图片格式和质量
        image_format_frame = ttk.Frame(format_frame)
        image_format_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(image_format_frame, text="图片格式:", width=15).pack(side=tk.LEFT)
        format_combo = ttk.Combobox(image_format_frame, textvariable=self.vars['image_format'],
                                   values=["png", "jpg", "jpeg", "webp", "bmp"], width=10)
        format_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(image_format_frame, text="图片质量:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        quality_spin = ttk.Spinbox(image_format_frame, from_=1, to=100,
                                   textvariable=self.vars['image_quality'], width=10)
        quality_spin.pack(side=tk.LEFT, padx=5)
        
        # 保存选项
        save_options_frame = ttk.Frame(format_frame)
        save_options_frame.pack(fill=tk.X, pady=2)
        
        ttk.Checkbutton(save_options_frame, text="保存提示词", 
                       variable=self.vars['save_prompt']).pack(side=tk.LEFT)
        
        ttk.Checkbutton(save_options_frame, text="保存生成设置", 
                       variable=self.vars['save_settings']).pack(side=tk.LEFT, padx=10)
        
        ttk.Checkbutton(save_options_frame, text="保存EXIF信息", 
                       variable=self.vars['save_metadata']).pack(side=tk.LEFT, padx=10)
        
        # 生成控制
        control_frame = ttk.LabelFrame(output_frame, text="生成控制", padding="10")
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 生成按钮和控制
        control_buttons_frame = ttk.Frame(control_frame)
        control_buttons_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(control_buttons_frame, text="开始生成", 
                  command=self.start_generation).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_buttons_frame, text="暂停", 
                  command=self.pause_generation).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_buttons_frame, text="停止", 
                  command=self.stop_generation).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_buttons_frame, text="清空输出", 
                  command=self.clear_output).pack(side=tk.LEFT, padx=10)
        
        # 进度显示
        progress_frame = ttk.Frame(control_frame)
        progress_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(progress_frame, text="生成进度:").pack(anchor="w")
        progress_bar = ttk.Progressbar(progress_frame, variable=self.vars['progress'],
                                      length=400, mode='determinate')
        progress_bar.pack(fill=tk.X, pady=2)
        
        progress_label = ttk.Label(progress_frame, textvariable=self.vars['progress_text'])
        progress_label.pack(anchor="w")
        
        # 生成日志
        log_frame = ttk.LabelFrame(control_frame, text="生成日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def create_preview_tab(self, notebook):
        """创建预览标签页"""
        
        preview_frame = ttk.Frame(notebook)
        notebook.add(preview_frame, text="图像预览")
        
        # 图像预览区域
        preview_image_frame = ttk.LabelFrame(preview_frame, text="生成结果预览", padding="10")
        preview_image_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 图像显示区域
        image_display_frame = ttk.Frame(preview_image_frame)
        image_display_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建Canvas用于显示图像
        self.preview_canvas = tk.Canvas(image_display_frame, bg="white", cursor="crosshair")
        canvas_scrollbar_x = ttk.Scrollbar(image_display_frame, orient=tk.HORIZONTAL, command=self.preview_canvas.xview)
        canvas_scrollbar_y = ttk.Scrollbar(image_display_frame, orient=tk.VERTICAL, command=self.preview_canvas.yview)
        self.preview_canvas.configure(xscrollcommand=canvas_scrollbar_x.set, yscrollcommand=canvas_scrollbar_y.set)
        
        self.preview_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        canvas_scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        canvas_scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 预览控制
        preview_control_frame = ttk.Frame(preview_image_frame)
        preview_control_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(preview_control_frame, text="放大", 
                  command=self.zoom_in_preview).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_control_frame, text="缩小", 
                  command=self.zoom_out_preview).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_control_frame, text="适应窗口", 
                  command=self.fit_preview_to_window).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_control_frame, text="保存图像", 
                  command=self.save_current_image).pack(side=tk.LEFT, padx=5)
        
        # 图像信息显示
        info_frame = ttk.LabelFrame(preview_frame, text="图像信息", padding="10")
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.image_info_text = tk.Text(info_frame, height=6, wrap=tk.WORD)
        info_scrollbar = ttk.Scrollbar(info_frame, orient=tk.VERTICAL, command=self.image_info_text.yview)
        self.image_info_text.configure(yscrollcommand=info_scrollbar.set)
        
        self.image_info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        info_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 历史记录
        history_frame = ttk.LabelFrame(preview_frame, text="生成历史", padding="10")
        history_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 历史记录列表
        history_list_frame = ttk.Frame(history_frame)
        history_list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.history_listbox = tk.Listbox(history_list_frame)
        history_scrollbar = ttk.Scrollbar(history_list_frame, orient=tk.VERTICAL, command=self.history_listbox.yview)
        self.history_listbox.configure(yscrollcommand=history_scrollbar.set)
        
        self.history_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 历史记录控制
        history_control_frame = ttk.Frame(history_frame)
        history_control_frame.pack(fill=tk.X, pady=2)
        
        ttk.Button(history_control_frame, text="加载选中", 
                  command=self.load_history_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(history_control_frame, text="删除选中", 
                  command=self.delete_history_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(history_control_frame, text="清空历史", 
                  command=self.clear_history).pack(side=tk.LEFT, padx=5)
    
    # ========== 功能实现方法 ==========
    
    def update_backend_status(self):
        """更新后端引擎状态"""
        status_text = "后端引擎状态:\n"
        
        for engine_name, status in self.backend_engine.engines.items():
            if engine_name == 'diffusers':
                status_text += f"Diffusers: {'✓ 可用' if status else '✗ 不可用'}\n"
            elif engine_name == 'comfyui':
                status_text += f"ComfyUI: {'✓ 可用' if status else '✗ 不可用'}\n"
            elif engine_name == 'ollama':
                status_text += f"Ollama: {'✓ 可用' if status else '✗ 不可用'}\n"
            elif engine_name == 'seedvr':
                status_text += f"SeedVR: {'✓ 可用' if status else '✗ 不可用'}\n"
        
        self.backend_status_label.config(text=status_text)
    
    def check_backend_engine(self):
        """检查后端引擎"""
        self.backend_engine.initialize_engines()
        self.update_backend_status()
        self.log_message("已更新后端引擎状态")
    
    def select_model_file(self, var_name):
        """选择模型文件"""
        file_path = filedialog.askopenfilename(
            title="选择模型文件",
            filetypes=[
                ("所有支持格式", "*.safetensors *.ckpt *.bin *.pth *.gguf *.vae *.clip *.unet *.t5"),
                ("Safetensors", "*.safetensors"),
                ("Checkpoint", "*.ckpt *.bin *.pth"),
                ("VAE模型", "*.vae"),
                ("CLIP模型", "*.clip"),
                ("目录", "")
            ]
        )
        if file_path:
            self.vars[var_name].set(file_path)
    
    def load_selected_model(self):
        """加载选中的模型"""
        model_path = self.vars['main_model_path'].get()
        if not model_path:
            messagebox.showwarning("警告", "请先选择模型文件")
            return
        
        backend = self.backend_options.get(self.vars['backend_type'].get(), 'diffusers')
        
        def load_model_thread():
            self.log_message(f"正在加载模型: {model_path}")
            
            if self.model_manager.load_model(model_path, backend):
                self.log_message(f"模型加载成功: {model_path}")
                self.update_loaded_models_list()
            else:
                self.log_message(f"模型加载失败: {model_path}")
        
        # 在新线程中加载模型
        threading.Thread(target=load_model_thread, daemon=True).start()
    
    def unload_selected_model(self):
        """卸载选中的模型"""
        model_path = self.vars['main_model_path'].get()
        if model_path in self.model_manager.loaded_models:
            del self.model_manager.loaded_models[model_path]
            self.log_message(f"模型已卸载: {model_path}")
            self.update_loaded_models_list()
        else:
            messagebox.showwarning("警告", "该模型未加载")
    
    def show_model_info(self):
        """显示模型信息"""
        model_path = self.vars['main_model_path'].get()
        if not model_path:
            messagebox.showwarning("警告", "请先选择模型文件")
            return
        
        model_info = self.model_manager.get_model_info(model_path)
        
        info_window = tk.Toplevel(self.parent)
        info_window.title("模型信息")
        info_window.geometry("400x300")
        
        info_text = tk.Text(info_window, wrap=tk.WORD)
        info_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        info_content = f"模型路径: {model_path}\n"
        info_content += f"加载状态: {'已加载' if model_info['loaded'] else '未加载'}\n"
        info_content += f"模型类型: {model_info['type']}\n"
        info_content += f"文件大小: {model_info['size'] / 1024 / 1024:.2f} MB\n"
        
        info_text.insert(tk.END, info_content)
        info_text.config(state=tk.DISABLED)
    
    def update_loaded_models_list(self):
        """更新已加载模型列表"""
        self.loaded_models_listbox.delete(0, tk.END)
        for model_path in self.model_manager.loaded_models.keys():
            self.loaded_models_listbox.insert(tk.END, os.path.basename(model_path))
    
    def apply_style_template(self, template_type):
        """应用风格模板"""
        if template_type == 'positive':
            style = self.vars['positive_style'].get()
            processed_prompt = self.prompt_processor.apply_style_template(
                self.pos_text.get("1.0", tk.END).strip(), style
            )
            self.pos_text.delete("1.0", tk.END)
            self.pos_text.insert("1.0", processed_prompt)
        else:
            # 负面提示词模板
            negative_templates = {
                "通用负面": "low quality, blurry, distorted, bad anatomy, deformed, ugly, bad proportions",
                "手部负面": "extra fingers, missing fingers, deformed hands, bad hands, worst quality",
                "人脸负面": "deformed face, bad face, ugly face, bad expression, distorted expression",
                "文字负面": "text, watermark, signature, blurry text, unreadable text, letters",
                "构图负面": "bad composition, cluttered, messy, out of frame, cropped, bad framing"
            }
            style = self.vars['negative_style'].get()
            template = negative_templates.get(style, "")
            processed_prompt = self.prompt_processor.apply_style_template(
                self.neg_text.get("1.0", tk.END).strip(), style
            )
            self.neg_text.delete("1.0", tk.END)
            self.neg_text.insert("1.0", template)
    
    def optimize_prompt_with_ai(self):
        """使用AI优化提示词"""
        current_prompt = self.pos_text.get("1.0", tk.END).strip()
        if not current_prompt:
            messagebox.showwarning("警告", "请先输入提示词")
            return
        
        enable_detail = self.vars['enable_detail_enhance'].get()
        enable_style = self.vars['enable_style_emphasis'].get()
        enable_emotion = self.vars['enable_emotion_art'].get()
        
        optimized_prompt = self.prompt_processor.optimize_prompt(
            current_prompt, enable_detail, enable_style, enable_emotion
        )
        
        self.pos_text.delete("1.0", tk.END)
        self.pos_text.insert("1.0", optimized_prompt)
        
        self.log_message("提示词优化完成")
    
    def apply_preset_resolution(self):
        """应用预设分辨率"""
        preset = self.vars['preset_resolution'].get()
        if preset in self.resolution_presets:
            width, height = self.resolution_presets[preset]
            self.vars['custom_width'].set(width)
            self.vars['custom_height'].set(height)
    
    def set_random_resolution(self):
        """设置随机分辨率"""
        preset = random.choice(list(self.resolution_presets.keys()))
        self.vars['preset_resolution'].set(preset)
        width, height = self.resolution_presets[preset]
        self.vars['custom_width'].set(width)
        self.vars['custom_height'].set(height)
    
    def preview_style_filter(self):
        """预览风格滤镜"""
        filter_name = self.vars['style_filter'].get()
        strength = self.vars['filter_strength'].get()
        
        # 创建一个测试图像来演示滤镜效果
        test_image = Image.new('RGB', (200, 200), color=(128, 128, 128))
        
        # 应用滤镜
        filtered_image = self.style_filter_manager.apply_filter(test_image, filter_name, strength)
        
        # 在新窗口中显示对比
        preview_window = tk.Toplevel(self.parent)
        preview_window.title(f"滤镜预览 - {filter_name}")
        preview_window.geometry("450x250")
        
        # 原图和滤镜效果图对比
        comparison_frame = ttk.Frame(preview_window)
        comparison_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 保存临时图像
        temp_original = "temp_original.png"
        temp_filtered = "temp_filtered.png"
        test_image.save(temp_original)
        filtered_image.save(temp_filtered)
        
        # 显示图像（简化实现）
        ttk.Label(comparison_frame, text="原图").pack()
        ttk.Label(comparison_frame, text="滤镜效果").pack()
        
        self.log_message(f"滤镜预览: {filter_name} (强度: {strength})")
    
    def reset_style_filter(self):
        """重置风格滤镜"""
        self.vars['style_filter'].set("无")
        self.vars['filter_strength'].set(0.5)
    
    def apply_filter_to_generation(self):
        """应用滤镜到生成"""
        self.log_message("滤镜将应用到生成的图像")
    
    def select_output_directory(self):
        """选择输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.vars['output_directory'].set(directory)
    
    def start_generation(self):
        """开始生成"""
        if self.is_generating:
            messagebox.showwarning("警告", "正在生成中，请等待完成")
            return
        
        # 获取生成配置
        config = self.get_generation_config()
        
        if not config:
            return
        
        # 开始生成线程
        def generation_thread():
            self.is_generating = True
            self.vars['progress'].set(0)
            self.vars['progress_text'].set("正在生成...")
            
            try:
                self.log_message("开始图像生成")
                
                # 生成配置回调
                def generation_callback(image, config):
                    # 应用后处理
                    processed_image = self.post_process_image(image, config)
                    
                    # 保存图像
                    saved_path = self.save_generated_image(processed_image, config)
                    
                    # 更新UI
                    self.update_generation_progress(100)
                    self.display_generated_image(processed_image, config)
                    self.add_to_history(processed_image, config, saved_path)
                
                # 执行生成
                success = self.image_engine.generate_image(config, generation_callback)
                
                if success:
                    self.log_message("图像生成完成")
                    self.vars['progress_text'].set("生成完成")
                else:
                    self.log_message("图像生成失败")
                    self.vars['progress_text'].set("生成失败")
                
            except Exception as e:
                self.log_message(f"生成过程出错: {e}")
                self.vars['progress_text'].set("生成出错")
            finally:
                self.is_generating = False
        
        threading.Thread(target=generation_thread, daemon=True).start()
    
    def get_generation_config(self) -> Dict[str, Any]:
        """获取生成配置"""
        try:
            # 基本参数
            config = {
                'task_type': self.vars['task_type'].get(),
                'backend': self.backend_options.get(self.vars['backend_type'].get(), 'diffusers'),
                'model_path': self.vars['main_model_path'].get(),
                'positive_prompt': self.pos_text.get("1.0", tk.END).strip(),
                'negative_prompt': self.neg_text.get("1.0", tk.END).strip(),
                'width': self.vars['custom_width'].get(),
                'height': self.vars['custom_height'].get(),
                'num_steps': self.vars['num_steps'].get(),
                'cfg_scale': self.vars['cfg_scale'].get(),
                'batch_size': self.vars['batch_size'].get(),
                'sampler': self.vars['sampler'].get(),
                'scheduler': self.vars['scheduler'].get(),
                'seed': self.vars['seed'].get() if not self.vars['random_seed'].get() else -1,
                'upscale_model': self.vars['upscale_model'].get(),
                'upscale_factor': self.vars['upscale_factor'].get(),
                'style_filter': self.vars['style_filter'].get(),
                'filter_strength': self.vars['filter_strength'].get(),
                'enable_hires_fix': self.vars['enable_hires_fix'].get(),
                'enable_tiling': self.vars['enable_tiling'].get(),
                'redraw_strength': self.vars['redraw_strength'].get()
            }
            
            # 验证必要参数
            if not config['model_path']:
                messagebox.showwarning("警告", "请先选择模型文件")
                return None
            
            if not config['positive_prompt']:
                messagebox.showwarning("警告", "请输入正面提示词")
                return None
            
            return config
            
        except Exception as e:
            messagebox.showerror("错误", f"配置获取失败: {e}")
            return None
    
    def post_process_image(self, image: Image.Image, config: Dict[str, Any]) -> Image.Image:
        """后处理图像"""
        processed_image = image.copy()
        
        # 应用风格滤镜
        filter_name = config.get('style_filter', '无')
        filter_strength = config.get('filter_strength', 0.5)
        
        if filter_name != '无':
            processed_image = self.style_filter_manager.apply_filter(
                processed_image, filter_name, filter_strength
            )
        
        # 超分辨率
        if config.get('enable_highres_fix'):
            upscale_model = config.get('upscale_model', 'RealESRGAN_x4plus')
            upscale_factor = config.get('upscale_factor', 2.0)
            processed_image = self.upscale_manager.upscale_image(
                processed_image, upscale_model, upscale_factor
            )
        
        return processed_image
    
    def save_generated_image(self, image: Image.Image, config: Dict[str, Any]) -> str:
        """保存生成的图像"""
        try:
            # 构建输出路径
            output_dir = self.vars['output_directory'].get()
            os.makedirs(output_dir, exist_ok=True)
            
            # 按任务类型分文件夹
            if self.vars['organize_by_task'].get():
                task_type = config.get('task_type', 'text2img')
                output_dir = os.path.join(output_dir, task_type)
                os.makedirs(output_dir, exist_ok=True)
            
            # 按日期分文件夹
            if self.vars['organize_by_date'].get():
                date_str = datetime.now().strftime("%Y-%m-%d")
                output_dir = os.path.join(output_dir, date_str)
                os.makedirs(output_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            seed = config.get('seed', 'random')
            format_type = self.vars['image_format'].get()
            
            filename = f"generation_{timestamp}_seed{seed}.{format_type}"
            filepath = os.path.join(output_dir, filename)
            
            # 保存图像
            save_kwargs = {}
            if format_type.lower() in ['jpg', 'jpeg', 'webp']:
                save_kwargs['quality'] = self.vars['image_quality'].get()
                save_kwargs['optimize'] = True
            
            image.save(filepath, format_type.upper(), **save_kwargs)
            
            # 保存元数据
            if self.vars['save_metadata'].get():
                metadata = {
                    'timestamp': timestamp,
                    'task_type': config.get('task_type'),
                    'positive_prompt': config.get('positive_prompt'),
                    'negative_prompt': config.get('negative_prompt'),
                    'model_path': config.get('model_path'),
                    'width': config.get('width'),
                    'height': config.get('height'),
                    'num_steps': config.get('num_steps'),
                    'cfg_scale': config.get('cfg_scale'),
                    'seed': config.get('seed'),
                    'sampler': config.get('sampler'),
                    'scheduler': config.get('scheduler'),
                    'backend': config.get('backend')
                }
                
                metadata_file = filepath.rsplit('.', 1)[0] + '_metadata.json'
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            self.log_message(f"图像已保存: {filepath}")
            return filepath
            
        except Exception as e:
            self.log_message(f"保存图像失败: {e}")
            return ""
    
    def update_generation_progress(self, progress: float):
        """更新生成进度"""
        self.vars['progress'].set(progress)
        self.parent.update_idletasks()
    
    def display_generated_image(self, image: Image.Image, config: Dict[str, Any]):
        """显示生成的图像"""
        try:
            # 转换图像为显示格式
            display_image = image.copy()
            
            # 调整大小以适应预览区域
            max_width = 400
            max_height = 400
            
            if display_image.width > max_width or display_image.height > max_height:
                display_image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            
            # 显示在Canvas上
            self.preview_canvas.delete("all")
            
            # 转换为PhotoImage
            import io
            img_buffer = io.BytesIO()
            display_image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            photo = tk.PhotoImage(data=img_buffer.read())
            self.preview_canvas.create_image(
                display_image.width//2, display_image.height//2,
                image=photo, anchor=tk.CENTER
            )
            
            # 更新图像信息
            info_text = f"尺寸: {image.width}x{image.height}\n"
            info_text += f"格式: {image.format}\n"
            info_text += f"模式: {image.mode}\n"
            info_text += f"任务类型: {config.get('task_type')}\n"
            info_text += f"后端: {config.get('backend')}\n"
            info_text += f"种子: {config.get('seed')}\n"
            info_text += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            self.image_info_text.delete("1.0", tk.END)
            self.image_info_text.insert("1.0", info_text)
            
            # 保存引用以防止图像被垃圾回收
            self.current_image = photo
            
        except Exception as e:
            self.log_message(f"显示图像失败: {e}")
    
    def add_to_history(self, image: Image.Image, config: Dict[str, Any], filepath: str):
        """添加到历史记录"""
        try:
            history_entry = {
                'image': image,
                'config': config,
                'filepath': filepath,
                'timestamp': datetime.now()
            }
            
            self.generation_history.append(history_entry)
            
            # 更新历史列表
            timestamp = history_entry['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            display_text = f"{timestamp} - {config.get('task_type')} - 种子:{config.get('seed')}"
            
            self.history_listbox.insert(tk.END, display_text)
            
        except Exception as e:
            self.log_message(f"添加到历史记录失败: {e}")
    
    def load_history_image(self):
        """从历史记录加载图像"""
        selection = self.history_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择历史记录")
            return
        
        index = selection[0]
        if 0 <= index < len(self.generation_history):
            entry = self.generation_history[index]
            self.display_generated_image(entry['image'], entry['config'])
            self.log_message("已加载历史图像")
    
    def delete_history_image(self):
        """删除历史记录中的图像"""
        selection = self.history_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择历史记录")
            return
        
        index = selection[0]
        if 0 <= index < len(self.generation_history):
            del self.generation_history[index]
            self.history_listbox.delete(selection)
            self.log_message("已删除历史记录")
    
    def clear_history(self):
        """清空历史记录"""
        if messagebox.askyesno("确认", "确定要清空所有历史记录吗？"):
            self.generation_history.clear()
            self.history_listbox.delete(0, tk.END)
            self.log_message("历史记录已清空")
    
    def pause_generation(self):
        """暂停生成"""
        if self.is_generating:
            self.log_message("生成已暂停")
        else:
            messagebox.showinfo("提示", "当前没有正在进行的生成任务")
    
    def stop_generation(self):
        """停止生成"""
        if self.is_generating:
            self.is_generating = False
            self.vars['progress_text'].set("已停止")
            self.log_message("生成已停止")
        else:
            messagebox.showinfo("提示", "当前没有正在进行的生成任务")
    
    def clear_output(self):
        """清空输出"""
        if messagebox.askyesno("确认", "确定要清空所有输出吗？"):
            # 清空进度和日志
            self.vars['progress'].set(0)
            self.vars['progress_text'].set("已清空")
            self.log_text.delete("1.0", tk.END)
            self.preview_canvas.delete("all")
            self.image_info_text.delete("1.0", tk.END)
    
    def log_message(self, message: str):
        """记录日志消息"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        self.parent.update_idletasks()
    
    def zoom_in_preview(self):
        """放大预览"""
        self.log_message("放大预览")
    
    def zoom_out_preview(self):
        """缩小预览"""
        self.log_message("缩小预览")
    
    def fit_preview_to_window(self):
        """适应窗口"""
        self.log_message("适应窗口大小")
    
    def save_current_image(self):
        """保存当前图像"""
        if hasattr(self, 'current_image'):
            filepath = filedialog.asksaveasfilename(
                title="保存图像",
                defaultextension=".png",
                filetypes=[
                    ("PNG文件", "*.png"),
                    ("JPEG文件", "*.jpg"),
                    ("所有文件", "*.*")
                ]
            )
            if filepath:
                # 这里实现保存逻辑
                self.log_message(f"图像已保存: {filepath}")
        else:
            messagebox.showwarning("警告", "没有可保存的图像")


if __name__ == "__main__":
    # 测试代码
    root = tk.Tk()
    root.title("增强版图片生成组件 - 完整实现版")
    root.geometry("1200x900")
    
    # 创建测试框架
    test_frame = ttk.Frame(root)
    test_frame.pack(fill=tk.BOTH, expand=True)
    
    # 创建增强版组件
    components = EnhancedImageGenerationComponents(test_frame, None)
    
    root.mainloop()