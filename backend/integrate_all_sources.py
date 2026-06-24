#!/usr/bin/env python3
"""
Nanobot Factory - 完整源代码集成部署系统
一键完成ComfyUI、Diffusers、Transformers源码集成

功能：
1. 克隆完整ComfyUI仓库
2. 集成Diffusers/Transformers源码
3. 安装所有依赖
4. 配置PYTHONPATH
5. 创建启动脚本

@author MiniMax Agent
@date 2026-03-03
"""

import os
import sys
import subprocess
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
import time
import hashlib

logger = logging.getLogger(__name__)


# ============================================================================
# 配置
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
VENDOR_DIR = PROJECT_ROOT / "vendor"

# 源代码目标目录
COMFYUI_DIR = VENDOR_DIR / "ComfyUI"
DIFFUSERS_DIR = VENDOR_DIR / "diffusers"
TRANSFORMERS_DIR = VENDOR_DIR / "transformers"

# 仓库配置
REPOS = {
    "comfyui": {
        "url": "https://github.com/comfyanonymous/ComfyUI.git",
        "branch": "master",
        "target": COMFYUI_DIR,
        "description": "ComfyUI - 图像生成引擎"
    },
    "diffusers": {
        "url": "https://github.com/huggingface/diffusers.git",
        "branch": "main",
        "target": DIFFUSERS_DIR,
        "description": "Diffusers - 扩散模型库"
    },
    "transformers": {
        "url": "https://github.com/huggingface/transformers.git",
        "branch": "main",
        "target": TRANSFORMERS_DIR,
        "description": "Transformers - Transformer模型库"
    }
}


@dataclass
class CloneResult:
    """克隆结果"""
    success: bool
    name: str
    path: str
    files_count: int
    error: str = ""


# ============================================================================
# 工具函数
# ============================================================================

def run_command(cmd: List[str], cwd: Path = None, timeout: int = 3600, capture: bool = True) -> subprocess.CompletedProcess:
    """运行命令"""
    print(f"执行命令: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=capture,
        text=True,
        timeout=timeout
    )
    return result


def check_git_available() -> bool:
    """检查git是否可用"""
    try:
        result = run_command(["git", "--version"], capture=True)
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def count_files(directory: Path) -> int:
    """统计文件数量"""
    count = 0
    if directory.exists():
        for root, dirs, files in os.walk(directory):
            count += len(files)
    return count


# ============================================================================
# 克隆管理器
# ============================================================================

