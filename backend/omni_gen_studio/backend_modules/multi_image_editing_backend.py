#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OmniGen Studio - 多图片编辑后端模块
支持批量图生图、局部重绘、一致性编辑、背景替换、风格迁移等功能

作者：MiniMax Agent
版本：v1.0
"""

import os
import sys
import torch
import logging
import asyncio
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Union
from PIL import Image
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import gc

logger = logging.getLogger(__name__)


class ProgressCallback:
    """进度回调基类"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._current = 0
        self._total = 0
        self._message = ""
    
    def update(self, current: int, total: int, message: str = ""):
        """更新进度"""
        with self._lock:
            self._current = current
            self._total = total
            self._message = message
    
    @property
    def progress(self) -> float:
        """获取进度百分比"""
        if self._total == 0:
            return 0.0
        return (self._current / self._total) * 100
    
    @property
    def status(self) -> Dict[str, Any]:
        """获取状态信息"""
        return {
            "current": self._current,
            "total": self._total,
            "progress": self.progress,
            "message": self._message
        }


class MultiImageEditor:
    """
    多图片编辑核心类
    
    支持功能:
    - 批量图生图 (batch_img2img)
    - 批量局部重绘 (batch_inpaint)
    - 一致性编辑 (consistent_edit)
    - 背景替换 (background_replace)
    - 批量风格迁移 (batch_style_transfer)
    """
    
    def __init__(
        self,
        device: str = "auto",
        output_dir: str = "outputs/multi_edit",
        max_parallel: int = 2,
        enable_xformers: bool = True,
        enable_flash_attention: bool = False
    ):
        """
        初始化多图片编辑器
        
        Args:
            device: 运行设备 ("auto", "cuda", "cpu", "mps")
            output_dir: 输出目录
            max_parallel: 最大并行处理数
            enable_xformers: 启用xFormers加速
            enable_flash_attention: 启用FlashAttention加速
        """
        self.device = self._get_device(device)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_parallel = max(1, min(max_parallel, 4))
        self.enable_xformers = enable_xformers
        self.enable_flash_attention = enable_flash_attention
        
        # 模型缓存
        self._pipelines: Dict[str, Any] = {}
        self._models_loaded = False
        
        # 线程池用于批量处理
        self._executor: Optional[ThreadPoolExecutor] = None
        
        # 错误恢复相关
        self._retry_config = {
            "max_retries": 3,
            "retry_delay": 2.0,
            "backoff_factor": 2.0
        }
        
        # 内存管理
        self._memory_threshold_gb = 8  # 当GPU显存小于此值时触发清理
        
        logger.info(f"🎨 多图片编辑器初始化完成")
        logger.info(f"   设备: {self.device}")
        logger.info(f"   最大并行数: {self.max_parallel}")
        logger.info(f"   输出目录: {self.output_dir}")
    
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
    
    def _check_memory(self) -> bool:
        """检查显存是否充足"""
        if self.device == "cuda" and torch.cuda.is_available():
            free_memory_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            if free_memory_gb < self._memory_threshold_gb:
                logger.warning(f"⚠️ GPU显存不足 ({free_memory_gb:.1f}GB)，清理显存...")
                self._clear_memory()
                return False
        return True
    
    def _clear_memory(self):
        """清理显存"""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        gc.collect()
        logger.info("🧹 显存已清理")
    
    def _load_dependencies(self) -> bool:
        """加载依赖库"""
        try:
            from diffusers import (
                StableDiffusionImg2ImgPipeline,
                StableDiffusionInpaintPipeline,
                AutoPipelineForImage2Image,
                AutoPipelineForInpainting
            )
            self.diffusers_available = True
        except ImportError as e:
            logger.warning(f"⚠️ diffusers库不可用: {e}")
            self.diffusers_available = False
        
        try:
            import cv2
            self.cv2_available = True
        except ImportError:
            self.cv2_available = False
        
        try:
            from PIL import Image, ImageFilter, ImageEnhance
            self.pil_available = True
        except ImportError:
            self.pil_available = False
        
        return self.diffusers_available or self.pil_available
    
    def load_models(
        self,
        model_name: str = "sd15_img2img",
        model_path: Optional[str] = None
    ) -> bool:
        """
        加载编辑模型
        
        Args:
            model_name: 模型名称 ("sd15_img2img", "sd15_inpaint", "sdxl")
            model_path: 模型路径
            
        Returns:
            是否加载成功
        """
        try:
            if not self._load_dependencies():
                logger.warning("⚠️ 依赖库加载失败，使用基础模式")
                return False
            
            if model_name in self._pipelines:
                logger.info(f"✅ 模型已加载: {model_name}")
                return True
            
            logger.info(f"📥 加载模型: {model_name}")
            
            from diffusers import (
                StableDiffusionImg2ImgPipeline,
                StableDiffusionInpaintPipeline,
                StableDiffusionXLPipeline
            )
            
            dtype = torch.float16 if self.device == "cuda" else torch.float32
            
            if model_name == "sd15_img2img":
                path = model_path or "runwayml/stable-diffusion-v1-5"
                pipeline = StableDiffusionImg2ImgPipeline.from_pretrained(
                    path,
                    torch_dtype=dtype,
                    safety_checker=None,
                    requires_safety_checker=False
                )
                
            elif model_name == "sd15_inpaint":
                path = model_path or "runwayml/stable-diffusion-inpainting"
                pipeline = StableDiffusionInpaintPipeline.from_pretrained(
                    path,
                    torch_dtype=dtype,
                    safety_checker=None,
                    requires_safety_checker=False
                )
                
            elif model_name == "sdxl":
                path = model_path or "stabilityai/stable-diffusion-xl-base-1.0"
                pipeline = StableDiffusionXLPipeline.from_pretrained(
                    path,
                    torch_dtype=dtype,
                    safety_checker=None,
                    requires_safety_checker=False
                )
                # SDXL使用图生图管线
                from diffusers import AutoPipelineForImage2Image
                pipeline = AutoPipelineForImage2Image.from_pipe(pipeline)
            
            else:
                # 默认使用SD1.5图生图
                pipeline = StableDiffusionImg2ImgPipeline.from_pretrained(
                    "runwayml/stable-diffusion-v1-5",
                    torch_dtype=dtype,
                    safety_checker=None,
                    requires_safety_checker=False
                )
            
            # 应用加速优化
            if self.enable_flash_attention and self.device == "cuda":
                try:
                    pipeline.enable_flash_attention()
                    logger.info("✅ FlashAttention已启用")
                except:
                    pass
            
            if self.enable_xformers:
                try:
                    pipeline.enable_xformers_memory_efficient_attention()
                    logger.info("✅ xFormers已启用")
                except:
                    pass
            
            # 移动到设备
            pipeline.to(self.device)
            
            self._pipelines[model_name] = pipeline
            self._models_loaded = True
            
            logger.info(f"✅ 模型加载成功: {model_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 模型加载失败: {e}")
            self._models_loaded = False
            return False
    
    def _get_pipeline(self, model_name: str) -> Optional[Any]:
        """获取或加载管线"""
        if model_name not in self._pipelines:
            self.load_models(model_name)
        return self._pipelines.get(model_name)
    
    def batch_img2img(
        self,
        input_images: List[Image.Image],
        prompt: str,
        negative_prompt: str = "",
        # 基础参数
        strength: float = 0.75,
        steps: int = 28,
        cfg_scale: float = 7.5,
        seed: int = -1,
        # 批量参数
        batch_size: int = 1,
        max_parallel: Optional[int] = None,
        # 模型参数
        model_name: str = "sd15_img2img",
        # 输出参数
        save_images: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        output_prefix: str = "batch_img2img"
    ) -> Dict[str, Any]:
        """
        批量图生图处理
        
        Args:
            input_images: 输入图像列表
            prompt: 生成提示词
            negative_prompt: 负面提示词
            strength: 重构强度 (0.0-1.0)
            steps: 推理步数
            cfg_scale: CFG缩放因子
            seed: 随机种子 (-1表示随机)
            batch_size: 每批处理数量
            max_parallel: 最大并行数 (None使用默认值)
            model_name: 使用的模型名称
            save_images: 是否保存图像
            progress_callback: 进度回调函数
            output_prefix: 输出文件前缀
            
        Returns:
            处理结果字典
        """
        start_time = time.time()
        processed_count = 0
        failed_count = 0
        output_images: List[Image.Image] = []
        output_paths: List[str] = []
        seeds: List[int] = []
        errors: List[Dict[str, Any]] = []
        
        if not input_images:
            return {
                "success": False,
                "images": [],
                "output_paths": [],
                "seeds": [],
                "generation_time": 0.0,
                "processed_count": 0,
                "failed_count": 0,
                "error": "No input images provided"
            }
        
        # 确保模型已加载
        pipeline = self._get_pipeline(model_name)
        if pipeline is None:
            # 使用基础模式
            logger.warning("⚠️ 模型加载失败，使用基础图像处理模式")
            return self._batch_img2img_fallback(
                input_images, prompt, strength, output_prefix, progress_callback
            )
        
        parallel_count = max_parallel or self.max_parallel
        total_count = len(input_images)
        
        logger.info(f"🔄 开始批量图生图处理，共 {total_count} 张图像")
        logger.info(f"   并行数: {parallel_count}, 批次大小: {batch_size}")
        
        # 生成种子列表
        if seed >= 0:
            base_seed = seed
            seed_list = [(base_seed + i) % (2**32 - 1) for i in range(total_count)]
        else:
            seed_list = [np.random.randint(0, 2**32 - 1) for _ in range(total_count)]
        
        # 创建进度回调
        progress = ProgressCallback()
        progress.update(0, total_count, "开始处理...")
        
        def process_single(
            idx: int, 
            input_image: Image.Image, 
            current_seed: int
        ) -> Dict[str, Any]:
            """处理单张图像"""
            try:
                # 检查显存
                self._check_memory()
                
                # 预处理图像
                if input_image.mode != 'RGB':
                    input_image = input_image.convert('RGB')
                
                # 设置种子
                generator = torch.Generator(device=self.device).manual_seed(current_seed)
                
                # 执行推理
                with torch.autocast(self.device):
                    result = pipeline(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        image=input_image,
                        strength=strength,
                        num_inference_steps=steps,
                        guidance_scale=cfg_scale,
                        generator=generator,
                        num_images_per_prompt=1
                    )
                
                if result.images and len(result.images) > 0:
                    output_image = result.images[0]
                    
                    # 保存图像
                    output_path = None
                    if save_images:
                        filename = f"{output_prefix}_{idx:04d}_{current_seed}.png"
                        filepath = self.output_dir / filename
                        output_image.save(filepath, "PNG")
                        output_path = str(filepath)
                    
                    return {
                        "success": True,
                        "image": output_image,
                        "output_path": output_path,
                        "seed": current_seed,
                        "error": None
                    }
                else:
                    return {
                        "success": False,
                        "image": None,
                        "output_path": None,
                        "seed": current_seed,
                        "error": "No output image generated"
                    }
                    
            except Exception as e:
                logger.error(f"❌ 处理图像 {idx} 失败: {e}")
                return {
                    "success": False,
                    "image": None,
                    "output_path": None,
                    "seed": current_seed,
                    "error": str(e)
                }
        
        # 分批处理
        try:
            with ThreadPoolExecutor(max_workers=parallel_count) as executor:
                futures = []
                
                for idx, (input_image, current_seed) in enumerate(zip(input_images, seed_list)):
                    future = executor.submit(process_single, idx, input_image, current_seed)
                    futures.append((idx, future))
                
                # 收集结果
                results_dict: Dict[int, Dict[str, Any]] = {}
                for idx, future in futures:
                    result = future.result()
                    results_dict[idx] = result
                    
                    processed_count += 1
                    progress.update(processed_count, total_count, f"处理中 {processed_count}/{total_count}")
                    
                    if progress_callback:
                        progress_callback(progress.status)
                    
                    # 定期清理显存
                    if processed_count % batch_size == 0:
                        self._clear_memory()
                
                # 整理结果
                for idx in sorted(results_dict.keys()):
                    result = results_dict[idx]
                    if result["success"]:
                        output_images.append(result["image"])
                        output_paths.append(result["output_path"])
                        seeds.append(result["seed"])
                    else:
                        failed_count += 1
                        errors.append({
                            "index": idx,
                            "seed": result["seed"],
                            "error": result["error"]
                        })
        
        except Exception as e:
            logger.error(f"❌ 批量处理失败: {e}")
            errors.append({"stage": "batch_processing", "error": str(e)})
        
        generation_time = time.time() - start_time
        
        result = {
            "success": failed_count == 0,
            "images": output_images,
            "output_paths": output_paths,
            "seeds": seeds,
            "generation_time": generation_time,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "total_count": total_count,
            "errors": errors if errors else None,
            "metadata": {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "strength": strength,
                "steps": steps,
                "cfg_scale": cfg_scale,
                "batch_size": batch_size,
                "max_parallel": parallel_count,
                "model_name": model_name,
                "device": self.device
            }
        }
        
        logger.info(f"✅ 批量图生图完成: 成功 {processed_count - failed_count}, 失败 {failed_count}")
        logger.info(f"   耗时: {generation_time:.2f}秒")
        
        return result
    
    def _batch_img2img_fallback(
        self,
        input_images: List[Image.Image],
        prompt: str,
        strength: float,
        output_prefix: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """基础模式的批量图生图（无模型）"""
        start_time = time.time()
        output_images = []
        output_paths = []
        seeds = []
        
        for idx, img in enumerate(input_images):
            # 应用基础滤镜
            from PIL import ImageFilter, ImageEnhance
            enhanced = img.filter(ImageFilter.EDGE_ENHANCE_MORE)
            
            # 根据prompt调整
            prompt_lower = prompt.lower()
            if "bright" in prompt_lower or "light" in prompt_lower:
                enhanced = ImageEnhance.Brightness(enhanced).enhance(1.3)
            elif "dark" in prompt_lower:
                enhanced = ImageEnhance.Brightness(enhanced).enhance(0.7)
            elif "vibrant" in prompt_lower or "colorful" in prompt_lower:
                enhanced = ImageEnhance.Color(enhanced).enhance(1.4)
            
            # 保存
            filename = f"{output_prefix}_{idx:04d}_fallback.png"
            filepath = self.output_dir / filename
            enhanced.save(filepath, "PNG")
            
            output_images.append(enhanced)
            output_paths.append(str(filepath))
            seeds.append(-1)
            
            if progress_callback:
                progress_callback({"current": idx + 1, "total": len(input_images)})
        
        return {
            "success": True,
            "images": output_images,
            "output_paths": output_paths,
            "seeds": seeds,
            "generation_time": time.time() - start_time,
            "processed_count": len(input_images),
            "failed_count": 0,
            "metadata": {"mode": "fallback", "prompt": prompt}
        }
    
    def batch_inpaint(
        self,
        input_images: List[Image.Image],
        mask_images: List[Image.Image],
        prompt: str,
        negative_prompt: str = "",
        strength: float = 0.8,
        steps: int = 25,
        cfg_scale: float = 7.5,
        seed: int = -1,
        batch_size: int = 1,
        max_parallel: Optional[int] = None,
        model_name: str = "sd15_inpaint",
        save_images: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        output_prefix: str = "batch_inpaint"
    ) -> Dict[str, Any]:
        """
        批量局部重绘处理
        
        Args:
            input_images: 输入图像列表
            mask_images: 蒙版图像列表
            prompt: 生成提示词
            negative_prompt: 负面提示词
            strength: 重构强度
            steps: 推理步数
            cfg_scale: CFG缩放因子
            seed: 随机种子
            batch_size: 每批处理数量
            max_parallel: 最大并行数
            model_name: 模型名称
            save_images: 是否保存图像
            progress_callback: 进度回调
            output_prefix: 输出前缀
            
        Returns:
            处理结果字典
        """
        start_time = time.time()
        
        if len(input_images) != len(mask_images):
            return {
                "success": False,
                "error": f"Input images count ({len(input_images)}) != mask images count ({len(mask_images)})"
            }
        
        if not input_images:
            return {
                "success": False,
                "error": "No input images provided"
            }
        
        pipeline = self._get_pipeline(model_name)
        if pipeline is None:
            logger.warning("⚠️ 蒙版模型不可用，使用基础蒙版混合模式")
            return self._batch_inpaint_fallback(
                input_images, mask_images, output_prefix, progress_callback
            )
        
        parallel_count = max_parallel or self.max_parallel
        total_count = len(input_images)
        
        logger.info(f"🔄 开始批量局部重绘，共 {total_count} 张")
        
        if seed >= 0:
            seed_list = [(seed + i) % (2**32 - 1) for i in range(total_count)]
        else:
            seed_list = [np.random.randint(0, 2**32 - 1) for _ in range(total_count)]
        
        output_images = []
        output_paths = []
        seeds = []
        failed_count = 0
        errors = []
        
        progress = ProgressCallback()
        progress.update(0, total_count, "开始局部重绘...")
        
        def process_single(idx, input_image, mask_image, current_seed):
            try:
                self._check_memory()
                
                if input_image.mode != 'RGB':
                    input_image = input_image.convert('RGB')
                if mask_image.mode != 'RGB':
                    mask_image = mask_image.convert('RGB')
                
                generator = torch.Generator(device=self.device).manual_seed(current_seed)
                
                with torch.autocast(self.device):
                    result = pipeline(
                        prompt=prompt,
                        negative_prompt=negative_prompt,
                        image=input_image,
                        mask_image=mask_image,
                        strength=strength,
                        num_inference_steps=steps,
                        guidance_scale=cfg_scale,
                        generator=generator
                    )
                
                if result.images:
                    output_image = result.images[0]
                    output_path = None
                    if save_images:
                        filename = f"{output_prefix}_{idx:04d}_{current_seed}.png"
                        filepath = self.output_dir / filename
                        output_image.save(filepath, "PNG")
                        output_path = str(filepath)
                    
                    return {
                        "success": True,
                        "image": output_image,
                        "output_path": output_path,
                        "seed": current_seed
                    }
                return {"success": False, "seed": current_seed, "error": "No output"}
                
            except Exception as e:
                return {"success": False, "seed": current_seed, "error": str(e)}
        
        try:
            with ThreadPoolExecutor(max_workers=parallel_count) as executor:
                futures = []
                for idx, (img, mask, seed_val) in enumerate(zip(input_images, mask_images, seed_list)):
                    future = executor.submit(process_single, idx, img, mask, seed_val)
                    futures.append((idx, future))
                
                for idx, future in futures:
                    result = future.result()
                    progress.update(idx + 1, total_count)
                    
                    if result["success"]:
                        output_images.append(result["image"])
                        output_paths.append(result["output_path"])
                        seeds.append(result["seed"])
                    else:
                        failed_count += 1
                        errors.append({"index": idx, "error": result.get("error")})
                    
                    if progress_callback:
                        progress_callback(progress.status)
        
        except Exception as e:
            logger.error(f"❌ 批量重绘失败: {e}")
            errors.append({"error": str(e)})
        
        return {
            "success": failed_count == 0,
            "images": output_images,
            "output_paths": output_paths,
            "seeds": seeds,
            "generation_time": time.time() - start_time,
            "processed_count": len(output_images),
            "failed_count": failed_count,
            "metadata": {
                "prompt": prompt,
                "strength": strength,
                "steps": steps,
                "cfg_scale": cfg_scale
            }
        }
    
    def _batch_inpaint_fallback(
        self,
        input_images: List[Image.Image],
        mask_images: List[Image.Image],
        output_prefix: str,
        progress_callback: Optional[Callable]
    ) -> Dict[str, Any]:
        """基础蒙版混合"""
        output_images = []
        output_paths = []
        
        for idx, (img, mask) in enumerate(zip(input_images, mask_images)):
            if img.mode != 'RGB':
                img = img.convert('RGB')
            if mask.mode != 'RGB':
                mask = mask.convert('RGB')
            
            # 简单混合
            result = Image.composite(img, img.filter(ImageFilter.BLUR), mask)
            
            filename = f"{output_prefix}_{idx:04d}_fallback.png"
            filepath = self.output_dir / filename
            result.save(filepath, "PNG")
            
            output_images.append(result)
            output_paths.append(str(filepath))
            
            if progress_callback:
                progress_callback({"current": idx + 1, "total": len(input_images)})
        
        return {
            "success": True,
            "images": output_images,
            "output_paths": output_paths,
            "seeds": [-1] * len(input_images),
            "generation_time": 0.0,
            "processed_count": len(input_images),
            "failed_count": 0,
            "metadata": {"mode": "fallback"}
        }
    
    def consistent_edit(
        self,
        input_images: List[Image.Image],
        prompt: str,
        negative_prompt: str = "",
        edit_mode: str = "style",  # style, subject, background
        consistency_strength: float = 0.7,
        # 其他参数
        strength: float = 0.75,
        steps: int = 28,
        cfg_scale: float = 7.5,
        seed: int = -1,
        save_images: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        output_prefix: str = "consistent_edit"
    ) -> Dict[str, Any]:
        """
        一致性编辑 - 保持多张图像风格/主体一致性
        
        Args:
            input_images: 输入图像列表
            prompt: 生成提示词
            negative_prompt: 负面提示词
            edit_mode: 编辑模式 ("style", "subject", "background")
            consistency_strength: 一致性强度
            strength: 重构强度
            steps: 推理步数
            cfg_scale: CFG缩放因子
            seed: 随机种子
            save_images: 是否保存
            progress_callback: 进度回调
            output_prefix: 输出前缀
            
        Returns:
            处理结果字典
        """
        start_time = time.time()
        
        if not input_images:
            return {"success": False, "error": "No input images"}
        
        logger.info(f"🔄 开始一致性编辑，模式: {edit_mode}")
        logger.info(f"   一致性强度: {consistency_strength}")
        
        # 生成基准种子
        if seed >= 0:
            base_seed = seed
        else:
            base_seed = np.random.randint(0, 2**32 - 1)
        
        # 提取首张图像的特征作为参考
        reference_image = input_images[0]
        
        # 对每张图像应用一致性编辑
        result = self.batch_img2img(
            input_images=input_images,
            prompt=prompt,
            negative_prompt=negative_prompt,
            strength=strength,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=base_seed,
            batch_size=1,
            save_images=save_images,
            progress_callback=progress_callback,
            output_prefix=output_prefix
        )
        
        # 应用一致性后处理
        if result["success"] and len(result["images"]) > 1:
            result = self._ensure_consistency(
                result["images"],
                edit_mode=edit_mode,
                strength=consistency_strength
            )
        
        result["generation_time"] = time.time() - start_time
        return result
    
    def _ensure_consistency(
        self,
        images: List[Image.Image],
        edit_mode: str = "style",
        strength: float = 0.7
    ) -> Dict[str, Any]:
        """
        一致性保证 - 确保多张图像的一致性
        
        Args:
            images: 图像列表
            edit_mode: 一致性模式
            strength: 调整强度
            
        Returns:
            调整后的结果
        """
        if len(images) <= 1:
            return {
                "success": True,
                "images": images,
                "output_paths": [],
                "seeds": []
            }
        
        logger.info(f"🔧 应用一致性后处理: {edit_mode}")
        
        # 计算参考图像的特征
        reference = images[0]
        ref_features = self._extract_features(reference, edit_mode)
        
        adjusted_images = [reference]  # 首张保持不变
        output_paths = []
        
        for idx, img in enumerate(images[1:], 1):
            adjusted = self._match_features(img, ref_features, edit_mode, strength)
            adjusted_images.append(adjusted)
            
            # 保存
            filename = f"consistent_{idx:04d}.png"
            filepath = self.output_dir / filename
            adjusted.save(filepath, "PNG")
            output_paths.append(str(filepath))
        
        return {
            "success": True,
            "images": adjusted_images,
            "output_paths": output_paths,
            "seeds": []
        }
    
    def _extract_features(self, image: Image.Image, mode: str) -> Dict[str, Any]:
        """提取图像特征"""
        if not self.cv2_available:
            return {"mode": mode}
        
        import cv2
        
        img_array = np.array(image.convert('RGB'))
        
        features = {"mode": mode}
        
        if mode == "style":
            # 提取颜色特征
            lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
            features["mean_color"] = np.mean(lab, axis=(0, 1))
            features["std_color"] = np.std(lab, axis=(0, 1))
            
        elif mode == "subject":
            # 提取边缘特征
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            features["edge_density"] = np.mean(edges > 0)
        
        elif mode == "background":
            # 提取背景色调
            features["mean_color"] = np.mean(img_array, axis=(0, 1))
        
        return features
    
    def _match_features(
        self,
        image: Image.Image,
        reference_features: Dict[str, Any],
        mode: str,
        strength: float
    ) -> Image.Image:
        """匹配特征"""
        if not self.cv2_available:
            return image
        
        import cv2
        
        img_array = np.array(image.convert('RGB'))
        
        if mode == "style" and "mean_color" in reference_features:
            # 调整颜色分布
            target_mean = reference_features["mean_color"]
            lab = cv2.cvtColor(img_array, cv2.COLOR_RGB2LAB)
            current_mean = np.mean(lab, axis=(0, 1))
            
            # 线性调整
            adjustment = strength * (target_mean - current_mean)
            lab = np.clip(lab + adjustment, 0, 255).astype(np.uint8)
            img_array = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
        
        elif mode == "background":
            target_mean = reference_features.get("mean_color", [128, 128, 128])
            current_mean = np.mean(img_array, axis=(0, 1))
            adjustment = strength * (target_mean - current_mean)
            img_array = np.clip(img_array + adjustment, 0, 255).astype(np.uint8)
        
        return Image.fromarray(img_array)
    
    def background_replace(
        self,
        subject_images: List[Image.Image],
        subject_masks: List[Image.Image],
        background_prompt: str,
        negative_prompt: str = "",
        blend_mode: str = "poisson",  # poisson, gaussian, alpha
        strength: float = 0.9,
        steps: int = 25,
        cfg_scale: float = 7.5,
        seed: int = -1,
        save_images: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        output_prefix: str = "bg_replace"
    ) -> Dict[str, Any]:
        """
        背景替换 - 主体保留，背景生成
        
        Args:
            subject_images: 主体图像列表
            subject_masks: 主体蒙版列表
            background_prompt: 背景提示词
            negative_prompt: 负面提示词
            blend_mode: 混合模式
            strength: 生成强度
            steps: 推理步数
            cfg_scale: CFG缩放
            seed: 随机种子
            save_images: 保存图像
            progress_callback: 进度回调
            output_prefix: 输出前缀
            
        Returns:
            处理结果
        """
        start_time = time.time()
        
        if len(subject_images) != len(subject_masks):
            return {"success": False, "error": "Image/mask count mismatch"}
        
        if not subject_images:
            return {"success": False, "error": "No images provided"}
        
        logger.info(f"🔄 开始背景替换，共 {len(subject_images)} 张")
        logger.info(f"   混合模式: {blend_mode}")
        
        if seed >= 0:
            seed_list = [(seed + i) % (2**32 - 1) for i in range(len(subject_images))]
        else:
            seed_list = [np.random.randint(0, 2**32 - 1) for _ in range(len(subject_images))]
        
        output_images = []
        output_paths = []
        seeds = []
        failed_count = 0
        errors = []
        
        for idx, (subject_img, mask_img, current_seed) in enumerate(
            zip(subject_images, subject_masks, seed_list)
        ):
            try:
                # 生成背景
                background_result = self.batch_img2img(
                    input_images=[subject_img],
                    prompt=background_prompt,
                    negative_prompt=negative_prompt,
                    strength=strength,
                    steps=steps,
                    cfg_scale=cfg_scale,
                    seed=current_seed,
                    max_parallel=1,
                    save_images=False,
                    output_prefix=f"{output_prefix}_bg_{idx}"
                )
                
                if not background_result["success"] or not background_result["images"]:
                    raise Exception("Background generation failed")
                
                background = background_result["images"][0]
                
                # 混合主体和背景
                blended = self._blend_subject_background(
                    subject_img, mask_img, background, blend_mode
                )
                
                # 保存
                output_path = None
                if save_images:
                    filename = f"{output_prefix}_{idx:04d}_{current_seed}.png"
                    filepath = self.output_dir / filename
                    blended.save(filepath, "PNG")
                    output_path = str(filepath)
                
                output_images.append(blended)
                output_paths.append(output_path)
                seeds.append(current_seed)
                
            except Exception as e:
                logger.error(f"❌ 背景替换失败 [{idx}]: {e}")
                failed_count += 1
                errors.append({"index": idx, "error": str(e)})
            
            if progress_callback:
                progress_callback({
                    "current": idx + 1,
                    "total": len(subject_images),
                    "stage": "background_replace"
                })
        
        return {
            "success": failed_count == 0,
            "images": output_images,
            "output_paths": output_paths,
            "seeds": seeds,
            "generation_time": time.time() - start_time,
            "processed_count": len(output_images),
            "failed_count": failed_count,
            "metadata": {
                "background_prompt": background_prompt,
                "blend_mode": blend_mode,
                "strength": strength
            }
        }
    
    def _blend_subject_background(
        self,
        subject: Image.Image,
        mask: Image.Image,
        background: Image.Image,
        blend_mode: str
    ) -> Image.Image:
        """混合主体和背景"""
        if subject.size != background.size:
            background = background.resize(subject.size, Image.Resampling.LANCZOS)
        
        if mask.size != subject.size:
            mask = mask.resize(subject.size, Image.Resampling.LANCZOS)
        
        if blend_mode == "alpha":
            # 阿尔法混合
            subject_rgba = subject.convert('RGBA')
            mask_rgba = mask.convert('L')
            
            # 混合
            blended = Image.composite(
                subject_rgba,
                background.convert('RGBA'),
                mask_rgba
            )
            return blended.convert('RGB')
        
        elif blend_mode == "gaussian":
            # 高斯混合 - 边缘模糊
            from PIL import ImageFilter
            
            # 羽化蒙版边缘
            blurred_mask = mask.filter(ImageFilter.GaussianBlur(radius=5))
            blurred_mask = blurred_mask.convert('L')
            
            return Image.composite(subject, background, blurred_mask)
        
        elif blend_mode == "poisson":
            # 泊松混合 - 使用颜色匹配
            if not self.cv2_available:
                return Image.composite(subject, background, mask.convert('L'))
            
            import cv2
            
            subject_np = np.array(subject.convert('RGB'))
            background_np = np.array(background.convert('RGB'))
            mask_np = np.array(mask.convert('L'))
            
            # 边缘区域检测
            mask_float = mask_np.astype(np.float32) / 255.0
            edge_mask = np.abs(cv2.Laplacian(mask_float, cv2.CV_32F))
            edge_mask = np.clip(edge_mask * 10, 0, 1)
            
            # 泊松编辑简化版：边缘区域颜色融合
            for c in range(3):
                subject_channel = subject_np[:, :, c].astype(np.float32)
                background_channel = background_np[:, :, c].astype(np.float32)
                
                # 混合
                blended = subject_channel * mask_float + background_channel * (1 - mask_float)
                
                # 边缘融合
                blended = np.where(
                    edge_mask > 0.1,
                    subject_channel * 0.5 + background_channel * 0.5,
                    blended
                )
                
                background_np[:, :, c] = np.clip(blended, 0, 255).astype(np.uint8)
            
            return Image.fromarray(background_np)
        
        else:
            return Image.composite(subject, background, mask.convert('L'))
    
    def batch_style_transfer(
        self,
        input_images: List[Image.Image],
        style: str = "anime",
        style_reference: Optional[Image.Image] = None,
        strength: float = 1.0,
        consistency_mode: str = "off",  # off, color, composition
        # 其他参数
        steps: int = 20,
        cfg_scale: float = 7.0,
        seed: int = -1,
        save_images: bool = True,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        output_prefix: str = "style_transfer"
    ) -> Dict[str, Any]:
        """
        批量风格迁移
        
        Args:
            input_images: 输入图像列表
            style: 风格类型 ("anime", "oil_painting", "watercolor", "sketch", "impressionist")
            style_reference: 参考风格图像
            strength: 风格强度
            consistency_mode: 一致性模式
            steps: 推理步数
            cfg_scale: CFG缩放
            seed: 随机种子
            save_images: 保存图像
            progress_callback: 进度回调
            output_prefix: 输出前缀
            
        Returns:
            处理结果
        """
        start_time = time.time()
        
        if not input_images:
            return {"success": False, "error": "No input images"}
        
        logger.info(f"🔄 开始风格迁移，风格: {style}")
        logger.info(f"   一致性模式: {consistency_mode}")
        
        # 构建风格提示词
        style_prompts = {
            "anime": "anime style, vibrant colors, cel shading",
            "oil_painting": "oil painting style, rich textures, artistic brushstrokes",
            "watercolor": "watercolor painting style, soft edges, delicate colors",
            "sketch": "pencil sketch style, black and white, detailed linework",
            "impressionist": "impressionist painting style, light and color play",
            "cyberpunk": "cyberpunk style, neon lights, futuristic",
            "vintage": "vintage photograph style, warm tones, film grain",
            "abstract": "abstract art style, geometric shapes, bold colors"
        }
        
        style_prompt = style_prompts.get(style, style)
        
        # 生成
        result = self.batch_img2img(
            input_images=input_images,
            prompt=style_prompt,
            negative_prompt="low quality, distorted, blurry",
            strength=strength,
            steps=steps,
            cfg_scale=cfg_scale,
            seed=seed,
            batch_size=1,
            save_images=False,
            progress_callback=progress_callback,
            output_prefix=output_prefix
        )
        
        # 应用一致性后处理
        if result["success"] and consistency_mode != "off" and len(result["images"]) > 1:
            result = self._ensure_consistency(
                result["images"],
                edit_mode="style",
                strength=0.5 if consistency_mode == "color" else 0.3
            )
        
        # 保存图像
        output_paths = []
        if save_images and result["success"]:
            for idx, (img, seed_val) in enumerate(zip(result["images"], result.get("seeds", []))):
                filename = f"{output_prefix}_{style}_{idx:04d}.png"
                filepath = self.output_dir / filename
                img.save(filepath, "PNG")
                output_paths.append(str(filepath))
        
        result["generation_time"] = time.time() - start_time
        result["output_paths"] = output_paths
        result["metadata"] = {
            **result.get("metadata", {}),
            "style": style,
            "consistency_mode": consistency_mode
        }
        
        return result
    
    def _process_batch(
        self,
        items: List[Any],
        process_func: Callable,
        batch_size: int = 4,
        max_parallel: Optional[int] = None,
        progress_callback: Optional[Callable] = None
    ) -> List[Any]:
        """
        批量处理引擎
        
        Args:
            items: 待处理项目列表
            process_func: 处理函数
            batch_size: 批次大小
            max_parallel: 最大并行数
            progress_callback: 进度回调
            
        Returns:
            处理结果列表
        """
        parallel_count = max_parallel or self.max_parallel
        results = []
        total = len(items)
        
        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch_items = items[batch_start:batch_end]
            
            with ThreadPoolExecutor(max_workers=parallel_count) as executor:
                futures = [executor.submit(process_func, item) for item in batch_items]
                
                for idx, future in enumerate(futures):
                    result = future.result()
                    results.append(result)
                    
                    if progress_callback:
                        current = batch_start + idx + 1
                        progress_callback({
                            "current": current,
                            "total": total,
                            "progress": current / total * 100
                        })
            
            # 批次间清理显存
            self._clear_memory()
        
        return results
    
    def cleanup(self):
        """清理资源"""
        self._clear_memory()
        self._pipelines.clear()
        if self._executor:
            self._executor.shutdown(wait=True)
        logger.info("🧹 多图片编辑器资源已清理")


# 全局实例管理
_global_editor: Optional[MultiImageEditor] = None
_editor_lock = threading.Lock()


def get_multi_image_editor(
    device: str = "auto",
    output_dir: str = "outputs/multi_edit",
    max_parallel: int = 2
) -> MultiImageEditor:
    """获取全局多图片编辑器实例"""
    global _global_editor
    
    with _editor_lock:
        if _global_editor is None:
            _global_editor = MultiImageEditor(
                device=device,
                output_dir=output_dir,
                max_parallel=max_parallel
            )
        return _global_editor


def init_multi_image_editor(
    device: str = "auto",
    model_name: str = "sd15_img2img",
    output_dir: str = "outputs/multi_edit"
) -> bool:
    """初始化多图片编辑器"""
    editor = get_multi_image_editor(device=device, output_dir=output_dir)
    return editor.load_models(model_name=model_name)


def main():
    """测试函数"""
    print("🎨 多图片编辑器测试")
    
    editor = get_multi_image_editor()
    
    print(f"设备: {editor.device}")
    print(f"最大并行数: {editor.max_parallel}")
    print(f"输出目录: {editor.output_dir}")
    
    # 测试模型加载
    if editor.load_models():
        print("✅ 模型加载成功")
    else:
        print("⚠️ 模型加载失败，将使用基础模式")


if __name__ == "__main__":
    main()
