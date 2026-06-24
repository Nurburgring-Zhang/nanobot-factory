"""
ComfyUI控制器模块
支持：启动/停止/更新/工作区管理/扩展包管理

跨平台ComfyUI进程管理、工作流控制、扩展包管理的完整解决方案
支持Windows和Linux系统，提供进程池管理、API调用和WebSocket通信功能
"""

import subprocess
import os
import sys
import json
import time
import signal
import threading
import queue
import shutil
import re
import urllib.request
import urllib.error
import hashlib
import tempfile
from pathlib import Path
from typing import Optional, Dict, List, Callable, Any, Union
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from abc import ABC, abstractmethod
import logging
import socket
import webbrowser

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ComfyUIStatus(Enum):
    """ComfyUI状态枚举"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class ComfyUIError(Exception):
    """ComfyUI相关错误基类"""
    pass


class InstallationError(ComfyUIError):
    """安装错误"""
    pass


class WorkspaceError(ComfyUIError):
    """工作区错误"""
    pass


class ProcessError(ComfyUIError):
    """进程管理错误"""
    pass


@dataclass
class ComfyUIConfig:
    """ComfyUI配置数据类"""
    port: int = 8188
    listen_address: str = "127.0.0.1"
    auto_open_browser: bool = True
    extra_args: List[str] = field(default_factory=list)
    cuda_device: int = 0
    force_fp16: bool = False
    enable_cors: bool = True
    temp_dir: str = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'port': self.port,
            'listen_address': self.listen_address,
            'auto_open_browser': self.auto_open_browser,
            'extra_args': self.extra_args,
            'cuda_device': self.cuda_device,
            'force_fp16': self.force_fp16,
            'enable_cors': self.enable_cors,
            'temp_dir': self.temp_dir
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ComfyUIConfig':
        """从字典创建"""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})


@dataclass
class WorkflowInfo:
    """工作流信息数据类"""
    id: str
    name: str
    path: str
    created_at: datetime = None
    modified_at: datetime = None
    nodes_count: int = 0
    category: str = "default"
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'path': self.path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'modified_at': self.modified_at.isoformat() if self.modified_at else None,
            'nodes_count': self.nodes_count,
            'category': self.category
        }


@dataclass
class CustomNodeInfo:
    """自定义节点信息数据类"""
    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    installed_at: datetime = None
    update_available: bool = False
    dependencies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'author': self.author,
            'installed_at': self.installed_at.isoformat() if self.installed_at else None,
            'update_available': self.update_available,
            'dependencies': self.dependencies
        }


@dataclass
class ModelInfo:
    """模型信息数据类"""
    id: str
    name: str
    type: str
    path: str
    size: int = 0
    hash: str = ""
    download_url: str = ""
    installed_at: datetime = None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'path': self.path,
            'size': self.size,
            'hash': self.hash,
            'download_url': self.download_url,
            'installed_at': self.installed_at.isoformat() if self.installed_at else None
        }


class ProcessPool:
    """进程池管理器"""
    
    def __init__(self, max_processes: int = 3):
        self.max_processes = max_processes
        self.processes: Dict[str, subprocess.Popen] = {}
        self.process_lock = threading.Lock()
        self._cleanup_thread = None
        self._running = True
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup_loop():
            while self._running:
                self._cleanup_terminated_processes()
                time.sleep(5)
        
        self._cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def _cleanup_terminated_processes(self):
        """清理已终止的进程"""
        with self.process_lock:
            terminated = []
            for name, proc in self.processes.items():
                if proc.poll() is not None:
                    terminated.append(name)
            
            for name in terminated:
                del self.processes[name]
                logger.info(f"Cleaned up terminated process: {name}")
    
    def add_process(self, name: str, process: subprocess.Popen) -> bool:
        """添加进程到池中"""
        with self.process_lock:
            if len(self.processes) >= self.max_processes:
                logger.warning(f"Process pool full, cannot add: {name}")
                return False
            
            self.processes[name] = process
            logger.info(f"Added process to pool: {name}")
            return True
    
    def remove_process(self, name: str) -> Optional[subprocess.Popen]:
        """移除进程"""
        with self.process_lock:
            return self.processes.pop(name, None)
    
    def get_process(self, name: str) -> Optional[subprocess.Popen]:
        """获取进程"""
        with self.process_lock:
            return self.processes.get(name)
    
    def get_all_processes(self) -> Dict[str, subprocess.Popen]:
        """获取所有进程"""
        with self.process_lock:
            return dict(self.processes)
    
    def stop_all(self, force: bool = False):
        """停止所有进程"""
        with self.process_lock:
            for name, proc in self.processes.items():
                try:
                    if force:
                        proc.terminate()
                    else:
                        proc.terminate()
                        proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                except Exception as e:
                    logger.error(f"Error stopping process {name}: {e}")
            
            self.processes.clear()
    
    def shutdown(self):
        """关闭进程池"""
        self._running = False
        self.stop_all(force=True)


class LogWatcher:
    """日志监视器"""
    
    def __init__(self):
        self.log_lines = queue.Queue(maxsize=10000)
        self.watchers: List[Callable[[str], None]] = []
        self._running = False
        self._thread = None
    
    def add_watcher(self, callback: Callable[[str], None]):
        """添加日志观察者"""
        self.watchers.append(callback)
    
    def remove_watcher(self, callback: Callable[[str], None]):
        """移除日志观察者"""
        if callback in self.watchers:
            self.watchers.remove(callback)
    
    def put(self, line: str):
        """添加日志行"""
        self.log_lines.put(line)
        
        # 通知所有观察者
        for watcher in self.watchers:
            try:
                watcher(line)
            except Exception as e:
                logger.error(f"Error in log watcher callback: {e}")
    
    def get_lines(self, lines: int = 100) -> List[str]:
        """获取最近的日志行"""
        result = []
        try:
            while len(result) < lines:
                result.append(self.log_lines.get_nowait())
        except queue.Empty:
            pass
        
        # 重新放回队列
        for line in result:
            self.log_lines.put(line)
        
        return result[-lines:]
    
    def start(self):
        """启动日志监视"""
        self._running = True
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._watch_loop, daemon=True)
            self._thread.start()
    
    def stop(self):
        """停止日志监视"""
        self._running = False
    
    def _watch_loop(self):
        """监视循环"""
        while self._running:
            time.sleep(0.1)


class ComfyUIController:
    """
    ComfyUI主控制器
    
    负责管理ComfyUI进程的启动、停止、配置和监控
    支持跨平台（Windows/Linux）运行
    
    Attributes:
        comfyui_path: ComfyUI安装路径
        config: ComfyUI配置对象
        status: 当前状态
    
    Example:
        >>> controller = ComfyUIController("/path/to/ComfyUI")
        >>> controller.start()
        >>> print(controller.get_status())
        >>> controller.stop()
    """
    
    def __init__(self, comfyui_path: str = None, config: dict = None):
        """
        初始化ComfyUI控制器
        
        Args:
            comfyui_path: ComfyUI安装目录路径，默认为当前目录下的ComfyUI
            config: 配置字典，可选，包含port、listen_address等配置
        
        Raises:
            ValueError: 当路径无效或配置错误时
        """
        # 设置ComfyUI路径
        if comfyui_path is None:
            comfyui_path = os.path.join(os.getcwd(), "ComfyUI")
        
        self.comfyui_path = Path(comfyui_path)
        
        if not self.comfyui_path.exists():
            logger.warning(f"ComfyUI path does not exist: {comfyui_path}")
        
        # 初始化配置
        self.config = ComfyUIConfig()
        if config:
            self.update_config(config)
        
        # 进程相关
        self.process: Optional[subprocess.Popen] = None
        self.status = ComfyUIStatus.STOPPED
        self.process_lock = threading.Lock()
        
        # 进程池
        self.process_pool = ProcessPool(max_processes=3)
        
        # 日志监视器
        self.log_watcher = LogWatcher()
        self._log_thread = None
        
        # API端点
        self.api_base_url = f"http://{self.config.listen_address}:{self.config.port}"
        self.ws_url = f"ws://{self.config.listen_address}:{self.config.port}/ws"
        
        # 工作目录
        self.workdir = self.comfyui_path
        
        logger.info(f"ComfyUIController initialized with path: {comfyui_path}")
    
    @property
    def port(self) -> int:
        """获取端口"""
        return self.config.port
    
    @property
    def listen_address(self) -> str:
        """获取监听地址"""
        return self.config.listen_address
    
    @property
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self.status == ComfyUIStatus.RUNNING
    
    def _detect_platform(self) -> str:
        """检测操作系统平台"""
        if sys.platform.startswith('win'):
            return 'windows'
        elif sys.platform.startswith('linux'):
            return 'linux'
        elif sys.platform.startswith('darwin'):
            return 'macos'
        else:
            return 'unknown'
    
    def _get_python_executable(self) -> str:
        """获取Python解释器路径"""
        return sys.executable
    
    def _get_main_script(self) -> str:
        """获取主脚本路径"""
        platform = self._detect_platform()
        if platform == 'windows':
            script = "python_embeded\\python.exe" if os.path.exists(os.path.join(self.comfyui_path, "python_embeded", "python.exe")) else "python.exe"
        else:
            script = "python3"
        
        # 检查自定义python路径
        custom_python = self.comfyui_path / script
        if custom_python.exists():
            return str(custom_python)
        
        return script
    
    def _build_start_args(self, extra_args: List[str] = None) -> List[str]:
        """构建启动参数"""
        args = []
        
        # 添加端口
        args.extend(["--port", str(self.config.port)])
        
        # 添加监听地址
        args.extend(["--listen", self.config.listen_address])
        
        # 添加CUDA设备
        if self.config.cuda_device >= 0:
            args.extend(["--cuda-device", str(self.config.cuda_device)])
        
        # 强制FP16
        if self.config.force_fp16:
            args.append("--force-fp16")
        
        # 启用CORS
        if self.config.enable_cors:
            args.append("--enable-cors")
        
        # 添加临时目录
        if self.config.temp_dir:
            args.extend(["--temp-dir", self.config.temp_dir])
        
        # 添加额外参数
        if extra_args:
            args.extend(extra_args)
        
        return args
    
    def start(self, extra_args: List[str] = None, auto_open_browser: bool = True) -> bool:
        """
        启动ComfyUI进程
        
        Args:
            extra_args: 额外的命令行参数
            auto_open_browser: 是否自动打开浏览器
        
        Returns:
            bool: 启动是否成功
        
        Raises:
            ProcessError: 当进程启动失败时
        """
        with self.process_lock:
            if self.status == ComfyUIStatus.RUNNING:
                logger.warning("ComfyUI is already running")
                return True
            
            if self.status == ComfyUIStatus.STARTING:
                logger.warning("ComfyUI is already starting")
                return False
            
            self.status = ComfyUIStatus.STARTING
            logger.info("Starting ComfyUI...")
            
            try:
                # 检测平台
                platform = self._detect_platform()
                
                # 构建命令
                python_exec = self._get_python_executable()
                main_script = self.comfyui_path / "main.py"
                
                if not main_script.exists():
                    raise ProcessError(f"Main script not found: {main_script}")
                
                args = [python_exec, str(main_script)]
                args.extend(self._build_start_args(extra_args))
                
                # 启动进程
                startupinfo = None
                if platform == 'windows':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                
                self.process = subprocess.Popen(
                    args,
                    cwd=str(self.comfyui_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    startupinfo=startupinfo,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                # 添加到进程池
                self.process_pool.add_process("comfyui_main", self.process)
                
                # 等待进程启动
                if self._wait_for_ready(timeout=60):
                    self.status = ComfyUIStatus.RUNNING
                    logger.info("ComfyUI started successfully")
                    
                    # 启动日志监视
                    self._start_log_watcher()
                    
                    # 自动打开浏览器
                    if auto_open_browser and self.config.auto_open_browser:
                        self._open_browser()
                    
                    return True
                else:
                    raise ProcessError("ComfyUI failed to start within timeout")
                
            except Exception as e:
                self.status = ComfyUIStatus.ERROR
                logger.error(f"Failed to start ComfyUI: {e}")
                raise ProcessError(f"Failed to start ComfyUI: {e}")
    
    def _wait_for_ready(self, timeout: int = 60) -> bool:
        """等待ComfyUI就绪"""
        start_time = time.time()
        check_interval = 1
        
        while time.time() - start_time < timeout:
            # 检查进程是否退出
            if self.process and self.process.poll() is not None:
                stderr = self.process.stderr.read() if self.process.stderr else ""
                raise ProcessError(f"ComfyUI process terminated unexpectedly: {stderr}")
            
            # 检查端口是否可用
            if self._check_port_available(self.config.port):
                logger.info(f"ComfyUI is ready on port {self.config.port}")
                return True
            
            time.sleep(check_interval)
        
        return False
    
    def _check_port_available(self, port: int) -> bool:
        """检查端口是否可用"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(1)
            result = sock.connect_ex((self.config.listen_address, port))
            return result == 0
        except socket.error:
            return False
        finally:
            sock.close()
    
    def _open_browser(self):
        """打开浏览器"""
        try:
            url = f"http://{self.config.listen_address}:{self.config.port}"
            webbrowser.open(url)
            logger.info(f"Opened browser for {url}")
        except Exception as e:
            logger.warning(f"Failed to open browser: {e}")
    
    def _start_log_watcher(self):
        """启动日志监视线程"""
        def read_logs():
            if self.process and self.process.stdout:
                while self.status == ComfyUIStatus.RUNNING:
                    try:
                        line = self.process.stdout.readline()
                        if not line:
                            break
                        self.log_watcher.put(line.strip())
                    except Exception as e:
                        logger.error(f"Error reading logs: {e}")
                        break
        
        self._log_thread = threading.Thread(target=read_logs, daemon=True)
        self._log_thread.start()
        self.log_watcher.start()
    
    def stop(self, force: bool = False) -> bool:
        """
        停止ComfyUI进程
        
        Args:
            force: 是否强制终止
        
        Returns:
            bool: 停止是否成功
        """
        with self.process_lock:
            if self.status == ComfyUIStatus.STOPPED:
                logger.info("ComfyUI is already stopped")
                return True
            
            if self.status == ComfyUIStatus.STOPPING:
                logger.warning("ComfyUI is already stopping")
                return False
            
            self.status = ComfyUIStatus.STOPPING
            logger.info("Stopping ComfyUI...")
            
            try:
                if self.process:
                    if force:
                        self.process.kill()
                    else:
                        # 尝试正常终止
                        platform = self._detect_platform()
                        if platform == 'windows':
                            self.process.terminate()
                        else:
                            self.process.send_signal(signal.SIGTERM)
                        
                        try:
                            self.process.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            logger.warning("Process did not terminate in time, forcing...")
                            self.process.kill()
                            self.process.wait(timeout=5)
                    
                    # 从进程池移除
                    self.process_pool.remove_process("comfyui_main")
                    self.process = None
                
                self.status = ComfyUIStatus.STOPPED
                self.log_watcher.stop()
                logger.info("ComfyUI stopped successfully")
                return True
                
            except Exception as e:
                self.status = ComfyUIStatus.ERROR
                logger.error(f"Error stopping ComfyUI: {e}")
                return False
    
    def restart(self) -> bool:
        """
        重启ComfyUI进程
        
        Returns:
            bool: 重启是否成功
        """
        logger.info("Restarting ComfyUI...")
        
        # 先停止
        self.stop()
        
        # 等待一会儿确保完全停止
        time.sleep(2)
        
        # 再启动
        try:
            return self.start()
        except ProcessError as e:
            logger.error(f"Failed to restart ComfyUI: {e}")
            return False
    
    def get_status(self) -> ComfyUIStatus:
        """
        获取ComfyUI状态
        
        Returns:
            ComfyUIStatus: 当前状态
        """
        with self.process_lock:
            if self.status == ComfyUIStatus.RUNNING and self.process:
                # 检查进程是否真的在运行
                if self.process.poll() is not None:
                    self.status = ComfyUIStatus.ERROR
            
            return self.status
    
    def set_port(self, port: int):
        """
        设置端口
        
        Args:
            port: 端口号
        """
        if not isinstance(port, int) or port < 1 or port > 65535:
            raise ValueError(f"Invalid port number: {port}")
        
        self.config.port = port
        self.api_base_url = f"http://{self.config.listen_address}:{self.config.port}"
        logger.info(f"Port set to: {port}")
    
    def set_listen_address(self, address: str):
        """
        设置监听地址
        
        Args:
            address: IP地址或主机名
        """
        self.config.listen_address = address
        self.api_base_url = f"http://{address}:{self.config.port}"
        logger.info(f"Listen address set to: {address}")
    
    def get_config(self) -> dict:
        """
        获取配置
        
        Returns:
            dict: 配置字典
        """
        return self.config.to_dict()
    
    def update_config(self, config: dict):
        """
        更新配置
        
        Args:
            config: 配置字典
        """
        if not config:
            return
        
        valid_keys = set(ComfyUIConfig.__annotations__.keys())
        update_dict = {k: v for k, v in config.items() if k in valid_keys}
        
        for key, value in update_dict.items():
            setattr(self.config, key, value)
        
        # 更新API URL
        self.api_base_url = f"http://{self.config.listen_address}:{self.config.port}"
        logger.info(f"Configuration updated: {update_dict}")
    
    def get_logs(self, lines: int = 100) -> List[str]:
        """
        获取日志
        
        Args:
            lines: 获取的行数
        
        Returns:
            List[str]: 日志行列表
        """
        return self.log_watcher.get_lines(lines)
    
    def follow_logs(self, callback: Callable[[str], None] = None, lines: int = 50):
        """
        跟踪日志
        
        Args:
            callback: 日志回调函数
            lines: 初始获取的行数
        """
        if callback:
            self.log_watcher.add_watcher(callback)
        
        # 返回初始日志
        return self.get_logs(lines)
    
    def get_api_url(self, endpoint: str = "") -> str:
        """
        获取API URL
        
        Args:
            endpoint: API端点
        
        Returns:
            str: 完整的API URL
        """
        base = self.api_base_url
        if endpoint:
            return f"{base}{endpoint}"
        return base
    
    def api_request(self, endpoint: str, method: str = "GET", data: dict = None) -> dict:
        """
        发送API请求
        
        Args:
            endpoint: API端点
            method: 请求方法
            data: 请求数据
        
        Returns:
            dict: 响应数据
        
        Raises:
            ProcessError: 当请求失败时
        """
        import urllib.request as req
        import urllib.parse as parse
        
        url = self.get_api_url(endpoint)
        
        try:
            if method == "GET":
                request = req.Request(url, method="GET")
            elif method in ("POST", "PUT"):
                json_data = json.dumps(data).encode('utf-8') if data else b'{}'
                request = req.Request(url, data=json_data, method=method)
                request.add_header("Content-Type", "application/json")
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            with req.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
                
        except urllib.error.HTTPError as e:
            raise ProcessError(f"HTTP error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise ProcessError(f"URL error: {e.reason}")
        except Exception as e:
            raise ProcessError(f"API request failed: {e}")
    
    def get_system_stats(self) -> dict:
        """
        获取系统统计信息
        
        Returns:
            dict: 系统统计信息
        """
        try:
            return self.api_request("/system_stats", "GET")
        except ProcessError:
            return {}
    
    def get_queue_status(self) -> dict:
        """
        获取队列状态
        
        Returns:
            dict: 队列状态信息
        """
        try:
            return self.api_request("/queue", "GET")
        except ProcessError:
            return {"queue_pending": 0, "queue_running": 0}
    
    def __del__(self):
        """析构函数"""
        try:
            self.stop()
        except Exception:
            pass


class ComfyUIInstallationManager:
    """
    ComfyUI安装管理器
    
    负责ComfyUI的安装、更新、版本检测等功能
    支持从GitHub拉取代码、处理依赖关系
    
    Attributes:
        base_path: 安装根目录
        comfyui_path: ComfyUI安装路径
    
    Example:
        >>> manager = ComfyUIInstallationManager("/path/to/install")
        >>> manager.install()
        >>> version = manager.get_installed_version()
    """
    
    GITHUB_REPO = "comfyanonymous/ComfyUI"
    GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}"
    
    def __init__(self, base_path: str = None):
        """
        初始化安装管理器
        
        Args:
            base_path: 安装根目录，默认为当前目录
        """
        if base_path is None:
            base_path = os.getcwd()
        
        self.base_path = Path(base_path)
        self.comfyui_path = self.base_path / "ComfyUI"
        
        # Git相关
        self.git_executable = self._find_git()
        
        logger.info(f"InstallationManager initialized at: {base_path}")
    
    def _find_git(self) -> str:
        """查找Git可执行文件"""
        # 优先使用自定义Git
        custom_git = self.base_path / "git" / "bin" / "git.exe"
        if custom_git.exists():
            return str(custom_git)
        
        # 系统Git
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return "git"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return "git"
    
    def _run_command(self, cmd: List[str], cwd: str = None, progress_callback: Callable = None) -> subprocess.CompletedProcess:
        """运行命令并支持进度回调"""
        logger.info(f"Running command: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or str(self.base_path),
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if progress_callback and result.stdout:
                progress_callback(0.5, result.stdout[:500])
            
            return result
            
        except subprocess.TimeoutExpired as e:
            raise InstallationError(f"Command timed out: {' '.join(cmd)}")
        except Exception as e:
            raise InstallationError(f"Command failed: {e}")
    
    def _download_file(self, url: str, output_path: Path, progress_callback: Callable[[float, str], None] = None) -> bool:
        """下载文件"""
        try:
            def report_progress(block_num, block_size, total_size):
                if progress_callback and total_size > 0:
                    progress = min(block_num * block_size / total_size, 1.0)
                    progress_callback(progress, f"Downloaded {block_num * block_size / 1024 / 1024:.1f} MB")
            
            urllib.request.urlretrieve(url, output_path, reporthook=report_progress)
            return True
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False
    
    def install(self, branch: str = "master", install_models: bool = True, 
                progress_callback: Callable[[float, str], None] = None) -> bool:
        """
        安装ComfyUI
        
        Args:
            branch: Git分支，默认为master
            install_models: 是否安装基础模型
            progress_callback: 进度回调函数，接收(进度百分比, 状态消息)
        
        Returns:
            bool: 安装是否成功
        
        Raises:
            InstallationError: 当安装失败时
        """
        if progress_callback:
            progress_callback(0.0, "Starting installation...")
        
        try:
            # 检查是否已安装
            if self.comfyui_path.exists():
                logger.info("ComfyUI already installed, skipping installation")
                if progress_callback:
                    progress_callback(1.0, "ComfyUI already installed")
                return True
            
            # 创建目录
            self.base_path.mkdir(parents=True, exist_ok=True)
            
            if progress_callback:
                progress_callback(0.1, f"Cloning {branch} branch...")
            
            # 克隆仓库
            clone_cmd = [
                self.git_executable, "clone",
                "--branch", branch,
                "--depth", "1",
                f"https://github.com/{self.GITHUB_REPO}.git",
                str(self.comfyui_path)
            ]
            
            result = self._run_command(clone_cmd, progress_callback=progress_callback)
            
            if result.returncode != 0:
                raise InstallationError(f"Git clone failed: {result.stderr}")
            
            if progress_callback:
                progress_callback(0.4, "Cloned successfully, checking dependencies...")
            
            # 检查依赖
            if not self.check_dependencies():
                if progress_callback:
                    progress_callback(0.5, "Installing dependencies...")
                self.install_dependencies(progress_callback=progress_callback)
            
            if progress_callback:
                progress_callback(0.9, "Installation complete!")
            
            logger.info("ComfyUI installation completed")
            return True
            
        except Exception as e:
            error_msg = f"Installation failed: {e}"
            logger.error(error_msg)
            if progress_callback:
                progress_callback(0.0, error_msg)
            raise InstallationError(error_msg)
    
    def update(self, clean: bool = False, progress_callback: Callable[[float, str], None] = None) -> bool:
        """
        更新ComfyUI
        
        Args:
            clean: 是否执行清洁更新（会丢失本地修改）
            progress_callback: 进度回调函数
        
        Returns:
            bool: 更新是否成功
        
        Raises:
            InstallationError: 当更新失败时
        """
        if progress_callback:
            progress_callback(0.0, "Starting update...")
        
        try:
            if not self.comfyui_path.exists():
                raise InstallationError("ComfyUI not installed")
            
            # 获取当前版本
            current = self.get_installed_version()
            
            if progress_callback:
                progress_callback(0.2, "Fetching latest changes...")
            
            # 拉取最新代码
            if clean:
                reset_cmd = [self.git_executable, "reset", "--hard", "HEAD"]
                self._run_command(reset_cmd, cwd=str(self.comfyui_path))
            
            pull_cmd = [self.git_executable, "pull", "origin", "master"]
            result = self._run_command(pull_cmd, cwd=str(self.comfyui_path))
            
            if result.returncode != 0:
                raise InstallationError(f"Git pull failed: {result.stderr}")
            
            # 更新依赖
            if progress_callback:
                progress_callback(0.7, "Updating dependencies...")
            self.install_dependencies(progress_callback=progress_callback)
            
            new_version = self.get_installed_version()
            
            if progress_callback:
                progress_callback(1.0, f"Updated from {current} to {new_version}")
            
            logger.info(f"ComfyUI updated: {current} -> {new_version}")
            return True
            
        except Exception as e:
            error_msg = f"Update failed: {e}"
            logger.error(error_msg)
            raise InstallationError(error_msg)
    
    def check_updates(self) -> dict:
        """
        检查更新
        
        Returns:
            dict: 包含当前版本和最新版本信息
        """
        current = self.get_installed_version()
        latest = self.get_latest_version()
        
        return {
            'current': current,
            'latest': latest,
            'update_available': current != latest,
            'behind_by': self._compare_versions(current, latest) if current and latest else 0
        }
    
    def get_installed_version(self) -> str:
        """
        获取已安装版本
        
        Returns:
            str: 版本号，格式如 "2024.01.15.0"
        """
        if not self.comfyui_path.exists():
            return ""
        
        git_dir = self.comfyui_path / ".git"
        if not git_dir.exists():
            return ""
        
        try:
            result = subprocess.run(
                [self.git_executable, "rev-parse", "HEAD"],
                cwd=str(self.comfyui_path),
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                return result.stdout.strip()[:8]
            
        except Exception as e:
            logger.error(f"Failed to get version: {e}")
        
        return ""
    
    def get_latest_version(self) -> str:
        """
        获取最新版本
        
        Returns:
            str: 最新版本号
        """
        try:
            url = f"{self.GITHUB_API_URL}/releases/latest"
            request = urllib.request.Request(url, headers={"User-Agent": "ComfyUI-Installer"})
            
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data.get('tag_name', '')
                
        except Exception as e:
            logger.error(f"Failed to get latest version: {e}")
            return ""
    
    def _compare_versions(self, v1: str, v2: str) -> int:
        """
        比较版本号
        
        Args:
            v1: 版本1
            v2: 版本2
        
        Returns:
            int: 负数表示v1较旧，正数表示v1较新，0表示相同
        """
        try:
            # 尝试解析为日期格式版本
            def parse_version(v):
                # 清理版本号
                v = re.sub(r'^v', '', v)
                parts = re.split(r'[\.\-]', v)
                return [int(p) if p.isdigit() else 0 for p in parts[:6]]
            
            p1 = parse_version(v1)
            p2 = parse_version(v2)
            
            for i in range(max(len(p1), len(p2))):
                n1 = p1[i] if i < len(p1) else 0
                n2 = p2[i] if i < len(p2) else 0
                if n1 != n2:
                    return n1 - n2
            
            return 0
            
        except Exception:
            return 0
    
    def check_dependencies(self) -> Dict[str, bool]:
        """
        检查Python依赖
        
        Returns:
            Dict[str, bool]: 依赖名称到是否满足的映射
        """
        requirements_file = self.comfyui_path / "requirements.txt"
        
        if not requirements_file.exists():
            return {}
        
        try:
            with open(requirements_file, 'r', encoding='utf-8') as f:
                requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            result = {}
            for req in requirements:
                # 解析依赖
                match = re.match(r'^([a-zA-Z0-9\-_]+)', req)
                if match:
                    package_name = match.group(1)
                    
                    # 检查是否已安装
                    try:
                        subprocess.run(
                            [sys.executable, "-m", "pip", "show", package_name],
                            capture_output=True,
                            timeout=10
                        )
                        result[package_name] = True
                    except Exception:
                        result[package_name] = False
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to check dependencies: {e}")
            return {}
    
    def install_dependencies(self, progress_callback: Callable[[float, str], None] = None) -> bool:
        """
        安装Python依赖
        
        Args:
            progress_callback: 进度回调函数
        
        Returns:
            bool: 安装是否成功
        
        Raises:
            InstallationError: 当安装失败时
        """
        requirements_file = self.comfyui_path / "requirements.txt"
        
        if not requirements_file.exists():
            logger.warning("No requirements.txt found")
            return True
        
        try:
            if progress_callback:
                progress_callback(0.0, "Installing Python dependencies...")
            
            # 使用pip安装
            install_cmd = [
                sys.executable, "-m", "pip", "install",
                "-r", str(requirements_file),
                "--quiet",
                "--no-warn-script-location"
            ]
            
            result = subprocess.run(
                install_cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                logger.warning(f"Pip install had issues: {result.stderr}")
            
            if progress_callback:
                progress_callback(1.0, "Dependencies installed")
            
            logger.info("Dependencies installation completed")
            return True
            
        except subprocess.TimeoutExpired:
            raise InstallationError("Dependencies installation timed out")
        except Exception as e:
            raise InstallationError(f"Failed to install dependencies: {e}")


class ComfyUIWorkspaceManager:
    """
    ComfyUI工作区管理器
    
    管理工作区创建、切换，以及工作流的加载和保存
    每个工作区独立存储工作流配置和输出
    
    Attributes:
        controller: ComfyUI控制器实例
        workspaces_path: 工作区根目录
    
    Example:
        >>> controller = ComfyUIController()
        >>> workspace_manager = ComfyUIWorkspaceManager(controller)
        >>> workspace_manager.create_workspace("my_project")
        >>> workspace_manager.switch_workspace("my_project")
        >>> workflow = workspace_manager.load_workflow("workflow.json")
    """
    
    def __init__(self, controller: ComfyUIController):
        """
        初始化工作区管理器
        
        Args:
            controller: ComfyUI控制器实例
        """
        self.controller = controller
        self.workspaces_path = controller.comfyui_path / "workspaces"
        self.current_workspace: Optional[str] = None
        self._ensure_workspaces_dir()
    
    def _ensure_workspaces_dir(self):
        """确保工作区目录存在"""
        if not self.workspaces_path.exists():
            self.workspaces_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created workspaces directory: {self.workspaces_path}")
    
    def _get_workspace_path(self, name: str) -> Path:
        """获取工作区路径"""
        return self.workspaces_path / name
    
    def _get_workflow_dir(self, workspace: str = None) -> Path:
        """获取工作流目录"""
        ws = workspace or self.current_workspace or "default"
        workflow_dir = self._get_workspace_path(ws) / "workflows"
        if not workflow_dir.exists():
            workflow_dir.mkdir(parents=True, exist_ok=True)
        return workflow_dir
    
    def _load_workflow_metadata(self, workflow_path: Path) -> dict:
        """加载工作流元数据"""
        try:
            with open(workflow_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return {
                'nodes_count': len(data.get('nodes', {})) if isinstance(data, dict) else 0,
                'last_modified': datetime.fromtimestamp(workflow_path.stat().st_mtime),
                'size': workflow_path.stat().st_size
            }
        except Exception:
            return {'nodes_count': 0, 'last_modified': None, 'size': 0}
    
    def create_workspace(self, name: str, base_workflow: str = None) -> bool:
        """
        创建工作区
        
        Args:
            name: 工作区名称
            base_workflow: 基础工作流文件路径（可选）
        
        Returns:
            bool: 创建是否成功
        
        Raises:
            WorkspaceError: 当创建失败时
        """
        try:
            ws_path = self._get_workspace_path(name)
            
            if ws_path.exists():
                logger.warning(f"Workspace already exists: {name}")
                return True
            
            # 创建工作区目录
            ws_path.mkdir(parents=True, exist_ok=True)
            (ws_path / "workflows").mkdir(exist_ok=True)
            (ws_path / "outputs").mkdir(exist_ok=True)
            (ws_path / "inputs").mkdir(exist_ok=True)
            
            # 创建工作区配置
            config = {
                'name': name,
                'created_at': datetime.now().isoformat(),
                'workflows': []
            }
            
            config_file = ws_path / ".workspace.json"
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
            
            # 复制基础工作流
            if base_workflow and os.path.exists(base_workflow):
                self.import_workflow(base_workflow, workspace=name)
            
            logger.info(f"Workspace created: {name}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to create workspace: {e}"
            logger.error(error_msg)
            raise WorkspaceError(error_msg)
    
    def delete_workspace(self, name: str) -> bool:
        """
        删除工作区
        
        Args:
            name: 工作区名称
        
        Returns:
            bool: 删除是否成功
        
        Raises:
            WorkspaceError: 当删除失败时
        """
        try:
            ws_path = self._get_workspace_path(name)
            
            if not ws_path.exists():
                logger.warning(f"Workspace does not exist: {name}")
                return True
            
            # 检查当前工作区
            if self.current_workspace == name:
                self.current_workspace = None
            
            # 删除目录
            shutil.rmtree(ws_path)
            
            logger.info(f"Workspace deleted: {name}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to delete workspace: {e}"
            logger.error(error_msg)
            raise WorkspaceError(error_msg)
    
    def list_workspaces(self) -> List[Dict]:
        """
        列出所有工作区
        
        Returns:
            List[Dict]: 工作区信息列表
        """
        if not self.workspaces_path.exists():
            return []
        
        workspaces = []
        
        for item in self.workspaces_path.iterdir():
            if item.is_dir():
                config_file = item / ".workspace.json"
                info = {
                    'name': item.name,
                    'path': str(item),
                    'workflows_count': len(list((item / "workflows").glob("*.json"))) if (item / "workflows").exists() else 0,
                    'is_current': item.name == self.current_workspace
                }
                
                if config_file.exists():
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                            info['created_at'] = config.get('created_at')
                            info['description'] = config.get('description', '')
                    except Exception:
                        pass
                
                workspaces.append(info)
        
        return sorted(workspaces, key=lambda x: x['name'])
    
    def switch_workspace(self, name: str) -> bool:
        """
        切换工作区
        
        Args:
            name: 工作区名称
        
        Returns:
            bool: 切换是否成功
        
        Raises:
            WorkspaceError: 当切换失败时
        """
        try:
            ws_path = self._get_workspace_path(name)
            
            if not ws_path.exists():
                raise WorkspaceError(f"Workspace does not exist: {name}")
            
            self.current_workspace = name
            logger.info(f"Switched to workspace: {name}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to switch workspace: {e}"
            logger.error(error_msg)
            raise WorkspaceError(error_msg)
    
    def get_current_workspace(self) -> str:
        """
        获取当前工作区
        
        Returns:
            str: 当前工作区名称，无则为"default"
        """
        return self.current_workspace or "default"
    
    def load_workflow(self, workflow_path: str) -> dict:
        """
        加载工作流
        
        Args:
            workflow_path: 工作流文件路径
        
        Returns:
            dict: 工作流数据
        
        Raises:
            WorkspaceError: 当加载失败时
        """
        try:
            path = Path(workflow_path)
            
            if not path.exists():
                raise WorkspaceError(f"Workflow file not found: {workflow_path}")
            
            with open(path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            
            logger.info(f"Loaded workflow: {workflow_path}")
            return workflow
            
        except json.JSONDecodeError as e:
            raise WorkspaceError(f"Invalid JSON in workflow: {e}")
        except Exception as e:
            error_msg = f"Failed to load workflow: {e}"
            logger.error(error_msg)
            raise WorkspaceError(error_msg)
    
    def save_workflow(self, workflow: dict, output_path: str) -> bool:
        """
        保存工作流
        
        Args:
            workflow: 工作流数据
            output_path: 输出文件路径
        
        Returns:
            bool: 保存是否成功
        
        Raises:
            WorkspaceError: 当保存失败时
        """
        try:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(workflow, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved workflow: {output_path}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to save workflow: {e}"
            logger.error(error_msg)
            raise WorkspaceError(error_msg)
    
    def list_workflows(self, workspace: str = None) -> List[Dict]:
        """
        列出工作流
        
        Args:
            workspace: 工作区名称，默认为当前工作区
        
        Returns:
            List[Dict]: 工作流信息列表
        """
        ws = workspace or self.current_workspace or "default"
        workflow_dir = self._get_workflow_dir(ws)
        
        if not workflow_dir.exists():
            return []
        
        workflows = []
        
        for item in workflow_dir.glob("*.json"):
            meta = self._load_workflow_metadata(item)
            workflows.append({
                'id': item.stem,
                'name': item.name,
                'path': str(item),
                'nodes_count': meta.get('nodes_count', 0),
                'last_modified': meta.get('last_modified'),
                'size': meta.get('size', 0)
            })
        
        return sorted(workflows, key=lambda x: x['last_modified'] or datetime.min, reverse=True)
    
    def export_workflow(self, workflow_id: str, output_path: str) -> bool:
        """
        导出工作流
        
        Args:
            workflow_id: 工作流ID
            output_path: 输出路径
        
        Returns:
            bool: 导出是否成功
        """
        try:
            workflows = self.list_workflows()
            workflow_info = next((w for w in workflows if w['id'] == workflow_id), None)
            
            if not workflow_info:
                raise WorkspaceError(f"Workflow not found: {workflow_id}")
            
            workflow = self.load_workflow(workflow_info['path'])
            return self.save_workflow(workflow, output_path)
            
        except Exception as e:
            error_msg = f"Failed to export workflow: {e}"
            logger.error(error_msg)
            raise WorkspaceError(error_msg)
    
    def import_workflow(self, workflow_path: str, workspace: str = None) -> str:
        """
        导入工作流
        
        Args:
            workflow_path: 源工作流文件路径
            workspace: 目标工作区，默认为当前工作区
        
        Returns:
            str: 导入后的工作流ID
        
        Raises:
            WorkspaceError: 当导入失败时
        """
        try:
            ws = workspace or self.current_workspace or "default"
            
            # 创建工作区（如果不存在）
            if not self._get_workspace_path(ws).exists():
                self.create_workspace(ws)
            
            # 加载源工作流
            workflow = self.load_workflow(workflow_path)
            
            # 生成新ID
            workflow_id = Path(workflow_path).stem
            
            # 保存到目标工作区
            output_dir = self._get_workflow_dir(ws)
            output_path = output_dir / f"{workflow_id}.json"
            
            self.save_workflow(workflow, str(output_path))
            
            logger.info(f"Imported workflow: {workflow_id}")
            return workflow_id
            
        except Exception as e:
            error_msg = f"Failed to import workflow: {e}"
            logger.error(error_msg)
            raise WorkspaceError(error_msg)


class ComfyUIPackageManager:
    """
    ComfyUI扩展包管理器
    
    负责管理自定义节点、模型安装和依赖检查
    支持从GitHub安装自定义节点和模型
    
    Attributes:
        controller: ComfyUI控制器实例
        custom_nodes_path: 自定义节点目录
        models_path: 模型目录
    
    Example:
        >>> controller = ComfyUIController()
        >>> pkg_manager = ComfyUIPackageManager(controller)
        >>> pkg_manager.install_custom_node("KJNodes")
        >>> nodes = pkg_manager.list_installed_nodes()
    """
    
    def __init__(self, controller: ComfyUIController):
        """
        初始化包管理器
        
        Args:
            controller: ComfyUI控制器实例
        """
        self.controller = controller
        self.custom_nodes_path = controller.comfyui_path / "custom_nodes"
        self.models_path = controller.comfyui_path / "models"
        
        # 确保目录存在
        self._ensure_directories()
    
    def _ensure_directories(self):
        """确保必要目录存在"""
        if not self.custom_nodes_path.exists():
            self.custom_nodes_path.mkdir(parents=True, exist_ok=True)
        
        if not self.models_path.exists():
            self.models_path.mkdir(parents=True, exist_ok=True)
    
    def _parse_git_url(self, url: str) -> tuple:
        """解析Git URL获取用户和仓库名"""
        # 支持多种格式
        patterns = [
            r'github\.com[/:]([^/]+)/([^/.]+)',
            r'https?://([^/]+)/([^/]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1), match.group(2)
        
        return None, None
    
    def _get_node_readme(self, node_path: Path) -> Optional[str]:
        """获取节点README"""
        readme_paths = ['README.md', 'README.txt', 'readme.md']
        
        for name in readme_paths:
            readme = node_path / name
            if readme.exists():
                try:
                    with open(readme, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # 尝试提取描述
                        lines = content.split('\n')
                        description = []
                        for line in lines[:20]:
                            if len(line.strip()) > 10:
                                description.append(line.strip())
                            if len(description) >= 3:
                                break
                        
                        return '\n'.join(description[:3])
                except Exception:
                    pass
        
        return ""
    
    def install_custom_node(self, node_id: str, 
                          progress_callback: Callable[[float, str], None] = None) -> bool:
        """
        安装自定义节点
        
        Args:
            node_id: 节点ID，可以是完整的Git URL或GitHub上的节点名
            progress_callback: 进度回调函数
        
        Returns:
            bool: 安装是否成功
        
        Raises:
            ComfyUIError: 当安装失败时
        """
        if progress_callback:
            progress_callback(0.0, f"Installing custom node: {node_id}")
        
        try:
            # 解析节点ID
            if node_id.startswith('http'):
                git_url = node_id if node_id.endswith('.git') else f"{node_id}.git"
            else:
                git_url = f"https://github.com/{node_id}.git"
            
            user, repo = self._parse_git_url(git_url)
            if not user or not repo:
                raise ComfyUIError(f"Invalid node ID: {node_id}")
            
            repo_name = repo.replace('.git', '')
            node_path = self.custom_nodes_path / repo_name
            
            # 检查是否已安装
            if node_path.exists():
                logger.info(f"Node already installed: {repo_name}")
                if progress_callback:
                    progress_callback(1.0, "Already installed")
                return True
            
            if progress_callback:
                progress_callback(0.3, f"Cloning {repo_name}...")
            
            # 克隆仓库
            clone_cmd = [
                "git", "clone",
                "--recursive",
                git_url,
                str(node_path)
            ]
            
            result = subprocess.run(
                clone_cmd,
                cwd=str(self.custom_nodes_path),
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise ComfyUIError(f"Git clone failed: {result.stderr}")
            
            if progress_callback:
                progress_callback(0.8, "Installing dependencies...")
            
            # 检查并安装依赖
            self._install_node_dependencies(node_path)
            
            if progress_callback:
                progress_callback(1.0, f"Successfully installed {repo_name}")
            
            logger.info(f"Custom node installed: {repo_name}")
            return True
            
        except subprocess.TimeoutExpired:
            raise ComfyUIError("Installation timed out")
        except Exception as e:
            error_msg = f"Failed to install custom node: {e}"
            logger.error(error_msg)
            raise ComfyUIError(error_msg)
    
    def uninstall_custom_node(self, node_id: str) -> bool:
        """
        卸载自定义节点
        
        Args:
            node_id: 节点ID
        
        Returns:
            bool: 卸载是否成功
        """
        try:
            node_path = self.custom_nodes_path / node_id
            
            if not node_path.exists():
                logger.warning(f"Node not found: {node_id}")
                return True
            
            shutil.rmtree(node_path)
            logger.info(f"Custom node uninstalled: {node_id}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to uninstall custom node: {e}"
            logger.error(error_msg)
            raise ComfyUIError(error_msg)
    
    def update_custom_node(self, node_id: str) -> bool:
        """
        更新自定义节点
        
        Args:
            node_id: 节点ID
        
        Returns:
            bool: 更新是否成功
        """
        try:
            node_path = self.custom_nodes_path / node_id
            
            if not node_path.exists():
                raise ComfyUIError(f"Node not installed: {node_id}")
            
            # Git pull
            pull_cmd = ["git", "pull", "origin", "master"]
            result = subprocess.run(
                pull_cmd,
                cwd=str(node_path),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.warning(f"Git pull had issues: {result.stderr}")
            
            # 更新子模块
            submodule_cmd = ["git", "submodule", "update", "--init", "--recursive"]
            subprocess.run(
                submodule_cmd,
                cwd=str(node_path),
                capture_output=True,
                text=True,
                timeout=120
            )
            
            logger.info(f"Custom node updated: {node_id}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to update custom node: {e}"
            logger.error(error_msg)
            raise ComfyUIError(error_msg)
    
    def list_installed_nodes(self) -> List[Dict]:
        """
        列出已安装的自定义节点
        
        Returns:
            List[Dict]: 节点信息列表
        """
        if not self.custom_nodes_path.exists():
            return []
        
        nodes = []
        
        for item in self.custom_nodes_path.iterdir():
            if item.is_dir():
                # 获取版本信息
                version = "unknown"
                try:
                    result = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=str(item),
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        version = result.stdout.strip()[:8]
                except Exception:
                    pass
                
                # 获取描述
                description = self._get_node_readme(item)
                
                nodes.append({
                    'id': item.name,
                    'name': item.name,
                    'version': version,
                    'description': description,
                    'path': str(item),
                    'dependencies_met': True
                })
        
        return sorted(nodes, key=lambda x: x['name'])
    
    def _install_node_dependencies(self, node_path: Path):
        """安装节点依赖"""
        # 检查是否有requirements.txt
        requirements_file = node_path / "requirements.txt"
        
        if requirements_file.exists():
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
            except Exception as e:
                logger.warning(f"Failed to install node dependencies: {e}")
        
        # 检查是否有setup.py
        setup_file = node_path / "setup.py"
        
        if setup_file.exists():
            try:
                subprocess.run(
                    [sys.executable, "setup.py", "develop"],
                    cwd=str(node_path),
                    capture_output=True,
                    text=True,
                    timeout=300
                )
            except Exception as e:
                logger.warning(f"Failed to run setup.py: {e}")
    
    def install_model(self, model_url: str, model_type: str,
                      progress_callback: Callable[[float, str], None] = None) -> bool:
        """
        安装模型
        
        Args:
            model_url: 模型下载URL
            model_type: 模型类型 (checkpoints, vae, loras, etc.)
            progress_callback: 进度回调函数
        
        Returns:
            bool: 安装是否成功
        """
        if progress_callback:
            progress_callback(0.0, f"Downloading {model_type} model...")
        
        try:
            # 获取模型目录
            model_dir = self.models_path / model_type
            model_dir.mkdir(parents=True, exist_ok=True)
            
            # 解析文件名
            filename = model_url.split('/')[-1]
            filename = filename.split('?')[0]  # 移除查询参数
            
            output_path = model_dir / filename
            
            if output_path.exists():
                logger.info(f"Model already exists: {filename}")
                if progress_callback:
                    progress_callback(1.0, "Already installed")
                return True
            
            if progress_callback:
                progress_callback(0.1, f"Downloading {filename}...")
            
            # 下载模型
            success = self._download_file(model_url, output_path, progress_callback)
            
            if not success:
                raise ComfyUIError("Failed to download model")
            
            if progress_callback:
                progress_callback(1.0, f"Model installed: {filename}")
            
            logger.info(f"Model installed: {model_type}/{filename}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to install model: {e}"
            logger.error(error_msg)
            raise ComfyUIError(error_msg)
    
    def _download_file(self, url: str, output_path: Path, 
                      progress_callback: Callable[[float, str], None] = None) -> bool:
        """下载文件"""
        try:
            def report_progress(block_num, block_size, total_size):
                if progress_callback and total_size > 0:
                    progress = min(block_num * block_size / total_size, 1.0)
                    downloaded_mb = block_num * block_size / 1024 / 1024
                    total_mb = total_size / 1024 / 1024
                    progress_callback(progress, f"{downloaded_mb:.1f} / {total_mb:.1f} MB")
            
            urllib.request.urlretrieve(url, output_path, reporthook=report_progress)
            return True
            
        except Exception as e:
            logger.error(f"Download failed: {e}")
            if output_path.exists():
                output_path.unlink()
            return False
    
    def list_models(self, model_type: str = None) -> List[Dict]:
        """
        列出模型
        
        Args:
            model_type: 模型类型过滤，None表示所有类型
        
        Returns:
            List[Dict]: 模型信息列表
        """
        if not self.models_path.exists():
            return []
        
        models = []
        
        type_filter = model_type if model_type else None
        
        for type_dir in self.models_path.iterdir():
            if not type_dir.is_dir():
                continue
            
            if type_filter and type_dir.name != type_filter:
                continue
            
            for model_file in type_dir.iterdir():
                if model_file.is_file():
                    stat = model_file.stat()
                    models.append({
                        'id': model_file.stem,
                        'name': model_file.name,
                        'type': type_dir.name,
                        'path': str(model_file),
                        'size': stat.st_size,
                        'size_formatted': self._format_size(stat.st_size)
                    })
        
        return sorted(models, key=lambda x: (x['type'], x['name']))
    
    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def check_node_dependencies(self, node_id: str) -> List[str]:
        """
        检查节点依赖
        
        Args:
            node_id: 节点ID
        
        Returns:
            List[str]: 缺失的依赖列表
        """
        try:
            node_path = self.custom_nodes_path / node_id
            
            if not node_path.exists():
                return []
            
            requirements_file = node_path / "requirements.txt"
            
            if not requirements_file.exists():
                return []
            
            missing = []
            
            with open(requirements_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # 提取包名
                    match = re.match(r'^([a-zA-Z0-9\-_]+)', line)
                    if match:
                        package_name = match.group(1)
                        
                        # 检查是否已安装
                        result = subprocess.run(
                            [sys.executable, "-m", "pip", "show", package_name],
                            capture_output=True,
                            timeout=10
                        )
                        
                        if result.returncode != 0:
                            missing.append(package_name)
            
            return missing
            
        except Exception as e:
            logger.error(f"Failed to check dependencies: {e}")
            return []
    
    def install_node_dependencies(self, node_id: str) -> bool:
        """
        安装节点依赖
        
        Args:
            node_id: 节点ID
        
        Returns:
            bool: 安装是否成功
        """
        try:
            node_path = self.custom_nodes_path / node_id
            
            if not node_path.exists():
                raise ComfyUIError(f"Node not found: {node_id}")
            
            self._install_node_dependencies(node_path)
            
            logger.info(f"Node dependencies installed: {node_id}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to install node dependencies: {e}"
            logger.error(error_msg)
            raise ComfyUIError(error_msg)


class ComfyUIManager:
    """
    ComfyUI综合管理器
    
    整合控制器、安装管理器、工作区管理器和包管理器
    提供统一的接口管理ComfyUI的各个方面
    
    Example:
        >>> manager = ComfyUIManager("/path/to/ComfyUI")
        >>> manager.install()
        >>> manager.start()
        >>> stats = manager.get_stats()
    """
    
    def __init__(self, base_path: str = None):
        """
        初始化综合管理器
        
        Args:
            base_path: ComfyUI根目录
        """
        if base_path is None:
            base_path = os.getcwd()
        
        # 初始化各个管理器
        self.controller = ComfyUIController(base_path)
        self.installer = ComfyUIInstallationManager(base_path)
        self.workspace_manager = ComfyUIWorkspaceManager(self.controller)
        self.package_manager = ComfyUIPackageManager(self.controller)
        
        logger.info(f"ComfyUIManager initialized at: {base_path}")
    
    def setup(self, install_models: bool = True,
              progress_callback: Callable[[float, str], None] = None) -> bool:
        """
        设置ComfyUI（安装+配置）
        
        Args:
            install_models: 是否安装基础模型
            progress_callback: 进度回调
        
        Returns:
            bool: 设置是否成功
        """
        try:
            if progress_callback:
                progress_callback(0.0, "Installing ComfyUI...")
            
            # 安装
            success = self.installer.install(
                install_models=install_models,
                progress_callback=self._wrap_progress(progress_callback, 0, 0.7)
            )
            
            if not success:
                return False
            
            if progress_callback:
                progress_callback(0.8, "Verifying installation...")
            
            # 验证
            if not self.installer.check_dependencies():
                self.installer.install_dependencies()
            
            if progress_callback:
                progress_callback(1.0, "Setup complete!")
            
            return True
            
        except Exception as e:
            logger.error(f"Setup failed: {e}")
            return False
    
    def _wrap_progress(self, callback: Callable, start: float, end: float) -> Callable:
        """包装进度回调"""
        def wrapped(progress: float, message: str):
            adjusted = start + progress * (end - start)
            callback(adjusted, message)
        
        return wrapped
    
    def start(self, auto_open_browser: bool = True) -> bool:
        """
        启动ComfyUI
        
        Args:
            auto_open_browser: 是否自动打开浏览器
        
        Returns:
            bool: 启动是否成功
        """
        return self.controller.start(auto_open_browser=auto_open_browser)
    
    def stop(self) -> bool:
        """
        停止ComfyUI
        
        Returns:
            bool: 停止是否成功
        """
        return self.controller.stop()
    
    def restart(self) -> bool:
        """
        重启ComfyUI
        
        Returns:
            bool: 重启是否成功
        """
        return self.controller.restart()
    
    def get_status(self) -> ComfyUIStatus:
        """
        获取状态
        
        Returns:
            ComfyUIStatus: 当前状态
        """
        return self.controller.get_status()
    
    def get_stats(self) -> dict:
        """
        获取统计信息
        
        Returns:
            dict: 包含系统统计和队列状态
        """
        return {
            'status': self.controller.get_status().value,
            'system_stats': self.controller.get_system_stats(),
            'queue_status': self.controller.get_queue_status()
        }
    
    def check_updates(self) -> dict:
        """
        检查更新
        
        Returns:
            dict: 更新信息
        """
        return self.installer.check_updates()
    
    def shutdown(self):
        """关闭所有服务"""
        self.controller.stop()
        self.controller.process_pool.shutdown()
        logger.info("ComfyUIManager shutdown complete")


# 便捷函数

def create_manager(base_path: str = None) -> ComfyUIManager:
    """
    创建ComfyUI管理器
    
    Args:
        base_path: ComfyUI根目录
    
    Returns:
        ComfyUIManager: 管理器实例
    """
    return ComfyUIManager(base_path)


def quick_start(base_path: str = None, auto_open_browser: bool = True) -> ComfyUIManager:
    """
    快速启动ComfyUI
    
    Args:
        base_path: ComfyUI根目录
        auto_open_browser: 是否自动打开浏览器
    
    Returns:
        ComfyUIManager: 管理器实例
    """
    manager = ComfyUIManager(base_path)
    
    # 如果未安装，先安装
    if not (manager.controller.comfyui_path / "main.py").exists():
        manager.setup()
    
    # 启动
    manager.start(auto_open_browser=auto_open_browser)
    
    return manager
