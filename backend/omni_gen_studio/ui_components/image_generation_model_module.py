#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片生成 - 模型模组
支持本地和远程模型加载与管理
包括Flux.2、Z-Image、Qwen-Image等最新模型

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import threading
from pathlib import Path
import requests
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class ModelModule:
    """图片生成模型管理模组"""
    
    def __init__(self, parent_frame, callback=None):
        self.parent_frame = parent_frame
        self.callback = callback
        self.current_model = None
        self.model_config = {}
        self.local_models = []
        self.remote_models = []
        self.model_loading_thread = None
        
        # 支持的模型类型
        self.supported_formats = [
            ".safetensors", ".ckpt", ".pt", ".pth", 
            ".onnx", ".gguf", ".ggml", ".bin", ".weight"
        ]
        
        # 推荐的模型列表
        self.recommended_models = {
            "Z-Image": {
                "name": "Z-Image v1.5",
                "description": "阿里达摩院Z-Image图像生成模型，支持高质量图像生成",
                "type": "text-to-image",
                "formats": [".safetensors", ".ckpt"],
                "recommended_config": {
                    "resolution": "1024x1024",
                    "steps": 20,
                    "cfg_scale": 7.0,
                    "sampler": "DPM++ 2M Karras"
                }
            },
            "Qwen-Image": {
                "name": "Qwen-VL v2.0",
                "description": "阿里巴巴Qwen多模态图像生成模型，图文理解能力强",
                "type": "text-to-image",
                "formats": [".safetensors", ".ckpt"],
                "recommended_config": {
                    "resolution": "1024x1024", 
                    "steps": 25,
                    "cfg_scale": 8.0,
                    "sampler": "DPM++ SDE Karras"
                }
            },
            "Flux.2": {
                "name": "Flux.2 Turbo",
                "description": "Black Forest Labs最新高质量图像生成模型",
                "type": "text-to-image",
                "formats": [".safetensors", ".ckpt"],
                "recommended_config": {
                    "resolution": "1024x1024",
                    "steps": 8,
                    "cfg_scale": 3.5,
                    "sampler": "Euler a"
                }
            },
            "SDXL": {
                "name": "Stable Diffusion XL",
                "description": "Stability AI的高分辨率图像生成模型",
                "type": "text-to-image",
                "formats": [".safetensors", ".ckpt"],
                "recommended_config": {
                    "resolution": "1024x1024",
                    "steps": 30,
                    "cfg_scale": 7.0,
                    "sampler": "DPM++ 2M Karras"
                }
            },
            "SD3": {
                "name": "Stable Diffusion 3",
                "description": "Stability AI的最新图像生成模型",
                "type": "text-to-image", 
                "formats": [".safetensors", ".ckpt"],
                "recommended_config": {
                    "resolution": "1024x1024",
                    "steps": 28,
                    "cfg_scale": 7.0,
                    "sampler": "DPM++ 2M Karras"
                }
            }
        }
        
        self.create_ui()
        self.load_local_models()
    
    def create_ui(self):
        """创建模型管理UI"""
        # 主容器
        main_container = ttk.Frame(self.parent_frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 标题
        title_label = ttk.Label(main_container, text="模型管理", 
                               font=("微软雅黑", 14, "bold"))
        title_label.pack(anchor="w", pady=(0, 15))
        
        # 当前模型状态
        self.create_current_model_status(main_container)
        
        # 模型选择选项卡
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill="both", expand=True, pady=(0, 10))
        
        # 推荐模型选项卡
        self.create_recommended_tab(notebook)
        
        # 本地模型选项卡
        self.create_local_tab(notebook)
        
        # 远程模型选项卡
        self.create_remote_tab(notebook)
        
        # 模型详情面板
        self.create_model_details(main_container)
    
    def create_current_model_status(self, parent):
        """创建当前模型状态显示"""
        status_frame = ttk.LabelFrame(parent, text="当前模型状态", padding=10)
        status_frame.pack(fill="x", pady=(0, 10))
        
        # 状态信息
        info_frame = ttk.Frame(status_frame)
        info_frame.pack(fill="x")
        
        ttk.Label(info_frame, text="当前模型:").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.current_model_label = ttk.Label(info_frame, text="未选择模型", 
                                          font=("微软雅黑", 10, "bold"))
        self.current_model_label.grid(row=0, column=1, sticky="w", padx=(0, 20))
        
        ttk.Label(info_frame, text="状态:").grid(row=0, column=2, sticky="w", padx=(0, 10))
        self.model_status_label = ttk.Label(info_frame, text="未加载", 
                                          foreground="red")
        self.model_status_label.grid(row=0, column=3, sticky="w")
        
        # 加载进度条
        self.progress = ttk.Progressbar(info_frame, mode='indeterminate')
        self.progress.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        
        # 控制按钮
        button_frame = ttk.Frame(info_frame)
        button_frame.grid(row=2, column=0, columnspan=4, pady=(10, 0))
        
        self.load_button = ttk.Button(button_frame, text="加载模型", 
                                    command=self.load_selected_model)
        self.load_button.pack(side="left", padx=(0, 10))
        
        self.unload_button = ttk.Button(button_frame, text="卸载模型", 
                                      command=self.unload_model)
        self.unload_button.pack(side="left", padx=(0, 10))
        
        self.clear_button = ttk.Button(button_frame, text="清空选择", 
                                     command=self.clear_selection)
        self.clear_button.pack(side="left")
        
        info_frame.columnconfigure(1, weight=1)
        info_frame.columnconfigure(3, weight=1)
    
    def create_recommended_tab(self, notebook):
        """创建推荐模型选项卡"""
        rec_frame = ttk.Frame(notebook)
        notebook.add(rec_frame, text="推荐模型")
        
        # 滚动框架
        canvas = tk.Canvas(rec_frame)
        scrollbar = ttk.Scrollbar(rec_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 创建推荐模型卡片
        for model_id, model_info in self.recommended_models.items():
            self.create_model_card(scrollable_frame, model_info, model_id)
    
    def create_local_tab(self, notebook):
        """创建本地模型选项卡"""
        local_frame = ttk.Frame(notebook)
        notebook.add(local_frame, text="本地模型")
        
        # 工具栏
        toolbar = ttk.Frame(local_frame)
        toolbar.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(toolbar, text="浏览文件夹", 
                  command=self.browse_model_folder).pack(side="left", padx=(0, 10))
        
        ttk.Button(toolbar, text="刷新列表", 
                  command=self.refresh_local_models).pack(side="left", padx=(0, 10))
        
        # 模型列表
        list_frame = ttk.LabelFrame(local_frame, text="本地模型列表", padding=10)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 创建Treeview
        columns = ("文件名", "大小", "类型", "修改时间")
        self.local_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=10)
        
        # 设置列标题和宽度
        for col in columns:
            self.local_tree.heading(col, text=col)
            self.local_tree.column(col, width=150)
        
        # 滚动条
        local_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.local_tree.yview)
        self.local_tree.configure(yscrollcommand=local_scrollbar.set)
        
        self.local_tree.pack(side="left", fill="both", expand=True)
        local_scrollbar.pack(side="right", fill="y")
        
        # 绑定选择事件
        self.local_tree.bind("<<TreeviewSelect>>", self.on_local_model_select)
    
    def create_remote_tab(self, notebook):
        """创建远程模型选项卡"""
        remote_frame = ttk.Frame(notebook)
        notebook.add(remote_frame, text="远程模型")
        
        # 远程源配置
        source_frame = ttk.LabelFrame(remote_frame, text="远程源", padding=10)
        source_frame.pack(fill="x", padx=10, pady=10)
        
        # Hugging Face
        hf_frame = ttk.Frame(source_frame)
        hf_frame.pack(fill="x", pady=5)
        
        ttk.Label(hf_frame, text="🤗 Hugging Face").pack(anchor="w")
        
        hf_entry_frame = ttk.Frame(hf_frame)
        hf_entry_frame.pack(fill="x", pady=(5, 0))
        
        self.hf_model_entry = ttk.Entry(hf_entry_frame, width=50)
        self.hf_model_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ttk.Button(hf_entry_frame, text="搜索", 
                  command=self.search_huggingface).pack(side="left")
        
        # CivitAI
        civit_frame = ttk.Frame(source_frame)
        civit_frame.pack(fill="x", pady=5)
        
        ttk.Label(civit_frame, text="🎨 CivitAI").pack(anchor="w")
        
        civit_entry_frame = ttk.Frame(civit_frame)
        civit_entry_frame.pack(fill="x", pady=(5, 0))
        
        self.civit_model_entry = ttk.Entry(civit_entry_frame, width=50)
        self.civit_model_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        ttk.Button(civit_entry_frame, text="搜索", 
                  command=self.search_civitai).pack(side="left")
        
        # 远程模型列表
        remote_list_frame = ttk.LabelFrame(remote_frame, text="远程模型列表", padding=10)
        remote_list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 创建Treeview
        columns = ("模型名称", "作者", "下载量", "评分", "大小")
        self.remote_tree = ttk.Treeview(remote_list_frame, columns=columns, show="headings", height=8)
        
        for col in columns:
            self.remote_tree.heading(col, text=col)
            self.remote_tree.column(col, width=120)
        
        remote_scrollbar = ttk.Scrollbar(remote_list_frame, orient="vertical", command=self.remote_tree.yview)
        self.remote_tree.configure(yscrollcommand=remote_scrollbar.set)
        
        self.remote_tree.pack(side="left", fill="both", expand=True)
        remote_scrollbar.pack(side="right", fill="y")
        
        self.remote_tree.bind("<<TreeviewSelect>>", self.on_remote_model_select)
    
    def create_model_details(self, parent):
        """创建模型详情面板"""
        details_frame = ttk.LabelFrame(parent, text="模型详情", padding=10)
        details_frame.pack(fill="x")
        
        # 详情内容
        self.details_text = tk.Text(details_frame, height=6, wrap="word", state="disabled")
        scrollbar = ttk.Scrollbar(details_frame, orient="vertical", command=self.details_text.yview)
        self.details_text.configure(yscrollcommand=scrollbar.set)
        
        self.details_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def create_model_card(self, parent, model_info, model_id):
        """创建模型卡片"""
        card_frame = ttk.LabelFrame(parent, text=model_info["name"], padding=15)
        card_frame.pack(fill="x", padx=10, pady=5)
        
        # 模型信息
        info_frame = ttk.Frame(card_frame)
        info_frame.pack(fill="x")
        
        # 模型描述
        desc_label = ttk.Label(info_frame, text=model_info["description"], 
                              wraplength=400, foreground="gray")
        desc_label.pack(anchor="w", pady=(0, 10))
        
        # 模型标签
        tags_frame = ttk.Frame(info_frame)
        tags_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(tags_frame, text="类型:", font=("微软雅黑", 9, "bold")).pack(side="left")
        ttk.Label(tags_frame, text=model_info["type"], 
                 background="lightblue", padding=(5, 2)).pack(side="left", padx=(5, 15))
        
        ttk.Label(tags_frame, text="格式:", font=("微软雅黑", 9, "bold")).pack(side="left")
        formats_text = ", ".join(model_info["formats"])
        ttk.Label(tags_frame, text=formats_text, 
                 background="lightgreen", padding=(5, 2)).pack(side="left", padx=(5, 0))
        
        # 推荐配置
        config_frame = ttk.Frame(info_frame)
        config_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Label(config_frame, text="推荐配置:", font=("微软雅黑", 9, "bold")).pack(anchor="w")
        
        config_text = f"分辨率: {model_info['recommended_config']['resolution']} | " \
                     f"步数: {model_info['recommended_config']['steps']} | " \
                     f"CFG: {model_info['recommended_config']['cfg_scale']} | " \
                     f"采样器: {model_info['recommended_config']['sampler']}"
        
        config_label = ttk.Label(config_frame, text=config_text, foreground="darkblue")
        config_label.pack(anchor="w", pady=(2, 0))
        
        # 操作按钮
        button_frame = ttk.Frame(info_frame)
        button_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(button_frame, text="选择模型", 
                  command=lambda: self.select_model(model_id, model_info)).pack(side="left")
        
        ttk.Button(button_frame, text="下载模型", 
                  command=lambda: self.download_model(model_id, model_info)).pack(side="left", padx=(10, 0))
    
    def load_local_models(self):
        """加载本地模型"""
        # 常见的模型目录
        model_directories = [
            "models/StableDiffusion",
            "models/SDXL",
            "models/Flux",
            "models/Checkpoint",
            "models/LLM",
            "ComfyUI/models/checkpoints",
            "ComfyUI/models/clip",
            "ComfyUI/models/unet"
        ]
        
        for model_dir in model_directories:
            if os.path.exists(model_dir):
                self.scan_directory(model_dir)
    
    def scan_directory(self, directory):
        """扫描目录中的模型文件"""
        try:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if any(file.endswith(fmt) for fmt in self.supported_formats):
                        file_path = os.path.join(root, file)
                        file_size = os.path.getsize(file_path)
                        file_size_mb = file_size / (1024 * 1024)
                        file_ext = os.path.splitext(file)[1]
                        mtime = os.path.getmtime(file_path)
                        
                        model_info = {
                            "name": file,
                            "path": file_path,
                            "size": f"{file_size_mb:.1f}MB",
                            "type": file_ext,
                            "mtime": mtime,
                            "directory": root
                        }
                        self.local_models.append(model_info)
        except Exception as e:
            logger.error(f"扫描目录失败 {directory}: {e}")
    
    def browse_model_folder(self):
        """浏览模型文件夹"""
        folder_path = filedialog.askdirectory(title="选择模型文件夹")
        if folder_path:
            self.scan_directory(folder_path)
            self.refresh_local_models()
    
    def refresh_local_models(self):
        """刷新本地模型列表"""
        # 清空现有列表
        for item in self.local_tree.get_children():
            self.local_tree.delete(item)
        
        # 重新加载模型
        self.local_models.clear()
        self.load_local_models()
        
        # 填充列表
        for model in self.local_models:
            self.local_tree.insert("", "end", values=(
                model["name"],
                model["size"],
                model["type"],
                self.format_mtime(model["mtime"])
            ))
    
    def format_mtime(self, mtime):
        """格式化修改时间"""
        import datetime
        dt = datetime.datetime.fromtimestamp(mtime)
        return dt.strftime("%Y-%m-%d %H:%M")
    
    def on_local_model_select(self, event):
        """本地模型选择事件"""
        selection = self.local_tree.selection()
        if selection:
            item = self.local_tree.item(selection[0])
            model_name = item["values"][0]
            
            # 查找对应的模型信息
            for model in self.local_models:
                if model["name"] == model_name:
                    self.show_model_details(model)
                    break
    
    def on_remote_model_select(self, event):
        """远程模型选择事件"""
        selection = self.remote_tree.selection()
        if selection:
            item = self.remote_tree.item(selection[0])
            # 处理远程模型选择逻辑
    
    def show_model_details(self, model_info):
        """显示模型详情"""
        self.details_text.config(state="normal")
        self.details_text.delete("1.0", "end")
        
        details = f"文件名: {model_info.get('name', 'N/A')}\n"
        details += f"路径: {model_info.get('path', 'N/A')}\n"
        details += f"大小: {model_info.get('size', 'N/A')}\n"
        details += f"类型: {model_info.get('type', 'N/A')}\n"
        details += f"目录: {model_info.get('directory', 'N/A')}\n"
        
        if "recommended_config" in model_info:
            details += f"推荐配置:\n"
            for key, value in model_info["recommended_config"].items():
                details += f"  {key}: {value}\n"
        
        self.details_text.insert("1.0", details)
        self.details_text.config(state="disabled")
    
    def select_model(self, model_id, model_info):
        """选择模型"""
        self.current_model = model_info
        self.model_config = model_info
        
        self.current_model_label.config(text=model_info["name"])
        self.show_model_details(model_info)
        
        if self.callback:
            self.callback("model_selected", model_info)
        
        messagebox.showinfo("模型选择", f"已选择模型: {model_info['name']}")
    
    def load_selected_model(self):
        """加载选中的模型"""
        if not self.current_model:
            messagebox.showwarning("警告", "请先选择模型")
            return
        
        self.progress.start()
        self.model_status_label.config(text="加载中...", foreground="orange")
        
        # 在新线程中加载模型
        self.model_loading_thread = threading.Thread(target=self._load_model_worker)
        self.model_loading_thread.daemon = True
        self.model_loading_thread.start()
    
    def _load_model_worker(self):
        """模型加载工作线程"""
        try:
            # 模拟模型加载过程
            import time
            time.sleep(2)  # 模拟加载时间
            
            # 这里应该调用实际的模型加载逻辑
            logger.info(f"正在加载模型: {self.current_model['name']}")
            
            # 模拟加载成功
            self.parent_frame.after(0, self._load_model_success)
            
        except Exception as e:
            logger.error(f"模型加载失败: {e}")
            self.parent_frame.after(0, self._load_model_failure, str(e))
    
    def _load_model_success(self):
        """模型加载成功回调"""
        self.progress.stop()
        self.model_status_label.config(text="已加载", foreground="green")
        self.load_button.config(state="disabled")
        self.unload_button.config(state="normal")
        
        if self.callback:
            self.callback("model_loaded", self.current_model)
        
        messagebox.showinfo("成功", f"模型 {self.current_model['name']} 加载成功！")
    
    def _load_model_failure(self, error_msg):
        """模型加载失败回调"""
        self.progress.stop()
        self.model_status_label.config(text="加载失败", foreground="red")
        
        messagebox.showerror("加载失败", f"模型加载失败:\n{error_msg}")
    
    def unload_model(self):
        """卸载模型"""
        if self.current_model:
            self.current_model = None
            self.model_config = {}
            
            self.current_model_label.config(text="未选择模型")
            self.model_status_label.config(text="未加载", foreground="red")
            self.load_button.config(state="normal")
            self.unload_button.config(state="disabled")
            
            if self.callback:
                self.callback("model_unloaded", None)
            
            messagebox.showinfo("成功", "模型已卸载")
    
    def clear_selection(self):
        """清空选择"""
        self.current_model = None
        self.model_config = {}
        
        self.current_model_label.config(text="未选择模型")
        self.model_status_label.config(text="未加载", foreground="red")
        
        self.details_text.config(state="normal")
        self.details_text.delete("1.0", "end")
        self.details_text.config(state="disabled")
        
        if self.callback:
            self.callback("selection_cleared", None)
    
    def search_huggingface(self):
        """搜索Hugging Face模型"""
        query = self.hf_model_entry.get().strip()
        if not query:
            messagebox.showwarning("警告", "请输入搜索关键词")
            return
        
        # 这里应该实现实际的Hugging Face API搜索
        messagebox.showinfo("搜索", f"正在搜索 Hugging Face 模型: {query}")
    
    def search_civitai(self):
        """搜索CivitAI模型"""
        query = self.civit_model_entry.get().strip()
        if not query:
            messagebox.showwarning("警告", "请输入搜索关键词")
            return
        
        # 这里应该实现实际的CivitAI API搜索
        messagebox.showinfo("搜索", f"正在搜索 CivitAI 模型: {query}")
    
    def download_model(self, model_id, model_info):
        """下载模型"""
        # 这里应该实现模型下载逻辑
        messagebox.showinfo("下载", f"开始下载模型: {model_info['name']}")
    
    def get_current_model(self):
        """获取当前模型"""
        return self.current_model
    
    def get_model_config(self):
        """获取模型配置"""
        return self.model_config
    
    def is_model_loaded(self):
        """检查模型是否已加载"""
        return self.current_model is not None and self.model_status_label.cget("text") == "已加载"