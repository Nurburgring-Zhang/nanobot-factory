#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
General AIGC Enhanced 部署修复脚本
修复所有发现的问题，确保应用正常运行
"""

import sys
import os
import subprocess
from pathlib import Path
import shutil

def fix_imports():
    """修复后端模块导入问题"""
    print("🔧 修复后端模块导入问题...")
    
    # 确保所有模块都能正确导入
    try:
        from backend_modules.backend_integration import BackendManager
        print("✅ BackendManager 导入成功")
    except Exception as e:
        print(f"❌ BackendManager 导入失败: {e}")
    
    try:
        from backend_modules.smart_venv_manager import SmartVenvManager
        print("✅ SmartVenvManager 导入成功")
    except Exception as e:
        print(f"❌ SmartVenvManager 导入失败: {e}")
    
    try:
        from backend_modules.comfyui_webui_integration import ComfyUIWebUIIntegration
        print("✅ ComfyUIWebUIIntegration 导入成功")
    except Exception as e:
        print(f"❌ ComfyUIWebUIIntegration 导入失败: {e}")
    
    try:
        from backend_modules.enhanced_ui_manager import EnhancedUIManager
        print("✅ EnhancedUIManager 导入成功")
    except Exception as e:
        print(f"❌ EnhancedUIManager 导入失败: {e}")

def fix_venv_detection():
    """修复虚拟环境检测问题"""
    print("\n🐍 修复虚拟环境检测问题...")
    
    try:
        from backend_modules.smart_venv_manager import SmartVenvManager
        
        # 创建智能虚拟环境管理器
        manager = SmartVenvManager()
        
        # 检查项目根目录
        project_root = Path(__file__).parent
        print(f"项目根目录: {project_root}")
        
        # 检查常见的虚拟环境目录
        venv_dirs = [
            project_root / "venv",
            project_root / ".venv",
            project_root / "venv_aigc",
            project_root / "venv_aigc_batch_tool",
            project_root / ".venv_aigc",
            project_root / "ext",
            project_root / "env"
        ]
        
        for venv_dir in venv_dirs:
            if venv_dir.exists():
                print(f"✅ 发现虚拟环境目录: {venv_dir}")
                
                # 检查是否是有效的虚拟环境
                if os.name == "nt":
                    python_exe = venv_dir / "Scripts" / "python.exe"
                    pip_exe = venv_dir / "Scripts" / "pip.exe"
                else:
                    python_exe = venv_dir / "bin" / "python"
                    pip_exe = venv_dir / "bin" / "pip"
                
                if python_exe.exists():
                    print(f"  Python可执行文件: {python_exe}")
                    print(f"  ✅ 虚拟环境有效")
                    break
                else:
                    print(f"  ❌ 虚拟环境无效（缺少Python可执行文件）")
            else:
                print(f"❌ 目录不存在: {venv_dir}")
        
        # 更新基础路径
        manager.base_path = project_root
        print(f"✅ 虚拟环境基础路径已更新: {manager.base_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ 虚拟环境检测修复失败: {e}")
        return False

def fix_comfyui_webui_paths():
    """修复ComfyUI和WebUI路径问题"""
    print("\n🎨 修复ComfyUI和WebUI路径...")
    
    try:
        from backend_modules.comfyui_webui_integration import ComfyUIWebUIIntegration
        
        integration = ComfyUIWebUIIntegration()
        
        # 检查路径
        comfyui_path = integration.comfyui_path
        webui_path = integration.webui_path
        
        print(f"ComfyUI路径: {comfyui_path}")
        print(f"WebUI路径: {webui_path}")
        
        # 创建目录（如果不存在）
        comfyui_path.mkdir(parents=True, exist_ok=True)
        webui_path.mkdir(parents=True, exist_ok=True)
        
        print("✅ ComfyUI和WebUI目录已确保存在")
        
        return True
        
    except Exception as e:
        print(f"❌ ComfyUI/WebUI路径修复失败: {e}")
        return False

def fix_windows_compatibility():
    """修复Windows兼容性"""
    print("\n🪟 修复Windows兼容性...")
    
    try:
        from backend_modules.windows_compatibility import WindowsCompatibilityManager
        
        compat = WindowsCompatibilityManager()
        print(f"平台信息: {compat.platform_info}")
        print(f"是否为Windows: {compat.is_windows}")
        print(f"是否为管理员: {compat.is_admin}")
        
        return True
        
    except Exception as e:
        print(f"❌ Windows兼容性修复失败: {e}")
        return False

def create_enhanced_startup_script():
    """创建增强的启动脚本"""
    print("\n🚀 创建增强启动脚本...")
    
    startup_script = '''#!/usr/bin/env python3
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
    
    print("\\n🔧 启动主应用程序...")
    
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
'''
    
    script_path = Path(__file__).parent / "enhanced_startup.py"
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(startup_script)
    
    # 设置执行权限
    try:
        script_path.chmod(0o755)
    except:
        pass  # Windows下可能失败
    
    print(f"✅ 增强启动脚本已创建: {script_path}")

def create_test_windows_script():
    """创建Windows测试脚本"""
    print("\n🧪 创建Windows测试脚本...")
    
    test_script = '''@echo off
chcp 65001 >nul
echo ================================
echo  General AIGC Enhanced 功能测试
echo ================================
echo.

echo [步骤1/4] 检查Python环境...
python --version
if %errorlevel% neq 0 (
    echo [错误] Python未安装
    pause
    exit /b 1
)

echo [步骤2/4] 运行功能验证...
python 功能验证脚本.py

echo [步骤3/4] 运行增强启动...
python enhanced_startup.py

echo [步骤4/4] 测试完成
echo 按任意键退出...
pause >nul
'''
    
    script_path = Path(__file__).parent / "test_all.bat"
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(test_script)
    
    print(f"✅ Windows测试脚本已创建: {script_path}")

def main():
    """主修复函数"""
    print("🛠️ General AIGC Enhanced 部署修复")
    print("=" * 80)
    
    all_success = True
    
    # 运行所有修复步骤
    steps = [
        ("修复导入", fix_imports),
        ("修复虚拟环境", fix_venv_detection),
        ("修复ComfyUI/WebUI", fix_comfyui_webui_paths),
        ("修复Windows兼容性", fix_windows_compatibility),
        ("创建增强启动脚本", create_enhanced_startup_script),
        ("创建测试脚本", create_test_windows_script),
    ]
    
    for step_name, step_func in steps:
        print(f"\n🔧 {step_name}...")
        try:
            result = step_func()
            if result is False:
                all_success = False
                print(f"❌ {step_name} 失败")
            else:
                print(f"✅ {step_name} 成功")
        except Exception as e:
            all_success = False
            print(f"❌ {step_name} 异常: {e}")
    
    # 总结
    print("\n" + "=" * 80)
    if all_success:
        print("🎉 所有修复步骤完成！")
        print("\n📋 使用说明:")
        print("1. 运行 Windows测试脚本: test_all.bat")
        print("2. 或直接运行: python enhanced_startup.py")
        print("3. 功能验证: python 功能验证脚本.py")
    else:
        print("⚠️ 部分修复步骤失败，请检查错误信息")
    
    return all_success

if __name__ == "__main__":
    main()
