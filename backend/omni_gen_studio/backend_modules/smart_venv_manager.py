#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能虚拟环境管理器
解决虚拟环境路径检测问题，确保在Windows系统下正确工作
"""

import os
import sys
from pathlib import Path
from typing import Optional, List

class SmartVenvManager:
    """智能虚拟环境管理器"""
    
    def __init__(self, base_path: Optional[Path] = None):
        """初始化虚拟环境管理器"""
        self.base_path = base_path or self._detect_venv_base()
        print(f"🔧 智能虚拟环境管理器初始化")
        print(f"   基础路径: {self.base_path}")
        
    def _detect_venv_base(self) -> Path:
        """智能检测虚拟环境基础路径"""
        # 候选路径列表（按优先级排序）
        candidate_paths = []
        
        # 1. 相对于当前脚本的路径
        current_dir = Path(__file__).parent.parent  # backend_modules -> 项目根目录
        candidate_paths.extend([
            current_dir / "venv",
            current_dir / ".venv", 
            current_dir / "ext",
            current_dir / "env"
        ])
        
        # 2. 项目根目录下的常见虚拟环境名称
        project_root = current_dir
        candidate_paths.extend([
            project_root / "venv_aigc",
            project_root / "venv_aigc_batch_tool",
            project_root / ".venv_aigc",
            project_root / "python_env"
        ])
        
        # 3. 检查当前Python是否在虚拟环境中
        if self._is_in_virtual_env():
            current_venv = Path(sys.prefix)
            if current_venv.name in ['venv', '.venv', 'env', 'ext', 'venv_aigc']:
                candidate_paths.insert(0, current_venv)
        
        # 4. 检查环境变量
        env_venv_paths = [
            os.getenv('VIRTUAL_ENV'),
            os.getenv('CONDA_DEFAULT_ENV'),
            os.getenv('PYENV_VIRTUALENV_ENV')
        ]
        for env_path in env_venv_paths:
            if env_path:
                candidate_paths.insert(0, Path(env_path))
        
        # 5. 检查项目目录下的所有目录
        try:
            for item in project_root.iterdir():
                if item.is_dir() and any(name in item.name.lower() for name in ['venv', 'env', 'ext']):
                    candidate_paths.append(item)
        except Exception as e:
            print(f"⚠️ 扫描项目目录时出错: {e}")
        
        # 查找存在的虚拟环境
        for path in candidate_paths:
            if path.exists() and self._is_valid_venv(path):
                print(f"✅ 发现虚拟环境: {path}")
                return path.parent
        
        # 如果没找到，创建一个默认路径
        default_path = project_root / "venv"
        print(f"⚠️ 未找到现有虚拟环境，将创建: {default_path}")
        return default_path
    
    def _is_in_virtual_env(self) -> bool:
        """检查当前是否在虚拟环境中"""
        return (
            hasattr(sys, 'real_prefix') or 
            (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
        )
    
    def _is_valid_venv(self, venv_path: Path) -> bool:
        """验证是否为有效的虚拟环境"""
        if not venv_path.exists() or not venv_path.is_dir():
            return False
        
        # 检查关键文件和目录
        if os.name == "nt":
            python_exe = venv_path / "Scripts" / "python.exe"
            pip_exe = venv_path / "Scripts" / "pip.exe"
        else:
            python_exe = venv_path / "bin" / "python"
            pip_exe = venv_path / "bin" / "pip"
        
        return python_exe.exists() or pip_exe.exists()
    
    def get_venv_path(self, name: str = "venv") -> Path:
        """获取指定名称的虚拟环境路径"""
        return self.base_path / name
    
    def get_python_exe(self, name: str = "venv") -> Optional[str]:
        """获取Python可执行文件路径"""
        venv_path = self.get_venv_path(name)
        if not venv_path.exists():
            print(f"⚠️ 虚拟环境不存在: {venv_path}")
            return None
            
        if os.name == "nt":
            python_exe = venv_path / "Scripts" / "python.exe"
        else:
            python_exe = venv_path / "bin" / "python"
        
        if python_exe.exists():
            return str(python_exe)
        
        print(f"⚠️ Python可执行文件不存在: {python_exe}")
        return None
    
    def get_pip_exe(self, name: str = "venv") -> Optional[str]:
        """获取pip可执行文件路径"""
        venv_path = self.get_venv_path(name)
        if not venv_path.exists():
            return None
            
        if os.name == "nt":
            pip_exe = venv_path / "Scripts" / "pip.exe"
        else:
            pip_exe = venv_path / "bin" / "pip"
        
        if pip_exe.exists():
            return str(pip_exe)
        
        print(f"⚠️ pip可执行文件不存在: {pip_exe}")
        return None
    
    def create_venv(self, name: str = "venv") -> bool:
        """创建虚拟环境"""
        import venv
        venv_path = self.get_venv_path(name)
        
        try:
            print(f"🔄 创建虚拟环境: {venv_path}")
            venv.create(venv_path, with_pip=True)
            
            if self._is_valid_venv(venv_path):
                print(f"✅ 虚拟环境创建成功: {venv_path}")
                return True
            else:
                print(f"❌ 虚拟环境创建后验证失败: {venv_path}")
                return False
                
        except Exception as e:
            print(f"❌ 创建虚拟环境失败: {e}")
            return False
    
    def list_venvs(self) -> List[str]:
        """列出所有可用的虚拟环境"""
        if not self.base_path.exists():
            return []
        
        venvs = []
        try:
            for item in self.base_path.iterdir():
                if item.is_dir() and self._is_valid_venv(item):
                    venvs.append(item.name)
        except Exception as e:
            print(f"⚠️ 列出虚拟环境时出错: {e}")
        
        return venvs
    
    def ensure_venv_exists(self, name: str = "venv") -> bool:
        """确保虚拟环境存在，如果不存在则创建"""
        venv_path = self.get_venv_path(name)
        
        if self._is_valid_venv(venv_path):
            return True
        
        print(f"⚠️ 虚拟环境不存在或不完整: {venv_path}")
        return self.create_venv(name)

# 全局实例
_smart_venv_manager = None

def get_smart_venv_manager() -> SmartVenvManager:
    """获取全局智能虚拟环境管理器实例"""
    global _smart_venv_manager
    if _smart_venv_manager is None:
        _smart_venv_manager = SmartVenvManager()
    return _smart_venv_manager

def get_venv_path() -> Path:
    """获取虚拟环境路径 - 兼容原有接口"""
    return get_smart_venv_manager().get_venv_path()

def get_python_exe(venv_path: Optional[Path] = None) -> Optional[str]:
    """获取Python可执行文件路径 - 兼容原有接口"""
    if venv_path is None:
        venv_path = get_venv_path()
    return get_smart_venv_manager().get_python_exe(str(venv_path.name))

def get_pip_exe(venv_path: Optional[Path] = None) -> Optional[str]:
    """获取pip可执行文件路径 - 兼容原有接口"""
    if venv_path is None:
        venv_path = get_venv_path()
    return get_smart_venv_manager().get_pip_exe(str(venv_path.name))

if __name__ == "__main__":
    # 测试代码
    manager = SmartVenvManager()
    print(f"检测到的虚拟环境基础路径: {manager.base_path}")
    print(f"可用的虚拟环境: {manager.list_venvs()}")
    
    venv_path = manager.get_venv_path()
    print(f"默认虚拟环境路径: {venv_path}")
    
    python_exe = manager.get_python_exe()
    print(f"Python可执行文件: {python_exe}")
    
    pip_exe = manager.get_pip_exe()
    print(f"pip可执行文件: {pip_exe}")