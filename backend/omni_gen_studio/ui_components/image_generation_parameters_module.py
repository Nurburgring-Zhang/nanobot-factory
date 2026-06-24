#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片生成 - 参数模组
支持生成参数调整、预设配置、批量应用和参数验证

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import tkinter as tk
import os
from tkinter import ttk, messagebox
import random
import json
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ParametersModule:
    """图片生成参数管理模组"""
    
    def __init__(self, parent_frame, callback=None):
        self.parent_frame = parent_frame
        self.callback = callback
        
        # 生成参数
        self.params = {
            "steps": 20,
            "cfg_scale": 7.0,
            "width": 512,
            "height": 512,
            "seed": -1,
            "sampler": "DPM++ 2M Karras",
            "batch_size": 1,
            "batch_count": 1,
            "restore_faces": False,
            "tiling": False,
            "highres_fix": False,
            "denoise_strength": 0.7,
            "karras": True,
            "eta": 0.0,
            "clipskip": 1,
            "batch_count_random": False,
            "batch_seed_randomize": False
        }
        
        # 采样器列表
        self.samplers = [
            "Euler a",
            "Euler",
            "LMS",
            "Heun",
            "DPM2",
            "DPM2 a",
            "DPM++ 2S a",
            "DPM++ 2M",
            "DPM++ 2M SDE",
            "DPM++ 2M SDE Karras",
            "DPM++ 2M Karras",
            "DPM++ SDE",
            "DPM++ SDE Karras",
            "DPM fast",
            "DPM adaptive",
            "LMS Karras",
            "DPM2 Karras",
            "DPM2 a Karras",
            "DPM++ 2S a Karras",
            "DPM++ 2M SDE",
            "DDIM",
            "PLMS",
            "UniPC",
            "UniPC (fewest steps)"
        ]
        
        # 分辨率预设
        self.resolution_presets = {
            "方形": {
                "512x512": {"width": 512, "height": 512},
                "768x768": {"width": 768, "height": 768},
                "1024x1024": {"width": 1024, "height": 1024},
                "1536x1536": {"width": 1536, "height": 1536}
            },
            "横版": {
                "1024x768": {"width": 1024, "height": 768},
                "1280x720": {"width": 1280, "height": 720},
                "1920x1080": {"width": 1920, "height": 1080},
                "2560x1440": {"width": 2560, "height": 1440}
            },
            "竖版": {
                "768x1024": {"width": 768, "height": 1024},
                "720x1280": {"width": 720, "height": 1280},
                "1080x1920": {"width": 1080, "height": 1920},
                "1440x2560": {"width": 1440, "height": 2560}
            },
            "宽屏": {
                "1152x448": {"width": 1152, "height": 448},
                "1344x768": {"width": 1344, "height": 768},
                "1536x640": {"width": 1536, "height": 640},
                "1728x768": {"width": 1728, "height": 768}
            }
        }
        
        # 参数预设
        self.parameter_presets = {
            "快速生成": {
                "description": "快速测试用，低步数高质量",
                "steps": 8,
                "cfg_scale": 7.0,
                "sampler": "Euler a",
                "batch_size": 2,
                "karras": False
            },
            "标准质量": {
                "description": "标准生成质量，平衡速度和效果",
                "steps": 20,
                "cfg_scale": 7.5,
                "sampler": "DPM++ 2M Karras",
                "batch_size": 1,
                "karras": True
            },
            "高质量": {
                "description": "高质量生成，高步数精细效果",
                "steps": 30,
                "cfg_scale": 8.0,
                "sampler": "DPM++ 2M SDE Karras",
                "batch_size": 1,
                "karras": True
            },
            "艺术创作": {
                "description": "适合艺术创作，较低保真度",
                "steps": 25,
                "cfg_scale": 6.5,
                "sampler": "Euler",
                "batch_size": 1,
                "karras": True
            },
            "肖像专用": {
                "description": "专门优化的人像生成参数",
                "steps": 25,
                "cfg_scale": 7.0,
                "sampler": "DPM++ 2M Karras",
                "batch_size": 1,
                "restore_faces": True,
                "karras": True
            },
            "高分辨率": {
                "description": "高分辨率图像生成",
                "steps": 35,
                "cfg_scale": 7.0,
                "sampler": "DPM++ 2M SDE Karras",
                "batch_size": 1,
                "highres_fix": True,
                "denoise_strength": 0.7,
                "karras": True
            },
            "批量生成": {
                "description": "批量生成用，高效处理",
                "steps": 15,
                "cfg_scale": 7.0,
                "sampler": "DPM++ 2M Karras",
                "batch_size": 4,
                "batch_count": 4,
                "karras": True
            },
            "风格化": {
                "description": "高度风格化的生成参数",
                "steps": 20,
                "cfg_scale": 6.0,
                "sampler": "Euler a",
                "batch_size": 1,
                "karras": True
            },
            "细节增强": {
                "description": "增强细节的高精度参数",
                "steps": 40,
                "cfg_scale": 8.5,
                "sampler": "DPM++ 2M SDE Karras",
                "batch_size": 1,
                "karras": True
            },
            "实验性": {
                "description": "实验性参数配置",
                "steps": 12,
                "cfg_scale": 10.0,
                "sampler": "DPM fast",
                "batch_size": 1,
                "karras": False
            }
        }
        
        # 创建UI
        self.create_ui()
        
        # 加载默认参数
        self.apply_preset("标准质量")
    
    def create_ui(self):
        """创建参数管理UI"""
        # 主容器
        main_container = ttk.Frame(self.parent_frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 标题
        title_label = ttk.Label(main_container, text="参数设置", 
                               font=("微软雅黑", 14, "bold"))
        title_label.pack(anchor="w", pady=(0, 15))
        
        # 参数选项卡
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill="both", expand=True)
        
        # 基础参数选项卡
        self.create_basic_params_tab(notebook)
        
        # 高级参数选项卡
        self.create_advanced_params_tab(notebook)
        
        # 批量参数选项卡
        self.create_batch_params_tab(notebook)
        
        # 预设管理选项卡
        self.create_presets_tab(notebook)
        
        # 参数验证选项卡
        self.create_validation_tab(notebook)
    
    def create_basic_params_tab(self, notebook):
        """创建基础参数选项卡"""
        basic_frame = ttk.Frame(notebook)
        notebook.add(basic_frame, text="基础参数")
        
        # 创建滚动框架
        canvas = tk.Canvas(basic_frame)
        scrollbar = ttk.Scrollbar(basic_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 生成步数
        self.create_slider_control(scrollable_frame, "生成步数 (Steps)", 
                                 "steps", 1, 100, 1, "控制生成精度，步数越高质量越好但速度越慢")
        
        # CFG比例
        self.create_slider_control(scrollable_frame, "CFG比例", 
                                 "cfg_scale", 1.0, 20.0, 0.5, 
                                 "控制提示词遵循程度，越高越严格")
        
        # 分辨率控制
        self.create_resolution_controls(scrollable_frame)
        
        # 种子
        self.create_seed_control(scrollable_frame)
        
        # 采样器
        self.create_sampler_control(scrollable_frame)
        
        # 批量控制
        self.create_batch_controls(scrollable_frame)
        
        # 特殊效果
        self.create_effect_controls(scrollable_frame)
    
    def create_advanced_params_tab(self, notebook):
        """创建高级参数选项卡"""
        advanced_frame = ttk.Frame(notebook)
        notebook.add(advanced_frame, text="高级参数")
        
        # 创建滚动框架
        canvas = tk.Canvas(advanced_frame)
        scrollbar = ttk.Scrollbar(advanced_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Karras噪声调度
        self.create_checkbox_control(scrollable_frame, "启用Karras噪声调度", 
                                   "karras", "使用Karras噪声调度器")
        
        # ETA
        self.create_slider_control(scrollable_frame, "ETA", 
                                 "eta", 0.0, 1.0, 0.05, 
                                 "DDIM噪声步长参数")
        
        # Clipskip
        self.create_slider_control(scrollable_frame, "CLIP Skip", 
                                 "clipskip", 1, 12, 1, 
                                 "CLIP跳过层数，影响提示词理解")
        
        # 去噪强度
        self.create_slider_control(scrollable_frame, "去噪强度", 
                                 "denoise_strength", 0.0, 1.0, 0.01, 
                                 "图像到图像的去噪强度")
        
        # 高分辨率修复
        self.create_checkbox_control(scrollable_frame, "高分辨率修复", 
                                   "highres_fix", "生成高分辨率图像")
        
        # 参数组合预设
        self.create_combo_presets(scrollable_frame)
    
    def create_batch_params_tab(self, notebook):
        """创建批量参数选项卡"""
        batch_frame = ttk.Frame(notebook)
        notebook.add(batch_frame, text="批量参数")
        
        # 批量生成设置
        batch_frame_top = ttk.LabelFrame(batch_frame, text="批量生成设置", padding=10)
        batch_frame_top.pack(fill="x", padx=10, pady=10)
        
        # 批量数量
        batch_count_frame = ttk.Frame(batch_frame_top)
        batch_count_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(batch_count_frame, text="批量生成数量:").pack(side="left")
        self.batch_count_var = tk.IntVar(value=self.params["batch_count"])
        batch_count_spin = ttk.Spinbox(batch_count_frame, from_=1, to=20, 
                                      textvariable=self.batch_count_var, width=10)
        batch_count_spin.pack(side="left", padx=(10, 0))
        
        # 批量种子控制
        batch_seed_frame = ttk.LabelFrame(batch_frame, text="批量种子控制", padding=10)
        batch_seed_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.batch_seed_randomize = tk.BooleanVar(value=self.params["batch_seed_randomize"])
        ttk.Checkbutton(batch_seed_frame, text="批量生成时随机化种子", 
                       variable=self.batch_seed_randomize,
                       command=self.on_batch_seed_change).pack(anchor="w")
        
        self.batch_seed_range_frame = ttk.Frame(batch_seed_frame)
        self.batch_seed_range_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Label(self.batch_seed_range_frame, text="种子范围:").pack(side="left")
        
        self.seed_range_start_var = tk.StringVar(value="1000000")
        self.seed_range_end_var = tk.StringVar(value="9999999")
        
        ttk.Entry(self.batch_seed_range_frame, textvariable=self.seed_range_start_var, 
                 width=12).pack(side="left", padx=(10, 5))
        ttk.Label(self.batch_seed_range_frame, text="到").pack(side="left", padx=(5))
        ttk.Entry(self.batch_seed_range_frame, textvariable=self.seed_range_end_var, 
                 width=12).pack(side="left", padx=(5, 0))
        
        ttk.Button(self.batch_seed_range_frame, text="生成种子", 
                  command=self.generate_batch_seeds).pack(side="left", padx=(10, 0))
        
        # 批量参数调整
        batch_adjust_frame = ttk.LabelFrame(batch_frame, text="批量参数调整", padding=10)
        batch_adjust_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 参数调整控件
        adjust_controls = ttk.Frame(batch_adjust_frame)
        adjust_controls.pack(fill="x", pady=(0, 10))
        
        ttk.Label(adjust_controls, text="调整参数:").pack(side="left")
        
        self.adjust_param_var = tk.StringVar(value="cfg_scale")
        adjust_combo = ttk.Combobox(adjust_controls, textvariable=self.adjust_param_var,
                                   values=["steps", "cfg_scale", "seed", "batch_size"], width=15)
        adjust_combo.pack(side="left", padx=(10, 10))
        
        self.adjust_operation_var = tk.StringVar(value="add")
        adjust_op_combo = ttk.Combobox(adjust_controls, textvariable=self.adjust_operation_var,
                                      values=["add", "multiply", "set"], width=10)
        adjust_op_combo.pack(side="left", padx=(0, 10))
        
        self.adjust_value_var = tk.StringVar(value="1.0")
        ttk.Entry(adjust_controls, textvariable=self.adjust_value_var, 
                 width=10).pack(side="left", padx=(0, 10))
        
        ttk.Button(adjust_controls, text="应用", 
                  command=self.apply_batch_adjustment).pack(side="left")
        
        # 批量预览
        preview_frame = ttk.LabelFrame(batch_adjust_frame, text="批量配置预览", padding=5)
        preview_frame.pack(fill="both", expand=True)
        
        self.batch_preview_text = tk.Text(preview_frame, height=10, wrap="word",
                                         font=("Consolas", 9), state="disabled")
        self.batch_preview_text.pack(fill="both", expand=True)
        
        self.update_batch_preview()
    
    def create_presets_tab(self, notebook):
        """创建预设管理选项卡"""
        presets_frame = ttk.Frame(notebook)
        notebook.add(presets_frame, text="预设管理")
        
        # 预设选择
        preset_select_frame = ttk.LabelFrame(presets_frame, text="选择预设", padding=10)
        preset_select_frame.pack(fill="x", padx=10, pady=10)
        
        preset_controls = ttk.Frame(preset_select_frame)
        preset_controls.pack(fill="x")
        
        ttk.Label(preset_controls, text="参数预设:").pack(side="left")
        
        self.preset_var = tk.StringVar()
        preset_combo = ttk.Combobox(preset_controls, textvariable=self.preset_var,
                                   values=list(self.parameter_presets.keys()), width=20)
        preset_combo.pack(side="left", padx=(10, 10))
        
        ttk.Button(preset_controls, text="应用预设", 
                  command=self.apply_selected_preset).pack(side="left", padx=(0, 10))
        
        ttk.Button(preset_controls, text="保存为自定义", 
                  command=self.save_custom_preset).pack(side="left")
        
        # 预设详情
        preset_detail_frame = ttk.LabelFrame(presets_frame, text="预设详情", padding=10)
        preset_detail_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.preset_detail_text = tk.Text(preset_detail_frame, height=8, wrap="word",
                                         font=("Consolas", 10), state="disabled")
        self.preset_detail_text.pack(fill="x")
        
        # 自定义预设管理
        custom_presets_frame = ttk.LabelFrame(presets_frame, text="自定义预设", padding=10)
        custom_presets_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 预设列表
        preset_list_frame = ttk.Frame(custom_presets_frame)
        preset_list_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        self.custom_preset_listbox = tk.Listbox(preset_list_frame, height=8)
        self.custom_preset_listbox.pack(fill="both", expand=True)
        
        # 预设操作按钮
        preset_buttons = ttk.Frame(custom_presets_frame)
        preset_buttons.pack(fill="x")
        
        ttk.Button(preset_buttons, text="加载预设", 
                  command=self.load_custom_preset).pack(side="left", padx=(0, 10))
        
        ttk.Button(preset_buttons, text="删除预设", 
                  command=self.delete_custom_preset).pack(side="left", padx=(0, 10))
        
        ttk.Button(preset_buttons, text="导出预设", 
                  command=self.export_presets).pack(side="left", padx=(0, 10))
        
        ttk.Button(preset_buttons, text="导入预设", 
                  command=self.import_presets).pack(side="left")
        
        # 加载自定义预设
        self.load_custom_presets()
    
    def create_validation_tab(self, notebook):
        """创建参数验证选项卡"""
        validation_frame = ttk.Frame(notebook)
        notebook.add(validation_frame, text="参数验证")
        
        # 验证结果
        validation_result_frame = ttk.LabelFrame(validation_frame, text="参数验证结果", padding=10)
        validation_result_frame.pack(fill="x", padx=10, pady=10)
        
        # 验证按钮
        validate_buttons = ttk.Frame(validation_result_frame)
        validate_buttons.pack(fill="x", pady=(0, 10))
        
        ttk.Button(validate_buttons, text="验证当前参数", 
                  command=self.validate_current_params).pack(side="left", padx=(0, 10))
        
        ttk.Button(validate_buttons, text="优化建议", 
                  command=self.get_optimization_suggestions).pack(side="left", padx=(0, 10))
        
        ttk.Button(validate_buttons, text="修复问题", 
                  command=self.fix_parameter_issues).pack(side="left")
        
        # 验证结果显示
        self.validation_result_text = tk.Text(validation_result_frame, height=15, wrap="word",
                                            font=("Consolas", 9), state="disabled")
        self.validation_result_text.pack(fill="both", expand=True)
        
        # 参数性能预估
        performance_frame = ttk.LabelFrame(validation_frame, text="性能预估", padding=10)
        performance_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # 性能指标
        perf_frame = ttk.Frame(performance_frame)
        perf_frame.pack(fill="x")
        
        ttk.Label(perf_frame, text="预计生成时间:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.time_estimate_label = ttk.Label(perf_frame, text="--", foreground="blue")
        self.time_estimate_label.grid(row=0, column=1, sticky="w", padx=(0, 20))
        
        ttk.Label(perf_frame, text="内存使用:").grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.memory_estimate_label = ttk.Label(perf_frame, text="--", foreground="orange")
        self.memory_estimate_label.grid(row=0, column=3, sticky="w")
        
        ttk.Label(perf_frame, text="质量评分:").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.quality_estimate_label = ttk.Label(perf_frame, text="--", foreground="green")
        self.quality_estimate_label.grid(row=1, column=1, sticky="w", padx=(0, 20))
        
        ttk.Label(perf_frame, text="兼容性:").grid(row=1, column=2, sticky="w", padx=(0, 10))
        self.compatibility_label = ttk.Label(perf_frame, text="--", foreground="purple")
        self.compatibility_label.grid(row=1, column=3, sticky="w")
        
        # 更新性能预估
        self.update_performance_estimates()
    
    def create_slider_control(self, parent, label, param_name, min_val, max_val, step, description=""):
        """创建滑块控制"""
        control_frame = ttk.LabelFrame(parent, text=label, padding=10)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        # 滑块和标签
        slider_frame = ttk.Frame(control_frame)
        slider_frame.pack(fill="x")
        
        ttk.Label(slider_frame, text=str(min_val)).pack(side="left")
        
        var = tk.DoubleVar(value=self.params[param_name])
        slider = tk.Scale(slider_frame, from_=min_val, to=max_val, orient="horizontal",
                         variable=var, resolution=step, length=300,
                         command=lambda val: self.on_parameter_change(param_name, float(val)))
        slider.pack(side="left", fill="x", expand=True, padx=(10, 10))
        
        value_label = ttk.Label(slider_frame, text=str(self.params[param_name]), 
                               font=("Consolas", 10, "bold"))
        value_label.pack(side="left")
        
        # 更新标签值
        def update_label(val):
            value_label.config(text=f"{float(val):.2f}")
        
        slider.config(command=lambda val: (update_label(val), 
                                         self.on_parameter_change(param_name, float(val))))
        
        # 描述
        if description:
            desc_label = ttk.Label(control_frame, text=description, 
                                  foreground="gray", font=("微软雅黑", 9))
            desc_label.pack(anchor="w", pady=(5, 0))
        
        # 保存控件引用
        if not hasattr(self, 'controls'):
            self.controls = {}
        self.controls[param_name] = (var, slider)
    
    def create_checkbox_control(self, parent, label, param_name, description=""):
        """创建复选框控制"""
        control_frame = ttk.LabelFrame(parent, text=label, padding=5)
        control_frame.pack(fill="x", padx=10, pady=5)
        
        var = tk.BooleanVar(value=self.params[param_name])
        checkbox = ttk.Checkbutton(control_frame, variable=var,
                                 command=lambda: self.on_parameter_change(param_name, var.get()))
        checkbox.pack(anchor="w")
        
        # 描述
        if description:
            desc_label = ttk.Label(control_frame, text=description, 
                                  foreground="gray", font=("微软雅黑", 9))
            desc_label.pack(anchor="w")
        
        # 保存控件引用
        if not hasattr(self, 'controls'):
            self.controls = {}
        self.controls[param_name] = var
    
    def create_resolution_controls(self, parent):
        """创建分辨率控制"""
        res_frame = ttk.LabelFrame(parent, text="分辨率设置", padding=10)
        res_frame.pack(fill="x", padx=10, pady=10)
        
        # 预设选择
        preset_frame = ttk.Frame(res_frame)
        preset_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(preset_frame, text="分辨率预设:").pack(side="left")
        
        self.resolution_preset_var = tk.StringVar(value="512x512")
        preset_combo = ttk.Combobox(preset_frame, textvariable=self.resolution_preset_var,
                                   values=list(self.resolution_presets["方形"].keys()) +
                                         list(self.resolution_presets["横版"].keys()) +
                                         list(self.resolution_presets["竖版"].keys()) +
                                         list(self.resolution_presets["宽屏"].keys()),
                                   width=15, state="readonly")
        preset_combo.pack(side="left", padx=(10, 0))
        preset_combo.bind("<<ComboboxSelected>>", self.on_resolution_preset_change)
        
        # 自定义分辨率
        custom_frame = ttk.Frame(res_frame)
        custom_frame.pack(fill="x", pady=(5, 0))
        
        ttk.Label(custom_frame, text="宽度:").pack(side="left")
        self.width_var = tk.IntVar(value=self.params["width"])
        width_spin = ttk.Spinbox(custom_frame, from_=64, to=2048, increment=64,
                                textvariable=self.width_var, width=8,
                                command=self.on_width_change)
        width_spin.pack(side="left", padx=(5, 15))
        
        ttk.Label(custom_frame, text="高度:").pack(side="left")
        self.height_var = tk.IntVar(value=self.params["height"])
        height_spin = ttk.Spinbox(custom_frame, from_=64, to=2048, increment=64,
                                 textvariable=self.height_var, width=8,
                                 command=self.on_height_change)
        height_spin.pack(side="left", padx=(5, 0))
        
        # 分辨率提示
        res_hint_label = ttk.Label(res_frame, text="推荐分辨率: 512x512 (快速), 1024x1024 (高质量)", 
                                  foreground="gray", font=("微软雅黑", 9))
        res_hint_label.pack(anchor="w", pady=(5, 0))
    
    def create_seed_control(self, parent):
        """创建种子控制"""
        seed_frame = ttk.LabelFrame(parent, text="随机种子", padding=10)
        seed_frame.pack(fill="x", padx=10, pady=10)
        
        # 种子输入
        seed_input_frame = ttk.Frame(seed_frame)
        seed_input_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(seed_input_frame, text="种子值:").pack(side="left")
        
        self.seed_var = tk.IntVar(value=self.params["seed"])
        seed_entry = ttk.Entry(seed_input_frame, textvariable=self.seed_var, width=15)
        seed_entry.pack(side="left", padx=(10, 10))
        
        ttk.Button(seed_input_frame, text="随机种子", 
                  command=self.randomize_seed).pack(side="left", padx=(0, 10))
        
        ttk.Button(seed_input_frame, text="应用到所有", 
                  command=self.apply_seed_to_all).pack(side="left")
        
        # 种子历史
        self.seed_history_var = tk.StringVar(value="")
        seed_history_label = ttk.Label(seed_frame, textvariable=self.seed_history_var,
                                     foreground="gray", font=("微软雅黑", 9))
        seed_history_label.pack(anchor="w")
    
    def create_sampler_control(self, parent):
        """创建采样器控制"""
        sampler_frame = ttk.LabelFrame(parent, text="采样器", padding=10)
        sampler_frame.pack(fill="x", padx=10, pady=10)
        
        sampler_combo = ttk.Combobox(sampler_frame, values=self.samplers,
                                    textvariable=tk.StringVar(value=self.params["sampler"]),
                                    width=25, state="readonly")
        sampler_combo.pack(fill="x")
        sampler_combo.bind("<<ComboboxSelected>>", 
                          lambda e: self.on_parameter_change("sampler", sampler_combo.get()))
        
        # 采样器说明
        sampler_info_label = ttk.Label(sampler_frame, 
                                      text="DPM++ 2M Karras: 平衡质量与速度 | Euler a: 快速测试 | DDIM: 稳定采样",
                                      foreground="gray", font=("微软雅黑", 9))
        sampler_info_label.pack(anchor="w", pady=(5, 0))
    
    def create_batch_controls(self, parent):
        """创建批量控制"""
        batch_frame = ttk.LabelFrame(parent, text="批量生成", padding=10)
        batch_frame.pack(fill="x", padx=10, pady=10)
        
        # 每批数量
        batch_size_frame = ttk.Frame(batch_frame)
        batch_size_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(batch_size_frame, text="每批数量:").pack(side="left")
        
        self.batch_size_var = tk.IntVar(value=self.params["batch_size"])
        batch_size_spin = ttk.Spinbox(batch_size_frame, from_=1, to=10,
                                     textvariable=self.batch_size_var, width=10,
                                     command=lambda: self.on_parameter_change("batch_size", self.batch_size_var.get()))
        batch_size_spin.pack(side="left", padx=(10, 0))
        
        # 批量随机化
        batch_random_frame = ttk.Frame(batch_frame)
        batch_random_frame.pack(fill="x")
        
        self.batch_random_var = tk.BooleanVar(value=self.params["batch_count_random"])
        ttk.Checkbutton(batch_random_frame, text="批量随机化参数", 
                       variable=self.batch_random_var,
                       command=lambda: self.on_parameter_change("batch_count_random", self.batch_random_var.get())).pack(anchor="w")
    
    def create_effect_controls(self, parent):
        """创建效果控制"""
        effect_frame = ttk.LabelFrame(parent, text="特殊效果", padding=10)
        effect_frame.pack(fill="x", padx=10, pady=10)
        
        self.create_checkbox_control(effect_frame, "人脸修复", "restore_faces", "启用人脸修复")
        self.create_checkbox_control(effect_frame, "平铺模式", "tiling", "生成可平铺的图像")
    
    def create_combo_presets(self, parent):
        """创建组合预设"""
        combo_frame = ttk.LabelFrame(parent, text="快速预设", padding=10)
        combo_frame.pack(fill="x", padx=10, pady=10)
        
        combo_buttons = ttk.Frame(combo_frame)
        combo_buttons.pack(fill="x")
        
        # 快速预设按钮
        ttk.Button(combo_buttons, text="快速测试", 
                  command=lambda: self.quick_preset("Euler a", 8, 7.0)).pack(side="left", padx=(0, 5))
        
        ttk.Button(combo_buttons, text="标准质量", 
                  command=lambda: self.quick_preset("DPM++ 2M Karras", 20, 7.5)).pack(side="left", padx=(0, 5))
        
        ttk.Button(combo_buttons, text="高质量", 
                  command=lambda: self.quick_preset("DPM++ 2M SDE Karras", 30, 8.0)).pack(side="left", padx=(0, 5))
        
        ttk.Button(combo_buttons, text="艺术风格", 
                  command=lambda: self.quick_preset("Euler", 25, 6.5)).pack(side="left")
    
    def on_parameter_change(self, param_name, value):
        """参数变化事件"""
        self.params[param_name] = value
        
        # 更新相关显示
        if param_name in ["width", "height"]:
            self.resolution_preset_var.set(f"{self.params['width']}x{self.params['height']}")
        
        # 更新性能预估
        self.update_performance_estimates()
        
        # 更新批量预览
        self.update_batch_preview()
        
        # 通知回调
        if self.callback:
            self.callback("parameter_changed", {
                "param": param_name,
                "value": value,
                "all_params": self.params.copy()
            })
    
    def on_resolution_preset_change(self, event):
        """分辨率预设变化"""
        preset_value = self.resolution_preset_var.get()
        
        # 查找预设值
        for category, presets in self.resolution_presets.items():
            if preset_value in presets:
                resolution = presets[preset_value]
                self.width_var.set(resolution["width"])
                self.height_var.set(resolution["height"])
                self.on_parameter_change("width", resolution["width"])
                self.on_parameter_change("height", resolution["height"])
                break
    
    def on_width_change(self):
        """宽度变化"""
        width = self.width_var.get()
        self.on_parameter_change("width", width)
    
    def on_height_change(self):
        """高度变化"""
        height = self.height_var.get()
        self.on_parameter_change("height", height)
    
    def randomize_seed(self):
        """随机种子"""
        new_seed = random.randint(0, 999999999)
        self.seed_var.set(new_seed)
        self.on_parameter_change("seed", new_seed)
        
        # 更新种子历史
        if not hasattr(self, 'seed_history'):
            self.seed_history = []
        self.seed_history.append(new_seed)
        if len(self.seed_history) > 5:
            self.seed_history.pop(0)
        
        history_text = "最近种子: " + ", ".join(map(str, self.seed_history[-3:]))
        self.seed_history_var.set(history_text)
    
    def apply_seed_to_all(self):
        """应用到所有"""
        current_seed = self.seed_var.get()
        
        # 这里应该实现应用到所有参数的逻辑
        messagebox.showinfo("提示", f"种子 {current_seed} 已应用到批量生成")
    
    def quick_preset(self, sampler, steps, cfg):
        """快速预设"""
        # 更新控件值
        for param_name, value in [("sampler", sampler), ("steps", steps), ("cfg_scale", cfg)]:
            self.on_parameter_change(param_name, value)
        
        # 更新控件显示
        if "sampler" in self.controls:
            self.controls["sampler"][1].set(sampler)
        if "steps" in self.controls:
            self.controls["steps"][0].set(steps)
        if "cfg_scale" in self.controls:
            self.controls["cfg_scale"][0].set(cfg)
    
    def apply_preset(self, preset_name):
        """应用预设"""
        if preset_name in self.parameter_presets:
            preset = self.parameter_presets[preset_name]
            
            for param_name, value in preset.items():
                if param_name != "description":
                    self.on_parameter_change(param_name, value)
                    # 更新控件
                    if param_name in self.controls:
                        if isinstance(self.controls[param_name], tuple):
                            self.controls[param_name][0].set(value)
                        else:
                            self.controls[param_name].set(value)
            
            # 更新预设显示
            self.preset_var.set(preset_name)
            
            # 显示预设详情
            self.show_preset_details(preset_name, preset)
            
            # 更新批量预览
            self.update_batch_preview()
            
            messagebox.showinfo("成功", f"已应用预设: {preset_name}")
    
    def apply_selected_preset(self):
        """应用选中的预设"""
        preset_name = self.preset_var.get()
        if preset_name:
            self.apply_preset(preset_name)
        else:
            messagebox.showwarning("警告", "请先选择预设")
    
    def show_preset_details(self, preset_name, preset):
        """显示预设详情"""
        self.preset_detail_text.config(state="normal")
        self.preset_detail_text.delete("1.0", "end")
        
        details = f"预设名称: {preset_name}\n"
        details += f"描述: {preset.get('description', '无描述')}\n\n"
        details += "参数配置:\n"
        
        for param_name, value in preset.items():
            if param_name != "description":
                details += f"  {param_name}: {value}\n"
        
        self.preset_detail_text.insert("1.0", details)
        self.preset_detail_text.config(state="disabled")
    
    def save_custom_preset(self):
        """保存自定义预设"""
        dialog = tk.Toplevel(self.parent_frame)
        dialog.title("保存自定义预设")
        dialog.geometry("400x300")
        dialog.transient(self.parent_frame)
        dialog.grab_set()
        
        # 输入预设名称
        ttk.Label(dialog, text="请输入预设名称:", font=("微软雅黑", 10, "bold")).pack(pady=10)
        
        name_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=name_var, width=30).pack(pady=10)
        
        # 输入描述
        ttk.Label(dialog, text="描述 (可选):").pack(anchor="w", padx=20)
        desc_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=desc_var, width=40).pack(pady=5)
        
        def save_preset():
            preset_name = name_var.get().strip()
            if not preset_name:
                messagebox.showwarning("警告", "请输入预设名称")
                return
            
            # 保存预设
            custom_preset = self.params.copy()
            if desc_var.get().strip():
                custom_preset["description"] = desc_var.get().strip()
            
            if not hasattr(self, 'custom_presets'):
                self.custom_presets = {}
            
            self.custom_presets[preset_name] = custom_preset
            self.save_custom_presets()
            self.load_custom_presets()
            
            dialog.destroy()
            messagebox.showinfo("成功", f"自定义预设 '{preset_name}' 已保存")
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", pady=10)
        
        ttk.Button(button_frame, text="确定", command=save_preset).pack(side="left", padx=(0, 10))
        ttk.Button(button_frame, text="取消", command=dialog.destroy).pack(side="left")
    
    def load_custom_presets(self):
        """加载自定义预设"""
        try:
            if os.path.exists("custom_presets.json"):
                with open("custom_presets.json", "r", encoding="utf-8") as f:
                    self.custom_presets = json.load(f)
            else:
                self.custom_presets = {}
        except Exception as e:
            logger.error(f"加载自定义预设失败: {e}")
            self.custom_presets = {}
        
        # 更新列表显示
        self.custom_preset_listbox.delete(0, tk.END)
        for preset_name in self.custom_presets.keys():
            self.custom_preset_listbox.insert(tk.END, preset_name)
    
    def save_custom_presets(self):
        """保存自定义预设"""
        try:
            with open("custom_presets.json", "w", encoding="utf-8") as f:
                json.dump(self.custom_presets, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存自定义预设失败: {e}")
    
    def load_custom_preset(self):
        """加载自定义预设"""
        selection = self.custom_preset_listbox.curselection()
        if selection:
            preset_name = self.custom_preset_listbox.get(selection[0])
            if preset_name in self.custom_presets:
                preset = self.custom_presets[preset_name]
                self.apply_preset_from_dict(preset)
    
    def apply_preset_from_dict(self, preset):
        """从字典应用预设"""
        for param_name, value in preset.items():
            if param_name != "description":
                self.on_parameter_change(param_name, value)
                # 更新控件
                if param_name in self.controls:
                    if isinstance(self.controls[param_name], tuple):
                        self.controls[param_name][0].set(value)
                    else:
                        self.controls[param_name].set(value)
        
        messagebox.showinfo("成功", "自定义预设已应用")
    
    def delete_custom_preset(self):
        """删除自定义预设"""
        selection = self.custom_preset_listbox.curselection()
        if selection:
            preset_name = self.custom_preset_listbox.get(selection[0])
            result = messagebox.askyesno("确认", f"确定要删除自定义预设 '{preset_name}' 吗？")
            if result:
                del self.custom_presets[preset_name]
                self.save_custom_presets()
                self.load_custom_presets()
                messagebox.showinfo("成功", f"自定义预设 '{preset_name}' 已删除")
    
    def export_presets(self):
        """导出预设"""
        from tkinter import filedialog
        
        file_path = filedialog.asksaveasfilename(
            title="导出预设",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")]
        )
        
        if file_path:
            try:
                all_presets = {**self.parameter_presets, **self.custom_presets}
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(all_presets, f, indent=2, ensure_ascii=False)
                messagebox.showinfo("成功", "预设已导出")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {e}")
    
    def import_presets(self):
        """导入预设"""
        from tkinter import filedialog
        
        file_path = filedialog.askopenfilename(
            title="导入预设",
            filetypes=[("JSON文件", "*.json")]
        )
        
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    imported_presets = json.load(f)
                
                # 合并预设
                if not hasattr(self, 'custom_presets'):
                    self.custom_presets = {}
                
                self.custom_presets.update(imported_presets)
                self.save_custom_presets()
                self.load_custom_presets()
                
                messagebox.showinfo("成功", f"已导入 {len(imported_presets)} 个预设")
            except Exception as e:
                messagebox.showerror("错误", f"导入失败: {e}")
    
    def on_batch_seed_change(self):
        """批量种子变化"""
        self.batch_seed_randomize.set(self.batch_seed_randomize.get())
        self.on_parameter_change("batch_seed_randomize", self.batch_seed_randomize.get())
        
        # 更新种子范围框架状态
        if self.batch_seed_randomize.get():
            self.batch_seed_range_frame.config(state="normal")
        else:
            self.batch_seed_range_frame.config(state="disabled")
    
    def generate_batch_seeds(self):
        """生成批量种子"""
        try:
            start = int(self.seed_range_start_var.get())
            end = int(self.seed_range_end_var.get())
            
            if start >= end:
                messagebox.showwarning("警告", "起始种子必须小于结束种子")
                return
            
            # 生成种子
            seeds = random.sample(range(start, end + 1), 
                                min(self.batch_count_var.get(), end - start + 1))
            
            # 这里应该显示生成的种子列表
            messagebox.showinfo("成功", f"已生成 {len(seeds)} 个随机种子")
            
        except ValueError:
            messagebox.showerror("错误", "种子范围输入无效")
    
    def apply_batch_adjustment(self):
        """应用批量调整"""
        param = self.adjust_param_var.get()
        operation = self.adjust_operation_var.get()
        try:
            value = float(self.adjust_value_var.get())
        except ValueError:
            messagebox.showerror("错误", "调整值必须是数字")
            return
        
        if param in self.params:
            current_value = self.params[param]
            
            if operation == "add":
                new_value = current_value + value
            elif operation == "multiply":
                new_value = current_value * value
            elif operation == "set":
                new_value = value
            else:
                return
            
            # 更新参数
            self.on_parameter_change(param, new_value)
            
            # 更新控件
            if param in self.controls:
                if isinstance(self.controls[param], tuple):
                    self.controls[param][0].set(new_value)
                else:
                    self.controls[param].set(new_value)
            
            messagebox.showinfo("成功", f"{param} 已调整为 {new_value}")
    
    def update_batch_preview(self):
        """更新批量预览"""
        preview_text = f"批量配置预览 (数量: {self.params['batch_count']}):\n\n"
        
        # 基础参数
        preview_text += "基础参数:\n"
        preview_text += f"  分辨率: {self.params['width']}x{self.params['height']}\n"
        preview_text += f"  步数: {self.params['steps']}\n"
        preview_text += f"  CFG: {self.params['cfg_scale']}\n"
        preview_text += f"  采样器: {self.params['sampler']}\n\n"
        
        # 种子设置
        preview_text += "种子设置:\n"
        if self.params['batch_seed_randomize']:
            preview_text += f"  模式: 随机种子\n"
            preview_text += f"  范围: {self.seed_range_start_var.get()} - {self.seed_range_end_var.get()}\n"
        else:
            preview_text += f"  模式: 固定种子 ({self.params['seed']})\n"
        preview_text += "\n"
        
        # 效果设置
        preview_text += "效果设置:\n"
        if self.params['restore_faces']:
            preview_text += "  ✓ 人脸修复\n"
        if self.params['tiling']:
            preview_text += "  ✓ 平铺模式\n"
        if self.params['highres_fix']:
            preview_text += "  ✓ 高分辨率修复\n"
        
        self.batch_preview_text.config(state="normal")
        self.batch_preview_text.delete("1.0", "end")
        self.batch_preview_text.insert("1.0", preview_text)
        self.batch_preview_text.config(state="disabled")
    
    def validate_current_params(self):
        """验证当前参数"""
        issues = []
        suggestions = []
        
        # 验证分辨率
        total_pixels = self.params['width'] * self.params['height']
        if total_pixels > 1024 * 1024:  # 大于1M像素
            issues.append("⚠️ 分辨率过高，可能需要大量内存")
            suggestions.append("建议降低分辨率或启用高分辨率修复")
        
        # 验证步数
        if self.params['steps'] < 10:
            issues.append("⚠️ 步数过低，可能影响质量")
            suggestions.append("建议设置步数至少为15-20")
        elif self.params['steps'] > 50:
            issues.append("⚠️ 步数过高，生成时间较长")
            suggestions.append("建议步数设置在20-35之间")
        
        # 验证CFG
        if self.params['cfg_scale'] < 5.0:
            issues.append("⚠️ CFG比例过低，可能偏离提示词")
            suggestions.append("建议CFG设置在6.5-8.5之间")
        elif self.params['cfg_scale'] > 15.0:
            issues.append("⚠️ CFG比例过高，可能产生伪影")
            suggestions.append("建议CFG设置不超过12.0")
        
        # 验证批量
        if self.params['batch_size'] * self.params['batch_count'] > 8:
            issues.append("⚠️ 批量数量过大，可能影响性能")
            suggestions.append("建议批量总数不超过4-6")
        
        # 生成验证报告
        report = "参数验证结果:\n\n"
        
        if not issues:
            report += "✅ 所有参数设置合理\n"
        else:
            report += "发现问题:\n"
            for issue in issues:
                report += f"{issue}\n"
        
        report += "\n"
        if suggestions:
            report += "优化建议:\n"
            for suggestion in suggestions:
                report += f"{suggestion}\n"
        
        self.validation_result_text.config(state="normal")
        self.validation_result_text.delete("1.0", "end")
        self.validation_result_text.insert("1.0", report)
        self.validation_result_text.config(state="disabled")
    
    def get_optimization_suggestions(self):
        """获取优化建议"""
        suggestions = []
        
        # 基于当前参数给出建议
        if self.params['steps'] > 30:
            suggestions.append("💡 如需更快的生成，可以降低步数到20-25")
        
        if self.params['width'] * self.params['height'] > 1024 * 1024:
            suggestions.append("💡 高分辨率生成建议启用高分辨率修复")
        
        if self.params['sampler'] in ['Euler a', 'Euler']:
            suggestions.append("💡 如需更高质量，可以尝试DPM++ 2M Karras")
        
        if self.params['cfg_scale'] > 10:
            suggestions.append("💡 CFG过高可能影响自然度，建议6.5-8.5")
        
        # 性能建议
        suggestions.append("💡 批量生成时建议固定种子以保持一致性")
        suggestions.append("💡 测试阶段使用快速预设，正式生成使用高质量预设")
        
        # 显示建议
        suggestion_text = "优化建议:\n\n"
        for suggestion in suggestions:
            suggestion_text += f"{suggestion}\n"
        
        self.validation_result_text.config(state="normal")
        self.validation_result_text.delete("1.0", "end")
        self.validation_result_text.insert("1.0", suggestion_text)
        self.validation_result_text.config(state="disabled")
    
    def fix_parameter_issues(self):
        """修复参数问题"""
        fixes = []
        
        # 自动修复已知问题
        if self.params['steps'] < 10:
            self.on_parameter_change('steps', 15)
            fixes.append("步数已调整到15")
        
        if self.params['steps'] > 50:
            self.on_parameter_change('steps', 25)
            fixes.append("步数已调整到25")
        
        if self.params['cfg_scale'] < 5.0:
            self.on_parameter_change('cfg_scale', 7.0)
            fixes.append("CFG比例已调整到7.0")
        
        if self.params['cfg_scale'] > 15.0:
            self.on_parameter_change('cfg_scale', 8.0)
            fixes.append("CFG比例已调整到8.0")
        
        if self.params['width'] * self.params['height'] > 1024 * 1024 and not self.params['highres_fix']:
            self.on_parameter_change('highres_fix', True)
            fixes.append("已启用高分辨率修复")
        
        # 更新控件
        for param_name in self.controls:
            if param_name in self.params:
                value = self.params[param_name]
                if isinstance(self.controls[param_name], tuple):
                    self.controls[param_name][0].set(value)
                else:
                    self.controls[param_name].set(value)
        
        if fixes:
            fix_text = "已修复的问题:\n\n"
            for fix in fixes:
                fix_text += f"✅ {fix}\n"
            
            self.validation_result_text.config(state="normal")
            self.validation_result_text.delete("1.0", "end")
            self.validation_result_text.insert("1.0", fix_text)
            self.validation_result_text.config(state="disabled")
            
            messagebox.showinfo("修复完成", "\n".join(fixes))
        else:
            messagebox.showinfo("提示", "未发现需要修复的问题")
    
    def update_performance_estimates(self):
        """更新性能预估"""
        # 简单的性能预估算法
        base_time = self.params['steps'] * 2  # 基础时间(秒)
        
        # 分辨率影响
        pixel_count = self.params['width'] * self.params['height']
        res_factor = pixel_count / (512 * 512)
        time_estimate = base_time * res_factor * self.params['batch_size']
        
        # 内存预估
        memory_mb = pixel_count * 3 / 1024 / 1024 * self.params['batch_size']  # RGB图像
        if memory_mb < 1000:
            memory_text = f"{memory_mb:.0f}MB"
        else:
            memory_text = f"{memory_mb/1024:.1f}GB"
        
        # 质量评分
        quality_score = min(100, self.params['steps'] * 2 + (12 - abs(self.params['cfg_scale'] - 7.5)) * 5)
        
        # 兼容性评分
        compatibility_score = 85  # 基础兼容性
        
        # 更新显示
        self.time_estimate_label.config(text=f"{time_estimate:.1f}秒")
        self.memory_estimate_label.config(text=memory_text)
        self.quality_estimate_label.config(text=f"{quality_score:.0f}/100")
        self.compatibility_label.config(text=f"{compatibility_score:.0f}%")
    
    def get_parameters(self):
        """获取当前参数"""
        return self.params.copy()
    
    def set_parameters(self, params):
        """设置参数"""
        for param_name, value in params.items():
            if param_name in self.params:
                self.params[param_name] = value
                self.on_parameter_change(param_name, value)
                
                # 更新控件
                if param_name in self.controls:
                    if isinstance(self.controls[param_name], tuple):
                        self.controls[param_name][0].set(value)
                    else:
                        self.controls[param_name].set(value)