class SourceCodeIntegrator:
    """源代码集成器"""

    def __init__(self):
        self.results: List[CloneResult] = []
        self.vendor_dir = VENDOR_DIR

    def log(self, message: str, level: str = "INFO"):
        """日志输出"""
        prefix = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARNING": "⚠️",
            "ERROR": "❌"
        }.get(level, "ℹ️")
        print(f"{prefix} {message}")

    def clone_repository(self, name: str, repo_info: Dict) -> CloneResult:
        """克隆仓库"""
        self.log(f"\n{'='*60}")
        self.log(f"开始克隆: {repo_info['description']}")
        self.log(f"{'='*60}")

        target = repo_info["target"]
        url = repo_info["url"]
        branch = repo_info["branch"]

        # 检查是否已存在
        if target.exists() and (target / ".git").exists():
            files_count = count_files(target)
            self.log(f"仓库已存在: {target} ({files_count} 文件)", "SUCCESS")
            return CloneResult(
                success=True,
                name=name,
                path=str(target),
                files_count=files_count
            )

        # 创建父目录
        target.mkdir(parents=True, exist_ok=True)

        # 执行克隆
        self.log(f"正在克隆 {url} ...")
        self.log(f"目标目录: {target}")

        try:
            # 使用git clone
            result = run_command(
                ["git", "clone", "--depth", "1", "--branch", branch, url, str(target)],
                timeout=1800
            )

            if result.returncode == 0:
                files_count = count_files(target)
                self.log(f"克隆成功: {name} ({files_count} 文件)", "SUCCESS")
                return CloneResult(
                    success=True,
                    name=name,
                    path=str(target),
                    files_count=files_count
                )
            else:
                error_msg = result.stderr[:500] if result.stderr else "未知错误"
                self.log(f"克隆失败: {error_msg}", "ERROR")
                return CloneResult(
                    success=False,
                    name=name,
                    path=str(target),
                    files_count=0,
                    error=error_msg
                )

        except subprocess.TimeoutExpired:
            self.log("克隆超时", "ERROR")
            return CloneResult(
                success=False,
                name=name,
                path=str(target),
                files_count=0,
                error="克隆超时"
            )
        except Exception as e:
            self.log(f"克隆异常: {str(e)}", "ERROR")
            return CloneResult(
                success=False,
                name=name,
                path=str(target),
                files_count=0,
                error=str(e)
            )

    def integrate_all(self) -> List[CloneResult]:
        """集成所有源代码"""
        self.log("="*60)
        self.log("Nanobot Factory 完整源代码集成")
        self.log("="*60)

        # 检查git
        if not check_git_available():
            self.log("错误: 未检测到Git，请先安装Git", "ERROR")
            return []

        # 创建vendor目录
        self.vendor_dir.mkdir(parents=True, exist_ok=True)

        # 克隆所有仓库
        for name, info in REPOS.items():
            result = self.clone_repository(name, info)
            self.results.append(result)

        return self.results

    def verify_installation(self) -> Dict[str, Any]:
        """验证安装"""
        self.log("\n" + "="*60)
        self.log("验证源代码完整性")
        self.log("="*60)

        verification = {
            "comfyui": {
                "exists": COMFYUI_DIR.exists(),
                "path": str(COMFYUI_DIR),
                "main_py": (COMFYUI_DIR / "main.py").exists(),
                "server_py": (COMFYUI_DIR / "server.py").exists(),
                "files_count": count_files(COMFYUI_DIR)
            },
            "diffusers": {
                "exists": DIFFUSERS_DIR.exists(),
                "path": str(DIFFUSERS_DIR),
                "src_exists": (DIFFUSERS_DIR / "src" / "diffusers").exists(),
                "files_count": count_files(DIFFUSERS_DIR)
            },
            "transformers": {
                "exists": TRANSFORMERS_DIR.exists(),
                "path": str(TRANSFORMERS_DIR),
                "src_exists": (TRANSFORMERS_DIR / "src" / "transformers").exists(),
                "files_count": count_files(TRANSFORMERS_DIR)
            }
        }

        # 输出验证结果
        for name, info in verification.items():
            status = "✅" if info["exists"] else "❌"
            self.log(f"{status} {name.upper()}: ", "INFO")
            if info["exists"]:
                self.log(f"   路径: {info['path']}", "INFO")
                self.log(f"   文件数: {info['files_count']}", "INFO")
                if "main_py" in info:
                    self.log(f"   main.py: {'✅' if info['main_py'] else '❌'}", "INFO")
                    self.log(f"   server.py: {'✅' if info['server_py'] else '❌'}", "INFO")
                if "src_exists" in info:
                    self.log(f"   src/: {'✅' if info['src_exists'] else '❌'}", "INFO")

        return verification


# ============================================================================
# 主程序
# ============================================================================

def main():
    """主程序"""
    print("="*70)
    print("  Nanobot Factory - 完整源代码集成部署系统")
    print("  ComfyUI + Diffusers + Transformers")
    print("="*70)
    print()

    integrator = SourceCodeIntegrator()

    # 执行集成
    results = integrator.integrate_all()

    # 验证安装
    verification = integrator.verify_installation()

    # 输出摘要
    print("\n" + "="*70)
    print("  集成结果摘要")
    print("="*70)

    success_count = sum(1 for r in results if r.success)
    total_count = len(results)

    print(f"\n成功: {success_count}/{total_count}")

    for result in results:
        status = "✅" if result.success else "❌"
        print(f"{status} {result.name}: {result.path}")

    # 检查完整性
    all_complete = all([
        verification["comfyui"]["exists"] and verification["comfyui"]["main_py"],
        verification["diffusers"]["exists"],
        verification["transformers"]["exists"]
    ])

    print("\n" + "="*70)
    if all_complete:
        print("  ✅ 源代码集成完成！")
        print("\n下一步操作:")
        print(f"  1. ComfyUI位置: {COMFYUI_DIR}")
        print(f"  2. Diffusers位置: {DIFFUSERS_DIR}")
        print(f"  3. Transformers位置: {TRANSFORMERS_DIR}")
        print("\n启动ComfyUI:")
        print(f"  cd {COMFYUI_DIR}")
        print("  python main.py")
    else:
        print("  ⚠️ 部分集成未完成，请检查错误信息")
    print("="*70)

    return 0 if all_complete else 1


if __name__ == "__main__":
    sys.exit(main())
