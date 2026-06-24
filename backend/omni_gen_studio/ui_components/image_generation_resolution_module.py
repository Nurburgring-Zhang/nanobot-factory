#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片生成 - 分辨率模组
支持预设分辨率选择、自定义分辨率、分辨率优化和批量处理

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image
import math
from typing import Dict, List, Optional, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class ResolutionModule:
    """图片生成分辨率管理模组"""
    
    def __init__(self, parent_frame, callback=None):
        self.parent_frame = parent_frame
        self.callback = callback
        
        # 当前分辨率
        self.current_resolution = {"width": 512, "height": 512}
        
        # 分辨率预设分类
        self.resolution_presets = {
            "方形": {
                "方形 512": {"width": 512, "height": 512, "aspect_ratio": 1.0},
                "方形 768": {"width": 768, "height": 768, "aspect_ratio": 1.0},
                "方形 1024": {"width": 1024, "height": 1024, "aspect_ratio": 1.0},
                "方形 1536": {"width": 1536, "height": 1536, "aspect_ratio": 1.0},
                "方形 2048": {"width": 2048, "height": 2048, "aspect_ratio": 1.0},
                "方形 3072": {"width": 3072, "height": 3072, "aspect_ratio": 1.0}
            },
            "横版": {
                "横版 512x288": {"width": 512, "height": 288, "aspect_ratio": 16/9},
                "横版 768x432": {"width": 768, "height": 432, "aspect_ratio": 16/9},
                "横版 1024x576": {"width": 1024, "height": 576, "aspect_ratio": 16/9},
                "横版 1152x648": {"width": 1152, "height": 648, "aspect_ratio": 16/9},
                "横版 1280x720": {"width": 1280, "height": 720, "aspect_ratio": 16/9},
                "横版 1920x1080": {"width": 1920, "height": 1080, "aspect_ratio": 16/9},
                "横版 2560x1440": {"width": 2560, "height": 1440, "aspect_ratio": 16/9}
            },
            "竖版": {
                "竖版 288x512": {"width": 288, "height": 512, "aspect_ratio": 9/16},
                "竖版 432x768": {"width": 432, "height": 768, "aspect_ratio": 9/16},
                "竖版 576x1024": {"width": 576, "height": 1024, "aspect_ratio": 9/16},
                "竖版 720x1280": {"width": 720, "height": 1280, "aspect_ratio": 9/16},
                "竖版 1080x1920": {"width": 1080, "height": 1920, "aspect_ratio": 9/16},
                "竖版 1440x2560": {"width": 1440, "height": 2560, "aspect_ratio": 9/16}
            },
            "宽屏": {
                "宽屏 1344x768": {"width": 1344, "height": 768, "aspect_ratio": 21/12},
                "宽屏 1536x640": {"width": 1536, "height": 640, "aspect_ratio": 24/10},
                "宽屏 1728x768": {"width": 1728, "height": 768, "aspect_ratio": 225/100},
                "宽屏 2048x858": {"width": 2048, "height": 858, "aspect_ratio": 2.39/1},
                "宽屏 2560x1080": {"width": 2560, "height": 1080, "aspect_ratio": 2.37/1}
            },
            "经典比例": {
                "4:3 1024x768": {"width": 1024, "height": 768, "aspect_ratio": 4/3},
                "3:2 768x512": {"width": 768, "height": 512, "aspect_ratio": 3/2},
                "5:4 1024x819": {"width": 1024, "height": 819, "aspect_ratio": 5/4},
                "7:5 896x640": {"width": 896, "height": 640, "aspect_ratio": 7/5}
            },
            "专业摄影": {
                "A4 2480x3508": {"width": 2480, "height": 3508, "aspect_ratio": 2480/3508},
                "A3 3508x4961": {"width": 3508, "height": 4961, "aspect_ratio": 3508/4961},
                "Letter 2550x3300": {"width": 2550, "height": 3300, "aspect_ratio": 2550/3300},
                "海报 1748x2480": {"width": 1748, "height": 2480, "aspect_ratio": 1748/2480}
            }
        }
        
        # 分辨率优化规则
        self.optimization_rules = {
            "low_memory": {
                "max_pixels": 512 * 512,
                "recommended": [(512, 512), (384, 384), (320, 320)]
            },
            "medium_memory": {
                "max_pixels": 1024 * 1024,
                "recommended": [(1024, 1024), (768, 768), (896, 896)]
            },
            "high_memory": {
                "max_pixels": 2048 * 2048,
                "recommended": [(1536, 1536), (1792, 1792), (2048, 1024)]
            },
            "ultra_memory": {
                "max_pixels": 4096 * 4096,
                "recommended": [(3072, 3072), (4096, 4096), (5120, 2880)]
            }
        }
        
        # 创建UI
        self.create_ui()
    
    def create_ui(self):
        """创建分辨率管理UI"""
        # 主容器
        main_container = ttk.Frame(self.parent_frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 标题
        title_label = ttk.Label(main_container, text="分辨率管理", 
                               font=("微软雅黑", 14, "bold"))
        title_label.pack(anchor="w", pady=(0, 15))
        
        # 当前分辨率显示
        self.create_current_resolution_display(main_container)
        
        # 分辨率选项卡
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill="both", expand=True, pady=(10, 0))
        
        # 预设选择选项卡
        self.create_presets_tab(notebook)
        
        # 自定义设置选项卡
        self.create_custom_tab(notebook)
        
        # 优化建议选项卡
        self.create_optimization_tab(notebook)
        
        # 批量处理选项卡
        self.create_batch_tab(notebook)
        
        # 预览选项卡
        self.create_preview_tab(notebook)
    
    def create_current_resolution_display(self, parent):
        """创建当前分辨率显示"""
        display_frame = ttk.LabelFrame(parent, text="当前分辨率", padding=15)
        display_frame.pack(fill="x", pady=(0, 15))
        
        # 分辨率信息
        info_frame = ttk.Frame(display_frame)
        info_frame.pack(fill="x")
        
        ttk.Label(info_frame, text="当前分辨率:", font=("微软雅黑", 10, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.current_res_label = ttk.Label(info_frame, text="512 x 512", 
                                        font=("Consolas", 12, "bold"), foreground="blue")
        self.current_res_label.grid(row=0, column=1, sticky="w", padx=(0, 20))
        
        ttk.Label(info_frame, text="像素总数:", font=("微软雅黑", 10, "bold")).grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.pixel_count_label = ttk.Label(info_frame, text="262,144", 
                                        font=("Consolas", 12, "bold"), foreground="green")
        self.pixel_count_label.grid(row=0, column=3, sticky="w", padx=(0, 20))
        
        ttk.Label(info_frame, text="宽高比:", font=("微软雅黑", 10, "bold")).grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.aspect_ratio_label = ttk.Label(info_frame, text="1:1", 
                                          font=("Consolas", 12, "bold"), foreground="orange")
        self.aspect_ratio_label.grid(row=1, column=1, sticky="w", padx=(0, 20))
        
        ttk.Label(info_frame, text="性能影响:", font=("微软雅黑", 10, "bold")).grid(row=1, column=2, sticky="w", padx=(0, 10))
        self.performance_label = ttk.Label(info_frame, text="正常", 
                                         font=("Consolas", 12, "bold"), foreground="green")
        self.performance_label.grid(row=1, column=3, sticky="w")
        
        # 快速设置按钮
        quick_frame = ttk.Frame(display_frame)
        quick_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Label(quick_frame, text="快速设置:").pack(side="left")
        
        ttk.Button(quick_frame, text="512x512", 
                  command=lambda: self.set_resolution(512, 512)).pack(side="left", padx=(10, 5))
        
        ttk.Button(quick_frame, text="768x768", 
                  command=lambda: self.set_resolution(768, 768)).pack(side="left", padx=(5, 5))
        
        ttk.Button(quick_frame, text="1024x1024", 
                  command=lambda: self.set_resolution(1024, 1024)).pack(side="left", padx=(5, 5))
        
        ttk.Button(quick_frame, text="1920x1080", 
                  command=lambda: self.set_resolution(1920, 1080)).pack(side="left", padx=(5, 5))
        
        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(3, weight=1)
    
    def create_presets_tab(self, notebook):
        """创建预设选择选项卡"""
        presets_frame = ttk.Frame(notebook)
        notebook.add(presets_frame, text="预设选择")
        
        # 搜索和筛选
        filter_frame = ttk.Frame(presets_frame)
        filter_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(filter_frame, text="分类:").pack(side="left")
        self.preset_category_var = tk.StringVar(value="全部")
        category_combo = ttk.Combobox(filter_frame, textvariable=self.preset_category_var,
                                     values=["全部"] + list(self.resolution_presets.keys()),
                                     width=15, state="readonly")
        category_combo.pack(side="left", padx=(5, 10))
        
        ttk.Label(filter_frame, text="搜索:").pack(side="left")
        self.preset_search_var = tk.StringVar()
        self.preset_search_var.trace("w", self.on_preset_search)
        search_entry = ttk.Entry(filter_frame, textvariable=self.preset_search_var, width=20)
        search_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        # 预设网格
        grid_frame = ttk.LabelFrame(presets_frame, text="分辨率预设", padding=10)
        grid_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 创建Canvas和滚动条
        canvas = tk.Canvas(grid_frame, bg="white")
        scrollbar = ttk.Scrollbar(grid_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 预设按钮容器
        self.preset_buttons_frame = scrollable_frame
        self.refresh_preset_buttons()
    
    def create_custom_tab(self, notebook):
        """创建自定义设置选项卡"""
        custom_frame = ttk.Frame(notebook)
        notebook.add(custom_frame, text="自定义设置")
        
        # 自定义分辨率设置
        custom_frame_top = ttk.LabelFrame(custom_frame, text="自定义分辨率", padding=15)
        custom_frame_top.pack(fill="x", padx=10, pady=10)
        
        # 宽度和高度输入
        dim_frame = ttk.Frame(custom_frame_top)
        dim_frame.pack(fill="x", pady=(0, 15))
        
        ttk.Label(dim_frame, text="宽度:", font=("微软雅黑", 10, "bold")).pack(side="left")
        
        self.width_var = tk.IntVar(value=self.current_resolution["width"])
        width_spin = ttk.Spinbox(dim_frame, from_=64, to=8192, increment=64,
                               textvariable=self.width_var, width=12,
                               command=self.on_custom_dimension_change)
        width_spin.pack(side="left", padx=(10, 20))
        
        ttk.Label(dim_frame, text="高度:", font=("微软雅黑", 10, "bold")).pack(side="left")
        
        self.height_var = tk.IntVar(value=self.current_resolution["height"])
        height_spin = ttk.Spinbox(dim_frame, from_=64, to=8192, increment=64,
                                textvariable=self.height_var, width=12,
                                command=self.on_custom_dimension_change)
        height_spin.pack(side="left", padx=(10, 0))
        
        # 宽高比控制
        ratio_frame = ttk.LabelFrame(custom_frame, text="宽高比控制", padding=10)
        ratio_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # 预设宽高比
        ratio_presets = ttk.Frame(ratio_frame)
        ratio_presets.pack(fill="x", pady=(0, 10))
        
        ttk.Label(ratio_presets, text="常用比例:").pack(side="left")
        
        for ratio_name, ratio_value in [("1:1", 1.0), ("4:3", 4/3), ("3:2", 3/2), 
                                      ("16:9", 16/9), ("9:16", 9/16)]:
            ttk.Button(ratio_presets, text=ratio_name, 
                      command=lambda r=ratio_value: self.set_aspect_ratio(r)).pack(side="left", padx=(5, 0))
        
        # 自定义宽高比
        custom_ratio_frame = ttk.Frame(ratio_frame)
        custom_ratio_frame.pack(fill="x")
        
        ttk.Label(custom_ratio_frame, text="自定义比例:").pack(side="left")
        
        self.ratio_width_var = tk.StringVar(value="16")
        self.ratio_height_var = tk.StringVar(value="9")
        
        ratio_entry1 = ttk.Entry(custom_ratio_frame, textvariable=self.ratio_width_var, width=6)
        ratio_entry1.pack(side="left", padx=(10, 5))
        
        ttk.Label(custom_ratio_frame, text=":").pack(side="left", padx=(0, 5))
        
        ratio_entry2 = ttk.Entry(custom_ratio_frame, textvariable=self.ratio_height_var, width=6)
        ratio_entry2.pack(side="left", padx=(5, 10))
        
        ttk.Button(custom_ratio_frame, text="应用比例", 
                  command=self.apply_custom_aspect_ratio).pack(side="left")
        
        # 锁定宽高比
        lock_frame = ttk.Frame(custom_frame_top)
        lock_frame.pack(fill="x")
        
        self.lock_aspect_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(lock_frame, text="锁定宽高比", 
                       variable=self.lock_aspect_var,
                       command=self.toggle_aspect_lock).pack(side="left")
        
        # 分辨率建议
        suggestions_frame = ttk.LabelFrame(custom_frame, text="分辨率建议", padding=10)
        suggestions_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        suggestions_text = tk.Text(suggestions_frame, height=10, wrap="word",
                                 font=("微软雅黑", 9), state="disabled")
        suggestions_text.pack(fill="both", expand=True)
        
        self.suggestions_text = suggestions_text
        
        # 更新建议
        self.update_resolution_suggestions()
    
    def create_optimization_tab(self, notebook):
        """创建优化建议选项卡"""
        opt_frame = ttk.Frame(notebook)
        notebook.add(opt_frame, text="优化建议")
        
        # 内存等级设置
        memory_frame = ttk.LabelFrame(opt_frame, text="内存等级", padding=10)
        memory_frame.pack(fill="x", padx=10, pady=10)
        
        self.memory_level_var = tk.StringVar(value="medium_memory")
        memory_combo = ttk.Combobox(memory_frame, textvariable=self.memory_level_var,
                                   values=[("低内存", "low_memory"), 
                                          ("中等内存", "medium_memory"),
                                          ("高内存", "high_memory"),
                                          ("超高内存", "ultra_memory")],
                                   width=20, state="readonly")
        memory_combo.pack(side="left", padx=(0, 20))
        
        ttk.Button(memory_frame, text="应用等级", 
                  command=self.apply_memory_level).pack(side="left")
        
        # 优化建议
        advice_frame = ttk.LabelFrame(opt_frame, text="优化建议", padding=10)
        advice_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        advice_text = tk.Text(advice_frame, height=8, wrap="word",
                            font=("微软雅黑", 9), state="disabled")
        advice_text.pack(fill="x")
        
        self.advice_text = advice_text
        
        # 推荐分辨率
        recommended_frame = ttk.LabelFrame(opt_frame, text="推荐分辨率", padding=10)
        recommended_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 推荐列表
        self.recommended_listbox = tk.Listbox(recommended_frame, height=12)
        self.recommended_listbox.pack(fill="both", expand=True)
        
        self.recommended_listbox.bind("<<ListboxSelect>>", self.on_recommended_select)
        
        # 推荐操作按钮
        recommended_buttons = ttk.Frame(recommended_frame)
        recommended_buttons.pack(fill="x", pady=(10, 0))
        
        ttk.Button(recommended_buttons, text="应用推荐", 
                  command=self.apply_recommended_resolution).pack(side="left", padx=(0, 10))
        
        ttk.Button(recommended_buttons, text="查看详情", 
                  command=self.show_recommended_details).pack(side="left")
        
        # 更新优化信息
        self.update_optimization_info()
    
    def create_batch_tab(self, notebook):
        """创建批量处理选项卡"""
        batch_frame = ttk.Frame(notebook)
        notebook.add(batch_frame, text="批量处理")
        
        # 批量分辨率设置
        batch_settings_frame = ttk.LabelFrame(batch_frame, text="批量分辨率设置", padding=10)
        batch_settings_frame.pack(fill="x", padx=10, pady=10)
        
        # 批量尺寸列表
        sizes_frame = ttk.Frame(batch_settings_frame)
        sizes_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(sizes_frame, text="批量尺寸:", font=("微软雅黑", 10, "bold")).pack(anchor="w")
        
        # 尺寸输入
        size_inputs_frame = ttk.Frame(sizes_frame)
        size_inputs_frame.pack(fill="x", pady=(5, 0))
        
        ttk.Label(size_inputs_frame, text="宽度:").pack(side="left")
        
        self.batch_width_var = tk.StringVar(value="512,768,1024")
        ttk.Entry(size_inputs_frame, textvariable=self.batch_width_var, width=30).pack(side="left", padx=(5, 10))
        
        ttk.Label(size_inputs_frame, text="高度:").pack(side="left")
        
        self.batch_height_var = tk.StringVar(value="512,768,1024")
        ttk.Entry(size_inputs_frame, textvariable=self.batch_height_var, width=30).pack(side="left", padx=(5, 0))
        
        # 批量预览
        preview_frame = ttk.LabelFrame(batch_frame, text="批量预览", padding=10)
        preview_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 批量列表
        columns = ("序号", "宽度", "高度", "像素数", "宽高比", "建议用途")
        self.batch_tree = ttk.Treeview(preview_frame, columns=columns, show="headings", height=10)
        
        for col in columns:
            self.batch_tree.heading(col, text=col)
            self.batch_tree.column(col, width=100)
        
        batch_scrollbar = ttk.Scrollbar(preview_frame, orient="vertical", command=self.batch_tree.yview)
        self.batch_tree.configure(yscrollcommand=batch_scrollbar.set)
        
        self.batch_tree.pack(side="left", fill="both", expand=True)
        batch_scrollbar.pack(side="right", fill="y")
        
        # 批量操作按钮
        batch_buttons = ttk.Frame(preview_frame)
        batch_buttons.pack(fill="x", pady=(10, 0))
        
        ttk.Button(batch_buttons, text="生成列表", 
                  command=self.generate_batch_list).pack(side="left", padx=(0, 10))
        
        ttk.Button(batch_buttons, text="清除列表", 
                  command=self.clear_batch_list).pack(side="left", padx=(0, 10))
        
        ttk.Button(batch_buttons, text="导出列表", 
                  command=self.export_batch_list).pack(side="left", padx=(0, 10))
        
        ttk.Button(batch_buttons, text="应用全部", 
                  command=self.apply_all_batch_resolutions).pack(side="left")
        
        # 更新批量预览
        self.update_batch_preview()
    
    def create_preview_tab(self, notebook):
        """创建预览选项卡"""
        preview_frame = ttk.Frame(notebook)
        notebook.add(preview_frame, text="分辨率预览")
        
        # 预览控制
        control_frame = ttk.LabelFrame(preview_frame, text="预览控制", padding=10)
        control_frame.pack(fill="x", padx=10, pady=10)
        
        # 缩放比例
        scale_frame = ttk.Frame(control_frame)
        scale_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(scale_frame, text="缩放比例:").pack(side="left")
        
        self.preview_scale_var = tk.DoubleVar(value=0.5)
        scale_combo = ttk.Combobox(scale_frame, textvariable=self.preview_scale_var,
                                  values=[0.1, 0.25, 0.5, 1.0, 2.0], width=10)
        scale_combo.pack(side="left", padx=(10, 20))
        
        # 显示选项
        display_options = ttk.Frame(control_frame)
        display_options.pack(fill="x")
        
        self.show_grid_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(display_options, text="显示网格", 
                       variable=self.show_grid_var).pack(side="left", padx=(0, 10))
        
        self.show_labels_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(display_options, text="显示标签", 
                       variable=self.show_labels_var).pack(side="left", padx=(0, 10))
        
        ttk.Button(display_options, text="刷新预览", 
                  command=self.refresh_preview).pack(side="left", padx=(20, 0))
        
        # 预览画布
        canvas_frame = ttk.LabelFrame(preview_frame, text="分辨率预览", padding=10)
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 创建Canvas
        self.preview_canvas = tk.Canvas(canvas_frame, bg="white", width=600, height=400)
        self.preview_canvas.pack(fill="both", expand=True)
        
        # 画布滚动条
        canvas_scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.preview_canvas.yview)
        self.preview_canvas.configure(yscrollcommand=canvas_scrollbar.set)
        canvas_scrollbar.pack(fill="y", side="right")
        
        # 分辨率信息显示
        info_frame = ttk.LabelFrame(preview_frame, text="详细信息", padding=10)
        info_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.preview_info_text = tk.Text(info_frame, height=6, wrap="word",
                                       font=("Consolas", 9), state="disabled")
        self.preview_info_text.pack(fill="x")
        
        # 绘制初始预览
        self.draw_resolution_preview()
    
    def refresh_preset_buttons(self):
        """刷新预设按钮"""
        # 清空现有按钮
        for widget in self.preset_buttons_frame.winfo_children():
            widget.destroy()
        
        # 按分类组织按钮
        categories = self.resolution_presets.keys() if self.preset_category_var.get() == "全部" else [self.preset_category_var.get()]
        
        for category in categories:
            if category in self.resolution_presets:
                # 分类标题
                category_label = ttk.Label(self.preset_buttons_frame, text=category, 
                                        font=("微软雅黑", 12, "bold"))
                category_label.pack(anchor="w", pady=(10, 5))
                
                # 按钮网格
                button_grid = ttk.Frame(self.preset_buttons_frame)
                button_grid.pack(fill="x", pady=(0, 10))
                
                # 获取该分类的预设
                presets = self.resolution_presets[category]
                
                # 搜索过滤
                search_text = self.preset_search_var.get().lower()
                filtered_presets = {}
                if search_text:
                    for name, info in presets.items():
                        if (search_text in name.lower() or 
                            search_text in str(info["width"]) or 
                            search_text in str(info["height"])):
                            filtered_presets[name] = info
                else:
                    filtered_presets = presets
                
                # 创建按钮（3列布局）
                preset_items = list(filtered_presets.items())
                for i in range(0, len(preset_items), 3):
                    button_row = ttk.Frame(button_grid)
                    button_row.pack(fill="x", pady=2)
                    
                    for j in range(3):
                        if i + j < len(preset_items):
                            name, info = preset_items[i + j]
                            width, height = info["width"], info["height"]
                            
                            button = ttk.Button(button_row, 
                                              text=f"{width}x{height}",
                                              command=lambda w=width, h=height: self.set_resolution(w, h))
                            button.pack(side="left", padx=2, pady=2, fill="x", expand=True)
    
    def set_resolution(self, width, height):
        """设置分辨率"""
        self.current_resolution = {"width": width, "height": height}
        self.width_var.set(width)
        self.height_var.set(height)
        
        # 更新显示
        self.update_resolution_display()
        
        # 更新自定义比例
        self.update_custom_aspect_ratio()
        
        # 更新所有相关显示
        self.update_all_displays()
        
        # 通知回调
        if self.callback:
            self.callback("resolution_changed", {
                "width": width,
                "height": height,
                "resolution": self.current_resolution
            })
        
        # 显示确认信息
        messagebox.showinfo("分辨率设置", f"分辨率已设置为: {width} x {height}")
    
    def update_resolution_display(self):
        """更新分辨率显示"""
        width, height = self.current_resolution["width"], self.current_resolution["height"]
        pixel_count = width * height
        aspect_ratio = width / height
        
        # 更新显示标签
        self.current_res_label.config(text=f"{width} x {height}")
        self.pixel_count_label.config(text=f"{pixel_count:,}")
        self.aspect_ratio_label.config(text=f"{aspect_ratio:.2f}:1")
        
        # 更新性能评估
        if pixel_count <= 512 * 512:
            performance = "优秀"
            color = "green"
        elif pixel_count <= 1024 * 1024:
            performance = "良好"
            color = "green"
        elif pixel_count <= 2048 * 2048:
            performance = "一般"
            color = "orange"
        else:
            performance = "较慢"
            color = "red"
        
        self.performance_label.config(text=performance, foreground=color)
    
    def update_custom_aspect_ratio(self):
        """更新自定义宽高比"""
        width, height = self.current_resolution["width"], self.current_resolution["height"]
        ratio = width / height
        
        # 找到最接近的分数表示
        from fractions import Fraction
        ratio_fraction = Fraction(ratio).limit_denominator(100)
        
        # 更新输入框
        self.ratio_width_var.set(str(ratio_fraction.numerator))
        self.ratio_height_var.set(str(ratio_fraction.denominator))
    
    def on_preset_search(self, *args):
        """预设搜索事件"""
        self.refresh_preset_buttons()
    
    def on_custom_dimension_change(self):
        """自定义尺寸变化事件"""
        width = self.width_var.get()
        height = self.height_var.get()
        
        # 如果锁定宽高比，调整另一个尺寸
        if self.lock_aspect_var.get():
            current_ratio = self.current_resolution["width"] / self.current_resolution["height"]
            if width != self.current_resolution["width"]:
                new_height = int(width / current_ratio)
                self.height_var.set(new_height)
            elif height != self.current_resolution["height"]:
                new_width = int(height * current_ratio)
                self.width_var.set(new_width)
        
        # 更新当前分辨率
        self.current_resolution = {"width": self.width_var.get(), "height": self.height_var.get()}
        self.update_resolution_display()
        self.update_resolution_suggestions()
        
        # 通知回调
        if self.callback:
            self.callback("resolution_changed", {
                "width": self.width_var.get(),
                "height": self.height_var.get(),
                "resolution": self.current_resolution
            })
    
    def set_aspect_ratio(self, ratio):
        """设置宽高比"""
        width = self.width_var.get()
        new_height = int(width / ratio)
        
        # 调整到64的倍数
        new_height = (new_height // 64) * 64
        
        self.height_var.set(new_height)
        self.on_custom_dimension_change()
    
    def apply_custom_aspect_ratio(self):
        """应用自定义宽高比"""
        try:
            ratio_width = int(self.ratio_width_var.get())
            ratio_height = int(self.ratio_height_var.get())
            
            if ratio_width <= 0 or ratio_height <= 0:
                messagebox.showerror("错误", "宽高比值必须大于0")
                return
            
            ratio = ratio_width / ratio_height
            
            # 基于当前宽度计算高度
            width = self.width_var.get()
            new_height = int(width / ratio)
            
            # 调整到64的倍数
            new_height = (new_height // 64) * 64
            
            self.height_var.set(new_height)
            self.on_custom_dimension_change()
            
            messagebox.showinfo("成功", f"已应用宽高比 {ratio_width}:{ratio_height}")
            
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字")
    
    def toggle_aspect_lock(self):
        """切换宽高比锁定"""
        if self.lock_aspect_var.get():
            messagebox.showinfo("提示", "宽高比已锁定，修改宽度或高度时将保持比例")
        else:
            messagebox.showinfo("提示", "宽高比锁定已取消")
    
    def update_resolution_suggestions(self):
        """更新分辨率建议"""
        width, height = self.current_resolution["width"], self.current_resolution["height"]
        pixel_count = width * height
        
        suggestions = f"当前分辨率分析:\n\n"
        suggestions += f"分辨率: {width} x {height}\n"
        suggestions += f"像素总数: {pixel_count:,}\n"
        suggestions += f"内存需求: {pixel_count * 4 / 1024 / 1024:.1f}MB (RGB)\n"
        suggestions += f"推荐用途: "
        
        if pixel_count <= 512 * 512:
            suggestions += "快速测试、小图生成\n"
            suggestions += "\n建议:\n"
            suggestions += "• 适合快速迭代和预览\n"
            suggestions += "• 内存使用较少，生成速度快\n"
            suggestions += "• 适合大批量生成"
        elif pixel_count <= 1024 * 1024:
            suggestions += "标准质量图片生成\n"
            suggestions += "\n建议:\n"
            suggestions += "• 平衡质量与性能\n"
            suggestions += "• 适合大多数应用场景\n"
            suggestions += "• 推荐用于正式生成"
        elif pixel_count <= 2048 * 2048:
            suggestions += "高质量图片生成\n"
            suggestions += "\n建议:\n"
            suggestions += "• 高质量输出，细节丰富\n"
            suggestions += "• 需要较多内存和时间\n"
            suggestions += "• 建议配合高分辨率修复使用"
        else:
            suggestions += "超高分辨率图片生成\n"
            suggestions += "\n建议:\n"
            suggestions += "• 极高质量，适合印刷\n"
            suggestions += "• 需要大量内存和计算资源\n"
            suggestions += "• 建议分步骤生成"
        
        self.suggestions_text.config(state="normal")
        self.suggestions_text.delete("1.0", "end")
        self.suggestions_text.insert("1.0", suggestions)
        self.suggestions_text.config(state="disabled")
    
    def apply_memory_level(self):
        """应用内存等级"""
        memory_level = self.memory_level_var.get()
        rule = self.optimization_rules.get(memory_level, {})
        
        if "max_pixels" in rule:
            recommendations = rule["recommended"]
            
            # 清空推荐列表
            self.recommended_listbox.delete(0, tk.END)
            
            # 添加推荐分辨率
            for width, height in recommendations:
                pixel_count = width * height
                aspect_ratio = width / height
                info = f"{width}x{height} ({pixel_count:,}像素, {aspect_ratio:.2f}:1)"
                self.recommended_listbox.insert(tk.END, info)
            
            messagebox.showinfo("成功", f"已应用 {memory_level} 等级推荐")
        else:
            messagebox.showerror("错误", "未找到对应的优化规则")
    
    def update_optimization_info(self):
        """更新优化信息"""
        memory_level = self.memory_level_var.get()
        
        advice_text = f"当前内存等级: {memory_level}\n\n"
        
        if memory_level == "low_memory":
            advice_text += "优化建议:\n"
            advice_text += "• 使用512x512或更低的分辨率\n"
            advice_text += "• 降低批量生成数量\n"
            advice_text += "• 关闭高分辨率修复\n"
            advice_text += "• 适合快速测试和预览"
        
        elif memory_level == "medium_memory":
            advice_text += "优化建议:\n"
            advice_text += "• 使用1024x1024分辨率\n"
            advice_text += "• 可以适当增加批量数量\n"
            advice_text += "• 可以启用高分辨率修复\n"
            advice_text += "• 平衡质量与性能"
        
        elif memory_level == "high_memory":
            advice_text += "优化建议:\n"
            advice_text += "• 可以使用1536x1536或更高分辨率\n"
            advice_text += "• 适合高质量输出\n"
            advice_text += "• 可以使用复杂的ControlNet组合\n"
            advice_text += "• 适合专业应用"
        
        elif memory_level == "ultra_memory":
            advice_text += "优化建议:\n"
            advice_text += "• 可以使用4K或更高分辨率\n"
            advice_text += "• 适合印刷级别的输出\n"
            advice_text += "• 需要大量内存和计算时间\n"
            advice_text += "• 建议分步骤生成"
        
        self.advice_text.config(state="normal")
        self.advice_text.delete("1.0", "end")
        self.advice_text.insert("1.0", advice_text)
        self.advice_text.config(state="disabled")
        
        # 应用当前等级
        self.apply_memory_level()
    
    def on_recommended_select(self, event):
        """推荐分辨率选择事件"""
        # 可以在这里添加选择处理逻辑
        pass
    
    def apply_recommended_resolution(self):
        """应用推荐分辨率"""
        selection = self.recommended_listbox.curselection()
        if selection:
            info = self.recommended_listbox.get(selection[0])
            # 解析信息获取尺寸
            parts = info.split(" (")[0]
            if "x" in parts:
                width, height = map(int, parts.split("x"))
                self.set_resolution(width, height)
        else:
            messagebox.showwarning("警告", "请先选择推荐分辨率")
    
    def show_recommended_details(self):
        """显示推荐详情"""
        selection = self.recommended_listbox.curselection()
        if selection:
            info = self.recommended_listbox.get(selection[0])
            messagebox.showinfo("推荐详情", info)
        else:
            messagebox.showwarning("警告", "请先选择推荐分辨率")
    
    def generate_batch_list(self):
        """生成批量列表"""
        try:
            widths = [int(w.strip()) for w in self.batch_width_var.get().split(",")]
            heights = [int(h.strip()) for h in self.batch_height_var.get().split(",")]
            
            # 清空现有列表
            for item in self.batch_tree.get_children():
                self.batch_tree.delete(item)
            
            # 生成批量列表
            for i, (width, height) in enumerate(zip(widths, heights), 1):
                pixel_count = width * height
                aspect_ratio = width / height
                
                # 判断建议用途
                if pixel_count <= 512 * 512:
                    usage = "快速测试"
                elif pixel_count <= 1024 * 1024:
                    usage = "标准生成"
                elif pixel_count <= 2048 * 2048:
                    usage = "高质量"
                else:
                    usage = "超高分辨率"
                
                self.batch_tree.insert("", "end", values=(
                    i, width, height, pixel_count, f"{aspect_ratio:.2f}:1", usage
                ))
            
            messagebox.showinfo("成功", f"已生成 {len(widths)} 个分辨率配置")
            
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字，用逗号分隔")
    
    def clear_batch_list(self):
        """清空批量列表"""
        for item in self.batch_tree.get_children():
            self.batch_tree.delete(item)
        messagebox.showinfo("成功", "批量列表已清空")
    
    def export_batch_list(self):
        """导出批量列表"""
        items = self.batch_tree.get_children()
        if not items:
            messagebox.showwarning("警告", "批量列表为空")
            return
        
        from tkinter import filedialog
        
        file_path = filedialog.asksaveasfilename(
            title="导出批量分辨率列表",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("批量分辨率配置\n")
                    f.write("=" * 30 + "\n\n")
                    
                    for item in items:
                        values = self.batch_tree.item(item)["values"]
                        f.write(f"配置 {values[0]}: {values[1]}x{values[2]}\n")
                        f.write(f"  像素数: {values[3]:,}\n")
                        f.write(f"  宽高比: {values[4]}\n")
                        f.write(f"  建议用途: {values[5]}\n\n")
                
                messagebox.showinfo("成功", f"批量列表已导出到: {file_path}")
                
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {e}")
    
    def apply_all_batch_resolutions(self):
        """应用所有批量分辨率"""
        items = self.batch_tree.get_children()
        if not items:
            messagebox.showwarning("警告", "批量列表为空")
            return
        
        # 这里可以实现依次应用所有分辨率的逻辑
        messagebox.showinfo("提示", "批量应用功能将在后续版本中实现")
    
    def update_batch_preview(self):
        """更新批量预览"""
        # 初始状态下显示一些示例
        sample_data = [
            ("1", "512", "512", "262,144", "1.00:1", "快速测试"),
            ("2", "768", "768", "589,824", "1.00:1", "标准生成"),
            ("3", "1024", "1024", "1,048,576", "1.00:1", "高质量")
        ]
        
        for item in sample_data:
            self.batch_tree.insert("", "end", values=item)
    
    def refresh_preview(self):
        """刷新预览"""
        self.draw_resolution_preview()
        self.update_preview_info()
    
    def draw_resolution_preview(self):
        """绘制分辨率预览"""
        width, height = self.current_resolution["width"], self.current_resolution["height"]
        scale = self.preview_scale_var.get()
        
        # 清空画布
        self.preview_canvas.delete("all")
        
        # 计算显示尺寸
        display_width = width * scale
        display_height = height * scale
        
        # 绘制背景
        self.preview_canvas.create_rectangle(0, 0, display_width, display_height, 
                                          fill="lightblue", outline="blue", width=2)
        
        # 绘制网格
        if self.show_grid_var.get():
            grid_size = 64 * scale
            for x in range(0, int(display_width), int(grid_size)):
                self.preview_canvas.create_line(x, 0, x, display_height, fill="gray", dash="2,2")
            
            for y in range(0, int(display_height), int(grid_size)):
                self.preview_canvas.create_line(0, y, display_width, y, fill="gray", dash="2,2")
        
        # 绘制标签
        if self.show_labels_var.get():
            self.preview_canvas.create_text(display_width/2, 20, 
                                          text=f"{width} x {height}", 
                                          font=("Arial", 12, "bold"), fill="darkblue")
            
            self.preview_canvas.create_text(display_width/2, display_height-20, 
                                          text=f"像素: {width*height:,}", 
                                          font=("Arial", 10), fill="darkgreen")
        
        # 设置滚动区域
        self.preview_canvas.configure(scrollregion=(0, 0, display_width, display_height))
    
    def update_preview_info(self):
        """更新预览信息"""
        width, height = self.current_resolution["width"], self.current_resolution["height"]
        pixel_count = width * height
        
        info_text = f"分辨率信息:\n"
        info_text += f"尺寸: {width} x {height} 像素\n"
        info_text += f"像素总数: {pixel_count:,}\n"
        info_text += f"内存需求: {pixel_count * 4 / 1024 / 1024:.1f} MB (RGB)\n"
        info_text += f"宽高比: {width/height:.3f}:1\n"
        info_text += f"显示缩放: {self.preview_scale_var.get():.1f}x\n"
        info_text += f"网格显示: {'开启' if self.show_grid_var.get() else '关闭'}\n"
        info_text += f"标签显示: {'开启' if self.show_labels_var.get() else '关闭'}"
        
        self.preview_info_text.config(state="normal")
        self.preview_info_text.delete("1.0", "end")
        self.preview_info_text.insert("1.0", info_text)
        self.preview_info_text.config(state="disabled")
    
    def update_all_displays(self):
        """更新所有显示"""
        self.update_resolution_display()
        self.update_resolution_suggestions()
        self.refresh_preview()
    
    def get_current_resolution(self):
        """获取当前分辨率"""
        return self.current_resolution.copy()
    
    def set_resolution_preset(self, preset_name):
        """设置分辨率预设"""
        # 在所有预设中查找
        for category, presets in self.resolution_presets.items():
            if preset_name in presets:
                resolution = presets[preset_name]
                self.set_resolution(resolution["width"], resolution["height"])
                return True
        return False