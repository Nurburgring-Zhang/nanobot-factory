#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片生成主页面
集成所有图片生成相关的模组和功能

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class PageImageGeneration:
    """图片生成主页面"""
    
    def __init__(self, parent_frame, callback=None):
        self.parent_frame = parent_frame
        self.callback = callback
        
        # 模组实例
        self.model_module = None
        self.prompt_module = None
        self.lora_module = None
        self.controlnet_module = None
        self.parameters_module = None
        self.resolution_module = None
        self.optimization_module = None
        
        # 当前配置状态
        self.current_config = {
            "model": None,
            "prompt": {"positive": "", "negative": ""},
            "loras": [],
            "controlnets": [],
            "parameters": {},
            "resolution": {"width": 512, "height": 512},
            "optimization": {}
        }
        
        # 创建UI
        self.create_ui()
        self.initialize_modules()
    
    def create_ui(self):
        """创建图片生成页面UI"""
        # 主容器
        main_container = ttk.Frame(self.parent_frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 标题区域
        self.create_title_area(main_container)
        
        # 主要内容区域
        self.create_main_content_area(main_container)
        
        # 底部操作区域
        self.create_action_area(main_container)
    
    def create_title_area(self, parent):
        """创建标题区域"""
        title_frame = ttk.Frame(parent)
        title_frame.pack(fill="x", pady=(0, 15))
        
        # 主标题
        title_label = ttk.Label(title_frame, text="🎨 图片生成", 
                              font=("微软雅黑", 16, "bold"))
        title_label.pack(side="left")
        
        # 状态指示器
        status_frame = ttk.Frame(title_frame)
        status_frame.pack(side="right")
        
        ttk.Label(status_frame, text="状态:").pack(side="left")
        self.status_label = ttk.Label(status_frame, text="就绪", foreground="green", 
                                    font=("微软雅黑", 10, "bold"))
        self.status_label.pack(side="left", padx=(10, 0))
        
        # 快速信息
        info_frame = ttk.Frame(parent)
        info_frame.pack(fill="x", pady=(5, 0))
        
        self.info_text = ttk.Label(info_frame, text="已配置模型和参数，可以开始生成", 
                                 foreground="gray", font=("微软雅黑", 9))
        self.info_text.pack(side="left")
        
        # 快捷操作按钮
        quick_frame = ttk.Frame(parent)
        quick_frame.pack(side="right")
        
        ttk.Button(quick_frame, text="快速生成", 
                  command=self.quick_generate).pack(side="left", padx=(0, 5))
        
        ttk.Button(quick_frame, text="保存配置", 
                  command=self.save_current_config).pack(side="left", padx=(0, 5))
        
        ttk.Button(quick_frame, text="加载配置", 
                  command=self.load_config).pack(side="left")
    
    def create_main_content_area(self, parent):
        """创建主要内容区域"""
        # 创建PanedWindow用于可调整布局
        main_paned = ttk.PanedWindow(parent, orient="horizontal")
        main_paned.pack(fill="both", expand=True, pady=(0, 10))
        
        # 左侧面板：配置区域
        left_panel = ttk.Frame(main_paned)
        main_paned.add(left_panel, weight=3)
        
        # 右侧面板：预览和结果
        right_panel = ttk.Frame(main_paned)
        main_paned.add(right_panel, weight=2)
        
        # 创建左侧配置面板
        self.create_config_panel(left_panel)
        
        # 创建右侧预览面板
        self.create_preview_panel(right_panel)
    
    def create_config_panel(self, parent):
        """创建配置面板"""
        # 配置选项卡
        config_notebook = ttk.Notebook(parent)
        config_notebook.pack(fill="both", expand=True)
        
        # 模型配置选项卡
        self.create_model_config_tab(config_notebook)
        
        # 提示词选项卡
        self.create_prompt_config_tab(config_notebook)
        
        # LoRA配置选项卡
        self.create_lora_config_tab(config_notebook)
        
        # ControlNet配置选项卡
        self.create_controlnet_config_tab(config_notebook)
        
        # 参数配置选项卡
        self.create_parameters_config_tab(config_notebook)
        
        # 分辨率选项卡
        self.create_resolution_config_tab(config_notebook)
        
        # 优化选项卡
        self.create_optimization_config_tab(config_notebook)
        
        # 设置默认选项卡
        config_notebook.select(0)
    
    def create_model_config_tab(self, notebook):
        """创建模型配置选项卡"""
        model_frame = ttk.Frame(notebook)
        notebook.add(model_frame, text="模型")
        
        try:
            from ui_components.image_generation_model_module import ModelModule
            self.model_module = ModelModule(model_frame, self.on_model_module_change)
        except ImportError as e:
            error_frame = ttk.Frame(model_frame)
            error_frame.pack(fill="both", expand=True)
            
            ttk.Label(error_frame, text="❌ 模型模块加载失败", 
                     font=("微软雅黑", 12, "bold"), foreground="red").pack(pady=20)
            ttk.Label(error_frame, text=f"错误: {e}", 
                     foreground="gray").pack()
            
            logger.error(f"模型模块加载失败: {e}")
    
    def create_prompt_config_tab(self, notebook):
        """创建提示词配置选项卡"""
        prompt_frame = ttk.Frame(notebook)
        notebook.add(prompt_frame, text="提示词")
        
        try:
            from ui_components.image_generation_prompt_module import PromptModule
            self.prompt_module = PromptModule(prompt_frame, self.on_prompt_module_change)
        except ImportError as e:
            error_frame = ttk.Frame(prompt_frame)
            error_frame.pack(fill="both", expand=True)
            
            ttk.Label(error_frame, text="❌ 提示词模块加载失败", 
                     font=("微软雅黑", 12, "bold"), foreground="red").pack(pady=20)
            ttk.Label(error_frame, text=f"错误: {e}", 
                     foreground="gray").pack()
            
            logger.error(f"提示词模块加载失败: {e}")
    
    def create_lora_config_tab(self, notebook):
        """创建LoRA配置选项卡"""
        lora_frame = ttk.Frame(notebook)
        notebook.add(lora_frame, text="LoRA")
        
        try:
            from ui_components.image_generation_lora_module import LoRAModule
            self.lora_module = LoRAModule(lora_frame, self.on_lora_module_change)
        except ImportError as e:
            error_frame = ttk.Frame(lora_frame)
            error_frame.pack(fill="both", expand=True)
            
            ttk.Label(error_frame, text="❌ LoRA模块加载失败", 
                     font=("微软雅黑", 12, "bold"), foreground="red").pack(pady=20)
            ttk.Label(error_frame, text=f"错误: {e}", 
                     foreground="gray").pack()
            
            logger.error(f"LoRA模块加载失败: {e}")
    
    def create_controlnet_config_tab(self, notebook):
        """创建ControlNet配置选项卡"""
        controlnet_frame = ttk.Frame(notebook)
        notebook.add(controlnet_frame, text="ControlNet")
        
        try:
            from ui_components.image_generation_controlnet_module import ControlNetModule
            self.controlnet_module = ControlNetModule(controlnet_frame, self.on_controlnet_module_change)
        except ImportError as e:
            error_frame = ttk.Frame(controlnet_frame)
            error_frame.pack(fill="both", expand=True)
            
            ttk.Label(error_frame, text="❌ ControlNet模块加载失败", 
                     font=("微软雅黑", 12, "bold"), foreground="red").pack(pady=20)
            ttk.Label(error_frame, text=f"错误: {e}", 
                     foreground="gray").pack()
            
            logger.error(f"ControlNet模块加载失败: {e}")
    
    def create_parameters_config_tab(self, notebook):
        """创建参数配置选项卡"""
        params_frame = ttk.Frame(notebook)
        notebook.add(params_frame, text="参数")
        
        try:
            from ui_components.image_generation_parameters_module import ParametersModule
            self.parameters_module = ParametersModule(params_frame, self.on_parameters_module_change)
        except ImportError as e:
            error_frame = ttk.Frame(params_frame)
            error_frame.pack(fill="both", expand=True)
            
            ttk.Label(error_frame, text="❌ 参数模块加载失败", 
                     font=("微软雅黑", 12, "bold"), foreground="red").pack(pady=20)
            ttk.Label(error_frame, text=f"错误: {e}", 
                     foreground="gray").pack()
            
            logger.error(f"参数模块加载失败: {e}")
    
    def create_resolution_config_tab(self, notebook):
        """创建分辨率配置选项卡"""
        resolution_frame = ttk.Frame(notebook)
        notebook.add(resolution_frame, text="分辨率")
        
        try:
            from ui_components.image_generation_resolution_module import ResolutionModule
            self.resolution_module = ResolutionModule(resolution_frame, self.on_resolution_module_change)
        except ImportError as e:
            error_frame = ttk.Frame(resolution_frame)
            error_frame.pack(fill="both", expand=True)
            
            ttk.Label(error_frame, text="❌ 分辨率模块加载失败", 
                     font=("微软雅黑", 12, "bold"), foreground="red").pack(pady=20)
            ttk.Label(error_frame, text=f"错误: {e}", 
                     foreground="gray").pack()
            
            logger.error(f"分辨率模块加载失败: {e}")
    
    def create_optimization_config_tab(self, notebook):
        """创建优化配置选项卡"""
        optimization_frame = ttk.Frame(notebook)
        notebook.add(optimization_frame, text="优化")
        
        try:
            from ui_components.image_generation_optimization_module import OptimizationModule
            self.optimization_module = OptimizationModule(optimization_frame, self.on_optimization_module_change)
        except ImportError as e:
            error_frame = ttk.Frame(optimization_frame)
            error_frame.pack(fill="both", expand=True)
            
            ttk.Label(error_frame, text="❌ 优化模块加载失败", 
                     font=("微软雅黑", 12, "bold"), foreground="red").pack(pady=20)
            ttk.Label(error_frame, text=f"错误: {e}", 
                     foreground="gray").pack()
            
            logger.error(f"优化模块加载失败: {e}")
    
    def create_preview_panel(self, parent):
        """创建预览面板"""
        # 预览选项卡
        preview_notebook = ttk.Notebook(parent)
        preview_notebook.pack(fill="both", expand=True)
        
        # 图像预览选项卡
        self.create_image_preview_tab(preview_notebook)
        
        # 配置摘要选项卡
        self.create_config_summary_tab(preview_notebook)
        
        # 进度监控选项卡
        self.create_progress_monitor_tab(preview_notebook)
    
    def create_image_preview_tab(self, notebook):
        """创建图像预览选项卡"""
        preview_frame = ttk.Frame(notebook)
        notebook.add(preview_frame, text="预览")
        
        # 预览控制栏
        control_bar = ttk.Frame(preview_frame)
        control_bar.pack(fill="x", padx=10, pady=5)
        
        ttk.Button(control_bar, text="生成预览", 
                  command=self.generate_preview).pack(side="left", padx=(0, 10))
        
        ttk.Button(control_bar, text="清空预览", 
                  command=self.clear_preview).pack(side="left", padx=(0, 10))
        
        # 缩放控制
        zoom_frame = ttk.Frame(control_bar)
        zoom_frame.pack(side="right")
        
        ttk.Label(zoom_frame, text="缩放:").pack(side="left")
        
        self.zoom_var = tk.StringVar(value="100%")
        zoom_combo = ttk.Combobox(zoom_frame, textvariable=self.zoom_var,
                                values=["25%", "50%", "75%", "100%", "150%", "200%"], 
                                width=8, state="readonly")
        zoom_combo.pack(side="left", padx=(5, 0))
        zoom_combo.bind("<<ComboboxSelected>>", self.on_zoom_change)
        
        # 预览画布
        canvas_frame = ttk.Frame(preview_frame)
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 创建Canvas用于显示图像
        self.preview_canvas = tk.Canvas(canvas_frame, bg="lightgray", width=400, height=300)
        self.preview_canvas.pack(fill="both", expand=True)
        
        # 滚动条
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.preview_canvas.yview)
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.preview_canvas.xview)
        
        self.preview_canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # 图像信息显示
        info_frame = ttk.LabelFrame(preview_frame, text="图像信息", padding=5)
        info_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.image_info_text = tk.Text(info_frame, height=3, wrap="word", 
                                     font=("Consolas", 9), state="disabled")
        self.image_info_text.pack(fill="x")
        
        # 初始化预览
        self.init_preview_canvas()
    
    def create_config_summary_tab(self, notebook):
        """创建配置摘要选项卡"""
        summary_frame = ttk.Frame(notebook)
        notebook.add(summary_frame, text="摘要")
        
        # 摘要文本显示
        self.summary_text = tk.Text(summary_frame, wrap="word", 
                                   font=("微软雅黑", 10), state="disabled")
        self.summary_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 更新摘要
        self.update_config_summary()
    
    def create_progress_monitor_tab(self, notebook):
        """创建进度监控选项卡"""
        progress_frame = ttk.Frame(notebook)
        notebook.add(progress_frame, text="进度")
        
        # 当前任务信息
        current_task_frame = ttk.LabelFrame(progress_frame, text="当前任务", padding=10)
        current_task_frame.pack(fill="x", padx=10, pady=10)
        
        self.current_task_label = ttk.Label(current_task_frame, text="无活动任务", 
                                          font=("微软雅黑", 10, "bold"))
        self.current_task_label.pack()
        
        # 进度条
        progress_bar_frame = ttk.Frame(current_task_frame)
        progress_bar_frame.pack(fill="x", pady=(10, 0))
        
        self.main_progress = ttk.Progressbar(progress_bar_frame, mode='determinate')
        self.main_progress.pack(fill="x", padx=(0, 10))
        
        self.main_progress_label = ttk.Label(progress_bar_frame, text="0%")
        self.main_progress_label.pack(side="right")
        
        # 子任务进度
        self.sub_progress = ttk.Progressbar(current_task_frame, mode='indeterminate')
        self.sub_progress.pack(fill="x", pady=(5, 0))
        
        # 任务历史
        history_frame = ttk.LabelFrame(progress_frame, text="任务历史", padding=10)
        history_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.task_history_text = tk.Text(history_frame, height=15, wrap="word",
                                       font=("Consolas", 9), state="disabled")
        self.task_history_text.pack(fill="both", expand=True)
        
        # 滚动条
        history_scrollbar = ttk.Scrollbar(history_frame, orient="vertical", 
                                        command=self.task_history_text.yview)
        self.task_history_text.configure(yscrollcommand=history_scrollbar.set)
        
        # 初始化进度监控
        self.init_progress_monitor()
    
    def create_action_area(self, parent):
        """创建操作区域"""
        action_frame = ttk.LabelFrame(parent, text="生成操作", padding=15)
        action_frame.pack(fill="x")
        
        # 主要操作按钮
        main_actions = ttk.Frame(action_frame)
        main_actions.pack(fill="x", pady=(0, 10))
        
        ttk.Button(main_actions, text="🚀 开始生成", 
                  command=self.start_generation, 
                  style="Accent.TButton").pack(side="left", padx=(0, 10))
        
        ttk.Button(main_actions, text="⏸️ 暂停", 
                  command=self.pause_generation).pack(side="left", padx=(0, 10))
        
        ttk.Button(main_actions, text="⏹️ 停止", 
                  command=self.stop_generation).pack(side="left", padx=(0, 10))
        
        ttk.Button(main_actions, text="🔄 重试", 
                  command=self.retry_generation).pack(side="left")
        
        # 高级操作按钮
        advanced_actions = ttk.Frame(action_frame)
        advanced_actions.pack(fill="x")
        
        ttk.Button(advanced_actions, text="📋 批量生成", 
                  command=self.batch_generation).pack(side="left", padx=(0, 10))
        
        ttk.Button(advanced_actions, text="💾 保存配置", 
                  command=self.save_current_config).pack(side="left", padx=(0, 10))
        
        ttk.Button(advanced_actions, text="📂 加载配置", 
                  command=self.load_config).pack(side="left", padx=(0, 10))
        
        ttk.Button(advanced_actions, text="⚙️ 高级设置", 
                  command=self.show_advanced_settings).pack(side="left", padx=(0, 10))
        
        ttk.Button(advanced_actions, text="🧹 清理", 
                  command=self.cleanup).pack(side="left")
    
    def initialize_modules(self):
        """初始化所有模组"""
        logger.info("初始化图片生成页面模组...")
        
        # 检查模组状态
        modules_status = {}
        
        if self.model_module:
            modules_status["模型"] = "✅ 已加载"
        else:
            modules_status["模型"] = "❌ 加载失败"
        
        if self.prompt_module:
            modules_status["提示词"] = "✅ 已加载"
        else:
            modules_status["提示词"] = "❌ 加载失败"
        
        if self.lora_module:
            modules_status["LoRA"] = "✅ 已加载"
        else:
            modules_status["LoRA"] = "❌ 加载失败"
        
        if self.controlnet_module:
            modules_status["ControlNet"] = "✅ 已加载"
        else:
            modules_status["ControlNet"] = "❌ 加载失败"
        
        if self.parameters_module:
            modules_status["参数"] = "✅ 已加载"
        else:
            modules_status["参数"] = "❌ 加载失败"
        
        if self.resolution_module:
            modules_status["分辨率"] = "✅ 已加载"
        else:
            modules_status["分辨率"] = "❌ 加载失败"
        
        if self.optimization_module:
            modules_status["优化"] = "✅ 已加载"
        else:
            modules_status["优化"] = "❌ 加载失败"
        
        # 更新状态
        success_count = sum(1 for status in modules_status.values() if "✅" in status)
        total_count = len(modules_status)
        
        if success_count == total_count:
            self.status_label.config(text="全部就绪", foreground="green")
            self.info_text.config(text=f"所有 {total_count} 个模组已就绪，可以开始生成")
        elif success_count > 0:
            self.status_label.config(text="部分就绪", foreground="orange")
            self.info_text.config(text=f"{success_count}/{total_count} 个模组已就绪，部分功能可能受限")
        else:
            self.status_label.config(text="未就绪", foreground="red")
            self.info_text.config(text="模组加载失败，无法进行生成")
        
        # 记录初始化结果
        for module, status in modules_status.items():
            logger.info(f"{module}: {status}")
    
    def init_preview_canvas(self):
        """初始化预览画布"""
        # 绘制默认背景
        self.preview_canvas.create_text(200, 150, text="图像预览区域", 
                                     font=("微软雅黑", 16), fill="gray")
        self.preview_canvas.create_text(200, 180, text="点击'生成预览'开始", 
                                     font=("微软雅黑", 12), fill="lightgray")
    
    def init_progress_monitor(self):
        """初始化进度监控"""
        self.add_task_log("系统已启动，等待用户操作")
    
    # 模组变化事件处理
    def on_model_module_change(self, event, data):
        """模型模块变化事件"""
        logger.info(f"模型模块变化: {event}")
        self.current_config["model"] = data
        self.update_config_summary()
        
        if self.callback:
            self.callback("model_changed", data)
    
    def on_prompt_module_change(self, event, data):
        """提示词模块变化事件"""
        logger.info(f"提示词模块变化: {event}")
        self.current_config["prompt"] = data
        self.update_config_summary()
        
        if self.callback:
            self.callback("prompt_changed", data)
    
    def on_lora_module_change(self, event, data):
        """LoRA模块变化事件"""
        logger.info(f"LoRA模块变化: {event}")
        self.current_config["loras"] = data
        self.update_config_summary()
        
        if self.callback:
            self.callback("lora_changed", data)
    
    def on_controlnet_module_change(self, event, data):
        """ControlNet模块变化事件"""
        logger.info(f"ControlNet模块变化: {event}")
        self.current_config["controlnets"] = data
        self.update_config_summary()
        
        if self.callback:
            self.callback("controlnet_changed", data)
    
    def on_parameters_module_change(self, event, data):
        """参数模块变化事件"""
        logger.info(f"参数模块变化: {event}")
        self.current_config["parameters"] = data
        self.update_config_summary()
        
        if self.callback:
            self.callback("parameters_changed", data)
    
    def on_resolution_module_change(self, event, data):
        """分辨率模块变化事件"""
        logger.info(f"分辨率模块变化: {event}")
        self.current_config["resolution"] = data
        self.update_config_summary()
        
        if self.callback:
            self.callback("resolution_changed", data)
    
    def on_optimization_module_change(self, event, data):
        """优化模块变化事件"""
        logger.info(f"优化模块变化: {event}")
        self.current_config["optimization"] = data
        self.update_config_summary()
        
        if self.callback:
            self.callback("optimization_changed", data)
    
    def on_zoom_change(self, event):
        """缩放变化事件"""
        zoom_percent = self.zoom_var.get()
        # 这里应该实现图像缩放逻辑
        logger.info(f"缩放变化: {zoom_percent}")
    
    def update_config_summary(self):
        """更新配置摘要"""
        summary_text = "📊 图片生成配置摘要\n\n"
        summary_text += "=" * 40 + "\n\n"
        
        # 模型信息
        model_info = self.current_config.get("model")
        if model_info:
            summary_text += f"🎯 模型: {model_info.get('name', 'N/A')}\n"
            summary_text += f"   状态: {'已加载' if model_info.get('loaded', False) else '未加载'}\n\n"
        else:
            summary_text += "❌ 模型: 未选择\n\n"
        
        # 提示词信息
        prompt_info = self.current_config.get("prompt", {})
        summary_text += f"📝 提示词:\n"
        summary_text += f"   正面: {len(prompt_info.get('positive', ''))} 字符\n"
        summary_text += f"   负面: {len(prompt_info.get('negative', ''))} 字符\n\n"
        
        # LoRA信息
        lora_info = self.current_config.get("loras", [])
        summary_text += f"🔗 LoRA: {len(lora_info)} 个已加载\n"
        for lora in lora_info[:3]:  # 只显示前3个
            summary_text += f"   • {lora.get('name', 'N/A')} (权重: {lora.get('weight', 0)})\n"
        if len(lora_info) > 3:
            summary_text += f"   ... 等 {len(lora_info)} 个\n"
        summary_text += "\n"
        
        # ControlNet信息
        cn_info = self.current_config.get("controlnets", [])
        summary_text += f"🎮 ControlNet: {len(cn_info)} 个已加载\n"
        for cn in cn_info[:2]:  # 只显示前2个
            summary_text += f"   • {cn.get('name', 'N/A')} (处理器: {cn.get('processor', 'N/A')})\n"
        if len(cn_info) > 2:
            summary_text += f"   ... 等 {len(cn_info)} 个\n"
        summary_text += "\n"
        
        # 参数信息
        params_info = self.current_config.get("parameters", {})
        summary_text += f"⚙️ 参数:\n"
        summary_text += f"   分辨率: {params_info.get('width', 512)}x{params_info.get('height', 512)}\n"
        summary_text += f"   步数: {params_info.get('steps', 20)}\n"
        summary_text += f"   CFG: {params_info.get('cfg_scale', 7.0)}\n"
        summary_text += f"   采样器: {params_info.get('sampler', 'N/A')}\n\n"
        
        # 优化信息
        opt_info = self.current_config.get("optimization", {})
        enabled_features = [k for k, v in opt_info.items() if v.get("enabled", False)]
        summary_text += f"✨ 优化: {len(enabled_features)} 个功能已启用\n"
        for feature in enabled_features[:3]:  # 只显示前3个
            summary_text += f"   • {feature}\n"
        if len(enabled_features) > 3:
            summary_text += f"   ... 等 {len(enabled_features)} 个\n"
        
        # 配置完整性
        summary_text += "\n" + "=" * 40 + "\n"
        summary_text += "🔍 配置检查:\n"
        
        issues = []
        if not model_info:
            issues.append("❌ 未选择模型")
        if not prompt_info.get("positive"):
            issues.append("⚠️ 缺少正面提示词")
        if len(lora_info) > 10:
            issues.append("⚠️ LoRA数量较多，可能影响性能")
        if len(cn_info) > 5:
            issues.append("⚠️ ControlNet数量较多，可能影响性能")
        
        if not issues:
            summary_text += "✅ 配置完整，可以开始生成"
        else:
            summary_text += "\n".join(f"   {issue}" for issue in issues)
        
        # 更新摘要显示
        if hasattr(self, 'summary_text') and self.summary_text is not None:
            self.summary_text.config(state="normal")
            self.summary_text.delete("1.0", "end")
            self.summary_text.insert("1.0", summary_text)
            self.summary_text.config(state="disabled")
    
    # 操作方法
    def quick_generate(self):
        """快速生成"""
        self.add_task_log("开始快速生成...")
        self.current_task_label.config(text="快速生成进行中...")
        
        # 模拟快速生成过程
        self.main_progress.config(value=20)
        self.main_progress_label.config(text="20%")
        self.sub_progress.start()
        
        # 这里应该调用实际的生成逻辑
        messagebox.showinfo("快速生成", "快速生成功能将在实际集成时实现")
    
    def generate_preview(self):
        """生成预览"""
        self.add_task_log("生成图像预览...")
        self.current_task_label.config(text="生成预览中...")
        
        # 模拟预览生成
        self.main_progress.config(value=30)
        self.main_progress_label.config(text="30%")
        self.sub_progress.start()
        
        # 清空画布并显示预览
        self.preview_canvas.delete("all")
        self.preview_canvas.create_text(200, 150, text="🔍 预览图像", 
                                       font=("微软雅黑", 16), fill="blue")
        
        # 更新图像信息
        self.update_image_info("预览图像", "512x512", "PNG", "2.5MB")
        
        # 模拟完成
        self.main_progress.config(value=100)
        self.main_progress_label.config(text="100%")
        self.sub_progress.stop()
        
        self.current_task_label.config(text="预览生成完成")
        self.add_task_log("预览生成完成")
    
    def clear_preview(self):
        """清空预览"""
        self.preview_canvas.delete("all")
        self.init_preview_canvas()
        
        self.image_info_text.config(state="normal")
        self.image_info_text.delete("1.0", "end")
        self.image_info_text.config(state="disabled")
    
    def start_generation(self):
        """开始生成"""
        self.add_task_log("开始图片生成...")
        self.current_task_label.config(text="图片生成进行中...")
        
        # 重置进度
        self.main_progress.config(value=0)
        self.main_progress_label.config(text="0%")
        self.sub_progress.start()
        
        # 验证配置
        if not self.validate_config():
            self.sub_progress.stop()
            self.current_task_label.config(text="配置验证失败")
            return
        
        # 开始生成（模拟）
        self.simulate_generation_progress()
        
        if self.callback:
            self.callback("start_generation", self.current_config)
    
    def pause_generation(self):
        """暂停生成"""
        self.sub_progress.stop()
        self.current_task_label.config(text="生成已暂停")
        self.add_task_log("生成已暂停")
    
    def stop_generation(self):
        """停止生成"""
        self.sub_progress.stop()
        self.main_progress.config(value=0)
        self.main_progress_label.config(text="0%")
        self.current_task_label.config(text="生成已停止")
        self.add_task_log("生成已停止")
    
    def retry_generation(self):
        """重试生成"""
        self.add_task_log("重试生成...")
        self.start_generation()
    
    def batch_generation(self):
        """批量生成"""
        self.add_task_log("开始批量生成...")
        self.current_task_label.config(text="批量生成进行中...")
        
        # 模拟批量生成
        messagebox.showinfo("批量生成", "批量生成功能将在实际集成时实现")
    
    def save_current_config(self):
        """保存当前配置"""
        try:
            config_file = "image_generation_config.json"
            import json
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.current_config, f, indent=2, ensure_ascii=False)
            
            self.add_task_log(f"配置已保存到 {config_file}")
            messagebox.showinfo("保存成功", f"配置已保存到 {config_file}")
            
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            messagebox.showerror("保存失败", f"保存配置失败: {e}")
    
    def load_config(self):
        """加载配置"""
        try:
            config_file = "image_generation_config.json"
            import json
            
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                
                # 更新当前配置
                self.current_config.update(loaded_config)
                
                # 更新各个模块
                self.update_modules_from_config()
                
                self.add_task_log(f"配置已从 {config_file} 加载")
                messagebox.showinfo("加载成功", f"配置已从 {config_file} 加载")
            else:
                messagebox.showwarning("文件不存在", f"配置文件 {config_file} 不存在")
                
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            messagebox.showerror("加载失败", f"加载配置失败: {e}")
    
    def show_advanced_settings(self):
        """显示高级设置"""
        messagebox.showinfo("高级设置", "高级设置对话框将在后续版本中实现")
    
    def cleanup(self):
        """清理"""
        self.clear_preview()
        self.current_task_label.config(text="无活动任务")
        self.main_progress.config(value=0)
        self.main_progress_label.config(text="0%")
        self.sub_progress.stop()
        
        self.add_task_log("系统已清理")
    
    def validate_config(self):
        """验证配置"""
        issues = []
        
        # 检查模型
        if not self.current_config.get("model"):
            issues.append("未选择模型")
        
        # 检查提示词
        if not self.current_config.get("prompt", {}).get("positive"):
            issues.append("缺少正面提示词")
        
        # 检查分辨率
        resolution = self.current_config.get("resolution", {})
        if not resolution.get("width") or not resolution.get("height"):
            issues.append("分辨率设置不完整")
        
        if issues:
            error_msg = "配置验证失败:\n" + "\n".join(f"• {issue}" for issue in issues)
            messagebox.showerror("配置错误", error_msg)
            return False
        
        return True
    
    def update_modules_from_config(self):
        """从配置更新模块"""
        # 更新各个模块的状态
        config = self.current_config
        
        # 这里应该将配置应用到各个模块
        # 为了简化，这里只记录日志
        logger.info("从配置更新模块状态...")
        
        self.update_config_summary()
    
    def simulate_generation_progress(self):
        """模拟生成进度"""
        import time
        
        steps = [
            ("加载模型", 10),
            ("处理提示词", 20),
            ("加载LoRA", 30),
            ("加载ControlNet", 40),
            ("开始生成", 50),
            ("采样中", 70),
            ("后处理", 85),
            ("保存结果", 95),
            ("完成", 100)
        ]
        
        for step_name, progress in steps:
            self.main_progress.config(value=progress)
            self.main_progress_label.config(text=f"{progress}%")
            self.current_task_label.config(text=step_name)
            
            if step_name != "完成":
                self.add_task_log(step_name)
            
            time.sleep(0.5)  # 模拟处理时间
        
        self.sub_progress.stop()
        self.current_task_label.config(text="生成完成!")
        self.add_task_log("图片生成完成!")
    
    def update_image_info(self, filename, resolution, format_type, size):
        """更新图像信息"""
        info_text = f"文件名: {filename}\n"
        info_text += f"分辨率: {resolution}\n"
        info_text += f"格式: {format_type}\n"
        info_text += f"大小: {size}\n"
        
        self.image_info_text.config(state="normal")
        self.image_info_text.delete("1.0", "end")
        self.image_info_text.insert("1.0", info_text)
        self.image_info_text.config(state="disabled")
    
    def add_task_log(self, message):
        """添加任务日志"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.task_history_text.config(state="normal")
        self.task_history_text.insert("end", log_entry)
        self.task_history_text.see("end")
        self.task_history_text.config(state="disabled")
    
    def get_current_config(self):
        """获取当前配置"""
        return self.current_config.copy()
    
    def set_current_config(self, config):
        """设置当前配置"""
        self.current_config.update(config)
        self.update_modules_from_config()
        self.update_config_summary()
        
        if self.callback:
            self.callback("config_updated", config)