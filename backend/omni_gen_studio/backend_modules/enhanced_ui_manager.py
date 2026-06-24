#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增强版UI管理器
实现符合要求的现代化界面设计
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Any, Optional
import json
from pathlib import Path

class EnhancedUIManager:
    """增强版UI管理器"""
    
    def __init__(self):
        """初始化UI管理器"""
        self.main_window = None
        self.current_module = "image-gen"
        self.modules = {
            "image-gen": {"name": "图像生成", "color": "#4CAF50"},
            "image-edit": {"name": "图像编辑", "color": "#2196F3"}, 
            "video-gen": {"name": "视频生成", "color": "#FF9800"},
            "3d-gen": {"name": "3D生成", "color": "#9C27B0"}
        }
        self.module_frames = {}
        
    def create_main_window(self):
        """创建主窗口"""
        if self.main_window:
            return self.main_window
            
        # 创建主窗口
        self.main_window = tk.Tk()
        self.main_window.title("General AIGC Enhanced - 本地化AI生成工具")
        self.main_window.geometry("1600x1000")
        self.main_window.configure(bg='#2E2E2E')
        
        # 设置窗口图标（如果有）
        try:
            # self.main_window.iconbitmap("assets/icon.ico")
            pass
        except:
            pass
        
        # 创建界面布局
        self._create_header()
        self._create_module_buttons()
        self._create_main_content()
        self._create_sidebar()
        self._create_status_bar()
        
        return self.main_window
    
    def _create_header(self):
        """创建顶部标题区域"""
        header_frame = tk.Frame(self.main_window, bg='#1E1E1E', height=80)
        header_frame.pack(fill='x', padx=10, pady=(10, 5))
        header_frame.pack_propagate(False)
        
        # 主标题
        title_label = tk.Label(
            header_frame,
            text="General AIGC Enhanced",
            font=('Microsoft YaHei', 24, 'bold'),
            fg='#FFFFFF',
            bg='#1E1E1E'
        )
        title_label.pack(side='left', padx=20, pady=20)
        
        # 副标题
        subtitle_label = tk.Label(
            header_frame,
            text="本地化AI生成工具 - 支持图像、视频、3D生成",
            font=('Microsoft YaHei', 12),
            fg='#CCCCCC',
            bg='#1E1E1E'
        )
        subtitle_label.pack(side='left', padx=(10, 0), pady=25)
        
        # 系统状态指示器
        status_frame = tk.Frame(header_frame, bg='#1E1E1E')
        status_frame.pack(side='right', padx=20, pady=20)
        
        # GPU状态
        gpu_label = tk.Label(
            status_frame,
            text="🟢 RTX4090",
            font=('Microsoft YaHei', 10),
            fg='#4CAF50',
            bg='#1E1E1E'
        )
        gpu_label.pack(anchor='e')
        
        # 显存状态
        memory_label = tk.Label(
            status_frame,
            text="📊 48GB",
            font=('Microsoft YaHei', 10),
            fg='#4CAF50',
            bg='#1E1E1E'
        )
        memory_label.pack(anchor='e')
    
    def _create_module_buttons(self):
        """创建模块切换按钮（顶部）"""
        # 模块按钮容器
        button_frame = tk.Frame(self.main_window, bg='#3E3E3E', height=60)
        button_frame.pack(fill='x', padx=10, pady=(0, 5))
        button_frame.pack_propagate(False)
        
        # 创建四个模块按钮
        for i, (module_id, module_info) in enumerate(self.modules.items()):
            button = tk.Button(
                button_frame,
                text=module_info['name'],
                command=lambda m=module_id: self.switch_module(m),
                bg=module_info['color'],
                fg='white',
                font=('Microsoft YaHei', 12, 'bold'),
                relief='flat',
                bd=0,
                padx=20,
                pady=10,
                cursor='hand2'
            )
            button.pack(side='left', padx=5, pady=10)
            
            # 保存按钮引用用于状态更新
            self.module_buttons[module_id] = button
        
        # 初始化按钮状态
        self._update_module_buttons()
    
    def _create_main_content(self):
        """创建主内容区域"""
        # 主内容容器
        content_frame = tk.Frame(self.main_window, bg='#2E2E2E')
        content_frame.pack(fill='both', expand=True, padx=10, pady=(0, 5))
        
        # 左侧参数面板 (30%)
        self._create_parameter_panel(content_frame)
        
        # 中央预览区域 (40%)
        self._create_preview_panel(content_frame)
        
        # 右侧文件管理面板 (30%)
        self._create_file_panel(content_frame)
    
    def _create_parameter_panel(self, parent):
        """创建左侧参数面板"""
        param_frame = tk.Frame(parent, bg='#3E3E3E', width=480)
        param_frame.pack(side='left', fill='both', expand=False, padx=(0, 5))
        param_frame.pack_propagate(False)
        
        # 参数面板标题
        param_title = tk.Label(
            param_frame,
            text="📝 参数设置",
            font=('Microsoft YaHei', 14, 'bold'),
            fg='#FFFFFF',
            bg='#3E3E3E'
        )
        param_title.pack(anchor='w', padx=15, pady=15)
        
        # 参数设置区域
        self.param_notebook = ttk.Notebook(param_frame)
        self.param_notebook.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        # 为每个模块创建参数选项卡
        self._create_module_parameters()
    
    def _create_preview_panel(self, parent):
        """创建中央预览面板"""
        preview_frame = tk.Frame(parent, bg='#2E2E2E')
        preview_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        # 预览标题
        preview_title = tk.Label(
            preview_frame,
            text="🖼️ 预览区域",
            font=('Microsoft YaHei', 14, 'bold'),
            fg='#FFFFFF',
            bg='#2E2E2E'
        )
        preview_title.pack(anchor='w', padx=15, pady=15)
        
        # 预览画布区域
        self.preview_canvas = tk.Canvas(
            preview_frame,
            bg='#1E1E1E',
            highlightthickness=0
        )
        self.preview_canvas.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            preview_frame,
            variable=self.progress_var,
            length=300
        )
        self.progress_bar.pack(pady=5)
    
    def _create_file_panel(self, parent):
        """创建右侧文件管理面板"""
        file_frame = tk.Frame(parent, bg='#3E3E3E', width=480)
        file_frame.pack(side='right', fill='both', expand=False, padx=(5, 0))
        file_frame.pack_propagate(False)
        
        # 文件面板标题
        file_title = tk.Label(
            file_frame,
            text="📁 文件管理",
            font=('Microsoft YaHei', 14, 'bold'),
            fg='#FFFFFF',
            bg='#3E3E3E'
        )
        file_title.pack(anchor='w', padx=15, pady=15)
        
        # 文件列表
        self.file_listbox = tk.Listbox(
            file_frame,
            bg='#2E2E2E',
            fg='#FFFFFF',
            selectbackground='#4CAF50',
            font=('Microsoft YaHei', 10)
        )
        self.file_listbox.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        # 文件操作按钮
        button_frame = tk.Frame(file_frame, bg='#3E3E3E')
        button_frame.pack(fill='x', padx=10, pady=(0, 10))
        
        tk.Button(
            button_frame,
            text="上传",
            command=self.upload_file,
            bg='#4CAF50',
            fg='white',
            relief='flat',
            bd=0
        ).pack(side='left', padx=2, pady=2)
        
        tk.Button(
            button_frame,
            text="删除",
            command=self.delete_file,
            bg='#F44336',
            fg='white',
            relief='flat',
            bd=0
        ).pack(side='left', padx=2, pady=2)
        
        tk.Button(
            button_frame,
            text="打开",
            command=self.open_file,
            bg='#2196F3',
            fg='white',
            relief='flat',
            bd=0
        ).pack(side='left', padx=2, pady=2)
    
    def _create_status_bar(self):
        """创建状态栏"""
        status_frame = tk.Frame(self.main_window, bg='#1E1E1E', height=30)
        status_frame.pack(fill='x', side='bottom')
        status_frame.pack_propagate(False)
        
        # 左侧状态
        self.status_label = tk.Label(
            status_frame,
            text="就绪",
            font=('Microsoft YaHei', 9),
            fg='#CCCCCC',
            bg='#1E1E1E',
            anchor='w'
        )
        self.status_label.pack(side='left', padx=10, pady=5, fill='x', expand=True)
        
        # 右侧状态
        self.right_status_label = tk.Label(
            status_frame,
            text="GPU: NVIDIA RTX4090 | 显存: 48GB",
            font=('Microsoft YaHei', 9),
            fg='#CCCCCC',
            bg='#1E1E1E',
            anchor='e'
        )
        self.right_status_label.pack(side='right', padx=10, pady=5)
    
    def _create_module_parameters(self):
        """为每个模块创建参数设置"""
        # 图像生成参数
        image_frame = tk.Frame(self.param_notebook, bg='#3E3E3E')
        self.param_notebook.add(image_frame, text="图像生成")
        
        # 提示词输入
        prompt_label = tk.Label(
            image_frame,
            text="提示词:",
            font=('Microsoft YaHei', 10),
            fg='#FFFFFF',
            bg='#3E3E3E'
        )
        prompt_label.pack(anchor='w', padx=10, pady=(10, 5))
        
        self.prompt_entry = tk.Text(
            image_frame,
            height=3,
            bg='#2E2E2E',
            fg='#FFFFFF',
            font=('Microsoft YaHei', 10),
            wrap='word'
        )
        self.prompt_entry.pack(fill='x', padx=10, pady=(0, 10))
        
        # 负面提示词
        neg_prompt_label = tk.Label(
            image_frame,
            text="负面提示词:",
            font=('Microsoft YaHei', 10),
            fg='#FFFFFF',
            bg='#3E3E3E'
        )
        neg_prompt_label.pack(anchor='w', padx=10, pady=(0, 5))
        
        self.neg_prompt_entry = tk.Text(
            image_frame,
            height=2,
            bg='#2E2E2E',
            fg='#FFFFFF',
            font=('Microsoft YaHei', 10),
            wrap='word'
        )
        self.neg_prompt_entry.pack(fill='x', padx=10, pady=(0, 10))
        
        # 模型选择
        model_label = tk.Label(
            image_frame,
            text="模型选择:",
            font=('Microsoft YaHei', 10),
            fg='#FFFFFF',
            bg='#3E3E3E'
        )
        model_label.pack(anchor='w', padx=10, pady=(0, 5))
        
        self.model_combo = ttk.Combobox(
            image_frame,
            values=["SDXL", "SD1.5", "Flux", "SD3"],
            state="readonly"
        )
        self.model_combo.pack(fill='x', padx=10, pady=(0, 10))
        self.model_combo.set("SDXL")
        
        # 其他参数...
        # 这里可以添加更多的参数控件
        
        # 图像编辑参数
        edit_frame = tk.Frame(self.param_notebook, bg='#3E3E3E')
        self.param_notebook.add(edit_frame, text="图像编辑")
        
        # 视频生成参数
        video_frame = tk.Frame(self.param_notebook, bg='#3E3E3E')
        self.param_notebook.add(video_frame, text="视频生成")
        
        # 3D生成参数
        threed_frame = tk.Frame(self.param_notebook, bg='#3E3E3E')
        self.param_notebook.add(threed_frame, text="3D生成")
    
    def switch_module(self, module_id: str):
        """切换模块"""
        if module_id not in self.modules:
            return
            
        self.current_module = module_id
        self._update_module_buttons()
        
        # 更新参数面板
        module_names = {
            "image-gen": 0,
            "image-edit": 1, 
            "video-gen": 2,
            "3d-gen": 3
        }
        
        if module_id in module_names:
            self.param_notebook.select(module_names[module_id])
        
        # 更新状态栏
        self.status_label.config(text=f"当前模块: {self.modules[module_id]['name']}")
        
        print(f"切换到模块: {self.modules[module_id]['name']}")
    
    def _update_module_buttons(self):
        """更新模块按钮状态"""
        for module_id, button in getattr(self, 'module_buttons', {}).items():
            if module_id == self.current_module:
                # 当前模块按钮 - 高亮
                button.configure(relief='sunken', bg='#2E7D32')
            else:
                # 其他模块按钮 - 正常
                button.configure(relief='flat', bg=self.modules[module_id]['color'])
    
    def update_status(self, message: str):
        """更新状态栏消息"""
        self.status_label.config(text=message)
        self.main_window.update_idletasks()
    
    def show_progress(self, value: float, message: str = ""):
        """显示进度"""
        self.progress_var.set(value)
        if message:
            self.status_label.config(text=message)
    
    def upload_file(self):
        """上传文件"""
        from tkinter import filedialog
        filename = filedialog.askopenfilename(
            title="选择文件",
            filetypes=[
                ("图像文件", "*.png *.jpg *.jpeg"),
                ("视频文件", "*.mp4 *.avi *.mov"),
                ("所有文件", "*.*")
            ]
        )
        if filename:
            self.file_listbox.insert(0, Path(filename).name)
            self.status_label.config(text=f"已上传: {Path(filename).name}")
    
    def delete_file(self):
        """删除选中文件"""
        selection = self.file_listbox.curselection()
        if selection:
            self.file_listbox.delete(selection[0])
    
    def open_file(self):
        """打开选中文件"""
        selection = self.file_listbox.curselection()
        if selection:
            filename = self.file_listbox.get(selection[0])
            import subprocess
            import platform
            
            try:
                if platform.system() == "Windows":
                    subprocess.run(["start", filename], shell=True)
                elif platform.system() == "Darwin":  # macOS
                    subprocess.run(["open", filename])
                else:  # Linux
                    subprocess.run(["xdg-open", filename])
            except:
                pass
    
    def run(self):
        """运行UI"""
        self.create_main_window()
        self.main_window.mainloop()

# 初始化UI管理器
_enhanced_ui_manager = None

def get_enhanced_ui_manager() -> EnhancedUIManager:
    """获取增强版UI管理器实例"""
    global _enhanced_ui_manager
    if _enhanced_ui_manager is None:
        _enhanced_ui_manager = EnhancedUIManager()
    return _enhanced_ui_manager

if __name__ == "__main__":
    # 测试UI
    manager = get_enhanced_ui_manager()
    manager.run()
