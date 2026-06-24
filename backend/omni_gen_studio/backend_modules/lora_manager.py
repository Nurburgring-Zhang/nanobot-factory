#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LoRA and ControlNet Management Module
LoRA管理和ControlNet支持模块
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LoRAConfig:
    """LoRA配置文件"""
    lora_path: str
    weight: float = 1.0
    clip_weight: float = 1.0

    def __post_init__(self):
        """验证参数范围"""
        if not 0.0 <= self.weight <= 2.0:
            logger.warning(f"LoRA weight {self.weight} out of range [0.0, 2.0], clamping")
            self.weight = max(0.0, min(2.0, self.weight))
        if not 0.0 <= self.clip_weight <= 2.0:
            logger.warning(f"CLIP weight {self.clip_weight} out of range [0.0, 2.0], clamping")
            self.clip_weight = max(0.0, min(2.0, self.clip_weight))


@dataclass
class ControlNetConfig:
    """ControlNet配置文件"""
    controlnet_path: str
    weight: float = 1.0
    guidance_start: float = 0.0
    guidance_end: float = 1.0
    preprocessor: str = "canny"

    def __post_init__(self):
        """验证参数范围"""
        if not 0.0 <= self.weight <= 2.0:
            self.weight = max(0.0, min(2.0, self.weight))
        if not 0.0 <= self.guidance_start <= 1.0:
            self.guidance_start = max(0.0, min(1.0, self.guidance_start))
        if not 0.0 <= self.guidance_end <= 1.0:
            self.guidance_end = max(0.0, min(1.0, self.guidance_end))
        if self.guidance_start > self.guidance_end:
            self.guidance_start, self.guidance_end = self.guidance_end, self.guidance_start


