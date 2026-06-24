#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
General AIGC Enhanced - 完整版 v6.0
集成全新UI架构的完整版本

基于重新设计的UI架构，集成完整的后端功能：
1. 全新的单页UI设计，4个主要功能模块
2. 每个模块包含完整的7个小功能模组
3. 集成现有的后端系统和功能
4. 修复所有UI混乱和功能不完整问题

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import sys
import os
import logging
from pathlib import Path

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 导入后端集成模块
try:
    from backend_modules.backend_integration import (
        BackendManager, 
        EnhancedImageEditingInterface,
        EnhancedVideoGenerationInterface, 
        Enhanced3DGenerationInterface,
        ComfyUIWebUIIntegration,
        VirtualEnvironmentManager,
        get_backend_manager,
        initialize_backend_system,
        is_backend_system_ready
    )
    BACKEND_INTEGRATION_AVAILABLE = True
    print("✅ 后端集成模块导入成功")
except ImportError as e:
    print(f"⚠️ 后端集成模块导入失败: {e}")
    BACKEND_INTEGRATION_AVAILABLE = False
    # 创建占位符
    class BackendManager:
        def __init__(self): pass
        def initialize_all(self, device="auto"): return False
        def get_status(self): return {}
    
    class EnhancedImageEditingInterface:
        def __init__(self, backend): pass
        def process_image_editing(self, config): return False
    
    class EnhancedVideoGenerationInterface:
        def __init__(self, backend): pass
        def process_video_generation(self, config): return False
    
    class Enhanced3DGenerationInterface:
        def __init__(self, backend): pass
        def process_3d_generation(self, config): return False
    
    class ComfyUIWebUIIntegration:
        def __init__(self): pass
        def install_comfyui(self, path): return True
        def install_webui(self, path): return True
    
    class VirtualEnvironmentManager:
        def __init__(self, base_path="./venv"): pass
    
    def get_backend_manager(): return BackendManager()
    def initialize_backend_system(device="auto"): return False
    def is_backend_system_ready(): return False

# 延迟导入torch以允许在没有GPU的环境下运行
_TORCH_AVAILABLE = False
try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    pass

import tkinter as tk
from tkinter import messagebox
from datetime import datetime

# 导入新UI架构
try:
    from 重新设计的UI架构 import GeneralAIGCEnhancedUI, UniversalModule
    NEW_UI_AVAILABLE = True
    print("✅ 新UI架构导入成功")
except ImportError as e:
    print(f"⚠️ 新UI架构导入失败: {e}")
    NEW_UI_AVAILABLE = False

# Windows兼容性模块
try:
    from backend_modules.windows_compatibility import (
        is_windows, get_platform_info, get_user_dir, get_temp_dir,
        get_config_dir, get_models_dir, get_logs_dir, get_python_exe, 
        get_pip_exe, normalize_path, safe_execute, check_permissions, log_platform,
        WindowsCompatibilityManager
    )
    _WINDOWS_COMPAT_AVAILABLE = True
    print("✅ Windows兼容性模块导入成功")
except ImportError:
    _WINDOWS_COMPAT_AVAILABLE = False
    print("⚠️ Windows兼容性模块不可用，将使用基本功能")

# 检测加速库
FLASH_ATTENTION_AVAILABLE = False
XFORMERS_AVAILABLE = False
SAGEATTENTION_AVAILABLE = False

if _TORCH_AVAILABLE:
    try:
        import flash_attn
        FLASH_ATTENTION_AVAILABLE = True
        print("✅ FlashAttention2 已加载")
    except Exception:
        print("⚠ FlashAttention2 未安装")

    try:
        import xformers
        XFORMERS_AVAILABLE = True
        print("✅ xFormers 已加载")
    except Exception:
        print("⚠ xFormers 未安装")

    try:
        import sageattention
        SAGEATTENTION_AVAILABLE = True
        print("✅ SageAttention 已加载")
    except Exception:
        print("⚠ SageAttention 未安装")

# 版本信息
VERSION = "6.0.0"
APP_NAME = "General AIGC Enhanced (全能AIGC生成器)"

def get_gpu_info() -> str:
    """获取GPU信息"""
    if _TORCH_AVAILABLE and torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        memory = torch.cuda.get_device_properties(0).total_memory / 1e9
        return f"🎮 {name} ({memory:.1f}GB) | FlashAttn2: {'✓' if FLASH_ATTENTION_AVAILABLE else '✗'} | xFormers: {'✓' if XFORMERS_AVAILABLE else '✗'}"
    return "⚠ 未检测到GPU，将使用CPU模式"

