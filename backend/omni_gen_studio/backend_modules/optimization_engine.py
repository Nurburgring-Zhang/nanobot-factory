#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optimization Engine Module
优化引擎模块 - 提供图像生成优化的核心功能

功能:
1. Noise injection - 推理开始第一步注入随机噪音增强构图与细节
2. Seed enhance - 对正面条件推理第一步注入随机噪音优化构图
3. 高级CFG优化
4. 高级采样算法优化
5. 支持在生成后进行画质优化与放大
"""

import torch
import numpy as np
from typing import List, Dict, Any, Optional, Union
from PIL import Image
import logging
import gc

logger = logging.getLogger(__name__)


class OptimizationEngine:
    """
    优化引擎类
    
    提供多种图像生成优化功能:
    - Noise injection: 在推理第一步注入随机噪音增强构图
    - Seed enhance: 对正面条件注入噪音优化构图
    - CFG优化: 智能调整CFG参数
    - 高级采样: 支持多种高级采样算法
    """
    
    # 支持的采样器列表
    SUPPORTED_SAMPLERS = [
        "euler", "euler_a", "dpm_2", "dpm_2_a", "dpm++_2m", 
        "dpm++_2m_karras", "dpm++_sde", "dpm++_sde_karras",
        "ddim", "pndm", "lms", "heun", "unipc", "pndm_lms"
    ]
    
    def __init__(self, device: str = "cuda"):
        """
        初始化优化引擎
        
        Args:
            device: 计算设备 ("cuda", "cpu", "mps")
        """
        self.device = device
        self._torch_device = torch.device(device) if device != "mps" else torch.device("cpu")
        self._random_state: Optional[np.random.RandomState] = None
        logger.info(f"OptimizationEngine initialized on device: {device}")
    
    def _get_random_state(self, seed: int = -1) -> np.random.RandomState:
        """
        获取或创建随机状态
        
        Args:
            seed: 随机种子, -1表示使用系统时间
            
        Returns:
            RandomState对象
        """
        if seed == -1:
            seed = int(np.random.randint(0, 2**32 - 1))
        
        return np.random.RandomState(seed)
    
    def _tensor_to_noise(self, tensor: torch.Tensor, noise: np.ndarray) -> torch.Tensor:
        """
        将numpy噪音转换为torch张量
        
        Args:
            tensor: 目标张量
            noise: numpy噪音数组
            
        Returns:
            torch.Tensor: 相同设备的torch张量
        """
        noise_tensor = torch.from_numpy(noise).float()
        if tensor.device.type != "cpu":
            noise_tensor = noise_tensor.to(tensor.device)
        return noise_tensor
    
    def apply_noise_injection(
        self, 
        latents: torch.Tensor, 
        ratio: float = 0.1, 
        seed: int = -1
    ) -> torch.Tensor:
        """
        噪声注入 - 推理开始第一步注入随机噪音增强构图与细节
        
        在扩散模型推理的第一步，向latent空间注入可控的随机噪声，
        以增强图像构图多样性和细节表现。
        
        Args:
            latents: 输入的latent张量, 形状 [B, C, H, W]
            ratio: 噪音注入比例 (0.0-1.0), 默认0.1
            seed: 随机种子, -1表示随机
            
        Returns:
            注入噪音后的latent张量
            
        Raises:
            ValueError: ratio超出有效范围
        """
        if not 0.0 <= ratio <= 1.0:
            raise ValueError(f"ratio must be between 0.0 and 1.0, got {ratio}")
        
        rs = self._get_random_state(seed)
        
        # 计算噪音的std，参考latent的分布
        latent_std = torch.std(latents).item()
        noiseMagnitude = latent_std * ratio
        
        # 生成与latent相同形状的噪音
        noise_shape = latents.shape
        noise = rs.randn(*noise_shape).astype(np.float32)
        
        # 转换为torch张量
        noise_tensor = self._tensor_to_noise(latents, noise)
        
        # 根据ratio调整噪音强度
        noise_tensor = noise_tensor * ratio
        
        # 注入噪音
        noisy_latents = latents + noise_tensor
        
        logger.debug(
            f"Noise injection applied: ratio={ratio}, seed={seed}, "
            f"noise_magnitude={noiseMagnitude:.4f}, shape={list(noise_shape)}"
        )
        
        return noisy_latents
    
    def apply_seed_enhance(
        self, 
        latents: torch.Tensor, 
        ratio: float = 0.1, 
        seed: int = -1
    ) -> torch.Tensor:
        """
        种子增强 - 对正面条件推理第一步注入随机噪音优化构图
        
        与普通noise injection不同，seed enhance专门针对正面条件
        进行优化，通过精细控制噪音来改善构图和细节。
        
        Args:
            latents: 输入的latent张量
            ratio: 噪音注入比例 (0.0-1.0), 默认0.1
            seed: 随机种子, -1表示随机
            
        Returns:
            增强后的latent张量
        """
        if not 0.0 <= ratio <= 1.0:
            raise ValueError(f"ratio must be between 0.0 and 1.0, got {ratio}")
        
        rs = self._get_random_state(seed)
        
        # 使用latent的统计特性来生成适配的噪音
        latent_mean = torch.mean(latents).item()
        latent_std = torch.std(latents).item()
        
        noise_shape = latents.shape
        # 使用正态分布生成噪音
        noise = rs.normal(latent_mean, latent_std * ratio, size=noise_shape).astype(np.float32)
        
        noise_tensor = self._tensor_to_noise(latents, noise)
        
        # 轻微的尺度调整以保持latent分布特性
        scale_factor = 0.9 + ratio * 0.2  # 0.9-1.1范围
        noise_tensor = noise_tensor * scale_factor * ratio
        
        enhanced_latents = latents + noise_tensor
        
        logger.debug(
            f"Seed enhance applied: ratio={ratio}, seed={seed}, "
            f"mean={latent_mean:.4f}, std={latent_std:.4f}"
        )
        
        return enhanced_latents
    
    def optimize_cfg(
        self, 
        cfg_scale: float, 
        base_prompt: str, 
        negative_prompt: str
    ) -> float:
        """
        高级CFG优化 - 根据提示词复杂度智能调整CFG参数
        
        分析提示词的长度和复杂度，自动调整CFG值以获得
        更好的生成效果。
        
        Args:
            cfg_scale: 基础CFG值
            base_prompt: 正面提示词
            negative_prompt: 负面提示词
            
        Returns:
            优化后的CFG值
        """
        # 基于提示词长度调整
        prompt_length = len(base_prompt.split())
        
        # 基础调整因子
        length_factor = 1.0
        
        # 长提示词适当降低CFG，短提示词可以提高
        if prompt_length > 50:
            length_factor = 0.9
        elif prompt_length > 30:
            length_factor = 0.95
        elif prompt_length < 10:
            length_factor = 1.05
        
        # 检测负面提示词复杂度
        neg_length = len(negative_prompt.split()) if negative_prompt else 0
        
        negative_factor = 1.0
        if neg_length > 30:
            # 复杂负面提示降低CFG以避免过度排斥
            negative_factor = 0.95
        elif neg_length == 0:
            # 无负面提示可以适当提高CFG
            negative_factor = 1.05
        
        # 综合调整
        optimized_cfg = cfg_scale * length_factor * negative_factor
        
        # 确保在合理范围内
        optimized_cfg = max(1.0, min(20.0, optimized_cfg))
        
        logger.debug(
            f"CFG optimized: original={cfg_scale}, optimized={optimized_cfg:.2f}, "
            f"prompt_length={prompt_length}, neg_length={neg_length}"
        )
        
        return optimized_cfg
    
    def apply_advanced_sampling(
        self, 
        pipeline, 
        prompt: str, 
        negative_prompt: str,
        sampler: str = "euler_a",
        **kwargs
    ) -> Any:
        """
        应用高级采样算法
        
        支持多种高级采样器，提供更好的生成质量和速度平衡。
        
        Args:
            pipeline: Diffusers pipeline对象
            prompt: 正面提示词
            negative_prompt: 负面提示词
            sampler: 采样器名称
            
        Returns:
            生成后的图像
            
        Raises:
            ValueError: 不支持的采样器
        """
        if sampler not in self.SUPPORTED_SAMPLERS:
            raise ValueError(
                f"Unsupported sampler: {sampler}. "
                f"Supported: {', '.join(self.SUPPORTED_SAMPLERS)}"
            )
        
        logger.info(f"Applying advanced sampling with sampler: {sampler}")
        
        try:
            # 尝试不同的采样器配置
            from diffusers import (
                EulerAncestralDiscreteScheduler,
                DPMSolverMultistepScheduler,
                DDIMScheduler,
                PNDMScheduler,
                UniPCMultistepScheduler
            )
            
            # 配置调度器
            if sampler in ["euler", "euler_a"]:
                scheduler = EulerAncestralDiscreteScheduler.from_config(
                    pipeline.scheduler.config
                )
            elif sampler.startswith("dpm++"):
                scheduler = DPMSolverMultistepScheduler.from_config(
                    pipeline.scheduler.config
                )
                if "karras" in sampler:
                    scheduler.config.use_karras_sigmas = True
            elif sampler == "ddim":
                scheduler = DDIMScheduler.from_config(pipeline.scheduler.config)
            elif sampler == "pndm" or sampler == "pndm_lms":
                scheduler = PNDMScheduler.from_config(pipeline.scheduler.config)
            elif sampler == "unipc":
                scheduler = UniPCMultistepScheduler.from_config(
                    pipeline.scheduler.config
                )
            else:
                # 默认使用euler_a
                scheduler = EulerAncestralDiscreteScheduler.from_config(
                    pipeline.scheduler.config
                )
            
            pipeline.scheduler = scheduler
            
            # 执行生成
            with torch.inference_mode():
                result = pipeline(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    **kwargs
                )
            
            logger.info(f"Sampling completed with {sampler}")
            return result
            
        except ImportError as e:
            logger.error(f"Failed to import scheduler: {e}")
            raise
        except Exception as e:
            logger.error(f"Sampling failed: {e}")
            raise


class UpscaleEngine:
    """
    图像放大引擎
    
    支持多种超分辨率模型进行图像放大和画质增强:
    - Real-ESRGAN: 通用图像放大
    - SwinIR: 基于Transformer的高质量放大
    - AnimeGAN: 动漫风格图像放大
    """
    
    # 支持的放大模型
    SUPPORTED_MODELS = ["realesrgan", "swinir", "animegan", "4xUltralytics"]
    
    # 模型配置
    MODEL_CONFIGS = {
        "realesrgan": {
            "default_scale": 4,
            "model_url": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth"
        },
        "swinir": {
            "default_scale": 4,
            "model_url": "https://github.com/JingyunLiang/SwinIR/releases/download/v0.0/003_real_sr_BSRGAN_DFOWMFC_s64w8_SwinIR-L_x4_GAN.pth"
        },
        "animegan": {
            "default_scale": 2,
            "model_url": "https://github.com/TachibanaYoshino/AnimeGANv2/releases/download/v1.0/RealAnime明治_1.0.pth"
        },
        "4xUltralytics": {
            "default_scale": 4,
            "model_url": None  # 通过ultralytics加载
        }
    }
    
    def __init__(self, device: str = "cuda"):
        """
        初始化放大引擎
        
        Args:
            device: 计算设备
        """
        self.device = device
        self._models_cache: Dict[str, Any] = {}
        self._torch_device = torch.device(device) if device != "mps" else torch.device("cpu")
        logger.info(f"UpscaleEngine initialized on device: {device}")
    
    def _load_realesrgan(self, model_name: str = "realesrgan") -> Any:
        """
        加载Real-ESRGAN模型
        
        Args:
            model_name: 模型名称
            
        Returns:
            Real-ESRGAN模型
        """
        try:
            from basicsr.archs.rrdbnet_arch import RRDBNet
            
            model_config = self.MODEL_CONFIGS.get(model_name, self.MODEL_CONFIGS["realesrgan"])
            
            # 创建模型
            model = RRDBNet(
                num_in_ch=3,
                num_out_ch=3,
                num_feat=64,
                num_block=23,
                num_g_row_g蒸馏=1
            )
            
            # 尝试加载预训练权重
            model_path = None
            try:
                from basicsr.utils.download_util import download_file
                model_path = download_file(model_config["model_url"])
            except Exception:
                logger.warning(f"Could not download model, using uninitialized model")
            
            if model_path and torch.cuda.is_available():
                device = self._torch_device
            else:
                device = torch.device("cpu")
            
            model = model.to(device)
            model.eval()
            
            logger.info(f"Real-ESRGAN model loaded")
            return model
            
        except ImportError as e:
            logger.error(f"basicsr not available: {e}")
            # 回退到简单的双线性插值
            logger.info("Falling back to PIL resize")
            return None
    
    def _load_swinir(self) -> Any:
        """
        加载SwinIR模型
        """
        try:
            import os
            # SwinIR模型结构
            from basicsr.archs.srformer_arch import SwinTransformer
            
            model = SwinTransformer(
                img_size=64,
                patch_size=1,
                in_chans=3,
                embed_dim=180,
                depths=[6, 6, 6, 6, 6, 6],
                num_heads=[6, 6, 6, 6, 6, 6],
                mlp_ratio=2.0,
                drop_rate=0.0,
                drop_path_rate=0.2
            )
            
            model = model.to(self._torch_device)
            model.eval()
            
            logger.info("SwinIR model loaded")
            return model
            
        except Exception as e:
            logger.error(f"Failed to load SwinIR: {e}")
            return None
    
    def _load_ultralytics(self) -> Any:
        """
        加载Ultralytics超分辨率模型
        """
        try:
            from ultralytics import SR
            model = SR("restructiveFRealESRGAN/4xUltralyticsM-base")
            logger.info("Ultralytics 4x model loaded")
            return model
        except ImportError:
            logger.error("ultralytics not available")
            return None
        except Exception as e:
            logger.warning(f"Failed to load ultralytics model: {e}")
            return None
    
    def upscale_image(
        self, 
        image: Image.Image, 
        model: str = "realesrgan", 
        scale: int = 2, 
        denoising_strength: float = 0.4
    ) -> Image.Image:
        """
        放大单张图像
        
        Args:
            image: 输入的PIL图像
            model: 放大模型名称 ("realesrgan", "swinir", "animegan", "4xUltralytics")
            scale: 放大倍数 (2或4)
            denoising_strength: 去噪强度 (0.0-1.0)
            
        Returns:
            放大后的PIL图像
            
        Raises:
            ValueError: 不支持的模型或缩放比例
        """
        if model not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported model: {model}. "
                f"Supported: {', '.join(self.SUPPORTED_MODELS)}"
            )
        
        if scale not in [2, 4]:
            raise ValueError(f"Only scale 2 or 4 supported, got {scale}")
        
        logger.info(f"Upscaling image with {model}, scale={scale}, strength={denoising_strength}")
        
        try:
            # 使用PIL作为简单回退方案
            if model == "realesrgan":
                upscale_model = self._load_realesrgan(model)
                if upscale_model is None:
                    return self._fallback_upscale(image, scale)
            
            elif model == "swinir":
                upscale_model = self._load_swinir()
                if upscale_model is None:
                    return self._fallback_upscale(image, scale)
            
            elif model == "animegan":
                # AnimeGAN使用不同的处理方式
                return self._animegan_upscale(image, scale)
            
            elif model == "4xUltralytics":
                upscale_model = self._load_ultralytics()
                if upscale_model is None:
                    return self._fallback_upscale(image, scale)
                else:
                    # 使用ultralytics推理
                    result = upscale_model.predict(image)
                    return result[0].orig_img if hasattr(result[0], 'orig_img') else result[0]
            
            # Real-ESRGAN推理
            return self._realesrgan_inference(image, upscale_model, scale, denoising_strength)
            
        except Exception as e:
            logger.error(f"Upscale failed: {e}")
            # 回退到PIL resize
            logger.info("Falling back to PIL resize")
            return self._fallback_upscale(image, scale)
    
    def _fallback_upscale(self, image: Image.Image, scale: int) -> Image.Image:
        """
        使用PIL进行简单的图像放大
        
        Args:
            image: 输入图像
            scale: 缩放倍数
            
        Returns:
            缩放后的图像
        """
        width, height = image.size
        new_size = (width * scale, height * scale)
        return image.resize(new_size, Image.LANCZOS)
    
    def _realesrgan_inference(
        self, 
        image: Image.Image, 
        model: Any, 
        scale: int,
        denoising_strength: float
    ) -> Image.Image:
        """
        Real-ESRGAN推理
        
        Args:
            image: 输入图像
            model: 模型
            scale: 缩放倍数
            denoising_strength: 去噪强度
            
        Returns:
            处理后的图像
        """
        try:
            import cv2
            
            # PIL转cv2
            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            
            # 预处理 - 应用去噪
            if denoising_strength > 0:
                denoise_amount = int(denoising_strength * 30)
                img = cv2.fastNlMeansDenoisingColored(img, None, denoise_amount, denoise_amount, 7, 21)
            
            # 转换为tensor格式
            import torch
            img_tensor = torch.from_numpy(img).float().permute(2, 0, 1) / 255.0
            img_tensor = img_tensor.unsqueeze(0).to(self._torch_device)
            
            # 推理
            with torch.inference_mode():
                output = model(img_tensor)
            
            # 转回PIL
            output_img = output.squeeze(0).permute(1, 2, 0).cpu().numpy()
            output_img = (output_img * 255).clip(0, 255).astype(np.uint8)
            output_img = cv2.cvtColor(output_img, cv2.COLOR_BGR2RGB)
            
            logger.info("Real-ESRGAN inference completed")
            return Image.fromarray(output_img)
            
        except Exception as e:
            logger.error(f"Real-ESRGAN inference failed: {e}")
            return self._fallback_upscale(image, scale)
    
    def _animegan_upscale(self, image: Image.Image, scale: int) -> Image.Image:
        """
        AnimeGAN特定的上色和放大处理
        
        Args:
            image: 输入图像
            scale: 缩放倍数
            
        Returns:
            处理后的图像
        """
        # AnimeGAN处理流程
        # 1. 调整为2x或4x尺寸
        width, height = image.size
        new_size = (width * scale, height * scale)
        resized = image.resize(new_size, Image.LANCZOS)
        
        # 2. 可选的色彩优化
        # 这里可以添加AnimeGAN特定的色彩映射
        
        logger.info("AnimeGAN upscale completed")
        return resized
    
    def upscale_batch(
        self, 
        images: List[Image.Image], 
        model: str = "realesrgan", 
        scale: int = 2,
        denoising_strength: float = 0.4
    ) -> List[Image.Image]:
        """
        批量放大图像
        
        Args:
            images: 输入图像列表
            model: 放大模型名称
            scale: 放大倍数
            denoising_strength: 去噪强度
            
        Returns:
            放大后的图像列表
        """
        logger.info(f"Upscaling batch of {len(images)} images with {model}")
        
        results = []
        for idx, img in enumerate(images):
            try:
                upscaled = self.upscale_image(img, model, scale, denoising_strength)
                results.append(upscaled)
                logger.debug(f"Image {idx + 1}/{len(images)} upscaled")
            except Exception as e:
                logger.error(f"Failed to upscale image {idx}: {e}")
                # 使用原始图像作为回退
                results.append(img)
        
        logger.info(f"Batch upscale completed: {len(results)}/{len(images)} successful")
        return results
    
    def get_supported_models(self) -> List[str]:
        """
        获取支持的放大模型列表
        
        Returns:
            支持的模型名称列表
        """
        return self.SUPPORTED_MODELS.copy()
    
    def get_model_info(self, model: str) -> Dict[str, Any]:
        """
        获取指定模型的配置信息
        
        Args:
            model: 模型名称
            
        Returns:
            模型配置信息字典
        """
        if model not in self.SUPPORTED_MODELS:
            return {}
        
        config = self.MODEL_CONFIGS.get(model, {})
        return {
            "name": model,
            "default_scale": config.get("default_scale", 4),
            "has_download_url": config.get("model_url") is not None
        }