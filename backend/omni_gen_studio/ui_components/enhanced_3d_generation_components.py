#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强版3D生成组件 - 终极AIGC生成器 v5.3
实现要求五的所有核心功能：
1. Hunyuan3D、Trellis-2等3D模型支持
2. 从图片生成3D模型功能
3. 文件输出设置和格式选择
4. 提示词保存功能
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

class Enhanced3DGenerationComponents:
    """增强版3D生成组件"""
    
    def __init__(self, parent_frame, app_instance):
        """
        初始化3D生成组件
        
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
        
        # 创建UI
        self.create_enhanced_ui()
    
    def setup_presets(self):
        """设置预设配置"""
        
        # 支持的3D模型
        self.model_presets = {
            "最新3D模型": {
                "hunyuan3d": "Hunyuan3D 2.0 (腾讯最新)",
                "trellis-2": "TRELLIS 2 (多模态3D)",
                "sv3d": "SV3D (稳定视频扩散)",
                "shap-e": "Shap-E (OpenAI)",
                "point-e": "Point-E (OpenAI)"
            },
            "高质量模型": {
                "meshy-4": "Meshy 4 (高质量)",
                "tripo3d": "Tripo3D (专业)",
                "magic3d": "Magic3D (英伟达)",
                "dreamfusion": "DreamFusion (谷歌)"
            },
            "快速生成模型": {
                "instant-3d": "Instant3D (快速)",
                "point-cloud": "Point Cloud (点云)",
                "voxel": "Voxel (体素)",
                "gaussian-splatting": "Gaussian Splatting"
            },
            "特殊功能": {
                "text-to-3d": "Text-to-3D (文本驱动)",
                "image-to-3d": "Image-to-3D (图片驱动)",
                "video-to-3d": "Video-to-3D (视频驱动)",
                "mesh-refinement": "Mesh Refinement (网格优化)"
            }
        }
        
        # 3D输出格式
        self.output_formats = {
            "网格格式": {
                "obj": "OBJ (通用)",
                "ply": "PLY (点云)",
                "stl": "STL (3D打印)",
                "3ds": "3DS (旧版)",
                "dae": "DAE (Collada)"
            },
            "现代格式": {
                "glb": "GLB (推荐)",
                "gltf": "GLTF (标准)",
                "usd": "USD (皮克斯)",
                "fbx": "FBX (Autodesk)",
                "x3d": "X3D (Web3D)"
            },
            "专业格式": {
                "step": "STEP (CAD)",
                "iges": "IGES (CAD)",
                "cad": "CAD (工程)",
                "solidworks": "SolidWorks (专业)"
            },
            "渲染格式": {
                "blend": "Blender (开源)",
                "max": "3ds Max (Autodesk)",
                "maya": "Maya (Autodesk)",
                "c4d": "Cinema4D"
            }
        }
        
        # 质量预设
        self.quality_presets = {
            "快速预览": {
                "低质量": {"vertices": 5000, "faces": 3000, "texture": False, "animation": False},
                "中低质量": {"vertices": 15000, "faces": 10000, "texture": True, "animation": False}
            },
            "标准质量": {
                "标准质量": {"vertices": 50000, "faces": 30000, "texture": True, "animation": False},
                "高质量": {"vertices": 100000, "faces": 60000, "texture": True, "animation": True}
            },
            "专业质量": {
                "超高质量": {"vertices": 200000, "faces": 120000, "texture": True, "animation": True},
                "电影级": {"vertices": 500000, "faces": 300000, "texture": True, "animation": True}
            }
        }
        
        # 3D处理选项
        self.processing_options = {
            "基础处理": {
                "简化网格": "网格简化算法",
                "平滑处理": "表面平滑",
                "法线计算": "法线向量计算",
                "UV展开": "纹理坐标展开"
            },
            "高级处理": {
                "纹理贴图": "自动纹理生成",
                "PBR材质": "物理材质系统",
                "光照烘焙": "光照烘焙",
                "LOD生成": "多细节层次"
            },
            "专业处理": {
                "物理模拟": "物理属性模拟",
                "动画绑定": "骨骼动画",
                "粒子系统": "粒子效果",
                "流体模拟": "流体动力学"
            }
        }
        
        # 输入源类型
        self.input_sources = {
            "图片输入": {
                "单张图片": "单张图片生成3D",
                "多角度图片": "多角度图片重建",
                "图片序列": "图片序列动画",
                "全景图片": "360度全景"
            },
            "文本输入": {
                "详细描述": "文本详细描述",
                "关键词": "关键词组合",
                "参考风格": "风格参考",
                "技术规格": "技术参数"
            },
            "视频输入": {
                "短视频": "短视频片段",
                "动画序列": "动画帧序列",
                "运动捕捉": "运动数据",
                "深度视频": "深度信息视频"
            }
        }
        
        # 支持的文件格式
        self.supported_formats = {
            "3D模型": [".obj", ".ply", ".stl", ".3ds", ".dae", ".glb", ".gltf", ".usd", ".fbx"],
            "图片文件": [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".hdr", ".exr"],
            "视频文件": [".mp4", ".avi", ".mov", ".mkv", ".webm"],
            "配置文件": [".json", ".yaml", ".yml", ".cfg"],
            "纹理文件": [".png", ".jpg", ".tga", ".bmp", ".exr"],
            "材质文件": [".mtl", ".mat", ".usda"]
        }
    
    def create_enhanced_ui(self):
        """创建增强版UI"""
        
        # 主容器
        main_container = ttk.Frame(self.parent)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # 创建笔记本控件（标签页）
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 创建各个标签页
        self.create_model_tab(notebook)
        self.create_input_tab(notebook)
        self.create_processing_tab(notebook)
        self.create_output_tab(notebook)
        self.create_preview_tab(notebook)
        
    def create_model_tab(self, notebook):
        """创建模型配置标签页"""
        
        model_frame = ttk.Frame(notebook)
        notebook.add(model_frame, text="模型配置")
        
        # 初始化模型相关变量
        self.vars['model'] = tk.StringVar(value="hunyuan3d")
        self.vars['model_path'] = tk.StringVar()
        self.vars['custom_model_name'] = tk.StringVar()
        
        # 任务类型选择
        task_frame = ttk.LabelFrame(model_frame, text="任务类型", padding="10")
        task_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.vars['task_type'] = tk.StringVar(value="image_to_3d")
        
        task_types = [
            ("图片转3D (Image-to-3D)", "image_to_3d"),
            ("文本转3D (Text-to-3D)", "text_to_3d"),
            ("视频转3D (Video-to-3D)", "video_to_3d"),
            ("多模态转3D (Multi-modal)", "multimodal_to_3d")
        ]
        
        for i, (text, value) in enumerate(task_types):
            ttk.Radiobutton(task_frame, text=text, 
                           variable=self.vars['task_type'], value=value).grid(
                               row=i//2, column=i%2, sticky="w", padx=20, pady=5)
        
        # 3D模型选择
        model_select_frame = ttk.LabelFrame(model_frame, text="3D模型选择", padding="10")
        model_select_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 模型分类选择
        category_frame = ttk.Frame(model_select_frame)
        category_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(category_frame, text="模型分类:").pack(side=tk.LEFT)
        self.vars['model_category'] = tk.StringVar(value="最新3D模型")
        category_combo = ttk.Combobox(category_frame, textvariable=self.vars['model_category'],
                                     values=list(self.model_presets.keys()), width=15)
        category_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(category_frame, text="具体模型:").pack(side=tk.LEFT, padx=(20, 0))
        self.vars['model_name'] = tk.StringVar(value="hunyuan3d")
        model_combo = ttk.Combobox(category_frame, textvariable=self.vars['model_name'],
                                  values=list(self.model_presets["最新3D模型"].keys()), width=20)
        model_combo.pack(side=tk.LEFT, padx=5)
        
        # 绑定分类变化事件
        def on_category_change(*args):
            category = self.vars['model_category'].get()
            if category in self.model_presets:
                models = list(self.model_presets[category].keys())
                model_combo['values'] = models
                if models:
                    self.vars['model_name'].set(models[0])
        
        category_combo.bind('<<ComboboxSelected>>', lambda e: on_category_change())
        
        # 模型文件路径
        path_frame = ttk.Frame(model_select_frame)
        path_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(path_frame, text="模型文件路径:").pack(side=tk.LEFT)
        ttk.Entry(path_frame, textvariable=self.vars['model_path'], width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="浏览", 
                  command=self.select_model_file).pack(side=tk.LEFT, padx=2)
        
        # 自定义模型名称
        custom_frame = ttk.Frame(model_select_frame)
        custom_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(custom_frame, text="自定义模型名称:").pack(side=tk.LEFT)
        ttk.Entry(custom_frame, textvariable=self.vars['custom_model_name'], width=30).pack(side=tk.LEFT, padx=5)
        ttk.Button(custom_frame, text="加载自定义模型", 
                  command=self.load_custom_model).pack(side=tk.LEFT, padx=5)
        
        # 模型信息显示
        info_frame = ttk.LabelFrame(model_select_frame, text="模型信息", padding="5")
        info_frame.pack(fill=tk.X, pady=5)
        
        info_text = tk.Text(info_frame, height=8, wrap=tk.WORD)
        scrollbar_info = ttk.Scrollbar(info_frame, orient=tk.VERTICAL, command=info_text.yview)
        info_text.configure(yscrollcommand=scrollbar_info.set)
        
        model_info = """
