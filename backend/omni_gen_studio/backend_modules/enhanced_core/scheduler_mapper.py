#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OmniGen Studio - 采样器与调度器映射
将UI选项映射到Diffusers调度器
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SchedulerMapper:
    """采样器到调度器的映射"""

    # UI采样器名称到Diffusers调度器的映射
    SAMPLER_TO_SCHEDULER = {
        # Euler系列
        "euler": {
            "scheduler": "EulerDiscreteScheduler",
            "kwargs": {}
        },
        "euler a": {
            "scheduler": "EulerAncestralDiscreteScheduler",
            "kwargs": {}
        },
        "euler_a": {
            "scheduler": "EulerAncestralDiscreteScheduler",
            "kwargs": {}
        },

        # DPM系列
        "dpm++ 2m": {
            "scheduler": "DPMSolverMultistepScheduler",
            "kwargs": {
                "algorithm_type": "dpmsolver++",
                "use_karras_sigmas": False
            }
        },
        "dpm++ 2m karras": {
            "scheduler": "DPMSolverMultistepScheduler",
            "kwargs": {
                "algorithm_type": "dpmsolver++",
                "use_karras_sigmas": True
            }
        },
        "dpm++ sde": {
            "scheduler": "DPMSolverSinglestepScheduler",
            "kwargs": {
                "algorithm_type": "dpmsolver++"
            }
        },
        "dpm++ sde karras": {
            "scheduler": "DPMSolverSinglestepScheduler",
            "kwargs": {
                "algorithm_type": "dpmsolver++",
                "use_karras_sigmas": True
            }
        },
        "dpm2": {
            "scheduler": "KDPM2DiscreteScheduler",
            "kwargs": {}
        },
        "dpm2 karras": {
            "scheduler": "KDPM2DiscreteScheduler",
            "kwargs": {
                "use_karras_sigmas": True
            }
        },
        "dpm2 a": {
            "scheduler": "KDPM2AncestralDiscreteScheduler",
            "kwargs": {}
        },
        "dpm2_a": {
            "scheduler": "KDPM2AncestralDiscreteScheduler",
            "kwargs": {}
        },
        "dpm2 a karras": {
            "scheduler": "KDPM2AncestralDiscreteScheduler",
            "kwargs": {
                "use_karras_sigmas": True
            }
        },

        # UniPC
        "unipc": {
            "scheduler": "UniPCMultistepScheduler",
            "kwargs": {}
        },
        "unipc cf": {
            "scheduler": "UniPCMultistepScheduler",
            "kwargs": {
                "use_cf_guidance": True
            }
        },

        # DDIM
        "ddim": {
            "scheduler": "DDIMScheduler",
            "kwargs": {}
        },

        # LCM (Latent Consistency Models)
        "lcm": {
            "scheduler": "LCMScheduler",
            "kwargs": {}
        },

        # PNDM
        "pndm": {
            "scheduler": "PNDMScheduler",
            "kwargs": {}
        },

        # LMS
        "lms": {
            "scheduler": "LMSDiscreteScheduler",
            "kwargs": {}
        },
        "lms karras": {
            "scheduler": "LMSDiscreteScheduler",
            "kwargs": {
                "use_karras_sigmas": True
            }
        },

        # Heun
        "heun": {
            "scheduler": "HeunDiscreteScheduler",
            "kwargs": {}
        },

        # DDPMScheduler
        "ddpm": {
            "scheduler": "DDPMScheduler",
            "kwargs": {}
        },
    }

    # 调度器配置
    SCHEDULER_CONFIGS = {
        "normal": {
            "beta_start": 0.00085,
            "beta_end": 0.012,
            "beta_schedule": "scaled_linear"
        },
        "simple": {
            "beta_start": 0.00085,
            "beta_end": 0.012,
            "beta_schedule": "linear"
        },
        "karras": {
            "beta_start": 0.00085,
            "beta_end": 0.012,
            "beta_schedule": "scaled_linear",
            "use_karras_sigmas": True
        },
        "exponential": {
            "beta_start": 0.00085,
            "beta_end": 0.012,
            "beta_schedule": "exponential"
        },
        "ddim": {
            "beta_start": 0.00085,
            "beta_end": 0.012,
            "beta_schedule": "scaled_linear",
            "clip_sample": False
        },
    }

    def __init__(self):
        self.current_scheduler = None

    def get_scheduler(self, pipeline, sampler: str, scheduler_type: str = "normal"):
        """获取调度器"""
        try:
            from diffusers import (
                # Euler
                EulerDiscreteScheduler,
                EulerAncestralDiscreteScheduler,
                # DPM
                DPMSolverMultistepScheduler,
                DPMSolverSinglestepScheduler,
                KDPM2DiscreteScheduler,
                KDPM2AncestralDiscreteScheduler,
                # UniPC
                UniPCMultistepScheduler,
                # DDIM
                DDIMScheduler,
                # LCM
                LCMScheduler,
                # Others
                PNDMScheduler,
                LMSDiscreteScheduler,
                HeunDiscreteScheduler,
                DDPMScheduler
            )

            # 标准化采样器名称
            sampler_lower = sampler.lower().strip()

            # 获取调度器配置
            scheduler_config = self.SCHEDULER_CONFIGS.get(scheduler_type.lower(),
                                                           self.SCHEDULER_CONFIGS["normal"])

            # 获取调度器映射
            sampler_map = self.SAMPLER_TO_SCHEDULER.get(sampler_lower,
                                                          self.SAMPLER_TO_SCHEDULER["euler"])

            scheduler_class_name = sampler_map["scheduler"]
            scheduler_kwargs = sampler_map.get("kwargs", {})
            scheduler_kwargs.update(scheduler_config)

            # 获取调度器类
            scheduler_class = eval(scheduler_class_name)

            # 创建调度器
            scheduler = scheduler_class.from_config(pipeline.scheduler.config, **scheduler_kwargs)

            logger.info(f"✅ 创建调度器: {scheduler_class_name} ({scheduler_type})")
            return scheduler

        except Exception as e:
            logger.error(f"❌ 创建调度器失败: {e}")
            return None

    def get_available_samplers(self) -> list:
        """获取所有可用的采样器"""
        return list(self.SAMPLER_TO_SCHEDULER.keys())

    def get_available_schedulers(self) -> list:
        """获取所有可用的调度器类型"""
        return list(self.SCHEDULER_CONFIGS.keys())


