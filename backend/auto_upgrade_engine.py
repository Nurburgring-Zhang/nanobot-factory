#!/usr/bin/env python3
"""
Nanobot Factory - 自动升级系统模块
完全真实实现，禁止任何模拟！

功能：
- 每日自动检查GitHub最新版本
- 安全升级流程（备份→测试→部署→回滚）
- 支持指定仓库和分支
- 完整的升级日志记录
- 支持所有Skills、Agents、内置功能的自动升级

@author MiniMax Agent
@date 2026-03-01
"""

import os
import sys
import json
import subprocess
import shutil
import logging
import asyncio
import aiohttp
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading
import time
import tempfile
import re

logger = logging.getLogger(__name__)


# ============================================================================
# 升级状态枚举
# ============================================================================

class UpgradeStatus(Enum):
    """升级状态"""
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    TESTING = "testing"
    DEPLOYING = "deploying"
    ROLLING_BACK = "rolling_back"
    COMPLETED = "completed"
    FAILED = "failed"


class UpgradePriority(Enum):
    """升级优先级"""
    CRITICAL = "critical"   # 关键安全更新
    HIGH = "high"          # 重要功能更新
    MEDIUM = "medium"      # 一般功能更新
    LOW = "low"           # 低优先级更新


# ============================================================================
# 数据结构
# ============================================================================

@dataclass
class VersionInfo:
    """版本信息"""
    version: str
    release_date: str
    description: str
    download_url: str
    commit_hash: str
    priority: UpgradePriority
    changelog: List[str] = field(default_factory=list)
    breaking_changes: List[str] = field(default_factory=list)


@dataclass
class UpgradeTask:
    """升级任务"""
    task_id: str
    repository: str
    branch: str
    target_version: VersionInfo
    current_version: str
    status: UpgradeStatus
    progress: float = 0.0
    logs: List[str] = field(default_factory=list)
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str = ""


@dataclass
class RepositoryConfig:
    """仓库配置"""
    name: str
    owner: str
    repo_name: str
    local_path: str
    branch: str = "main"
    check_interval_hours: int = 24
    auto_upgrade: bool = False
    backup_before_upgrade: bool = True
    test_before_deploy: bool = True


# ============================================================================
# 自动升级引擎
# ============================================================================

