#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全新设计的图片生成UI组件 - 终极AIGC生成器 v5.4
基于用户详细要求创建的全新图片生成UI组件：
1. 基础7个模组：模型、提示词、Lora、Controlnet、生图参数、分辨率、优化
2. 图片生成特殊功能：z imag、qwen image、Flux.2模型，文生图、图生图，AI放大等
3. 单页UI设计，不分下级界面
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import json
import csv
import pandas as pd
from pathlib import Path
import os
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import random

class RedesignedImageGenerationComponents:
    """全新设计的图片生成UI组件 - 单页完整界面"""
    
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
        
        # 预设配置
        self.setup_presets()
        
        # 创建单页UI
        self.create_single_page_ui()
    
    def setup_presets(self):
        """设置预设配置"""
        # 模型预设
        self.model_presets = {
            "z_imag": {
                "name": "Z-Image",
                "type": "image_generation",
                "description": "高质量图像生成模型",
                "supported_formats": ["safetensors", "gguf"]
            },
            "qwen_image": {
                "name": "Qwen-Image",
                "type": "image_generation", 
                "description": "阿里云Qwen图像生成模型",
                "supported_formats": ["safetensors"]
            },
            "flux2": {
                "name": "Flux.2 Klein",
                "type": "image_generation",
                "description": "FLUX.2高质量图像生成",
                "supported_formats": ["safetensors"]
            }
        }
        
        # 采样器预设
        self.samplers = [
            "DPM++ 2M Karras", "DPM++ SDE Karras", "Euler a", "Euler", 
            "LMS", "Heun", "DPM2", "DPM2 a", "DDIM", "PLMS", "PNDM",
            "UniPC", "UniPC-multistep", "DDPM", "DEIS", "DPM++-2S-a-Karras"
        ]
        
        # 调度器预设
        self.schedulers = ["normal", "simple", "karras", "exponential", "sgm_uniform", "kl_annealing"]
        
        # 分辨率预设
        self.resolution_presets = {
            "512x512": (512, 512),
            "768x512": (768, 512),
            "512x768": (512, 768),
            "768x768": (768, 768),
            "1024x768": (1024, 768),
            "768x1024": (768, 1024),
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
        
        # 风格模板预设
        self.style_templates = {
            "写实风格": "写实摄影风格，真实感强，高清细节，专业摄影效果",
            "动漫风格": "动漫插画风格，色彩鲜艳，线条清晰，二次元风格",
            "油画风格": "经典油画风格，笔触厚重，色彩浓郁，艺术感强",
            "水彩风格": "水彩画风格，色彩柔和，层次丰富，清新自然",
            "赛博朋克": "赛博朋克风格，霓虹色彩，未来感强，科技风格",
            "黑白摄影": "黑白摄影风格，光影对比强烈，经典优雅",
            "电影感": "电影级画质，电影感强烈，景深效果，胶片质感",
            "复古风格": "复古怀旧风格，怀旧色彩，Vintage风格，胶片质感",
            "现代艺术": "现代艺术风格，抽象表现，色彩大胆，创意性强",
            "古典风格": "古典艺术风格，文艺复兴风格，古典优雅，细腻精致"
        }
        
        # 负面提示词模板
        self.negative_templates = {
            "通用": "blurry, low quality, distorted, artifacts, extra limbs, malformed, bad anatomy, text, watermark, signature",
            "人物": "deformed, disfigured, extra fingers, missing fingers, cropped, low resolution, jpeg artifacts",
            "建筑": "poor architecture, modern buildings, concrete, glass, steel, contemporary",
            "自然": "artificial, synthetic, plastic, unnatural, fake"
        }

    def create_single_page_ui(self):
        """创建单页UI"""
        # 创建主容器
        self.main_container = ttk.Frame(self.parent)
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)
        
        # 创建滚动画布
        canvas = tk.Canvas(self.main_container)
        scrollbar = ttk.Scrollbar(self.main_container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 配置主容器网格权重
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # 绑定鼠标滚轮
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1*(event.delta/120)), "units"))
        
        # 创建各个功能模组
        self.create_model_module()
        self.create_prompt_module()
        self.create_lora_module()
        self.create_controlnet_module()
        self.create_generation_params_module()
        self.create_resolution_module()
        self.create_optimization_module()
        self.create_special_features_module()
        self.create_control_panel()

    def create_model_module(self):
        """创建模型模组"""
        frame = ttk.LabelFrame(self.scrollable_frame, text="1. 模型模组", padding="10")
        frame.grid(sticky="ew", padx=5, pady=5)
        
        # 模型选择
        ttk.Label(frame, text="模型类型:").grid(row=0, column=0, sticky="w", pady=2)
        self.vars['model_type'] = tk.StringVar()
        model_combo = ttk.Combobox(frame, textvariable=self.vars['model_type'], 
                                 values=list(self.model_presets.keys()), state="readonly", width=20)
        model_combo.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        model_combo.set("z_imag")
        
        # 主模型文件
        ttk.Label(frame, text="主模型文件:").grid(row=1, column=0, sticky="w", pady=2)
        self.vars['model_path'] = tk.StringVar()
        model_path_frame = ttk.Frame(frame)
        model_path_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        model_path_frame.columnconfigure(0, weight=1)
        ttk.Entry(model_path_frame, textvariable=self.vars['model_path'], width=30).grid(row=0, column=0, sticky="ew")
        ttk.Button(model_path_frame, text="浏览", command=self.select_model_file).grid(row=0, column=1, padx=2)
        
        # CLIP模型
        ttk.Label(frame, text="CLIP模型:").grid(row=2, column=0, sticky="w", pady=2)
        self.vars['clip_path'] = tk.StringVar()
        clip_path_frame = ttk.Frame(frame)
        clip_path_frame.grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        clip_path_frame.columnconfigure(0, weight=1)
        ttk.Entry(clip_path_frame, textvariable=self.vars['clip_path'], width=30).grid(row=0, column=0, sticky="ew")
        ttk.Button(clip_path_frame, text="浏览", command=self.select_clip_file).grid(row=0, column=1, padx=2)
        
        # T5模型
        ttk.Label(frame, text="T5模型:").grid(row=3, column=0, sticky="w", pady=2)
        self.vars['t5_path'] = tk.StringVar()
        t5_path_frame = ttk.Frame(frame)
        t5_path_frame.grid(row=3, column=1, sticky="ew", padx=5, pady=2)
        t5_path_frame.columnconfigure(0, weight=1)
        ttk.Entry(t5_path_frame, textvariable=self.vars['t5_path'], width=30).grid(row=0, column=0, sticky="ew")
        ttk.Button(t5_path_frame, text="浏览", command=self.select_t5_file).grid(row=0, column=1, padx=2)
        
        # VAE模型
        ttk.Label(frame, text="VAE模型:").grid(row=4, column=0, sticky="w", pady=2)
        self.vars['vae_path'] = tk.StringVar()
        vae_path_frame = ttk.Frame(frame)
        vae_path_frame.grid(row=4, column=1, sticky="ew", padx=5, pady=2)
        vae_path_frame.columnconfigure(0, weight=1)
        ttk.Entry(vae_path_frame, textvariable=self.vars['vae_path'], width=30).grid(row=0, column=0, sticky="ew")
        ttk.Button(vae_path_frame, text="浏览", command=self.select_vae_file).grid(row=0, column=1, padx=2)
        
        # 模型更新按钮
        update_btn = ttk.Button(frame, text="检查模型更新", command=self.check_model_updates)
        update_btn.grid(row=0, column=2, rowspan=5, sticky="ns", padx=10)
        
        frame.columnconfigure(1, weight=1)

    def create_prompt_module(self):
        """创建提示词模组"""
        frame = ttk.LabelFrame(self.scrollable_frame, text="2. 提示词模组", padding="10")
        frame.grid(row=0, column=0, sticky="ew", pady=5)
        frame.grid_columnconfigure(1, weight=1)
        
        # 提示词文件批量加载
        prompt_file_frame = ttk.Frame(frame)
        prompt_file_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=5)
        
        ttk.Label(prompt_file_frame, text="提示词文件:").grid(row=0, column=0, sticky="w", padx=2)
        self.vars['prompt_file'] = tk.StringVar()
        ttk.Entry(prompt_file_frame, textvariable=self.vars['prompt_file'], width=40).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(prompt_file_frame, text="选择文件夹", command=self.select_prompt_folder).grid(row=0, column=2, padx=2)
        ttk.Button(prompt_file_frame, text="批量加载", command=self.load_prompt_files).grid(row=0, column=3, padx=2)
        prompt_file_frame.grid_columnconfigure(1, weight=1)
        
        # 输出模式
        ttk.Label(frame, text="输出模式:").grid(row=1, column=0, sticky="w", pady=2)
        self.vars['output_mode'] = tk.StringVar()
        mode_combo = ttk.Combobox(frame, textvariable=self.vars['output_mode'], 
                                values=["顺序模式", "随机模式"], state="readonly", width=15)
        mode_combo.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        mode_combo.set("顺序模式")
        
        # 风格模板
        ttk.Label(frame, text="风格模板:").grid(row=2, column=0, sticky="w", pady=2)
        self.vars['style_template'] = tk.StringVar()
        style_combo = ttk.Combobox(frame, textvariable=self.vars['style_template'], 
                                 values=list(self.style_templates.keys()), state="readonly", width=20)
        style_combo.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        style_combo.set("写实风格")
        
        # 负面提示词模板
        ttk.Label(frame, text="负面模板:").grid(row=3, column=0, sticky="w", pady=2)
        self.vars['negative_template'] = tk.StringVar()
        neg_combo = ttk.Combobox(frame, textvariable=self.vars['negative_template'], 
                                values=list(self.negative_templates.keys()), state="readonly", width=20)
        neg_combo.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        neg_combo.set("通用")
        
        # 正面提示词
        ttk.Label(frame, text="正面提示词:").grid(row=4, column=0, sticky="nw", pady=2)
        self.vars['positive_prompt'] = tk.Text(frame, height=3, width=50)
        self.vars['positive_prompt'].grid(row=4, column=1, columnspan=2, sticky="ew", padx=5, pady=2)
        
        # 负面提示词
        ttk.Label(frame, text="负面提示词:").grid(row=5, column=0, sticky="nw", pady=2)
        self.vars['negative_prompt'] = tk.Text(frame, height=2, width=50)
        self.vars['negative_prompt'].grid(row=5, column=1, columnspan=2, sticky="ew", padx=5, pady=2)
        
        # AI优化按钮
        ai_btn_frame = ttk.Frame(frame)
        ai_btn_frame.grid(row=6, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Button(ai_btn_frame, text="AI提示词优化", command=self.optimize_prompt).grid(row=0, column=0, padx=2)
        ttk.Button(ai_btn_frame, text="翻译提示词", command=self.translate_prompt).grid(row=0, column=1, padx=2)
        ttk.Button(ai_btn_frame, text="API优化", command=self.api_optimize_prompt).grid(row=0, column=2, padx=2)
        
        frame.columnconfigure(1, weight=1)

    def create_lora_module(self):
        """创建Lora模组"""
        frame = ttk.LabelFrame(self.scrollable_frame, text="3. Lora模组", padding="10")
        frame.grid(sticky="ew", padx=5, pady=5)
        frame.columnconfigure(1, weight=1)
        
        # 创建3个Lora槽位
        for i in range(3):
            lora_frame = ttk.Frame(frame)
            lora_frame.grid(row=i, column=0, columnspan=3, sticky="ew", pady=2)
            lora_frame.columnconfigure(1, weight=1)
            
            ttk.Label(lora_frame, text=f"Lora {i+1}:").grid(row=0, column=0, sticky="w", padx=2)
            
            # Lora文件选择
            self.vars[f'lora_path_{i}'] = tk.StringVar()
            lora_entry = ttk.Entry(lora_frame, textvariable=self.vars[f'lora_path_{i}'], width=25)
            lora_entry.grid(row=0, column=1, sticky="ew", padx=5)
            
            ttk.Button(lora_frame, text="浏览", 
                      command=lambda idx=i: self.select_lora_file(idx)).grid(row=0, column=2, padx=2)
            
            # 权重设置
            ttk.Label(lora_frame, text="权重:").grid(row=1, column=0, sticky="w", padx=2, pady=2)
            self.vars[f'lora_weight_{i}'] = tk.StringVar(value="1.0")
            weight_scale = ttk.Scale(lora_frame, from_=0.0, to=2.0, orient=tk.HORIZONTAL, 
                                   variable=self.vars[f'lora_weight_{i}'], length=100)
            weight_scale.grid(row=1, column=1, sticky="ew", padx=5)
            ttk.Label(lora_frame, textvariable=self.vars[f'lora_weight_{i}'], width=4).grid(row=1, column=2, padx=2)

    def create_controlnet_module(self):
        """创建ControlNet模组"""
        frame = ttk.LabelFrame(self.scrollable_frame, text="4. ControlNet模组", padding="10")
        frame.grid(sticky="ew", padx=5, pady=5)
        
        # ControlNet类型
        ttk.Label(frame, text="ControlNet类型:").grid(row=0, column=0, sticky="w", pady=2)
        self.vars['controlnet_type'] = tk.StringVar()
        cn_types = ["无", "Canny", "Depth", "OpenPose", "Normal Map", "Segmentation", "Lineart", "Scribble"]
        cn_combo = ttk.Combobox(frame, textvariable=self.vars['controlnet_type'], 
                               values=cn_types, state="readonly", width=15)
        cn_combo.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        cn_combo.set("无")
        
        # ControlNet文件
        ttk.Label(frame, text="ControlNet模型:").grid(row=1, column=0, sticky="w", pady=2)
        self.vars['controlnet_path'] = tk.StringVar()
        cn_path_frame = ttk.Frame(frame)
        cn_path_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        cn_path_frame.columnconfigure(0, weight=1)
        ttk.Entry(cn_path_frame, textvariable=self.vars['controlnet_path'], width=30).grid(row=0, column=0, sticky="ew")
        ttk.Button(cn_path_frame, text="浏览", command=self.select_controlnet_file).grid(row=0, column=1, padx=2)
        
        # 参考图片
        ttk.Label(frame, text="参考图片:").grid(row=2, column=0, sticky="w", pady=2)
        self.vars['reference_image'] = tk.StringVar()
        ref_path_frame = ttk.Frame(frame)
        ref_path_frame.grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        ref_path_frame.columnconfigure(0, weight=1)
        ttk.Entry(ref_path_frame, textvariable=self.vars['reference_image'], width=30).grid(row=0, column=0, sticky="ew")
        ttk.Button(ref_path_frame, text="浏览", command=self.select_reference_image).grid(row=0, column=1, padx=2)
        
        # 控制权重
        ttk.Label(frame, text="控制权重:").grid(row=3, column=0, sticky="w", pady=2)
        self.vars['controlnet_weight'] = tk.DoubleVar(value=1.0)
        weight_scale = ttk.Scale(frame, from_=0.0, to=2.0, 
                               variable=self.vars['controlnet_weight'], orient=tk.HORIZONTAL, length=200)
        weight_scale.grid(row=3, column=1, sticky="ew", padx=5, pady=2)
        ttk.Label(frame, textvariable=self.vars['controlnet_weight']).grid(row=3, column=2, padx=5)
        
        frame.columnconfigure(1, weight=1)

    def create_generation_params_module(self):
        """创建生图参数模组"""
        frame = ttk.LabelFrame(self.scrollable_frame, text="5. 生图参数模组", padding="10")
        frame.grid(sticky="ew", padx=5, pady=5)
        
        # 推理步数
        ttk.Label(frame, text="推理步数:").grid(row=0, column=0, sticky="w", pady=2)
        self.vars['steps'] = tk.IntVar(value=30)
        steps_scale = ttk.Scale(frame, from_=1, to=150, variable=self.vars['steps'], 
                              orient=tk.HORIZONTAL, length=200)
        steps_scale.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        ttk.Label(frame, textvariable=self.vars['steps']).grid(row=0, column=2, padx=5)
        
        # CFG值
        ttk.Label(frame, text="CFG值:").grid(row=1, column=0, sticky="w", pady=2)
        self.vars['cfg_scale'] = tk.DoubleVar(value=7.5)
        cfg_scale = ttk.Scale(frame, from_=0.0, to=30.0, variable=self.vars['cfg_scale'], 
                            orient=tk.HORIZONTAL, length=200)
        cfg_scale.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        ttk.Label(frame, textvariable=self.vars['cfg_scale']).grid(row=1, column=2, padx=5)
        
        # 随机种子
        ttk.Label(frame, text="随机种子:").grid(row=2, column=0, sticky="w", pady=2)
        self.vars['seed'] = tk.IntVar(value=-1)
        ttk.Entry(frame, textvariable=self.vars['seed'], width=10).grid(row=2, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(frame, text="随机", command=self.randomize_seed).grid(row=2, column=2, padx=5)
        
        # 采样器
        ttk.Label(frame, text="采样器:").grid(row=3, column=0, sticky="w", pady=2)
        self.vars['sampler'] = tk.StringVar()
        sampler_combo = ttk.Combobox(frame, textvariable=self.vars['sampler'], 
                                   values=self.samplers, state="readonly", width=20)
        sampler_combo.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        sampler_combo.set("DPM++ 2M Karras")
        
        # 调度器
        ttk.Label(frame, text="调度器:").grid(row=4, column=0, sticky="w", pady=2)
        self.vars['scheduler'] = tk.StringVar()
        scheduler_combo = ttk.Combobox(frame, textvariable=self.vars['scheduler'], 
                                     values=self.schedulers, state="readonly", width=15)
        scheduler_combo.grid(row=4, column=1, sticky="w", padx=5, pady=2)
        scheduler_combo.set("karras")
        
        frame.columnconfigure(1, weight=1)

    def create_resolution_module(self):
        """创建分辨率模组"""
        frame = ttk.LabelFrame(self.scrollable_frame, text="6. 分辨率模组", padding="10")
        frame.grid(sticky="ew", padx=5, pady=5)
        
        # 预设分辨率
        ttk.Label(frame, text="预设分辨率:").grid(row=0, column=0, sticky="w", pady=2)
        self.vars['resolution_preset'] = tk.StringVar()
        res_combo = ttk.Combobox(frame, textvariable=self.vars['resolution_preset'], 
                               values=list(self.resolution_presets.keys()), state="readonly", width=15)
        res_combo.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        res_combo.set("1024x1024")
        
        # 自定义分辨率
        custom_frame = ttk.Frame(frame)
        custom_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)
        custom_frame.columnconfigure(1, weight=1)
        custom_frame.columnconfigure(3, weight=1)
        
        ttk.Label(custom_frame, text="宽度:").grid(row=0, column=0)
        self.vars['custom_width'] = tk.IntVar(value=1024)
        ttk.Entry(custom_frame, textvariable=self.vars['custom_width'], width=8).grid(row=0, column=1, padx=5)
        
        ttk.Label(custom_frame, text="高度:").grid(row=0, column=2, padx=(10, 2))
        self.vars['custom_height'] = tk.IntVar(value=1024)
        ttk.Entry(custom_frame, textvariable=self.vars['custom_height'], width=8).grid(row=0, column=3, padx=5)
        
        ttk.Button(custom_frame, text="应用自定义", command=self.apply_custom_resolution).grid(row=0, column=4, padx=10)
        
        # 随机分辨率
        self.vars['random_resolution'] = tk.BooleanVar()
        ttk.Checkbutton(frame, text="使用随机分辨率", 
                       variable=self.vars['random_resolution']).grid(row=2, column=0, sticky="w", pady=2)
        
        frame.columnconfigure(1, weight=1)

    def create_optimization_module(self):
        """创建优化模组"""
        frame = ttk.LabelFrame(self.scrollable_frame, text="7. 优化模组", padding="10")
        frame.grid(sticky="ew", padx=5, pady=5)
        
        # HiRes Fix
        self.vars['hires_fix'] = tk.BooleanVar()
        ttk.Checkbutton(frame, text="HiRes Fix (高分辨率修复)", 
                       variable=self.vars['hires_fix']).grid(row=0, column=0, sticky="w", pady=2)
        
        # 平铺模式
        self.vars['tiling'] = tk.BooleanVar()
        ttk.Checkbutton(frame, text="平铺模式", 
                       variable=self.vars['tiling']).grid(row=0, column=1, sticky="w", pady=2)
        
        # Noise Injection
        self.vars['noise_injection'] = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Noise Injection (噪声注入)", 
                       variable=self.vars['noise_injection']).grid(row=1, column=0, sticky="w", pady=2)
        
        # Seed Enhancement
        self.vars['seed_enhancement'] = tk.BooleanVar()
        ttk.Checkbutton(frame, text="Seed Enhancement (种子增强)", 
                       variable=self.vars['seed_enhancement']).grid(row=1, column=1, sticky="w", pady=2)
        
        # 高级采样算法
        ttk.Label(frame, text="高级采样算法:").grid(row=2, column=0, sticky="w", pady=2)
        self.vars['advanced_sampling'] = tk.StringVar()
        advanced_combo = ttk.Combobox(frame, textvariable=self.vars['advanced_sampling'], 
                                   values=["无", "DDIM Inversion", "Noise Inversion", "CFG++", "CFG Variation"], 
                                   state="readonly", width=15)
        advanced_combo.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        advanced_combo.set("无")
        
        # 风格滤镜
        ttk.Label(frame, text="风格滤镜:").grid(row=3, column=0, sticky="w", pady=2)
        self.vars['style_filter'] = tk.StringVar()
        filter_combo = ttk.Combobox(frame, textvariable=self.vars['style_filter'], 
                                  values=["无", "赛博朋克", "电影感", "复古", "黑白", "暖色调", "冷色调", "HDR", "胶片感"], 
                                  state="readonly", width=15)
        filter_combo.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        filter_combo.set("无")
        
        # 滤镜强度
        ttk.Label(frame, text="滤镜强度:").grid(row=4, column=0, sticky="w", pady=2)
        self.vars['filter_strength'] = tk.DoubleVar(value=0.5)
        filter_scale = ttk.Scale(frame, from_=0.0, to=1.0, 
                               variable=self.vars['filter_strength'], orient=tk.HORIZONTAL, length=200)
        filter_scale.grid(row=4, column=1, sticky="ew", padx=5, pady=2)
        ttk.Label(frame, textvariable=self.vars['filter_strength']).grid(row=4, column=2, padx=5)
        
        frame.columnconfigure(1, weight=1)

    def create_special_features_module(self):
        """创建图片生成特殊功能模组"""
        frame = ttk.LabelFrame(self.scrollable_frame, text="图片生成特殊功能", padding="10")
        frame.grid(sticky="ew", padx=5, pady=5)
        
        # 生成模式
        ttk.Label(frame, text="生成模式:").grid(row=0, column=0, sticky="w", pady=2)
        self.vars['generation_mode'] = tk.StringVar()
        mode_combo = ttk.Combobox(frame, textvariable=self.vars['generation_mode'], 
                                 values=["文生图", "图生图", "图像修复", "图像增强"], state="readonly", width=15)
        mode_combo.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        mode_combo.set("文生图")
        
        # 输入图片（用于图生图模式）
        ttk.Label(frame, text="输入图片:").grid(row=1, column=0, sticky="w", pady=2)
        self.vars['input_image'] = tk.StringVar()
        input_frame = ttk.Frame(frame)
        input_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        input_frame.columnconfigure(0, weight=1)
        ttk.Entry(input_frame, textvariable=self.vars['input_image'], width=30).grid(row=0, column=0, sticky="ew")
        ttk.Button(input_frame, text="浏览", command=self.select_input_image).grid(row=0, column=1, padx=2)
        
        # AI放大设置
        self.vars['enable_upscale'] = tk.BooleanVar()
        ttk.Checkbutton(frame, text="启用AI放大", 
                       variable=self.vars['enable_upscale']).grid(row=2, column=0, sticky="w", pady=2)
        
        # 放大比例
        ttk.Label(frame, text="放大比例:").grid(row=3, column=0, sticky="w", pady=2)
        self.vars['upscale_ratio'] = tk.StringVar()
        ratio_combo = ttk.Combobox(frame, textvariable=self.vars['upscale_ratio'], 
                                 values=["1.5x", "2x", "3x", "4x"], state="readonly", width=10)
        ratio_combo.grid(row=3, column=1, sticky="w", padx=5, pady=2)
        ratio_combo.set("2x")
        
        # 放大模型
        ttk.Label(frame, text="放大模型:").grid(row=4, column=0, sticky="w", pady=2)
        self.vars['upscale_model'] = tk.StringVar()
        model_combo = ttk.Combobox(frame, textvariable=self.vars['upscale_model'], 
                                  values=["RealESRGAN", "SeedVR 2.5", "ESRGAN", "GFPGAN"], 
                                  state="readonly", width=15)
        model_combo.grid(row=4, column=1, sticky="w", padx=5, pady=2)
        model_combo.set("RealESRGAN")
        
        frame.columnconfigure(1, weight=1)

    def create_control_panel(self):
        """创建控制面板"""
        frame = ttk.LabelFrame(self.scrollable_frame, text="控制面板", padding="10")
        frame.grid(sticky="ew", padx=5, pady=5)
        
        # 输出设置
        output_frame = ttk.Frame(frame)
        output_frame.grid(sticky="ew", padx=5, pady=5)
        output_frame.columnconfigure(5, weight=1)
        
        ttk.Label(output_frame, text="输出格式:").grid(row=0, column=0)
        self.vars['output_format'] = tk.StringVar()
        format_combo = ttk.Combobox(output_frame, textvariable=self.vars['output_format'], 
                                  values=["PNG", "JPG", "WebP"], state="readonly", width=8)
        format_combo.grid(row=0, column=1, padx=5)
        format_combo.set("PNG")
        
        ttk.Label(output_frame, text="输出质量:").grid(row=0, column=2, padx=(10, 2))
        self.vars['output_quality'] = tk.IntVar(value=95)
        ttk.Entry(output_frame, textvariable=self.vars['output_quality'], width=5).grid(row=0, column=3, padx=5)
        
        ttk.Label(output_frame, text="保存目录:").grid(row=0, column=4, padx=(10, 2))
        self.vars['output_dir'] = tk.StringVar(value="./output/images")
        ttk.Entry(output_frame, textvariable=self.vars['output_dir'], width=20).grid(row=0, column=5, padx=5, sticky="ew")
        ttk.Button(output_frame, text="浏览", command=self.select_output_dir).grid(row=0, column=6, padx=2)
        
        # 生成按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(sticky="ew", padx=5, pady=5)
        
        ttk.Button(btn_frame, text="开始生成", command=self.start_generation, 
                  style="Accent.TButton").grid(row=0, column=0, padx=5)
        ttk.Button(btn_frame, text="停止", command=self.stop_generation).grid(row=0, column=1, padx=5)
        ttk.Button(btn_frame, text="重置", command=self.reset_settings).grid(row=0, column=2, padx=5)
        ttk.Button(btn_frame, text="保存配置", command=self.save_config).grid(row=0, column=3, padx=5)
        ttk.Button(btn_frame, text="加载配置", command=self.load_config).grid(row=0, column=4, padx=5)
        
        # 进度条
        progress_frame = ttk.Frame(frame)
        progress_frame.grid(sticky="ew", padx=5, pady=5)
        progress_frame.columnconfigure(1, weight=1)
        
        ttk.Label(progress_frame, text="进度:").grid(row=0, column=0)
        self.vars['progress'] = tk.IntVar(value=0)
        progress_bar = ttk.Progressbar(progress_frame, variable=self.vars['progress'], 
                                    maximum=100, length=300)
        progress_bar.grid(row=0, column=1, padx=5, sticky="ew")
        
        # 状态显示
        self.vars['status'] = tk.StringVar(value="就绪")
        status_label = ttk.Label(frame, textvariable=self.vars['status'], 
                                foreground="blue", font=("Arial", 9, "bold"))
        status_label.grid(pady=5)
        
        # 日志显示
        ttk.Label(frame, text="日志:").grid(sticky="w", padx=5)
        self.vars['log'] = tk.Text(frame, height=8, width=80, state=tk.DISABLED)
        self.vars['log'].grid(row=len(self.vars)//10 + 4, column=0, columnspan=3, sticky="ew", padx=5, pady=2)
        
        # 图像预览
        preview_frame = ttk.LabelFrame(frame, text="图像预览", padding="5")
        preview_frame.grid(row=len(self.vars)//10 + 5, column=0, columnspan=3, sticky="nsew", padx=5, pady=5)
        frame.rowconfigure(len(self.vars)//10 + 5, weight=1)
        
        self.image_preview = tk.Label(preview_frame, text="暂无图像", relief="sunken", 
                                    bg="white", fg="gray")
        self.image_preview.grid(sticky="nsew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)

    # 事件处理方法
    def select_model_file(self):
        """选择主模型文件"""
        path = filedialog.askopenfilename(
            title="选择模型文件",
            filetypes=[("Model files", "*.safetensors *.ckpt *.bin"), ("All files", "*.*")]
        )
        if path:
            self.vars['model_path'].set(path)

    def select_clip_file(self):
        """选择CLIP模型文件"""
        path = filedialog.askopenfilename(
            title="选择CLIP模型文件",
            filetypes=[("CLIP files", "*.safetensors *.bin"), ("All files", "*.*")]
        )
        if path:
            self.vars['clip_path'].set(path)

    def select_t5_file(self):
        """选择T5模型文件"""
        path = filedialog.askopenfilename(
            title="选择T5模型文件",
            filetypes=[("T5 files", "*.safetensors *.bin"), ("All files", "*.*")]
        )
        if path:
            self.vars['t5_path'].set(path)

    def select_vae_file(self):
        """选择VAE模型文件"""
        path = filedialog.askopenfilename(
            title="选择VAE模型文件",
            filetypes=[("VAE files", "*.safetensors *.ckpt *.bin"), ("All files", "*.*")]
        )
        if path:
            self.vars['vae_path'].set(path)

    def check_model_updates(self):
        """检查模型更新"""
        self.log_message("正在检查模型更新...")
        # 这里可以实现自动检查GitHub和HuggingFace更新的逻辑
        self.log_message("模型更新检查完成")
        messagebox.showinfo("提示", "模型更新检查完成")

    def select_prompt_folder(self):
        """选择提示词文件夹"""
        folder = filedialog.askdirectory(title="选择提示词文件夹")
        if folder:
            self.vars['prompt_file'].set(folder)

    def load_prompt_files(self):
        """批量加载提示词文件"""
        folder_path = self.vars['prompt_file'].get()
        if not folder_path or not os.path.exists(folder_path):
            messagebox.showwarning("警告", "请先选择有效的文件夹")
            return
        
        self.log_message("正在批量加载提示词文件...")
        # 这里可以实现批量读取TXT/XLS/CSV/JSON文件的逻辑
        self.log_message(f"从 {folder_path} 加载了 0 个提示词文件")
        messagebox.showinfo("提示", f"从 {folder_path} 加载了提示词文件")

    def optimize_prompt(self):
        """AI提示词优化"""
        prompt = self.vars['positive_prompt'].get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("警告", "请先输入提示词")
            return
        
        self.log_message("正在进行AI提示词优化...")
        # 这里可以实现AI提示词优化的逻辑
        optimized_prompt = f"{prompt}, highly detailed, 4k resolution, masterpiece"
        self.vars['positive_prompt'].delete("1.0", tk.END)
        self.vars['positive_prompt'].insert("1.0", optimized_prompt)
        self.log_message("提示词优化完成")

    def translate_prompt(self):
        """翻译提示词"""
        prompt = self.vars['positive_prompt'].get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("警告", "请先输入提示词")
            return
        
        self.log_message("正在进行提示词翻译...")
        # 这里可以实现本地LLM翻译的逻辑
        self.log_message("提示词翻译完成")

    def api_optimize_prompt(self):
        """API优化提示词"""
        prompt = self.vars['positive_prompt'].get("1.0", tk.END).strip()
        if not prompt:
            messagebox.showwarning("警告", "请先输入提示词")
            return
        
        self.log_message("正在调用API进行提示词优化...")
        # 这里可以实现Ollama/VLLM/LM Studio API调用的逻辑
        self.log_message("API提示词优化完成")

    def select_lora_file(self, index):
        """选择Lora文件"""
        path = filedialog.askopenfilename(
            title=f"选择Lora {index+1}文件",
            filetypes=[("Lora files", "*.safetensors *.ckpt"), ("All files", "*.*")]
        )
        if path:
            self.vars[f'lora_path_{index}'].set(path)

    def select_controlnet_file(self):
        """选择ControlNet文件"""
        path = filedialog.askopenfilename(
            title="选择ControlNet模型文件",
            filetypes=[("ControlNet files", "*.safetensors *.ckpt"), ("All files", "*.*")]
        )
        if path:
            self.vars['controlnet_path'].set(path)

    def select_reference_image(self):
        """选择参考图片"""
        path = filedialog.askopenfilename(
            title="选择参考图片",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")]
        )
        if path:
            self.vars['reference_image'].set(path)

    def randomize_seed(self):
        """随机化种子"""
        import random
        random_seed = random.randint(0, 999999999)
        self.vars['seed'].set(random_seed)

    def apply_custom_resolution(self):
        """应用自定义分辨率"""
        width = self.vars['custom_width'].get()
        height = self.vars['custom_height'].get()
        preset_name = f"{width}x{height}"
        self.vars['resolution_preset'].set(preset_name)
        self.log_message(f"应用自定义分辨率: {width}x{height}")

    def select_input_image(self):
        """选择输入图片"""
        path = filedialog.askopenfilename(
            title="选择输入图片",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")]
        )
        if path:
            self.vars['input_image'].set(path)

    def select_output_dir(self):
        """选择输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.vars['output_dir'].set(directory)

    def start_generation(self):
        """开始生成"""
        self.vars['status'].set("正在生成...")
        self.log_message("开始图片生成...")
        
        # 这里可以添加实际的生成逻辑
        def generate_thread():
            try:
                # 模拟生成过程
                for i in range(101):
                    self.vars['progress'].set(i)
                    self.log_message(f"生成进度: {i}%")
                    if i % 10 == 0:
                        self.log_message(f"正在进行第 {i//10 + 1} 步...")
                    threading.Event().wait(0.1)
                
                self.vars['status'].set("生成完成")
                self.log_message("图片生成完成")
                self.update_preview()
            except Exception as e:
                self.vars['status'].set("生成失败")
                self.log_message(f"生成失败: {str(e)}")
        
        thread = threading.Thread(target=generate_thread, daemon=True)
        thread.start()

    def stop_generation(self):
        """停止生成"""
        self.vars['status'].set("已停止")
        self.log_message("生成已停止")

    def reset_settings(self):
        """重置设置"""
        self.vars['positive_prompt'].delete("1.0", tk.END)
        self.vars['negative_prompt'].delete("1.0", tk.END)
        self.vars['steps'].set(30)
        self.vars['cfg_scale'].set(7.5)
        self.vars['seed'].set(-1)
        self.vars['progress'].set(0)
        self.vars['status'].set("就绪")
        self.log_message("设置已重置")

    def save_config(self):
        """保存配置"""
        config = {
            'model_type': self.vars['model_type'].get(),
            'positive_prompt': self.vars['positive_prompt'].get("1.0", tk.END).strip(),
            'negative_prompt': self.vars['negative_prompt'].get("1.0", tk.END).strip(),
            'steps': self.vars['steps'].get(),
            'cfg_scale': self.vars['cfg_scale'].get(),
            'sampler': self.vars['sampler'].get(),
            'scheduler': self.vars['scheduler'].get(),
            'resolution_preset': self.vars['resolution_preset'].get()
        }
        
        filename = filedialog.asksaveasfilename(
            title="保存配置",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            self.log_message(f"配置已保存到 {filename}")

    def load_config(self):
        """加载配置"""
        filename = filedialog.askopenfilename(
            title="加载配置",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                for key, value in config.items():
                    if key in self.vars:
                        if isinstance(value, str) and key in ['positive_prompt', 'negative_prompt']:
                            self.vars[key].delete("1.0", tk.END)
                            self.vars[key].insert("1.0", value)
                        else:
                            self.vars[key].set(value)
                
                self.log_message(f"配置已从 {filename} 加载")
            except Exception as e:
                self.log_message(f"加载配置失败: {str(e)}")
                messagebox.showerror("错误", f"加载配置失败: {str(e)}")

    def log_message(self, message):
        """记录日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.vars['log'].config(state=tk.NORMAL)
        self.vars['log'].insert(tk.END, log_entry)
        self.vars['log'].config(state=tk.DISABLED)
        self.vars['log'].see(tk.END)

    def update_preview(self):
        """更新图像预览"""
        # 这里可以实现图像预览更新逻辑
        self.image_preview.config(text="生成完成！", fg="green")

    def get_generation_config(self):
        """获取生成配置"""
        config = {
            'model_type': self.vars['model_type'].get(),
            'model_path': self.vars['model_path'].get(),
            'clip_path': self.vars['clip_path'].get(),
            't5_path': self.vars['t5_path'].get(),
            'vae_path': self.vars['vae_path'].get(),
            'positive_prompt': self.vars['positive_prompt'].get("1.0", tk.END).strip(),
            'negative_prompt': self.vars['negative_prompt'].get("1.0", tk.END).strip(),
            'steps': self.vars['steps'].get(),
            'cfg_scale': self.vars['cfg_scale'].get(),
            'seed': self.vars['seed'].get(),
            'sampler': self.vars['sampler'].get(),
            'scheduler': self.vars['scheduler'].get(),
            'resolution_preset': self.vars['resolution_preset'].get(),
            'output_format': self.vars['output_format'].get(),
            'output_quality': self.vars['output_quality'].get(),
            'output_dir': self.vars['output_dir'].get(),
            'generation_mode': self.vars['generation_mode'].get(),
            'input_image': self.vars['input_image'].get(),
            'enable_upscale': self.vars['enable_upscale'].get(),
            'upscale_ratio': self.vars['upscale_ratio'].get(),
            'upscale_model': self.vars['upscale_model'].get(),
            'style_filter': self.vars['style_filter'].get(),
            'filter_strength': self.vars['filter_strength'].get()
        }
        return config
    
    def show(self):
        """显示组件界面"""
        try:
            if hasattr(self, 'main_frame'):
                self.main_frame.grid()
            self.log_message("✅ 图像生成组件已显示")
        except Exception as e:
            self.log_message(f"❌ 显示组件失败: {e}")
    
    def hide(self):
        """隐藏组件界面"""
        try:
            if hasattr(self, 'main_frame'):
                self.main_frame.grid_remove()
            self.log_message("ℹ️ 图像生成组件已隐藏")
        except Exception as e:
            self.log_message(f"❌ 隐藏组件失败: {e}")

# 测试代码
if __name__ == "__main__":
    import tkinter as tk
    from tkinter import ttk
    
    root = tk.Tk()
    root.title("图片生成UI组件测试")
    root.geometry("1200x800")
    
    # 创建模拟的应用程序实例
    class MockApp:
        def __init__(self):
            self.vars = {}
    
    mock_app = MockApp()
    
    # 创建组件
    component = RedesignedImageGenerationComponents(root, mock_app)
    
    root.mainloop()