class AdvancedScheduler:
    """高级调度器功能"""

    @staticmethod
    def apply_noise_injection(latents, noise_level: float = 0.1):
        """噪点注入"""
        import torch
        try:
            if noise_level > 0:
                # 生成随机噪点
                noise = torch.randn_like(latents) * noise_level
                latents = latents + noise
                logger.info(f"✅ 已应用噪点注入: level={noise_level}")
            return latents
        except Exception as e:
            logger.error(f"❌ 噪点注入失败: {e}")
            return latents

    @staticmethod
    def apply_seed_enhancement(latents, seed: int, strength: float = 0.5):
        """种子增强 - 通过调整潜在空间的噪声模式来增强生成稳定性"""
        import torch
        try:
            if strength > 0 and seed >= 0:
                # 创建确定性的噪声
                generator = torch.Generator(device=latents.device)
                generator.manual_seed(seed)

                # 生成增强噪声
                enhanced_noise = torch.randn_like(latents, generator=generator) * strength

                # 混合原始潜空间和增强潜空间
                latents = latents * (1 - strength) + enhanced_noise * strength

                logger.info(f"✅ 已应用种子增强: seed={seed}, strength={strength}")
            return latents
        except Exception as e:
            logger.error(f"❌ 种子增强失败: {e}")
            return latents

    @staticmethod
    def apply_freeu(bypass: bool = True, b1: float = 1.2, b2: float = 1.4, s1: float = 0.9, s2: float = 0.2):
        """FreeU - 增强生成质量的后处理"""
        # FreeU是一种后处理技术，可以提升生成质量
        # 这个实现是一个简化版本
        logger.info(f"✅ FreeU配置: bypass={bypass}, b1={b1}, b2={b2}, s1={s1}, s2={s2}")
        return {
            "enabled": bypass,
            "b1": b1,
            "b2": b2,
            "s1": s1,
            "s2": s2
        }


# 全局调度器映射器
_scheduler_mapper = None


def get_scheduler_mapper() -> SchedulerMapper:
    """获取调度器映射器实例"""
    global _scheduler_mapper
    if _scheduler_mapper is None:
        _scheduler_mapper = SchedulerMapper()
    return _scheduler_mapper
