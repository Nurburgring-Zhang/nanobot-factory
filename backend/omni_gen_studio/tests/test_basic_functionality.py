#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC批处理工具基本功能测试
"""

import unittest
import os
import sys
import tkinter as tk
from unittest.mock import patch, MagicMock

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

class TestBasicFunctionality(unittest.TestCase):
    """基本功能测试类"""
    
    def setUp(self):
        """测试初始化"""
        self.root = tk.Tk()
        self.root.withdraw()  # 隐藏主窗口
    
    def tearDown(self):
        """测试清理"""
        self.root.destroy()
    
    def test_import_main_module(self):
        """测试主模块导入"""
        try:
            from main import ZImageBatchGenerator
            self.assertTrue(True, "主模块导入成功")
        except ImportError as e:
            self.fail(f"主模块导入失败：{e}")
    
    def test_import_ui_components(self):
        """测试UI组件导入"""
        components = [
            'ui_components.enhanced_image_generation_components',
            'ui_components.enhanced_image_editing_components',
            'ui_components.enhanced_video_generation_components',
            'ui_components.enhanced_3d_generation_components'
        ]
        
        for component in components:
            try:
                __import__(component)
                self.assertTrue(True, f"{component} 导入成功")
            except ImportError as e:
                self.fail(f"{component} 导入失败：{e}")
    
    def test_import_backend_modules(self):
        """测试后端模块导入"""
        modules = [
            'backend_modules.backend_integration',
            'backend_modules.windows_compatibility',
            'backend_modules.image_editing_backend',
            'backend_modules.video_generation_backend',
            'backend_modules.threed_generation_backend'
        ]
        
        for module in modules:
            try:
                __import__(module)
                self.assertTrue(True, f"{module} 导入成功")
            except ImportError as e:
                self.fail(f"{module} 导入失败：{e}")
    
    def test_config_files_exist(self):
        """测试配置文件存在"""
        config_files = [
            'config/model_config.json',
            'requirements.txt',
            'README.md'
        ]
        
        for config_file in config_files:
            self.assertTrue(
                os.path.exists(config_file),
                f"配置文件 {config_file} 不存在"
            )
    
    @patch('builtins.input')
    def test_main_window_creation(self, mock_input):
        """测试主窗口创建"""
        mock_input.return_value = "test"
        
        try:
            # 导入主窗口类
            from main import ZImageBatchGenerator
            
            # 创建窗口实例
            app = ZImageBatchGenerator()
            
            # 验证窗口创建成功
            self.assertIsNotNone(app.root)
            self.assertTrue(hasattr(app, 'notebook'))
            
            app.root.destroy()
            
        except Exception as e:
            self.fail(f"主窗口创建失败：{e}")
    
    def test_directory_structure(self):
        """测试目录结构"""
        required_dirs = [
            'ui_components',
            'backend_modules',
            'config',
            'models',
            'output',
            'logs',
            'examples',
            'tests'
        ]
        
        for directory in required_dirs:
            self.assertTrue(
                os.path.exists(directory),
                f"目录 {directory} 不存在"
            )

class TestBackendIntegration(unittest.TestCase):
    """后端集成测试类"""
    
    def test_backend_manager_initialization(self):
        """测试后端管理器初始化"""
        try:
            from backend_modules.backend_integration import BackendManager
            
            manager = BackendManager()
            status = manager.get_status()
            
            self.assertIsInstance(status, dict)
            self.assertTrue(True, "后端管理器初始化成功")
            
        except Exception as e:
            self.fail(f"后端管理器初始化失败：{e}")
    
    def test_windows_compatibility(self):
        """测试Windows兼容性"""
        try:
            from backend_modules.windows_compatibility import WindowsCompatibilityManager
            
            compat_manager = WindowsCompatibilityManager()
            self.assertIsNotNone(compat_manager)
            
            # 测试路径处理
            test_path = "./test/path"
            normalized_path = compat_manager.normalize_path(test_path)
            self.assertIsInstance(normalized_path, str)
            
        except Exception as e:
            self.fail(f"Windows兼容性测试失败：{e}")

if __name__ == '__main__':
    print("🧪 开始运行AIGC批处理工具基本功能测试...")
    print("=" * 50)
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestBasicFunctionality))
    suite.addTests(loader.loadTestsFromTestCase(TestBackendIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出结果
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("✅ 所有测试通过！")
    else:
        print("❌ 存在测试失败")
        print(f"失败数：{len(result.failures)}")
        print(f"错误数：{len(result.errors)}")
    
    print(f"运行时间：{result.testsRun} 个测试")