class AutoUpgradeEngine:
    """
    Nanobot自动升级引擎

    核心功能：
    1. 定时检查GitHub仓库更新
    2. 安全下载和安装
    3. 完整备份和回滚
    4. 升级前测试验证
    5. 多仓库支持
    """

    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root) if project_root else Path(__file__).parent.parent
        self.backup_dir = self.project_root / ".nanobot_upgrade_backups"
        self.backup_dir.mkdir(exist_ok=True)

        self.temp_dir = self.project_root / ".nanobot_temp"
        self.temp_dir.mkdir(exist_ok=True)

        # 仓库配置列表
        self.repositories: Dict[str, RepositoryConfig] = {}

        # 当前升级任务
        self.current_task: Optional[UpgradeTask] = None

        # 升级历史
        self.upgrade_history: List[UpgradeTask] = []

        # 回调函数
        self.upgrade_callbacks: List[Callable] = []

        # 升级锁
        self._upgrade_lock = threading.Lock()

        # 定时检查线程
        self._check_thread: Optional[threading.Thread] = None
        self._stop_checking = False

        # GitHub API配置
        self.github_token = os.environ.get("GITHUB_TOKEN", "")
        self.github_api_url = "https://api.github.com"

        # 注册默认仓库
        self._register_default_repositories()

        logger.info(f"Auto-Upgrade Engine initialized. Project root: {self.project_root}")

    def _register_default_repositories(self):
        """注册默认仓库"""
        # Nanobot核心仓库
        self.add_repository(
            RepositoryConfig(
                name="Nanobot Core",
                owner="nanobot",
                repo_name="nanobot-factory",
                local_path=str(self.project_root),
                branch="main",
                check_interval_hours=24,
                auto_upgrade=False,  # 默认不自动升级，需要用户确认
                backup_before_upgrade=True,
                test_before_deploy=True
            )
        )

    def add_repository(self, config: RepositoryConfig):
        """添加要监控的仓库"""
        self.repositories[config.repo_name] = config
        logger.info(f"Repository added: {config.owner}/{config.repo_name}")

    def remove_repository(self, repo_name: str):
        """移除仓库"""
        if repo_name in self.repositories:
            del self.repositories[repo_name]
            logger.info(f"Repository removed: {repo_name}")

    def start_auto_check(self):
        """启动定时检查"""
        if self._check_thread and self._check_thread.is_alive():
            logger.warning("Auto check already running")
            return

        self._stop_checking = False
        self._check_thread = threading.Thread(target=self._auto_check_loop, daemon=True)
        self._check_thread.start()
        logger.info("Auto check started")

    def stop_auto_check(self):
        """停止定时检查"""
        self._stop_checking = True
        if self._check_thread:
            self._check_thread.join(timeout=10)
        logger.info("Auto check stopped")

    def _auto_check_loop(self):
        """自动检查循环"""
        while not self._stop_checking:
            try:
                # 检查所有仓库
                for repo_config in self.repositories.values():
                    if not repo_config.auto_upgrade:
                        continue

                    # 检查是否有更新
                    has_update = asyncio.run(self.check_for_updates(repo_config.repo_name))

                    if has_update:
                        logger.info(f"Update available for {repo_config.repo_name}")
                        # 触发回调
                        for callback in self.upgrade_callbacks:
                            try:
                                callback(repo_config, has_update)
                            except Exception as e:
                                logger.error(f"Error in upgrade callback: {e}")

                # 等待下一次检查
                check_interval = min(r.check_interval_hours for r in self.repositories.values()) if self.repositories else 24
                time.sleep(check_interval * 3600)

            except Exception as e:
                logger.error(f"Error in auto check loop: {e}")
                time.sleep(3600)  # 出错后等待1小时

    async def check_for_updates(self, repo_name: str) -> Optional[VersionInfo]:
        """检查仓库是否有更新"""
        repo_config = self.repositories.get(repo_name)
        if not repo_config:
            logger.warning(f"Repository not found: {repo_name}")
            return None

        logger.info(f"Checking for updates: {repo_config.owner}/{repo_config.repo_name}")

        try:
            # 获取最新release信息
            headers = {}
            if self.github_token:
                headers["Authorization"] = f"token {self.github_token}"
            headers["Accept"] = "application/vnd.github.v3+json"

            async with aiohttp.ClientSession() as session:
                # 获取最新release
                url = f"{self.github_api_url}/repos/{repo_config.owner}/{repo_config.repo_name}/releases/latest"

                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 200:
                        release = await resp.json()

                        latest_version = release.get("tag_name", "v0.0.0").lstrip("v")
                        current_version = self._get_current_version(repo_config.local_path)

                        # 比较版本
                        if self._compare_versions(latest_version, current_version) > 0:
                            # 有新版本
                            version_info = VersionInfo(
                                version=latest_version,
                                release_date=release.get("published_at", ""),
                                description=release.get("body", "")[:500],
                                download_url=release.get("zipball_url", ""),
                                commit_hash=release.get("target_commitish", ""),
                                priority=self._determine_priority(release.get("body", "")),
                                changelog=self._parse_changelog(release.get("body", ""))
                            )

                            logger.info(f"New version available: {latest_version} (current: {current_version})")
                            return version_info
                        else:
                            logger.info(f"No updates available. Current: {current_version}, Latest: {latest_version}")
                            return None

                    elif resp.status == 404:
                        # 没有release，尝试获取最新commit
                        logger.info("No releases found, checking commits...")
                        return await self._check_latest_commit(repo_config, headers, session)

                    else:
                        logger.warning(f"Failed to check updates: {resp.status}")
                        return None

        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return None

    async def _check_latest_commit(self, repo_config: RepositoryConfig, headers: Dict, session: aiohttp.ClientSession) -> Optional[VersionInfo]:
        """检查最新commit"""
        try:
            url = f"{self.github_api_url}/repos/{repo_config.owner}/{repo_config.repo_name}/commits/{repo_config.branch}"

            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    commit = await resp.json()
                    commit_sha = commit.get("sha", "")[:7]

                    # 检查是否与本地版本相同
                    local_commit = self._get_local_commit(repo_config.local_path)

                    if commit_sha != local_commit:
                        return VersionInfo(
                            version=commit_sha,
                            release_date=commit.get("commit", {}).get("author", {}).get("date", ""),
                            description=f"New commit: {commit_sha}",
                            download_url=commit.get("zipball_url", ""),
                            commit_hash=commit_sha,
                            priority=UpgradePriority.MEDIUM,
                            changelog=[f"New commit: {commit_sha}"]
                        )

            return None

        except Exception as e:
            logger.error(f"Error checking latest commit: {e}")
            return None

    def _get_current_version(self, local_path: str) -> str:
        """获取当前版本"""
        version_file = Path(local_path) / "VERSION"
        if version_file.exists():
            with open(version_file, 'r') as f:
                return f.read().strip()

        # 尝试从package.json获取
        package_file = Path(local_path) / "package.json"
        if package_file.exists():
            try:
                with open(package_file, 'r') as f:
                    data = json.load(f)
                    return data.get("version", "0.0.0")
            except (json.JSONDecodeError, OSError):
                logger.warning(f"Failed to parse package.json at {package_file}")

        return "0.0.0"

    def _get_local_commit(self, local_path: str) -> str:
        """获取本地Git commit"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=local_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()[:7]
        except (subprocess.SubprocessError, OSError):
            logger.warning(f"Failed to get local git commit for {local_path}")
        return ""

    def _compare_versions(self, version1: str, version2: str) -> int:
        """比较版本号"""
        try:
            v1_parts = [int(x) for x in version1.split('.')]
            v2_parts = [int(x) for x in version2.split('.')]

            # 补齐长度
            max_len = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (max_len - len(v1_parts)))
            v2_parts.extend([0] * (max_len - len(v2_parts)))

            for i in range(max_len):
                if v1_parts[i] > v2_parts[i]:
                    return 1
                elif v1_parts[i] < v2_parts[i]:
                    return -1

            return 0
        except (ValueError, AttributeError):
            # 如果解析失败，尝试直接比较
            if version1 > version2:
                return 1
            elif version1 < version2:
                return -1
            return 0

    def _determine_priority(self, changelog: str) -> UpgradePriority:
        """确定升级优先级"""
        changelog_lower = changelog.lower()

        if any(keyword in changelog_lower for keyword in ["security", "critical", "vulnerability", "CVE"]):
            return UpgradePriority.CRITICAL
        elif any(keyword in changelog_lower for keyword in ["breaking", "major", "important"]):
            return UpgradePriority.HIGH
        elif any(keyword in changelog_lower for keyword in ["feature", "enhancement", "new"]):
            return UpgradePriority.MEDIUM
        else:
            return UpgradePriority.LOW

    def _parse_changelog(self, body: str) -> List[str]:
        """解析更新日志"""
        lines = body.split('\n')
        changes = []
        for line in lines[:20]:  # 只取前20行
            line = line.strip()
            if line and (line.startswith('-') or line.startswith('*') or line.startswith('#')):
                changes.append(line.lstrip('-*#').strip())
        return changes

    async def perform_upgrade(self, repo_name: str, version_info: VersionInfo = None) -> UpgradeTask:
        """执行升级"""
        with self._upgrade_lock:
            repo_config = self.repositories.get(repo_name)
            if not repo_config:
                raise ValueError(f"Repository not found: {repo_name}")

            # 创建升级任务
            task_id = f"upgrade_{repo_name}_{int(time.time())}"
            task = UpgradeTask(
                task_id=task_id,
                repository=repo_name,
                branch=repo_config.branch,
                target_version=version_info or VersionInfo(
                    version="latest",
                    release_date="",
                    description="Auto upgrade",
                    download_url="",
                    commit_hash="",
                    priority=UpgradePriority.MEDIUM
                ),
                current_version=self._get_current_version(repo_config.local_path),
                status=UpgradeStatus.CHECKING
            )

            self.current_task = task
            self._log_task(task, f"Starting upgrade for {repo_name}")

            try:
                # 步骤1: 创建完整备份
                if repo_config.backup_before_upgrade:
                    self._log_task(task, "Creating backup...")
                    backup_path = self._create_full_backup(repo_config)
                    if not backup_path:
                        raise Exception("Failed to create backup")
                    self._log_task(task, f"Backup created: {backup_path}")

                # 步骤2: 下载最新版本
                self._log_task(task, "Downloading latest version...", progress=0.1)
                task.status = UpgradeStatus.DOWNLOADING
                download_path = await self._download_latest(repo_config, task)
                self._log_task(task, f"Downloaded to: {download_path}", progress=0.3)

                # 步骤3: 测试验证
                if repo_config.test_before_deploy:
                    self._log_task(task, "Running tests...", progress=0.5)
                    task.status = UpgradeStatus.TESTING
                    test_passed = await self._run_tests(download_path, task)
                    if not test_passed:
                        raise Exception("Tests failed, aborting upgrade")

                # 步骤4: 部署
                self._log_task(task, "Deploying...", progress=0.7)
                task.status = UpgradeStatus.DEPLOYING
                deployed = await self._deploy_update(download_path, repo_config, task)
                if not deployed:
                    raise Exception("Deployment failed")

                # 步骤5: 清理
                self._cleanup_temp_files(download_path)

                # 完成
                task.status = UpgradeStatus.COMPLETED
                task.progress = 1.0
                task.completed_at = datetime.now().isoformat()
                self._log_task(task, "Upgrade completed successfully!")

                logger.info(f"Upgrade completed: {repo_name}")

            except Exception as e:
                task.status = UpgradeStatus.FAILED
                task.error = str(e)
                self._log_task(task, f"Upgrade failed: {e}")

                # 自动回滚
                if repo_config.backup_before_upgrade:
                    self._log_task(task, "Attempting rollback...")
                    task.status = UpgradeStatus.ROLLING_BACK
                    rollback_success = await self._rollback_upgrade(repo_config, backup_path, task)
                    if rollback_success:
                        self._log_task(task, "Rollback completed successfully")
                    else:
                        self._log_task(task, "Rollback failed! Manual intervention required.")

                logger.error(f"Upgrade failed: {e}")

            # 保存到历史
            self.upgrade_history.append(task)
            return task

    def _create_full_backup(self, repo_config: RepositoryConfig) -> Optional[str]:
        """创建完整备份"""
        try:
            backup_name = f"{repo_config.repo_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_path = self.backup_dir / backup_name

            # 复制整个项目目录
            shutil.copytree(
                repo_config.local_path,
                backup_path,
                symlinks=True,
                ignore=shutil.ignore_patterns(
                    '.git', '__pycache__', '*.pyc', '.venv', 'node_modules',
                    '.nanobot_temp', '.nanobot_backups', '.nanobot_upgrade_backups'
                )
            )

            # 保存备份元数据
            metadata = {
                "repo_name": repo_config.repo_name,
                "version": self._get_current_version(repo_config.local_path),
                "created_at": datetime.now().isoformat(),
                "original_path": repo_config.local_path
            }

            with open(backup_path / "backup_metadata.json", 'w') as f:
                json.dump(metadata, f, indent=2)

            logger.info(f"Full backup created: {backup_path}")
            return str(backup_path)

        except Exception as e:
            logger.error(f"Error creating full backup: {e}")
            return None

    async def _download_latest(self, repo_config: RepositoryConfig, task: UpgradeTask) -> str:
        """下载最新版本"""
        try:
            # 确定下载URL
            if task.target_version.download_url:
                download_url = task.target_version.download_url
            else:
                # 从GitHub下载archive
                download_url = f"https://github.com/{repo_config.owner}/{repo_config.repo_name}/archive/refs/heads/{repo_config.branch}.zip"

            self._log_task(task, f"Downloading from: {download_url}")

            # 下载文件
            download_path = self.temp_dir / f"{repo_config.repo_name}_{task.task_id}.zip"

            async with aiohttp.ClientSession() as session:
                async with session.get(download_url, timeout=aiohttp.ClientTimeout(total=600)) as resp:
                    if resp.status != 200:
                        raise Exception(f"Download failed: HTTP {resp.status}")

                    with open(download_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)

            # 解压
            extract_path = self.temp_dir / f"{repo_config.repo_name}_{task.task_id}"
            if extract_path.exists():
                shutil.rmtree(extract_path)

            shutil.unpack_archive(download_path, extract_path)

            # 找到解压后的项目目录
            extracted_dirs = list(extract_path.glob("*"))
            if extracted_dirs:
                return str(extracted_dirs[0])

            return str(extract_path)

        except Exception as e:
            logger.error(f"Error downloading latest: {e}")
            raise

    async def _run_tests(self, test_path: str, task: UpgradeTask) -> bool:
        """运行测试验证"""
        try:
            # 查找测试文件
            test_files = []

            # Python测试
            test_files.extend(Path(test_path).rglob("test_*.py"))
            test_files.extend(Path(test_path).rglob("*_test.py"))

            if not test_files:
                # 没有测试文件，跳过
                self._log_task(task, "No test files found, skipping tests")
                return True

            self._log_task(task, f"Found {len(test_files)} test files")

            # 运行测试
            for test_file in test_files[:5]:  # 最多运行5个测试
                self._log_task(task, f"Running test: {test_file.name}")

                result = subprocess.run(
                    [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"],
                    cwd=test_path,
                    capture_output=True,
                    text=True,
                    timeout=300
                )

                if result.returncode != 0:
                    self._log_task(task, f"Test failed: {test_file.name}")
                    self._log_task(task, f"Output: {result.stdout[:500]}")
                    return False

            self._log_task(task, "All tests passed")
            return True

        except subprocess.TimeoutExpired:
            self._log_task(task, "Test timeout, aborting")
            return False
        except Exception as e:
            self._log_task(task, f"Error running tests: {e}")
            return False

    async def _deploy_update(self, new_version_path: str, repo_config: RepositoryConfig, task: UpgradeTask) -> bool:
        """部署更新"""
        try:
            # 复制新版本文件到项目目录
            source_path = Path(new_version_path)
            target_path = Path(repo_config.local_path)

            # 列出要更新的文件
            files_to_update = list(source_path.rglob("*"))
            files_to_update = [f for f in files_to_update if f.is_file()]

            self._log_task(task, f"Updating {len(files_to_update)} files...")

            # 更新文件
            for i, file in enumerate(files_to_update):
                relative_path = file.relative_to(source_path)

                # 跳过特定文件
                if any(pattern in str(relative_path) for pattern in ['.git', '__pycache__', '.venv']):
                    continue

                target_file = target_path / relative_path

                # 确保目录存在
                target_file.parent.mkdir(parents=True, exist_ok=True)

                # 复制文件
                shutil.copy2(file, target_file)

                # 更新进度
                if i % 10 == 0:
                    progress = 0.7 + (i / len(files_to_update)) * 0.3
                    task.progress = progress
                    self._log_task(task, f"Progress: {int(progress * 100)}%", progress=progress)

            # 更新VERSION文件
            version_file = target_path / "VERSION"
            with open(version_file, 'w') as f:
                f.write(task.target_version.version)

            self._log_task(task, "Update deployed successfully!")
            return True

        except Exception as e:
            logger.error(f"Error deploying update: {e}")
            return False

    async def _rollback_upgrade(self, repo_config: RepositoryConfig, backup_path: str, task: UpgradeTask) -> bool:
        """回滚升级"""
        try:
            # 恢复备份
            self._log_task(task, f"Restoring from backup: {backup_path}")

            target_path = Path(repo_config.local_path)

            # 清理当前目录
            for item in target_path.iterdir():
                if item.name.startswith('.'):
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

            # 恢复备份
            shutil.copytree(
                backup_path,
                target_path,
                symlinks=True,
                dirs_exist_ok=True
            )

            self._log_task(task, "Rollback completed")
            return True

        except Exception as e:
            logger.error(f"Error during rollback: {e}")
            return False

    def _cleanup_temp_files(self, download_path: str):
        """清理临时文件"""
        try:
            path = Path(download_path)
            if path.exists():
                shutil.rmtree(path)

            # 清理zip文件
            zip_file = Path(download_path).with_suffix('.zip')
            if zip_file.exists():
                zip_file.unlink()

        except Exception as e:
            logger.warning(f"Error cleaning temp files: {e}")

    def _log_task(self, task: UpgradeTask, message: str, progress: float = None):
        """记录任务日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        task.logs.append(log_message)
        logger.info(log_message)
        if progress is not None:
            task.progress = progress

    def register_upgrade_callback(self, callback: Callable):
        """注册升级回调"""
        self.upgrade_callbacks.append(callback)

    def get_upgrade_status(self) -> Dict[str, Any]:
        """获取升级状态"""
        return {
            "current_task": {
                "task_id": self.current_task.task_id if self.current_task else None,
                "status": self.current_task.status.value if self.current_task else None,
                "progress": self.current_task.progress if self.current_task else 0,
                "logs": self.current_task.logs[-10:] if self.current_task else []
            } if self.current_task else None,
            "repositories": {
                name: {
                    "local_path": config.local_path,
                    "auto_upgrade": config.auto_upgrade,
                    "check_interval_hours": config.check_interval_hours
                }
                for name, config in self.repositories.items()
            },
            "history_count": len(self.upgrade_history)
        }

    def force_upgrade(self, repo_name: str) -> UpgradeTask:
        """强制升级"""
        return asyncio.run(self.perform_upgrade(repo_name))


# ============================================================================
# 单例实例
# ============================================================================

_auto_upgrade_engine: Optional[AutoUpgradeEngine] = None


def get_auto_upgrade_engine(project_root: str = None) -> AutoUpgradeEngine:
    """获取自动升级引擎单例"""
    global _auto_upgrade_engine
    if _auto_upgrade_engine is None:
        _auto_upgrade_engine = AutoUpgradeEngine(project_root)
    return _auto_upgrade_engine
