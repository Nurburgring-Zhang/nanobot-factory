"""智影 V4 — StorageEngine: 多后端存储 (MinIO/S3/OSS/Local/Postgres+Lineage)"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..crawler.base import RawDocument
from .base import ProcessedItem, ProcessingPipeline

logger = logging.getLogger(__name__)


class StorageBackend(str, Enum):
    """存储后端"""

    MINIO = "minio"
    S3 = "s3"
    ALIYUN_OSS = "oss"
    TENCENT_COS = "cos"
    LOCAL = "local"
    POSTGRES = "postgres"
    SQLITE = "sqlite"


class StorageEngine(ProcessingPipeline):
    """多后端存储 — 内容 → 对象存储 + 元数据 → Postgres"""

    def __init__(
        self,
        content_backend: StorageBackend = StorageBackend.MINIO,
        metadata_backend: StorageBackend = StorageBackend.SQLITE,
        bucket: str = "imdf-intelligence",
        prefix: str = "v4/",
        record_lineage: bool = True,
    ):
        super().__init__(name="store")
        self.content_backend = content_backend
        self.metadata_backend = metadata_backend
        self.bucket = bucket
        self.prefix = prefix
        self.record_lineage = record_lineage
        # 懒加载
        self._oss = None
        self._s3 = None
        self._minio = None
        # in-memory index (真实环境走 DB)
        self._stored_index: Dict[str, ProcessedItem] = {}
        self._lineage: List[Dict[str, Any]] = []

    def process(self, items: List[Union[ProcessedItem, RawDocument]]) -> List[ProcessedItem]:
        items = self._to_items(items)
        self.metrics.total += len(items)
        out: List[ProcessedItem] = []
        for item in items:
            try:
                self._store_one(item)
                self.metrics.stored += 1
                item.status = "stored"
                item.audit_chain.append(
                    {
                        "step": "store",
                        "action": "stored",
                        "media_uri": item.media_uri,
                        "backend": self.content_backend.value,
                        "ts": _now(),
                    }
                )
                out.append(item)
            except Exception as e:
                self.metrics.rejected += 1
                item.rejection_reason = f"store_error:{e}"
                logger.warning(f"storage failed for {item.source_url}: {e}")
                out.append(item)
        self.finish()
        return out

    def _store_one(self, item: ProcessedItem):
        """存一个 item: 内容 → 对象存储, 元数据 → DB"""
        # 1. 算 storage key
        key = self._compute_key(item)
        # 2. 写对象存储
        content = self._serialize(item)
        if self.content_backend == StorageBackend.LOCAL:
            uri = self._store_local(key, content)
        elif self.content_backend in (StorageBackend.MINIO, StorageBackend.S3):
            uri = self._store_s3_compat(key, content)
        else:
            uri = self._store_local(key, content)  # 退化
        item.media_uri = uri
        # 3. 写元数据 (in-memory index, 真实环境走 DB)
        self._stored_index[item.content_hash] = item
        # 4. Lineage
        if self.record_lineage:
            self._lineage.append(
                {
                    "content_hash": item.content_hash,
                    "source_url": item.source_url,
                    "source_channel": item.source_channel,
                    "media_uri": uri,
                    "crawled_at": item.created_at,
                    "stored_at": _now(),
                }
            )

    def _compute_key(self, item: ProcessedItem) -> str:
        """存 key — prefix/date/hash[:2]/hash"""
        from datetime import datetime
        h = item.content_hash or hashlib.sha256(
            ((item.text or "") + item.source_url).encode("utf-8")
        ).hexdigest()
        date_part = datetime.utcnow().strftime("%Y/%m/%d")
        return f"{self.prefix}{date_part}/{h[:2]}/{h}"

    def _serialize(self, item: ProcessedItem) -> bytes:
        """序列化为 JSON bytes"""
        d = item.to_dict()
        d.pop("embedding", None)  # embedding 单独存
        d.pop("audit_chain", None)
        return json.dumps(d, ensure_ascii=False, default=str).encode("utf-8")

    def _store_local(self, key: str, content: bytes) -> str:
        """本地文件存储"""
        base = os.environ.get("IMDF_LOCAL_STORAGE_ROOT", "D:/Hermes/生产平台/nanobot-factory/backend/data/v4_storage")
        full = os.path.join(base, key.replace("/", os.sep))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(content)
        return f"file:///{full.replace(os.sep, '/')}"

    def _store_s3_compat(self, key: str, content: bytes) -> str:
        """S3 / MinIO 兼容存储"""
        try:
            import boto3
        except ImportError:
            return self._store_local(key, content)
        if self._s3 is None:
            endpoint = os.environ.get("IMDF_S3_ENDPOINT", "")  # MinIO endpoint
            access_key = os.environ.get("IMDF_S3_ACCESS_KEY", "")
            secret_key = os.environ.get("IMDF_S3_SECRET_KEY", "")
            region = os.environ.get("IMDF_S3_REGION", "us-east-1")
            self._s3 = boto3.client(
                "s3",
                endpoint_url=endpoint or None,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
        try:
            self._s3.put_object(Bucket=self.bucket, Key=key, Body=content)
            endpoint = self._s3.meta.endpoint_url or f"s3://{self.bucket}"
            return f"{endpoint.rstrip('/')}/{self.bucket}/{key}"
        except Exception as e:
            logger.warning(f"S3 store failed ({e}), fallback to local")
            return self._store_local(key, content)

    # 公开方法
    def get_index_size(self) -> int:
        return len(self._stored_index)

    def get_lineage(self, content_hash: Optional[str] = None) -> List[Dict[str, Any]]:
        if content_hash:
            return [l for l in self._lineage if l["content_hash"] == content_hash]
        return self._lineage

    def export_index(self) -> List[Dict[str, Any]]:
        """导出 in-memory index (调试/审计用)"""
        return [
            {
                "content_hash": h,
                "title": it.title,
                "url": it.source_url,
                "modality": it.modality,
                "labels": it.labels,
                "quality": it.quality_score,
                "aesthetic": it.aesthetic_score,
            }
            for h, it in self._stored_index.items()
        ]


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
