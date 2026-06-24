"""
Windows兼容性增强模块
用于确保AIGC_batch_tool在Windows环境下的完美运行
"""

import os
import sys
import platform
import subprocess
import pathlib
from pathlib import Path
from typing import Union, Optional, Dict, Any
import shutil


class WindowsCompatibilityManager:
    """Windows兼容性管理器"""
    
    def __init__(self):
        self.platform_info = self._get_platform_info()
        self.is_windows = self.platform_info['is_windows']
        self.is_admin = self._check_admin_privileges()
        self.user_dir = self._get_user_directory()
        self.temp_dir = self._get_temp_directory()
        
    def _get_platform_info(self) -> Dict[str, Any]:
        """获取详细的平台信息"""
        system = platform.system()
        is_windows = system == "Windows"
        is_admin = self._check_admin_privileges()
        
        return {
            'system': system,
            'is_windows': is_windows,
            'is_admin': is_admin,
            'python_executable': sys.executable,
            'python_version': sys.version_info,
            'architecture': platform.machine(),
            'processor': platform.processor(),
            'node': platform.node()
        }
    
    def _check_admin_privileges(self) -> bool:
        """检查是否具有管理员权限"""
        try:
            if platform.system() == "Windows":
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin()
            else:
                return os.getuid() == 0 if hasattr(os, 'getuid') else False
        except:
            return False
    
    def _get_user_directory(self) -> Path:
        """获取用户配置文件目录"""
        if platform.system() == "Windows":
            # Windows: 使用用户目录下的隐藏文件夹
            user_dir = Path.home() / ".zimage_batch_tool"
        elif platform.system() == "Darwin":  # macOS
            user_dir = Path.home() / "Library" / "Application Support" / "Z-Image-Batch-Tool"
        else:  # Linux and others
            user_dir = Path.home() / ".local" / "share" / "zimage-batch-tool"
        
        # 确保目录存在
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    
    def _get_temp_directory(self) -> Path:
        """获取临时目录"""
        import tempfile
        temp_dir = Path(tempfile.gettempdir()) / "zimage_batch_tool"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir
    
    def get_config_dir(self) -> Path:
        """获取配置文件目录"""
        config_dir = self.user_dir / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir
    
    def get_cache_dir(self) -> Path:
        """获取缓存目录"""
        cache_dir = self.user_dir / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    
    def get_models_dir(self) -> Path:
        """获取模型目录"""
        models_dir = self.user_dir / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        return models_dir
    
    def get_logs_dir(self) -> Path:
        """获取日志目录"""
        logs_dir = self.user_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir
    
    def get_venv_base_dir(self) -> Path:
        """获取虚拟环境基础目录"""
        venv_dir = self.user_dir / "environments"
        venv_dir.mkdir(parents=True, exist_ok=True)
        return venv_dir
    
    def get_comfyui_dir(self) -> Path:
        """获取ComfyUI安装目录"""
        comfyui_dir = self.user_dir / "comfyui"
        comfyui_dir.mkdir(parents=True, exist_ok=True)
        return comfyui_dir
    
    def get_webui_dir(self) -> Path:
        """获取WebUI安装目录"""
        webui_dir = self.user_dir / "webui"
        webui_dir.mkdir(parents=True, exist_ok=True)
        return webui_dir
    
    def get_output_dir(self) -> Path:
        """获取输出目录"""
        output_dir = self.user_dir / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir
    
    def get_python_executable(self, venv_path: Path) -> str:
        """获取虚拟环境中的Python可执行文件路径"""
        if self.is_windows:
            return str(venv_path / "Scripts" / "python.exe")
        else:
            return str(venv_path / "bin" / "python")
    
    def get_pip_executable(self, venv_path: Path) -> str:
        """获取虚拟环境中的pip可执行文件路径"""
        if self.is_windows:
            return str(venv_path / "Scripts" / "pip.exe")
        else:
            return str(venv_path / "bin" / "pip")
    
    def create_venv(self, venv_name: str, python_version: str = "3.10") -> Dict[str, str]:
        """创建虚拟环境的统一接口"""
        venv_path = self.get_venv_base_dir() / venv_name
        
        try:
            # 创建虚拟环境
            if self.is_windows:
                # Windows特殊处理
                cmd = [sys.executable, "-m", "venv", str(venv_path)]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            else:
                cmd = [sys.executable, "-m", "venv", str(venv_path)]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            
            return {
                "success": True,
                "python_exe": self.get_python_executable(venv_path),
                "pip_exe": self.get_pip_executable(venv_path),
                "venv_path": str(venv_path)
            }
        except subprocess.CalledProcessError as e:
            return {
                "success": False,
                "error": f"创建虚拟环境失败: {e.stderr}"
            }
    
    def safe_execute_command(self, cmd: list, shell: bool = None, **kwargs) -> subprocess.CompletedProcess:
        """安全执行命令的跨平台方法"""
        if shell is None:
            shell = self.is_windows
        
        # Windows特定的命令处理
        if self.is_windows:
            # 确保命令使用正确的shell
            if not shell:
                # 尝试使用Windows的cmd.exe
                cmd = ["cmd", "/c"] + cmd
            shell = True
        
        try:
            result = subprocess.run(cmd, shell=shell, capture_output=True, text=True, **kwargs)
            return result
        except Exception as e:
            # 记录错误但不崩溃
            print(f"命令执行失败: {e}")
            return subprocess.CompletedProcess(cmd, 1, "", str(e), "")
    
    def get_pip_index_url(self) -> str:
        """获取适合当前平台的pip镜像源"""
        if self.is_windows:
            # Windows用户可能需要不同的镜像源
            return "https://pypi.org/simple"
        else:
            return "https://pypi.org/simple"
    
    def normalize_path(self, path: Union[str, Path]) -> Path:
        """标准化路径，确保跨平台兼容性"""
        if isinstance(path, str):
            path = Path(path)
        
        # 转换相对路径为绝对路径
        if not path.is_absolute():
            path = Path.cwd() / path
        
        # Windows路径标准化
        if self.is_windows:
            # 确保使用正确的路径分隔符
            path = path.resolve()
        
        return path
    
    def check_permissions(self, path: Path, check_write: bool = True) -> bool:
        """检查路径权限"""
        try:
            if check_write:
                # 尝试写入权限
                test_file = path / ".permission_test"
                test_file.touch()
                test_file.unlink()
            else:
                # 尝试读取权限
                path.stat()
            return True
        except (PermissionError, OSError):
            return False
    
    def get_default_shell(self) -> str:
        """获取默认shell"""
        if self.is_windows:
            return "cmd"
        else:
            return "bash"
    
    def get_file_executable_flags(self) -> Dict[str, Any]:
        """获取文件执行权限标志"""
        if self.is_windows:
            return {"is_executable": True}  # Windows不区分可执行权限
        else:
            return {"is_executable": os.access}
    
    def log_platform_info(self) -> None:
        """记录平台信息"""
        print(f"\n=== 平台信息 ===")
        print(f"系统: {self.platform_info['system']}")
        print(f"是否为Windows: {self.platform_info['is_windows']}")
        print(f"管理员权限: {self.platform_info['is_admin']}")
        print(f"Python路径: {self.platform_info['python_executable']}")
        print(f"Python版本: {self.platform_info['python_version']}")
        print(f"架构: {self.platform_info['architecture']}")
        print(f"节点: {self.platform_info['node']}")
        print(f"用户目录: {self.user_dir}")
        print(f"临时目录: {self.temp_dir}")
        print(f"==================\n")


