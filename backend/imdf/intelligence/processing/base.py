"""智影 V4 — 处理流水线基类 + 数据结构"""
from __future__ import annotations

import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from ..crawler.base import RawDocument

logger = logging.getLogger(__name__)


@dataclass
class ProcessedItem:
    """处理后的标准化项 — 跨模态统一"""

    # 来源追溯
    source_url: str = ""
    source_channel: str = ""
    source_metadata: Dict[str, Any] = field(default_factory=dict)
    raw_doc_hash: str = ""

    # 内容
    type: str = "text"  # text / image / video / audio / mixed
    title: str = ""
    text: str = ""
    images: List[str] = field(default_factory=list)  # URLs
    files: List[Dict[str, Any]] = field(default_factory=list)
    media_uri: str = ""  # MinIO / OSS URI

    # 评分
    quality_score: float = 0.0  # 0-1
    aesthetic_score: float = 0.0  # 0-1
    custom_scores: Dict[str, float] = field(default_factory=dict)

    # 标签
    labels: List[str] = field(default_factory=list)
    label_confidences: Dict[str, float] = field(default_factory=dict)

    # 分类
    taxonomy_path: List[str] = field(default_factory=list)  # ['Image', 'Nature', 'Landscape']
    modality: str = "text"  # image / video / audio / text / 3d
    domain: str = ""  # Nature / Urban / Portrait / etc.

    # 特征
    embedding: Optional[List[float]] = None  # 1024-d
    content_hash: str = ""
    perceptual_hash: str = ""  # pHash for images/videos
    simhash: str = ""  # text near-dup
    language: str = ""
    size_bytes: int = 0

    # 状态
    status: str = "raw"  # raw / deduped / cleaned / labeled / scored / stored / rejected
    rejection_reason: str = ""
    audit_chain: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v != "" and v != [] and v != {} and v is not None or k in ("rejection_reason", "audit_chain")}


@dataclass
class ProcessingMetrics:
    """处理指标"""

    started_at: float = 0.0
    ended_at: float = 0.0
    total: int = 0
    deduped: int = 0
    cleaned: int = 0
    labeled: int = 0
    scored: int = 0
    classified: int = 0
    stored: int = 0
    rejected: int = 0
    errors: List[str] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "deduped": self.deduped,
            "cleaned": self.cleaned,
            "labeled": self.labeled,
            "scored": self.scored,
            "classified": self.classified,
            "stored": self.stored,
            "rejected": self.rejected,
            "errors": len(self.errors),
            "throughput": round(self.total / max(self.ended_at - self.started_at, 0.001), 2) if self.ended_at else 0,
        }


class ProcessingPipeline(ABC):
    """所有处理阶段的基类"""

    def __init__(self, name: str = "pipeline"):
        self.name = name
        self.metrics = ProcessingMetrics()
        self.metrics.started_at = time.time()

    @abstractmethod
    def process(self, items: List[Union[ProcessedItem, RawDocument]]) -> List[ProcessedItem]:
        pass

    def _to_items(self, items: List[Union[ProcessedItem, RawDocument]]) -> List[ProcessedItem]:
        """统一为 ProcessedItem"""
        result: List[ProcessedItem] = []
        for it in items:
            if isinstance(it, ProcessedItem):
                result.append(it)
            else:
                result.append(self._raw_to_item(it))
        return result

    def _raw_to_item(self, raw: RawDocument) -> ProcessedItem:
        """RawDocument → ProcessedItem"""
        return ProcessedItem(
            source_url=raw.url,
            source_channel=raw.source_channel,
            source_metadata=raw.source_metadata or {},
            raw_doc_hash=raw.content_sha256,
            type=raw.type,
            title=raw.title,
            text=raw.text,
            images=raw.images,
            files=raw.files,
            content_hash=raw.content_sha256,
            size_bytes=raw.content_length,
            source_language=raw.language,
            created_at=raw.crawled_at or _now(),
            status="raw",
        )

    def finish(self):
        self.metrics.ended_at = time.time()

    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics.summary()


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
