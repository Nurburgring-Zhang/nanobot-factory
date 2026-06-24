#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI架构更新脚本
将新的UI架构集成到现有项目中

作者：MiniMax Agent
版本：v6.0 (2026-02-04)
"""

import os
import shutil
import sys
from pathlib import Path

def backup_original_main():
    """备份原始main.py文件"""
    main_py = Path("main.py")
    backup_py = Path("main.py.backup")
    
    if main_py.exists():
        # 如果备份文件已存在，添加时间戳
        if backup_py.exists():
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_py = Path(f"main.py.backup_{timestamp}")
        
        shutil.copy2(main_py, backup_py)
        print(f"✅ 已备份原始main.py为: {backup_py}")
        return True
    else:
        print("⚠ 未找到原始main.py文件")
        return False

def replace_main_file():
    """替换main.py文件"""
    new_main = Path("main_v6.py")
    old_main = Path("main.py")
    
    if new_main.exists():
        # 如果原始main.py存在，先删除
        if old_main.exists():
            old_main.unlink()
        
        # 重命名新文件为main.py
        new_main.rename(old_main)
        print(f"✅ 已替换main.py文件")
        return True
    else:
        print("❌ 未找到新main.py文件")
        return False

def update_ui_files():
    """更新UI相关文件"""
    # 确保UI架构文件存在
    ui_file = Path("重新设计的UI架构.py")
    if ui_file.exists():
        print("✅ UI架构文件已存在")
        return True
    else:
        print("❌ UI架构文件不存在")
        return False

def test_new_ui():
    """测试新UI是否正常"""
    print("\n🧪 测试新UI架构...")
    
    try:
        # 尝试导入新UI
        sys.path.insert(0, str(Path.cwd()))
        from 重新设计的UI架构 import GeneralAIGCEnhancedUI
        print("✅ 新UI架构导入成功")
        
        # 尝试创建基础UI实例（不显示窗口）
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()  # 隐藏窗口
        
        app = GeneralAIGCEnhancedUI()
        print("✅ 新UI架构初始化成功")
        
        root.destroy()
        return True
        
    except Exception as e:
        print(f"❌ 新UI架构测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def print_update_summary():
    """打印更新摘要"""
    print("\n" + "="*60)
    print("🎉 UI架构更新完成！")
    print("="*60)
    print("\n📋 更新内容:")
    print("• 全新UI架构 - 解决界面混乱问题")
    print("• 单页设计 - 4个主要功能模块")
    print("• 完整7小模组 - 每个模块都包含完整功能")
    print("• 清晰的模块切换 - 解决切换问题")
    print("• 统一的控制面板 - 更好的用户体验")
    print("\n🚀 使用方法:")
    print("• 运行: python main.py")
    print("• 或: python main_v6.py (直接运行新版本)")
    print("\n💡 新功能特点:")
    print("• 图片生成: Z-Image, Qwen-Image, Flux.2等模型")
    print("• 图片编辑: 局部重绘, 风格转换, 人脸保持")
    print("• 视频生成: Wan 2.2, LTX-2等最新模型")
    print("• 3D生成: Hunyuan3D, Trellis-2等3D模型")
    print("• 完整7模组: 模型、提示词、Lora、ControlNet、参数、分辨率、优化")
    print("\n" + "="*60)

def main():
    """主更新流程"""
    print("🔄 开始更新UI架构...")
    
    # 1. 备份原始文件
    if not backup_original_main():
        print("⚠ 备份失败，但继续更新...")
    
    # 2. 替换main.py文件
    if not replace_main_file():
        print("❌ main.py替换失败")
        return False
    
    # 3. 更新UI文件
    if not update_ui_files():
        print("❌ UI文件更新失败")
        return False
    
    # 4. 测试新UI
    if not test_new_ui():
        print("⚠ 新UI测试失败，但更新已完成")
    
    # 5. 打印摘要
    print_update_summary()
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if success:
            print("\n✅ 更新成功完成！")
            input("\n按回车键退出...")
        else:
            print("\n❌ 更新失败！")
            input("\n按回车键退出...")
    except KeyboardInterrupt:
        print("\n\n⚠ 用户取消更新")
    except Exception as e:
        print(f"\n❌ 更新过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车键退出...")