#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片生成 - ControlNet模组
支持ControlNet模型加载、预处理、权重控制和多模型组合

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import base64
from PIL import Image, ImageTk
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ControlNetModule:
    """图片生成ControlNet管理模组"""
    
    def __init__(self, parent_frame, callback=None):
        self.parent_frame = parent_frame
        self.callback = callback
        self.loaded_controlnets = {}  # {name: {"path": str, "weight": float, "enabled": bool, "processor": str}}
        self.controlnet_models = {
            "Canny边缘检测": {
                "name": "canny",
                "description": "Canny边缘检测，用于精确轮廓控制",
                "processor": "canny",
                "parameters": {
                    "low_threshold": {"min": 50, "max": 200, "default": 100},
                    "high_threshold": {"min": 150, "max": 300, "default": 200},
                    "gaussian_kernel": {"min": 1, "max": 7, "default": 5}
                },
                "weight_range": {"min": 0.0, "max": 2.0, "default": 1.0}
            },
            "OpenPose姿态检测": {
                "name": "openpose",
                "description": "人体姿态检测，用于姿态控制",
                "processor": "openpose",
                "parameters": {
                    "detect_hand": {"default": True},
                    "detect_face": {"default": True},
                    "detect_body": {"default": True},
                    "confidence_threshold": {"min": 0.1, "max": 1.0, "default": 0.5}
                },
                "weight_range": {"min": 0.0, "max": 2.0, "default": 1.0}
            },
            "深度图控制": {
                "name": "depth",
                "description": "深度图检测，用于立体结构控制",
                "processor": "depth",
                "parameters": {
                    "resolution": {"options": ["512", "768", "1024"], "default": "512"},
                    "model_type": {"options": ["MiDaS", "DPT"], "default": "MiDaS"},
                    "normalize": {"default": True}
                },
                "weight_range": {"min": 0.0, "max": 2.0, "default": 0.8}
            },
            "法线贴图": {
                "name": "normal",
                "description": "法线贴图检测，用于表面细节控制",
                "processor": "normal",
                "parameters": {
                    "resolution": {"options": ["512", "768", "1024"], "default": "512"},
                    "blur_radius": {"min": 0, "max": 10, "default": 2},
                    "alpha": {"min": 0.0, "max": 1.0, "default": 1.0}
                },
                "weight_range": {"min": 0.0, "max": 2.0, "default": 0.7}
            },
            "线条画": {
                "name": "lineart",
                "description": "线条提取，用于线稿控制",
                "processor": "lineart",
                "parameters": {
                    "resolution": {"options": ["512", "768", "1024"], "default": "512"},
                    "threshold": {"min": 0, "max": 255, "default": 128},
                    "blur_radius": {"min": 0, "max": 5, "default": 1}
                },
                "weight_range": {"min": 0.0, "max": 2.0, "default": 0.9}
            },
            "软边缘": {
                "name": "softedge",
                "description": "软边缘检测，用于柔和轮廓控制",
                "processor": "softedge",
                "parameters": {
                    "resolution": {"options": ["512", "768", "1024"], "default": "512"},
                    "safe": {"default": True},
                    "blur": {"min": 0, "max": 10, "default": 2}
                },
                "weight_range": {"min": 0.0, "max": 2.0, "default": 0.8}
            },
            "分割掩码": {
                "name": "segmentation",
                "description": "语义分割，用于区域控制",
                "processor": "segmentation",
                "parameters": {
                    "resolution": {"options": ["512", "768", "1024"], "default": "512"},
                    "random_colors": {"default": False},
                    "alpha": {"min": 0.0, "max": 1.0, "default": 1.0}
                },
                "weight_range": {"min": 0.0, "max": 2.0, "default": 0.6}
            },
            "人体关键点": {
                "name": "pose",
                "description": "人体关键点检测，用于精细姿态控制",
                "processor": "pose",
                "parameters": {
                    "detect_hand": {"default": True},
                    "detect_face": {"default": True},
                    "detect_body": {"default": True},
                    "detect_ped": {"default": False}
                },
                "weight_range": {"min": 0.0, "max": 2.0, "default": 1.0}
            }
        }
        
        # 预处理类型
        self.preprocessors = {
            "自动检测": "auto",
            "Canny": "canny",
            "OpenPose": "openpose", 
            "Depth": "depth",
            "Normal": "normal",
            "Lineart": "lineart",
            "SoftEdge": "softedge",
            "Scribble": "scribble",
            "MLSD": "mlsd",
            "Tile": "tile"
        }
        
        # 支持的文件格式
        self.supported_formats = [".safetensors", ".ckpt", ".pt", ".pth", ".onnx"]
        
        # 当前输入图像
        self.current_input_image = None
        self.current_processed_images = {}  # {processor_name: image_path}
        
        self.create_ui()
        self.scan_local_controlnets()
    
    def create_ui(self):
        """创建ControlNet管理UI"""
        # 主容器
        main_container = ttk.Frame(self.parent_frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 标题
        title_label = ttk.Label(main_container, text="ControlNet管理", 
                               font=("微软雅黑", 14, "bold"))
        title_label.pack(anchor="w", pady=(0, 15))
        
        # 状态和输入区域
        self.create_status_and_input_area(main_container)
        
        # ControlNet选项卡
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill="both", expand=True, pady=(10, 0))
        
        # ControlNet模型选项卡
        self.create_models_tab(notebook)
        
        # 预处理选项卡
        self.create_preprocessing_tab(notebook)
        
        # 已加载ControlNet选项卡
        self.create_loaded_tab(notebook)
        
        # 权重和参数选项卡
        self.create_parameters_tab(notebook)
    
    def create_status_and_input_area(self, parent):
        """创建状态和输入区域"""
        status_frame = ttk.LabelFrame(parent, text="ControlNet状态", padding=10)
        status_frame.pack(fill="x", pady=(0, 15))
        
        # 状态信息
        info_frame = ttk.Frame(status_frame)
        info_frame.pack(fill="x")
        
        ttk.Label(info_frame, text="已加载ControlNet:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.loaded_count_label = ttk.Label(info_frame, text="0个", 
                                           font=("微软雅黑", 10, "bold"))
        self.loaded_count_label.grid(row=0, column=1, sticky="w", padx=(0, 20))
        
        ttk.Label(info_frame, text="输入图像:").grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.input_status_label = ttk.Label(info_frame, text="未设置", foreground="red")
        self.input_status_label.grid(row=0, column=3, sticky="w", padx=(0, 20))
        
        ttk.Label(info_frame, text="预处理:").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.preprocessing_status_label = ttk.Label(info_frame, text="待处理", foreground="orange")
        self.preprocessing_status_label.grid(row=1, column=1, sticky="w")
        
        # 输入图像控制
        input_control_frame = ttk.Frame(status_frame)
        input_control_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(input_control_frame, text="选择输入图像", 
                  command=self.select_input_image).pack(side="left", padx=(0, 10))
        
        ttk.Button(input_control_frame, text="批量预处理", 
                  command=self.batch_preprocessing).pack(side="left", padx=(0, 10))
        
        ttk.Button(input_control_frame, text="清除", 
                  command=self.clear_input_image).pack(side="left")
        
        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(3, weight=1)
    
    def create_models_tab(self, notebook):
        """创建ControlNet模型选项卡"""
        models_frame = ttk.Frame(notebook)
        notebook.add(models_frame, text="模型管理")
        
        # 模型列表和详情
        content_frame = ttk.Frame(models_frame)
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 左侧：模型列表
        list_frame = ttk.LabelFrame(content_frame, text="可用ControlNet模型", padding=10)
        list_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        # 搜索框
        search_frame = ttk.Frame(list_frame)
        search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_frame, text="搜索:").pack(side="left")
        self.model_search_var = tk.StringVar()
        self.model_search_var.trace("w", self.on_model_search)
        search_entry = ttk.Entry(search_frame, textvariable=self.model_search_var, width=25)
        search_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        # 模型列表框
        self.model_listbox = tk.Listbox(list_frame, height=15)
        self.model_listbox.pack(fill="both", expand=True, pady=(0, 10))
        
        # 填充模型列表
        for model_name in self.controlnet_models.keys():
            self.model_listbox.insert(tk.END, model_name)
        
        self.model_listbox.bind("<<ListboxSelect>>", self.on_model_select)
        self.model_listbox.bind("<Double-1>", self.on_model_double_click)
        
        # 操作按钮
        model_buttons = ttk.Frame(list_frame)
        model_buttons.pack(fill="x")
        
        ttk.Button(model_buttons, text="加载模型", 
                  command=self.load_selected_controlnet).pack(side="left", padx=(0, 10))
        
        ttk.Button(model_buttons, text="预览", 
                  command=self.preview_controlnet_model).pack(side="left")
        
        # 右侧：模型详情
        detail_frame = ttk.LabelFrame(content_frame, text="模型详情", padding=10)
        detail_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))
        
        # 详情文本
        self.model_detail_text = tk.Text(detail_frame, wrap="word", 
                                        font=("Consolas", 10), state="disabled")
        self.model_detail_text.pack(fill="both", expand=True)
        
        # 模型管理
        management_frame = ttk.LabelFrame(models_frame, text="模型管理", padding=10)
        management_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        management_buttons = ttk.Frame(management_frame)
        management_buttons.pack(fill="x")
        
        ttk.Button(management_buttons, text="扫描本地模型", 
                  command=self.scan_local_controlnets).pack(side="left", padx=(0, 10))
        
        ttk.Button(management_buttons, text="批量加载", 
                  command=self.batch_load_controlnets).pack(side="left", padx=(0, 10))
        
        ttk.Button(management_buttons, text="导入模型", 
                  command=self.import_controlnet_model).pack(side="left")
    
    def create_preprocessing_tab(self, notebook):
        """创建预处理选项卡"""
        preprocess_frame = ttk.Frame(notebook)
        notebook.add(preprocess_frame, text="预处理")
        
        # 预处理控制
        control_frame = ttk.LabelFrame(preprocess_frame, text="预处理控制", padding=10)
        control_frame.pack(fill="x", padx=10, pady=10)
        
        # 选择预处理类型
        preprocessor_frame = ttk.Frame(control_frame)
        preprocessor_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(preprocessor_frame, text="预处理类型:", 
                  font=("微软雅黑", 10, "bold")).pack(anchor="w")
        
        self.preprocessor_var = tk.StringVar(value="自动检测")
        preprocessor_combo = ttk.Combobox(preprocessor_frame, textvariable=self.preprocessor_var,
                                         values=list(self.preprocessors.keys()),
                                         width=30)
        preprocessor_combo.pack(fill="x", pady=(5, 0))
        
        # 预处理参数
        self.preprocess_params_frame = ttk.LabelFrame(control_frame, text="预处理参数", padding=10)
        self.preprocess_params_frame.pack(fill="x", pady=(10, 0))
        
        # 预处理按钮
        preprocess_buttons = ttk.Frame(control_frame)
        preprocess_buttons.pack(fill="x", pady=(10, 0))
        
        ttk.Button(preprocess_buttons, text="开始预处理", 
                  command=self.start_preprocessing).pack(side="left", padx=(0, 10))
        
        ttk.Button(preprocess_buttons, text="保存结果", 
                  command=self.save_preprocess_result).pack(side="left", padx=(0, 10))
        
        ttk.Button(preprocess_buttons, text="重置", 
                  command=self.reset_preprocessing).pack(side="left")
        
        # 预处理结果
        result_frame = ttk.LabelFrame(preprocess_frame, text="预处理结果", padding=10)
        result_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 图像显示区域
        self.image_display_frame = ttk.Frame(result_frame)
        self.image_display_frame.pack(fill="both", expand=True)
        
        # 创建Canvas用于显示图像
        self.preview_canvas = tk.Canvas(self.image_display_frame, bg="white", 
                                       width=400, height=300)
        self.preview_canvas.pack(fill="both", expand=True)
        
        # 滚动条
        scrollbar = ttk.Scrollbar(self.image_display_frame, orient="horizontal", 
                                 command=self.preview_canvas.xview)
        self.preview_canvas.configure(xscrollcommand=scrollbar.set)
        scrollbar.pack(fill="x")
    
    def create_loaded_tab(self, notebook):
        """创建已加载ControlNet选项卡"""
        loaded_frame = ttk.Frame(notebook)
        notebook.add(loaded_frame, text="已加载")
        
        # 已加载ControlNet列表
        loaded_list_frame = ttk.LabelFrame(loaded_frame, text="当前加载的ControlNet", padding=10)
        loaded_list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 创建Treeview
        columns = ("名称", "权重", "状态", "预处理类型", "路径")
        self.loaded_controlnet_tree = ttk.Treeview(loaded_list_frame, columns=columns, 
                                                  show="headings", height=12)
        
        for col in columns:
            self.loaded_controlnet_tree.heading(col, text=col)
            self.loaded_controlnet_tree.column(col, width=120)
        
        loaded_scrollbar = ttk.Scrollbar(loaded_list_frame, orient="vertical", 
                                        command=self.loaded_controlnet_tree.yview)
        self.loaded_controlnet_tree.configure(yscrollcommand=loaded_scrollbar.set)
        
        self.loaded_controlnet_tree.pack(side="left", fill="both", expand=True)
        loaded_scrollbar.pack(side="right", fill="y")
        
        self.loaded_controlnet_tree.bind("<<TreeviewSelect>>", self.on_loaded_controlnet_select)
        
        # 操作按钮
        button_frame = ttk.Frame(loaded_list_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="卸载", 
                  command=self.unload_selected_controlnet).pack(side="left", padx=(0, 10))
        
        ttk.Button(button_frame, text="启用/禁用", 
                  command=self.toggle_controlnet_status).pack(side="left", padx=(0, 10))
        
        ttk.Button(button_frame, text="应用配置", 
                  command=self.apply_controlnet_config).pack(side="left")
    
    def create_parameters_tab(self, notebook):
        """创建权重和参数选项卡"""
        params_frame = ttk.Frame(notebook)
        notebook.add(params_frame, text="参数设置")
        
        # ControlNet权重设置
        weight_frame = ttk.LabelFrame(params_frame, text="权重设置", padding=10)
        weight_frame.pack(fill="x", padx=10, pady=10)
        
        # 当前选中的ControlNet
        selection_frame = ttk.Frame(weight_frame)
        selection_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(selection_frame, text="选中的ControlNet:", 
                 font=("微软雅黑", 10, "bold")).pack(anchor="w")
        
        self.selected_controlnet_name = ttk.Label(selection_frame, text="无", 
                                                foreground="gray")
        self.selected_controlnet_name.pack(anchor="w", pady=(2, 10))
        
        # 权重控制
        weight_control_frame = ttk.Frame(weight_frame)
        weight_control_frame.pack(fill="x", pady=(5, 0))
        
        ttk.Label(weight_control_frame, text="权重:").pack(side="left")
        
        self.controlnet_weight_slider = tk.Scale(weight_control_frame, from_=0.0, to=2.0, 
                                                orient="horizontal", resolution=0.01, 
                                                length=300)
        self.controlnet_weight_slider.pack(side="left", fill="x", expand=True, 
                                          padx=(10, 10))
        
        self.controlnet_weight_label = ttk.Label(weight_control_frame, text="0.00", 
                                               font=("Consolas", 10), foreground="blue")
        self.controlnet_weight_label.pack(side="left", padx=(10, 0))
        
        self.controlnet_weight_slider.bind("<Motion>", self.on_controlnet_weight_change)
        
        # 快速权重按钮
        quick_weight_frame = ttk.Frame(weight_frame)
        quick_weight_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Label(quick_weight_frame, text="快速设置:").pack(side="left")
        
        for weight in [0.1, 0.5, 0.8, 1.0, 1.2, 1.5]:
            ttk.Button(quick_weight_frame, text=str(weight), 
                      command=lambda w=weight: self.set_controlnet_weight(w)).pack(side="left", padx=(2, 0))
        
        # 预处理参数设置
        self.processor_params_frame = ttk.LabelFrame(params_frame, text="预处理参数", padding=10)
        self.processor_params_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # 参数控件将在这里动态创建
        self.param_controls = {}
        
        # 批量操作
        batch_frame = ttk.LabelFrame(params_frame, text="批量操作", padding=10)
        batch_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        batch_controls = ttk.Frame(batch_frame)
        batch_controls.pack(fill="x")
        
        ttk.Label(batch_controls, text="批量调整:").pack(side="left")
        
        self.batch_controlnet_operation = tk.StringVar(value="multiply")
        batch_combo = ttk.Combobox(batch_controls, textvariable=self.batch_controlnet_operation,
                                  values=["乘以", "加上", "设置到", "重置到默认"])
        batch_combo.pack(side="left", padx=(5, 10))
        
        self.batch_controlnet_value = tk.DoubleVar(value=1.0)
        ttk.Entry(batch_controls, textvariable=self.batch_controlnet_value, 
                 width=10).pack(side="left", padx=(0, 10))
        
        ttk.Button(batch_controls, text="应用", 
                  command=self.apply_batch_controlnet_operation).pack(side="left")
    
    def scan_local_controlnets(self):
        """扫描本地ControlNet模型"""
        # 常见的ControlNet目录
        controlnet_directories = [
            "models/ControlNet",
            "models/controlnet",
            "models/StableDiffusion/controlnet",
            "ComfyUI/models/controlnet",
            "extensions/sd-webui-controlnet/models"
        ]
        
        self.local_controlnets = {}
        
        for cn_dir in controlnet_directories:
            if os.path.exists(cn_dir):
                try:
                    for file in os.listdir(cn_dir):
                        if any(file.endswith(fmt) for fmt in self.supported_formats):
                            file_path = os.path.join(cn_dir, file)
                            file_size = os.path.getsize(file_path)
                            file_size_mb = file_size / (1024 * 1024)
                            
                            # 解析文件名
                            info = self.parse_controlnet_filename(file)
                            
                            cn_info = {
                                "name": info["name"],
                                "path": file_path,
                                "size": f"{file_size_mb:.1f}MB",
                                "type": info["type"],
                                "description": info.get("description", ""),
                                "enabled": False,
                                "weight": 0.0,
                                "processor": info.get("processor", "auto")
                            }
                            
                            self.local_controlnets[info["name"]] = cn_info
                            
                except Exception as e:
                    logger.error(f"扫描目录失败 {cn_dir}: {e}")
        
        self.refresh_loaded_controlnet_list()
    
    def parse_controlnet_filename(self, filename):
        """解析ControlNet文件名"""
        name_without_ext = os.path.splitext(filename)[0]
        
        info = {"name": name_without_ext, "type": "未分类", "processor": "auto"}
        
        # 检查是否为预训练模型
        if "canny" in filename.lower():
            info["type"] = "Canny边缘检测"
            info["processor"] = "canny"
        elif "openpose" in filename.lower():
            info["type"] = "OpenPose姿态检测"
            info["processor"] = "openpose"
        elif "depth" in filename.lower():
            info["type"] = "深度图控制"
            info["processor"] = "depth"
        elif "normal" in filename.lower():
            info["type"] = "法线贴图"
            info["processor"] = "normal"
        elif "lineart" in filename.lower():
            info["type"] = "线条画"
            info["processor"] = "lineart"
        elif "softedge" in filename.lower():
            info["type"] = "软边缘"
            info["processor"] = "softedge"
        elif "segmentation" in filename.lower():
            info["type"] = "分割掩码"
            info["processor"] = "segmentation"
        elif "pose" in filename.lower():
            info["type"] = "人体关键点"
            info["processor"] = "pose"
        
        return info
    
    def refresh_loaded_controlnet_list(self):
        """刷新已加载ControlNet列表"""
        # 清空现有列表
        for item in self.loaded_controlnet_tree.get_children():
            self.loaded_controlnet_tree.delete(item)
        
        # 填充列表
        for cn_name, cn_info in self.loaded_controlnets.items():
            status = "启用" if cn_info["enabled"] else "禁用"
            processor = cn_info["processor"]
            
            self.loaded_controlnet_tree.insert("", "end", values=(
                cn_name,
                f"{cn_info['weight']:.2f}",
                status,
                processor,
                cn_info["path"]
            ))
        
        # 更新状态信息
        self.loaded_count_label.config(text=f"{len(self.loaded_controlnets)}个")
    
    def on_model_search(self, *args):
        """模型搜索事件"""
        search_text = self.model_search_var.get().lower()
        
        # 清空列表
        self.model_listbox.delete(0, tk.END)
        
        # 搜索所有模型
        for model_name in self.controlnet_models.keys():
            if search_text in model_name.lower():
                self.model_listbox.insert(tk.END, model_name)
    
    def on_model_select(self, event):
        """模型选择事件"""
        selection = self.model_listbox.curselection()
        if selection:
            model_name = self.model_listbox.get(selection[0])
            self.show_model_details(model_name)
    
    def on_model_double_click(self, event):
        """模型双击事件"""
        self.load_selected_controlnet()
    
    def show_model_details(self, model_name):
        """显示模型详情"""
        if model_name in self.controlnet_models:
            model_info = self.controlnet_models[model_name]
            
            self.model_detail_text.config(state="normal")
            self.model_detail_text.delete("1.0", "end")
            
            details = f"模型名称: {model_info['name']}\n"
            details += f"类型: {model_name}\n"
            details += f"描述: {model_info['description']}\n"
            details += f"处理器: {model_info['processor']}\n\n"
            
            details += "参数配置:\n"
            for param_name, param_info in model_info["parameters"].items():
                if "default" in param_info:
                    details += f"  {param_name}: 默认值 {param_info['default']}\n"
                elif "min" in param_info and "max" in param_info:
                    details += f"  {param_name}: 范围 {param_info['min']}-{param_info['max']}\n"
                elif "options" in param_info:
                    details += f"  {param_name}: 选项 {param_info['options']}\n"
            
            details += f"\n权重范围: {model_info['weight_range']['min']}-{model_info['weight_range']['max']}\n"
            details += f"默认权重: {model_info['weight_range']['default']}\n\n"
            
            details += "使用建议:\n"
            if model_info["processor"] == "canny":
                details += "• 适用于精确轮廓控制\n• 权重建议: 0.8-1.2\n• 需要边缘清晰的输入图像"
            elif model_info["processor"] == "openpose":
                details += "• 适用于人体姿态控制\n• 权重建议: 0.9-1.1\n• 适合人体图像"
            elif model_info["processor"] == "depth":
                details += "• 适用于立体结构控制\n• 权重建议: 0.6-1.0\n• 需要深度信息的图像"
            elif model_info["processor"] == "normal":
                details += "• 适用于表面细节控制\n• 权重建议: 0.5-0.9\n• 需要法线贴图"
            
            self.model_detail_text.insert("1.0", details)
            self.model_detail_text.config(state="disabled")
    
    def load_selected_controlnet(self):
        """加载选中的ControlNet"""
        selection = self.model_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择ControlNet模型")
            return
        
        model_name = self.model_listbox.get(selection[0])
        
        if model_name in self.loaded_controlnets:
            messagebox.showwarning("警告", f"ControlNet '{model_name}' 已经加载")
            return
        
        # 获取默认配置
        if model_name in self.controlnet_models:
            model_info = self.controlnet_models[model_name]
            default_weight = model_info["weight_range"]["default"]
            processor = model_info["processor"]
        else:
            default_weight = 1.0
            processor = "auto"
        
        # 添加到已加载列表
        self.loaded_controlnets[model_name] = {
            "path": f"models/{model_name.replace(' ', '_').lower()}.safetensors",
            "weight": default_weight,
            "enabled": True,
            "processor": processor,
            "parameters": self.get_default_parameters(model_name),
            "info": self.controlnet_models.get(model_name, {})
        }
        
        self.refresh_loaded_controlnet_list()
        
        if self.callback:
            self.callback("controlnet_loaded", {
                "name": model_name,
                "weight": default_weight,
                "processor": processor,
                "path": self.loaded_controlnets[model_name]["path"]
            })
        
        messagebox.showinfo("成功", f"ControlNet '{model_name}' 加载成功")
    
    def get_default_parameters(self, model_name):
        """获取默认参数"""
        if model_name in self.controlnet_models:
            model_info = self.controlnet_models[model_name]
            params = {}
            for param_name, param_info in model_info["parameters"].items():
                if "default" in param_info:
                    params[param_name] = param_info["default"]
                elif "min" in param_info and "max" in param_info:
                    params[param_name] = param_info["default"] if "default" in param_info else param_info["min"]
                elif "options" in param_info:
                    params[param_name] = param_info["default"]
            return params
        return {}
    
    def unload_selected_controlnet(self):
        """卸载选中的ControlNet"""
        selection = self.loaded_controlnet_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择ControlNet")
            return
        
        item = self.loaded_controlnet_tree.item(selection[0])
        cn_name = item["values"][0]
        
        if cn_name in self.loaded_controlnets:
            del self.loaded_controlnets[cn_name]
            
            self.refresh_loaded_controlnet_list()
            
            if self.callback:
                self.callback("controlnet_unloaded", {"name": cn_name})
            
            messagebox.showinfo("成功", f"ControlNet '{cn_name}' 已卸载")
    
    def toggle_controlnet_status(self):
        """切换ControlNet状态"""
        selection = self.loaded_controlnet_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择ControlNet")
            return
        
        item = self.loaded_controlnet_tree.item(selection[0])
        cn_name = item["values"][0]
        current_status = item["values"][2]
        
        if cn_name in self.loaded_controlnets:
            new_status = not self.loaded_controlnets[cn_name]["enabled"]
            self.loaded_controlnets[cn_name]["enabled"] = new_status
            
            self.refresh_loaded_controlnet_list()
            
            if self.callback:
                self.callback("controlnet_status_changed", {
                    "name": cn_name,
                    "enabled": new_status
                })
            
            status_text = "启用" if new_status else "禁用"
            messagebox.showinfo("成功", f"ControlNet '{cn_name}' 已{status_text}")
    
    def on_loaded_controlnet_select(self, event):
        """已加载ControlNet选择事件"""
        selection = self.loaded_controlnet_tree.selection()
        if selection:
            item = self.loaded_controlnet_tree.item(selection[0])
            cn_name = item["values"][0]
            weight = float(item["values"][1])
            
            # 更新权重控制面板
            self.selected_controlnet_name.config(text=cn_name)
            self.controlnet_weight_slider.set(weight)
            self.controlnet_weight_label.config(text=f"{weight:.2f}")
            
            # 更新参数控件
            self.update_parameter_controls(cn_name)
    
    def on_controlnet_weight_change(self, event):
        """ControlNet权重变化事件"""
        weight = self.controlnet_weight_slider.get()
        self.controlnet_weight_label.config(text=f"{weight:.2f}")
        
        # 更新已加载的ControlNet
        selection = self.loaded_controlnet_tree.selection()
        if selection:
            item = self.loaded_controlnet_tree.item(selection[0])
            cn_name = item["values"][0]
            
            if cn_name in self.loaded_controlnets:
                self.loaded_controlnets[cn_name]["weight"] = weight
                self.refresh_loaded_controlnet_list()
                
                if self.callback:
                    self.callback("controlnet_weight_changed", {
                        "name": cn_name,
                        "weight": weight
                    })
    
    def set_controlnet_weight(self, weight):
        """设置ControlNet权重"""
        self.controlnet_weight_slider.set(weight)
        self.controlnet_weight_label.config(text=f"{weight:.2f}")
        self.on_controlnet_weight_change(None)
    
    def update_parameter_controls(self, cn_name):
        """更新参数控件"""
        # 清空现有控件
        for widget in self.processor_params_frame.winfo_children():
            widget.destroy()
        self.param_controls.clear()
        
        if cn_name in self.loaded_controlnets:
            cn_info = self.loaded_controlnets[cn_name]
            
            if cn_info["info"] and "parameters" in cn_info["info"]:
                for param_name, param_info in cn_info["info"]["parameters"].items():
                    param_frame = ttk.Frame(self.processor_params_frame)
                    param_frame.pack(fill="x", pady=5)
                    
                    ttk.Label(param_frame, text=f"{param_name}:").pack(side="left")
                    
                    # 根据参数类型创建控件
                    if "options" in param_info:
                        var = tk.StringVar(value=str(param_info["default"]))
                        combo = ttk.Combobox(param_frame, textvariable=var, 
                                           values=param_info["options"], width=20)
                        combo.pack(side="right")
                        self.param_controls[param_name] = (var, combo)
                    
                    elif "min" in param_info and "max" in param_info:
                        var = tk.DoubleVar(value=param_info["default"] if "default" in param_info else param_info["min"])
                        scale = tk.Scale(param_frame, from_=param_info["min"], to=param_info["max"],
                                       orient="horizontal", variable=var, length=200)
                        scale.pack(side="right", fill="x", expand=True, padx=(10, 0))
                        label = ttk.Label(param_frame, text=str(var.get()))
                        label.pack(side="right", padx=(5, 0))
                        
                        def on_scale_change(val, param=param_name, label=label):
                            label.config(text=f"{float(val):.2f}")
                            if param in self.param_controls:
                                self.param_controls[param][0].set(float(val))
                        
                        scale.bind("<Motion>", lambda e, val=scale.get(): on_scale_change(val))
                        self.param_controls[param_name] = (var, scale)
                    
                    elif "default" in param_info:
                        if isinstance(param_info["default"], bool):
                            var = tk.BooleanVar(value=param_info["default"])
                            check = ttk.Checkbutton(param_frame, variable=var)
                            check.pack(side="right")
                            self.param_controls[param_name] = (var, check)
                        else:
                            var = tk.StringVar(value=str(param_info["default"]))
                            entry = ttk.Entry(param_frame, textvariable=var, width=20)
                            entry.pack(side="right")
                            self.param_controls[param_name] = (var, entry)
    
    def apply_batch_controlnet_operation(self):
        """应用批量ControlNet操作"""
        operation = self.batch_controlnet_operation.get()
        value = self.batch_controlnet_value.get()
        
        if not self.loaded_controlnets:
            messagebox.showwarning("警告", "没有已加载的ControlNet")
            return
        
        if operation == "乘以":
            for cn_info in self.loaded_controlnets.values():
                cn_info["weight"] *= value
        
        elif operation == "加上":
            for cn_info in self.loaded_controlnets.values():
                cn_info["weight"] += value
        
        elif operation == "设置到":
            for cn_info in self.loaded_controlnets.values():
                cn_info["weight"] = value
        
        elif operation == "重置到默认":
            for cn_name, cn_info in self.loaded_controlnets.items():
                if cn_name in self.controlnet_models:
                    model_info = self.controlnet_models[cn_name]
                    cn_info["weight"] = model_info["weight_range"]["default"]
        
        self.refresh_loaded_controlnet_list()
        
        if self.callback:
            self.callback("controlnet_batch_weight_changed", {
                "operation": operation,
                "value": value,
                "controlnets": list(self.loaded_controlnets.keys())
            })
    
    def select_input_image(self):
        """选择输入图像"""
        file_path = filedialog.askopenfilename(
            title="选择ControlNet输入图像",
            filetypes=[("图像文件", "*.png *.jpg *.jpeg *.bmp *.tiff"), ("所有文件", "*.*")]
        )
        
        if file_path:
            try:
                # 加载图像
                self.current_input_image = Image.open(file_path)
                
                # 更新状态
                self.input_status_label.config(text="已设置", foreground="green")
                
                # 显示图像
                self.display_image(self.current_input_image, "原始图像")
                
                if self.callback:
                    self.callback("input_image_changed", {
                        "path": file_path,
                        "image": self.current_input_image
                    })
                
                messagebox.showinfo("成功", "输入图像设置成功")
                
            except Exception as e:
                messagebox.showerror("错误", f"加载图像失败: {e}")
    
    def display_image(self, image, title):
        """显示图像"""
        # 缩放图像以适应显示区域
        max_width = 400
        max_height = 300
        
        # 计算缩放比例
        image_ratio = image.width / image.height
        canvas_ratio = max_width / max_height
        
        if image_ratio > canvas_ratio:
            new_width = max_width
            new_height = int(max_width / image_ratio)
        else:
            new_height = max_height
            new_width = int(max_height * image_ratio)
        
        # 缩放图像
        resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # 转换为PhotoImage
        photo = ImageTk.PhotoImage(resized_image)
        
        # 清空Canvas并显示图像
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(new_width//2, new_height//2, image=photo, anchor="center")
        self.preview_canvas.image = photo  # 保持引用
        
        # 设置Canvas滚动区域
        self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all"))
    
    def clear_input_image(self):
        """清除输入图像"""
        self.current_input_image = None
        self.input_status_label.config(text="未设置", foreground="red")
        self.preprocessing_status_label.config(text="待处理", foreground="orange")
        
        # 清空图像显示
        self.preview_canvas.delete("all")
        
        if self.callback:
            self.callback("input_image_cleared", {})
    
    def start_preprocessing(self):
        """开始预处理"""
        if not self.current_input_image:
            messagebox.showwarning("警告", "请先选择输入图像")
            return
        
        processor_type = self.preprocessor_var.get()
        
        # 模拟预处理过程
        self.preprocessing_status_label.config(text="处理中...", foreground="orange")
        
        # 这里应该实现实际的预处理逻辑
        messagebox.showinfo("提示", f"正在使用 {processor_type} 进行预处理...")
        
        # 模拟处理完成
        self.preprocessing_status_label.config(text="完成", foreground="green")
        
        if self.callback:
            self.callback("preprocessing_completed", {
                "processor": processor_type,
                "input_image": self.current_input_image
            })
    
    def batch_preprocessing(self):
        """批量预处理"""
        if not self.current_input_image:
            messagebox.showwarning("警告", "请先选择输入图像")
            return
        
        # 批量预处理所有处理器
        for processor_name in self.preprocessors.keys():
            if processor_name != "自动检测":
                # 这里应该实现每个处理器的逻辑
                pass
        
        messagebox.showinfo("成功", "批量预处理完成")
    
    def reset_preprocessing(self):
        """重置预处理"""
        self.preprocessing_status_label.config(text="待处理", foreground="orange")
        self.preview_canvas.delete("all")
    
    def self_Save_preprocess_result(self):
        """保存预处理结果"""
        messagebox.showinfo("提示", "保存功能将在后续版本中实现")
    
    def preview_controlnet_model(self):
        """预览ControlNet模型"""
        selection = self.model_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择模型")
            return
        
        model_name = self.model_listbox.get(selection[0])
        messagebox.showinfo("预览", f"预览ControlNet模型: {model_name}")
    
    def batch_load_controlnets(self):
        """批量加载ControlNet"""
        selection = self.model_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要加载的ControlNet")
            return
        
        selected_models = []
        for item in selection:
            selected_models.append(self.model_listbox.get(item))
        
        # 确认对话框
        result = messagebox.askyesno("确认", f"确定要加载 {len(selected_models)} 个ControlNet吗？")
        if not result:
            return
        
        # 批量加载
        loaded_count = 0
        for model_name in selected_models:
            if model_name not in self.loaded_controlnets:
                self.load_selected_controlnet()
                loaded_count += 1
        
        messagebox.showinfo("成功", f"已批量加载 {loaded_count} 个ControlNet")
    
    def import_controlnet_model(self):
        """导入ControlNet模型"""
        file_path = filedialog.askopenfilename(
            title="导入ControlNet模型",
            filetypes=[("模型文件", "*.safetensors *.ckpt *.pt *.pth *.onnx"), ("所有文件", "*.*")]
        )
        
        if file_path:
            # 这里应该实现模型导入逻辑
            messagebox.showinfo("提示", f"导入模型功能: {file_path}")
    
    def apply_controlnet_config(self):
        """应用ControlNet配置"""
        if not self.loaded_controlnets:
            messagebox.showwarning("警告", "没有已加载的ControlNet")
            return
        
        active_controlnets = []
        for cn_name, cn_info in self.loaded_controlnets.items():
            if cn_info["enabled"]:
                active_controlnets.append({
                    "name": cn_name,
                    "weight": cn_info["weight"],
                    "processor": cn_info["processor"],
                    "parameters": cn_info.get("parameters", {}),
                    "path": cn_info["path"]
                })
        
        if self.callback:
            self.callback("controlnet_config_applied", {"controlnets": active_controlnets})
        
        messagebox.showinfo("成功", f"已应用 {len(active_controlnets)} 个活跃ControlNet配置")
    
    def get_loaded_controlnets(self):
        """获取已加载的ControlNet"""
        return self.loaded_controlnets
    
    def get_active_controlnets(self):
        """获取活跃的ControlNet（启用的）"""
        active = []
        for cn_name, cn_info in self.loaded_controlnets.items():
            if cn_info["enabled"]:
                active.append({
                    "name": cn_name,
                    "weight": cn_info["weight"],
                    "processor": cn_info["processor"],
                    "parameters": cn_info.get("parameters", {}),
                    "path": cn_info["path"]
                })
        return active
    def save_preprocess_result(self):
        """保存预处理结果"""
        # 这里可以实现保存预处理结果的逻辑
        messagebox.showinfo("提示", "保存预处理结果功能开发中...")
