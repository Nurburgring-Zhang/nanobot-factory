#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文生图(Text-to-Image)后端逻辑增强模块
实现完整的文生图功能，支持多种扩散模型
"""

import torch
import os
import time
import gc
import threading
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Union
from PIL import Image
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TextToImageGenerator:
    """
    文生图生成器类
    
    支持的模型:
    - FLUX.1-dev (black-forest-labs/FLUX.1-dev)
    - FLUX.1-schnell (black-forest-labs/FLUX.1-schnell)
    - SDXL (runwayml/stable-diffusion-xl-base-1.0)
    - SD 1.5 (runwayml/stable-diffusion-v1-5)
    - Zephyr (zemyhx/zephyr-mistral-7b-sflux)
    - HunyuanDiT (Tencent/HunyuanDiT)
    """
    
    # 模型映射表
    MODEL_MAPPING = {
        "flux_dev": "black-forest-labs/FLUX.1-dev",
        "flux_schnell": "black-forest-labs/FLUX.1-schnell",
        "sdxl": "runwayml/stable-diffusion-xl-base-1.0",
        "sd15": "runwayml/stable-diffusion-v1-5",
        "zephyr": "zemyhx/zephyr-mistral-7b-sflux",
        "hunyuan_dit": "Tencent/HunyuanDiT",
    }
    
    # 采样器映射
    SAMPLER_MAPPING = {
        "euler": "euler",
        "euler_a": "euler-a",
        "dpm_2": "dpm_2",
        "dpm_2_a": "dpm_2_a",
        "ddim": "ddim",
        "pndm": "pndm",
        "lms": "lms",
        "heun": "heun",
    }
    
    # 调度器映射
    SCHEDULER_MAPPING = {
        "normal": "normal",
        "karras": "karras",
        "exponential": "exponential",
        "simple": "simple",
        "ddim_uniform": "ddim_uniform",
    }
    
    def __init__(
        self,
        device: str = "auto",
        output_dir: str = "./outputs/text_to_image",
        cache_dir: Optional[str] = None,
    ):
        """
        初始化文生图生成器
        
        Args:
            device: 计算设备 ("auto", "cuda", "mps", "cpu")
            output_dir: 输出目录
            cache_dir: 模型缓存目录
        """
        self.device = self._get_device(device)
        self.output_dir = Path(output_dir)
        self.cache_dir = cache_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 模型相关
        self.current_model_name: Optional[str] = None
        self.pipeline: Optional[Any] = None
        self.pipeline_lock = threading.Lock()
        self.models_loaded = False
        
        # 内存管理
        self.enable_attention_slicing = True
        self.enable_vae_slicing = True
        self.enable_cpu_offload = False
        
        # 模型缓存
        self._model_cache: Dict[str, Any] = {}
        self._cache_enabled = True
        
        # 进度回调
        self._progress_callback: Optional[Callable] = None
        
        # 依赖检查
        self._check_dependencies()
        
        logger.info(f"文生图生成器初始化完成，使用设备: {self.device}")
    
    def _get_device(self, device: str) -> str:
        """
        获取最佳计算设备
        
        Args:
            device: 请求的设备 ("auto", "cuda", "mps", "cpu")
            
        Returns:
            str: 实际使用的设备
        """
        if device == "auto":
            if torch.cuda.is_available():
                return "cuda"
            elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                return "mps"
            else:
                return "cpu"
        return device
    
    def _check_dependencies(self) -> None:
        """检查依赖是否可用"""
        import os
        # 主人命令：忽略transformers版本限制
        os.environ["HF_HUB_DISABLE_VERSION_CHECK"] = "1"
        
        self.diffusers_available = False
        self.transformers_available = False
        self.peft_available = False
        
        try:
            # 使用importlib绕过版本检查
            import importlib
            import sys
            # 禁用transformers版本检查
            if hasattr(sys.modules.get('transformers', None), '__version__'):
                pass  # 已加载
            # 尝试直接导入
            import diffusers
            from diffusers import DiffusionPipeline, StableDiffusionPipeline
            self.diffusers_available = True
        except ImportError as e:
            logger.warning(f"diffusers库导入失败: {e}，文生图功能将使用降级模式")
        
        try:
            from transformers import AutoTokenizer, AutoModel
            self.transformers_available = True
        except ImportError:
            logger.warning("transformers库未安装")
    
    @property
    def torch_dtype(self) -> torch.dtype:
        """获取当前设备对应的torch数据类型"""
        if self.device == "cuda":
            return torch.float16
        elif self.device == "mps":
            return torch.float16
        else:
            return torch.float32
    
    def set_progress_callback(self, callback: Optional[Callable]) -> None:
        """
        设置进度回调函数
        
        Args:
            callback: 回调函数，签名为 callback(step: int, total: int, latents: torch.Tensor)
        """
        self._progress_callback = callback
    
    def _progress_callback_wrapper(self, step: int, timestep: int, latents: torch.Tensor) -> None:
        """进度回调包装器"""
        if self._progress_callback:
            self._progress_callback(step, self.last_total_steps, latents)
    
    def get_memory_info(self) -> Dict[str, Any]:
        """
        获取当前内存使用信息
        
        Returns:
            Dict: 包含内存信息的字典
        """
        info = {
            "device": self.device,
            "cuda_available": torch.cuda.is_available(),
        }
        
        if torch.cuda.is_available():
            info.update({
                "cuda_memory_allocated": torch.cuda.memory_allocated() / 1024**3,  # GB
                "cuda_memory_reserved": torch.cuda.memory_reserved() / 1024**3,  # GB
                "cuda_max_memory_allocated": torch.cuda.max_memory_allocated() / 1024**3,  # GB
            })
        
        if self.device == "mps":
            try:
                import torch.mps as mps
                info["mps_memory_allocated"] = mps.current_allocated_memory() / 1024**3
            except:
                pass
        
        return info
    
    def clear_memory(self) -> None:
        """清理GPU和系统内存"""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        
        gc.collect()
        logger.info("内存清理完成")
    
    def load_model(
        self,
        model_name: str = "flux_dev",
        model_path: Optional[str] = None,
        torch_dtype: str = "fp16",
        variant: Optional[str] = None,
    ) -> bool:
        """
        加载指定的文生图模型
        
        Args:
            model_name: 模型名称 (flux_dev, flux_schnell, sdxl, sd15, zephyr, hunyuan_dit)
            model_path: 自定义模型路径，如果为None则使用预定义模型
            torch_dtype: 数据类型 ("fp16", "bf16", "fp32")
            variant: 模型变体
            
        Returns:
            bool: 加载是否成功
        """
        with self.pipeline_lock:
            try:
                # 如果模型已加载且相同，直接返回
                if self.models_loaded and self.current_model_name == model_name:
                    logger.info(f"模型 {model_name} 已加载")
                    return True
                
                # 卸载现有模型
                self.unload_model()
                
                # 解析模型名称
                model_id = model_path or self.MODEL_MAPPING.get(model_name, model_name)
                logger.info(f"正在加载模型: {model_id}")
                
                # 获取数据类型
                dtype_map = {
                    "fp16": torch.float16,
                    "bf16": torch.bfloat16,
"fp32": torch.float32,
                }
                dtype = dtype_map.get(torch_dtype, torch.float16)
                
                # 根据模型类型加载不同的pipeline
                if model_name in ["flux_dev", "flux_schnell"]:
                    success = self._load_flux_pipeline(model_id, dtype, variant)
                elif model_name == "sdxl":
                    success = self._load_sdxl_pipeline(model_id, dtype, variant)
                elif model_name == "sd15":
                    success = self._load_sd15_pipeline(model_id, dtype, variant)
                elif model_name == "hunyuan_dit":
                    success = self._load_hunyuan_pipeline(model_id, dtype, variant)
                else:
                    # 默认尝试加载SD pipeline
                    success = self._load_sd15_pipeline(model_id, dtype, variant)
                
                if success:
                    self.current_model_name = model_name
                    self.models_loaded = True
                    logger.info(f"模型 {model_name} 加载成功")
                else:
                    logger.error(f"模型 {model_name} 加载失败")
                
                return success
                
            except Exception as e:
                logger.error(f"加载模型时出错: {e}")
                self.models_loaded = False
                return False
    
    def _load_flux_pipeline(
        self,
        model_id: str,
        dtype: torch.dtype,
        variant: Optional[str],
    ) -> bool:
        """加载FLUX模型"""
        try:
            from diffusers import FluxPipeline
            
            load_kwargs = {
                "torch_dtype": dtype,
                "cache_dir": self.cache_dir,
            }
            
            if variant:
                load_kwargs["variant"] = variant
            
            self.pipeline = FluxPipeline.from_pretrained(
                model_id,
                **load_kwargs
            )
            
            # 应用内存优化
            self._apply_memory_optimizations()
            
            # 移动到设备
            self.pipeline.to(self.device)
            
            return True
            
        except Exception as e:
            logger.error(f"加载FLUX模型失败: {e}")
            return False
    
    def _load_sdxl_pipeline(
        self,
        model_id: str,
        dtype: torch.dtype,
        variant: Optional[str],
    ) -> bool:
        """加载SDXL模型"""
        try:
            from diffusers import StableDiffusionXLPipeline
            
            load_kwargs = {
                "torch_dtype": dtype,
                "cache_dir": self.cache_dir,
            }
            
            if variant:
                load_kwargs["variant"] = variant
            
            self.pipeline = StableDiffusionXLPipeline.from_pretrained(
                model_id,
                **load_kwargs
            )
            
            self._apply_memory_optimizations()
            self.pipeline.to(self.device)
            
            return True
            
        except Exception as e:
            logger.error(f"加载SDXL模型失败: {e}")
            return False
    
    def _load_sd15_pipeline(
        self,
        model_id: str,
        dtype: torch.dtype,
        variant: Optional[str],
    ) -> bool:
        """加载SD 1.5模型"""
        try:
            from diffusers import StableDiffusionPipeline
            
            load_kwargs = {
                "torch_dtype": dtype,
                "cache_dir": self.cache_dir,
                "safety_checker": None,
                "requires_safety_checker": False,
            }
            
            if variant:
                load_kwargs["variant"] = variant
            
            self.pipeline = StableDiffusionPipeline.from_pretrained(
                model_id,
                **load_kwargs
            )
            
            self._apply_memory_optimizations()
            self.pipeline.to(self.device)
            
            return True
            
        except Exception as e:
            logger.error(f"加载SD1.5模型失败: {e}")
            return False
    
    def _load_hunyuan_pipeline(
        self,
        model_id: str,
        dtype: torch.dtype,
        variant: Optional[str],
    ) -> bool:
        """加载HunyuanDiT模型"""
        try:
            # HunyuanDiT使用自定义pipeline
            from diffusers import HunyuanDiTPipeline
            
            load_kwargs = {
                "torch_dtype": dtype,
                "cache_dir": self.cache_dir,
            }
            
            self.pipeline = HunyuanDiTPipeline.from_pretrained(
                model_id,
                **load_kwargs
            )
            
            self._apply_memory_optimizations()
            self.pipeline.to(self.device)
            
            return True
            
        except Exception as e:
            logger.error(f"加载HunyuanDiT模型失败: {e}")
            # 尝试使用通用SDXL pipeline
            return self._load_sdxl_pipeline(model_id, dtype, variant)
    
    def _apply_memory_optimizations(self) -> None:
        """应用内存优化设置"""
        if not hasattr(self.pipeline, 'enable_attention_slicing'):
            return
            
        if self.enable_attention_slicing:
            try:
                self.pipeline.enable_attention_slicing()
                logger.info("已启用attention slicing")
            except Exception as e:
                logger.warning(f"启用attention slicing失败: {e}")
        
        if self.enable_vae_slicing:
            try:
                self.pipeline.enable_vae_slicing()
                logger.info("已启用VAE slicing")
            except Exception as e:
                logger.warning(f"启用VAE slicing失败: {e}")
        
        if self.enable_cpu_offload and self.device == "cuda":
            try:
                self.pipeline.enable_sequential_cpu_offload()
                logger.info("已启用CPU offload")
            except Exception as e:
                logger.warning(f"启用CPU offload失败: {e}")
    
    def unload_model(self) -> None:
        """卸载当前模型，释放内存"""
        with self.pipeline_lock:
            if self.pipeline is not None:
                logger.info("正在卸载模型...")
                
                # 清理pipeline
                del self.pipeline
                self.pipeline = None
                
                # 清理缓存
                self._model_cache.clear()
                
                # 清理内存
                self.clear_memory()
                
                self.models_loaded = False
                self.current_model_name = None
                
                logger.info("模型卸载完成")
    
    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        # 基础参数
        width: int = 1024,
        height: int = 1024,
        steps: int = 28,
        cfg_scale: float = 7.0,
        seed: int = -1,
        batch_size: int = 1,
        # 采样器参数
        sampler: str = "euler_a",
        scheduler: str = "karras",
        # 模型参数
        model_name: str = "flux_dev",
        model_path: Optional[str] = None,
        torch_dtype: str = "fp16",
        # LoRA参数
        lora_paths: List[str] = [],
        lora_weights: List[float] = [],
        # ControlNet参数
        controlnet_paths: List[str] = [],
        controlnet_weights: List[float] = [],
        control_images: List[Image.Image] = [],
        # 高级参数
        guidance_scale: float = 3.5,
        num_variance_groups: int = 0,
        # 优化参数
        enable_attention_slicing: bool = True,
        enable_vae_slicing: bool = True,
        enable_cpu_offload: bool = False,
    ) -> Dict[str, Any]:
        """
        生成图像
        
        Args:
            prompt: 正向提示词
            negative_prompt: 负向提示词
            width: 图像宽度
            height: 图像高度
            steps: 推理步数
            cfg_scale: CFG比例
            seed: 随机种子，-1表示随机
            batch_size: 批量大小
            sampler: 采样器类型
            scheduler: 调度器类型
            model_name: 模型名称
            model_path: 自定义模型路径
            torch_dtype: 数据类型
            lora_paths: LoRA模型路径列表
            lora_weights: LoRA权重列表
            controlnet_paths: ControlNet路径列表
            controlnet_weights: ControlNet权重列表
            control_images: ControlNet控制图像列表
            guidance_scale: 引导比例 (FLUX专用)
            num_variance_groups: 方差组数量
            enable_attention_slicing: 启用注意力切片
            enable_vae_slicing: 启用VAE切片
            enable_cpu_offload: 启用CPU卸载
            
        Returns:
            Dict: 包含生成结果的字典
        """
        start_time = time.time()
        
        # 记录参数
        generation_params = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "steps": steps,
            "cfg_scale": cfg_scale,
            "seed": seed,
            "batch_size": batch_size,
            "sampler": sampler,
            "scheduler": scheduler,
            "model_name": model_name,
            "lora_paths": lora_paths,
            "controlnet_paths": controlnet_paths,
            "guidance_scale": guidance_scale,
        }
        
        try:
            # 应用优化参数
            self.enable_attention_slicing = enable_attention_slicing
            self.enable_vae_slicing = enable_vae_slicing
            self.enable_cpu_offload = enable_cpu_offload
            
            # 确保模型已加载
            if not self.models_loaded or self.current_model_name != model_name:
                logger.info(f"自动加载模型: {model_name}")
                if not self.load_model(model_name, model_path, torch_dtype):
                    return {
                        "success": False,
                        "error": f"模型 {model_name} 加载失败",
                        "generation_time": time.time() - start_time,
                        "metadata": generation_params,
                    }
            
            # 准备pipeline
            pipeline = self._prepare_pipeline(
                sampler=sampler,
                scheduler=scheduler,
            )
            
            # 应用LoRA
            if lora_paths:
                self._apply_loras(lora_paths, lora_weights)
            
            # 应用ControlNet
            if controlnet_paths and control_images:
                self._apply_controlnet(controlnet_paths, controlnet_weights, control_images)
            
            # 生成种子
            if seed < 0:
                seed = torch.randint(0, 2**32 - 1, (1,)).item()
            
            # 设置推理步数
            self.last_total_steps = steps
            
            # 确定是否为FLUX模型
            is_flux = model_name in ["flux_dev", "flux_schnell"]
            
            # 准备生成参数
            if is_flux:
                # FLUX模型的生成参数
                generator_args = {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "width": width,
                    "height": height,
                    "num_inference_steps": steps,
                    "guidance_scale": guidance_scale,
                    "max_sequence_length": 512,
                    "num_images_per_prompt": batch_size,
                }
                
                if seed >= 0:
                    generator_args["generator"] = torch.Generator(device=self.device).manual_seed(seed)
                
                # 添加回调
                if self._progress_callback:
                    generation_args["callback"] = self._progress_callback_wrapper
                    generation_args["callback_steps"] = 1
                
                # 执行生成
                with torch.autocast(self.device, dtype=torch.float16) if self.device == "cuda" else torch.no_grad():
                    result = pipeline(**generation_args)
                
                images = result.images
                
            else:
                # SD/SDXL模型的生成参数
                generator_args = {
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "width": width,
                    "height": height,
                    "num_inference_steps": steps,
                    "guidance_scale": cfg_scale,
                    "num_images_per_prompt": batch_size,
                }
                
                if seed >= 0:
                    generator_args["generator"] = torch.Generator(device=self.device).manual_seed(seed)
                
                # 添加回调
                if self._progress_callback:
                    generator_args["callback"] = self._progress_callback_wrapper
                    generator_args["callback_steps"] = 1
                
                # 执行生成
                with torch.autocast(self.device, dtype=torch.float16) if self.device == "cuda" else torch.no_grad():
                    result = pipeline(**generator_args)
                
                images = result.images
            
            # 保存输出图像
            output_paths = self._save_output(images, seed, model_name)
            
            generation_time = time.time() - start_time
            
            logger.info(f"生成完成: {len(images)}张图像, 耗时: {generation_time:.2f}秒")
            
            return {
                "success": True,
                "images": images,
                "output_paths": output_paths,
                "seed": seed,
                "generation_time": generation_time,
                "model": model_name,
                "metadata": {
                    **generation_params,
                    "lora_used": lora_paths,
                    "controlnet_used": controlnet_paths,
                },
            }
            
        except Exception as e:
            logger.error(f"生成失败: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "error": str(e),
                "generation_time": time.time() - start_time,
                "metadata": generation_params,
            }
    
    def _prepare_pipeline(
        self,
        sampler: str = "euler_a",
        scheduler: str = "karras",
    ) -> Any:
        """
        准备pipeline，应用采样器和调度器设置
        
        Args:
            sampler: 采样器类型
            scheduler: 调度器类型
            
        Returns:
            配置好的pipeline
        """
        if self.pipeline is None:
            raise RuntimeError("Pipeline未加载")
        
        try:
            # 获取调度器
            scheduler_name = self.SCHEDULER_MAPPING.get(scheduler, scheduler)
            
            # 根据采样器设置调度器
            if hasattr(self.pipeline, 'scheduler'):
                from diffusers import (
                    EulerDiscreteScheduler,
                    EulerAncestralDiscreteScheduler,
                    DPMSolverMultistepScheduler,
                    DDIMScheduler,
                    PNDMScheduler,
                    LMSDiscreteScheduler,
                    HeunDiscreteScheduler,
                )
                
                scheduler_map = {
                    "euler": EulerDiscreteScheduler,
                    "euler_a": EulerAncestralDiscreteScheduler,
                    "dpm_2": lambda config: DPMSolverMultistepScheduler.from_config(config, algorithm_type="dpmsolver"),
                    "dpm_2_a": lambda config: DPMSolverMultistepScheduler.from_config(config, algorithm_type="dpmsolver++"),
                    "ddim": DDIMScheduler,
                    "pndm": PNDMScheduler,
                    "lms": LMSDiscreteScheduler,
                    "heun": HeunDiscreteScheduler,
                }
                
                scheduler_class = scheduler_map.get(sampler)
                if scheduler_class:
                    scheduler_instance = scheduler_class.from_config(self.pipeline.scheduler.config)
                    self.pipeline.scheduler = scheduler_instance
            
            return self.pipeline
            
        except Exception as e:
            logger.warning(f"设置调度器失败: {e}")
            return self.pipeline
    
    def _apply_loras(
        self,
        lora_paths: List[str],
        lora_weights: List[float] = [],
    ) -> bool:
        """
        应用LoRA模型
        
        Args:
            lora_paths: LoRA模型路径列表
            lora_weights: 对应的权重列表
            
        Returns:
            bool: 是否成功
        """
        if not self.peft_available or self.pipeline is None:
            logger.warning("LoRA功能不可用或pipeline未加载")
            return False
        
        try:
            from peft import PeftModel
            
            # 确保pipeline有text_encoder
            if not hasattr(self.pipeline, 'text_encoder'):
                logger.warning("Pipeline没有text_encoder，无法应用LoRA")
                return False
            
            # 默认权重
            if not lora_weights:
                lora_weights = [1.0] * len(lora_paths)
            
            # 应用每个LoRA
            for lora_path, weight in zip(lora_paths, lora_weights):
                logger.info(f"应用LoRA: {lora_path}, 权重: {weight}")
                
                # 检查是否是safetensors格式
                if lora_path.endswith('.safetensors'):
                    from safetensors.torch import load_file
                    state_dict = load_file(lora_path)
                else:
                    # 尝试使用torch加载
                    state_dict = torch.load(lora_path, map_location=self.device)
                
                # 应用LoRA到text_encoder
                self.pipeline.text_encoder = PeftModel.from_pretrained(
                    self.pipeline.text_encoder,
                    lora_path
                )
                
                # 设置LoRA权重
                # 注意: 这里需要根据具体的PeftModel实现来设置权重
            
            logger.info(f"成功应用 {len(lora_paths)} 个LoRA")
            return True
            
        except Exception as e:
            logger.error(f"应用LoRA失败: {e}")
            return False
    
    def _apply_controlnet(
        self,
        controlnet_paths: List[str],
        controlnet_weights: List[float],
        control_images: List[Image.Image],
    ) -> bool:
        """
        应用ControlNet
        
        Args:
            controlnet_paths: ControlNet路径列表
            controlnet_weights: 控制权重列表
            control_images: 控制图像列表
            
        Returns:
            bool: 是否成功
        """
        if not controlnet_paths or not control_images:
            return True
        
        if self.pipeline is None:
            logger.warning("Pipeline未加载，无法应用ControlNet")
            return False
        
        try:
            from diffusers import ControlNetModel, StableDiffusionControlNetPipeline
            
            # 默认权重
            if not controlnet_weights:
                controlnet_weights = [1.0] * len(controlnet_paths)
            
            logger.info(f"准备应用 {len(controlnet_paths)} 个ControlNet")
            
            # 对于多ControlNet，需要创建MultiControlNet
            # 这里简化处理，只使用第一个ControlNet
            controlnet_model = ControlNetModel.from_pretrained(
                controlnet_paths[0],
                torch_dtype=self.torch_dtype,
                cache_dir=self.cache_dir,
            )
            
            # 创建ControlNet pipeline
            self.pipeline = StableDiffusionControlNetPipeline.from_pipe(
                self.pipeline,
                controlnet=controlnet_model,
                torch_dtype=self.torch_dtype,
            )
            
            self.pipeline.to(self.device)
            
            logger.info("ControlNet应用成功")
            return True
            
        except Exception as e:
            logger.error(f"应用ControlNet失败: {e}")
            return False
    
    def _save_output(
        self,
        images: List[Image.Image],
        seed: int,
        model_name: str,
    ) -> List[str]:
        """
        保存生成的图像
        
        Args:
            images: 图像列表
            seed: 使用的种子
            model_name: 模型名称
            
        Returns:
            List[str]: 保存的文件路径列表
        """
        output_paths = []
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        
        for i, img in enumerate(images):
            filename = f"{model_name}_{timestamp}_{seed}_{i:03d}.png"
            filepath = self.output_dir / filename
            
            # 确保目录存在
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存图像
            img.save(filepath, "PNG")
            output_paths.append(str(filepath))
            logger.info(f"已保存图像: {filepath}")
        
        return output_paths
    
    def get_available_models(self) -> List[Dict[str, str]]:
        """
        获取可用的模型列表
        
        Returns:
            List[Dict]: 模型信息列表
        """
        models = []
        for key, model_id in self.MODEL_MAPPING.items():
            models.append({
                "name": key,
                "model_id": model_id,
            })
        return models
    
    def get_available_samplers(self) -> List[str]:
        """
        获取可用的采样器列表
        
        Returns:
            List[str]: 采样器名称列表
        """
        return list(self.SAMPLER_MAPPING.keys())
    
    def get_available_schedulers(self) -> List[str]:
        """
        获取可用的调度器列表
        
        Returns:
            List[str]: 调度器名称列表
        """
        return list(self.SCHEDULER_MAPPING.keys())


class TextToImageAPIService:
    """
    文生图API服务类
    
    提供RESTful API接口，支持:
    - 同步/异步图像生成
    - 批量生成
    - 任务队列管理
    """
    
    def __init__(self, generator: Optional[TextToImageGenerator] = None):
        """
        初始化API服务
        
        Args:
            generator: TextToImageGenerator实例，如果为None则创建新实例
        """
        self.generator = generator or TextToImageGenerator()
        self.task_queue: Dict[str, Dict[str, Any]] = {}
        self._task_counter = 0
    
    def create_task(
        self,
        params: Dict[str, Any],
    ) -> str:
        """
        创建生成任务
        
        Args:
            params: 生成参数
            
        Returns:
            str: 任务ID
        """
        self._task_counter += 1
        task_id = f"t2i_{int(time.time())}_{self._task_counter}"
        
        self.task_queue[task_id] = {
            "id": task_id,
            "params": params,
            "status": "pending",
            "created_at": time.time(),
            "started_at": None,
            "completed_at": None,
            "result": None,
            "error": None,
        }
        
        return task_id
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[Dict]: 任务信息
        """
        return self.task_queue.get(task_id)
    
    def execute_task(self, task_id: str) -> Dict[str, Any]:
        """
        执行指定任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 执行结果
        """
        task = self.task_queue.get(task_id)
        if not task:
            return {"success": False, "error": "任务不存在"}
        
        task["status"] = "running"
        task["started_at"] = time.time()
        
        try:
            result = self.generator.generate(**task["params"])
            task["status"] = "completed"
            task["completed_at"] = time.time()
            task["result"] = result
            return result
        except Exception as e:
            task["status"] = "failed"
            task["completed_at"] = time.time()
            task["error"] = str(e)
            return {"success": False, "error": str(e)}
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            bool: 是否成功
        """
        task = self.task_queue.get(task_id)
        if not task:
            return False
        
        if task["status"] in ["pending", "running"]:
            task["status"] = "cancelled"
            return True
        
        return False


# 全局生成器实例
_global_generator: Optional[TextToImageGenerator] = None
_global_api_service: Optional[TextToImageAPIService] = None


def get_generator(device: str = "auto") -> TextToImageGenerator:
    """
    获取全局文生图生成器实例
    
    Args:
        device: 计算设备
        
    Returns:
        TextToImageGenerator: 生成器实例
    """
    global _global_generator
    if _global_generator is None:
        _global_generator = TextToImageGenerator(device=device)
    return _global_generator


def get_api_service(generator: Optional[TextToImageGenerator] = None) -> TextToImageAPIService:
    """
    获取全局API服务实例
    
    Args:
        generator: 可选的生成器实例
        
    Returns:
        TextToImageAPIService: API服务实例
    """
    global _global_api_service
    if _global_api_service is None:
        _global_api_service = TextToImageAPIService(generator)
    return _global_api_service


def init_generator(
    model_name: str = "flux_dev",
    device: str = "auto",
    torch_dtype: str = "fp16",
) -> bool:
    """
    初始化文生图生成器
    
    Args:
        model_name: 默认模型名称
        device: 计算设备
        torch_dtype: 数据类型
        
    Returns:
        bool: 初始化是否成功
    """
    generator = get_generator(device)
    return generator.load_model(model_name, torch_dtype=torch_dtype)


def generate_image(
    prompt: str,
    negative_prompt: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """
    快捷生成函数
    
    Args:
        prompt: 正向提示词
        negative_prompt: 负向提示词
        **kwargs: 其他生成参数
        
    Returns:
        Dict: 生成结果
    """
    generator = get_generator()
    return generator.generate(prompt, negative_prompt, **kwargs)


if __name__ == "__main__":
    # 测试代码
    print("测试文生图模块...")
    
    generator = TextToImageGenerator(device="auto")
    
    # 显示可用模型
    print(f"\n可用模型: {generator.get_available_models()}")
    print(f"可用采样器: {generator.get_available_samplers()}")
    print(f"可用调度器: {generator.get_available_schedulers()}")
    
    # 显示内存信息
    print(f"\n内存信息: {generator.get_memory_info()}")
    
    # 尝试加载模型（如果有diffusers）
    if generator.diffusers_available:
        print("\n尝试加载SD 1.5模型...")
        if generator.load_model("sd15"):
            print("模型加载成功")
            
            # 执行测试生成（使用简单提示词）
            print("\n执行测试生成...")
            result = generator.generate(
                prompt="a beautiful landscape",
                negative_prompt="blurry, low quality",
                width=512,
                height=512,
                steps=10,  # 较少步数用于快速测试
                seed=42,
            )
            
            if result["success"]:
                print(f"生成成功!")
                print(f"输出路径: {result['output_paths']}")
                print(f"耗时: {result['generation_time']:.2f}秒")
            else:
                print(f"生成失败: {result.get('error', '未知错误')}")
            
            # 卸载模型
            generator.unload_model()
        else:
            print("模型加载失败")
    else:
        print("diffusers库未安装，无法测试模型加载")
    
    print("\n测试完成")
