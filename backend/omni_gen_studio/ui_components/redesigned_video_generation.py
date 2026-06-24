#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全新设计的视频生成UI组件 - 终极AIGC生成器 v5.4
基于用户详细要求创建的全新视频生成UI组件：
1. 基础7个模组：模型、提示词、Lora、Controlnet、生图参数、分辨率、优化
2. 视频生成特殊功能：wan2.2、ltx-2模型支持、CFG调节、降噪步数、生成帧率/帧数、首帧/首尾帧/视频参考、AI放大、提示词保存
3. 单页UI设计，不分下级界面
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import json
import threading
from typing import Dict, List, Any, Optional
import requests
import asyncio
import numpy as np

class RedesignedVideoGenerationComponents:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        
        # 视频生成相关变量
        self.first_frame_path = None
        self.last_frame_path = None
        self.reference_video_path = None
        self.output_dir = tk.StringVar(value="./video_output")
        self.output_format = tk.StringVar(value="MP4")
        self.output_quality = tk.IntVar(value=95)
        self.save_prompt = tk.BooleanVar(value=True)
        self.upscaling_enabled = tk.BooleanVar(value=False)
        self.upscale_ratio = tk.DoubleVar(value=2.0)
        
        # 模型相关
        self.model_var = tk.StringVar(value="wan2.2")
        self.model_list = [
            "wan2.2", "ltx-2", "sora", "runway_ml", "stable_video_diffusion", 
            "animate_diff", "videofy", "pika_labs"
        ]
        
        # 提示词相关
        self.positive_prompt = tk.StringVar()
        self.negative_prompt = tk.StringVar()
        self.prompt_templates = {}
        self.negative_templates = {}
        
        # LoRA相关
        self.lora_files = []
        self.lora_weights = []
        
        # ControlNet相关
        self.controlnet_files = []
        self.controlnet_enabled = tk.BooleanVar(value=False)
        self.controlnet_weight = tk.DoubleVar(value=0.8)
        
        # 视频生成参数
        self.steps = tk.IntVar(value=50)
        self.cfg_scale = tk.DoubleVar(value=7.0)
        self.seed = tk.IntVar(value=-1)
        self.fps = tk.IntVar(value=24)
        self.frame_count = tk.IntVar(value=120)
        self.sampler = tk.StringVar(value="DPM++ 2M Karras")
        self.scheduler = tk.StringVar(value="Karras")
        
        # 分辨率
        self.resolution_preset = tk.StringVar(value="1280x720")
        self.custom_width = tk.IntVar(value=1280)
        self.custom_height = tk.IntVar(value=720)
        self.resolution_presets = {
            "1280x720": (1280, 720),
            "720x1280": (720, 1280),
            "1920x1080": (1920, 1080),
            "1080x1920": (1080, 1920),
            "640x480": (640, 480),
            "480x640": (480, 640),
            "256x256": (256, 256),
            "512x512": (512, 512),
            "随机分辨率": None
        }
        
        # 优化选项
        self.noise_injection = tk.BooleanVar(value=False)
        self.noise_ratio = tk.DoubleVar(value=0.1)
        self.seed_enhance = tk.BooleanVar(value=False)
        self.advanced_sampling = tk.BooleanVar(value=True)
        self.advanced_cfg = tk.BooleanVar(value=True)
        
        # 视频生成特殊功能
        self.reference_mode = tk.StringVar(value="首帧参考")
        self.motion_strength = tk.DoubleVar(value=0.8)
        self.temporal_consistency = tk.BooleanVar(value=True)
        self.motion_preservation = tk.DoubleVar(value=0.7)
        
        self.create_ui()
    
    def create_ui(self):
        """创建视频生成UI"""
        # 主滚动框架
        main_frame = tk.Frame(self.parent, bg="#f0f0f0")
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)
        
        # 创建滚动区域
        canvas = tk.Canvas(main_frame, bg="#f0f0f0")
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#f0f0f0")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 滚动区域布局
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        # 鼠标滚轮绑定
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # 设置滚动框架的grid布局
        scrollable_frame.grid_rowconfigure(0, weight=1)
        scrollable_frame.grid_columnconfigure(0, weight=1)
        
        # 模块计数器
        module_row = 0
        
        # === 基础7个模组 ===
        self.create_model_module(scrollable_frame, module_row)
        module_row += 1
        self.create_prompt_module(scrollable_frame, module_row)
        module_row += 1
        self.create_lora_module(scrollable_frame, module_row)
        module_row += 1
        self.create_controlnet_module(scrollable_frame, module_row)
        module_row += 1
        self.create_generation_params_module(scrollable_frame, module_row)
        module_row += 1
        self.create_resolution_module(scrollable_frame, module_row)
        module_row += 1
        self.create_optimization_module(scrollable_frame, module_row)
        module_row += 1
        
        # === 视频生成特殊功能模组 ===
        self.create_video_generation_special_module(scrollable_frame, module_row)
        module_row += 1
        
        # === 输出设置模组 ===
        self.create_output_module(scrollable_frame, module_row)
        module_row += 1
        
        # === 生成控制按钮 ===
        self.create_action_buttons(scrollable_frame, module_row)
    
    def create_model_module(self, parent, row):
        """模型模组"""
        module_frame = ttk.LabelFrame(parent, text="🔧 模型模组", padding=15)
        module_frame.grid(row=row, column=0, sticky="ew", pady=(0, 15))
        
        # 模型选择
        ttk.Label(module_frame, text="选择模型:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        model_combo = ttk.Combobox(module_frame, textvariable=self.model_var, 
                                 values=self.model_list, width=25)
        model_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        # 自定义模型路径
        ttk.Label(module_frame, text="自定义模型:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        custom_model_frame = ttk.Frame(module_frame)
        custom_model_frame.grid(row=1, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        self.custom_model_path = tk.StringVar()
        custom_model_frame.grid_columnconfigure(0, weight=1)
        ttk.Entry(custom_model_frame, textvariable=self.custom_model_path, width=30).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(custom_model_frame, text="浏览", 
                  command=self.browse_custom_model).grid(row=0, column=1)
        
        # 自动更新按钮
        ttk.Button(module_frame, text="🔄 更新模型列表", 
                  command=self.update_model_list).grid(row=0, column=2, padx=(20, 0), pady=5)
        
        # GitHub/HuggingFace搜索
        search_frame = ttk.LabelFrame(module_frame, text="🔍 在线搜索模型", padding=10)
        search_frame.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0))
        
        self.github_search_var = tk.StringVar()
        search_frame.grid_columnconfigure(1, weight=1)
        ttk.Entry(search_frame, textvariable=self.github_search_var, width=40).grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ttk.Button(search_frame, text="搜索GitHub", 
                  command=self.search_github_models).grid(row=0, column=1, sticky="w")
        ttk.Button(search_frame, text="搜索HuggingFace", 
                  command=self.search_huggingface_models).grid(row=0, column=2, sticky="w", padx=(5, 0))
        
        module_frame.columnconfigure(1, weight=1)
    
    def create_prompt_module(self, parent, row):
        """提示词模组"""
        module_frame = ttk.LabelFrame(parent, text="📝 提示词模组", padding=15)
        module_frame.grid(row=row, column=0, sticky="ew", pady=(0, 15))
        
        # 正向提示词
        ttk.Label(module_frame, text="正向提示词:").grid(row=0, column=0, sticky=tk.NW, pady=5)
        
        positive_frame = ttk.Frame(module_frame)
        positive_frame.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=(10, 0))
        
        # 预设正向风格模板
        ttk.Label(positive_frame, text="风格模板:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        style_template_frame = ttk.Frame(positive_frame)
        style_template_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        style_template_frame.grid_columnconfigure(1, weight=1)
        
        self.positive_style_var = tk.StringVar(value="默认")
        style_combo = ttk.Combobox(style_template_frame, textvariable=self.positive_style_var, width=20)
        style_combo.grid(row=0, column=0, sticky="w")
        ttk.Button(style_template_frame, text="应用", 
                  command=self.apply_positive_style).grid(row=0, column=1, sticky="w", padx=(5, 0))
        ttk.Button(style_template_frame, text="编辑", 
                  command=self.edit_positive_styles).grid(row=0, column=2, sticky="w", padx=(5, 0))
        
        # 正向提示词输入
        self.positive_text = scrolledtext.ScrolledText(positive_frame, height=4, width=50)
        self.positive_text.grid(row=2, column=0, columnspan=2, sticky="ew")
        
        # 批量提示词导入
        batch_frame = ttk.Frame(positive_frame)
        batch_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        batch_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Button(batch_frame, text="📁 批量导入TXT", 
                  command=self.import_batch_prompts).grid(row=0, column=0, sticky="w")
        ttk.Button(batch_frame, text="📊 导入Excel/CSV", 
                  command=self.import_excel_prompts).grid(row=0, column=1, sticky="w", padx=(5, 0))
        
        # AI优化按钮
        ttk.Button(batch_frame, text="🤖 AI优化提示词", 
                  command=self.optimize_prompt).grid(row=0, column=2, sticky="e")
        
        # 翻译按钮
        ttk.Button(batch_frame, text="🌐 翻译为中文", 
                  command=self.translate_prompt).grid(row=0, column=3, sticky="e", padx=(5, 0))
        
        # 负向提示词
        ttk.Label(module_frame, text="负向提示词:").grid(row=1, column=0, sticky=tk.NW, pady=(10, 5))
        
        negative_frame = ttk.Frame(module_frame)
        negative_frame.grid(row=1, column=1, sticky=tk.EW, pady=(10, 5), padx=(10, 0))
        
        # 预设负向风格模板
        ttk.Label(negative_frame, text="负面模板:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        neg_template_frame = ttk.Frame(negative_frame)
        neg_template_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        neg_template_frame.grid_columnconfigure(1, weight=1)
        
        self.negative_style_var = tk.StringVar(value="默认")
        neg_style_combo = ttk.Combobox(neg_template_frame, textvariable=self.negative_style_var, width=20)
        neg_style_combo.grid(row=0, column=0, sticky="w")
        ttk.Button(neg_template_frame, text="应用", 
                  command=self.apply_negative_style).grid(row=0, column=1, sticky="w", padx=(5, 0))
        ttk.Button(neg_template_frame, text="编辑", 
                  command=self.edit_negative_styles).grid(row=0, column=2, sticky="w", padx=(5, 0))
        
        # 负向提示词输入
        self.negative_text = scrolledtext.ScrolledText(negative_frame, height=3, width=50)
        self.negative_text.grid(row=2, column=0, columnspan=2, sticky="ew")
        
        module_frame.columnconfigure(1, weight=1)
    
    def create_lora_module(self, parent, row):
        """LoRA模组"""
        module_frame = ttk.LabelFrame(parent, text="🎨 LoRA模组", padding=15)
        module_frame.grid(row=row, column=0, sticky="ew", pady=(0, 15))
        
        # LoRA列表
        lora_frame = ttk.Frame(module_frame)
        lora_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        lora_frame.grid_columnconfigure(1, weight=1)
        
        # 添加LoRA按钮
        ttk.Button(lora_frame, text="➕ 添加LoRA", 
                  command=self.add_lora).grid(row=0, column=0, sticky="w", pady=5)
        ttk.Button(lora_frame, text="🗑️ 清除所有", 
                  command=self.clear_loras).grid(row=0, column=1, sticky="w", padx=(10, 0), pady=5)
        
        # LoRA列表显示
        list_frame = ttk.Frame(module_frame)
        list_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        list_frame.grid_columnconfigure(0, weight=1)
        
        self.lora_tree = ttk.Treeview(list_frame, columns=("权重"), show="tree headings")
        self.lora_tree.heading("#0", text="LoRA文件")
        self.lora_tree.heading("权重", text="权重")
        self.lora_tree.column("权重", width=80)
        self.lora_tree.grid(row=0, column=0, sticky="ew")
        
        # 支持最多3个LoRA的提示
        ttk.Label(module_frame, text="支持最多3个LoRA，可调节权重", 
                 foreground="gray").grid(row=2, column=0, sticky="w", pady=(5, 0))
    
    def create_controlnet_module(self, parent, row):
        """ControlNet模组"""
        module_frame = ttk.LabelFrame(parent, text="🎛️ ControlNet模组", padding=15)
        module_frame.grid(row=row, column=0, sticky="ew", pady=(0, 15))
        
        # 启用ControlNet
        ttk.Checkbutton(module_frame, text="启用ControlNet", 
                       variable=self.controlnet_enabled).grid(row=0, column=0, sticky="w", pady=5)
        
        if self.controlnet_enabled.get():
            # ControlNet文件选择
            ttk.Button(module_frame, text="📁 选择ControlNet文件", 
                      command=self.select_controlnet_files).grid(row=1, column=0, sticky="w", pady=5)
            
            # 控制权重
            weight_frame = ttk.Frame(module_frame)
            weight_frame.grid(row=2, column=0, sticky="ew", pady=5)
            weight_frame.grid_columnconfigure(1, weight=1)
            
            ttk.Label(weight_frame, text="控制权重:").grid(row=0, column=0, sticky="w")
            ttk.Scale(weight_frame, from_=0.0, to=1.0, variable=self.controlnet_weight, 
                     orient=tk.HORIZONTAL, length=200).grid(row=0, column=1, sticky="ew", padx=(10, 0))
            ttk.Label(weight_frame, textvariable=self.controlnet_weight).grid(row=0, column=2, sticky="w", padx=(10, 0))
    
    def create_generation_params_module(self, parent, row):
        """生图参数模组"""
        module_frame = ttk.LabelFrame(parent, text="⚙️ 视频生成参数", padding=15)
        module_frame.grid(row=row, column=0, sticky="ew", pady=(0, 15))
        
        # 参数网格
        params_frame = ttk.Frame(module_frame)
        params_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        params_frame.grid_columnconfigure(1, weight=1)
        
        # 降噪步数
        ttk.Label(params_frame, text="降噪步数:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Scale(params_frame, from_=10, to=100, variable=self.steps, 
                 orient=tk.HORIZONTAL, length=150).grid(row=0, column=1, padx=(10, 0), pady=5)
        ttk.Label(params_frame, textvariable=self.steps).grid(row=0, column=2, padx=(10, 0), pady=5)
        
        # CFG比例
        ttk.Label(params_frame, text="CFG比例:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Scale(params_frame, from_=1.0, to=20.0, variable=self.cfg_scale, 
                 orient=tk.HORIZONTAL, length=150).grid(row=1, column=1, padx=(10, 0), pady=5)
        ttk.Label(params_frame, textvariable=self.cfg_scale).grid(row=1, column=2, padx=(10, 0), pady=5)
        
        # 随机种子
        ttk.Label(params_frame, text="随机种子:").grid(row=2, column=0, sticky=tk.W, pady=5)
        seed_frame = ttk.Frame(params_frame)
        seed_frame.grid(row=2, column=1, sticky=tk.EW, padx=(10, 0), pady=5)
        seed_frame.grid_columnconfigure(0, weight=1)
        
        ttk.Entry(seed_frame, textvariable=self.seed, width=15).grid(row=0, column=0, sticky="w")
        ttk.Button(seed_frame, text="随机", 
                  command=lambda: self.seed.set(np.random.randint(0, 99999999))).grid(row=0, column=1, sticky="w", padx=(5, 0))
        ttk.Button(seed_frame, text="固定", 
                  command=lambda: self.seed.set(self.seed.get())).grid(row=0, column=2, sticky="w", padx=(5, 0))
        
        # 生成帧率
        ttk.Label(params_frame, text="帧率(FPS):").grid(row=3, column=0, sticky=tk.W, pady=5)
        fps_frame = ttk.Frame(params_frame)
        fps_frame.grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=5)
        
        fps_combo = ttk.Combobox(fps_frame, textvariable=self.fps,
                               values=[12, 15, 24, 30, 60], width=10)
        fps_combo.grid(row=0, column=0, sticky="w")
        
        # 生成帧数
        ttk.Label(params_frame, text="生成帧数:").grid(row=3, column=2, sticky=tk.W, padx=(20, 0), pady=5)
        frames_frame = ttk.Frame(params_frame)
        frames_frame.grid(row=3, column=3, sticky=tk.W, padx=(10, 0), pady=5)
        
        frames_combo = ttk.Combobox(frames_frame, textvariable=self.frame_count,
                                   values=[24, 48, 72, 96, 120, 144], width=10)
        frames_combo.grid(row=0, column=0, sticky="w")
        
        # 采样器
        ttk.Label(params_frame, text="采样器:").grid(row=4, column=0, sticky=tk.W, pady=5)
        sampler_combo = ttk.Combobox(params_frame, textvariable=self.sampler, 
                                    values=["DPM++ 2M Karras", "DPM++ SDE Karras", "Euler a", 
                                           "LMS", "Heun", "DPM2", "DPM2 a", "DDIM", "PLMS"],
                                    width=20)
        sampler_combo.grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=5)
        
        # 调度器
        ttk.Label(params_frame, text="调度器:").grid(row=4, column=2, sticky=tk.W, padx=(20, 0), pady=5)
        scheduler_combo = ttk.Combobox(params_frame, textvariable=self.scheduler,
                                     values=["Karras", "Simple", "Normal", "Exponential", 
                                            "Scaled Exponential", "Beta"],
                                     width=15)
        scheduler_combo.grid(row=4, column=3, sticky=tk.W, padx=(10, 0), pady=5)
        
        params_frame.columnconfigure(1, weight=1)
    
    def create_resolution_module(self, parent, row):
        """分辨率模组"""
        module_frame = ttk.LabelFrame(parent, text="📐 分辨率模组", padding=15)
        module_frame.grid(row=row, column=0, sticky="ew", pady=(0, 15))
        
        # 预设分辨率
        ttk.Label(module_frame, text="预设分辨率:").grid(row=0, column=0, sticky=tk.W, pady=5)
        resolution_combo = ttk.Combobox(module_frame, textvariable=self.resolution_preset,
                                      values=list(self.resolution_presets.keys()),
                                      width=20)
        resolution_combo.grid(row=0, column=1, sticky=tk.W, padx=(10, 0), pady=5)
        resolution_combo.bind('<<ComboboxSelected>>', self.on_resolution_change)
        
        # 自定义分辨率
        custom_frame = ttk.LabelFrame(module_frame, text="自定义分辨率", padding=10)
        custom_frame.grid(row=1, column=0, columnspan=4, sticky=tk.EW, pady=(10, 0))
        
        ttk.Label(custom_frame, text="宽度:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(custom_frame, textvariable=self.custom_width, width=10).grid(row=0, column=1, padx=(5, 15))
        
        ttk.Label(custom_frame, text="高度:").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(custom_frame, textvariable=self.custom_height, width=10).grid(row=0, column=3, padx=(5, 0))
        
        ttk.Button(custom_frame, text="应用自定义", 
                  command=self.apply_custom_resolution).grid(row=0, column=4, padx=(15, 0))
        
        # 显示当前分辨率
        self.current_resolution_label = ttk.Label(module_frame, text="当前分辨率: 1280x720", 
                                                foreground="blue", font=("Arial", 10, "bold"))
        self.current_resolution_label.grid(row=2, column=0, columnspan=4, pady=(10, 0))
        
        module_frame.columnconfigure(1, weight=1)
    
    def create_optimization_module(self, parent, row):
        """优化模组"""
        module_frame = ttk.LabelFrame(parent, text="🚀 优化模组", padding=15)
        module_frame.grid(row=row, column=0, sticky="ew", pady=(0, 15))
        
        # 高级采样算法优化
        ttk.Checkbutton(module_frame, text="启用高级采样算法优化", 
                       variable=self.advanced_sampling).grid(row=0, column=0, sticky="w", pady=5)
        
        # 高级CFG优化
        ttk.Checkbutton(module_frame, text="启用高级CFG优化", 
                       variable=self.advanced_cfg).grid(row=1, column=0, sticky="w", pady=5)
        
        # Noise Injection
        noise_frame = ttk.LabelFrame(module_frame, text="🎲 Noise Injection", padding=10)
        noise_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        noise_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Checkbutton(noise_frame, text="启用Noise Injection", 
                       variable=self.noise_injection).grid(row=0, column=0, sticky="w", pady=5)
        
        if self.noise_injection.get():
            noise_ratio_frame = ttk.Frame(noise_frame)
            noise_ratio_frame.grid(row=1, column=0, sticky="ew", pady=5)
            noise_ratio_frame.grid_columnconfigure(1, weight=1)
            
            ttk.Label(noise_ratio_frame, text="噪音比例:").grid(row=0, column=0, sticky="w")
            ttk.Scale(noise_ratio_frame, from_=0.0, to=0.5, variable=self.noise_ratio, 
                     orient=tk.HORIZONTAL, length=150).grid(row=0, column=1, sticky="ew", padx=(10, 0))
            ttk.Label(noise_ratio_frame, textvariable=self.noise_ratio).grid(row=0, column=2, sticky="w", padx=(10, 0))
        
        # Seed Enhancement
        seed_frame = ttk.LabelFrame(module_frame, text="🌱 Seed Enhancement", padding=10)
        seed_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        
        ttk.Checkbutton(seed_frame, text="启用Seed Enhancement", 
                       variable=self.seed_enhance).grid(row=0, column=0, sticky="w", pady=5)
    
    def create_video_generation_special_module(self, parent, row):
        """视频生成特殊功能模组"""
        module_frame = ttk.LabelFrame(parent, text="🎬 视频生成特殊功能", padding=15)
        module_frame.grid(row=row, column=0, sticky="ew", pady=(0, 15))
        
        # 参考图片/视频设置
        reference_frame = ttk.LabelFrame(module_frame, text="🖼️ 参考模式", padding=10)
        reference_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        reference_frame.grid_columnconfigure(1, weight=1)
        
        # 参考模式选择
        mode_frame = ttk.Frame(reference_frame)
        mode_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        mode_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(mode_frame, text="参考模式:").grid(row=0, column=0, sticky="w")
        mode_combo = ttk.Combobox(mode_frame, textvariable=self.reference_mode,
                                 values=["首帧参考", "首尾帧参考", "视频参考", "无参考"], width=15)
        mode_combo.grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        # 参考文件选择
        if self.reference_mode.get() == "首帧参考":
            ttk.Button(mode_frame, text="📷 选择首帧", 
                      command=self.select_first_frame).grid(row=0, column=2, sticky="e")
        elif self.reference_mode.get() == "首尾帧参考":
            first_last_frame = ttk.Frame(mode_frame)
            first_last_frame.grid(row=0, column=2, sticky="e")
            ttk.Button(first_last_frame, text="📷 首帧", 
                      command=self.select_first_frame).grid(row=0, column=0, padx=(0, 5))
            ttk.Button(first_last_frame, text="📷 尾帧", 
                      command=self.select_last_frame).grid(row=0, column=1)
        elif self.reference_mode.get() == "视频参考":
            ttk.Button(mode_frame, text="🎥 选择参考视频", 
                      command=self.select_reference_video).grid(row=0, column=2, sticky="e")
        
        # 显示参考文件
        self.reference_display_frame = ttk.Frame(reference_frame)
        self.reference_display_frame.grid(row=1, column=0, sticky="ew")
        
        # 视频运动参数
        motion_frame = ttk.LabelFrame(module_frame, text="⚡ 运动参数", padding=10)
        motion_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        motion_frame.grid_columnconfigure(1, weight=1)
        
        # 运动强度
        motion_strength_frame = ttk.Frame(motion_frame)
        motion_strength_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        motion_strength_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(motion_strength_frame, text="运动强度:").grid(row=0, column=0, sticky="w")
        ttk.Scale(motion_strength_frame, from_=0.1, to=1.0, variable=self.motion_strength,
                 orient=tk.HORIZONTAL, length=150).grid(row=0, column=1, sticky="ew", padx=(10, 0))
        ttk.Label(motion_strength_frame, textvariable=self.motion_strength).grid(row=0, column=2, sticky="w", padx=(10, 0))
        
        # 运动保持
        motion_preservation_frame = ttk.Frame(motion_frame)
        motion_preservation_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        motion_preservation_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(motion_preservation_frame, text="运动保持:").grid(row=0, column=0, sticky="w")
        ttk.Scale(motion_preservation_frame, from_=0.0, to=1.0, variable=self.motion_preservation,
                 orient=tk.HORIZONTAL, length=150).grid(row=0, column=1, sticky="ew", padx=(10, 0))
        ttk.Label(motion_preservation_frame, textvariable=self.motion_preservation).grid(row=0, column=2, sticky="w", padx=(10, 0))
        
        # 时间一致性
        ttk.Checkbutton(motion_frame, text="启用时间一致性优化", 
                       variable=self.temporal_consistency).grid(row=2, column=0, sticky="w", pady=5)
        
        # 视频质量设置
        quality_frame = ttk.LabelFrame(module_frame, text="🎯 视频质量", padding=10)
        quality_frame.grid(row=2, column=0, sticky="ew")
        quality_frame.grid_columnconfigure(1, weight=1)
        
        # 编码器选择
        ttk.Label(quality_frame, text="视频编码器:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        self.encoder_var = tk.StringVar(value="H.264")
        encoder_combo = ttk.Combobox(quality_frame, textvariable=self.encoder_var,
                                   values=["H.264", "H.265", "VP9", "AV1"], width=15)
        encoder_combo.grid(row=0, column=1, sticky="w", pady=(0, 5))
        
        # 比特率设置
        bitrate_frame = ttk.Frame(quality_frame)
        bitrate_frame.grid(row=1, column=0, sticky="ew", pady=(0, 5))
        bitrate_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(bitrate_frame, text="比特率:").grid(row=0, column=0, sticky="w")
        self.bitrate_var = tk.StringVar(value="自动")
        bitrate_combo = ttk.Combobox(bitrate_frame, textvariable=self.bitrate_var,
                                   values=["自动", "1M", "2M", "4M", "6M", "8M"], width=10)
        bitrate_combo.grid(row=0, column=1, sticky="w", padx=(10, 0))
    
    def create_output_module(self, parent, row):
        """输出设置模组"""
        module_frame = ttk.LabelFrame(parent, text="💾 输出设置", padding=15)
        module_frame.grid(row=row, column=0, sticky="ew", pady=(0, 15))
        
        # 保存目录
        dir_frame = ttk.Frame(module_frame)
        dir_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        dir_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(dir_frame, text="保存目录:").grid(row=0, column=0, sticky="w")
        ttk.Entry(dir_frame, textvariable=self.output_dir, width=40).grid(row=0, column=1, sticky="ew", padx=(10, 0))
        ttk.Button(dir_frame, text="浏览", command=self.browse_output_dir).grid(row=0, column=2, padx=(5, 0))
        
        # 输出格式和质量
        format_frame = ttk.Frame(module_frame)
        format_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        format_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Label(format_frame, text="输出格式:").grid(row=0, column=0, sticky="w")
        format_combo = ttk.Combobox(format_frame, textvariable=self.output_format,
                                   values=["MP4", "AVI", "MOV", "WEBM", "GIF"], width=10)
        format_combo.grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        ttk.Label(format_frame, text="质量:").grid(row=0, column=2, sticky="w", padx=(20, 0))
        quality_scale = ttk.Scale(format_frame, from_=1, to=100, variable=self.output_quality,
                                 orient=tk.HORIZONTAL, length=100)
        quality_scale.grid(row=0, column=3, sticky="w", padx=(10, 0))
        ttk.Label(format_frame, textvariable=self.output_quality).grid(row=0, column=4, sticky="w", padx=(5, 0))
        
        # 保存选项
        save_frame = ttk.Frame(module_frame)
        save_frame.grid(row=2, column=0, sticky="ew")
        save_frame.grid_columnconfigure(0, weight=1)
        
        ttk.Checkbutton(save_frame, text="保存提示词到文件", 
                       variable=self.save_prompt).grid(row=0, column=0, sticky="w")
        
        # AI放大设置
        upscale_frame = ttk.LabelFrame(module_frame, text="🔍 AI放大", padding=10)
        upscale_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        upscale_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Checkbutton(upscale_frame, text="启用AI放大", 
                       variable=self.upscaling_enabled).grid(row=0, column=0, sticky="w", pady=5)
        
        if self.upscaling_enabled.get():
            upscale_params_frame = ttk.Frame(upscale_frame)
            upscale_params_frame.grid(row=1, column=0, sticky="ew", pady=(5, 0))
            upscale_params_frame.grid_columnconfigure(1, weight=1)
            
            ttk.Label(upscale_params_frame, text="放大倍数:").grid(row=0, column=0, sticky="w")
            ratio_combo = ttk.Combobox(upscale_params_frame, textvariable=self.upscale_ratio,
                                      values=[1.5, 2.0, 3.0, 4.0], width=10)
            ratio_combo.grid(row=0, column=1, sticky="w", padx=(10, 0))
            
            ttk.Button(upscale_params_frame, text="使用SeedVR2.5", 
                      command=self.use_seedvr_upscale).grid(row=0, column=2, sticky="e")
        
        module_frame.columnconfigure(1, weight=1)
    
    def create_action_buttons(self, parent, row):
        """创建操作按钮"""
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=row, column=0, sticky="ew", pady=(20, 0))
        button_frame.grid_columnconfigure(1, weight=1)
        
        # 生成按钮
        generate_btn = ttk.Button(button_frame, text="🎬 开始生成", 
                                command=self.start_video_generation,
                                style="Accent.TButton")
        generate_btn.grid(row=0, column=0, sticky="w", padx=(0, 10))
        
        # 预览按钮
        preview_btn = ttk.Button(button_frame, text="👁️ 预览效果", 
                               command=self.preview_generation)
        preview_btn.grid(row=0, column=1, sticky="w", padx=(0, 10))
        
        # 批量生成按钮
        batch_btn = ttk.Button(button_frame, text="📚 批量生成", 
                             command=self.batch_generate_videos)
        batch_btn.grid(row=0, column=2, sticky="w", padx=(0, 10))
        
        # 清空按钮
        clear_btn = ttk.Button(button_frame, text="🗑️ 清空设置", 
                             command=self.clear_all_settings)
        clear_btn.grid(row=0, column=3, sticky="w", padx=(0, 10))
        
        # 进度显示
        self.progress_var = tk.StringVar(value="就绪")
        progress_label = ttk.Label(button_frame, textvariable=self.progress_var, 
                                  foreground="blue")
        progress_label.grid(row=0, column=4, sticky="e")
        
        # 进度条
        self.progress_bar = ttk.Progressbar(button_frame, mode='indeterminate')
        self.progress_bar.grid(row=0, column=5, sticky="e", padx=(10, 0))
    
    # === 功能方法实现 ===
    
    def browse_custom_model(self):
        """浏览自定义模型"""
        filename = filedialog.askopenfilename(
            title="选择模型文件",
            filetypes=[
                ("模型文件", "*.safetensors *.ckpt *.bin *.onnx *.pt *.pth"),
                ("所有文件", "*.*")
            ]
        )
        if filename:
            self.custom_model_path.set(filename)
    
    def update_model_list(self):
        """更新模型列表"""
        # 模拟从本地扫描模型文件
        model_dirs = [
            "./models", "./models/diffusers", "./models/safetensors", 
            "./models/checkpoints", "./models/controlnet"
        ]
        
        discovered_models = []
        for model_dir in model_dirs:
            if os.path.exists(model_dir):
                for file in os.listdir(model_dir):
                    if file.endswith(('.safetensors', '.ckpt', '.bin', '.onnx', '.pt', '.pth')):
                        discovered_models.append(os.path.join(model_dir, file))
        
        if discovered_models:
            self.model_list.extend(discovered_models)
            messagebox.showinfo("成功", f"发现 {len(discovered_models)} 个模型文件")
        else:
            messagebox.showinfo("提示", "未发现新的模型文件")
    
    def search_github_models(self):
        """搜索GitHub模型"""
        query = self.github_search_var.get().strip()
        if not query:
            messagebox.showwarning("警告", "请输入搜索关键词")
            return
        
        # 模拟GitHub API调用
        messagebox.showinfo("提示", f"正在搜索GitHub: {query}\n功能开发中...")
    
    def search_huggingface_models(self):
        """搜索HuggingFace模型"""
        query = self.github_search_var.get().strip()
        if not query:
            messagebox.showwarning("警告", "请输入搜索关键词")
            return
        
        # 模拟HuggingFace API调用
        messagebox.showinfo("提示", f"正在搜索HuggingFace: {query}\n功能开发中...")
    
    def apply_positive_style(self):
        """应用正向风格模板"""
        style = self.positive_style_var.get()
        if style in self.prompt_templates:
            current_text = self.positive_text.get(1.0, tk.END).strip()
            template = self.prompt_templates[style]
            if current_text:
                new_text = f"{template} {current_text}"
            else:
                new_text = template
            self.positive_text.delete(1.0, tk.END)
            self.positive_text.insert(1.0, new_text)
    
    def edit_positive_styles(self):
        """编辑正向风格模板"""
        messagebox.showinfo("提示", "风格模板编辑器功能开发中...")
    
    def apply_negative_style(self):
        """应用负向风格模板"""
        style = self.negative_style_var.get()
        if style in self.negative_templates:
            current_text = self.negative_text.get(1.0, tk.END).strip()
            template = self.negative_templates[style]
            if current_text:
                new_text = f"{current_text} {template}"
            else:
                new_text = template
            self.negative_text.delete(1.0, tk.END)
            self.negative_text.insert(1.0, new_text)
    
    def edit_negative_styles(self):
        """编辑负向风格模板"""
        messagebox.showinfo("提示", "负向模板编辑器功能开发中...")
    
    def import_batch_prompts(self):
        """批量导入TXT提示词"""
        filename = filedialog.askopenfilename(
            title="选择TXT文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    prompts = f.readlines()
                messagebox.showinfo("成功", f"导入 {len(prompts)} 条提示词")
            except Exception as e:
                messagebox.showerror("错误", f"导入失败: {str(e)}")
    
    def import_excel_prompts(self):
        """导入Excel/CSV提示词"""
        filename = filedialog.askopenfilename(
            title="选择Excel/CSV文件",
            filetypes=[
                ("Excel文件", "*.xlsx *.xls"),
                ("CSV文件", "*.csv"),
                ("JSON文件", "*.json"),
                ("所有文件", "*.*")
            ]
        )
        if filename:
            messagebox.showinfo("提示", "Excel/CSV导入功能开发中...")
    
    def optimize_prompt(self):
        """AI优化提示词"""
        # 模拟调用本地LLM或API进行提示词优化
        messagebox.showinfo("提示", "AI提示词优化功能开发中...")
    
    def translate_prompt(self):
        """翻译提示词为中文"""
        # 模拟调用翻译API
        messagebox.showinfo("提示", "提示词翻译功能开发中...")
    
    def add_lora(self):
        """添加LoRA"""
        if len(self.lora_files) >= 3:
            messagebox.showwarning("警告", "最多支持3个LoRA")
            return
        
        filename = filedialog.askopenfilename(
            title="选择LoRA文件",
            filetypes=[("LoRA文件", "*.safetensors *.ckpt"), ("所有文件", "*.*")]
        )
        if filename:
            self.lora_files.append(filename)
            self.lora_weights.append(1.0)
            self.update_lora_display()
    
    def clear_loras(self):
        """清除所有LoRA"""
        self.lora_files.clear()
        self.lora_weights.clear()
        self.update_lora_display()
    
    def update_lora_display(self):
        """更新LoRA显示"""
        for item in self.lora_tree.get_children():
            self.lora_tree.delete(item)
        
        for i, (lora_file, weight) in enumerate(zip(self.lora_files, self.lora_weights)):
            self.lora_tree.insert("", "end", text=os.path.basename(lora_file), 
                                 values=(f"{weight:.2f}"))
    
    def select_controlnet_files(self):
        """选择ControlNet文件"""
        filenames = filedialog.askopenfilenames(
            title="选择ControlNet文件",
            filetypes=[("模型文件", "*.safetensors *.ckpt"), ("所有文件", "*.*")]
        )
        if filenames:
            self.controlnet_files = list(filenames)
            messagebox.showinfo("成功", f"选择 {len(filenames)} 个ControlNet文件")
    
    def on_resolution_change(self, event=None):
        """分辨率选择变化"""
        preset = self.resolution_preset.get()
        if preset in self.resolution_presets and self.resolution_presets[preset]:
            width, height = self.resolution_presets[preset]
            self.custom_width.set(width)
            self.custom_height.set(height)
        
        self.update_current_resolution()
    
    def apply_custom_resolution(self):
        """应用自定义分辨率"""
        preset = f"{self.custom_width.get()}x{self.custom_height.get()}"
        self.resolution_preset.set(preset)
        self.update_current_resolution()
    
    def update_current_resolution(self):
        """更新当前分辨率显示"""
        width = self.custom_width.get()
        height = self.custom_height.get()
        self.current_resolution_label.config(text=f"当前分辨率: {width}x{height}")
    
    def select_first_frame(self):
        """选择首帧"""
        filename = filedialog.askopenfilename(
            title="选择首帧图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"),
                ("所有文件", "*.*")
            ]
        )
        if filename:
            self.first_frame_path = filename
            self.update_reference_display()
    
    def select_last_frame(self):
        """选择尾帧"""
        filename = filedialog.askopenfilename(
            title="选择尾帧图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"),
                ("所有文件", "*.*")
            ]
        )
        if filename:
            self.last_frame_path = filename
            self.update_reference_display()
    
    def select_reference_video(self):
        """选择参考视频"""
        filename = filedialog.askopenfilename(
            title="选择参考视频",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("所有文件", "*.*")
            ]
        )
        if filename:
            self.reference_video_path = filename
            self.update_reference_display()
    
    def update_reference_display(self):
        """更新参考文件显示"""
        # 清空现有显示
        for widget in self.reference_display_frame.winfo_children():
            widget.destroy()
        
        # 设置网格布局
        self.reference_display_frame.grid_columnconfigure(0, weight=1)
        
        # 显示参考文件信息
        row = 0
        if self.first_frame_path:
            ttk.Label(self.reference_display_frame, text=f"首帧: {os.path.basename(self.first_frame_path)}").grid(row=row, column=0, sticky="w")
            row += 1
        if self.last_frame_path:
            ttk.Label(self.reference_display_frame, text=f"尾帧: {os.path.basename(self.last_frame_path)}").grid(row=row, column=0, sticky="w")
            row += 1
        if self.reference_video_path:
            ttk.Label(self.reference_display_frame, text=f"参考视频: {os.path.basename(self.reference_video_path)}").grid(row=row, column=0, sticky="w")
            row += 1
        
        if not any([self.first_frame_path, self.last_frame_path, self.reference_video_path]):
            ttk.Label(self.reference_display_frame, text="未选择参考文件", foreground="gray").grid(row=row, column=0, sticky="w")
    
    def browse_output_dir(self):
        """浏览输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.output_dir.set(directory)
    
    def use_seedvr_upscale(self):
        """使用SeedVR2.5放大"""
        messagebox.showinfo("提示", "SeedVR2.5放大功能开发中...")
    
    def start_video_generation(self):
        """开始视频生成"""
        # 更新UI状态
        self.progress_var.set("正在生成视频...")
        self.progress_bar.start()
        
        # 在后台线程执行生成任务
        def generate_task():
            try:
                # 收集所有参数
                params = self.collect_generation_params()
                
                # 调用视频生成后端
                result = self.call_video_generation_backend(params)
                
                # 更新UI状态
                self.parent.after(0, self.on_generation_complete, result)
            except Exception as e:
                self.parent.after(0, self.on_generation_error, str(e))
        
        threading.Thread(target=generate_task, daemon=True).start()
    
    def collect_generation_params(self):
        """收集生成参数"""
        return {
            "model": self.model_var.get(),
            "first_frame": self.first_frame_path,
            "last_frame": self.last_frame_path,
            "reference_video": self.reference_video_path,
            "positive_prompt": self.positive_text.get(1.0, tk.END).strip(),
            "negative_prompt": self.negative_text.get(1.0, tk.END).strip(),
            "lora_files": self.lora_files,
            "lora_weights": self.lora_weights,
            "controlnet_enabled": self.controlnet_enabled.get(),
            "controlnet_files": self.controlnet_files,
            "controlnet_weight": self.controlnet_weight.get(),
            "steps": self.steps.get(),
            "cfg_scale": self.cfg_scale.get(),
            "seed": self.seed.get(),
            "fps": self.fps.get(),
            "frame_count": self.frame_count.get(),
            "sampler": self.sampler.get(),
            "scheduler": self.scheduler.get(),
            "width": self.custom_width.get(),
            "height": self.custom_height.get(),
            "resolution_preset": self.resolution_preset.get(),
            "advanced_sampling": self.advanced_sampling.get(),
            "advanced_cfg": self.advanced_cfg.get(),
            "noise_injection": self.noise_injection.get(),
            "noise_ratio": self.noise_ratio.get(),
            "seed_enhance": self.seed_enhance.get(),
            "reference_mode": self.reference_mode.get(),
            "motion_strength": self.motion_strength.get(),
            "temporal_consistency": self.temporal_consistency.get(),
            "motion_preservation": self.motion_preservation.get(),
            "encoder": self.encoder_var.get(),
            "bitrate": self.bitrate_var.get(),
            "upscaling_enabled": self.upscaling_enabled.get(),
            "upscale_ratio": self.upscale_ratio.get(),
            "output_format": self.output_format.get(),
            "output_quality": self.output_quality.get(),
            "output_dir": self.output_dir.get(),
            "save_prompt": self.save_prompt.get()
        }
    
    def call_video_generation_backend(self, params):
        """调用视频生成后端"""
        # 模拟后端调用
        import time
        time.sleep(3)  # 模拟处理时间
        
        # 返回模拟结果
        return {
            "success": True,
            "output_path": os.path.join(params["output_dir"], "generated_video.mp4"),
            "message": "视频生成完成"
        }
    
    def on_generation_complete(self, result):
        """生成完成回调"""
        self.progress_bar.stop()
        if result["success"]:
            self.progress_var.set("生成完成！")
            messagebox.showinfo("成功", f"视频生成完成！\n保存路径: {result['output_path']}")
        else:
            self.progress_var.set("生成失败")
            messagebox.showerror("错误", result.get("message", "未知错误"))
    
    def on_generation_error(self, error_msg):
        """生成错误回调"""
        self.progress_bar.stop()
        self.progress_var.set("生成失败")
        messagebox.showerror("错误", f"视频生成失败: {error_msg}")
    
    def preview_generation(self):
        """预览生成效果"""
        messagebox.showinfo("提示", "预览功能开发中...")
    
    def batch_generate_videos(self):
        """批量生成视频"""
        messagebox.showinfo("提示", "批量生成功能开发中...")
    
    def clear_all_settings(self):
        """清空所有设置"""
        # 确认对话框
        if messagebox.askyesno("确认", "确定要清空所有设置吗？"):
            # 重置所有变量
            self.model_var.set("wan2.2")
            self.positive_text.delete(1.0, tk.END)
            self.negative_text.delete(1.0, tk.END)
            self.lora_files.clear()
            self.lora_weights.clear()
            self.controlnet_files.clear()
            self.controlnet_enabled.set(False)
            self.steps.set(50)
            self.cfg_scale.set(7.0)
            self.seed.set(-1)
            self.fps.set(24)
            self.frame_count.set(120)
            self.sampler.set("DPM++ 2M Karras")
            self.scheduler.set("Karras")
            self.resolution_preset.set("1280x720")
            self.custom_width.set(1280)
            self.custom_height.set(720)
            self.advanced_sampling.set(True)
            self.advanced_cfg.set(True)
            self.noise_injection.set(False)
            self.seed_enhance.set(False)
            self.reference_mode.set("首帧参考")
            self.motion_strength.set(0.8)
            self.temporal_consistency.set(True)
            self.motion_preservation.set(0.7)
            self.output_format.set("MP4")
            self.output_quality.set(95)
            self.save_prompt.set(True)
            self.upscaling_enabled.set(False)
            self.upscale_ratio.set(2.0)
            
            # 清空显示
            self.first_frame_path = None
            self.last_frame_path = None
            self.reference_video_path = None
            
            # 更新显示
            self.update_lora_display()
            self.update_current_resolution()
            self.update_reference_display()
            
            self.progress_var.set("设置已清空")
            messagebox.showinfo("成功", "所有设置已清空")
    
    def show(self):
        """显示组件界面"""
        try:
            if hasattr(self, 'main_frame'):
                self.main_frame.grid()
            self.log_message("✅ 视频生成组件已显示")
        except Exception as e:
            self.log_message(f"❌ 显示组件失败: {e}")
    
    def hide(self):
        """隐藏组件界面"""
        try:
            if hasattr(self, 'main_frame'):
                self.main_frame.grid_remove()
            self.log_message("ℹ️ 视频生成组件已隐藏")
        except Exception as e:
            self.log_message(f"❌ 隐藏组件失败: {e}")
    
    def log_message(self, message):
        """记录日志消息"""
        if hasattr(self, 'main_app') and hasattr(self.main_app, 'log'):
            self.main_app.log(message)
        else:
            print(f"[Video Generation] {message}")