class LoRAManager:
    """LoRA管理器 - 负责LoRA的扫描、加载和管理"""

    SUPPORTED_FORMATS = {'.safetensors', '.ckpt', '.pt', '.pth'}

    def __init__(self, loras_dir: str, device: str = "cuda"):
        self.loras_dir = Path(loras_dir)
        self.device = device
        self._loaded_loras: Dict[str, Any] = {}
        self._max_loras = 3
        logger.info(f"LoRAManager initialized: dir={loras_dir}, device={device}, max_loras={self._max_loras}")

    def scan_loras(self) -> List[LoRAConfig]:
        """扫描LoRA目录获取可用的LoRA"""
        loras = []
        if not self.loras_dir.exists():
            logger.warning(f"LoRA directory not found: {self.loras_dir}")
            return loras

        logger.info(f"Scanning LoRA directory: {self.loras_dir}")
        for file_path in self.loras_dir.rglob("*"):
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext in self.SUPPORTED_FORMATS:
                    lora_config = LoRAConfig(lora_path=str(file_path), weight=1.0, clip_weight=1.0)
                    loras.append(lora_config)
                    logger.debug(f"Found LoRA: {file_path.name}")

        logger.info(f"Scan complete, found {len(loras)} LoRAs")
        return loras

    def apply_loras_to_pipeline(self, pipeline, loras: List[LoRAConfig]) -> Any:
        """将多个LoRA应用到pipeline（最多3个）"""
        if len(loras) > self._max_loras:
            logger.warning(f"LoRA count ({len(loras)}) exceeds maximum ({self._max_loras}), using first {self._max_loras}")
            loras = loras[:self._max_loras]

        if not loras:
            logger.info("No LoRAs to load")
            return pipeline

        logger.info(f"Applying {len(loras)} LoRAs to pipeline")
        sorted_loras = sorted(loras, key=lambda x: x.weight, reverse=True)

        for idx, lora_config in enumerate(sorted_loras):
            try:
                pipeline = self.apply_single_lora(pipeline, lora_config.lora_path, lora_config.weight, lora_config.clip_weight)
            except Exception as e:
                logger.error(f"Failed to apply LoRA: {lora_config.lora_path}, error: {e}")
                continue

        return pipeline

    def apply_single_lora(self, pipeline, lora_path: str, weight: float = 1.0, clip_weight: float = 1.0) -> Any:
        """将单个LoRA应用到pipeline"""
        try:
            from safetensors.torch import load_file
            import torch

            lora_path = Path(lora_path)
            if not lora_path.exists():
                raise FileNotFoundError(f"LoRA file not found: {lora_path}")

            ext = lora_path.suffix.lower()
            if ext == '.safetensors':
                lora_state_dict = load_file(str(lora_path), device=self.device)
            else:
                lora_state_dict = torch.load(lora_path, map_location=self.device)

            pipeline_has_lora = hasattr(pipeline, 'load_lora_weights')
            if pipeline_has_lora:
                pipeline.load_lora_weights(str(lora_path), weight_name=lora_path.name)
                if hasattr(pipeline, 'set_adapters'):
                    adapter_name = lora_path.stem
                    pipeline.set_adapters([adapter_name], adapter_weights=[weight])
                logger.info(f"LoRA loaded successfully: {lora_path.name}")
            else:
                pipeline = self._apply_lora_manually(pipeline, lora_state_dict, weight, clip_weight)
                logger.info(f"LoRA manually loaded: {lora_path.name}")

            self._loaded_loras[str(lora_path)] = {'weight': weight, 'clip_weight': clip_weight}
            return pipeline

        except ImportError as e:
            logger.error(f"Missing required library: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load LoRA: {lora_path}, error: {e}")
            raise

    def _apply_lora_manually(self, pipeline, lora_state_dict: Dict, weight: float, clip_weight: float) -> Any:
        """手动将LoRA权重应用到pipeline"""
        import torch

        unet = getattr(pipeline, 'unet', None)
        text_encoder = getattr(pipeline, 'text_encoder', None)

        if unet is not None:
            for key, value in lora_state_dict.items():
                if 'unet' in key.lower():
                    target_key = key.replace('lora_', '').replace('_lora', '')
                    if hasattr(unet, target_key):
                        target = getattr(unet, target_key)
                        if isinstance(target, torch.nn.Module) and hasattr(target, 'weight'):
                            if isinstance(target.weight, torch.Tensor):
                                target.weight.data += value.to(target.weight.device) * weight

        if text_encoder is not None and clip_weight != 1.0:
            for key, value in lora_state_dict.items():
                if 'text_encoder' in key.lower() or 'clip' in key.lower():
                    target_key = key.replace('lora_', '').replace('_lora', '')
                    if hasattr(text_encoder, target_key):
                        target = getattr(text_encoder, target_key)
                        if isinstance(target, torch.nn.Module) and hasattr(target, 'weight'):
                            if isinstance(target.weight, torch.Tensor):
                                target.weight.data += value.to(target.weight.device) * clip_weight

        return pipeline

    def remove_loras(self, pipeline) -> Any:
        """从pipeline中移除所有LoRA"""
        logger.info("Removing LoRAs from pipeline")
        try:
            if hasattr(pipeline, 'unload_lora_weights'):
                pipeline.unload_lora_weights()
                logger.info("LoRAs unloaded successfully")
            elif hasattr(pipeline, '_lora_scale'):
                pipeline._lora_scale = 1.0
            self._loaded_loras.clear()
            return pipeline
        except Exception as e:
            logger.error(f"Failed to remove LoRAs: {e}")
            return pipeline

    def get_lora_info(self, lora_path: str) -> Dict:
        """获取LoRA文件的详细信息"""
        lora_path = Path(lora_path)
        info = {
            "name": lora_path.name,
            "path": str(lora_path),
            "exists": lora_path.exists(),
            "size_mb": 0.0,
            "format": lora_path.suffix.lower(),
            "is_loaded": str(lora_path) in self._loaded_loras,
            "loaded_weight": None,
            "loaded_clip_weight": None
        }

        if lora_path.exists():
            try:
                info["size_mb"] = lora_path.stat().st_size / (1024 * 1024)
                if lora_path.suffix.lower() == '.safetensors':
                    try:
                        from safetensors import safe_open
                        with safe_open(lora_path, framework="pt", device="cpu") as f:
                            keys = f.keys()
                            info["lora_keys"] = len(keys)
                            info["has_unet_lora"] = any('unet' in k.lower() for k in keys)
                            info["has_clip_lora"] = any('clip' in k.lower() or 'text' in k.lower() for k in keys)
                    except:
                        pass
            except Exception as e:
                logger.error(f"Failed to get LoRA info: {e}")

        if str(lora_path) in self._loaded_loras:
            loaded_info = self._loaded_loras[str(lora_path)]
            info["loaded_weight"] = loaded_info.get('weight')
            info["loaded_clip_weight"] = loaded_info.get('clip_weight')

        return info


