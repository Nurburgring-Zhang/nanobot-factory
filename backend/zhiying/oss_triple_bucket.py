"""OSS三桶存储架构

智影数据工场的三层存储设计:
- Bucket A (Raw):     原始数据桶 — 采集的原始文件
- Bucket B (Processed): 加工数据桶 — 经过清洗/标注的数据
- Bucket C (Archive):   归档数据桶 — 最终交付与长期保存

基于 infrastructure.storage.StorageManager 的 S3/OSS/MinIO 抽象层
"""

import os
import logging
from typing import Optional, Dict, Any, List
from enum import Enum

from infrastructure.storage import (
    StorageType,
    StorageManager,
)

logger = logging.getLogger(__name__)


class BucketTier(str, Enum):
    """三桶分层"""
    RAW = "raw"              # 原始数据桶 — 采集入
    PROCESSED = "processed"  # 加工数据桶 — 清洗/标注后
    ARCHIVE = "archive"      # 归档数据桶 — 最终交付


class TripleBucketManager:
    """OSS三桶管理器 — 数据在三个桶之间流转

    数据流: Raw → Processed → Archive
    每个桶对应独立的存储策略和生命周期
    """

    def __init__(self, storage_type: StorageType = StorageType.LOCAL,
                 config: Dict[str, Any] = None):
        self._storage_type = storage_type
        self._base_config = config or {}
        self._managers: Dict[BucketTier, StorageManager] = {}

    def _get_manager(self, tier: BucketTier) -> StorageManager:
        """获取指定桶的存储管理器"""
        if tier not in self._managers:
            tier_config = dict(self._base_config)
            # 为每个桶设置独立的bucket名
            bucket_prefix = tier_config.get("bucket_prefix", "zhiying")
            tier_config["bucket"] = f"{bucket_prefix}-{tier.value}"
            self._managers[tier] = StorageManager(
                storage_type=self._storage_type,
                config={"s3": tier_config, "oss": tier_config, "local": tier_config},
            )
        return self._managers[tier]

    def upload_raw(self, file_path: str, object_name: str = None,
                   metadata: dict = None) -> str:
        """上传原始数据到 Raw 桶"""
        mgr = self._get_manager(BucketTier.RAW)
        result = mgr.upload_file(file_path, object_name, metadata or {})
        logger.info(f"Uploaded raw: {object_name or file_path}")
        return result.get("url", "") if isinstance(result, dict) else str(result)

    def promote_to_processed(self, raw_key: str, processed_key: str,
                              file_path: str, metadata: dict = None) -> str:
        """将清洗/标注后的数据提升到 Processed 桶"""
        mgr = self._get_manager(BucketTier.PROCESSED)
        meta = metadata or {}
        meta["source_bucket"] = BucketTier.RAW.value
        meta["source_key"] = raw_key
        result = mgr.upload_file(file_path, processed_key, meta)
        logger.info(f"Promoted to processed: {raw_key} → {processed_key}")
        return result.get("url", "") if isinstance(result, dict) else str(result)

    def archive(self, processed_key: str, archive_key: str,
                 file_path: str, metadata: dict = None) -> str:
        """归档最终数据到 Archive 桶"""
        mgr = self._get_manager(BucketTier.ARCHIVE)
        meta = metadata or {}
        meta["source_bucket"] = BucketTier.PROCESSED.value
        meta["source_key"] = processed_key
        result = mgr.upload_file(file_path, archive_key, meta)
        logger.info(f"Archived: {processed_key} → {archive_key}")
        return result.get("url", "") if isinstance(result, dict) else str(result)

    def download_raw(self, object_name: str, local_path: str) -> str:
        """从 Raw 桶下载"""
        mgr = self._get_manager(BucketTier.RAW)
        return mgr.download_file(object_name, local_path)

    def download_processed(self, object_name: str, local_path: str) -> str:
        """从 Processed 桶下载"""
        mgr = self._get_manager(BucketTier.PROCESSED)
        return mgr.download_file(object_name, local_path)

    def download_archive(self, object_name: str, local_path: str) -> str:
        """从 Archive 桶下载"""
        mgr = self._get_manager(BucketTier.ARCHIVE)
        return mgr.download_file(object_name, local_path)

    def list_bucket(self, tier: BucketTier, prefix: str = "",
                     max_keys: int = 1000) -> List[dict]:
        """列出桶中对象"""
        mgr = self._get_manager(tier)
        return mgr.list_objects(prefix=prefix, max_keys=max_keys)

    def delete_from_raw(self, object_name: str):
        """从 Raw 桶删除"""
        mgr = self._get_manager(BucketTier.RAW)
        mgr.delete_object(object_name)

    def get_stats(self) -> Dict[str, Any]:
        """获取三桶存储统计"""
        stats = {}
        for tier in BucketTier:
            try:
                mgr = self._get_manager(tier)
                stats[tier.value] = {
                    "bucket": mgr.bucket if hasattr(mgr, 'bucket') else f"zhiying-{tier.value}",
                    "storage_type": self._storage_type.value,
                    "configured": getattr(mgr, '_is_configured', False),
                }
            except Exception as e:
                stats[tier.value] = {"error": str(e)}
        return stats


# 全局单例
_triple_bucket: Optional[TripleBucketManager] = None


def get_triple_bucket(storage_type: StorageType = None,
                       config: Dict[str, Any] = None) -> TripleBucketManager:
    global _triple_bucket
    if _triple_bucket is None:
        _triple_bucket = TripleBucketManager(
            storage_type=storage_type or StorageType.LOCAL,
            config=config,
        )
    return _triple_bucket


__all__ = [
    "BucketTier",
    "TripleBucketManager",
    "get_triple_bucket",
]
