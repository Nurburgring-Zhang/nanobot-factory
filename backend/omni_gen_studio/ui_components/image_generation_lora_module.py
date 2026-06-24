#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片生成 - LoRA模组
支持多LoRA加载、权重控制、冲突检测和兼容性管理

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import shutil
from typing import Dict, List, Optional, Any, Tuple
import logging
from pathlib import Path
import re

logger = logging.getLogger(__name__)

class LoRAModule:
    """图片生成LoRA管理模组"""
    
    def __init__(self, parent_frame, callback=None):
        self.parent_frame = parent_frame
        self.callback = callback
        self.loaded_loras = {}  # {name: {"path": str, "weight": float, "enabled": bool, "info": dict}}
        self.lora_categories = {
            "角色人物": {
                "人像风格": ["anime_style", "realistic_portrait", "fantasy_character", "cyberpunk_character"],
                "特定角色": ["anime_character", "game_character", "movie_character"],
                "人物特征": ["beautiful_face", "expressive_eyes", "detailed_hair", "elegant_pose"]
            },
            "艺术风格": {
                "绘画风格": ["oil_painting", "watercolor", "sketch_style", "digital_art"],
                "摄影风格": ["portrait_photography", "street_photography", "nature_photography"],
                "艺术流派": ["impressionist", "abstract_art", "minimalist", "baroque"]
            },
            "场景环境": {
                "自然风景": ["landscape", "mountain_view", "ocean_scene", "forest_path"],
                "城市环境": ["cityscape", "street_scene", "interior_design", "architectural"],
                "幻想场景": ["fantasy_landscape", "cyberpunk_city", "space_station", "medieval_castle"]
            },
            "技术效果": {
                "画质增强": ["high_quality", "detailed_texture", "sharp_focus", "color_grading"],
                "特效渲染": ["lighting_effects", "volumetric_lighting", "bokeh_effect", "motion_blur"],
                "风格转换": ["artistic_filter", "vintage_style", "modern_style", "classic_style"]
            }
        }
        
        # 兼容性检查规则
        self.compatibility_rules = {
            "conflicts": {
                "realistic_portrait": ["anime_style", "cartoon_style"],
                "anime_style": ["realistic_portrait", "photography_style"],
                "oil_painting": ["digital_art", "photography_style"],
                "photography": ["oil_painting", "watercolor", "sketch_style"]
            },
            "synergies": {
                "beautiful_face": ["detailed_eyes", "elegant_pose"],
                "landscape": ["lighting_effects", "color_grading"],
                "high_quality": ["sharp_focus", "detailed_texture"]
            },
            "categories": {
                "portrait": ["beautiful_face", "realistic_portrait", "anime_character", "expressive_eyes"],
                "style": ["oil_painting", "watercolor", "digital_art", "photography"],
                "environment": ["landscape", "cityscape", "interior", "fantasy_landscape"],
                "technical": ["high_quality", "lighting_effects", "bokeh_effect"]
            }
        }
        
        # 推荐权重配置
        self.recommended_weights = {
            "character": {"min": 0.3, "max": 1.0, "default": 0.7},
            "style": {"min": 0.1, "max": 0.8, "default": 0.5},
            "environment": {"min": 0.2, "max": 0.9, "default": 0.6},
            "technical": {"min": 0.1, "max": 0.7, "default": 0.4}
        }
        
        self.create_ui()
        self.scan_local_loras()
    
    def create_ui(self):
        """创建LoRA管理UI"""
        # 主容器
        main_container = ttk.Frame(self.parent_frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 标题
        title_label = ttk.Label(main_container, text="LoRA管理", 
                               font=("微软雅黑", 14, "bold"))
        title_label.pack(anchor="w", pady=(0, 15))
        
        # LoRA库和已加载区域
        self.create_library_and_loaded_area(main_container)
        
        # LoRA选项卡
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill="both", expand=True, pady=(10, 0))
        
        # LoRA库选项卡
        self.create_library_tab(notebook)
        
        # 已加载LoRA选项卡
        self.create_loaded_tab(notebook)
        
        # 权重控制选项卡
        self.create_weights_tab(notebook)
        
        # 兼容性检查选项卡
        self.create_compatibility_tab(notebook)
    
    def create_library_and_loaded_area(self, parent):
        """创建LoRA库和已加载区域"""
        status_frame = ttk.LabelFrame(parent, text="当前状态", padding=10)
        status_frame.pack(fill="x", pady=(0, 15))
        
        # 状态信息
        info_frame = ttk.Frame(status_frame)
        info_frame.pack(fill="x")
        
        ttk.Label(info_frame, text="已加载LoRA:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.loaded_count_label = ttk.Label(info_frame, text="0个", 
                                           font=("微软雅黑", 10, "bold"))
        self.loaded_count_label.grid(row=0, column=1, sticky="w", padx=(0, 20))
        
        ttk.Label(info_frame, text="总权重:").grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.total_weight_label = ttk.Label(info_frame, text="0.0", 
                                           foreground="blue", font=("微软雅黑", 10, "bold"))
        self.total_weight_label.grid(row=0, column=3, sticky="w", padx=(0, 20))
        
        ttk.Label(info_frame, text="状态:").grid(row=1, column=0, sticky="w", padx=(0, 10))
        self.status_label = ttk.Label(info_frame, text="正常", foreground="green")
        self.status_label.grid(row=1, column=1, sticky="w")
        
        # 控制按钮
        button_frame = ttk.Frame(info_frame)
        button_frame.grid(row=2, column=0, columnspan=4, pady=(10, 0))
        
        ttk.Button(button_frame, text="批量加载", 
                  command=self.batch_load_loras).pack(side="left", padx=(0, 10))
        
        ttk.Button(button_frame, text="批量卸载", 
                  command=self.batch_unload_loras).pack(side="left", padx=(0, 10))
        
        ttk.Button(button_frame, text="导出配置", 
                  command=self.export_lora_config).pack(side="left", padx=(0, 10))
        
        ttk.Button(button_frame, text="导入配置", 
                  command=self.import_lora_config).pack(side="left")
        
        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(3, weight=1)
    
    def create_library_tab(self, notebook):
        """创建LoRA库选项卡"""
        library_frame = ttk.Frame(notebook)
        notebook.add(library_frame, text="LoRA库")
        
        # 搜索和筛选
        filter_frame = ttk.Frame(library_frame)
        filter_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(filter_frame, text="搜索:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self.on_library_search)
        search_entry = ttk.Entry(filter_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side="left", padx=(5, 10))
        
        ttk.Label(filter_frame, text="分类:").pack(side="left")
        self.category_var = tk.StringVar()
        category_combo = ttk.Combobox(filter_frame, textvariable=self.category_var, width=15)
        category_combo['values'] = ["全部"] + list(self.lora_categories.keys())
        category_combo.pack(side="left", padx=(5, 10))
        
        ttk.Button(filter_frame, text="浏览文件夹", 
                  command=self.browse_lora_folder).pack(side="left", padx=(10, 0))
        
        # LoRA列表
        list_frame = ttk.LabelFrame(library_frame, text="可用LoRA", padding=10)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 创建Treeview
        columns = ("名称", "分类", "权重范围", "大小", "状态")
        self.library_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        
        for col in columns:
            self.library_tree.heading(col, text=col)
            self.library_tree.column(col, width=120)
        
        library_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.library_tree.yview)
        self.library_tree.configure(yscrollcommand=library_scrollbar.set)
        
        self.library_tree.pack(side="left", fill="both", expand=True)
        library_scrollbar.pack(side="right", fill="y")
        
        self.library_tree.bind("<<TreeviewSelect>>", self.on_library_select)
        self.library_tree.bind("<Double-1>", self.on_library_double_click)
        
        # 操作按钮
        button_frame = ttk.Frame(list_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="加载", 
                  command=self.load_selected_lora).pack(side="left", padx=(0, 10))
        
        ttk.Button(button_frame, text="详细信息", 
                  command=self.show_lora_details).pack(side="left", padx=(0, 10))
        
        ttk.Button(button_frame, text="删除", 
                  command=self.delete_lora).pack(side="left")
    
    def create_loaded_tab(self, notebook):
        """创建已加载LoRA选项卡"""
        loaded_frame = ttk.Frame(notebook)
        notebook.add(loaded_frame, text="已加载")
        
        # 已加载LoRA列表
        loaded_list_frame = ttk.LabelFrame(loaded_frame, text="当前加载的LoRA", padding=10)
        loaded_list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 创建Treeview
        columns = ("名称", "权重", "状态", "路径")
        self.loaded_tree = ttk.Treeview(loaded_list_frame, columns=columns, show="headings", height=12)
        
        for col in columns:
            self.loaded_tree.heading(col, text=col)
            self.loaded_tree.column(col, width=150)
        
        loaded_scrollbar = ttk.Scrollbar(loaded_list_frame, orient="vertical", command=self.loaded_tree.yview)
        self.loaded_tree.configure(yscrollcommand=loaded_scrollbar.set)
        
        self.loaded_tree.pack(side="left", fill="both", expand=True)
        loaded_scrollbar.pack(side="right", fill="y")
        
        self.loaded_tree.bind("<<TreeviewSelect>>", self.on_loaded_select)
        
        # 操作按钮
        button_frame = ttk.Frame(loaded_list_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="卸载", 
                  command=self.unload_selected_lora).pack(side="left", padx=(0, 10))
        
        ttk.Button(button_frame, text="启用/禁用", 
                  command=self.toggle_lora_status).pack(side="left", padx=(0, 10))
        
        ttk.Button(button_frame, text="应用配置", 
                  command=self.apply_loaded_config).pack(side="left")
    
    def create_weights_tab(self, notebook):
        """创建权重控制选项卡"""
        weights_frame = ttk.Frame(notebook)
        notebook.add(weights_frame, text="权重控制")
        
        # 权重设置面板
        self.create_weight_control_panel(weights_frame)
        
        # 批量权重调整
        batch_frame = ttk.LabelFrame(weights_frame, text="批量调整", padding=10)
        batch_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        batch_controls = ttk.Frame(batch_frame)
        batch_controls.pack(fill="x")
        
        ttk.Label(batch_controls, text="调整方式:").pack(side="left")
        self.batch_operation = tk.StringVar(value="multiply")
        batch_combo = ttk.Combobox(batch_controls, textvariable=self.batch_operation, width=15)
        batch_combo['values'] = ["乘以", "加上", "设置到", "重置到默认"]
        batch_combo.pack(side="left", padx=(5, 10))
        
        self.batch_value = tk.DoubleVar(value=1.0)
        ttk.Entry(batch_controls, textvariable=self.batch_value, width=10).pack(side="left", padx=(0, 10))
        
        ttk.Button(batch_controls, text="应用", 
                  command=self.apply_batch_weight_operation).pack(side="left")
        
        # 权重预设
        preset_frame = ttk.LabelFrame(weights_frame, text="权重预设", padding=10)
        preset_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        preset_buttons = ttk.Frame(preset_frame)
        preset_buttons.pack(fill="x")
        
        ttk.Button(preset_buttons, text="人物预设", 
                  command=lambda: self.apply_weight_preset("character")).pack(side="left", padx=(0, 10))
        
        ttk.Button(preset_buttons, text="风格预设", 
                  command=lambda: self.apply_weight_preset("style")).pack(side="left", padx=(0, 10))
        
        ttk.Button(preset_buttons, text="环境预设", 
                  command=lambda: self.apply_weight_preset("environment")).pack(side="left", padx=(0, 10))
        
        ttk.Button(preset_buttons, text="技术预设", 
                  command=lambda: self.apply_weight_preset("technical")).pack(side="left", padx=(0, 10))
        
        ttk.Button(preset_buttons, text="自定义", 
                  command=self.apply_custom_preset).pack(side="left")
    
    def create_weight_control_panel(self, parent):
        """创建权重控制面板"""
        weight_frame = ttk.LabelFrame(parent, text="权重设置", padding=10)
        weight_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # 当前选中的LoRA权重控制
        control_frame = ttk.Frame(weight_frame)
        control_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(control_frame, text="选中的LoRA:", font=("微软雅黑", 10, "bold")).pack(anchor="w")
        
        self.selected_lora_name = ttk.Label(control_frame, text="无", foreground="gray")
        self.selected_lora_name.pack(anchor="w", pady=(2, 10))
        
        # 权重滑块
        slider_frame = ttk.Frame(control_frame)
        slider_frame.pack(fill="x", pady=(5, 0))
        
        ttk.Label(slider_frame, text="权重:").pack(side="left")
        
        self.weight_slider = tk.Scale(slider_frame, from_=0.0, to=2.0, orient="horizontal", 
                                     resolution=0.01, length=300)
        self.weight_slider.pack(side="left", fill="x", expand=True, padx=(10, 10))
        
        self.weight_value_label = ttk.Label(slider_frame, text="0.00", 
                                          font=("Consolas", 10), foreground="blue")
        self.weight_value_label.pack(side="left", padx=(10, 0))
        
        self.weight_slider.bind("<Motion>", self.on_weight_change)
        
        # 快速设置按钮
        quick_frame = ttk.Frame(control_frame)
        quick_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Label(quick_frame, text="快速设置:").pack(side="left")
        
        for weight in [0.1, 0.5, 0.7, 1.0, 1.2, 1.5]:
            ttk.Button(quick_frame, text=str(weight), 
                      command=lambda w=weight: self.set_weight(w)).pack(side="left", padx=(2, 0))
        
        # 权重范围建议
        suggestion_frame = ttk.LabelFrame(control_frame, text="权重建议", padding=5)
        suggestion_frame.pack(fill="x", pady=(10, 0))
        
        self.suggestion_text = tk.Text(suggestion_frame, height=3, wrap="word", 
                                      font=("微软雅黑", 9), state="disabled")
        self.suggestion_text.pack(fill="x")
    
    def create_compatibility_tab(self, notebook):
        """创建兼容性检查选项卡"""
        compat_frame = ttk.Frame(notebook)
        notebook.add(compat_frame, text="兼容性")
        
        # 冲突检测
        conflict_frame = ttk.LabelFrame(compat_frame, text="冲突检测", padding=10)
        conflict_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(conflict_frame, text="检查冲突", 
                  command=self.check_conflicts).pack(anchor="w", pady=(0, 10))
        
        # 冲突列表
        self.conflict_listbox = tk.Listbox(conflict_frame, height=8)
        self.conflict_listbox.pack(fill="both", expand=True)
        
        # 协同效果
        synergy_frame = ttk.LabelFrame(compat_frame, text="协同效果", padding=10)
        synergy_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        ttk.Button(synergy_frame, text="检查协同", 
                  command=self.check_synergies).pack(anchor="w", pady=(0, 10))
        
        # 协同列表
        self.synergy_listbox = tk.Listbox(synergy_frame, height=8)
        self.synergy_listbox.pack(fill="both", expand=True)
    
    def scan_local_loras(self):
        """扫描本地LoRA文件"""
        # 常见的LoRA目录
        lora_directories = [
            "models/LoRA",
            "models/lora",
            "models/Lora",
            "models/StableDiffusion/lora",
            "ComfyUI/models/lora",
            "ComfyUI/custom_nodes/ComfyUI-Impact-Pack/models/lora"
        ]
        
        # 支持的文件扩展名
        lora_extensions = [".safetensors", ".ckpt", ".pt", ".pth"]
        
        self.local_loras = {}
        
        for lora_dir in lora_directories:
            if os.path.exists(lora_dir):
                try:
                    for file in os.listdir(lora_dir):
                        if any(file.endswith(ext) for ext in lora_extensions):
                            file_path = os.path.join(lora_dir, file)
                            file_size = os.path.getsize(file_path)
                            file_size_mb = file_size / (1024 * 1024)
                            
                            # 解析文件名获取信息
                            info = self.parse_lora_filename(file)
                            
                            lora_info = {
                                "name": info["name"],
                                "path": file_path,
                                "size": f"{file_size_mb:.1f}MB",
                                "category": info["category"],
                                "weight_range": info["weight_range"],
                                "description": info.get("description", ""),
                                "enabled": False,
                                "weight": 0.0
                            }
                            
                            self.local_loras[info["name"]] = lora_info
                            
                except Exception as e:
                    logger.error(f"扫描目录失败 {lora_dir}: {e}")
        
        self.refresh_library_list()
    
    def parse_lora_filename(self, filename):
        """解析LoRA文件名获取信息"""
        name_without_ext = os.path.splitext(filename)[0]
        
        # 尝试从文件名中提取信息
        info = {"name": name_without_ext, "category": "未分类", "weight_range": "0.1-1.0"}
        
        # 检查是否是分类关键词
        for category, subcategories in self.lora_categories.items():
            for subcategory, loras in subcategories.items():
                for lora in loras:
                    if lora.lower() in name_without_ext.lower():
                        info["category"] = category
                        break
        
        # 检查权重建议
        if "high_weight" in name_without_ext.lower():
            info["weight_range"] = "0.8-1.5"
        elif "low_weight" in name_without_ext.lower():
            info["weight_range"] = "0.1-0.5"
        elif "medium_weight" in name_without_ext.lower():
            info["weight_range"] = "0.3-0.8"
        
        return info
    
    def refresh_library_list(self):
        """刷新LoRA库列表"""
        # 清空现有列表
        for item in self.library_tree.get_children():
            self.library_tree.delete(item)
        
        # 填充列表
        search_text = self.search_var.get().lower()
        category_filter = self.category_var.get()
        
        for lora_name, lora_info in self.local_loras.items():
            # 应用搜索和筛选
            if search_text and search_text not in lora_name.lower():
                continue
            
            if category_filter and category_filter != "全部":
                if category_filter not in lora_info["category"]:
                    continue
            
            status = "已加载" if lora_name in self.loaded_loras else "未加载"
            
            self.library_tree.insert("", "end", values=(
                lora_name,
                lora_info["category"],
                lora_info["weight_range"],
                lora_info["size"],
                status
            ))
    
    def refresh_loaded_list(self):
        """刷新已加载LoRA列表"""
        # 清空现有列表
        for item in self.loaded_tree.get_children():
            self.loaded_tree.delete(item)
        
        # 填充列表
        for lora_name, lora_info in self.loaded_loras.items():
            status = "启用" if lora_info["enabled"] else "禁用"
            
            self.loaded_tree.insert("", "end", values=(
                lora_name,
                f"{lora_info['weight']:.2f}",
                status,
                lora_info["path"]
            ))
        
        # 更新状态信息
        self.loaded_count_label.config(text=f"{len(self.loaded_loras)}个")
        
        total_weight = sum(lora_info["weight"] for lora_info in self.loaded_loras.values() 
                          if lora_info["enabled"])
        self.total_weight_label.config(text=f"{total_weight:.2f}")
        
        if total_weight > 3.0:
            self.status_label.config(text="权重过高", foreground="orange")
        else:
            self.status_label.config(text="正常", foreground="green")
    
    def on_library_search(self, *args):
        """库搜索事件"""
        self.refresh_library_list()
    
    def on_library_select(self, event):
        """库选择事件"""
        selection = self.library_tree.selection()
        if selection:
            item = self.library_tree.item(selection[0])
            lora_name = item["values"][0]
            
            # 显示建议
            self.show_weight_suggestion(lora_name)
    
    def on_library_double_click(self, event):
        """库双击事件"""
        self.load_selected_lora()
    
    def on_loaded_select(self, event):
        """已加载LoRA选择事件"""
        selection = self.loaded_tree.selection()
        if selection:
            item = self.loaded_tree.item(selection[0])
            lora_name = item["values"][0]
            weight = float(item["values"][1])
            
            # 更新权重控制面板
            self.selected_lora_name.config(text=lora_name)
            self.weight_slider.set(weight)
            self.weight_value_label.config(text=f"{weight:.2f}")
    
    def on_weight_change(self, event):
        """权重变化事件"""
        weight = self.weight_slider.get()
        self.weight_value_label.config(text=f"{weight:.2f}")
        
        # 更新已加载的LoRA
        selection = self.loaded_tree.selection()
        if selection:
            item = self.loaded_tree.item(selection[0])
            lora_name = item["values"][0]
            
            if lora_name in self.loaded_loras:
                self.loaded_loras[lora_name]["weight"] = weight
                self.refresh_loaded_list()
                
                if self.callback:
                    self.callback("lora_weight_changed", {
                        "name": lora_name,
                        "weight": weight
                    })
    
    def show_weight_suggestion(self, lora_name):
        """显示权重建议"""
        suggestion_text = ""
        
        if lora_name in self.local_loras:
            lora_info = self.local_loras[lora_name]
            category = lora_info["category"]
            
            if category in self.lora_categories:
                if category == "角色人物":
                    suggestion_text = "建议权重: 0.5-1.0\n主要用于角色特征增强"
                elif category == "艺术风格":
                    suggestion_text = "建议权重: 0.3-0.8\n用于风格转换和艺术效果"
                elif category == "场景环境":
                    suggestion_text = "建议权重: 0.4-0.9\n用于环境和背景增强"
                elif category == "技术效果":
                    suggestion_text = "建议权重: 0.2-0.6\n用于画质和技术增强"
        
        self.suggestion_text.config(state="normal")
        self.suggestion_text.delete("1.0", "end")
        self.suggestion_text.insert("1.0", suggestion_text)
        self.suggestion_text.config(state="disabled")
    
    def set_weight(self, weight):
        """设置权重"""
        self.weight_slider.set(weight)
        self.weight_value_label.config(text=f"{weight:.2f}")
        self.on_weight_change(None)
    
    def load_selected_lora(self):
        """加载选中的LoRA"""
        selection = self.library_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择LoRA")
            return
        
        item = self.library_tree.item(selection[0])
        lora_name = item["values"][0]
        
        if lora_name in self.loaded_loras:
            messagebox.showwarning("警告", f"LoRA '{lora_name}' 已经加载")
            return
        
        # 获取默认权重
        default_weight = 0.7
        if lora_name in self.local_loras:
            lora_info = self.local_loras[lora_name]
            category = lora_info["category"]
            
            if category in ["角色人物"]:
                default_weight = self.recommended_weights["character"]["default"]
            elif category in ["艺术风格"]:
                default_weight = self.recommended_weights["style"]["default"]
            elif category in ["场景环境"]:
                default_weight = self.recommended_weights["environment"]["default"]
            elif category in ["技术效果"]:
                default_weight = self.recommended_weights["technical"]["default"]
        
        # 添加到已加载列表
        self.loaded_loras[lora_name] = {
            "path": self.local_loras[lora_name]["path"],
            "weight": default_weight,
            "enabled": True,
            "info": self.local_loras[lora_name]
        }
        
        self.refresh_loaded_list()
        self.refresh_library_list()
        
        if self.callback:
            self.callback("lora_loaded", {
                "name": lora_name,
                "weight": default_weight,
                "path": self.local_loras[lora_name]["path"]
            })
        
        messagebox.showinfo("成功", f"LoRA '{lora_name}' 加载成功，权重: {default_weight}")
    
    def unload_selected_lora(self):
        """卸载选中的LoRA"""
        selection = self.loaded_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择LoRA")
            return
        
        item = self.loaded_tree.item(selection[0])
        lora_name = item["values"][0]
        
        if lora_name in self.loaded_loras:
            del self.loaded_loras[lora_name]
            
            self.refresh_loaded_list()
            self.refresh_library_list()
            
            if self.callback:
                self.callback("lora_unloaded", {"name": lora_name})
            
            messagebox.showinfo("成功", f"LoRA '{lora_name}' 已卸载")
    
    def toggle_lora_status(self):
        """切换LoRA状态"""
        selection = self.loaded_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择LoRA")
            return
        
        item = self.loaded_tree.item(selection[0])
        lora_name = item["values"][0]
        current_status = item["values"][2]
        
        if lora_name in self.loaded_loras:
            new_status = not self.loaded_loras[lora_name]["enabled"]
            self.loaded_loras[lora_name]["enabled"] = new_status
            
            self.refresh_loaded_list()
            
            if self.callback:
                self.callback("lora_status_changed", {
                    "name": lora_name,
                    "enabled": new_status
                })
            
            status_text = "启用" if new_status else "禁用"
            messagebox.showinfo("成功", f"LoRA '{lora_name}' 已{status_text}")
    
    def batch_load_loras(self):
        """批量加载LoRA"""
        selection = self.library_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要加载的LoRA")
            return
        
        # 获取选择的LoRA
        selected_loras = []
        for item in selection:
            item_data = self.library_tree.item(item)
            selected_loras.append(item_data["values"][0])
        
        # 确认对话框
        result = messagebox.askyesno("确认", f"确定要加载 {len(selected_loras)} 个LoRA吗？")
        if not result:
            return
        
        # 批量加载
        for lora_name in selected_loras:
            if lora_name not in self.loaded_loras:
                self.loaded_loras[lora_name] = {
                    "path": self.local_loras[lora_name]["path"],
                    "weight": 0.7,
                    "enabled": True,
                    "info": self.local_loras[lora_name]
                }
        
        self.refresh_loaded_list()
        self.refresh_library_list()
        
        messagebox.showinfo("成功", f"已批量加载 {len(selected_loras)} 个LoRA")
    
    def batch_unload_loras(self):
        """批量卸载LoRA"""
        selection = self.loaded_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要卸载的LoRA")
            return
        
        selected_loras = []
        for item in selection:
            item_data = self.loaded_tree.item(item)
            selected_loras.append(item_data["values"][0])
        
        result = messagebox.askyesno("确认", f"确定要卸载 {len(selected_loras)} 个LoRA吗？")
        if not result:
            return
        
        for lora_name in selected_loras:
            if lora_name in self.loaded_loras:
                del self.loaded_loras[lora_name]
        
        self.refresh_loaded_list()
        self.refresh_library_list()
        
        messagebox.showinfo("成功", f"已批量卸载 {len(selected_loras)} 个LoRA")
    
    def apply_batch_weight_operation(self):
        """应用批量权重操作"""
        operation = self.batch_operation.get()
        value = self.batch_value.get()
        
        if not self.loaded_loras:
            messagebox.showwarning("警告", "没有已加载的LoRA")
            return
        
        if operation == "乘以":
            for lora_info in self.loaded_loras.values():
                lora_info["weight"] *= value
        
        elif operation == "加上":
            for lora_info in self.loaded_loras.values():
                lora_info["weight"] += value
        
        elif operation == "设置到":
            for lora_info in self.loaded_loras.values():
                lora_info["weight"] = value
        
        elif operation == "重置到默认":
            for lora_name, lora_info in self.loaded_loras.items():
                category = lora_info["info"]["category"]
                if category in ["角色人物"]:
                    lora_info["weight"] = self.recommended_weights["character"]["default"]
                elif category in ["艺术风格"]:
                    lora_info["weight"] = self.recommended_weights["style"]["default"]
                elif category in ["场景环境"]:
                    lora_info["weight"] = self.recommended_weights["environment"]["default"]
                elif category in ["技术效果"]:
                    lora_info["weight"] = self.recommended_weights["technical"]["default"]
        
        self.refresh_loaded_list()
        
        if self.callback:
            self.callback("lora_batch_weight_changed", {
                "operation": operation,
                "value": value,
                "loras": list(self.loaded_loras.keys())
            })
    
    def apply_weight_preset(self, preset_type):
        """应用权重预设"""
        if not self.loaded_loras:
            messagebox.showwarning("警告", "没有已加载的LoRA")
            return
        
        for lora_name, lora_info in self.loaded_loras.items():
            category = lora_info["info"]["category"]
            
            if preset_type == "character" and category in ["角色人物"]:
                lora_info["weight"] = self.recommended_weights["character"]["default"]
            elif preset_type == "style" and category in ["艺术风格"]:
                lora_info["weight"] = self.recommended_weights["style"]["default"]
            elif preset_type == "environment" and category in ["场景环境"]:
                lora_info["weight"] = self.recommended_weights["environment"]["default"]
            elif preset_type == "technical" and category in ["技术效果"]:
                lora_info["weight"] = self.recommended_weights["technical"]["default"]
        
        self.refresh_loaded_list()
        messagebox.showinfo("成功", f"已应用{preset_type}权重预设")
    
    def apply_custom_preset(self):
        """应用自定义预设"""
        # 创建自定义预设对话框
        dialog = tk.Toplevel(self.parent_frame)
        dialog.title("自定义权重预设")
        dialog.geometry("400x300")
        dialog.transient(self.parent_frame)
        dialog.grab_set()
        
        ttk.Label(dialog, text="请输入每个分类的权重:", font=("微软雅黑", 10, "bold")).pack(pady=10)
        
        # 分类权重设置
        weights_frame = ttk.Frame(dialog)
        weights_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        categories = ["角色人物", "艺术风格", "场景环境", "技术效果"]
        weight_vars = {}
        
        for category in categories:
            frame = ttk.Frame(weights_frame)
            frame.pack(fill="x", pady=5)
            
            ttk.Label(frame, text=f"{category}:").pack(side="left")
            var = tk.DoubleVar(value=0.7)
            entry = ttk.Entry(frame, textvariable=var, width=10)
            entry.pack(side="right")
            weight_vars[category] = var
        
        def apply_custom_preset():
            if not self.loaded_loras:
                messagebox.showwarning("警告", "没有已加载的LoRA")
                return
            
            for lora_name, lora_info in self.loaded_loras.items():
                category = lora_info["info"]["category"]
                if category in weight_vars:
                    lora_info["weight"] = weight_vars[category].get()
            
            self.refresh_loaded_list()
            dialog.destroy()
            
            if self.callback:
                self.callback("lora_custom_preset_applied", weight_vars)
            
            messagebox.showinfo("成功", "自定义权重预设已应用")
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", pady=10)
        
        ttk.Button(button_frame, text="确定", command=apply_custom_preset).pack(side="left", padx=(0, 10))
        ttk.Button(button_frame, text="取消", command=dialog.destroy).pack(side="left")
    
    def check_conflicts(self):
        """检查冲突"""
        self.conflict_listbox.delete(0, tk.END)
        
        loaded_loras = list(self.loaded_loras.keys())
        conflicts = []
        
        for lora1 in loaded_loras:
            for lora2 in loaded_loras:
                if lora1 != lora2:
                    lora1_clean = self.clean_lora_name(lora1)
                    lora2_clean = self.clean_lora_name(lora2)
                    
                    # 检查冲突规则
                    if (lora1_clean in self.compatibility_rules["conflicts"] and
                        lora2_clean in self.compatibility_rules["conflicts"][lora1_clean]):
                        conflicts.append(f"{lora1} 与 {lora2} 可能存在冲突")
        
        if conflicts:
            for conflict in conflicts:
                self.conflict_listbox.insert(tk.END, conflict)
        else:
            self.conflict_listbox.insert(tk.END, "未发现冲突")
    
    def check_synergies(self):
        """检查协同效果"""
        self.synergy_listbox.delete(0, tk.END)
        
        loaded_loras = list(self.loaded_loras.keys())
        synergies = []
        
        for lora1 in loaded_loras:
            for lora2 in loaded_loras:
                if lora1 != lora2:
                    lora1_clean = self.clean_lora_name(lora1)
                    lora2_clean = self.clean_lora_name(lora2)
                    
                    # 检查协同规则
                    if (lora1_clean in self.compatibility_rules["synergies"] and
                        lora2_clean in self.compatibility_rules["synergies"][lora1_clean]):
                        synergies.append(f"{lora1} 与 {lora2} 可能产生协同效果")
        
        if synergies:
            for synergy in synergies:
                self.synergy_listbox.insert(tk.END, synergy)
        else:
            self.synergy_listbox.insert(tk.END, "未发现明显协同效果")
    
    def clean_lora_name(self, name):
        """清理LoRA名称以便匹配规则"""
        # 移除常见后缀和前缀
        cleaned = name.lower()
        cleaned = re.sub(r'[_\-\.]', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned
    
    def show_lora_details(self):
        """显示LoRA详细信息"""
        selection = self.library_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择LoRA")
            return
        
        item = self.library_tree.item(selection[0])
        lora_name = item["values"][0]
        
        if lora_name in self.local_loras:
            lora_info = self.local_loras[lora_name]
            
            # 创建详情对话框
            dialog = tk.Toplevel(self.parent_frame)
            dialog.title(f"LoRA详情 - {lora_name}")
            dialog.geometry("500x400")
            dialog.transient(self.parent_frame)
            
            # 详情内容
            details_text = tk.Text(dialog, wrap="word", font=("Consolas", 10))
            details_text.pack(fill="both", expand=True, padx=10, pady=10)
            
            details = f"名称: {lora_name}\n"
            details += f"分类: {lora_info['category']}\n"
            details += f"路径: {lora_info['path']}\n"
            details += f"大小: {lora_info['size']}\n"
            details += f"建议权重范围: {lora_info['weight_range']}\n\n"
            
            if lora_info['description']:
                details += f"描述: {lora_info['description']}\n\n"
            
            details += "使用建议:\n"
            if lora_info['category'] == "角色人物":
                details += "• 适用于人物特征增强\n• 建议权重: 0.5-1.0\n• 可以与其他角色LoRA组合使用"
            elif lora_info['category'] == "艺术风格":
                details += "• 适用于风格转换\n• 建议权重: 0.3-0.8\n• 注意与现实风格LoRA的冲突"
            elif lora_info['category'] == "场景环境":
                details += "• 适用于环境和背景\n• 建议权重: 0.4-0.9\n• 可以与其他环境LoRA协同"
            elif lora_info['category'] == "技术效果":
                details += "• 适用于画质增强\n• 建议权重: 0.2-0.6\n• 通常可以与任何LoRA组合"
            
            details_text.insert("1.0", details)
            details_text.config(state="disabled")
    
    def delete_lora(self):
        """删除LoRA文件"""
        selection = self.library_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择LoRA")
            return
        
        item = self.library_tree.item(selection[0])
        lora_name = item["values"][0]
        
        if lora_name in self.loaded_loras:
            messagebox.showwarning("警告", "无法删除已加载的LoRA，请先卸载")
            return
        
        result = messagebox.askyesno("确认", f"确定要删除LoRA '{lora_name}' 吗？\n此操作不可恢复！")
        if not result:
            return
        
        try:
            if lora_name in self.local_loras:
                file_path = self.local_loras[lora_name]["path"]
                os.remove(file_path)
                
                del self.local_loras[lora_name]
                self.refresh_library_list()
                
                messagebox.showinfo("成功", f"LoRA '{lora_name}' 已删除")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {e}")
    
    def browse_lora_folder(self):
        """浏览LoRA文件夹"""
        folder_path = filedialog.askdirectory(title="选择LoRA文件夹")
        if folder_path:
            # 将新文件夹添加到扫描目录
            try:
                for file in os.listdir(folder_path):
                    if file.endswith((".safetensors", ".ckpt", ".pt", ".pth")):
                        file_path = os.path.join(folder_path, file)
                        file_size = os.path.getsize(file_path)
                        file_size_mb = file_size / (1024 * 1024)
                        
                        info = self.parse_lora_filename(file)
                        
                        self.local_loras[info["name"]] = {
                            "name": info["name"],
                            "path": file_path,
                            "size": f"{file_size_mb:.1f}MB",
                            "category": info["category"],
                            "weight_range": info["weight_range"],
                            "description": "",
                            "enabled": False,
                            "weight": 0.0
                        }
                
                self.refresh_library_list()
                messagebox.showinfo("成功", "LoRA文件夹已扫描完成")
                
            except Exception as e:
                messagebox.showerror("错误", f"扫描文件夹失败: {e}")
    
    def export_lora_config(self):
        """导出LoRA配置"""
        if not self.loaded_loras:
            messagebox.showwarning("警告", "没有已加载的LoRA可以导出")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="保存LoRA配置",
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if file_path:
            try:
                config = {
                    "version": "1.0",
                    "export_time": str(tk.datetime.now()),
                    "loaded_loras": {}
                }
                
                for lora_name, lora_info in self.loaded_loras.items():
                    config["loaded_loras"][lora_name] = {
                        "path": lora_info["path"],
                        "weight": lora_info["weight"],
                        "enabled": lora_info["enabled"]
                    }
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                
                messagebox.showinfo("成功", f"LoRA配置已导出到: {file_path}")
                
            except Exception as e:
                messagebox.showerror("错误", f"导出配置失败: {e}")
    
    def import_lora_config(self):
        """导入LoRA配置"""
        file_path = filedialog.askopenfilename(
            title="选择LoRA配置文件",
            filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                loaded_count = 0
                for lora_name, lora_info in config["loaded_loras"].items():
                    if os.path.exists(lora_info["path"]):
                        self.loaded_loras[lora_name] = {
                            "path": lora_info["path"],
                            "weight": lora_info["weight"],
                            "enabled": lora_info["enabled"],
                            "info": self.local_loras.get(lora_name, {})
                        }
                        loaded_count += 1
                    else:
                        logger.warning(f"LoRA文件不存在: {lora_info['path']}")
                
                self.refresh_loaded_list()
                
                messagebox.showinfo("成功", f"已导入 {loaded_count} 个LoRA配置")
                
            except Exception as e:
                messagebox.showerror("错误", f"导入配置失败: {e}")
    
    def apply_loaded_config(self):
        """应用已加载的LoRA配置"""
        if not self.loaded_loras:
            messagebox.showwarning("警告", "没有已加载的LoRA")
            return
        
        active_loras = []
        for lora_name, lora_info in self.loaded_loras.items():
            if lora_info["enabled"]:
                active_loras.append({
                    "name": lora_name,
                    "weight": lora_info["weight"],
                    "path": lora_info["path"]
                })
        
        if self.callback:
            self.callback("lora_config_applied", {"loras": active_loras})
        
        messagebox.showinfo("成功", f"已应用 {len(active_loras)} 个活跃LoRA配置")
    
    def get_loaded_loras(self):
        """获取已加载的LoRA"""
        return self.loaded_loras
    
    def get_active_loras(self):
        """获取活跃的LoRA（启用的）"""
        active = []
        for lora_name, lora_info in self.loaded_loras.items():
            if lora_info["enabled"]:
                active.append({
                    "name": lora_name,
                    "weight": lora_info["weight"],
                    "path": lora_info["path"]
                })
        return active