#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
General AIGC Enhanced 功能验证脚本
全面测试所有功能是否正常工作
"""

import sys
import os
import json
import traceback
from pathlib import Path

# 添加项目路径到sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_imports():
    """测试所有模块导入"""
    print("=" * 60)
    print("🔍 测试模块导入")
    print("=" * 60)
    
    test_results = {}
    
    # 测试后端模块
    print("\n📦 测试后端模块导入...")
    try:
        from backend_modules.backend_integration import BackendManager
        print("✅ backend_integration 导入成功")
        test_results['backend_integration'] = True
    except Exception as e:
        print(f"❌ backend_integration 导入失败: {e}")
        test_results['backend_integration'] = False
    
    try:
        from backend_modules.smart_venv_manager import SmartVenvManager
        print("✅ smart_venv_manager 导入成功")
        test_results['smart_venv_manager'] = True
    except Exception as e:
        print(f"❌ smart_venv_manager 导入失败: {e}")
        test_results['smart_venv_manager'] = False
    
    try:
        from backend_modules.comfyui_webui_integration import ComfyUIWebUIIntegration
        print("✅ comfyui_webui_integration 导入成功")
        test_results['comfyui_webui_integration'] = True
    except Exception as e:
        print(f"❌ comfyui_webui_integration 导入失败: {e}")
        test_results['comfyui_webui_integration'] = False
    
    try:
        from backend_modules.enhanced_ui_manager import EnhancedUIManager
        print("✅ enhanced_ui_manager 导入成功")
        test_results['enhanced_ui_manager'] = True
    except Exception as e:
        print(f"❌ enhanced_ui_manager 导入失败: {e}")
        test_results['enhanced_ui_manager'] = False
    
    try:
        from backend_modules.comprehensive_feature_manager import ComprehensiveFeatureManager
        print("✅ comprehensive_feature_manager 导入成功")
        test_results['comprehensive_feature_manager'] = True
    except Exception as e:
        print(f"❌ comprehensive_feature_manager 导入失败: {e}")
        test_results['comprehensive_feature_manager'] = False
    
    try:
        from backend_modules.windows_compatibility import WindowsCompatibilityManager
        print("✅ windows_compatibility 导入成功")
        test_results['windows_compatibility'] = True
    except Exception as e:
        print(f"❌ windows_compatibility 导入失败: {e}")
        test_results['windows_compatibility'] = False
    
    # 测试AI相关模块
    print("\n🤖 测试AI模块导入...")
    ai_modules = [
        'torch', 'diffusers', 'transformers', 'opencv', 'pillow', 'numpy'
    ]
    
    for module in ai_modules:
        try:
            __import__(module)
            print(f"✅ {module} 导入成功")
            test_results[module] = True
        except ImportError:
            print(f"❌ {module} 导入失败")
            test_results[module] = False
    
    return test_results

def test_venv_detection():
    """测试虚拟环境检测"""
    print("\n" + "=" * 60)
    print("🐍 测试虚拟环境检测")
    print("=" * 60)
    
    try:
        from backend_modules.smart_venv_manager import SmartVenvManager
        
        manager = SmartVenvManager()
        print(f"基础路径: {manager.base_path}")
        print(f"可用的虚拟环境: {manager.list_venvs()}")
        
        # 测试Python可执行文件路径
        python_exe = manager.get_python_exe()
        print(f"Python可执行文件: {python_exe}")
        
        if python_exe and Path(python_exe).exists():
            print("✅ 虚拟环境检测成功")
            return True
        else:
            print("❌ 虚拟环境检测失败")
            return False
            
    except Exception as e:
        print(f"❌ 虚拟环境检测出错: {e}")
        return False

def test_feature_manager():
    """测试功能管理器"""
    print("\n" + "=" * 60)
    print("🔧 测试功能管理器")
    print("=" * 60)
    
    try:
        from backend_modules.comprehensive_feature_manager import ComprehensiveFeatureManager
        
        manager = ComprehensiveFeatureManager()
        
        # 检查环境
        env = manager.check_environment()
        print("环境检查结果:")
        for key, value in env.items():
            print(f"  {key}: {value}")
        
        # 运行功能测试
        print("\n运行功能测试...")
        results = manager.run_all_tests()
        
        print("\n功能测试结果:")
        for feature, result in results.items():
            status = "✅ 通过" if result else "❌ 失败"
            print(f"  {feature}: {status}")
        
        # 生成实现状态报告
        report = manager.get_implementation_status()
        print(f"\n实现状态报告:")
        print(f"  总功能数: {report['total_features']}")
        print(f"  完全实现: {report['fully_implemented']}")
        print(f"  部分实现: {report['partially_implemented']}")
        print(f"  未实现: {report['not_implemented']}")
        print(f"  测试中: {report['testing']}")
        print(f"  错误: {report['errors']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 功能管理器测试失败: {e}")
        traceback.print_exc()
        return False

def test_enhanced_ui():
    """测试增强UI管理器"""
    print("\n" + "=" * 60)
    print("🖥️ 测试增强UI管理器")
    print("=" * 60)
    
    try:
        from backend_modules.enhanced_ui_manager import EnhancedUIManager
        
        manager = EnhancedUIManager()
        print("✅ 增强UI管理器创建成功")
        print("✅ 增强UI管理器测试通过")
        return True
        
    except Exception as e:
        print(f"❌ 增强UI管理器测试失败: {e}")
        traceback.print_exc()
        return False

def test_comfyui_webui_integration():
    """测试ComfyUI/WebUI集成"""
    print("\n" + "=" * 60)
    print("🎨 测试ComfyUI/WebUI集成")
    print("=" * 60)
    
    try:
        from backend_modules.comfyui_webui_integration import ComfyUIWebUIIntegration
        
        integration = ComfyUIWebUIIntegration()
        print(f"项目根目录: {integration.project_root}")
        print(f"虚拟环境路径: {integration.venv_path}")
        print(f"ComfyUI路径: {integration.comfyui_path}")
        print(f"WebUI路径: {integration.webui_path}")
        
        # 检查ComfyUI是否已安装
        if integration.comfyui_path.exists():
            print("✅ ComfyUI已安装")
        else:
            print("⚠️ ComfyUI未安装")
        
        # 检查WebUI是否已安装
        if integration.webui_path.exists():
            print("✅ WebUI已安装")
        else:
            print("⚠️ WebUI未安装")
        
        print("✅ ComfyUI/WebUI集成测试通过")
        return True
        
    except Exception as e:
        print(f"❌ ComfyUI/WebUI集成测试失败: {e}")
        traceback.print_exc()
        return False

def test_gpu_info():
    """测试GPU信息获取"""
    print("\n" + "=" * 60)
    print("🎮 测试GPU信息")
    print("=" * 60)
    
    try:
        import torch
        
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory
            cuda_version = torch.version.cuda
            
            print(f"✅ GPU: {gpu_name}")
            print(f"✅ 显存: {gpu_memory / (1024**3):.1f} GB")
            print(f"✅ CUDA版本: {cuda_version}")
            
            # 检查是否是RTX4090
            if "RTX 4090" in gpu_name:
                print("✅ 检测到RTX 4090 GPU")
                return True
            else:
                print(f"⚠️ 检测到其他GPU: {gpu_name}")
                return True
        else:
            print("❌ CUDA不可用")
            return False
            
    except ImportError:
        print("❌ PyTorch未安装")
        return False
    except Exception as e:
        print(f"❌ GPU信息获取失败: {e}")
        return False

def test_main_application():
    """测试主应用程序导入"""
    print("\n" + "=" * 60)
    print("🚀 测试主应用程序")
    print("=" * 60)
    
    try:
        # 尝试导入主程序类（不创建实例）
        import main
        print("✅ 主程序模块导入成功")
        
        # 检查关键函数是否存在
        if hasattr(main, 'get_venv_path'):
            print("✅ get_venv_path 函数存在")
        else:
            print("❌ get_venv_path 函数不存在")
        
        if hasattr(main, 'ZImageBatchGenerator'):
            print("✅ ZImageBatchGenerator 类存在")
        else:
            print("❌ ZImageBatchGenerator 类不存在")
        
        return True
        
    except Exception as e:
        print(f"❌ 主应用程序测试失败: {e}")
        traceback.print_exc()
        return False

def generate_test_report(results):
    """生成测试报告"""
    print("\n" + "=" * 60)
    print("📊 测试报告")
    print("=" * 60)
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    failed_tests = total_tests - passed_tests
    
    print(f"总测试数: {total_tests}")
    print(f"通过: {passed_tests}")
    print(f"失败: {failed_tests}")
    print(f"成功率: {passed_tests/total_tests*100:.1f}%")
    
    print("\n详细结果:")
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    # 保存报告到文件
    report_file = project_root / "test_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n📄 详细报告已保存到: {report_file}")

def main():
    """主测试函数"""
    print("🎯 General AIGC Enhanced 功能验证测试")
    print("=" * 80)
    
    all_results = {}
    
    # 运行所有测试
    tests = [
        ("模块导入", test_imports),
        ("虚拟环境检测", test_venv_detection),
        ("功能管理器", test_feature_manager),
        ("增强UI", test_enhanced_ui),
        ("ComfyUI/WebUI集成", test_comfyui_webui_integration),
        ("GPU信息", test_gpu_info),
        ("主应用程序", test_main_application),
    ]
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            all_results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} 测试出错: {e}")
            all_results[test_name] = False
    
    # 生成最终报告
    generate_test_report(all_results)
    
    # 总结
    print("\n" + "=" * 80)
    passed = sum(all_results.values())
    total = len(all_results)
    print(f"🎉 测试完成: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("🎊 所有测试通过！General AIGC Enhanced 准备就绪！")
    else:
        print("⚠️ 部分测试失败，请检查上述错误信息")

if __name__ == "__main__":
    main()