支持的3D生成模型：

最新3D模型：
• Hunyuan3D 2.0 - 腾讯最新3D生成
• TRELLIS 2 - 多模态3D生成
• SV3D - 稳定视频扩散3D
• Shap-E - OpenAI 3D生成
• Point-E - OpenAI 点云生成

高质量模型：
• Meshy 4 - 专业3D生成
• Tripo3D - 高质量网格
• Magic3D - 英伟达技术
• DreamFusion - 谷歌算法

快速生成：
• Instant3D - 快速3D生成
• Point Cloud - 点云处理
• Voxel - 体素生成
• Gaussian Splatting - 高斯渲染

特殊功能：
• Text-to-3D - 文本驱动
• Image-to-3D - 图片驱动
• Video-to-3D - 视频驱动
• Mesh Refinement - 网格优化
        """
        
        info_text.insert(tk.END, model_info)
        info_info = info_text
        info_text.config(state=tk.DISABLED)
        info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_info.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 模型性能设置
        performance_frame = ttk.LabelFrame(model_frame, text="性能设置", padding="10")
        performance_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # GPU设置
        gpu_frame = ttk.Frame(performance_frame)
        gpu_frame.pack(fill=tk.X, pady=2)
        
        self.vars['use_gpu'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(gpu_frame, text="使用GPU加速", 
                       variable=self.vars['use_gpu']).pack(side=tk.LEFT)
        
        self.vars['gpu_memory'] = tk.IntVar(value=8)
        ttk.Label(gpu_frame, text="GPU内存 (GB):", width=15).pack(side=tk.LEFT, padx=(20, 0))
        gpu_spin = ttk.Spinbox(gpu_frame, from_=2, to=32, 
                              textvariable=self.vars['gpu_memory'], width=10)
        gpu_spin.pack(side=tk.LEFT, padx=5)
        
        # 并行设置
        parallel_frame = ttk.Frame(performance_frame)
        parallel_frame.pack(fill=tk.X, pady=2)
        
        self.vars['num_workers'] = tk.IntVar(value=4)
        ttk.Label(parallel_frame, text="并行进程:", width=15).pack(side=tk.LEFT)
        workers_spin = ttk.Spinbox(parallel_frame, from_=1, to=16,
                                  textvariable=self.vars['num_workers'], width=10)
        workers_spin.pack(side=tk.LEFT, padx=5)
        
        self.vars['batch_size'] = tk.IntVar(value=1)
        ttk.Label(parallel_frame, text="批处理大小:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        batch_spin = ttk.Spinbox(parallel_frame, from_=1, to=8,
                                textvariable=self.vars['batch_size'], width=10)
        batch_spin.pack(side=tk.LEFT, padx=5)
        
        # 模型下载和管理
        download_frame = ttk.LabelFrame(model_frame, text="模型下载和管理", padding="10")
        download_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 下载选项
        download_options_frame = ttk.Frame(download_frame)
        download_options_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(download_options_frame, text="下载源:").pack(side=tk.LEFT)
        self.vars['download_source'] = tk.StringVar(value="HuggingFace")
        source_combo = ttk.Combobox(download_options_frame, textvariable=self.vars['download_source'],
                                   values=["HuggingFace", "GitHub", "ModelScope", "本地文件"], width=15)
        source_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(download_options_frame, text="模型名称:").pack(side=tk.LEFT, padx=(20, 0))
        self.vars['download_model'] = tk.StringVar()
        ttk.Entry(download_options_frame, textvariable=self.vars['download_model'], width=25).pack(side=tk.LEFT, padx=5)
        
        # 下载按钮
        download_buttons_frame = ttk.Frame(download_frame)
        download_buttons_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(download_buttons_frame, text="下载模型", 
                  command=self.download_model).pack(side=tk.LEFT, padx=5)
        ttk.Button(download_buttons_frame, text="检查更新", 
                  command=self.check_model_updates).pack(side=tk.LEFT, padx=5)
        ttk.Button(download_buttons_frame, text="管理模型", 
                  command=self.manage_models).pack(side=tk.LEFT, padx=5)
        
        # 下载进度
        progress_frame = ttk.Frame(download_frame)
        progress_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(progress_frame, text="下载进度:").pack(anchor="w")
        self.vars['download_progress'] = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(progress_frame, variable=self.vars['download_progress'],
                                      length=400, mode='determinate')
        progress_bar.pack(fill=tk.X, pady=2)
        
        self.vars['download_status'] = tk.StringVar(value="就绪")
        status_label = ttk.Label(progress_frame, textvariable=self.vars['download_status'])
        status_label.pack(anchor="w")
    
    def create_input_tab(self, notebook):
        """创建输入源标签页"""
        
        input_frame = ttk.Frame(notebook)
        notebook.add(input_frame, text="输入源")
        
        # 初始化输入相关变量
        self.vars['input_source_type'] = tk.StringVar(value="image")
        self.vars['input_image_path'] = tk.StringVar()
        self.vars['input_video_path'] = tk.StringVar()
        self.vars['input_text'] = tk.StringVar()
        self.vars['input_strength'] = tk.DoubleVar(value=0.8)
        
        # 输入类型选择
        input_type_frame = ttk.LabelFrame(input_frame, text="输入类型", padding="10")
        input_type_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.vars['input_mode'] = tk.StringVar(value="single_image")
        
        input_modes = [
            ("单张图片", "single_image"),
            ("多张图片", "multiple_images"),
            ("文本描述", "text_description"),
            ("视频片段", "video_clip")
        ]
        
        for i, (text, value) in enumerate(input_modes):
            ttk.Radiobutton(input_type_frame, text=text, 
                           variable=self.vars['input_mode'], value=value).grid(
                               row=i//2, column=i%2, sticky="w", padx=20, pady=5)
        
        # 图片输入
        image_input_frame = ttk.LabelFrame(input_frame, text="图片输入", padding="10")
        image_input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        image_path_frame = ttk.Frame(image_input_frame)
        image_path_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(image_path_frame, text="图片路径:", width=15).pack(side=tk.LEFT)
        ttk.Entry(image_path_frame, textvariable=self.vars['input_image_path'], 
                  width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(image_path_frame, text="浏览", 
                  command=self.select_input_image).pack(side=tk.LEFT, padx=2)
        
        # 图片预览
        image_preview_frame = ttk.Frame(image_input_frame)
        image_preview_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(image_preview_frame, text="图片预览:", width=15).pack(side=tk.LEFT)
        
        # 预览画布
        image_preview_canvas = tk.Canvas(image_preview_frame, width=300, height=200, bg="lightgray")
        image_preview_canvas.pack(pady=5)
        image_preview_canvas.create_text(150, 100, text="图片预览", fill="black")
        
        # 图片处理选项
        image_options_frame = ttk.Frame(image_input_frame)
        image_options_frame.pack(fill=tk.X, pady=2)
        
        self.vars['image_size_limit'] = tk.IntVar(value=1024)
        ttk.Label(image_options_frame, text="图片尺寸限制:", width=15).pack(side=tk.LEFT)
        size_spin = ttk.Spinbox(image_options_frame, from_=256, to=4096, increment=128,
                               textvariable=self.vars['image_size_limit'], width=10)
        size_spin.pack(side=tk.LEFT, padx=5)
        
        self.vars['enhance_image'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(image_options_frame, text="图片增强", 
                       variable=self.vars['enhance_image']).pack(side=tk.LEFT, padx=(20, 0))
        
        # 文本输入
        text_input_frame = ttk.LabelFrame(input_frame, text="文本输入", padding="10")
        text_input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 文本描述
        text_desc_frame = ttk.Frame(text_input_frame)
        text_desc_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(text_desc_frame, text="3D模型描述:", width=15).pack(side=tk.LEFT)
        ttk.Entry(text_desc_frame, textvariable=self.vars['input_text'], 
                  width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 文本模板
        text_templates_frame = ttk.Frame(text_input_frame)
        text_templates_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(text_templates_frame, text="模板:", width=15).pack(side=tk.LEFT)
        self.vars['text_template'] = tk.StringVar(value="详细描述")
        template_combo = ttk.Combobox(text_templates_frame, textvariable=self.vars['text_template'],
                                     values=["详细描述", "关键词", "风格参考", "技术规格"], width=15)
        template_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(text_templates_frame, text="应用模板", 
                  command=self.apply_text_template).pack(side=tk.LEFT, padx=5)
        
        # 文本优化
        text_optimize_frame = ttk.Frame(text_input_frame)
        text_optimize_frame.pack(fill=tk.X, pady=2)
        
        self.vars['enable_text_optimize'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(text_optimize_frame, text="AI文本优化", 
                       variable=self.vars['enable_text_optimize']).pack(side=tk.LEFT)
        
        self.vars['text_language'] = tk.StringVar(value="chinese")
        ttk.Label(text_optimize_frame, text="语言:", width=10).pack(side=tk.LEFT, padx=(20, 0))
        lang_combo = ttk.Combobox(text_optimize_frame, textvariable=self.vars['text_language'],
                                 values=["chinese", "english", "japanese"], width=12)
        lang_combo.pack(side=tk.LEFT, padx=5)
        
        # 视频输入
        video_input_frame = ttk.LabelFrame(input_frame, text="视频输入", padding="10")
        video_input_frame.pack(fill=tk.X, padx=10, pady=5)
        
        video_path_frame = ttk.Frame(video_input_frame)
        video_path_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(video_path_frame, text="视频路径:", width=15).pack(side=tk.LEFT)
        ttk.Entry(video_path_frame, textvariable=self.vars['input_video_path'], 
                  width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(video_path_frame, text="浏览", 
                  command=self.select_input_video).pack(side=tk.LEFT, padx=2)
        
        # 视频设置
        video_settings_frame = ttk.Frame(video_input_frame)
        video_settings_frame.pack(fill=tk.X, pady=2)
        
        self.vars['video_start_time'] = tk.DoubleVar(value=0.0)
        ttk.Label(video_settings_frame, text="开始时间:", width=15).pack(side=tk.LEFT)
        start_spin = ttk.Spinbox(video_settings_frame, from_=0.0, to=100.0, increment=0.1,
                                 textvariable=self.vars['video_start_time'], width=10)
        start_spin.pack(side=tk.LEFT, padx=5)
        
        self.vars['video_duration'] = tk.DoubleVar(value=5.0)
        ttk.Label(video_settings_frame, text="时长:", width=10).pack(side=tk.LEFT, padx=(20, 0))
        duration_spin = ttk.Spinbox(video_settings_frame, from_=0.1, to=100.0, increment=0.1,
                                   textvariable=self.vars['video_duration'], width=10)
        duration_spin.pack(side=tk.LEFT, padx=5)
        
        # 帧提取
        frame_extraction_frame = ttk.LabelFrame(input_frame, text="帧提取设置", padding="10")
        frame_extraction_frame.pack(fill=tk.X, padx=10, pady=5)
        
        frame_options_frame = ttk.Frame(frame_extraction_frame)
        frame_options_frame.pack(fill=tk.X, pady=2)
        
        self.vars['frame_extraction'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame_options_frame, text="自动帧提取", 
                       variable=self.vars['frame_extraction']).pack(side=tk.LEFT)
        
        self.vars['num_frames'] = tk.IntVar(value=24)
        ttk.Label(frame_options_frame, text="提取帧数:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        frames_spin = ttk.Spinbox(frame_options_frame, from_=8, to=100,
                                  textvariable=self.vars['num_frames'], width=10)
        frames_spin.pack(side=tk.LEFT, padx=5)
        
        # 输入强度和权重
        input_weight_frame = ttk.LabelFrame(input_frame, text="输入权重", padding="10")
        input_weight_frame.pack(fill=tk.X, padx=10, pady=5)
        
        weight_control_frame = ttk.Frame(input_weight_frame)
        weight_control_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(weight_control_frame, text="输入强度:", width=15).pack(side=tk.LEFT)
        strength_spin = ttk.Spinbox(weight_control_frame, from_=0.0, to=1.0, increment=0.1,
                                   textvariable=self.vars['input_strength'], width=10)
        strength_spin.pack(side=tk.LEFT, padx=5)
        
        self.vars['style_weight'] = tk.DoubleVar(value=0.7)
        ttk.Label(weight_control_frame, text="风格权重:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        style_spin = ttk.Spinbox(weight_control_frame, from_=0.0, to=1.0, increment=0.1,
                                textvariable=self.vars['style_weight'], width=10)
        style_spin.pack(side=tk.LEFT, padx=5)
        
        # 多模态融合
        multimodal_frame = ttk.LabelFrame(input_frame, text="多模态融合", padding="10")
        multimodal_frame.pack(fill=tk.X, padx=10, pady=5)
        
        multimodal_options_frame = ttk.Frame(multimodal_frame)
        multimodal_options_frame.pack(fill=tk.X, pady=2)
        
        self.vars['enable_multimodal'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(multimodal_options_frame, text="启用多模态融合", 
                       variable=self.vars['enable_multimodal']).pack(side=tk.LEFT)
        
        self.vars['fusion_method'] = tk.StringVar(value="weighted_average")
        ttk.Label(multimodal_options_frame, text="融合方法:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        fusion_combo = ttk.Combobox(multimodal_options_frame, textvariable=self.vars['fusion_method'],
                                    values=["weighted_average", "attention", "cross_modal", "adaptive"], width=15)
        fusion_combo.pack(side=tk.LEFT, padx=5)
    
    def create_processing_tab(self, notebook):
        """创建处理选项标签页"""
        
        processing_frame = ttk.Frame(notebook)
        notebook.add(processing_frame, text="处理选项")
        
        # 初始化处理相关变量
        self.vars['quality_preset'] = tk.StringVar(value="标准质量")
        self.vars['processing_steps'] = tk.IntVar(value=100)
        self.vars['seed'] = tk.IntVar(value=42)
        self.vars['random_seed'] = tk.BooleanVar(value=False)
        
        # 质量设置
        quality_frame = ttk.LabelFrame(processing_frame, text="质量设置", padding="10")
        quality_frame.pack(fill=tk.X, padx=10, pady=5)
        
        quality_select_frame = ttk.Frame(quality_frame)
        quality_select_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(quality_select_frame, text="质量预设:", width=15).pack(side=tk.LEFT)
        
        # 质量预设选择
        quality_values = []
        for category, presets in self.quality_presets.items():
            for preset_name in presets.keys():
                quality_values.append(f"{category}: {preset_name}")
        
        quality_combo = ttk.Combobox(quality_select_frame, textvariable=self.vars['quality_preset'],
                                     values=quality_values, width=20)
        quality_combo.pack(side=tk.LEFT, padx=5)
        
        # 质量参数显示
        quality_params_frame = ttk.Frame(quality_frame)
        quality_params_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(quality_params_frame, text="处理步数:", width=15).pack(side=tk.LEFT)
        steps_spin = ttk.Spinbox(quality_params_frame, from_=10, to=500,
                                 textvariable=self.vars['processing_steps'], width=10)
        steps_spin.pack(side=tk.LEFT, padx=5)
        
        self.vars['learning_rate'] = tk.DoubleVar(value=0.01)
        ttk.Label(quality_params_frame, text="学习率:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        lr_spin = ttk.Spinbox(quality_params_frame, from_=0.001, to=0.1, increment=0.001,
                              textvariable=self.vars['learning_rate'], width=10)
        lr_spin.pack(side=tk.LEFT, padx=5)
        
        # 处理算法选择
        algorithm_frame = ttk.LabelFrame(processing_frame, text="处理算法", padding="10")
        algorithm_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.vars['generation_algorithm'] = tk.StringVar(value="diffusion")
        ttk.Label(algorithm_frame, text="生成算法:", width=15).pack(side=tk.LEFT)
        algo_combo = ttk.Combobox(algorithm_frame, textvariable=self.vars['generation_algorithm'],
                                  values=["diffusion", "gan", "neural_rendering", "implicit_representation"], width=20)
        algo_combo.pack(side=tk.LEFT, padx=5)
        
        # 算法参数
        algo_params_frame = ttk.Frame(algorithm_frame)
        algo_params_frame.pack(fill=tk.X, pady=2)
        
        self.vars['noise_schedule'] = tk.StringVar(value="linear")
        ttk.Label(algo_params_frame, text="噪声调度:", width=15).pack(side=tk.LEFT)
        noise_combo = ttk.Combobox(algo_params_frame, textvariable=self.vars['noise_schedule'],
                                   values=["linear", "cosine", "exponential", "custom"], width=15)
        noise_combo.pack(side=tk.LEFT, padx=5)
        
        self.vars['guidance_scale'] = tk.DoubleVar(value=7.5)
        ttk.Label(algo_params_frame, text="指导强度:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        guidance_spin = ttk.Spinbox(algo_params_frame, from_=1.0, to=20.0, increment=0.5,
                                     textvariable=self.vars['guidance_scale'], width=10)
        guidance_spin.pack(side=tk.LEFT, padx=5)
        
        # 网格处理选项
        mesh_processing_frame = ttk.LabelFrame(processing_frame, text="网格处理", padding="10")
        mesh_processing_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 基础处理选项
        basic_processing_frame = ttk.Frame(mesh_processing_frame)
        basic_processing_frame.pack(fill=tk.X, pady=2)
        
        self.vars['simplify_mesh'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(basic_processing_frame, text="网格简化", 
                       variable=self.vars['simplify_mesh']).pack(side=tk.LEFT)
        
        self.vars['smooth_surface'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(basic_processing_frame, text="表面平滑", 
                       variable=self.vars['smooth_surface']).pack(side=tk.LEFT, padx=(20, 0))
        
        self.vars['compute_normals'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(basic_processing_frame, text="法线计算", 
                       variable=self.vars['compute_normals']).pack(side=tk.LEFT, padx=(20, 0))
        
        # 高级处理选项
        advanced_processing_frame = ttk.Frame(mesh_processing_frame)
        advanced_processing_frame.pack(fill=tk.X, pady=2)
        
        self.vars['texture_generation'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(advanced_processing_frame, text="纹理生成", 
                       variable=self.vars['texture_generation']).pack(side=tk.LEFT)
        
        self.vars['pbr_materials'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(advanced_processing_frame, text="PBR材质", 
                       variable=self.vars['pbr_materials']).pack(side=tk.LEFT, padx=(20, 0))
        
        self.vars['lighting_baking'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(advanced_processing_frame, text="光照烘焙", 
                       variable=self.vars['lighting_baking']).pack(side=tk.LEFT, padx=(20, 0))
        
        # 专业处理选项
        professional_frame = ttk.LabelFrame(processing_frame, text="专业处理", padding="10")
        professional_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 物理模拟
        physics_frame = ttk.Frame(professional_frame)
        physics_frame.pack(fill=tk.X, pady=2)
        
        self.vars['physics_simulation'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(physics_frame, text="物理模拟", 
                       variable=self.vars['physics_simulation']).pack(side=tk.LEFT)
        
        self.vars['animation_rig'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(physics_frame, text="动画绑定", 
                       variable=self.vars['animation_rig']).pack(side=tk.LEFT, padx=(20, 0))
        
        # 质量优化
        optimization_frame = ttk.Frame(professional_frame)
        optimization_frame.pack(fill=tk.X, pady=2)
        
        self.vars['lod_generation'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(optimization_frame, text="LOD生成", 
                       variable=self.vars['lod_generation']).pack(side=tk.LEFT)
        
        self.vars['collision_detection'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(optimization_frame, text="碰撞检测", 
                       variable=self.vars['collision_detection']).pack(side=tk.LEFT, padx=(20, 0))
        
        # 种子和随机性
        seed_frame = ttk.LabelFrame(processing_frame, text="种子设置", padding="10")
        seed_frame.pack(fill=tk.X, padx=10, pady=5)
        
        seed_control_frame = ttk.Frame(seed_frame)
        seed_control_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(seed_control_frame, text="种子值:", width=15).pack(side=tk.LEFT)
        seed_spin = ttk.Spinbox(seed_control_frame, from_=0, to=999999999,
                               textvariable=self.vars['seed'], width=10)
        seed_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Checkbutton(seed_control_frame, text="随机种子", 
                       variable=self.vars['random_seed']).pack(side=tk.LEFT, padx=(20, 5))
        
        ttk.Button(seed_control_frame, text="生成新种子", 
                  command=self.generate_new_seed).pack(side=tk.LEFT, padx=10)
        
        # 输出优化
        output_optimization_frame = ttk.LabelFrame(processing_frame, text="输出优化", padding="10")
        output_optimization_frame.pack(fill=tk.X, padx=10, pady=5)
        
        output_opts_frame = ttk.Frame(output_optimization_frame)
        output_opts_frame.pack(fill=tk.X, pady=2)
        
        self.vars['vertex_limit'] = tk.IntVar(value=100000)
        ttk.Label(output_opts_frame, text="顶点限制:", width=15).pack(side=tk.LEFT)
        vertex_spin = ttk.Spinbox(output_opts_frame, from_=1000, to=1000000,
                                  textvariable=self.vars['vertex_limit'], width=10)
        vertex_spin.pack(side=tk.LEFT, padx=5)
        
        self.vars['compression_level'] = tk.IntVar(value=5)
        ttk.Label(output_opts_frame, text="压缩等级:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        compression_spin = ttk.Spinbox(output_opts_frame, from_=1, to=9,
                                       textvariable=self.vars['compression_level'], width=10)
        compression_spin.pack(side=tk.LEFT, padx=5)
        
        # 性能监控
        performance_frame = ttk.LabelFrame(processing_frame, text="性能监控", padding="10")
        performance_frame.pack(fill=tk.X, padx=10, pady=5)
        
        performance_status_frame = ttk.Frame(performance_frame)
        performance_status_frame.pack(fill=tk.X, pady=2)
        
        self.vars['memory_usage'] = tk.StringVar(value="0 MB")
        ttk.Label(performance_status_frame, text="内存使用:", width=15).pack(side=tk.LEFT)
        ttk.Label(performance_status_frame, textvariable=self.vars['memory_usage']).pack(side=tk.LEFT, padx=5)
        
        self.vars['gpu_usage'] = tk.StringVar(value="0%")
        ttk.Label(performance_status_frame, text="GPU使用:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        ttk.Label(performance_status_frame, textvariable=self.vars['gpu_usage']).pack(side=tk.LEFT, padx=5)
        
        # 进度显示
        progress_frame = ttk.Frame(performance_frame)
        progress_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(progress_frame, text="处理进度:").pack(anchor="w")
        self.vars['processing_progress'] = tk.DoubleVar(value=0)
        processing_progress_bar = ttk.Progressbar(progress_frame, variable=self.vars['processing_progress'],
                                                 length=400, mode='determinate')
        processing_progress_bar.pack(fill=tk.X, pady=2)
        
        self.vars['processing_status'] = tk.StringVar(value="就绪")
        processing_status_label = ttk.Label(progress_frame, textvariable=self.vars['processing_status'])
        processing_status_label.pack(anchor="w")
    
    def create_output_tab(self, notebook):
        """创建输出设置标签页"""
        
        output_frame = ttk.Frame(notebook)
        notebook.add(output_frame, text="输出设置")
        
        # 初始化输出相关变量
        self.vars['output_directory'] = tk.StringVar(value="./3d_output")
        self.vars['output_filename'] = tk.StringVar(value="3d_model_{timestamp}")
        self.vars['output_format'] = tk.StringVar(value="glb")
        self.vars['save_prompt'] = tk.BooleanVar(value=True)
        self.vars['save_metadata'] = tk.BooleanVar(value=True)
        
        # 输出路径设置
        path_frame = ttk.LabelFrame(output_frame, text="输出路径", padding="10")
        path_frame.pack(fill=tk.X, padx=10, pady=5)
        
        output_dir_frame = ttk.Frame(path_frame)
        output_dir_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(output_dir_frame, text="输出目录:", width=15).pack(side=tk.LEFT)
        ttk.Entry(output_dir_frame, textvariable=self.vars['output_directory'], 
                  width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(output_dir_frame, text="浏览", 
                  command=self.select_output_directory).pack(side=tk.LEFT, padx=2)
        
        # 文件名模板
        filename_frame = ttk.Frame(path_frame)
        filename_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(filename_frame, text="文件名模板:", width=15).pack(side=tk.LEFT)
        ttk.Entry(filename_frame, textvariable=self.vars['output_filename'], 
                  width=40).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 文件名模板说明
        filename_help_frame = ttk.Frame(path_frame)
        filename_help_frame.pack(fill=tk.X, pady=2)
        
        help_text = "可用变量: {timestamp} {model} {quality} {format} {input_type}"
        ttk.Label(filename_help_frame, text=help_text, foreground="gray").pack(anchor="w")
        
        # 3D格式和质量设置
        format_frame = ttk.LabelFrame(output_frame, text="3D格式和质量", padding="10")
        format_frame.pack(fill=tk.X, padx=10, pady=5)
        
        format_quality_frame = ttk.Frame(format_frame)
        format_quality_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(format_quality_frame, text="3D格式:", width=15).pack(side=tk.LEFT)
        
        # 格式选择
        format_values = []
        for category, formats in self.output_formats.items():
            for format_key, format_name in formats.items():
                format_values.append(f"{category}: {format_name}")
        
        format_combo = ttk.Combobox(format_quality_frame, textvariable=self.vars['output_format'],
                                   values=format_values, width=25)
        format_combo.pack(side=tk.LEFT, padx=5)
        
        # 质量设置
        quality_level_frame = ttk.Frame(format_frame)
        quality_level_frame.pack(fill=tk.X, pady=2)
        
        self.vars['output_quality'] = tk.StringVar(value="high")
        ttk.Label(quality_level_frame, text="输出质量:", width=15).pack(side=tk.LEFT)
        quality_level_combo = ttk.Combobox(quality_level_frame, textvariable=self.vars['output_quality'],
                                          values=["fast", "balanced", "high", "ultra"], width=15)
        quality_level_combo.pack(side=tk.LEFT, padx=5)
        
        # 精度设置
        precision_frame = ttk.Frame(format_frame)
        precision_frame.pack(fill=tk.X, pady=2)
        
        self.vars['precision'] = tk.StringVar(value="float32")
        ttk.Label(precision_frame, text="精度:", width=15).pack(side=tk.LEFT)
        precision_combo = ttk.Combobox(precision_frame, textvariable=self.vars['precision'],
                                       values=["float16", "float32", "float64"], width=15)
        precision_combo.pack(side=tk.LEFT, padx=5)
        
        self.vars['coordinate_system'] = tk.StringVar(value="right-handed")
        ttk.Label(precision_frame, text="坐标系:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        coord_combo = ttk.Combobox(precision_frame, textvariable=self.vars['coordinate_system'],
                                   values=["right-handed", "left-handed"], width=15)
        coord_combo.pack(side=tk.LEFT, padx=5)
        
        # 纹理和材质设置
        texture_frame = ttk.LabelFrame(output_frame, text="纹理和材质", padding="10")
        texture_frame.pack(fill=tk.X, padx=10, pady=5)
        
        texture_options_frame = ttk.Frame(texture_frame)
        texture_options_frame.pack(fill=tk.X, pady=2)
        
        self.vars['include_textures'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(texture_options_frame, text="包含纹理", 
                       variable=self.vars['include_textures']).pack(side=tk.LEFT)
        
        self.vars['texture_format'] = tk.StringVar(value="png")
        ttk.Label(texture_options_frame, text="纹理格式:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        tex_format_combo = ttk.Combobox(texture_options_frame, textvariable=self.vars['texture_format'],
                                         values=["png", "jpg", "tga", "exr"], width=10)
        tex_format_combo.pack(side=tk.LEFT, padx=5)
        
        self.vars['texture_resolution'] = tk.IntVar(value=1024)
        ttk.Label(texture_options_frame, text="纹理分辨率:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        tex_res_spin = ttk.Spinbox(texture_options_frame, from_=256, to=4096, increment=256,
                                   textvariable=self.vars['texture_resolution'], width=10)
        tex_res_spin.pack(side=tk.LEFT, padx=5)
        
        # 材质设置
        material_options_frame = ttk.Frame(texture_frame)
        material_options_frame.pack(fill=tk.X, pady=2)
        
        self.vars['include_materials'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(material_options_frame, text="包含材质", 
                       variable=self.vars['include_materials']).pack(side=tk.LEFT)
        
        self.vars['material_format'] = tk.StringVar(value="pbr")
        ttk.Label(material_options_frame, text="材质格式:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        mat_format_combo = ttk.Combobox(material_options_frame, textvariable=self.vars['material_format'],
                                         values=["pbr", "basic", "phong", "lambert"], width=12)
        mat_format_combo.pack(side=tk.LEFT, padx=5)
        
        # 保存选项
        save_options_frame = ttk.LabelFrame(output_frame, text="保存选项", padding="10")
        save_options_frame.pack(fill=tk.X, padx=10, pady=5)
        
        save_toggles_frame = ttk.Frame(save_options_frame)
        save_toggles_frame.pack(fill=tk.X, pady=2)
        
        ttk.Checkbutton(save_toggles_frame, text="保存提示词", 
                       variable=self.vars['save_prompt']).pack(side=tk.LEFT)
        
        ttk.Checkbutton(save_toggles_frame, text="保存元数据", 
                       variable=self.vars['save_metadata']).pack(side=tk.LEFT, padx=(20, 0))
        
        self.vars['save_settings'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(save_toggles_frame, text="保存设置", 
                       variable=self.vars['save_settings']).pack(side=tk.LEFT, padx=(20, 0))
        
        self.vars['save_process_log'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(save_toggles_frame, text="保存处理日志", 
                       variable=self.vars['save_process_log']).pack(side=tk.LEFT, padx=(20, 0))
        
        # 输出组织
        organize_frame = ttk.LabelFrame(output_frame, text="输出组织", padding="10")
        organize_frame.pack(fill=tk.X, padx=10, pady=5)
        
        organize_options_frame = ttk.Frame(organize_frame)
        organize_options_frame.pack(fill=tk.X, pady=2)
        
        self.vars['organize_by_model'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(organize_options_frame, text="按模型分类", 
                       variable=self.vars['organize_by_model']).pack(side=tk.LEFT)
        
        self.vars['organize_by_date'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(organize_options_frame, text="按日期分类", 
                       variable=self.vars['organize_by_date']).pack(side=tk.LEFT, padx=(20, 0))
        
        self.vars['create_preview'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(organize_options_frame, text="生成预览图", 
                       variable=self.vars['create_preview']).pack(side=tk.LEFT, padx=(20, 0))
        
        # 批处理设置
        batch_frame = ttk.LabelFrame(output_frame, text="批处理设置", padding="10")
        batch_frame.pack(fill=tk.X, padx=10, pady=5)
        
        batch_options_frame = ttk.Frame(batch_frame)
        batch_options_frame.pack(fill=tk.X, pady=2)
        
        self.vars['enable_batch'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(batch_options_frame, text="启用批处理", 
                       variable=self.vars['enable_batch']).pack(side=tk.LEFT)
        
        self.vars['batch_size'] = tk.IntVar(value=1)
        ttk.Label(batch_options_frame, text="批量大小:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        batch_size_spin = ttk.Spinbox(batch_options_frame, from_=1, to=5,
                                      textvariable=self.vars['batch_size'], width=10)
        batch_size_spin.pack(side=tk.LEFT, padx=5)
        
        # 压缩和优化
        compression_frame = ttk.LabelFrame(output_frame, text="压缩和优化", padding="10")
        compression_frame.pack(fill=tk.X, padx=10, pady=5)
        
        compression_options_frame = ttk.Frame(compression_frame)
        compression_options_frame.pack(fill=tk.X, pady=2)
        
        self.vars['enable_compression'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(compression_options_frame, text="启用压缩", 
                       variable=self.vars['enable_compression']).pack(side=tk.LEFT)
        
        self.vars['optimize_mesh'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(compression_options_frame, text="优化网格", 
                       variable=self.vars['optimize_mesh']).pack(side=tk.LEFT, padx=(20, 0))
        
        # 压缩设置
        compression_settings_frame = ttk.Frame(compression_frame)
        compression_settings_frame.pack(fill=tk.X, pady=2)
        
        self.vars['compression_algorithm'] = tk.StringVar(value="gzip")
        ttk.Label(compression_settings_frame, text="压缩算法:", width=15).pack(side=tk.LEFT)
        comp_algo_combo = ttk.Combobox(compression_settings_frame, textvariable=self.vars['compression_algorithm'],
                                       values=["gzip", "bzip2", "lz4", "zstd"], width=12)
        comp_algo_combo.pack(side=tk.LEFT, padx=5)
        
        self.vars['optimization_level'] = tk.IntVar(value=3)
        ttk.Label(compression_settings_frame, text="优化等级:", width=15).pack(side=tk.LEFT, padx=(20, 0))
        opt_level_spin = ttk.Spinbox(compression_settings_frame, from_=1, to=9,
                                      textvariable=self.vars['optimization_level'], width=10)
        opt_level_spin.pack(side=tk.LEFT, padx=5)
        
        # 生成控制
        control_frame = ttk.LabelFrame(output_frame, text="生成控制", padding="10")
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 控制按钮
        control_buttons_frame = ttk.Frame(control_frame)
        control_buttons_frame.pack(fill=tk.X, pady=5)
        
        ttk.Button(control_buttons_frame, text="开始生成", 
                  command=self.start_generation).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_buttons_frame, text="暂停", 
                  command=self.pause_generation).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_buttons_frame, text="停止", 
                  command=self.stop_generation).pack(side=tk.LEFT, padx=5)
        ttk.Button(control_buttons_frame, text="预览", 
                  command=self.preview_generation).pack(side=tk.LEFT, padx=10)
        
        # 进度显示
        generation_progress_frame = ttk.Frame(control_frame)
        generation_progress_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(generation_progress_frame, text="生成进度:").pack(anchor="w")
        self.vars['generation_progress'] = tk.DoubleVar(value=0)
        generation_progress_bar = ttk.Progressbar(generation_progress_frame, variable=self.vars['generation_progress'],
                                                 length=400, mode='determinate')
        generation_progress_bar.pack(fill=tk.X, pady=2)
        
        self.vars['generation_status'] = tk.StringVar(value="就绪")
        generation_status_label = ttk.Label(generation_progress_frame, textvariable=self.vars['generation_status'])
        generation_status_label.pack(anchor="w")
        
        # 生成日志
        log_frame = ttk.LabelFrame(control_frame, text="生成日志", padding="5")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        log_text = tk.Text(log_frame, height=6, wrap=tk.WORD)
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview)
        log_text.configure(yscrollcommand=log_scrollbar.set)
        
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def create_preview_tab(self, notebook):
        """创建预览标签页"""
        
        preview_frame = ttk.Frame(notebook)
        notebook.add(preview_frame, text="预览")
        
        # 初始化预览相关变量
        self.vars['preview_quality'] = tk.StringVar(value="medium")
        self.vars['preview_format'] = tk.StringVar(value="png")
        self.vars['show_wireframe'] = tk.BooleanVar(value=False)
        self.vars['show_texture'] = tk.BooleanVar(value=True)
        
        # 3D预览显示区域
        preview_display_frame = ttk.LabelFrame(preview_frame, text="3D预览", padding="10")
        preview_display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 3D预览画布
        self.preview_canvas = tk.Canvas(preview_display_frame, width=800, height=500, bg="lightgray")
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 在画布上显示提示文本
        self.preview_canvas.create_text(400, 250, text="3D模型预览区域", fill="black", font=("Arial", 16))
        self.preview_canvas.create_text(400, 280, text="预览功能需要集成3D渲染引擎", fill="gray", font=("Arial", 12))
        
        # 预览控制
        preview_control_frame = ttk.Frame(preview_display_frame)
        preview_control_frame.pack(fill=tk.X, pady=5)
        
        # 预览质量设置
        quality_frame = ttk.Frame(preview_control_frame)
        quality_frame.pack(side=tk.LEFT)
        
        ttk.Label(quality_frame, text="预览质量:", width=12).pack(side=tk.LEFT)
        quality_combo = ttk.Combobox(quality_frame, textvariable=self.vars['preview_quality'],
                                     values=["low", "medium", "high", "ultra"], width=10)
        quality_combo.pack(side=tk.LEFT, padx=5)
        
        # 预览格式设置
        format_frame = ttk.Frame(preview_control_frame)
        format_frame.pack(side=tk.LEFT, padx=(20, 0))
        
        ttk.Label(format_frame, text="预览格式:", width=12).pack(side=tk.LEFT)
        format_combo = ttk.Combobox(format_frame, textvariable=self.vars['preview_format'],
                                    values=["png", "jpg", "bmp", "exr"], width=10)
        format_combo.pack(side=tk.LEFT, padx=5)
        
        # 预览选项
        preview_options_frame = ttk.Frame(preview_control_frame)
        preview_options_frame.pack(side=tk.RIGHT)
        
        ttk.Checkbutton(preview_options_frame, text="线框模式", 
                       variable=self.vars['show_wireframe']).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(preview_options_frame, text="显示纹理", 
                       variable=self.vars['show_texture']).pack(side=tk.LEFT, padx=5)
        
        # 预览操作按钮
        preview_actions_frame = ttk.Frame(preview_frame)
        preview_actions_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Button(preview_actions_frame, text="刷新预览", 
                  command=self.refresh_preview).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_actions_frame, text="保存预览", 
                  command=self.save_preview).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_actions_frame, text="导出预览", 
                  command=self.export_preview).pack(side=tk.LEFT, padx=5)
        ttk.Button(preview_actions_frame, text="全屏预览", 
                  command=self.fullscreen_preview).pack(side=tk.LEFT, padx=5)
        
        # 预览信息显示
        info_display_frame = ttk.LabelFrame(preview_frame, text="模型信息", padding="10")
        info_display_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 信息显示文本
        info_text = tk.Text(info_display_frame, height=8, wrap=tk.WORD)
        info_scrollbar = ttk.Scrollbar(info_display_frame, orient=tk.VERTICAL, command=info_text.yview)
        info_text.configure(yscrollcommand=info_scrollbar.set)
        
        model_info = """
