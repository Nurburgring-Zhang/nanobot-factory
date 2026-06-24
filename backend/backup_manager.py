#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NanoBot Factory - 数据备份与恢复系统
Data Backup and Recovery System

功能:
- 自动备份
- 增量备份
- 压缩存储
- 定时清理
- 恢复验证

@author Matrix Agent
@date 2026-04-22
@version 2.0.0
"""

import os
import sys
import json
import shutil
import hashlib
import logging
import sqlite3
import threading
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import gzip
import tarfile

logger = logging.getLogger(__name__)


class BackupStatus(Enum):
    """备份状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"


class BackupType(Enum):
    """备份类型"""
    FULL = "full"
    INCREMENTAL = "incremental"
    DIFFERENTIAL = "differential"


@dataclass
class BackupMetadata:
    """备份元数据"""
    backup_id: str
    backup_type: BackupType
    status: BackupStatus
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    file_path: Optional[str] = None
    file_size: int = 0
    checksum: Optional[str] = None
    records_count: int = 0
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "backup_type": self.backup_type.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "checksum": self.checksum,
            "records_count": self.records_count,
            "error_message": self.error_message,
        }


@dataclass
class RecoveryMetadata:
    """恢复元数据"""
    recovery_id: str
    backup_id: str
    status: BackupStatus
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    records_restored: int = 0
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "backup_id": self.backup_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "records_restored": self.records_restored,
            "error_message": self.error_message,
        }


