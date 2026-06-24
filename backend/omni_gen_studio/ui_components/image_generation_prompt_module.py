#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片生成 - 提示词模组
支持批量提示词加载、模板化管理、AI优化和翻译功能

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import json
import re
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class PromptModule:
    """图片生成提示词管理模组"""
    
    def __init__(self, parent_frame, callback=None):
        self.parent_frame = parent_frame
        self.callback = callback
        self.prompt_templates = {}
        self.current_prompt = ""
        self.current_negative_prompt = ""
        self.batch_prompts = []
        self.prompt_history = []
        self.optimization_enabled = False
        self.translation_enabled = False
        
        # 提示词模板分类
        self.template_categories = {
            "人物肖像": {
                "人像摄影": "A professional portrait of [subject], high quality, detailed facial features, natural lighting, photorealistic, 8k",
                "动漫角色": "anime character, [character_style], detailed eyes, colorful hair, school uniform, high quality art",
                "古风美女": "ancient Chinese beauty, elegant hanfu dress, traditional makeup, cherry blossoms background, traditional art style",
                "科幻人物": "futuristic character, cyberpunk style, neon lighting, high tech clothing, detailed mechanical elements",
                "时尚模特": "fashion model, elegant pose, professional lighting, high fashion clothing, magazine quality, sophisticated"
            },
            "风景场景": {
                "自然风景": "beautiful landscape, [scenery_type], natural lighting, high resolution, detailed nature, panoramic view",
                "城市夜景": "cityscape at night, neon lights, urban environment, modern architecture, atmospheric lighting, 4k",
                "山水画风": "Chinese landscape painting style, mountains and water, traditional art, ink wash technique, elegant composition",
                "未来城市": "futuristic city, flying cars, skyscrapers, holographic displays, cyberpunk aesthetic, detailed architecture",
                "梦幻森林": "mystical forest, magical atmosphere, soft lighting, fantasy elements, ethereal, enchanted"
            },
            "艺术风格": {
                "油画风格": "oil painting style, classical art, rich colors, brushstrokes visible, detailed texture, masterpiece quality",
                "水彩画风": "watercolor painting, soft colors, flowing brushstrokes, artistic style, delicate details, elegant",
                "像素艺术": "pixel art style, retro gaming, 8-bit graphics, nostalgic, colorful pixels, classic arcade",
                "概念艺术": "concept art, fantasy illustration, digital painting, detailed environment, dramatic lighting, professional",
                "插画风格": "illustration style, book art, character design, clean lines, vibrant colors, engaging composition"
            },
            "技术特效": {
                "景深效果": "shallow depth of field, bokeh effect, sharp focus on subject, blurred background, professional photography",
                "光影效果": "dramatic lighting, volumetric lighting, god rays, cinematic lighting, atmospheric effects",
                "粒子特效": "particle effects, sparkles, magical particles, glowing elements, dynamic motion, fantasy",
                "反射折射": "water reflections, glass refraction, transparent materials, realistic physics, detailed surfaces",
                "动态模糊": "motion blur, dynamic movement, action scene, speed lines, dynamic composition"
            }
        }
        
        # AI优化关键词映射
        self.optimization_mappings = {
            "高质量": "masterpiece, high quality, best quality, ultra detailed",
            "4K分辨率": "4k, 8k, uhd, ultra high resolution, crisp details",
            "专业摄影": "professional photography, studio lighting, commercial photography, award winning",
            "电影级": "cinematic lighting, movie quality, film photography, epic composition",
            "艺术级": "artistic masterpiece, gallery quality, museum worthy, fine art photography",
            "细节丰富": "intricate details, elaborate textures, complex patterns, refined details",
            "色彩鲜艳": "vibrant colors, rich saturation, dynamic color palette, bold contrast",
            "柔和自然": "natural lighting, soft shadows, gentle curves, organic feel",
            "清晰锐利": "sharp focus, crystal clear, high definition, precise details"
        }
        
        # 负面提示词模板
        self.negative_prompt_templates = {
            "通用负面": "low quality, blurry, distorted, ugly, bad anatomy, bad proportions, extra limbs, missing limbs",
            "人像负面": "bad face, deformed, extra fingers, missing fingers, poorly drawn hands, poorly drawn face, mutation",
            "艺术负面": "watermark, signature, text, logo, artist name, frame, border, copyright",
            "技术负面": "jpeg artifacts, compression artifacts, noise, grain, pixelated, low resolution, blurry"
        }
        
        self.create_ui()
        self.load_default_templates()
    
    def create_ui(self):
        """创建提示词管理UI"""
        # 主容器
        main_container = ttk.Frame(self.parent_frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 标题
        title_label = ttk.Label(main_container, text="提示词管理", 
                               font=("微软雅黑", 14, "bold"))
        title_label.pack(anchor="w", pady=(0, 15))
        
        # 提示词输入区域
        self.create_prompt_input_area(main_container)
        
        # 功能选项卡
        notebook = ttk.Notebook(main_container)
        notebook.pack(fill="both", expand=True, pady=(10, 0))
        
        # 模板管理选项卡
        self.create_templates_tab(notebook)
        
        # 批量处理选项卡
        self.create_batch_tab(notebook)
        
        # 历史记录选项卡
        self.create_history_tab(notebook)
        
        # AI优化选项卡
        self.create_optimization_tab(notebook)
    
    def create_prompt_input_area(self, parent):
        """创建提示词输入区域"""
        input_frame = ttk.LabelFrame(parent, text="提示词输入", padding=15)
        input_frame.pack(fill="x", pady=(0, 15))
        
        # 正面提示词
        positive_frame = ttk.Frame(input_frame)
        positive_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(positive_frame, text="正面提示词:", font=("微软雅黑", 10, "bold")).pack(anchor="w")
        
        self.positive_text = tk.Text(positive_frame, height=4, wrap="word", 
                                    font=("Consolas", 10))
        self.positive_text.pack(fill="x", pady=(5, 0))
        
        # 正面提示词工具栏
        positive_tools = ttk.Frame(positive_frame)
        positive_tools.pack(fill="x", pady=(5, 0))
        
        ttk.Button(positive_tools, text="清空", 
                  command=lambda: self.positive_text.delete("1.0", "end")).pack(side="left", padx=(0, 10))
        
        ttk.Button(positive_tools, text="复制", 
                  command=self.copy_positive_prompt).pack(side="left", padx=(0, 10))
        
        self.ai_optimize_positive = tk.BooleanVar()
        ttk.Checkbutton(positive_tools, text="AI优化", 
                       variable=self.ai_optimize_positive).pack(side="left", padx=(0, 10))
        
        ttk.Button(positive_tools, text="应用模板", 
                  command=self.apply_template_to_positive).pack(side="left")
        
        # 负面提示词
        negative_frame = ttk.Frame(input_frame)
        negative_frame.pack(fill="x")
        
        ttk.Label(negative_frame, text="负面提示词:", font=("微软雅黑", 10, "bold")).pack(anchor="w")
        
        self.negative_text = tk.Text(negative_frame, height=3, wrap="word", 
                                    font=("Consolas", 10))
        self.negative_text.pack(fill="x", pady=(5, 0))
        
        # 负面提示词工具栏
        negative_tools = ttk.Frame(negative_frame)
        negative_tools.pack(fill="x", pady=(5, 0))
        
        ttk.Button(negative_tools, text="清空", 
                  command=lambda: self.negative_text.delete("1.0", "end")).pack(side="left", padx=(0, 10))
        
        ttk.Button(negative_tools, text="复制", 
                  command=self.copy_negative_prompt).pack(side="left", padx=(0, 10))
        
        ttk.Button(negative_tools, text="加载模板", 
                  command=self.load_negative_template).pack(side="left", padx=(0, 10))
        
        # 保存到历史记录按钮
        save_frame = ttk.Frame(input_frame)
        save_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(save_frame, text="保存到历史记录", 
                  command=self.save_to_history).pack(side="left")
        
        ttk.Button(save_frame, text="应用到当前", 
                  command=self.apply_current_prompt).pack(side="left", padx=(10, 0))
    
    def create_templates_tab(self, notebook):
        """创建模板管理选项卡"""
        templates_frame = ttk.Frame(notebook)
        notebook.add(templates_frame, text="模板管理")
        
        # 模板分类和列表
        list_frame = ttk.Frame(templates_frame)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 分类列表
        category_frame = ttk.LabelFrame(list_frame, text="模板分类", padding=10)
        category_frame.pack(side="left", fill="y", padx=(0, 10))
        
        self.category_listbox = tk.Listbox(category_frame, height=15)
        self.category_listbox.pack(fill="both", expand=True)
        
        # 填充分类
        for category in self.template_categories.keys():
            self.category_listbox.insert(tk.END, category)
        
        self.category_listbox.bind("<<ListboxSelect>>", self.on_category_select)
        
        # 模板列表
        template_frame = ttk.LabelFrame(list_frame, text="模板列表", padding=10)
        template_frame.pack(side="left", fill="both", expand=True)
        
        # 搜索框
        search_frame = ttk.Frame(template_frame)
        search_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(search_frame, text="搜索:").pack(side="left")
        self.template_search_var = tk.StringVar()
        self.template_search_var.trace("w", self.on_template_search)
        search_entry = ttk.Entry(search_frame, textvariable=self.template_search_var)
        search_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        # 模板列表框
        self.template_listbox = tk.Listbox(template_frame, height=12)
        self.template_listbox.pack(fill="both", expand=True, pady=(0, 10))
        
        self.template_listbox.bind("<<ListboxSelect>>", self.on_template_select)
        
        # 模板操作按钮
        template_buttons = ttk.Frame(template_frame)
        template_buttons.pack(fill="x")
        
        ttk.Button(template_buttons, text="使用模板", 
                  command=self.use_selected_template).pack(side="left", padx=(0, 10))
        
        ttk.Button(template_buttons, text="编辑模板", 
                  command=self.edit_template).pack(side="left", padx=(0, 10))
        
        ttk.Button(template_buttons, text="新建模板", 
                  command=self.new_template).pack(side="left")
        
        # 模板预览
        preview_frame = ttk.LabelFrame(template_frame, text="模板预览", padding=10)
        preview_frame.pack(fill="both", expand=True, pady=(10, 0))
        
        self.template_preview = tk.Text(preview_frame, height=8, wrap="word", 
                                       font=("Consolas", 9), state="disabled")
        self.template_preview.pack(fill="both", expand=True)
    
    def create_batch_tab(self, notebook):
        """创建批量处理选项卡"""
        batch_frame = ttk.Frame(notebook)
        notebook.add(batch_frame, text="批量处理")
        
        # 批量输入
        input_frame = ttk.LabelFrame(batch_frame, text="批量提示词输入", padding=10)
        input_frame.pack(fill="x", padx=10, pady=10)
        
        # 文件导入
        file_frame = ttk.Frame(input_frame)
        file_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Button(file_frame, text="从文件导入", 
                  command=self.import_batch_file).pack(side="left", padx=(0, 10))
        
        ttk.Button(file_frame, text="从模板生成", 
                  command=self.generate_batch_from_template).pack(side="left", padx=(0, 10))
        
        # 批量列表
        list_frame = ttk.LabelFrame(batch_frame, text="批量提示词列表", padding=10)
        list_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 列表控件
        columns = ("序号", "提示词", "状态")
        self.batch_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        
        for col in columns:
            self.batch_tree.heading(col, text=col)
            self.batch_tree.column(col, width=200)
        
        batch_scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.batch_tree.yview)
        self.batch_tree.configure(yscrollcommand=batch_scrollbar.set)
        
        self.batch_tree.pack(side="left", fill="both", expand=True)
        batch_scrollbar.pack(side="right", fill="y")
        
        # 批量操作按钮
        batch_buttons = ttk.Frame(list_frame)
        batch_buttons.pack(fill="x", pady=(10, 0))
        
        ttk.Button(batch_buttons, text="添加到当前", 
                  command=self.add_batch_to_current).pack(side="left", padx=(0, 10))
        
        ttk.Button(batch_buttons, text="清空列表", 
                  command=self.clear_batch_list).pack(side="left", padx=(0, 10))
        
        ttk.Button(batch_buttons, text="导出列表", 
                  command=self.export_batch_list).pack(side="left")
    
    def create_history_tab(self, notebook):
        """创建历史记录选项卡"""
        history_frame = ttk.Frame(notebook)
        notebook.add(history_frame, text="历史记录")
        
        # 历史记录列表
        list_frame = ttk.LabelFrame(history_frame, text="历史记录", padding=10)
        list_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 搜索和筛选
        filter_frame = ttk.Frame(list_frame)
        filter_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(filter_frame, text="搜索:").pack(side="left")
        self.history_search_var = tk.StringVar()
        self.history_search_var.trace("w", self.on_history_search)
        history_search_entry = ttk.Entry(filter_frame, textvariable=self.history_search_var)
        history_search_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        # 历史记录列表
        self.history_listbox = tk.Listbox(list_frame, height=15)
        self.history_listbox.pack(fill="both", expand=True, pady=(0, 10))
        
        self.history_listbox.bind("<<ListboxSelect>>", self.on_history_select)
        
        # 历史操作按钮
        history_buttons = ttk.Frame(list_frame)
        history_buttons.pack(fill="x")
        
        ttk.Button(history_buttons, text="恢复", 
                  command=self.restore_from_history).pack(side="left", padx=(0, 10))
        
        ttk.Button(history_buttons, text="删除", 
                  command=self.delete_from_history).pack(side="left", padx=(0, 10))
        
        ttk.Button(history_buttons, text="清空历史", 
                  command=self.clear_history).pack(side="left")
    
    def create_optimization_tab(self, notebook):
        """创建AI优化选项卡"""
        opt_frame = ttk.Frame(notebook)
        notebook.add(opt_frame, text="AI优化")
        
        # 优化设置
        settings_frame = ttk.LabelFrame(opt_frame, text="优化设置", padding=10)
        settings_frame.pack(fill="x", padx=10, pady=10)
        
        # 优化选项
        options_frame = ttk.Frame(settings_frame)
        options_frame.pack(fill="x", pady=(0, 10))
        
        self.enable_optimization = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="启用AI优化", 
                       variable=self.enable_optimization).pack(anchor="w", pady=2)
        
        self.enable_translation = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="自动翻译", 
                       variable=self.enable_translation).pack(anchor="w", pady=2)
        
        self.enable_enhancement = tk.BooleanVar()
        ttk.Checkbutton(options_frame, text="内容增强", 
                       variable=self.enable_enhancement).pack(anchor="w", pady=2)
        
        # 优化预设
        preset_frame = ttk.Frame(settings_frame)
        preset_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Label(preset_frame, text="优化预设:").pack(side="left")
        self.preset_var = tk.StringVar()
        preset_combo = ttk.Combobox(preset_frame, textvariable=self.preset_var, 
                                   values=["高质量", "艺术风格", "摄影效果", "细节增强", "创意风格"])
        preset_combo.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        # 优化按钮
        opt_buttons = ttk.Frame(settings_frame)
        opt_buttons.pack(fill="x", pady=(10, 0))
        
        ttk.Button(opt_buttons, text="优化正面提示词", 
                  command=self.optimize_positive_prompt).pack(side="left", padx=(0, 10))
        
        ttk.Button(opt_buttons, text="优化负面提示词", 
                  command=self.optimize_negative_prompt).pack(side="left", padx=(0, 10))
        
        ttk.Button(opt_buttons, text="一键优化", 
                  command=self.optimize_all_prompts).pack(side="left")
        
        # 优化结果预览
        result_frame = ttk.LabelFrame(opt_frame, text="优化结果", padding=10)
        result_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.optimization_result = tk.Text(result_frame, height=10, wrap="word", 
                                          font=("Consolas", 9), state="disabled")
        self.optimization_result.pack(fill="both", expand=True)
    
    def load_default_templates(self):
        """加载默认模板"""
        # 模板已通过self.template_categories初始化
        pass
    
    def on_category_select(self, event):
        """分类选择事件"""
        selection = self.category_listbox.curselection()
        if selection:
            category = self.category_listbox.get(selection[0])
            self.refresh_template_list(category)
    
    def refresh_template_list(self, category):
        """刷新模板列表"""
        self.template_listbox.delete(0, tk.END)
        
        if category in self.template_categories:
            templates = self.template_categories[category]
            for template_name in templates.keys():
                self.template_listbox.insert(tk.END, template_name)
    
    def on_template_search(self, *args):
        """模板搜索事件"""
        search_text = self.template_search_var.get().lower()
        
        # 清空列表
        self.template_listbox.delete(0, tk.END)
        
        # 搜索所有模板
        for category, templates in self.template_categories.items():
            for template_name, template_content in templates.items():
                if (search_text in template_name.lower() or 
                    search_text in template_content.lower()):
                    self.template_listbox.insert(tk.END, f"[{category}] {template_name}")
    
    def on_template_select(self, event):
        """模板选择事件"""
        selection = self.template_listbox.curselection()
        if selection:
            template_text = self.template_listbox.get(selection[0])
            
            # 解析分类和模板名
            if template_text.startswith("["):
                category_end = template_text.find("] ")
                if category_end != -1:
                    category = template_text[1:category_end]
                    template_name = template_text[category_end+2:]
                    
                    if category in self.template_categories:
                        templates = self.template_categories[category]
                        if template_name in templates:
                            template_content = templates[template_name]
                            self.show_template_preview(template_name, template_content)
    
    def show_template_preview(self, name, content):
        """显示模板预览"""
        self.template_preview.config(state="normal")
        self.template_preview.delete("1.0", "end")
        
        preview_text = f"模板名称: {name}\n\n"
        preview_text += f"内容:\n{content}\n\n"
        preview_text += f"变量说明:\n"
        preview_text += "[subject] - 主体对象\n"
        preview_text += "[scenery_type] - 风景类型\n"
        preview_text += "[character_style] - 角色风格\n"
        
        self.template_preview.insert("1.0", preview_text)
        self.template_preview.config(state="disabled")
    
    def use_selected_template(self):
        """使用选中的模板"""
        selection = self.template_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择模板")
            return
        
        template_text = self.template_listbox.get(selection[0])
        
        # 解析并应用模板
        if template_text.startswith("["):
            category_end = template_text.find("] ")
            if category_end != -1:
                category = template_text[1:category_end]
                template_name = template_text[category_end+2:]
                
                if category in self.template_categories:
                    templates = self.template_categories[category]
                    if template_name in templates:
                        template_content = templates[template_name]
                        self.apply_template(template_content)
    
    def apply_template(self, template_content):
        """应用模板"""
        # 简单的变量替换对话框
        variables = re.findall(r'\[(\w+)\]', template_content)
        
        if variables:
            # 创建变量替换对话框
            dialog = tk.Toplevel(self.parent_frame)
            dialog.title("替换变量")
            dialog.geometry("400x300")
            dialog.transient(self.parent_frame)
            dialog.grab_set()
            
            ttk.Label(dialog, text="请输入变量值:", font=("微软雅黑", 10, "bold")).pack(pady=10)
            
            entries = {}
            for var in variables:
                frame = ttk.Frame(dialog)
                frame.pack(fill="x", padx=20, pady=5)
                
                ttk.Label(frame, text=f"{var}:").pack(side="left")
                entry = ttk.Entry(frame)
                entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
                entries[var] = entry
            
            def apply_replacement():
                try:
                    result = template_content
                    for var, entry in entries.items():
                        result = result.replace(f"[{var}]", entry.get())
                    
                    self.positive_text.delete("1.0", "end")
                    self.positive_text.insert("1.0", result)
                    
                    dialog.destroy()
                except Exception as e:
                    messagebox.showerror("错误", f"应用模板失败: {e}")
            
            button_frame = ttk.Frame(dialog)
            button_frame.pack(pady=20)
            
            ttk.Button(button_frame, text="确定", command=apply_replacement).pack(side="left", padx=(0, 10))
            ttk.Button(button_frame, text="取消", command=dialog.destroy).pack(side="left")
        
        else:
            # 没有变量，直接应用
            self.positive_text.delete("1.0", "end")
            self.positive_text.insert("1.0", template_content)
    
    def apply_template_to_positive(self):
        """应用模板到正面提示词"""
        self.use_selected_template()
    
    def load_negative_template(self):
        """加载负面提示词模板"""
        # 创建选择对话框
        dialog = tk.Toplevel(self.parent_frame)
        dialog.title("选择负面提示词模板")
        dialog.geometry("400x300")
        dialog.transient(self.parent_frame)
        dialog.grab_set()
        
        ttk.Label(dialog, text="选择负面提示词模板:", font=("微软雅黑", 10, "bold")).pack(pady=10)
        
        # 模板选择列表
        listbox = tk.Listbox(dialog, height=8)
        listbox.pack(fill="both", expand=True, padx=20, pady=10)
        
        for template_name in self.negative_prompt_templates.keys():
            listbox.insert(tk.END, template_name)
        
        def apply_negative_template():
            selection = listbox.curselection()
            if selection:
                template_name = listbox.get(selection[0])
                if template_name in self.negative_prompt_templates:
                    template_content = self.negative_prompt_templates[template_name]
                    self.negative_text.delete("1.0", "end")
                    self.negative_text.insert("1.0", template_content)
            
            dialog.destroy()
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)
        
        ttk.Button(button_frame, text="确定", command=apply_negative_template).pack(side="left", padx=(0, 10))
        ttk.Button(button_frame, text="取消", command=dialog.destroy).pack(side="left")
    
    def copy_positive_prompt(self):
        """复制正面提示词"""
        content = self.positive_text.get("1.0", "end-1c")
        self.parent_frame.clipboard_clear()
        self.parent_frame.clipboard_append(content)
        messagebox.showinfo("成功", "正面提示词已复制到剪贴板")
    
    def copy_negative_prompt(self):
        """复制负面提示词"""
        content = self.negative_text.get("1.0", "end-1c")
        self.parent_frame.clipboard_clear()
        self.parent_frame.clipboard_append(content)
        messagebox.showinfo("成功", "负面提示词已复制到剪贴板")
    
    def save_to_history(self):
        """保存到历史记录"""
        positive = self.positive_text.get("1.0", "end-1c").strip()
        negative = self.negative_text.get("1.0", "end-1c").strip()
        
        if not positive and not negative:
            messagebox.showwarning("警告", "提示词为空，无法保存")
            return
        
        history_item = {
            "id": len(self.prompt_history) + 1,
            "positive": positive,
            "negative": negative,
            "timestamp": str(tk.datetime.now()),
            "length": len(positive) + len(negative)
        }
        
        self.prompt_history.append(history_item)
        self.refresh_history_list()
        
        messagebox.showinfo("成功", "提示词已保存到历史记录")
    
    def refresh_history_list(self):
        """刷新历史记录列表"""
        self.history_listbox.delete(0, tk.END)
        
        for item in reversed(self.prompt_history):  # 最新的在前面
            display_text = f"#{item['id']} ({item['length']}字符) - {item['timestamp']}"
            self.history_listbox.insert(tk.END, display_text)
    
    def on_history_select(self, event):
        """历史记录选择事件"""
        selection = self.history_listbox.curselection()
        if selection:
            index = len(self.prompt_history) - 1 - selection[0]  # 反向索引
            if 0 <= index < len(self.prompt_history):
                history_item = self.prompt_history[index]
                
                # 在新的选项卡中显示详细内容
                self.show_history_detail(history_item)
    
    def show_history_detail(self, history_item):
        """显示历史记录详情"""
        dialog = tk.Toplevel(self.parent_frame)
        dialog.title(f"历史记录 #{history_item['id']}")
        dialog.geometry("600x400")
        dialog.transient(self.parent_frame)
        dialog.grab_set()
        
        # 创建选项卡
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 正面提示词选项卡
        positive_frame = ttk.Frame(notebook)
        notebook.add(positive_frame, text="正面提示词")
        
        positive_text = tk.Text(positive_frame, wrap="word", font=("Consolas", 10))
        positive_text.pack(fill="both", expand=True, padx=10, pady=10)
        positive_text.insert("1.0", history_item["positive"])
        positive_text.config(state="disabled")
        
        # 负面提示词选项卡
        negative_frame = ttk.Frame(notebook)
        notebook.add(negative_frame, text="负面提示词")
        
        negative_text = tk.Text(negative_frame, wrap="word", font=("Consolas", 10))
        negative_text.pack(fill="both", expand=True, padx=10, pady=10)
        negative_text.insert("1.0", history_item["negative"])
        negative_text.config(state="disabled")
    
    def restore_from_history(self):
        """从历史记录恢复"""
        selection = self.history_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择历史记录")
            return
        
        index = len(self.prompt_history) - 1 - selection[0]
        if 0 <= index < len(self.prompt_history):
            history_item = self.prompt_history[index]
            
            self.positive_text.delete("1.0", "end")
            self.positive_text.insert("1.0", history_item["positive"])
            
            self.negative_text.delete("1.0", "end")
            self.negative_text.insert("1.0", history_item["negative"])
            
            messagebox.showinfo("成功", "已从历史记录恢复提示词")
    
    def delete_from_history(self):
        """删除历史记录"""
        selection = self.history_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择历史记录")
            return
        
        index = len(self.prompt_history) - 1 - selection[0]
        if 0 <= index < len(self.prompt_history):
            self.prompt_history.pop(index)
            self.refresh_history_list()
            messagebox.showinfo("成功", "历史记录已删除")
    
    def clear_history(self):
        """清空历史记录"""
        if messagebox.askyesno("确认", "确定要清空所有历史记录吗？"):
            self.prompt_history.clear()
            self.refresh_history_list()
            messagebox.showinfo("成功", "历史记录已清空")
    
    def optimize_positive_prompt(self):
        """优化正面提示词"""
        content = self.positive_text.get("1.0", "end-1c")
        
        # 应用优化映射
        optimized = content
        for keyword, enhancement in self.optimization_mappings.items():
            if keyword in optimized:
                optimized = optimized.replace(keyword, enhancement)
        
        # 应用预设
        preset = self.preset_var.get()
        if preset == "高质量":
            optimized += ", masterpiece, best quality, ultra detailed"
        elif preset == "艺术风格":
            optimized += ", artistic style, fine art, gallery quality"
        elif preset == "摄影效果":
            optimized += ", professional photography, studio lighting, high resolution"
        elif preset == "细节增强":
            optimized += ", intricate details, sharp focus, crisp details"
        elif preset == "创意风格":
            optimized += ", creative composition, innovative design, unique style"
        
        # 更新提示词
        self.positive_text.delete("1.0", "end")
        self.positive_text.insert("1.0", optimized)
        
        # 显示优化结果
        self.show_optimization_result("正面提示词优化", content, optimized)
    
    def optimize_negative_prompt(self):
        """优化负面提示词"""
        content = self.negative_text.get("1.0", "end-1c")
        
        # 应用优化映射
        optimized = content
        for keyword, enhancement in self.optimization_mappings.items():
            if keyword in optimized:
                optimized = optimized.replace(keyword, enhancement)
        
        # 添加通用负面提示词
        if not optimized:
            optimized = self.negative_prompt_templates["通用负面"]
        else:
            optimized += ", " + self.negative_prompt_templates["通用负面"]
        
        # 更新提示词
        self.negative_text.delete("1.0", "end")
        self.negative_text.insert("1.0", optimized)
        
        # 显示优化结果
        self.show_optimization_result("负面提示词优化", content, optimized)
    
    def optimize_all_prompts(self):
        """一键优化所有提示词"""
        self.optimize_positive_prompt()
        self.optimize_negative_prompt()
        messagebox.showinfo("成功", "所有提示词已优化完成")
    
    def show_optimization_result(self, title, original, optimized):
        """显示优化结果"""
        self.optimization_result.config(state="normal")
        self.optimization_result.delete("1.0", "end")
        
        result_text = f"{title}结果:\n\n"
        result_text += f"原文:\n{original}\n\n"
        result_text += f"优化后:\n{optimized}\n\n"
        result_text += f"改进说明:\n"
        result_text += f"- 字符数: {len(original)} → {len(optimized)}\n"
        result_text += f"- 优化效果: {'提升' if len(optimized) > len(original) else '保持'}\n"
        
        self.optimization_result.insert("1.0", result_text)
        self.optimization_result.config(state="disabled")
    
    def apply_current_prompt(self):
        """应用到当前"""
        positive = self.positive_text.get("1.0", "end-1c").strip()
        negative = self.negative_text.get("1.0", "end-1c").strip()
        
        self.current_prompt = positive
        self.current_negative_prompt = negative
        
        if self.callback:
            self.callback("prompt_updated", {
                "positive": positive,
                "negative": negative
            })
        
        messagebox.showinfo("成功", "提示词已应用到当前")
    
    def edit_template(self):
        """编辑模板"""
        messagebox.showinfo("提示", "模板编辑功能将在后续版本中实现")
    
    def new_template(self):
        """新建模板"""
        messagebox.showinfo("提示", "新建模板功能将在后续版本中实现")
    
    def import_batch_file(self):
        """从文件导入批量提示词"""
        file_path = filedialog.askopenfilename(
            title="选择提示词文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 清空批量列表
                for item in self.batch_tree.get_children():
                    self.batch_tree.delete(item)
                
                # 添加批量提示词
                for i, line in enumerate(lines, 1):
                    prompt = line.strip()
                    if prompt:
                        self.batch_tree.insert("", "end", values=(i, prompt, "待处理"))
                
                messagebox.showinfo("成功", f"已导入 {len(lines)} 条提示词")
                
            except Exception as e:
                messagebox.showerror("错误", f"导入文件失败: {e}")
    
    def generate_batch_from_template(self):
        """从模板生成批量提示词"""
        messagebox.showinfo("提示", "批量生成功能将在后续版本中实现")
    
    def add_batch_to_current(self):
        """将批量提示词添加到当前"""
        # 这里可以实现将批量提示词逐个应用到当前的功能
        messagebox.showinfo("提示", "批量应用功能将在后续版本中实现")
    
    def clear_batch_list(self):
        """清空批量列表"""
        for item in self.batch_tree.get_children():
            self.batch_tree.delete(item)
        messagebox.showinfo("成功", "批量列表已清空")
    
    def export_batch_list(self):
        """导出批量列表"""
        file_path = filedialog.asksaveasfilename(
            title="保存批量提示词",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        
        if file_path:
            try:
                prompts = []
                for item in self.batch_tree.get_children():
                    values = self.batch_tree.item(item)["values"]
                    if len(values) >= 2:
                        prompts.append(values[1])  # 提示词列
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    for prompt in prompts:
                        f.write(prompt + '\n')
                
                messagebox.showinfo("成功", f"已导出 {len(prompts)} 条提示词")
                
            except Exception as e:
                messagebox.showerror("错误", f"导出文件失败: {e}")
    
    def get_current_prompts(self):
        """获取当前提示词"""
        return {
            "positive": self.positive_text.get("1.0", "end-1c").strip(),
            "negative": self.negative_text.get("1.0", "end-1c").strip()
        }
    
    def set_prompts(self, positive="", negative=""):
        """设置提示词"""
        self.positive_text.delete("1.0", "end")
        if positive:
            self.positive_text.insert("1.0", positive)
        
        self.negative_text.delete("1.0", "end")
        if negative:
            self.negative_text.insert("1.0", negative)
    
    def on_history_search(self, *args):
        """历史记录搜索处理"""
        search_text = self.history_search_var.get().lower()
        # 这里可以添加搜索逻辑
        # 目前只是打印搜索文本
        print(f"搜索历史记录: {search_text}")
        
        # 实际的搜索实现
        self.history_listbox.delete(0, tk.END)
        
        if not search_text:
            # 如果没有搜索文本，显示所有历史记录
            self.refresh_history_list()
        else:
            # 搜索匹配的历史记录
            for item in reversed(self.prompt_history):  # 最新的在前面
                display_text = f"#{item['id']} ({item['length']}字符) - {item['timestamp']}"
                if (search_text in item['positive'].lower() or 
                    search_text in item['negative'].lower() or
                    search_text in display_text.lower()):
                    self.history_listbox.insert(tk.END, display_text)