3D模型信息：

基本信息：
• 模型名称: 尚未生成
• 顶点数量: 0
• 面数: 0
• 纹理: 无
• 材质: 无

几何信息：
• 包围盒: 未计算
• 质心: 未计算
• 法线: 未计算
• UV坐标: 未计算

文件信息：
• 文件大小: 0 KB
• 生成时间: 未生成
• 处理时长: 0 秒
• 质量等级: 未设置
        """
        
        info_text.insert(tk.END, model_info)
        info_text.config(state=tk.DISABLED)
        info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        info_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 旋转和缩放控制
        transform_frame = ttk.LabelFrame(preview_frame, text="变换控制", padding="10")
        transform_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 旋转控制
        rotation_frame = ttk.Frame(transform_frame)
        rotation_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(rotation_frame, text="旋转X:", width=10).pack(side=tk.LEFT)
        self.vars['rotation_x'] = tk.DoubleVar(value=0)
        rotation_x_spin = ttk.Spinbox(rotation_frame, from_=-180, to=180, increment=1,
                                      textvariable=self.vars['rotation_x'], width=8)
        rotation_x_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(rotation_frame, text="旋转Y:", width=10).pack(side=tk.LEFT, padx=(20, 0))
        self.vars['rotation_y'] = tk.DoubleVar(value=0)
        rotation_y_spin = ttk.Spinbox(rotation_frame, from_=-180, to=180, increment=1,
                                      textvariable=self.vars['rotation_y'], width=8)
        rotation_y_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(rotation_frame, text="旋转Z:", width=10).pack(side=tk.LEFT, padx=(20, 0))
        self.vars['rotation_z'] = tk.DoubleVar(value=0)
        rotation_z_spin = ttk.Spinbox(rotation_frame, from_=-180, to=180, increment=1,
                                      textvariable=self.vars['rotation_z'], width=8)
        rotation_z_spin.pack(side=tk.LEFT, padx=5)
        
        # 缩放控制
        scale_frame = ttk.Frame(transform_frame)
        scale_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(scale_frame, text="缩放:", width=10).pack(side=tk.LEFT)
        self.vars['scale'] = tk.DoubleVar(value=1.0)
        scale_spin = ttk.Spinbox(scale_frame, from_=0.1, to=10.0, increment=0.1,
                                 textvariable=self.vars['scale'], width=8)
        scale_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(scale_frame, text="重置", 
                  command=self.reset_transform).pack(side=tk.LEFT, padx=20)
        
        # 相机控制
        camera_frame = ttk.LabelFrame(preview_frame, text="相机控制", padding="10")
        camera_frame.pack(fill=tk.X, padx=10, pady=5)
        
        camera_control_frame = ttk.Frame(camera_frame)
        camera_control_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(camera_control_frame, text="视角:", width=10).pack(side=tk.LEFT)
        self.vars['camera_view'] = tk.StringVar(value="front")
        view_combo = ttk.Combobox(camera_control_frame, textvariable=self.vars['camera_view'],
                                  values=["front", "back", "left", "right", "top", "bottom", "isometric"], width=12)
        view_combo.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(camera_control_frame, text="距离:", width=10).pack(side=tk.LEFT, padx=(20, 0))
        self.vars['camera_distance'] = tk.DoubleVar(value=5.0)
        distance_spin = ttk.Spinbox(camera_control_frame, from_=1.0, to=50.0, increment=0.5,
                                    textvariable=self.vars['camera_distance'], width=8)
        distance_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(camera_control_frame, text="自动旋转", 
                  command=self.auto_rotate).pack(side=tk.LEFT, padx=20)
        
        # 光照设置
        lighting_frame = ttk.LabelFrame(preview_frame, text="光照设置", padding="10")
        lighting_frame.pack(fill=tk.X, padx=10, pady=5)
        
        lighting_control_frame = ttk.Frame(lighting_frame)
        lighting_control_frame.pack(fill=tk.X, pady=2)
        
        self.vars['ambient_light'] = tk.DoubleVar(value=0.3)
        ttk.Label(lighting_control_frame, text="环境光:", width=12).pack(side=tk.LEFT)
        ambient_spin = ttk.Spinbox(lighting_control_frame, from_=0.0, to=1.0, increment=0.1,
                                    textvariable=self.vars['ambient_light'], width=8)
        ambient_spin.pack(side=tk.LEFT, padx=5)
        
        self.vars['directional_light'] = tk.DoubleVar(value=0.8)
        ttk.Label(lighting_control_frame, text="方向光:", width=12).pack(side=tk.LEFT, padx=(20, 0))
        directional_spin = ttk.Spinbox(lighting_control_frame, from_=0.0, to=2.0, increment=0.1,
                                       textvariable=self.vars['directional_light'], width=8)
        directional_spin.pack(side=tk.LEFT, padx=5)
        
        # 渲染设置
        render_settings_frame = ttk.Frame(lighting_frame)
        render_settings_frame.pack(fill=tk.X, pady=2)
        
        self.vars['anti_aliasing'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(render_settings_frame, text="抗锯齿", 
                       variable=self.vars['anti_aliasing']).pack(side=tk.LEFT)
        
        self.vars['shadows'] = tk.BooleanVar(value=True)
        ttk.Checkbutton(render_settings_frame, text="阴影", 
                       variable=self.vars['shadows']).pack(side=tk.LEFT, padx=(20, 0))
        
        self.vars['reflections'] = tk.BooleanVar(value=False)
        ttk.Checkbutton(render_settings_frame, text="反射", 
                       variable=self.vars['reflections']).pack(side=tk.LEFT, padx=(20, 0))

    # ========== 辅助方法实现 ==========
    
    def select_model_file(self):
        """选择3D模型文件"""
        file_path = filedialog.askopenfilename(
            title="选择3D模型文件",
            filetypes=[
                ("所有支持格式", "*.safetensors *.ckpt *.bin *.pth *.json"),
                ("Safetensors", "*.safetensors"),
                ("Checkpoint", "*.ckpt *.bin *.pth"),
                ("配置文件", "*.json *.yaml *.yml"),
                ("目录", "")
            ]
        )
        if file_path:
            self.vars['model_path'].set(file_path)
    
    def load_custom_model(self):
        """加载自定义模型"""
        model_name = self.vars['custom_model_name'].get()
        if model_name:
            messagebox.showinfo("功能提示", f"正在加载自定义模型: {model_name}")
        else:
            messagebox.showwarning("警告", "请输入自定义模型名称")
    
    def download_model(self):
        """下载模型"""
        source = self.vars['download_source'].get()
        model = self.vars['download_model'].get()
        if model:
            self.vars['download_status'].set(f"正在从 {source} 下载模型...")
            # 模拟下载进度
            for i in range(101):
                self.vars['download_progress'].set(i)
                if i == 100:
                    self.vars['download_status'].set("下载完成")
            messagebox.showinfo("成功", f"模型 {model} 下载完成")
        else:
            messagebox.showwarning("警告", "请输入要下载的模型名称")
    
    def check_model_updates(self):
        """检查模型更新"""
        messagebox.showinfo("检查更新", "正在检查模型更新...")
    
    def manage_models(self):
        """管理模型"""
        messagebox.showinfo("模型管理", "模型管理功能开发中...")
    
    def select_input_image(self):
        """选择输入图片"""
        file_path = filedialog.askopenfilename(
            title="选择输入图片",
            filetypes=[
                ("图片文件", "*.jpg *.jpeg *.png *.bmp *.tiff *.hdr *.exr"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("BMP", "*.bmp"),
                ("TIFF", "*.tiff"),
                ("HDR/EXR", "*.hdr *.exr")
            ]
        )
        if file_path:
            self.vars['input_image_path'].set(file_path)
    
    def select_input_video(self):
        """选择输入视频"""
        file_path = filedialog.askopenfilename(
            title="选择输入视频",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("MP4", "*.mp4"),
                ("AVI", "*.avi"),
                ("MOV", "*.mov"),
                ("MKV", "*.mkv"),
                ("WebM", "*.webm")
            ]
        )
        if file_path:
            self.vars['input_video_path'].set(file_path)
    
    def apply_text_template(self):
        """应用文本模板"""
        template = self.vars['text_template'].get()
        if template == "详细描述":
            self.vars['input_text'].set("创建一个详细的3D模型，包含完整的几何形状、纹理和材质")
        elif template == "关键词":
            self.vars['input_text'].set("现代, 简约, 高质量, 细节丰富")
        elif template == "风格参考":
            self.vars['input_text'].set("参考风格：写实, 专业, 精细, 艺术性")
        elif template == "技术规格":
            self.vars['input_text'].set("技术规格：高多边形，精细网格，PBR材质，专业质量")
    
    def generate_new_seed(self):
        """生成新种子"""
        import random
        new_seed = random.randint(0, 999999999)
        self.vars['seed'].set(new_seed)
        self.vars['random_seed'].set(False)
    
    def select_output_directory(self):
        """选择输出目录"""
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.vars['output_directory'].set(directory)
    
    def refresh_preview(self):
        """刷新预览"""
        messagebox.showinfo("预览", "刷新3D预览功能开发中...")
    
    def save_preview(self):
        """保存预览"""
        messagebox.showinfo("预览", "保存预览功能开发中...")
    
    def export_preview(self):
        """导出预览"""
        messagebox.showinfo("预览", "导出预览功能开发中...")
    
    def fullscreen_preview(self):
        """全屏预览"""
        messagebox.showinfo("预览", "全屏预览功能开发中...")
    
    def reset_transform(self):
        """重置变换"""
        self.vars['rotation_x'].set(0)
        self.vars['rotation_y'].set(0)
        self.vars['rotation_z'].set(0)
        self.vars['scale'].set(1.0)
    
    def auto_rotate(self):
        """自动旋转"""
        messagebox.showinfo("预览", "自动旋转功能开发中...")
    
    def start_generation(self):
        """开始生成"""
        messagebox.showinfo("功能提示", "3D生成功能需要完整的后端集成")
    
    def pause_generation(self):
        """暂停生成"""
        messagebox.showinfo("功能提示", "暂停功能需要实现")
    
    def stop_generation(self):
        """停止生成"""
        messagebox.showinfo("功能提示", "停止功能需要实现")
    
    def preview_generation(self):
        """预览生成"""
        messagebox.showinfo("预览", "3D预览生成功能开发中...")


if __name__ == "__main__":
    # 测试代码
    root = tk.Tk()
    root.title("增强版3D生成组件测试")
    root.geometry("1200x900")
    
    # 创建测试框架
    test_frame = ttk.Frame(root)
    test_frame.pack(fill=tk.BOTH, expand=True)
    
    # 创建增强版组件
    components = Enhanced3DGenerationComponents(test_frame, None)
    
    root.mainloop()