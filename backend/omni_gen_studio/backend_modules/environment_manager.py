#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
环境管理器模块 - OmniGen Studio
功能:
1. 自动检测代码所在文件夹是否有虚拟环境，如果没有则自动创建
2. 自动部署CUDA、PyTorch、FlashAttention2、xFormers等驱动和依赖
3. 支持选择FlashAttention2或xFormers推理加速
4. 自动断点续传、自动更换下载源
5. 联网检索github/huggingface检查diffusers和comfyui最新版本并自动更新

作者: Matrix Agent
版本: v1.0
"""

import os
import sys
import subprocess
import platform
import shutil
import time
import logging
import re
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EnvironmentManager:
    """智能环境管理器 - 自动检测和配置虚拟环境及深度学习依赖"""

    def __init__(self, base_dir: str):
        """
        初始化环境管理器

        Args:
            base_dir: 项目根目录路径
        """
        self.base_dir = Path(base_dir)
        self.venv_name = "venv"
        self.venv_path = self.base_dir / self.venv_name

        # 确定路径
        if platform.system() == "Windows":
            self.python_exe = self.venv_path / "Scripts" / "python.exe"
            self.pip_exe = self.venv_path / "Scripts" / "pip.exe"
        else:
            self.python_exe = self.venv_path / "bin" / "python"
            self.pip_exe = self.venv_path / "bin" / "pip"

        # 下载源配置
        self.mirrors = {
            "pypi": [
                "https://pypi.org/simple",
                "https://mirrors.aliyun.com/pypi/simple/",
                "https://pypi.tuna.tsinghua.edu.cn/simple/"
            ],
            "pytorch": [
                "https://download.pytorch.org/whl/cu121",
                "https://download.pytorch.org/whl/cu118",
                "https://mirror.sjtu.edu.cn/pytorch-wheels/"
            ],
        }

        self.current_mirror_index = {"pypi": 0, "pytorch": 0}

        # GitHub API 配置
        self.github_api = "https://api.github.com"
        self.huggingface_api = "https://huggingface.co/api"

        logger.info(f"EnvironmentManager initialized with base_dir: {self.base_dir}")
        logger.info(f"Virtual environment path: {self.venv_path}")

    def check_environment(self) -> bool:
        """
        检查虚拟环境是否存在且有效

        Returns:
            bool: 虚拟环境是否存在且有效
        """
        logger.info("检查虚拟环境状态...")

        # 检查基础路径
        if not self.venv_path.exists():
            logger.info("虚拟环境不存在")
            return False

        # 检查Python可执行文件
        if not self.python_exe.exists():
            logger.warning(f"Python可执行文件不存在: {self.python_exe}")
            return False

        # 验证虚拟环境
        try:
            result = subprocess.run(
                [str(self.python_exe), "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                logger.info(f"虚拟环境有效: {result.stdout.strip()}")
                return True
            else:
                logger.warning("虚拟环境验证失败")
                return False
        except Exception as e:
            logger.warning(f"虚拟环境验证异常: {e}")
            return False

    def create_virtual_environment(self) -> bool:
        """
        创建虚拟环境

        Returns:
            bool: 创建是否成功
        """
        logger.info(f"创建虚拟环境: {self.venv_path}")

        # 如果已存在，先删除
        if self.venv_path.exists():
            logger.info("删除现有虚拟环境...")
            try:
                shutil.rmtree(self.venv_path)
            except Exception as e:
                logger.error(f"删除现有虚拟环境失败: {e}")
                return False

        try:
            # 使用Python标准库创建虚拟环境
            result = subprocess.run(
                [sys.executable, "-m", "venv", str(self.venv_path)],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                logger.info("虚拟环境创建成功")
                return True
            else:
                logger.error(f"虚拟环境创建失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"创建虚拟环境异常: {e}")
            return False

    def _get_trusted_host(self, mirror: str) -> str:
        """获取镜像源信任主机"""
        if "aliyun" in mirror:
            return "mirrors.aliyun.com"
        elif "tsinghua" in mirror:
            return "pypi.tuna.tsinghua.edu.cn"
        elif "sjtu" in mirror:
            return "mirror.sjtu.edu.cn"
        return ""

    def _switch_mirror(self, mirror_type: str) -> str:
        """切换下载源并返回新的镜像URL"""
        if mirror_type in self.current_mirror_index:
            self.current_mirror_index[mirror_type] = (
                self.current_mirror_index[mirror_type] + 1
            ) % len(self.mirrors[mirror_type])

            new_mirror = self.mirrors[mirror_type][self.current_mirror_index[mirror_type]]
            logger.info(f"切换{self._get_mirror_type_name(mirror_type)}镜像源: {new_mirror}")
            return new_mirror
        return ""

    def _get_mirror_type_name(self, mirror_type: str) -> str:
        """获取镜像类型名称"""
        names = {"pypi": "PyPI", "pytorch": "PyTorch"}
        return names.get(mirror_type, mirror_type)

    def _download_with_resume(self, url: str, output_path: Path, max_retries: int = 5) -> bool:
        """
        支持断点续传的文件下载

        Args:
            url: 下载URL
            output_path: 输出文件路径
            max_retries: 最大重试次数

        Returns:
            bool: 下载是否成功
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 检查已下载大小
        downloaded_size = 0
        if output_path.exists():
            downloaded_size = output_path.stat().st_size
            logger.info(f"断点续传: 已下载 {downloaded_size} bytes")

        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url)
                if downloaded_size > 0:
                    req.add_header('Range', f'bytes={downloaded_size}-')
                    mode = 'ab'
                else:
                    mode = 'wb'

                logger.info(f"下载: {url} (尝试 {attempt + 1}/{max_retries})")

                with urllib.request.urlopen(req, timeout=120) as response:
                    total_size = int(response.headers.get('Content-Length', 0))
                    if downloaded_size > 0 and total_size > 0:
                        total_size += downloaded_size

                    chunk_size = 8192
                    with open(output_path, mode) as f:
                        downloaded = downloaded_size
                        while True:
                            chunk = response.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)

                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                if downloaded % (1024 * 1024 * 10) < chunk_size:
                                    logger.info(f"下载进度: {progress:.1f}%")

                logger.info(f"下载完成: {output_path}")
                return True

            except Exception as e:
                logger.warning(f"下载失败: {e}")
                self._switch_mirror("pypi")
                time.sleep(2)

        logger.error(f"下载失败，已尝试 {max_retries} 次")
        return False

    def install_dependencies(
        self,
        use_flashattention: bool = True,
        use_xformers: bool = False,
        cuda_version: str = "12.1"
    ) -> bool:
        """
        安装项目依赖

        Args:
            use_flashattention: 是否安装FlashAttention2
            use_xformers: 是否安装xFormers
            cuda_version: CUDA版本 (如 "12.1", "11.8")

        Returns:
            bool: 安装是否成功
        """
        logger.info("=" * 60)
        logger.info("开始安装依赖")
        logger.info(f"CUDA版本: {cuda_version}")
        logger.info(f"FlashAttention2: {'是' if use_flashattention else '否'}")
        logger.info(f"xFormers: {'是' if use_xformers else '否'}")
        logger.info("=" * 60)

        # 确保虚拟环境存在
        if not self.check_environment():
            logger.info("虚拟环境无效，需要创建...")
            if not self.create_virtual_environment():
                logger.error("虚拟环境创建失败")
                return False

        # 升级pip
        if not self._upgrade_pip():
            logger.warning("pip升级失败，继续安装...")

        # 安装基础依赖
        if not self._install_base_dependencies():
            logger.error("基础依赖安装失败")
            return False

        # 安装PyTorch
        if not self._install_pytorch(cuda_version):
            logger.error("PyTorch安装失败")
            return False

        # 安装FlashAttention2
        if use_flashattention:
            self._install_flash_attention()

        # 安装xFormers
        if use_xformers:
            self._install_xformers()

        logger.info("=" * 60)
        logger.info("依赖安装完成")
        logger.info("=" * 60)
        return True

    def _upgrade_pip(self, max_retries: int = 3) -> bool:
        """升级pip"""
        if not self.check_environment():
            logger.error("虚拟环境不存在")
            return False

        for attempt in range(max_retries):
            try:
                logger.info(f"升级pip (尝试 {attempt + 1}/{max_retries})...")
                mirror = self.mirrors["pypi"][self.current_mirror_index["pypi"]]

                result = subprocess.run(
                    [str(self.pip_exe), "install", "--upgrade", "pip",
                     "-i", mirror, "--trusted-host", self._get_trusted_host(mirror)],
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                if result.returncode == 0:
                    logger.info("pip升级成功")
                    return True
                else:
                    logger.warning(f"pip升级失败: {result.stderr[:200]}")
                    self._switch_mirror("pypi")

            except Exception as e:
                logger.warning(f"pip升级异常: {e}")
                self._switch_mirror("pypi")
                time.sleep(2)

        return False

    def _install_base_dependencies(self) -> bool:
        """安装基础依赖"""
        logger.info("安装基础依赖...")

        base_packages = [
            "wheel", "setuptools", "numpy", "scipy", "pandas",
            "pillow", "opencv-python-headless", "tqdm", "requests",
            "pyyaml", "transformers", "accelerate", "safetensors"
        ]

        for package in base_packages:
            if not self._install_single_package(package):
                logger.warning(f"{package} 安装失败，继续...")

        return True

    def _install_single_package(self, package: str, max_retries: int = 3) -> bool:
        """安装单个包"""
        for attempt in range(max_retries):
            try:
                logger.info(f"安装: {package} (尝试 {attempt + 1}/{max_retries})")
                mirror = self.mirrors["pypi"][self.current_mirror_index["pypi"]]

                result = subprocess.run(
                    [str(self.pip_exe), "install", package,
                     "-i", mirror, "--trusted-host", self._get_trusted_host(mirror),
                     "--no-cache-dir"],
                    capture_output=True,
                    text=True,
                    timeout=600
                )

                if result.returncode == 0:
                    logger.info(f"{package} 安装成功")
                    return True
                else:
                    logger.warning(f"{package} 安装失败: {result.stderr[:200]}")
                    self._switch_mirror("pypi")

            except subprocess.TimeoutExpired:
                logger.warning(f"{package} 安装超时")
            except Exception as e:
                logger.warning(f"{package} 安装异常: {e}")

            time.sleep(2)

        return False

    def _install_pytorch(self, cuda_version: str = "12.1") -> bool:
        """安装PyTorch"""
        logger.info(f"安装PyTorch (CUDA {cuda_version})...")

        # 根据CUDA版本选择安装索引
        if cuda_version.startswith("12"):
            index_url = "https://download.pytorch.org/whl/cu121"
        elif cuda_version.startswith("11"):
            index_url = "https://download.pytorch.org/whl/cu118"
        else:
            index_url = "https://download.pytorch.org/whl/cu121"

        for attempt in range(3):
            try:
                logger.info(f"安装PyTorch (尝试 {attempt + 1}/3)...")

                result = subprocess.run(
                    [str(self.pip_exe), "install",
                     "torch", "torchvision", "torchaudio",
                     "--index-url", index_url],
                    capture_output=True,
                    text=True,
                    timeout=900
                )

                if result.returncode == 0:
                    logger.info("PyTorch安装成功")
                    return True
                else:
                    logger.warning("PyTorch安装失败，尝试备用安装...")
                    # 备用CPU安装
                    result = subprocess.run(
                        [str(self.pip_exe), "install", "torch", "torchvision", "torchaudio"],
                        capture_output=True,
                        text=True,
                        timeout=900
                    )
                    if result.returncode == 0:
                        logger.info("PyTorch安装成功 (CPU版本)")
                        return True

            except Exception as e:
                logger.warning(f"PyTorch安装异常: {e}")

            time.sleep(2)

        return False

    def _install_flash_attention(self) -> bool:
        """安装FlashAttention2"""
        logger.info("安装FlashAttention2...")

        try:
            # Flash Attention 2 安装
            result = subprocess.run(
                [str(self.pip_exe), "install", "flash-attn", "--no-build-isolation"],
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode == 0:
                logger.info("FlashAttention2安装成功")
                return True
            else:
                logger.warning(f"FlashAttention2安装失败: {result.stderr[:200]}")
                # 尝试从源码安装
                return self._install_flash_attention_from_source()

        except Exception as e:
            logger.warning(f"FlashAttention2安装异常: {e}")
            return False

    def _install_flash_attention_from_source(self) -> bool:
        """从源码安装FlashAttention2"""
        logger.info("尝试从源码安装FlashAttention2...")

        try:
            result = subprocess.run(
                [str(self.pip_exe), "install",
                 "flash-attn>=2.0.0", "--no-build-isolation",
                 "--verbose"],
                capture_output=True,
                text=True,
                timeout=900
            )

            if result.returncode == 0:
                logger.info("FlashAttention2安装成功")
                return True
            else:
                logger.warning(f"FlashAttention2源码安装失败")
                return False

        except Exception as e:
            logger.warning(f"FlashAttention2源码安装异常: {e}")
            return False

    def _install_xformers(self) -> bool:
        """安装xFormers"""
        logger.info("安装xFormers...")

        try:
            result = subprocess.run(
                [str(self.pip_exe), "install", "xformers"],
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode == 0:
                logger.info("xFormers安装成功")
                return True
            else:
                logger.warning(f"xFormers安装失败")
                return False

        except Exception as e:
            logger.warning(f"xFormers安装异常: {e}")
            return False

    def _check_cuda_available(self) -> Tuple[bool, str]:
        """检查CUDA是否可用"""
        try:
            result = subprocess.run(
                ["nvidia-smi"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if "CUDA Version:" in line:
                        cuda_version = line.split("CUDA Version:")[1].strip().split()[0]
                        logger.info(f"CUDA版本: {cuda_version}")
                        return True, cuda_version
                return True, "Unknown"
        except FileNotFoundError:
            pass
        return False, ""

    def check_latest_versions(self) -> dict:
        """
        检查diffusers和comfyui最新版本

        Returns:
            dict: 包含最新版本信息的字典
        """
        logger.info("检查最新版本...")
        versions = {
            "diffusers": {"current": None, "latest": None, "update_available": False},
            "comfyui": {"current": None, "latest": None, "update_available": False}
        }

        # 检查当前安装的diffusers版本
        versions["diffusers"]["current"] = self._get_installed_package_version("diffusers")
        versions["comfyui"]["current"] = self._get_comfyui_installed_version()

        # 获取最新版本
        versions["diffusers"]["latest"] = self._get_latest_github_version("huggingface", "diffusers")
        versions["comfyui"]["latest"] = self._get_latest_github_version("comfyanonymous", "ComfyUI")

        # 判断是否需要更新
        if versions["diffusers"]["current"] and versions["diffusers"]["latest"]:
            versions["diffusers"]["update_available"] = (
                versions["diffusers"]["current"] != versions["diffusers"]["latest"]
            )

        if versions["comfyui"]["current"] and versions["comfyui"]["latest"]:
            versions["comfyui"]["update_available"] = (
                versions["comfyui"]["current"] != versions["comfyui"]["latest"]
            )

        logger.info(f"diffusers: 当前={versions['diffusers']['current']}, 最新={versions['diffusers']['latest']}")
        logger.info(f"comfyui: 当前={versions['comfyui']['current']}, 最新={versions['comfyui']['latest']}")

        return versions

    def _get_installed_package_version(self, package: str) -> Optional[str]:
        """获取已安装包的版本"""
        try:
            result = subprocess.run(
                [str(self.pip_exe), "show", package],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith("Version:"):
                        return line.split(":", 1)[1].strip()
        except Exception as e:
            logger.warning(f"获取{package}版本失败: {e}")
        return None

    def _get_comfyui_installed_version(self) -> Optional[str]:
        """获取ComfyUI已安装版本"""
        # ComfyUI通常通过git安装，检查git仓库的版本标签
        comfyui_paths = [
            self.base_dir / "ComfyUI",
            self.base_dir / "comfyui",
            self.base_dir / "models" / "ComfyUI"
        ]

        for path in comfyui_paths:
            git_dir = path / ".git"
            if git_dir.exists():
                try:
                    result = subprocess.run(
                        ["git", "describe", "--tags", "--abbrev=0"],
                        cwd=str(path),
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0:
                        return result.stdout.strip()
                except Exception:
                    pass

        return None

    def _get_latest_github_version(self, owner: str, repo: str) -> Optional[str]:
        """从GitHub获取最新版本标签"""
        try:
            url = f"{self.github_api}/repos/{owner}/{repo}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "Python"})

            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
                if "tag_name" in data:
                    tag = data["tag_name"].lstrip('v')
                    logger.info(f"GitHub {owner}/{repo} 最新版本: {tag}")
                    return tag

        except urllib.error.HTTPError as e:
            if e.code == 403:
                logger.warning(f"GitHub API限流，使用备用方法获取{repo}版本")
                return self._get_latest_github_version_fallback(owner, repo)
            else:
                logger.warning(f"获取{repo}版本失败: HTTP {e.code}")
        except Exception as e:
            logger.warning(f"获取{repo}版本异常: {e}")

        return None

    def _get_latest_github_version_fallback(self, owner: str, repo: str) -> Optional[str]:
        """备用方法获取GitHub版本"""
        try:
            url = f"https://github.com/{owner}/{repo}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "Python"})

            with urllib.request.urlopen(req, timeout=30) as response:
                final_url = response.geturl()
                if "/releases/tag/" in final_url:
                    tag = final_url.split("/releases/tag/")[1]
                    # 处理URL编码的tag
                    from urllib.parse import unquote
                    tag = unquote(tag).lstrip('v')
                    return tag

        except Exception as e:
            logger.warning(f"备用方法获取{repo}版本失败: {e}")

        return None

    def update_comfyui(self) -> bool:
        """
        更新ComfyUI到最新版本

        Returns:
            bool: 更新是否成功
        """
        logger.info("更新ComfyUI...")

        comfyui_paths = [
            self.base_dir / "ComfyUI",
            self.base_dir / "comfyui"
        ]

        comfyui_path = None
        for path in comfyui_paths:
            if path.exists() and (path / ".git").exists():
                comfyui_path = path
                break

        if not comfyui_path:
            logger.info("ComfyUI未安装，尝试克隆...")
            return self._clone_comfyui()

        try:
            # 获取远程最新版本
            logger.info("获取远程最新版本...")
            result = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=str(comfyui_path),
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                logger.warning(f"git fetch失败: {result.stderr}")

            # 获取最新标签
            result = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0", "origin/master"],
                cwd=str(comfyui_path),
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                latest_tag = result.stdout.strip()
                logger.info(f"最新版本: {latest_tag}")

                # 检查当前版本
                result = subprocess.run(
                    ["git", "describe", "--tags", "--abbrev=0"],
                    cwd=str(comfyui_path),
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                current_tag = result.stdout.strip() if result.returncode == 0 else None

                if current_tag == latest_tag:
                    logger.info("ComfyUI已是最新版本")
                    return True

                # 检出最新版本
                logger.info(f"更新到版本: {latest_tag}")
                result = subprocess.run(
                    ["git", "checkout", latest_tag],
                    cwd=str(comfyui_path),
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                if result.returncode == 0:
                    logger.info("ComfyUI更新成功")
                    # 更新子模块
                    subprocess.run(
                        ["git", "submodule", "update", "--init", "--recursive"],
                        cwd=str(comfyui_path),
                        capture_output=True,
                        text=True,
                        timeout=300
                    )
                    return True
                else:
                    logger.error(f"更新失败: {result.stderr}")
                    return False
            else:
                logger.warning("无法获取最新版本标签")
                return False

        except Exception as e:
            logger.error(f"更新ComfyUI异常: {e}")
            return False

    def _clone_comfyui(self) -> bool:
        """克隆ComfyUI仓库"""
        logger.info("克隆ComfyUI...")

        target_path = self.base_dir / "ComfyUI"

        if target_path.exists():
            logger.info("ComfyUI目录已存在")
            return False

        try:
            result = subprocess.run(
                ["git", "clone", "https://github.com/comfyanonymous/ComfyUI.git", str(target_path)],
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode == 0:
                logger.info("ComfyUI克隆成功")
                # 初始化子模块
                subprocess.run(
                    ["git", "submodule", "update", "--init", "--recursive"],
                    cwd=str(target_path),
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                return True
            else:
                logger.error(f"克隆失败: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"克隆ComfyUI异常: {e}")
            return False

    def update_diffusers(self) -> bool:
        """
        更新diffusers到最新版本

        Returns:
            bool: 更新是否成功
        """
        logger.info("更新diffusers...")

        if not self.check_environment():
            logger.error("虚拟环境不存在")
            return False

        # 获取最新版本号
        latest_version = self._get_latest_github_version("huggingface", "diffusers")

        if not latest_version:
            logger.error("无法获取diffusers最新版本")
            return False

        # 获取当前版本
        current_version = self._get_installed_package_version("diffusers")

        if current_version == latest_version:
            logger.info("diffusers已是最新版本")
            return True

        logger.info(f"更新diffusers: {current_version} -> {latest_version}")

        try:
            # 使用pip升级
            mirror = self.mirrors["pypi"][self.current_mirror_index["pypi"]]
            result = subprocess.run(
                [str(self.pip_exe), "install", f"diffusers=={latest_version}",
                 "-i", mirror, "--trusted-host", self._get_trusted_host(mirror)],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                logger.info("diffusers更新成功")
                return True
            else:
                logger.error(f"diffusers更新失败: {result.stderr}")
                # 尝试不指定版本升级
                result = subprocess.run(
                    [str(self.pip_exe), "install", "--upgrade", "diffusers",
                     "-i", mirror, "--trusted-host", self._get_trusted_host(mirror)],
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                if result.returncode == 0:
                    logger.info("diffusers更新成功")
                    return True
                return False

        except Exception as e:
            logger.error(f"更新diffusers异常: {e}")
            return False

    def initialize(self, force: bool = False) -> bool:
        """
        初始化环境 - 自动检测/创建虚拟环境并安装依赖

        Args:
            force: 是否强制重新创建虚拟环境

        Returns:
            bool: 初始化是否成功
        """
        logger.info("=" * 60)
        logger.info("开始环境初始化")
        logger.info("=" * 60)

        # 检查Python版本
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 10):
            logger.error(f"需要Python 3.10+，当前版本: {version.major}.{version.minor}")
            return False
        logger.info(f"Python版本: {version.major}.{version.minor}.{version.micro}")

        # 检查CUDA
        cuda_available, cuda_ver = self._check_cuda_available()
        if cuda_available:
            logger.info(f"CUDA可用: {cuda_ver}")
        else:
            logger.warning("CUDA不可用，将使用CPU模式")

        # 检测/创建虚拟环境
        if force or not self.check_environment():
            logger.info("需要创建虚拟环境...")
            if not self.create_virtual_environment():
                logger.error("虚拟环境创建失败")
                return False
        else:
            logger.info("使用现有虚拟环境")

        # 自动检测最佳加速方案
        cuda_version = cuda_ver.split('.')[0] + "." + cuda_ver.split('.')[1] if cuda_ver and cuda_ver != "Unknown" else "12.1"

        # 安装依赖
        if not self.install_dependencies(
            use_flashattention=True,
            use_xformers=False,
            cuda_version=cuda_version
        ):
            logger.error("依赖安装失败")
            return False

        # 检查最新版本
        versions = self.check_latest_versions()

        logger.info("=" * 60)
        logger.info("环境初始化完成")
        logger.info(f"虚拟环境路径: {self.venv_path}")
        logger.info("=" * 60)

        return True

    def get_environment_info(self) -> Dict[str, Any]:
        """
        获取环境信息

        Returns:
            dict: 环境信息字典
        """
        info = {
            "venv_exists": self.check_environment(),
            "venv_path": str(self.venv_path),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "cuda_available": self._check_cuda_available()[0],
            "cuda_version": self._check_cuda_available()[1],
            "platform": platform.system(),
        }

        if self.check_environment():
            try:
                # 检查PyTorch
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
            except Exception as e:
                logger.warning(f"获取PyTorch信息失败: {e}")

            # 检查FlashAttention
            try:
                result = subprocess.run(
                    [str(self.python_exe), "-c", "import flash_attn; print('OK')"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                info["flash_attention_available"] = result.returncode == 0
            except Exception:
                info["flash_attention_available"] = False

            # 检查xFormers
            try:
                result = subprocess.run(
                    [str(self.python_exe), "-c", "import xformers; print('OK')"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                info["xformers_available"] = result.returncode == 0
            except Exception:
                info["xformers_available"] = False

        return info


# 全局实例管理
_environment_manager_instance = None


def get_environment_manager(base_dir: str = None) -> EnvironmentManager:
    """获取全局EnvironmentManager实例"""
    global _environment_manager_instance
    if _environment_manager_instance is None:
        if base_dir is None:
            base_dir = Path(__file__).parent.parent.absolute()
        _environment_manager_instance = EnvironmentManager(str(base_dir))
    return _environment_manager_instance


def initialize_environment(base_dir: str = None, force: bool = False) -> bool:
    """快速初始化环境"""
    manager = get_environment_manager(base_dir)
    return manager.initialize(force=force)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OmniGen Studio - 环境管理器")
    parser.add_argument("--base-dir", default=None, help="项目根目录")
    parser.add_argument("--init", action="store_true", help="初始化环境")
    parser.add_argument("--force", action="store_true", help="强制重新创建虚拟环境")
    parser.add_argument("--check", action="store_true", help="检查环境状态")
    parser.add_argument("--check-versions", action="store_true", help="检查最新版本")
    parser.add_argument("--update-diffusers", action="store_true", help="更新diffusers")
    parser.add_argument("--update-comfyui", action="store_true", help="更新ComfyUI")

    args = parser.parse_args()

    if args.base_dir:
        manager = EnvironmentManager(args.base_dir)
    else:
        manager = get_environment_manager()

    if args.init:
        manager.initialize(force=args.force)
    elif args.check:
        info = manager.get_environment_info()
        print("\n=== 环境信息 ===")
        for key, value in info.items():
            print(f"{key}: {value}")
    elif args.check_versions:
        versions = manager.check_latest_versions()
        print("\n=== 版本信息 ===")
        print(f"diffusers: 当前={versions['diffusers']['current']}, 最新={versions['diffusers']['latest']}, 可更新={versions['diffusers']['update_available']}")
        print(f"comfyui: 当前={versions['comfyui']['current']}, 最新={versions['comfyui']['latest']}, 可更新={versions['comfyui']['update_available']}")
    elif args.update_diffusers:
        manager.update_diffusers()
    elif args.update_comfyui:
        manager.update_comfyui()
    else:
        parser.print_help()
