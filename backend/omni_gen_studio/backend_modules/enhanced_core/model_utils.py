#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OmniGen Studio - LoRA管理器
支持加载多个LoRA模型
"""

import os
import torch
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class LoRAManager:
    """LoRA管理器"""

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.loaded_loras = []

    def load_lora(self, lora_path: str, weight: float = 1.0) -> bool:
        """加载LoRA"""
        try:
            from peft import LoraConfig, PeftModel
            from diffusers import UNet2DConditionModel

            logger.info(f"📥 加载LoRA: {lora_path} (权重: {weight})")

            # 检查LoRA文件
            if not os.path.exists(lora_path):
                logger.error(f"❌ LoRA文件不存在: {lora_path}")
                return False

            # 加载LoRA到UNet
            if hasattr(self.pipeline, 'unet'):
                self.pipeline.unet = PeftModel.from_pretrained(
                    self.pipeline.unet,
                    lora_path
                )

            # 设置权重
            if weight != 1.0:
                # 调整LoRA权重
                for name, param in self.pipeline.unet.named_parameters():
                    if 'lora' in name:
                        param.data *= weight

            self.loaded_loras.append({
                "path": lora_path,
                "weight": weight
            })

            logger.info(f"✅ LoRA加载成功")
            return True

        except Exception as e:
            logger.error(f"❌ LoRA加载失败: {e}")
            return False

    def unload_lora(self, index: int = -1) -> bool:
        """卸载LoRA"""
        try:
            if not self.loaded_loras:
                logger.warning("⚠️ 没有已加载的LoRA")
                return False

            if hasattr(self.pipeline, 'unet'):
                # 重新加载原始模型
                self.pipeline.unet = self.pipeline.unet.base_model.model

            if index < 0:
                self.loaded_loras.clear()
            else:
                self.loaded_loras.pop(index)

            logger.info("✅ LoRA已卸载")
            return True

        except Exception as e:
            logger.error(f"❌ LoRA卸载失败: {e}")
            return False

    def get_loaded_loras(self) -> List[Dict[str, Any]]:
        """获取已加载的LoRA"""
        return self.loaded_loras


class ControlNetManager:
    """ControlNet管理器"""

    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.controlnets = []

    def load_controlnet(self, controlnet_path: str,
                       processor_type: str = "canny") -> bool:
        """加载ControlNet"""
        try:
            from diffusers import ControlNetModel

            logger.info(f"📥 加载ControlNet: {controlnet_path} (类型: {processor_type})")

            # 加载ControlNet模型
            if os.path.exists(controlnet_path):
                controlnet = ControlNetModel.from_pretrained(
                    controlnet_path,
                    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32
                )
            else:
                # 使用默认ControlNet
                if processor_type == "canny":
                    controlnet = ControlNetModel.from_pretrained(
                        "lllyasviel/sd-controlnet-canny"
                    )
                elif processor_type == "depth":
                    controlnet = ControlNetModel.from_pretrained(
                        "lllyasviel/sd-controlnet-depth"
                    )
                elif processor_type == "pose":
                    controlnet = ControlNetModel.from_pretrained(
                        "lllyasviel/sd-controlnet-openpose"
                    )
                elif processor_type == "normal":
                    controlnet = ControlNetModel.from_pretrained(
                        "lllyasviel/sd-controlnet-normal"
                    )
                else:
                    controlnet = ControlNetModel.from_pretrained(
                        "lllyasviel/sd-controlnet-canny"
                    )

            controlnet.to("cuda" if torch.cuda.is_available() else "cpu")

            self.controlnets.append({
                "model": controlnet,
                "type": processor_type,
                "weight": 1.0
            })

            logger.info(f"✅ ControlNet加载成功")
            return True

        except Exception as e:
            logger.error(f"❌ ControlNet加载失败: {e}")
            return False

    def apply_controlnet(self, control_image, weight: float = 1.0,
                       guidance_scale: float = 1.0):
        """应用ControlNet"""
        if not self.controlnets:
            logger.warning("⚠️ 没有加载的ControlNet")
            return control_image

        # 使用MultiControlNet
        return control_image

    def set_controlnet_weight(self, index: int, weight: float):
        """设置ControlNet权重"""
        if 0 <= index < len(self.controlnets):
            self.controlnets[index]["weight"] = weight
            logger.info(f"✅ ControlNet {index} 权重设置为 {weight}")

    def remove_controlnet(self, index: int):
        """移除ControlNet"""
        if 0 <= index < len(self.controlnets):
            removed = self.controlnets.pop(index)
            logger.info(f"✅ 已移除ControlNet: {removed['type']}")

    def get_controlnets_info(self):
        """获取所有ControlNet信息"""
        return [
            {"type": cn["type"], "weight": cn["weight"]}
            for cn in self.controlnets
        ]


class ControlNetPreprocessor:
    """ControlNet预处理器"""

    # 预处理器类型
    PREPROCESSORS = {
        "canny": "CannyEdgePreprocessor",
        "depth": "DepthMapPreprocessor",
        "normal": "NormalMapPreprocessor",
        "pose": "OpenPosePreprocessor",
        "seg": "SemanticSegmentationPreprocessor",
        "lineart": "LineartPreprocessor",
        "scribble": "ScribblePreprocessor"
    }

    def __init__(self):
        self.preprocessor_cache = {}

    def preprocess(self, image, processor_type: str) -> Any:
        """预处理图像"""
        try:
            from controlnet_aux import (
                CannyEdgeDetector,
                DepthDetector,
                NormalMapDetector,
                OpenPoseDetector,
                LineartDetector,
                ScribbleDetector
            )
            from PIL import Image
            import numpy as np

            logger.info(f"🖼️ 预处理图像: {processor_type}")

            # 转换为PIL Image
            if not isinstance(image, Image.Image):
                if isinstance(image, np.ndarray):
                    image = Image.fromarray(image)
                else:
                    raise ValueError("不支持的图像格式")

            # 预处理
            if processor_type == "canny":
                preprocessor = CannyEdgeDetector()
                result = preprocessor(image, low_threshold=100, high_threshold=200)

            elif processor_type == "depth":
                preprocessor = DepthDetector.from_pretrained("lllyasviel/Annotators")
                result = preprocessor(image)

            elif processor_type == "normal":
                preprocessor = NormalMapDetector.from_pretrained("lllyasviel/Annotators")
                result = preprocessor(image)

            elif processor_type == "pose":
                preprocessor = OpenPoseDetector.from_pretrained("lllyasviel/Annotators")
                result = preprocessor(image)

            elif processor_type == "lineart":
                preprocessor = LineartDetector.from_pretrained("lllyasviel/Annotators")
                result = preprocessor(image)

            elif processor_type == "scribble":
                preprocessor = ScribbleDetector()
                result = preprocessor(image)

            elif processor_type == "seg":
                # 使用ADE20K语义分割
                from controlnet_aux import SemanticSegmentationDetector
                preprocessor = SemanticSegmentationDetector.from_pretrained("lllyasviel/Annotators")
                result = preprocessor(image)

            else:
                logger.warning(f"⚠️ 未知的预处理器类型: {processor_type}")
                return image

            logger.info(f"✅ 预处理完成")
            return result

        except ImportError as e:
            logger.warning(f"⚠️ controlnet_aux未安装: {e}")
            # 返回原图作为后备
            return image
        except Exception as e:
            logger.error(f"❌ 预处理失败: {e}")
            return image


class PromptProcessor:
    """提示词处理器"""

    def __init__(self):
        self.positive_templates = {
            "默认": "",
            "写实": "photorealistic, detailed, realistic lighting, high quality, 8k",
            "动漫": "anime style, illustration, vibrant colors, clean lines, anime artwork",
            "油画": "oil painting style, painterly, artistic, rich colors, brushstrokes",
            "水彩": "watercolor style, soft colors, flowing, delicate, artistic",
            "赛博朋克": "cyberpunk, neon lights, futuristic, dark atmosphere, sci-fi",
            "奇幻": "fantasy, magical, epic, detailed fantasy world, mystical",
            "电影感": "cinematic, film grain, cinematic lighting, dramatic, movie scene"
        }

        self.negative_templates = {
            "默认": "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry",
            "写实": "cartoon, anime, painting, drawing, illustration, 3d render",
            "动漫": "realistic, photorealistic, photo, 3d render",
            "油画": "photo, photograph, realistic",
            "水彩": "digital art, 3d render",
            "赛博朋克": "natural, rustic, medieval",
            "奇幻": "modern, realistic, sci-fi",
            "电影感": "amateur, low quality"
        }

    def add_style_template(self, prompt: str, style: str) -> str:
        """添加风格模板"""
        if style in self.positive_templates:
            template = self.positive_templates[style]
            if template:
                return f"{prompt}, {template}"
        return prompt

    def add_negative_template(self, negative_prompt: str, style: str) -> str:
        """添加负面模板"""
        if style in self.negative_templates:
            template = self.negative_templates[style]
            if template:
                if negative_prompt:
                    return f"{negative_prompt}, {template}"
                return template
        return negative_prompt

    def load_prompts_from_file(self, file_path: str) -> List[str]:
        """从文件加载提示词"""
        prompts = []

        try:
            ext = os.path.splitext(file_path)[1].lower()

            if ext == '.txt':
                with open(file_path, 'r', encoding='utf-8') as f:
                    prompts = [line.strip() for line in f if line.strip()]

            elif ext in ['.json', '.jsonl']:
                import json
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        prompts = [item if isinstance(item, str) else item.get('prompt', '')
                                 for item in data]
                    elif isinstance(data, dict):
                        prompts = [data.get('prompt', '')]

            elif ext in ['.csv']:
                import pandas as pd
                df = pd.read_csv(file_path)
                prompts = df.iloc[:, 0].tolist()

            elif ext in ['.xlsx', '.xls']:
                import pandas as pd
                df = pd.read_excel(file_path)
                prompts = df.iloc[:, 0].tolist()

            logger.info(f"✅ 从文件加载了 {len(prompts)} 条提示词")
            return prompts

        except Exception as e:
            logger.error(f"❌ 提示词文件加载失败: {e}")
            return []

    def optimize_prompt(self, prompt: str, api_type: str = "ollama",
                       api_url: str = "http://localhost:11434") -> str:
        """AI优化提示词"""
        try:
            import requests

            if api_type == "ollama":
                response = requests.post(
                    f"{api_url}/api/generate",
                    json={
                        "model": "llama2",
                        "prompt": f"Improve this prompt for AI image generation, make it more detailed and descriptive: {prompt}",
                        "stream": False
                    },
                    timeout=30
                )
                if response.status_code == 200:
                    result = response.json()
                    return result.get('response', prompt)

            elif api_type == "vllm":
                response = requests.post(
                    f"{api_url}/v1/completions",
                    json={
                        "prompt": f"Improve this prompt for AI image generation: {prompt}",
                        "max_tokens": 200
                    },
                    timeout=30
                )
                if response.status_code == 200:
                    result = response.json()
                    return result.get('choices', [{}])[0].get('text', prompt)

            return prompt

        except Exception as e:
            logger.error(f"❌ 提示词优化失败: {e}")
            return prompt

    def translate_prompt(self, prompt: str, target_lang: str = "en") -> str:
        """翻译提示词"""
        # 简单的翻译实现
        # 实际可以使用Google Translate API或其他翻译服务
        try:
            import requests

            # 使用免费的翻译API
            if target_lang == "en":
                # 简单的中英翻译
                return prompt  # TODO: 实现真正的翻译

            return prompt

        except Exception as e:
            logger.error(f"❌ 提示词翻译失败: {e}")
            return prompt


class ImageOptimizer:
    """图像优化器"""

    def __init__(self):
        self.upscale_models = {}
        self.noise_injection_enabled = False
        self.seed_enhance_enabled = False

    def apply_noise_injection(self, image: Image.Image, noise_level: float = 0.1) -> Image.Image:
        """噪点注入 - 增加图像噪点以增强细节"""
        try:
            import numpy as np
            from PIL import ImageEnhance

            logger.info(f"🖼️ 应用噪点注入: level={noise_level}")

            # 转换为numpy数组
            img_array = np.array(image).astype(np.float32)

            # 添加高斯噪点
            noise = np.random.normal(0, noise_level * 255, img_array.shape)
            img_array = np.clip(img_array + noise, 0, 255).astype(np.uint8)

            # 转换回PIL
            result = Image.fromarray(img_array)

            # 轻微锐化以保持细节
            enhancer = ImageEnhance.Sharpness(result)
            result = enhancer.enhance(1.1)

            logger.info("✅ 噪点注入完成")
            return result

        except Exception as e:
            logger.error(f"❌ 噪点注入失败: {e}")
            return image

    def apply_seed_enhance(self, image: Image.Image, strength: float = 0.5) -> Image.Image:
        """种子增强 - 增强图像的细节和纹理"""
        try:
            from PIL import ImageFilter, ImageEnhance
            import numpy as np

            logger.info(f"🖼️ 应用种子增强: strength={strength}")

            # 应用USM锐化
            result = image.filter(ImageFilter.UnsharpMask(
                radius=2,
                percent=int(150 * strength),
                threshold=3
            ))

            # 增强对比度
            enhancer = ImageEnhance.Contrast(result)
            result = enhancer.enhance(1.0 + strength * 0.2)

            # 增强细节
            enhancer = ImageEnhance.Sharpness(result)
            result = enhancer.enhance(1.0 + strength * 0.3)

            logger.info("✅ 种子增强完成")
            return result

        except Exception as e:
            logger.error(f"❌ 种子增强失败: {e}")
            return image

    def upscale_image(self, image: Image.Image, scale: float = 2.0,
                    model: str = "RealESRGAN") -> Image.Image:
        """AI放大图像"""
        try:
            logger.info(f"🖼️ 正在放大图像: {scale}x ({model})")

            if model == "RealESRGAN":
                return self._upscale_realesrgan(image, scale)
            elif model == "SeedVR":
                return self._upscale_seedvr(image, scale)
            else:
                # 使用PIL进行简单放大
                new_size = (int(image.width * scale), int(image.height * scale))
                return image.resize(new_size, Image.LANCZOS)

        except Exception as e:
            logger.error(f"❌ 图像放大失败: {e}")
            return image

    def _upscale_realesrgan(self, image: Image.Image, scale: float) -> Image.Image:
        """使用RealESRGAN放大"""
        try:
            from realesrgan_ncnn_vulkan import RealESRGAN

            if "realesrgan" not in self.upscale_models:
                self.upscale_models["realesrgan"] = RealESRGAN(gpu_id=0)

            result = self.upscale_models["realesrgan"].process(image, scale)
            return result

        except ImportError:
            logger.warning("⚠️ RealESRGAN未安装，使用PIL放大")
            new_size = (int(image.width * scale), int(image.height * scale))
            return image.resize(new_size, Image.LANCZOS)

    def _upscale_seedvr(self, image: Image.Image, scale: float) -> Image.Image:
        """使用SeedVR放大"""
        # TODO: 实现SeedVR放大
        logger.info("⚠️ SeedVR放大未实现，使用RealESRGAN")
        return self._upscale_realesrgan(image, scale)

    def apply_style_filter(self, image: Image.Image, style: str) -> Image.Image:
        """应用风格滤镜"""
        try:
            from PIL import ImageFilter, ImageEnhance

            if style == "清新":
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(1.1)
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(1.15)
                image = image.filter(ImageFilter.SMOOTH)

            elif style == "复古":
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(0.8)
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.1)
                image = image.filter(ImageFilter.SMOOTH_MORE)

            elif style == "电影感":
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.2)
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(0.9)
                # 添加暗角效果（简化）
                image = image.filter(ImageFilter.VIGNETTE)

            elif style == "HDR":
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.3)
                enhancer = ImageEnhance.Sharpness(image)
                image = enhancer.enhance(1.5)

            elif style == "黑白":
                image = image.convert('L').convert('RGB')

            elif style == "赛博朋克":
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(1.5)
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.3)
                # 添加青色/品红色调（简化）

            elif style == "动漫":
                image = image.filter(ImageFilter.SHARPEN)
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(1.2)
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(1.3)

            elif style == "油画":
                image = image.filter(ImageFilter.MedianFilter(size=5))
                enhancer = ImageEnhance.Color(image)
                image = enhancer.enhance(1.2)

            elif style == "水彩":
                image = image.filter(ImageFilter.GaussianBlur(radius=2))
                enhancer = ImageEnhance.Brightness(image)
                image = enhancer.enhance(1.1)
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(0.9)

            logger.info(f"✅ 风格滤镜应用: {style}")
            return image

        except Exception as e:
            logger.error(f"❌ 风格滤镜失败: {e}")
            return image


# 导入PIL
from PIL import Image