# 全局兼容性管理器实例
compat_manager = WindowsCompatibilityManager()

# 便捷函数
def is_windows() -> bool:
    """检查是否为Windows系统"""
    return compat_manager.is_windows

def get_platform_info() -> Dict[str, Any]:
    """获取平台信息"""
    return compat_manager.platform_info

def get_user_dir() -> Path:
    """获取用户目录"""
    return compat_manager.user_dir

def get_temp_dir() -> Path:
    """获取临时目录"""
    return compat_manager.temp_dir

def get_config_dir() -> Path:
    """获取配置目录"""
    return compat_manager.get_config_dir()

def get_models_dir() -> Path:
    """获取模型目录"""
    return compat_manager.get_models_dir()

def get_logs_dir() -> Path:
    """获取日志目录"""
    return compat_manager.get_logs_dir()

def get_python_exe(venv_path: Path) -> str:
    """获取Python可执行文件路径"""
    return compat_manager.get_python_executable(venv_path)

def get_pip_exe(venv_path: Path) -> str:
    """获取pip可执行文件路径"""
    return compat_manager.get_pip_executable(venv_path)

def normalize_path(path: Union[str, Path]) -> Path:
    """标准化路径"""
    return compat_manager.normalize_path(path)

def safe_execute(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    """安全执行命令"""
    return compat_manager.safe_execute_command(cmd, **kwargs)

def check_permissions(path: Path, write: bool = True) -> bool:
    """检查权限"""
    return compat_manager.check_permissions(path, write)

def log_platform():
    """记录平台信息"""
    compat_manager.log_platform_info()

def get_pip_index_url() -> str:
    """获取适合当前平台的pip镜像源"""
    return compat_manager.get_pip_index_url()