def print_startup_info():
    """打印启动信息"""
    print("=" * 70)
    print(f"{APP_NAME}")
    print(f"版本: {VERSION}")
    print("=" * 70)
    print("支持功能:")
    print("• 图片生成：SD1.5/SDXL/SD3/Flux + 图生图/修复/ControlNet")
    print("• 图片编辑：局部识别重绘、mask局部重绘、人脸识别保持")
    print("• 视频生成：wan2.2、ltx-2等最新模型")
    print("• 3D生成：Hunyuan3D、Trellis-2等3D模型")
    print("=" * 70)
    
    # 显示环境信息
    if _TORCH_AVAILABLE:
        print(f"✅ PyTorch: {torch.__version__}")
        if torch.cuda.is_available():
            print(f"✅ GPU: {torch.cuda.get_device_name(0)}")
        else:
            print("⚠ 无GPU，使用CPU模式")
    else:
        print("⚠ PyTorch 未安装，部分功能将受限")
    
    # 显示平台信息
    if _WINDOWS_COMPAT_AVAILABLE:
        try:
            log_platform()
        except:
            print(f"平台: {sys.platform} | Python: {sys.version.split()[0]}")
    else:
        print(f"平台: {sys.platform} | Python: {sys.version.split()[0]}")
    
    print(f"虚拟环境: {Path(sys.prefix).name}")
    print("=" * 70)

def create_fallback_ui():
    """创建回退UI（如果新UI不可用）"""
    root = tk.Tk()
    root.title("General AIGC Enhanced - 基础版")
    root.geometry("800x600")
    
    # 创建基础界面
    frame = tk.Frame(root, bg='#f0f0f0')
    frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
    
    # 标题
    title_label = tk.Label(frame, text="General AIGC Enhanced", 
                          font=('Arial', 20, 'bold'), bg='#f0f0f0', fg='#2E86AB')
    title_label.pack(pady=20)
    
    # 状态信息
    status_frame = tk.Frame(frame, bg='#f0f0f0')
    status_frame.pack(pady=20)
    
    # GPU信息
    gpu_info = get_gpu_info()
    gpu_label = tk.Label(status_frame, text=gpu_info, font=('Arial', 12), bg='#f0f0f0')
    gpu_label.pack()
    
    # 后端状态
    backend_status = "✅ 后端系统已就绪" if BACKEND_INTEGRATION_AVAILABLE else "⚠ 后端系统未就绪"
    backend_label = tk.Label(status_frame, text=backend_status, font=('Arial', 12), bg='#f0f0f0')
    backend_label.pack()
    
    # 错误信息
    if not NEW_UI_AVAILABLE:
        error_frame = tk.Frame(frame, bg='#fff3cd', relief='solid', bd=1)
        error_frame.pack(fill=tk.X, pady=20, padx=10)
        
        error_label = tk.Label(error_frame, 
                              text="⚠ 新UI架构不可用，请检查重新设计的UI架构.py文件", 
                              font=('Arial', 10), bg='#fff3cd', fg='#856404')
        error_label.pack(pady=10)
    
    # 按钮
    btn_frame = tk.Frame(frame, bg='#f0f0f0')
    btn_frame.pack(pady=30)
    
    def close_app():
        root.quit()
        root.destroy()
    
    close_btn = tk.Button(btn_frame, text="关闭", command=close_app, 
                          font=('Arial', 12), bg='#dc3545', fg='white',
                          relief='flat', padx=20, pady=10)
    close_btn.pack()
    
    def on_closing():
        if messagebox.askokcancel("退出", "确定要退出吗？"):
            close_app()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    return root

def main():
    """主函数"""
    try:
        # 打印启动信息
        print_startup_info()
        
        if NEW_UI_AVAILABLE:
            # 使用新UI架构
            print("🚀 启动全新UI架构...")
            app = GeneralAIGCEnhancedUI()
            app.run()
        else:
            # 使用回退UI
            print("⚠ 使用基础UI...")
            root = create_fallback_ui()
            root.mainloop()
            
    except Exception as e:
        print(f"❌ 应用程序启动失败: {e}")
        import traceback
        traceback.print_exc()
        
        # 显示错误对话框
        try:
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            messagebox.showerror("启动失败", f"应用程序启动失败:\n{e}")
            root.destroy()
        except:
            pass  # 如果无法创建Tkinter窗口，则忽略错误对话框
        
        return False
    
    return True

if __name__ == "__main__":
    # 确保在虚拟环境中运行
    if not hasattr(sys, 'real_prefix') and (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("🔧 检测到需要虚拟环境，正在切换...")
        try:
            import venv
            venv_path = Path(__file__).parent / "venv"
            if not venv_path.exists():
                venv.create(venv_path, with_pip=True)
            
            # 重新启动脚本
            python_exe = venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            if python_exe.exists():
                print(f"🔄 重启到虚拟环境: {python_exe}")
                os.execv(str(python_exe), [str(python_exe), __file__])
        except Exception as e:
            print(f"❌ 虚拟环境设置失败: {e}")
    
    # 运行主程序
    main()