class ControlNetManager:
    """ControlNet管理器 - 负责ControlNet的扫描、加载和管理"""

    SUPPORTED_FORMATS = {'.safetensors', '.ckpt', '.pt', '.pth'}

    PREPROCESSOR_MAPPING = {
        "canny": "canny_edge",
        "depth": "depth_map",
        "pose": "openpose",
        "seg": "semantic_seg",
        "softedge": "soft_edge",
        "tile": "tile_resample",
        "lineart": "lineart",
        "mlsd": "mlsd",
    }

    def __init__(self, controlnets_dir: str, device: str = "cuda"):
        self.controlnets_dir = Path(controlnets_dir)
        self.device = device
        self._loaded_controlnets: Dict[str, Any] = {}
        logger.info(f"ControlNetManager initialized: dir={controlnets_dir}, device={device}")

    def scan_controlnets(self) -> List[ControlNetConfig]:
        """扫描ControlNet目录获取可用的ControlNet"""
        controlnets = []
        if not self.controlnets_dir.exists():
            logger.warning(f"ControlNet directory not found: {self.controlnets_dir}")
            return controlnets

        logger.info(f"Scanning ControlNet directory: {self.controlnets_dir}")
        for file_path in self.controlnets_dir.rglob("*"):
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext in self.SUPPORTED_FORMATS:
                    controlnet_config = ControlNetConfig(
                        controlnet_path=str(file_path),
                        weight=1.0,
                        guidance_start=0.0,
                        guidance_end=1.0,
                        preprocessor="canny"
                    )
                    controlnets.append(controlnet_config)
                    logger.debug(f"Found ControlNet: {file_path.name}")

        logger.info(f"Scan complete, found {len(controlnets)} ControlNets")
        return controlnets

    def load_controlnet(self, controlnet_path: str) -> Any:
        """加载ControlNet模型"""
        import torch

        controlnet_path = Path(controlnet_path)
        if not controlnet_path.exists():
            raise FileNotFoundError(f"ControlNet file not found: {controlnet_path}")

        cache_key = str(controlnet_path)
        if cache_key in self._loaded_controlnets:
            logger.info(f"Loading ControlNet from cache: {controlnet_path.name}")
            return self._loaded_controlnets[cache_key]

        logger.info(f"Loading ControlNet: {controlnet_path.name}")

        try:
            from diffusers import ControlNetModel

            controlnet = ControlNetModel.from_pretrained(
                str(controlnet_path),
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map=None if self.device == "cpu" else "auto"
            )

            self._loaded_controlnets[cache_key] = controlnet
            logger.info(f"ControlNet loaded successfully: {controlnet_path.name}")
            return controlnet

        except ImportError as e:
            logger.error(f"Missing required library: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to load ControlNet: {controlnet_path}, error: {e}")
            raise

    def apply_controlnet(self, pipeline, controlnet, config: ControlNetConfig) -> Any:
        """将ControlNet应用到pipeline"""
        try:
            from diffusers import StableDiffusionControlNetPipeline, StableDiffusionXLControlNetPipeline

            if isinstance(pipeline, (StableDiffusionControlNetPipeline, StableDiffusionXLControlNetPipeline)):
                if hasattr(pipeline, 'controlnet'):
                    try:
                        from diffusers import MultiControlNet
                        multi_controlnet = MultiControlNet([pipeline.controlnet, controlnet])
                        pipeline.controlnet = multi_controlnet
                        logger.info("Converted to MultiControlNet pipeline")
                    except ImportError:
                        logger.warning("MultiControlNet not available, overwriting existing ControlNet")
                        pipeline.controlnet = controlnet
                else:
                    pipeline.controlnet = controlnet
            else:
                logger.info("Converting regular pipeline to ControlNet pipeline")
                pipeline_class_name = pipeline.__class__.__name__

                if "XL" in pipeline_class_name or hasattr(pipeline, 'feature_extractor'):
                    target_class = StableDiffusionXLControlNetPipeline
                else:
                    target_class = StableDiffusionControlNetPipeline

                pipeline = target_class.from_pipe(pipeline, controlnet=controlnet, torch_dtype=pipeline.dtype if hasattr(pipeline, 'dtype') else None)

            if hasattr(pipeline, 'set_controlnet_params'):
                pipeline.set_controlnet_params(
                    guidance_scale=config.weight,
                    guidance_start=config.guidance_start,
                    guidance_end=config.guidance_end
                )

            logger.info(f"ControlNet applied: weight={config.weight}, guidance=[{config.guidance_start}, {config.guidance_end}], preprocessor={config.preprocessor}")
            return pipeline

        except ImportError as e:
            logger.error(f"Missing diffusers library: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to apply ControlNet: {e}")
            raise

    def get_controlnet_info(self, controlnet_path: str) -> Dict:
        """获取ControlNet文件的详细信息"""
        import torch

        controlnet_path = Path(controlnet_path)
        info = {
            "name": controlnet_path.name,
            "path": str(controlnet_path),
            "exists": controlnet_path.exists(),
            "size_mb": 0.0,
            "format": controlnet_path.suffix.lower(),
            "is_loaded": str(controlnet_path) in self._loaded_controlnets
        }

        if controlnet_path.exists():
            try:
                info["size_mb"] = controlnet_path.stat().st_size / (1024 * 1024)
            except Exception as e:
                logger.error(f"Failed to get ControlNet info: {e}")

        return info


# 全局实例管理
_lora_manager_instance: Optional[LoRAManager] = None
_controlnet_manager_instance: Optional[ControlNetManager] = None


def get_lora_manager(loras_dir: str = None, device: str = "cuda") -> LoRAManager:
    """获取LoRA管理器单例"""
    global _lora_manager_instance
    if _lora_manager_instance is None:
        if loras_dir is None:
            raise ValueError("loras_dir is required for first call to get_lora_manager")
        _lora_manager_instance = LoRAManager(loras_dir, device)
    return _lora_manager_instance


def get_controlnet_manager(controlnets_dir: str = None, device: str = "cuda") -> ControlNetManager:
    """获取ControlNet管理器单例"""
    global _controlnet_manager_instance
    if _controlnet_manager_instance is None:
        if controlnets_dir is None:
            raise ValueError("controlnets_dir is required for first call to get_controlnet_manager")
        _controlnet_manager_instance = ControlNetManager(controlnets_dir, device)
    return _controlnet_manager_instance


def reset_managers():
    """重置全局管理器实例"""
    global _lora_manager_instance, _controlnet_manager_instance
    _lora_manager_instance = None
    _controlnet_manager_instance = None
    logger.info("LoRA and ControlNet managers reset")
