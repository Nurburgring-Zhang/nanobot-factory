#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIGC批处理工具 v5.4 虚拟环境管理器
在代码所在目录内创建和管理虚拟环境，支持ComfyUI和WebUI集成
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

class VirtualEnvManager:
    def __init__(self):
        self.project_root = Path(__file__).parent.absolute()
        self.venv_name = "venv_aigc"
        self.venv_path = self.project_root / self.venv_name
        self.python_exe = self.venv_path / "Scripts" / "python.exe" if platform.system() == "Windows" else self.venv_path / "bin" / "python"
        
    def create_virtual_env(self):
        """创建虚拟环境"""
        print(f"🐍 在项目目录内创建虚拟环境...")
        print(f"📍 项目目录: {self.project_root}")
        print(f"🔧 虚拟环境路径: {self.venv_path}")
        
        try:
            # 检查虚拟环境是否已存在
            if self.venv_path.exists():
                print(f"⚠️ 虚拟环境已存在: {self.venv_path}")
                response = input("是否重新创建? (y/N): ").lower().strip()
                if response in ['y', 'yes']:
                    print("🗑️  删除现有虚拟环境...")
                    import shutil
                    shutil.rmtree(self.venv_path)
                else:
                    print("✅ 使用现有虚拟环境")
                    return True
            
            # 创建虚拟环境
            print("🔧 正在创建虚拟环境...")
            result = subprocess.run([
                sys.executable, "-m", "venv", str(self.venv_path)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ 虚拟环境创建成功")
                return True
            else:
                print(f"❌ 虚拟环境创建失败: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ 创建虚拟环境时出错: {e}")
            return False
    
    def activate_virtual_env(self):
        """激活虚拟环境"""
        if not self.venv_path.exists():
            print("❌ 虚拟环境不存在，请先创建")
            return False
        
        print(f"🔧 激活虚拟环境: {self.venv_path}")
        
        # 设置环境变量
        if platform.system() == "Windows":
            scripts_path = self.venv_path / "Scripts"
            os.environ["PATH"] = str(scripts_path) + os.pathsep + os.environ["PATH"]
            python_path = scripts_path / "python.exe"
        else:
            bin_path = self.venv_path / "bin"
            os.environ["PATH"] = str(bin_path) + os.pathsep + os.environ["PATH"]
            python_path = bin_path / "python"
        
        os.environ["VIRTUAL_ENV"] = str(self.venv_path)
        os.environ["PYTHONPATH"] = str(self.project_root)
        
        print("✅ 虚拟环境已激活")
        return True
    
    def install_requirements(self):
        """安装依赖包"""
        if not self.venv_path.exists():
            print("❌ 虚拟环境不存在，请先创建")
            return False
        
        print("📦 安装项目依赖包...")
        
        # 获取pip路径
        pip_path = self.venv_path / "Scripts" / "pip.exe" if platform.system() == "Windows" else self.venv_path / "bin" / "pip"
        
        try:
            # 升级pip
            print("🔄 升级pip...")
            subprocess.run([str(self.python_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True)
            
            # 选择合适的requirements文件
            requirements_file = None
            if platform.system() == "Windows":
                # Windows系统优先使用Windows优化版本
                windows_req = self.project_root / "requirements_windows.txt"
                if windows_req.exists():
                    requirements_file = windows_req
                    print(f"📋 使用Windows优化依赖: {requirements_file}")
                else:
                    requirements_file = self.project_root / "requirements.txt"
                    print(f"📋 使用标准依赖: {requirements_file}")
            else:
                requirements_file = self.project_root / "requirements.txt"
                print(f"📋 使用标准依赖: {requirements_file}")
            
            if requirements_file and requirements_file.exists():
                result = subprocess.run([
                    str(pip_path), "install", "-r", str(requirements_file)
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    print("✅ 依赖包安装成功")
                    return True
                else:
                    print(f"❌ 依赖包安装失败: {result.stderr}")
                    return False
            else:
                print("⚠️ requirements文件不存在")
                return False
                
        except Exception as e:
            print(f"❌ 安装依赖包时出错: {e}")
            return False
    
    def setup_comfyui_webui(self):
        """设置ComfyUI和WebUI"""
        try:
            if not self.venv_path.exists():
                print("❌ 虚拟环境不存在，请先创建虚拟环境")
                return False
            
            print("🎨 设置ComfyUI和WebUI集成...")
            
            # 使用虚拟环境Python导入ComfyUI/WebUI集成模块
            python_exe = self.python_exe
            
            # 运行ComfyUI/WebUI设置脚本
            setup_script = f'''
import sys
sys.path.insert(0, "{self.project_root}")
from backend_modules.comfyui_webui_integration import ComfyUIWebUIIntegration

print("🎨 初始化ComfyUI和WebUI集成...")
integration = ComfyUIWebUIIntegration("{self.venv_path}")

print("📥 安装ComfyUI...")
comfyui_success = integration.install_comfyui()

print("📥 安装WebUI...")
webui_success = integration.install_webui()

print("✅ ComfyUI和WebUI设置完成!")
print(f"ComfyUI: {{'✅ 成功' if comfyui_success else '❌ 失败'}}")
print(f"WebUI: {{'✅ 成功' if webui_success else '❌ 失败'}}")
'''
            
            # 创建临时脚本文件
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(setup_script)
                temp_script = f.name
            
            try:
                result = subprocess.run([
                    str(python_exe), temp_script
                ], capture_output=True, text=True)
                
                print(result.stdout)
                if result.stderr:
                    print(f"警告: {result.stderr}")
                
                return result.returncode == 0
                
            finally:
                # 清理临时文件
                os.unlink(temp_script)
                
        except Exception as e:
            print(f"❌ 设置ComfyUI/WebUI失败: {e}")
            return False
    
    def setup_all(self):
        """完整设置：虚拟环境 + 依赖 + ComfyUI + WebUI"""
        print("🔧 开始完整环境设置...")
        
        steps = [
            ("创建虚拟环境", self.create_virtual_env),
            ("安装依赖包", self.install_requirements),
            ("设置ComfyUI和WebUI", self.setup_comfyui_webui)
        ]
        
        for step_name, step_func in steps:
            print(f"\n📋 执行: {step_name}")
            try:
                if not step_func():
                    print(f"❌ {step_name} 失败")
                    return False
                print(f"✅ {step_name} 成功")
            except Exception as e:
                print(f"❌ {step_name} 出错: {e}")
                return False
        
        print("\n🎉 完整环境设置完成!")
        return True
    
    def start_comfyui(self):
        """启动ComfyUI"""
        return self._start_service("comfyui")
    
    def start_webui(self):
        """启动WebUI"""
        return self._start_service("webui")
    
    def start_all(self):
        """启动所有服务"""
        try:
            print("🚀 启动所有AI服务...")
            
            python_exe = self.python_exe
            
            # 启动ComfyUI和WebUI的脚本
            start_script = f'''
import sys
sys.path.insert(0, "{self.project_root}")
from backend_modules.comfyui_webui_integration import ComfyUIWebUIIntegration
import webbrowser

print("🔗 初始化ComfyUI和WebUI集成...")
integration = ComfyUIWebUIIntegration("{self.venv_path}")

print("🚀 启动ComfyUI...")
comfyui_success = integration.start_comfyui(auto_open=False)

print("🚀 启动WebUI...")
webui_success = integration.start_webui(auto_open=False)

print("⏳ 等待服务启动...")
import time
time.sleep(3)

if comfyui_success:
    print("✅ ComfyUI启动成功 - http://localhost:8188")
    # webbrowser.open("http://localhost:8188")

if webui_success:
    print("✅ WebUI启动成功 - http://localhost:7860")
    # webbrowser.open("http://localhost:7860")

print("👋 服务启动完成! 按 Ctrl+C 停止...")
try:
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\\n🛑 正在停止服务...")
    integration.stop_comfyui()
    integration.stop_webui()
    print("✅ 所有服务已停止")
'''
            
            # 创建临时脚本文件
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(start_script)
                temp_script = f.name
            
            try:
                subprocess.run([str(python_exe), temp_script])
                return True
            finally:
                os.unlink(temp_script)
                
        except Exception as e:
            print(f"❌ 启动服务失败: {e}")
            return False
    
    def _start_service(self, service_name):
        """启动单个服务"""
        try:
            print(f"🚀 启动{service_name}...")
            
            python_exe = self.python_exe
            
            start_script = f'''
import sys
sys.path.insert(0, "{self.project_root}")
from backend_modules.comfyui_webui_integration import ComfyUIWebUIIntegration

integration = ComfyUIWebUIIntegration("{self.venv_path}")

if "{service_name}" == "comfyui":
    integration.start_comfyui()
else:
    integration.start_webui()
'''
            
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(start_script)
                temp_script = f.name
            
            try:
                subprocess.run([str(python_exe), temp_script])
                return True
            finally:
                os.unlink(temp_script)
                
        except Exception as e:
            print(f"❌ 启动{service_name}失败: {e}")
            return False
    
    def run_main_app(self):
        """运行主程序"""
        if not self.venv_path.exists():
            print("❌ 虚拟环境不存在，请先创建")
            return False
        
        print("🚀 启动AIGC批处理工具...")
        
        # 运行主程序
        main_file = self.project_root / "main.py"
        if main_file.exists():
            try:
                result = subprocess.run([str(self.python_exe), str(main_file)])
                return result.returncode == 0
            except Exception as e:
                print(f"❌ 运行主程序时出错: {e}")
                return False
        else:
            print("❌ 主程序文件 main.py 不存在")
            return False
    
    def check_environment(self):
        """检查环境"""
        print("🔍 检查Python环境...")
        print(f"🐍 Python版本: {sys.version}")
        print(f"💻 系统平台: {platform.system()} {platform.release()}")
        print(f"📁 项目目录: {self.project_root}")
        print(f"🔧 虚拟环境路径: {self.venv_path}")
        
        if self.venv_path.exists():
            print("✅ 虚拟环境已存在")
            
            # 检查ComfyUI和WebUI
            comfyui_path = self.project_root / "comfyui"
            webui_path = self.project_root / "webui"
            
            if comfyui_path.exists():
                print("✅ ComfyUI已安装")
            else:
                print("❌ ComfyUI未安装")
            
            if webui_path.exists():
                print("✅ WebUI已安装")
            else:
                print("❌ WebUI未安装")
        else:
            print("❌ 虚拟环境不存在")
    
    def show_help(self):
        """显示帮助信息"""
        print("""
🔧 AIGC批处理工具 v5.4 虚拟环境管理器 (支持ComfyUI和WebUI)

用法: python manage_venv.py [命令]

命令:
  create      - 创建虚拟环境
  activate    - 激活虚拟环境
  install     - 安装依赖包
  comfyui     - 安装和设置ComfyUI
  webui       - 安装和设置WebUI  
  setup-all   - 完整设置 (虚拟环境 + 依赖 + ComfyUI + WebUI)
  run         - 运行主程序 (创建+安装+运行)
  start       - 启动所有AI服务 (ComfyUI + WebUI)
  start-cw    - 启动ComfyUI
  start-wu    - 启动WebUI
  check       - 检查环境
  clean       - 清理虚拟环境
  help        - 显示此帮助信息

示例:
  python manage_venv.py create        # 创建虚拟环境
  python manage_venv.py setup-all     # 完整设置 (推荐)
  python manage_venv.py start         # 启动所有AI服务
        """)

def main():
    """主函数"""
    manager = VirtualEnvManager()
    
    if len(sys.argv) < 2:
        manager.show_help()
        return
    
    command = sys.argv[1].lower()
    
    if command == "create":
        manager.create_virtual_env()
    elif command == "activate":
        manager.activate_virtual_env()
    elif command == "install":
        manager.install_requirements()
    elif command == "comfyui":
        manager.setup_comfyui_webui()
    elif command == "webui":
        manager.setup_comfyui_webui()
    elif command == "setup-all":
        manager.setup_all()
    elif command == "run":
        if manager.setup_all():
            manager.run_main_app()
    elif command == "start":
        manager.start_all()
    elif command == "start-cw":
        manager.start_comfyui()
    elif command == "start-wu":
        manager.start_webui()
    elif command == "check":
        manager.check_environment()
    elif command == "clean":
        if manager.venv_path.exists():
            import shutil
            shutil.rmtree(manager.venv_path)
            print("✅ 虚拟环境已清理")
        else:
            print("✅ 虚拟环境不存在，无需清理")
    elif command == "help":
        manager.show_help()
    else:
        print(f"❌ 未知命令: {command}")
        manager.show_help()

if __name__ == "__main__":
    main()