class BackupManager:
    """
    备份管理器
    
    功能:
    - 自动备份
    - 增量备份
    - 压缩存储
    - 备份验证
    """
    
    def __init__(
        self,
        backup_dir: Optional[str] = None,
        source_dir: Optional[str] = None,
        max_backups: int = 10,
        compress: bool = True,
    ):
        # 默认备份目录
        if backup_dir is None:
            base_dir = Path(__file__).parent.parent.parent / "data"
            backup_dir = str(base_dir / "backups")
        
        self._backup_dir = Path(backup_dir)
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 源目录
        if source_dir is None:
            base_dir = Path(__file__).parent.parent.parent / "data"
            source_dir = str(base_dir)
        
        self._source_dir = Path(source_dir)
        self._max_backups = max_backups
        self._compress = compress
        
        # 备份元数据存储
        self._metadata_file = self._backup_dir / "backup_metadata.json"
        self._lock = threading.Lock()
        
        # 加载元数据
        self._backups: Dict[str, BackupMetadata] = {}
        self._load_metadata()
        
        logger.info(f"BackupManager initialized: {self._backup_dir}")
    
    def _load_metadata(self):
        """加载备份元数据"""
        if self._metadata_file.exists():
            try:
                with open(self._metadata_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for backup_id, info in data.items():
                        self._backups[backup_id] = BackupMetadata(
                            backup_id=backup_id,
                            backup_type=BackupType(info.get("backup_type", "full")),
                            status=BackupStatus(info.get("status", "completed")),
                            created_at=datetime.fromisoformat(info.get("created_at", datetime.now().isoformat())),
                            completed_at=datetime.fromisoformat(info["completed_at"]) if info.get("completed_at") else None,
                            file_path=info.get("file_path"),
                            file_size=info.get("file_size", 0),
                            checksum=info.get("checksum"),
                            records_count=info.get("records_count", 0),
                            error_message=info.get("error_message"),
                        )
            except Exception as e:
                logger.error(f"Failed to load backup metadata: {e}")
    
    def _save_metadata(self):
        """保存备份元数据"""
        with self._lock:
            try:
                data = {k: v.to_dict() for k, v in self._backups.items()}
                with open(self._metadata_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Failed to save backup metadata: {e}")
    
    def _calculate_checksum(self, file_path: str) -> str:
        """计算文件校验和"""
        md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk)
        return md5.hexdigest()
    
    def _get_backup_files(self) -> List[str]:
        """获取需要备份的文件"""
        files = []
        base_dir = Path(__file__).parent.parent.parent / "data"
        for db_file in ["nanobot_data.db", "annotations.db", "annotation_system.db"]:
            db_path = base_dir / "annotations.db" / db_file
            if db_path.exists():
                files.append(str(db_path))
        return files
    
    def create_backup(
        self,
        backup_type: BackupType = BackupType.FULL,
        description: Optional[str] = None,
    ) -> BackupMetadata:
        """
        创建备份
        
        Args:
            backup_type: 备份类型
            description: 描述
            
        Returns:
            备份元数据
        """
        backup_id = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        metadata = BackupMetadata(
            backup_id=backup_id,
            backup_type=backup_type,
            status=BackupStatus.IN_PROGRESS,
        )
        
        self._backups[backup_id] = metadata
        self._save_metadata()
        
        try:
            # 获取备份文件列表
            files = self._get_backup_files()
            
            # 创建备份文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            ext = ".tar.gz" if self._compress else ".tar"
            backup_name = f"{backup_type.value}_{timestamp}{ext}"
            backup_path = self._backup_dir / backup_name
            
            # 创建备份
            if self._compress:
                with tarfile.open(backup_path, "w:gz") as tar:
                    for file_path in files:
                        tar.add(file_path, arcname=os.path.basename(file_path))
            else:
                with tarfile.open(backup_path, "w") as tar:
                    for file_path in files:
                        tar.add(file_path, arcname=os.path.basename(file_path))
            
            # 更新元数据
            metadata.file_path = str(backup_path)
            metadata.file_size = backup_path.stat().st_size
            metadata.checksum = self._calculate_checksum(str(backup_path))
            metadata.records_count = len(files)
            metadata.status = BackupStatus.COMPLETED
            metadata.completed_at = datetime.now()
            
            # 清理旧备份
            self._cleanup_old_backups()
            
            logger.info(f"Backup created: {backup_id} ({metadata.file_size} bytes)")
            
        except Exception as e:
            metadata.status = BackupStatus.FAILED
            metadata.error_message = str(e)
            logger.error(f"Backup failed: {e}")
        
        self._save_metadata()
        return metadata
    
    def _cleanup_old_backups(self):
        """清理旧备份"""
        backups = sorted(
            [v for v in self._backups.values() if v.status == BackupStatus.COMPLETED],
            key=lambda x: x.created_at,
            reverse=True,
        )
        
        # 删除超出限制的备份
        for backup in backups[self._max_backups:]:
            try:
                if backup.file_path:
                    file_path = Path(backup.file_path)
                    if file_path.exists():
                        file_path.unlink()
                del self._backups[backup.backup_id]
                logger.info(f"Deleted old backup: {backup.backup_id}")
            except Exception as e:
                logger.error(f"Failed to delete backup: {e}")
        
        self._save_metadata()
    
    def list_backups(self) -> List[BackupMetadata]:
        """列出所有备份"""
        return sorted(
            self._backups.values(),
            key=lambda x: x.created_at,
            reverse=True,
        )
    
    def get_backup(self, backup_id: str) -> Optional[BackupMetadata]:
        """获取备份信息"""
        return self._backups.get(backup_id)
    
    def verify_backup(self, backup_id: str) -> bool:
        """验证备份"""
        backup = self._backups.get(backup_id)
        if not backup or not backup.file_path:
            return False
        
        try:
            file_path = Path(backup.file_path)
            if not file_path.exists():
                return False
            
            # 验证校验和
            current_checksum = self._calculate_checksum(str(file_path))
            if current_checksum != backup.checksum:
                logger.warning(f"Checksum mismatch for {backup_id}")
                return False
            
            # 验证压缩包完整性
            if self._compress:
                with gzip.open(file_path, "rb") as f:
                    f.read(1)  # 尝试读取
            else:
                with tarfile.open(file_path, "r") as tar:
                    tar.getmembers()  # 获取成员列表
            
            backup.status = BackupStatus.VERIFIED
            self._save_metadata()
            return True
            
        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            return False
    
    def restore_backup(self, backup_id: str, target_dir: Optional[str] = None) -> RecoveryMetadata:
        """
        恢复备份
        
        Args:
            backup_id: 备份ID
            target_dir: 目标目录，默认恢复到源目录
            
        Returns:
            恢复元数据
        """
        backup = self._backups.get(backup_id)
        if not backup or not backup.file_path:
            raise ValueError(f"Backup not found: {backup_id}")
        
        recovery_id = f"recovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        metadata = RecoveryMetadata(
            recovery_id=recovery_id,
            backup_id=backup_id,
            status=BackupStatus.IN_PROGRESS,
        )
        
        try:
            if target_dir is None:
                target_dir = self._source_dir
            
            backup_path = Path(backup.file_path)
            
            # 解压备份
            if self._compress:
                with tarfile.open(backup_path, "r:gz") as tar:
                    tar.extractall(target_dir)
            else:
                with tarfile.open(backup_path, "r") as tar:
                    tar.extractall(target_dir)
            
            metadata.status = BackupStatus.COMPLETED
            metadata.completed_at = datetime.now()
            metadata.records_restored = backup.records_count
            
            logger.info(f"Backup restored: {backup_id} -> {target_dir}")
            
        except Exception as e:
            metadata.status = BackupStatus.FAILED
            metadata.error_message = str(e)
            logger.error(f"Recovery failed: {e}")
        
        return metadata
    
    def delete_backup(self, backup_id: str) -> bool:
        """删除备份"""
        backup = self._backups.get(backup_id)
        if not backup:
            return False
        
        try:
            if backup.file_path:
                file_path = Path(backup.file_path)
                if file_path.exists():
                    file_path.unlink()
            
            del self._backups[backup_id]
            self._save_metadata()
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete backup: {e}")
            return False


