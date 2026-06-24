#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
General AIGC Enhanced 增强启动脚本
"""

import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def main():
    print("🎯 General AIGC Enhanced 启动中...")
    print("=" * 60)
    
    # 初始化所有管理器
    try:
        from backend_modules.smart_venv_manager import get_smart_venv_manager
        venv_manager = get_smart_venv_manager()
        print("✅ 虚拟环境管理器初始化成功")
    except Exception as e:
        print(f"⚠️ 虚拟环境管理器初始化失败: {e}")
    
    try:
        from backend_modules.comprehensive_feature_manager import get_comprehensive_feature_manager
        feature_manager = get_comprehensive_feature_manager()
        print("✅ 功能管理器初始化成功")
    except Exception as e:
        print(f"⚠️ 功能管理器初始化失败: {e}")
    
    try:
        from backend_modules.enhanced_ui_manager import get_enhanced_ui_manager
        ui_manager = get_enhanced_ui_manager()
        print("✅ UI管理器初始化成功")
    except Exception as e:
        print(f"⚠️ UI管理器初始化失败: {e}")
    
    try:
        from backend_modules.comfyui_webui_integration import ComfyUIWebUIIntegration
        integration = ComfyUIWebUIIntegration()
        print("✅ ComfyUI/WebUI集成初始化成功")
    except Exception as e:
        print(f"⚠️ ComfyUI/WebUI集成初始化失败: {e}")
    
    print("\n🔧 启动主应用程序...")
    
    # 导入并启动主程序
    try:
        import main
        main.main()
    except Exception as e:
        print(f"❌ 主程序启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
