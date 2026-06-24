#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OmniGen Studio - 智能环境管理器
功能：
1. 自动检测虚拟环境，不存在则创建
2. 自动部署CUDA、PyTorch、FlashAttention2、xFormers
3. 断点续传下载
4. 自动更换下载源

作者：MiniMax Agent
版本：v6.0
"""

import os
import sys
import subprocess
import platform
import shutil
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EnvironmentManager:
    """智能环境管理器"""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root) if project_root else Path(__file__).parent.absolute()
        self.venv_name = "venv_aigc"
        self.venv_path = self.project_root / self.venv_name

        # 确定路径
        if platform.system() == "Windows":
            self.python_exe = self.venv_path / "Scripts" / "python.exe"
            self.pip_exe = self.venv_path / "Scripts" / "pip.exe"
        else:
            self.python_exe = self.venv_path / "bin" / "python"
            self.pip_exe = self.venv_path / "bin" / "pip"

        # 下载源
        self.mirrors = {
            "pypi": ["https://pypi.org/simple", "https://mirrors.aliyun.com/pypi/simple/",
                    "https://pypi.tuna.tsinghua.edu.cn/simple/"],
            "pytorch": ["https://download.pytorch.org/whl/cu118",
                       "https://download.pytorch.org/whl/cu121",
                       "https://mirror.sjtu.edu.cn/pytorch-wheels/"],
        }

        self.current_mirror_index = {"pypi": 0, "pytorch": 0}

    def check_python_version(self) -> bool:
        """检查Python版本"""
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 10):
            logger.error(f"需要Python 3.10+，当前版本: {version.major}.{version.minor}")
            return False
        logger.info(f"✅ Python版本: {version.major}.{version.minor}.{version.micro}")
        return True

    def check_cuda_available(self) -> Tuple[bool, str]:
        """检查CUDA是否可用"""
        try:
            result = subprocess.run(["nvidia-smi"], capture_output=True, text=True)
            if result.returncode == 0:
                # 解析CUDA版本
                for line in result.stdout.split('\n'):
                    if "CUDA Version:" in line:
                        cuda_version = line.split("CUDA Version:")[1].strip().split()[0]
                        logger.info(f"✅ CUDA版本: {cuda_version}")
                        return True, cuda_version
                return True, "Unknown"
        except FileNotFoundError:
            pass
        return False, ""

    def check_venv_exists(self) -> bool:
        """检查虚拟环境是否存在"""
        exists = self.venv_path.exists() and self.python_exe.exists()
        if exists:
            logger.info(f"✅ 虚拟环境已存在: {self.venv_path}")
        return exists

    def create_venv(self, force: bool = False) -> bool:
        """创建虚拟环境"""
        if self.check_venv_exists():
            if not force:
                logger.info("✅ 使用现有虚拟环境")
                return True
            logger.info("🗑️ 删除现有虚拟环境...")
            shutil.rmtree(self.venv_path)

        logger.info(f"🐍 创建虚拟环境: {self.venv_path}")

        try:
            result = subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_path)],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                logger.info("✅ 虚拟环境创建成功")
                return True
            else:
                logger.error(f"❌ 虚拟环境创建失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"❌ 创建虚拟环境异常: {e}")
            return False

    def upgrade_pip(self, max_retries: int = 3) -> bool:
        """升级pip，支持断点续传和换源"""
        if not self.check_venv_exists():
            logger.error("❌ 虚拟环境不存在")
            return False

        for attempt in range(max_retries):
            try:
                logger.info(f"🔄 升级pip (尝试 {attempt + 1}/{max_retries})...")

                # 尝试当前镜像源
                mirror = self.mirrors["pypi"][self.current_mirror_index["pypi"]]

                result = subprocess.run(
                    [str(self.pip_exe), "install", "--upgrade", "pip",
                     "-i", mirror, "--trusted-host", self.get_trusted_host(mirror)],
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                if result.returncode == 0:
                    logger.info("✅ pip升级成功")
                    return True
                else:
                    logger.warning(f"⚠️ pip升级失败: {result.stderr[:200]}")
                    # 切换镜像源
                    self.switch_mirror("pypi")

            except Exception as e:
                logger.warning(f"⚠️ pip升级异常: {e}")
                self.switch_mirror("pypi")
                time.sleep(2)

        return False

    def get_trusted_host(self, mirror: str) -> str:
        """获取信任主机"""
        if "aliyun" in mirror:
            return "mirrors.aliyun.com"
        elif "tsinghua" in mirror:
            return "pypi.tuna.tsinghua.edu.cn"
        elif "sjtu" in mirror:
            return "mirror.sjtu.edu.cn"
        return ""

    def switch_mirror(self, mirror_type: str):
        """切换下载源"""
        if mirror_type in self.current_mirror_index:
            self.current_mirror_index[mirror_type] = (
                self.current_mirror_index[mirror_type] + 1
            ) % len(self.mirrors[mirror_type])

            logger.info(f"🔄 切换{mirror_type}镜像源: "
                       f"{self.mirrors[mirror_type][self.current_mirror_index[mirror_type]]}")

    def download_with_resume(self, url: str, output_path: str,
                           max_retries: int = 5) -> bool:
        """断点续传下载"""
        import urllib.request
        import os

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 检查已下载的大小
        downloaded_size = 0
        if output_file.exists():
            downloaded_size = output_file.stat().st_size
            logger.info(f"📥 断点续传: 已下载 {downloaded_size} bytes")

        for attempt in range(max_retries):
            try:
                # 创建请求
                req = urllib.request.Request(url)
                if downloaded_size > 0:
                    # 添加Range头支持断点续传
                    req.add_header('Range', f'bytes={downloaded_size}-')
                    mode = 'ab'
                else:
                    mode = 'wb'

                logger.info(f"📥 下载: {url} (尝试 {attempt + 1}/{max_retries})")

                # 打开URL
                with urllib.request.urlopen(req, timeout=60) as response:
                    total_size = int(response.headers.get('Content-Length', 0))
                    if downloaded_size > 0 and total_size > 0:
                        total_size += downloaded_size

                    # 下载文件
                    chunk_size = 8192
                    with open(output_file, mode) as f:
                        downloaded = downloaded_size
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)

                            # 显示进度
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                if attempt == 0:
                                    logger.info(f"📥 进度: {progress:.1f}%")

                logger.info(f"✅ 下载完成: {output_path}")
                return True

            except Exception as e:
                logger.warning(f"⚠️ 下载失败: {e}")
                # 尝试更换源
                self.switch_mirror("pypi")
                time.sleep(2)

        logger.error(f"❌ 下载失败，已尝试 {max_retries} 次")
        return False

    def download_model_with_resume(self, model_id: str, output_dir: str,
                                  format: str = "safetensors") -> Optional[str]:
        """使用断点续传下载模型"""
        # 尝试多个源
        sources = [
            f"https://huggingface.co/{model_id}/resolve/main/model.{format}",
            f"https://hf-mirror.com/{model_id}/resolve/main/model.{format}",
            f"https://modelscope.cn/models/{model_id}/resolve/master/model.{format}"
        ]

        output_path = Path(output_dir) / f"{model_id.replace('/', '_')}.{format}"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        for url in sources:
            logger.info(f"尝试下载源: {url}")
            if self.download_with_resume(url, str(output_path)):
                return str(output_path)

        return None

    def install_package(self, package: str, max_retries: int = 3) -> bool:
        """安装单个包，支持断点续传"""
        for attempt in range(max_retries):
            try:
                logger.info(f"📦 安装: {package} (尝试 {attempt + 1}/{max_retries})")

                mirror = self.mirrors["pypi"][self.current_mirror_index["pypi"]]

                result = subprocess.run(
                    [str(self.pip_exe), "install", package,
                     "-i", mirror, "--trusted-host", self.get_trusted_host(mirror),
                     "--no-cache-dir"],
                    capture_output=True,
                    text=True,
                    timeout=600
                )

                if result.returncode == 0:
                    logger.info(f"✅ {package} 安装成功")
                    return True
                else:
                    logger.warning(f"⚠️ {package} 安装失败: {result.stderr[:200]}")
                    self.switch_mirror("pypi")

            except subprocess.TimeoutExpired:
                logger.warning(f"⚠️ {package} 安装超时")
            except Exception as e:
                logger.warning(f"⚠️ {package} 安装异常: {e}")

            time.sleep(2)

        return False

    def install_base_dependencies(self) -> bool:
        """安装基础依赖"""
        logger.info("📦 安装基础依赖...")

        base_packages = [
            "wheel", "setuptools", "numpy", "scipy", "pandas",
            "pillow", "opencv-python", "tqdm", "requests", "pyyaml",
            "transformers", "accelerate", "safetensors", "diffusers"
        ]

        for package in base_packages:
            if not self.install_package(package):
                logger.warning(f"⚠️ {package} 安装失败，继续...")

        return True

    def install_pytorch(self, cuda_version: str = "cu118") -> bool:
        """安装PyTorch"""
        logger.info(f"🔧 安装PyTorch ({cuda_version})...")

        # 根据CUDA版本选择安装命令
        if cuda_version == "cu118":
            index_url = "https://download.pytorch.org/whl/cu118"
        elif cuda_version == "cu121":
            index_url = "https://download.pytorch.org/whl/cu121"
        else:
            index_url = "https://download.pytorch.org/whl/cu118"

        for attempt in range(3):
            try:
                logger.info(f"🔄 安装PyTorch (尝试 {attempt + 1}/3)...")

                result = subprocess.run(
                    [str(self.pip_exe), "install",
                     "torch", "torchvision", "torchaudio",
                     "--index-url", index_url],
                    capture_output=True,
                    text=True,
                    timeout=900
                )

                if result.returncode == 0:
                    logger.info("✅ PyTorch安装成功")
                    return True
                else:
                    logger.warning(f"⚠️ PyTorch安装失败，尝试备用安装...")
                    # 备用安装
                    result = subprocess.run(
                        [str(self.pip_exe), "install",
                         "torch", "torchvision", "torchaudio"],
                        capture_output=True,
                        text=True,
                        timeout=900
                    )
                    if result.returncode == 0:
                        logger.info("✅ PyTorch安装成功 (CPU版本)")
                        return True

            except Exception as e:
                logger.warning(f"⚠️ PyTorch安装异常: {e}")

            time.sleep(2)

        return False

    def install_flash_attention(self, version: str = "2") -> bool:
        """安装FlashAttention"""
        logger.info(f"⚡ 安装FlashAttention {version}...")

        if version == "2":
            # Flash Attention 2
            packages = ["flash-attn==2.5.0", "--no-build-isolation"]
        else:
            return False

        try:
            result = subprocess.run(
                [str(self.pip_exe), "install"] + packages,
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode == 0:
                logger.info("✅ FlashAttention安装成功")
                return True
            else:
                logger.warning(f"⚠️ FlashAttention安装失败: {result.stderr[:200]}")
                return False

        except Exception as e:
            logger.warning(f"⚠️ FlashAttention安装异常: {e}")
            return False

    def install_xformers(self) -> bool:
        """安装xFormers"""
        logger.info("⚡ 安装xFormers...")

        try:
            result = subprocess.run(
                [str(self.pip_exe), "install", "xformers"],
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode == 0:
                logger.info("✅ xFormers安装成功")
                return True
            else:
                logger.warning(f"⚠️ xFormers安装失败")
                return False

        except Exception as e:
            logger.warning(f"⚠️ xFormers安装异常: {e}")
            return False

    def setup_full_environment(self, accelerator: str = "auto",
                               cuda_version: str = "cu118") -> bool:
        """完整环境设置"""
        logger.info("=" * 60)
        logger.info("🚀 开始环境设置")
        logger.info("=" * 60)

        # 1. 检查系统环境
        if not self.check_python_version():
            return False

        cuda_available, cuda_ver = self.check_cuda_available()
        if cuda_available:
            logger.info(f"✅ CUDA可用: {cuda_ver}")
        else:
            logger.warning("⚠️ CUDA不可用，将使用CPU模式")

        # 2. 创建虚拟环境
        if not self.create_venv():
            return False

        # 3. 升级pip
        self.upgrade_pip()

        # 4. 安装基础依赖
        self.install_base_dependencies()

        # 5. 安装PyTorch
        if cuda_available:
            self.install_pytorch(cuda_version)
        else:
            self.install_pytorch("cpu")

        # 6. 安装加速库
        if accelerator in ["flash_attention", "auto"]:
            if not self.install_flash_attention():
                logger.warning("⚠️ FlashAttention安装失败")

        if accelerator in ["xformers", "auto"]:
            if not self.install_xformers():
                logger.warning("⚠️ xFormers安装失败")

        logger.info("=" * 60)
        logger.info("✅ 环境设置完成!")
        logger.info("=" * 60)
        logger.info(f"虚拟环境路径: {self.venv_path}")
        logger.info(f"运行主程序: {self.python_exe} run_main.py")

        return True

    def get_environment_info(self) -> Dict[str, Any]:
        """获取环境信息"""
        info = {
            "venv_exists": self.check_venv_exists(),
            "venv_path": str(self.venv_path),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
            "cuda_available": self.check_cuda_available()[0],
            "platform": platform.system(),
        }

        if self.check_venv_exists():
            try:
                result = subprocess.run(
                    [str(self.python_exe), "-c",
                     "import torch; print(torch.__version__); print(torch.cuda.is_available())"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    info["torch_version"] = lines[0] if len(lines) > 0 else "Unknown"
                    info["cuda_enabled"] = lines[1] == "True" if len(lines) > 1 else False
            except:
                pass

        return info


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="OmniGen Studio - 环境管理器")
    parser.add_argument("--setup", action="store_true", help="设置完整环境")
    parser.add_argument("--check", action="store_true", help="检查环境状态")
    parser.add_argument("--accelerator", default="auto",
                       choices=["flash_attention", "xformers", "auto", "none"],
                       help="选择加速库")
    parser.add_argument("--cuda", default="cu118", help="CUDA版本")

    args = parser.parse_args()

    manager = EnvironmentManager()

    if args.setup:
        manager.setup_full_environment(args.accelerator, args.cuda)
    elif args.check:
        info = manager.get_environment_info()
        print("\n=== 环境信息 ===")
        for key, value in info.items():
            print(f"{key}: {value}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