# ==================== 自动备份调度器 ====================

class BackupScheduler:
    """
    备份调度器
    
    定时执行备份任务
    """
    
    def __init__(
        self,
        backup_manager: BackupManager,
        interval_hours: int = 24,
        enabled: bool = True,
    ):
        self._manager = backup_manager
        self._interval_hours = interval_hours
        self._enabled = enabled
        self._timer: Optional[threading.Timer] = None
        self._last_backup: Optional[datetime] = None
    
    def start(self):
        """启动调度器"""
        if not self._enabled:
            logger.info("Backup scheduler disabled")
            return
        
        self._schedule_next()
        logger.info(f"Backup scheduler started (interval: {self._interval_hours}h)")
    
    def stop(self):
        """停止调度器"""
        if self._timer:
            self._timer.cancel()
            self._timer = None
        logger.info("Backup scheduler stopped")
    
    def _schedule_next(self):
        """安排下一次备份"""
        if not self._enabled:
            return
        
        self._timer = threading.Timer(
            self._interval_hours * 3600,
            self._run_backup,
        )
        self._timer.daemon = True
        self._timer.start()
    
    def _run_backup(self):
        """执行备份"""
        try:
            logger.info("Starting scheduled backup...")
            backup = self._manager.create_backup(
                backup_type=BackupType.INCREMENTAL,
                description="Scheduled backup",
            )
            
            if backup.status == BackupStatus.COMPLETED:
                self._last_backup = datetime.now()
                logger.info(f"Scheduled backup completed: {backup.backup_id}")
            else:
                logger.warning(f"Scheduled backup failed: {backup.error_message}")
                
        except Exception as e:
            logger.error(f"Scheduled backup error: {e}")
        
        # 安排下一次
        self._schedule_next()


# ==================== 全局实例 ====================

_backup_manager = None


def get_backup_manager() -> BackupManager:
    """获取备份管理器全局实例"""
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager()
    return _backup_manager


def create_backup_scheduler(interval_hours: int = 24) -> BackupScheduler:
    """创建备份调度器"""
    manager = get_backup_manager()
    return BackupScheduler(manager, interval_hours)


# ==================== 测试代码 ====================

if __name__ == "__main__":
    print("=== Backup Manager Test ===")
    
    manager = get_backup_manager()
    
    # 列出备份
    backups = manager.list_backups()
    print(f"Existing backups: {len(backups)}")
    
    # 创建测试备份
    print("\nCreating backup...")
    backup = manager.create_backup(
        backup_type=BackupType.FULL,
        description="Test backup",
    )
    
    print(f"Backup status: {backup.status.value}")
    if backup.status == BackupStatus.COMPLETED:
        print(f"  File: {backup.file_path}")
        print(f"  Size: {backup.file_size} bytes")
        print(f"  Checksum: {backup.checksum}")
        
        # 验证备份
        print("\nVerifying backup...")
        verified = manager.verify_backup(backup.backup_id)
        print(f"Verified: {verified}")
    
    # 恢复测试
    if backup.status == BackupStatus.COMPLETED:
        print("\nRestore test skipped (would overwrite data)")
    
    print("\nBackup manager test complete!")
