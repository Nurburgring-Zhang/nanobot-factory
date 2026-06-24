#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全新设计的图片编辑UI组件 - 终极AIGC生成器 v5.4
基于用户详细要求创建的全新图片编辑UI组件：
1. 基础7个模组：模型、提示词、Lora、Controlnet、生图参数、分辨率、优化
2. 图片编辑特殊功能：qwen edit 2511、Flux.2 Klein模型支持、单图/多图参考、局部重绘、人脸识别保持、风格转换、AI放大、风格滤镜
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
from PIL import Image, ImageTk, ImageFilter
import cv2
import numpy as np

class RedesignedImageEditingComponents:
    def __init__(self, parent, main_app):
        self.parent = parent
        self.main_app = main_app
        
        # 图片编辑相关变量
        self.input_image_path = None
        self.reference_images = []
        self.mask_image_path = None
        self.output_dir = tk.StringVar(value="./output")
        self.output_format = tk.StringVar(value="PNG")
        self.output_quality = tk.IntVar(value=95)
        self.save_prompt = tk.BooleanVar(value=True)
        self.upscaling_enabled = tk.BooleanVar(value=False)
        self.upscale_ratio = tk.DoubleVar(value=2.0)
        self.redraw_strength = tk.DoubleVar(value=0.3)
        self.style_filter_enabled = tk.BooleanVar(value=False)
        
        # 模型相关
        self.model_var = tk.StringVar(value="qwen_edit_2511")
        self.model_list = [
            "qwen_edit_2511", "flux2_klein", "sd_1_5", "sdxl", "flux2", 
            "dalle3", "midjourney", "stable_diffusion_2_1", "deepfloyd_if"
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
        
        # 生图参数
        self.steps = tk.IntVar(value=20)
        self.cfg_scale = tk.DoubleVar(value=7.0)
        self.seed = tk.IntVar(value=-1)
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
            "2048x1152": (2048, 1152),
            "1152x2048": (1152, 2048),
            "1536x1536": (1536, 1536),
            "随机分辨率": None
        }
        
        # 优化选项
        self.noise_injection = tk.BooleanVar(value=False)
        self.noise_ratio = tk.DoubleVar(value=0.1)
        self.seed_enhance = tk.BooleanVar(value=False)
        self.advanced_sampling = tk.BooleanVar(value=True)
        self.advanced_cfg = tk.BooleanVar(value=True)
        
        # 图片编辑特殊功能
        self.reference_mode = tk.StringVar(value="单图参考")
        self.editing_mode = tk.StringVar(value="整体风格转换")
        self.face_preservation = tk.BooleanVar(value=True)
        self.local_feature_transfer = tk.BooleanVar(value=False)
        
        self.create_ui()
    
    def create_ui(self):
        """创建图片编辑UI"""
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
        
        # 包装滚动区域
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # 鼠标滚轮绑定
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # === 基础7个模组 ===
        self.create_model_module(scrollable_frame)
        self.create_prompt_module(scrollable_frame)
        self.create_lora_module(scrollable_frame)
        self.create_controlnet_module(scrollable_frame)
        self.create_generation_params_module(scrollable_frame)
        self.create_resolution_module(scrollable_frame)
        self.create_optimization_module(scrollable_frame)
        
        # === 图片编辑特殊功能模组 ===
        self.create_image_editing_special_module(scrollable_frame)
        
        # === 输出设置模组 ===
        self.create_output_module(scrollable_frame)
        
        # === 生成控制按钮 ===
        self.create_action_buttons(scrollable_frame)
    
    def create_model_module(self, parent):
        """模型模组"""
        module_frame = ttk.LabelFrame(parent, text="🔧 模型模组", padding=15)
        module_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 15))
        
        # 模型选择
        ttk.Label(module_frame, text="选择模型:").grid(row=0, column=0, sticky=tk.W, pady=5)
        
        model_combo = ttk.Combobox(module_frame, textvariable=self.model_var, 
                                 values=self.model_list, width=25)
        model_combo.grid(row=0, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        
        # 自定义模型路径
        ttk.Label(module_frame, text="自定义模型:").grid(row=1, column=0, sticky=tk.W, pady=5)
        
        custom_model_frame = ttk.Frame(module_frame)
        custom_model_frame.grid(row=1, column=1, sticky=tk.W, pady=5, padx=(10, 0))
        custom_model_frame.columnconfigure(0, weight=1)
        
        self.custom_model_path = tk.StringVar()
        ttk.Entry(custom_model_frame, textvariable=self.custom_model_path, width=30).grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        ttk.Button(custom_model_frame, text="浏览", 
                  command=self.browse_custom_model).grid(row=0, column=1)
        
        # 自动更新按钮
        ttk.Button(module_frame, text="🔄 更新模型列表", 
                  command=self.update_model_list).grid(row=0, column=2, padx=(20, 0), pady=5)
        
        # GitHub/HuggingFace搜索
        search_frame = ttk.LabelFrame(module_frame, text="🔍 在线搜索模型", padding=10)
        search_frame.grid(row=2, column=0, columnspan=3, sticky=tk.EW, pady=(10, 0))
        search_frame.columnconfigure(0, weight=1)
        
        self.github_search_var = tk.StringVar()
        ttk.Entry(search_frame, textvariable=self.github_search_var, width=40).grid(row=0, column=0, sticky=tk.EW, padx=(0, 10))
        ttk.Button(search_frame, text="搜索GitHub", 
                  command=self.search_github_models).grid(row=0, column=1)
        ttk.Button(search_frame, text="搜索HuggingFace", 
                  command=self.search_huggingface_models).grid(row=0, column=2, padx=(5, 0))
        
        module_frame.columnconfigure(1, weight=1)
    
    def create_prompt_module(self, parent):
        """提示词模组"""
        module_frame = ttk.LabelFrame(parent, text="📝 提示词模组", padding=15)
        module_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 15))
        
        # 正向提示词
        ttk.Label(module_frame, text="正向提示词:").grid(row=0, column=0, sticky=tk.NW, pady=5)
        
        positive_frame = ttk.Frame(module_frame)
        positive_frame.grid(row=0, column=1, sticky=tk.EW, pady=5, padx=(10, 0))
        positive_frame.columnconfigure(0, weight=1)
        
        # 预设正向风格模板
        style_template_top = ttk.Frame(positive_frame)
        style_template_top.grid(row=0, column=0, sticky=tk.EW, pady=(0, 5))
        
        ttk.Label(style_template_top, text="风格模板:").grid(row=0, column=0, sticky=tk.W)
        
        style_template_frame = ttk.Frame(style_template_top)
        style_template_frame.grid(row=1, column=0, sticky=tk.EW, pady=(5, 0))
        style_template_frame.columnconfigure(0, weight=1)
        
        self.positive_style_var = tk.StringVar(value="默认")
        style_combo = ttk.Combobox(style_template_frame, textvariable=self.positive_style_var, width=20)
        style_combo.grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        ttk.Button(style_template_frame, text="应用", 
                  command=self.apply_positive_style).grid(row=0, column=1, padx=(0, 5))
        ttk.Button(style_template_frame, text="编辑", 
                  command=self.edit_positive_styles).grid(row=0, column=2)
        
        # 正向提示词输入
        self.positive_text = scrolledtext.ScrolledText(positive_frame, height=4, width=50)
        self.positive_text.grid(row=1, column=0, sticky=tk.EW)
        
        # 批量提示词导入
        batch_frame = ttk.Frame(positive_frame)
        batch_frame.grid(row=2, column=0, sticky=tk.EW, pady=(5, 0))
        batch_frame.columnconfigure(2, weight=1)
        
        ttk.Button(batch_frame, text="📁 批量导入TXT", 
                  command=self.import_batch_prompts).grid(row=0, column=0)
        ttk.Button(batch_frame, text="📊 导入Excel/CSV", 
                  command=self.import_excel_prompts).grid(row=0, column=1, padx=(5, 0))
        
        # AI优化按钮
        ttk.Button(batch_frame, text="🤖 AI优化提示词", 
                  command=self.optimize_prompt).grid(row=0, column=3)
        
        # 翻译按钮
        ttk.Button(batch_frame, text="🌐 翻译为中文", 
                  command=self.translate_prompt).grid(row=0, column=2, padx=(0, 5))
        
        # 负向提示词
        ttk.Label(module_frame, text="负向提示词:").grid(row=1, column=0, sticky=tk.NW, pady=(10, 5))
        
        negative_frame = ttk.Frame(module_frame)
        negative_frame.grid(row=1, column=1, sticky=tk.EW, pady=(10, 5), padx=(10, 0))
        negative_frame.columnconfigure(0, weight=1)
        
        # 预设负向风格模板
        neg_template_top = ttk.Frame(negative_frame)
        neg_template_top.grid(row=0, column=0, sticky=tk.EW, pady=(0, 5))
        
        ttk.Label(neg_template_top, text="负面模板:").grid(row=0, column=0, sticky=tk.W)
        
        neg_template_frame = ttk.Frame(neg_template_top)
        neg_template_frame.grid(row=1, column=0, sticky=tk.EW, pady=(5, 0))
        neg_template_frame.columnconfigure(0, weight=1)
        
        self.negative_style_var = tk.StringVar(value="默认")
        neg_style_combo = ttk.Combobox(neg_template_frame, textvariable=self.negative_style_var, width=20)
        neg_style_combo.grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        ttk.Button(neg_template_frame, text="应用", 
                  command=self.apply_negative_style).grid(row=0, column=1, padx=(0, 5))
        ttk.Button(neg_template_frame, text="编辑", 
                  command=self.edit_negative_styles).grid(row=0, column=2)
        
        # 负向提示词输入
        self.negative_text = scrolledtext.ScrolledText(negative_frame, height=3, width=50)
        self.negative_text.grid(row=1, column=0, sticky=tk.EW)
        
        module_frame.columnconfigure(1, weight=1)
    
    def create_lora_module(self, parent):
        """LoRA模组"""
        module_frame = ttk.LabelFrame(parent, text="🎨 LoRA模组", padding=15)
        module_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 15))
        
        # LoRA列表
        lora_frame = ttk.Frame(module_frame)
        lora_frame.grid(row=0, column=0, sticky=tk.EW)
        lora_frame.columnconfigure(1, weight=1)
        
        # 添加LoRA按钮
        ttk.Button(lora_frame, text="➕ 添加LoRA", 
                  command=self.add_lora).grid(row=0, column=0, pady=5)
        ttk.Button(lora_frame, text="🗑️ 清除所有", 
                  command=self.clear_loras).grid(row=0, column=1, padx=(10, 0), pady=5)
        
        # LoRA列表显示
        list_frame = ttk.Frame(module_frame)
        list_frame.grid(row=1, column=0, sticky=tk.EW, pady=(10, 0))
        
        self.lora_tree = ttk.Treeview(list_frame, columns=("权重"), show="tree headings")
        self.lora_tree.heading("#0", text="LoRA文件")
        self.lora_tree.heading("权重", text="权重")
        self.lora_tree.column("权重", width=80)
        self.lora_tree.grid(row=0, column=0, sticky=tk.EW)
        
        # 支持最多3个LoRA的提示
        ttk.Label(module_frame, text="支持最多3个LoRA，可调节权重", 
                 foreground="gray").grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
    
    def create_controlnet_module(self, parent):
        """ControlNet模组"""
        module_frame = ttk.LabelFrame(parent, text="🎛️ ControlNet模组", padding=15)
        module_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 15))
        
        # 启用ControlNet
        ttk.Checkbutton(module_frame, text="启用ControlNet", 
                       variable=self.controlnet_enabled).grid(row=0, column=0, sticky=tk.W, pady=5)
        
        if self.controlnet_enabled.get():
            # ControlNet文件选择
            ttk.Button(module_frame, text="📁 选择ControlNet文件", 
                      command=self.select_controlnet_files).grid(row=1, column=0, sticky=tk.W, pady=5)
            
            # 控制权重
            weight_frame = ttk.Frame(module_frame)
            weight_frame.grid(row=2, column=0, sticky=tk.EW, pady=5)
            weight_frame.columnconfigure(1, weight=1)
            
            ttk.Label(weight_frame, text="控制权重:").grid(row=0, column=0, sticky=tk.W)
            ttk.Scale(weight_frame, from_=0.0, to=1.0, variable=self.controlnet_weight, 
                     orient=tk.HORIZONTAL, length=200).grid(row=0, column=1, sticky=tk.EW, padx=(10, 0))
            ttk.Label(weight_frame, textvariable=self.controlnet_weight).grid(row=0, column=2, padx=(10, 0))
    
    def create_generation_params_module(self, parent):
        """生图参数模组"""
        module_frame = ttk.LabelFrame(parent, text="⚙️ 生图参数模组", padding=15)
        module_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 15))
        
        # 参数网格
        params_frame = ttk.Frame(module_frame)
        params_frame.grid(row=0, column=0, sticky=tk.EW)
        
        # 推理步数
        ttk.Label(params_frame, text="推理步数:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Scale(params_frame, from_=1, to=100, variable=self.steps, 
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
        seed_frame.columnconfigure(0, weight=1)
        
        ttk.Entry(seed_frame, textvariable=self.seed, width=15).grid(row=0, column=0, sticky=tk.W)
        ttk.Button(seed_frame, text="随机", 
                  command=lambda: self.seed.set(np.random.randint(0, 99999999))).grid(row=0, column=1, padx=(5, 0))
        ttk.Button(seed_frame, text="固定", 
                  command=lambda: self.seed.set(self.seed.get())).grid(row=0, column=2, padx=(5, 0))
        
        # 采样器
        ttk.Label(params_frame, text="采样器:").grid(row=3, column=0, sticky=tk.W, pady=5)
        sampler_combo = ttk.Combobox(params_frame, textvariable=self.sampler, 
                                    values=["DPM++ 2M Karras", "DPM++ SDE Karras", "Euler a", 
                                           "LMS", "Heun", "DPM2", "DPM2 a", "DDIM", "PLMS"],
                                    width=20)
        sampler_combo.grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=5)
        
        # 调度器
        ttk.Label(params_frame, text="调度器:").grid(row=3, column=2, sticky=tk.W, padx=(20, 0), pady=5)
        scheduler_combo = ttk.Combobox(params_frame, textvariable=self.scheduler,
                                     values=["Karras", "Simple", "Normal", "Exponential", 
                                            "Scaled Exponential", "Beta"],
                                     width=15)
        scheduler_combo.grid(row=3, column=3, sticky=tk.W, padx=(10, 0), pady=5)
        
        params_frame.columnconfigure(1, weight=1)
    
    def create_resolution_module(self, parent):
        """分辨率模组"""
        module_frame = ttk.LabelFrame(parent, text="📐 分辨率模组", padding=15)
        module_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 15))
        
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
    
    def create_optimization_module(self, parent):
        """优化模组"""
        module_frame = ttk.LabelFrame(parent, text="🚀 优化模组", padding=15)
        module_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 15))
        
        # 高级采样算法优化
        ttk.Checkbutton(module_frame, text="启用高级采样算法优化", 
                       variable=self.advanced_sampling).grid(row=0, column=0, sticky=tk.W, pady=5)
        
        # 高级CFG优化
        ttk.Checkbutton(module_frame, text="启用高级CFG优化", 
                       variable=self.advanced_cfg).grid(row=1, column=0, sticky=tk.W, pady=5)
        
        # Noise Injection
        noise_frame = ttk.LabelFrame(module_frame, text="🎲 Noise Injection", padding=10)
        noise_frame.grid(row=2, column=0, sticky=tk.EW, pady=(10, 0))
        
        ttk.Checkbutton(noise_frame, text="启用Noise Injection", 
                       variable=self.noise_injection).grid(row=0, column=0, sticky=tk.W, pady=5)
        
        if self.noise_injection.get():
            noise_ratio_frame = ttk.Frame(noise_frame)
            noise_ratio_frame.grid(row=1, column=0, sticky=tk.EW, pady=5)
            noise_ratio_frame.columnconfigure(1, weight=1)
            
            ttk.Label(noise_ratio_frame, text="噪音比例:").grid(row=0, column=0, sticky=tk.W)
            ttk.Scale(noise_ratio_frame, from_=0.0, to=0.5, variable=self.noise_ratio, 
                     orient=tk.HORIZONTAL, length=150).grid(row=0, column=1, sticky=tk.EW, padx=(10, 0))
            ttk.Label(noise_ratio_frame, textvariable=self.noise_ratio).grid(row=0, column=2, padx=(10, 0))
        
        # Seed Enhancement
        seed_frame = ttk.LabelFrame(module_frame, text="🌱 Seed Enhancement", padding=10)
        seed_frame.grid(row=3, column=0, sticky=tk.EW, pady=(10, 0))
        
        ttk.Checkbutton(seed_frame, text="启用Seed Enhancement", 
                       variable=self.seed_enhance).grid(row=0, column=0, sticky=tk.W, pady=5)
    
    def create_image_editing_special_module(self, parent):
        """图片编辑特殊功能模组"""
        module_frame = ttk.LabelFrame(parent, text="🎨 图片编辑特殊功能", padding=15)
        module_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 15))
        
        # 输入图片选择
        input_frame = ttk.LabelFrame(module_frame, text="📷 输入图片", padding=10)
        input_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 10))
        
        input_buttons = ttk.Frame(input_frame)
        input_buttons.grid(row=0, column=0, sticky=tk.EW)
        input_buttons.columnconfigure(1, weight=1)
        
        ttk.Button(input_buttons, text="📁 选择输入图片", 
                  command=self.select_input_image).grid(row=0, column=0)
        ttk.Button(input_buttons, text="📸 拍照", 
                  command=self.capture_image).grid(row=0, column=1, padx=(10, 0))
        
        # 显示输入图片
        self.input_image_label = ttk.Label(input_frame, text="未选择图片")
        self.input_image_label.grid(row=1, column=0, pady=10)
        
        # 参考图片设置
        reference_frame = ttk.LabelFrame(module_frame, text="🖼️ 参考图片模式", padding=10)
        reference_frame.grid(row=1, column=0, sticky=tk.EW, pady=(0, 10))
        
        # 参考模式选择
        mode_frame = ttk.Frame(reference_frame)
        mode_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 10))
        mode_frame.columnconfigure(1, weight=1)
        
        ttk.Label(mode_frame, text="参考模式:").grid(row=0, column=0, sticky=tk.W)
        mode_combo = ttk.Combobox(mode_frame, textvariable=self.reference_mode,
                                 values=["单图参考", "多图参考", "无参考"], width=15)
        mode_combo.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        # 添加参考图片
        if self.reference_mode.get() in ["单图参考", "多图参考"]:
            ttk.Button(mode_frame, text="➕ 添加参考图片", 
                      command=self.add_reference_images).grid(row=0, column=2)
        
        # 显示参考图片列表
        self.reference_images_frame = ttk.Frame(reference_frame)
        self.reference_images_frame.grid(row=1, column=0, sticky=tk.EW)
        
        # 编辑模式选择
        editing_frame = ttk.LabelFrame(module_frame, text="✏️ 编辑模式", padding=10)
        editing_frame.grid(row=2, column=0, sticky=tk.EW, pady=(0, 10))
        
        mode_select_frame = ttk.Frame(editing_frame)
        mode_select_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 10))
        mode_select_frame.columnconfigure(1, weight=1)
        
        ttk.Label(mode_select_frame, text="编辑模式:").grid(row=0, column=0, sticky=tk.W)
        editing_combo = ttk.Combobox(mode_select_frame, textvariable=self.editing_mode,
                                   values=["整体风格转换", "局部识别重绘", "Mask局部重绘", 
                                          "人脸识别保持", "局部特征迁移"], width=20)
        editing_combo.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        # 编辑参数
        if self.editing_mode.get() in ["局部识别重绘", "Mask局部重绘"]:
            params_frame = ttk.Frame(editing_frame)
            params_frame.grid(row=1, column=0, sticky=tk.EW, pady=(0, 10))
            params_frame.columnconfigure(1, weight=1)
            
            ttk.Label(params_frame, text="重绘幅度:").grid(row=0, column=0, sticky=tk.W)
            ttk.Scale(params_frame, from_=0.1, to=1.0, variable=self.redraw_strength,
                     orient=tk.HORIZONTAL, length=150).grid(row=0, column=1, sticky=tk.EW, padx=(10, 0))
            ttk.Label(params_frame, textvariable=self.redraw_strength).grid(row=0, column=2, padx=(10, 0))
        
        # 特殊功能选项
        special_frame = ttk.LabelFrame(module_frame, text="⚡ 特殊功能", padding=10)
        special_frame.grid(row=3, column=0, sticky=tk.EW)
        
        # 人脸识别保持
        ttk.Checkbutton(special_frame, text="启用人脸识别保持", 
                       variable=self.face_preservation).grid(row=0, column=0, sticky=tk.W, pady=5)
        
        # 局部特征迁移
        ttk.Checkbutton(special_frame, text="启用局部特征迁移", 
                       variable=self.local_feature_transfer).grid(row=1, column=0, sticky=tk.W, pady=5)
        
        # 风格滤镜
        style_frame = ttk.LabelFrame(special_frame, text="🎭 风格滤镜", padding=10)
        style_frame.grid(row=2, column=0, sticky=tk.EW, pady=(10, 0))
        
        ttk.Checkbutton(style_frame, text="启用风格滤镜", 
                       variable=self.style_filter_enabled).grid(row=0, column=0, sticky=tk.W, pady=5)
        
        if self.style_filter_enabled.get():
            self.style_filter_var = tk.StringVar(value="无滤镜")
            style_combo = ttk.Combobox(style_frame, textvariable=self.style_filter_var,
                                      values=["无滤镜", "油画风格", "水彩风格", "素描风格", 
                                             "复古风格", "现代风格", "黑白滤镜", "暖色调", "冷色调"],
                                      width=20)
            style_combo.grid(row=1, column=0, sticky=tk.W, pady=5)
    
    def create_output_module(self, parent):
        """输出设置模组"""
        module_frame = ttk.LabelFrame(parent, text="💾 输出设置", padding=15)
        module_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 15))
        
        # 保存目录
        dir_frame = ttk.Frame(module_frame)
        dir_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 10))
        dir_frame.columnconfigure(1, weight=1)
        
        ttk.Label(dir_frame, text="保存目录:").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(dir_frame, textvariable=self.output_dir, width=40).grid(row=0, column=1, sticky=tk.EW, padx=(10, 0))
        ttk.Button(dir_frame, text="浏览", command=self.browse_output_dir).grid(row=0, column=2, padx=(5, 0))
        
        # 输出格式和质量
        format_frame = ttk.Frame(module_frame)
        format_frame.grid(row=1, column=0, sticky=tk.EW, pady=(0, 10))
        
        ttk.Label(format_frame, text="输出格式:").grid(row=0, column=0, sticky=tk.W)
        format_combo = ttk.Combobox(format_frame, textvariable=self.output_format,
                                   values=["PNG", "JPEG", "WEBP"], width=10)
        format_combo.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        ttk.Label(format_frame, text="质量:").grid(row=0, column=2, sticky=tk.W, padx=(20, 0))
        quality_scale = ttk.Scale(format_frame, from_=1, to=100, variable=self.output_quality,
                                 orient=tk.HORIZONTAL, length=100)
        quality_scale.grid(row=0, column=3, sticky=tk.EW, padx=(10, 0))
        ttk.Label(format_frame, textvariable=self.output_quality).grid(row=0, column=4, padx=(5, 0))
        
        # 保存选项
        save_frame = ttk.Frame(module_frame)
        save_frame.grid(row=2, column=0, sticky=tk.EW)
        
        ttk.Checkbutton(save_frame, text="保存提示词到文件", 
                       variable=self.save_prompt).grid(row=0, column=0, sticky=tk.W)
        
        # AI放大设置
        upscale_frame = ttk.LabelFrame(module_frame, text="🔍 AI放大", padding=10)
        upscale_frame.grid(row=3, column=0, sticky=tk.EW, pady=(10, 0))
        
        ttk.Checkbutton(upscale_frame, text="启用AI放大", 
                       variable=self.upscaling_enabled).grid(row=0, column=0, sticky=tk.W, pady=5)
        
        if self.upscaling_enabled.get():
            upscale_params_frame = ttk.Frame(upscale_frame)
            upscale_params_frame.grid(row=1, column=0, sticky=tk.EW, pady=(5, 0))
            upscale_params_frame.columnconfigure(1, weight=1)
            
            ttk.Label(upscale_params_frame, text="放大倍数:").grid(row=0, column=0, sticky=tk.W)
            ratio_combo = ttk.Combobox(upscale_params_frame, textvariable=self.upscale_ratio,
                                      values=[1.5, 2.0, 3.0, 4.0], width=10)
            ratio_combo.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
            
            ttk.Button(upscale_params_frame, text="使用SeedVR2.5", 
                      command=self.use_seedvr_upscale).grid(row=0, column=2)
        
        module_frame.columnconfigure(1, weight=1)
    
    def create_action_buttons(self, parent):
        """创建操作按钮"""
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=0, column=0, sticky=tk.EW, pady=(20, 0))
        button_frame.columnconfigure(4, weight=1)
        
        # 生成按钮
        generate_btn = ttk.Button(button_frame, text="🎨 开始编辑", 
                                command=self.start_image_editing,
                                style="Accent.TButton")
        generate_btn.grid(row=0, column=0, padx=(0, 10))
        
        # 预览按钮
        preview_btn = ttk.Button(button_frame, text="👁️ 预览效果", 
                               command=self.preview_editing)
        preview_btn.grid(row=0, column=1, padx=(0, 10))
        
        # 批量编辑按钮
        batch_btn = ttk.Button(button_frame, text="📚 批量编辑", 
                             command=self.batch_edit_images)
        batch_btn.grid(row=0, column=2, padx=(0, 10))
        
        # 清空按钮
        clear_btn = ttk.Button(button_frame, text="🗑️ 清空设置", 
                             command=self.clear_all_settings)
        clear_btn.grid(row=0, column=3, padx=(0, 10))
        
        # 进度显示
        self.progress_var = tk.StringVar(value="就绪")
        progress_label = ttk.Label(button_frame, textvariable=self.progress_var, 
                                  foreground="blue")
        progress_label.grid(row=0, column=5)
        
        # 进度条
        self.progress_bar = ttk.Progressbar(button_frame, mode='indeterminate')
        self.progress_bar.grid(row=0, column=4, padx=(10, 0))
    
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
    
    def select_input_image(self):
        """选择输入图片"""
        filename = filedialog.askopenfilename(
            title="选择输入图片",
            filetypes=[
                ("图片文件", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"),
                ("所有文件", "*.*")
            ]
        )
        if filename:
            self.input_image_path = filename
            self.display_input_image(filename)
    
    def display_input_image(self, image_path):
        """显示输入图片"""
        try:
            # 加载并显示图片
            image = Image.open(image_path)
            image.thumbnail((200, 200))  # 缩略图
            photo = ImageTk.PhotoImage(image)
            
            self.input_image_label.config(image=photo, text="")
            self.input_image_label.image = photo  # 保持引用
        except Exception as e:
            messagebox.showerror("错误", f"显示图片失败: {str(e)}")
    
    def capture_image(self):
        """拍照功能"""
        messagebox.showinfo("提示", "拍照功能开发中...")
    
    def add_reference_images(self):
        """添加参考图片"""
        if self.reference_mode.get() == "单图参考":
            filename = filedialog.askopenfilename(
                title="选择参考图片",
                filetypes=[
                    ("图片文件", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"),
                    ("所有文件", "*.*")
                ]
            )
            if filename:
                self.reference_images = [filename]
                self.display_reference_images()
        elif self.reference_mode.get() == "多图参考":
            filenames = filedialog.askopenfilenames(
                title="选择多个参考图片",
                filetypes=[
                    ("图片文件", "*.png *.jpg *.jpeg *.bmp *.tiff *.webp"),
                    ("所有文件", "*.*")
                ]
            )
            if filenames:
                self.reference_images = list(filenames)
                self.display_reference_images()
    
    def display_reference_images(self):
        """显示参考图片"""
        # 清空现有显示
        for widget in self.reference_images_frame.winfo_children():
            widget.destroy()
        
        # 显示参考图片缩略图
        for i, img_path in enumerate(self.reference_images):
            try:
                image = Image.open(img_path)
                image.thumbnail((80, 80))
                photo = ImageTk.PhotoImage(image)
                
                label = ttk.Label(self.reference_images_frame, image=photo)
                label.image = photo  # 保持引用
                label.grid(row=0, column=len(self.reference_images), padx=2)
            except Exception as e:
                ttk.Label(self.reference_images_frame, text=f"错误: {os.path.basename(img_path)}").grid(row=0, column=len(self.reference_images), padx=2)
    
    def browse_output_dir(self):
        """浏览输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.output_dir.set(directory)
    
    def use_seedvr_upscale(self):
        """使用SeedVR2.5放大"""
        messagebox.showinfo("提示", "SeedVR2.5放大功能开发中...")
    
    def start_image_editing(self):
        """开始图片编辑"""
        if not self.input_image_path:
            messagebox.showwarning("警告", "请先选择输入图片")
            return
        
        # 更新UI状态
        self.progress_var.set("正在编辑图片...")
        self.progress_bar.start()
        
        # 在后台线程执行编辑任务
        def edit_task():
            try:
                # 收集所有参数
                params = self.collect_editing_params()
                
                # 调用图片编辑后端
                result = self.call_image_editing_backend(params)
                
                # 更新UI状态
                self.parent.after(0, self.on_editing_complete, result)
            except Exception as e:
                self.parent.after(0, self.on_editing_error, str(e))
        
        threading.Thread(target=edit_task, daemon=True).start()
    
    def collect_editing_params(self):
        """收集编辑参数"""
        return {
            "model": self.model_var.get(),
            "input_image": self.input_image_path,
            "reference_images": self.reference_images,
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
            "editing_mode": self.editing_mode.get(),
            "face_preservation": self.face_preservation.get(),
            "local_feature_transfer": self.local_feature_transfer.get(),
            "redraw_strength": self.redraw_strength.get(),
            "style_filter_enabled": self.style_filter_enabled.get(),
            "style_filter": self.style_filter_var.get() if hasattr(self, 'style_filter_var') else "无滤镜",
            "upscaling_enabled": self.upscaling_enabled.get(),
            "upscale_ratio": self.upscale_ratio.get(),
            "output_format": self.output_format.get(),
            "output_quality": self.output_quality.get(),
            "output_dir": self.output_dir.get(),
            "save_prompt": self.save_prompt.get()
        }
    
    def call_image_editing_backend(self, params):
        """调用图片编辑后端"""
        # 模拟后端调用
        import time
        time.sleep(2)  # 模拟处理时间
        
        # 返回模拟结果
        return {
            "success": True,
            "output_path": os.path.join(params["output_dir"], "edited_image.png"),
            "message": "图片编辑完成"
        }
    
    def on_editing_complete(self, result):
        """编辑完成回调"""
        self.progress_bar.stop()
        if result["success"]:
            self.progress_var.set("编辑完成！")
            messagebox.showinfo("成功", f"图片编辑完成！\n保存路径: {result['output_path']}")
        else:
            self.progress_var.set("编辑失败")
            messagebox.showerror("错误", result.get("message", "未知错误"))
    
    def on_editing_error(self, error_msg):
        """编辑错误回调"""
        self.progress_bar.stop()
        self.progress_var.set("编辑失败")
        messagebox.showerror("错误", f"图片编辑失败: {error_msg}")
    
    def preview_editing(self):
        """预览编辑效果"""
        messagebox.showinfo("提示", "预览功能开发中...")
    
    def batch_edit_images(self):
        """批量编辑图片"""
        messagebox.showinfo("提示", "批量编辑功能开发中...")
    
    def clear_all_settings(self):
        """清空所有设置"""
        # 确认对话框
        if messagebox.askyesno("确认", "确定要清空所有设置吗？"):
            # 重置所有变量
            self.model_var.set("qwen_edit_2511")
            self.positive_text.delete(1.0, tk.END)
            self.negative_text.delete(1.0, tk.END)
            self.lora_files.clear()
            self.lora_weights.clear()
            self.controlnet_files.clear()
            self.controlnet_enabled.set(False)
            self.steps.set(20)
            self.cfg_scale.set(7.0)
            self.seed.set(-1)
            self.sampler.set("DPM++ 2M Karras")
            self.scheduler.set("Karras")
            self.resolution_preset.set("1280x720")
            self.custom_width.set(1280)
            self.custom_height.set(720)
            self.advanced_sampling.set(True)
            self.advanced_cfg.set(True)
            self.noise_injection.set(False)
            self.seed_enhance.set(False)
            self.reference_mode.set("单图参考")
            self.editing_mode.set("整体风格转换")
            self.face_preservation.set(True)
            self.local_feature_transfer.set(False)
            self.redraw_strength.set(0.3)
            self.style_filter_enabled.set(False)
            self.upscaling_enabled.set(False)
            self.upscale_ratio.set(2.0)
            self.output_format.set("PNG")
            self.output_quality.set(95)
            self.save_prompt.set(True)
            
            # 清空显示
            self.input_image_path = None
            self.reference_images.clear()
            self.input_image_label.config(image="", text="未选择图片")
            for widget in self.reference_images_frame.winfo_children():
                widget.destroy()
            
            # 更新LoRA显示
            self.update_lora_display()
            self.update_current_resolution()
            
            self.progress_var.set("设置已清空")
            messagebox.showinfo("成功", "所有设置已清空")
    
    def show(self):
        """显示组件界面"""
        try:
            if hasattr(self, 'main_frame'):
                self.main_frame.grid()
            self.log_message("✅ 图像编辑组件已显示")
        except Exception as e:
            self.log_message(f"❌ 显示组件失败: {e}")
    
    def hide(self):
        """隐藏组件界面"""
        try:
            if hasattr(self, 'main_frame'):
                self.main_frame.grid_remove()
            self.log_message("ℹ️ 图像编辑组件已隐藏")
        except Exception as e:
            self.log_message(f"❌ 隐藏组件失败: {e}")
    
    def log_message(self, message):
        """记录日志消息"""
        if hasattr(self, 'main_app') and hasattr(self.main_app, 'log'):
            self.main_app.log(message)
        else:
            print(f"[Image Editing] {message}")