"""Embedding 表 — 向量化资产 / 用户 query, 走 pgvector 做语义搜索 — P3-1-W1。

设计:
- 业务侧 ID: ``emb_<16-hex>`` (UUID4 前 16 位)
- ``entity_type`` / ``entity_id`` 通用指针: 指向 ``asset`` / ``task`` / ``dataset`` / ``user_query``
  等多种实体, 不强制 FK (允许跨业务实体, 软引用)
- ``vector`` 字段: PG 上是 ``vector(1024)``, SQLite 降级为 JSON 数组
- ``model`` 字段: 记录 embedding 用的模型 (bge-large-zh / text-embedding-3-small 等)
- ``metadata`` 字段: PG 用 ``JSONB``, SQLite 用 ``JSON`` — 存 chunk 文本、来源、tag 等
- 索引: ``(entity_type, entity_id)`` 复合索引, 加速"找某实体的所有 embedding"

跨 DB 兼容:
- ``get_vector_column(1024)`` 在 PG 上用 pgvector, 其他用 JSON (开发态)
- ``get_jsonb_column()``     在 PG 上用 JSONB, 其他用 JSON

用法::

    from db import SessionLocal
    from models.embedding import Embedding
    import numpy as np

    with SessionLocal() as db:
        emb = Embedding(
            id=f"emb_{uuid.uuid4().hex[:16]}",
            entity_type="asset",
            entity_id="asset_abc123",
            vector=[0.1, 0.2, ...] + [0.0] * (1024 - 2),  # 1024 dim
            model="bge-large-zh",
            metadata={"chunk_text": "...", "source": "uploaded"},
        )
        db.add(emb)
        db.commit()
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from db.postgres import get_jsonb_column, get_vector_column


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# 向量维度 — 跟 model 字段绑定
# 1024 = bge-large-zh-v1.5 / bge-m3 默认输出维度
# 1536 = OpenAI text-embedding-3-small
# 3072 = OpenAI text-embedding-3-large
DEFAULT_VECTOR_DIM = 1024


class Embedding(Base):
    """Embedding 表 — 通用向量存储 + 语义搜索锚点。

    PG:  ``vector(1024)`` (pgvector) + JSONB metadata
    SQLite: JSON 数组 + JSON metadata (降级, 失去 cosine 索引)
    """

    __tablename__ = "embeddings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 关键字段: PG → vector(1024), SQLite → JSON
    # 注意: SA mapped_column 接受 Type 对象, 不是实例化后的列 — get_vector_column 返回的就是类型
    vector: Mapped[Any] = mapped_column(get_vector_column(DEFAULT_VECTOR_DIM), nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="bge-large-zh", nullable=False)
    # metadata 是 SQLAlchemy reserved attribute, 用 meta 字段名避坑
    meta: Mapped[Dict[str, Any]] = mapped_column(get_jsonb_column(), default=dict)
    chunk_text: Mapped[Optional[str]] = mapped_column(Text, default="")
    extra: Mapped[Dict[str, Any]] = mapped_column(get_jsonb_column(), default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    __table_args__ = (
        Index("ix_embeddings_entity", "entity_type", "entity_id"),
        Index("ix_embeddings_model", "model"),
        Index("ix_embeddings_created_at", "created_at"),
    )

    def to_dict(self) -> dict:
        """API 响应 — 不返回 vector 原始数组(太大), 改返长度 + sample。"""
        vec = self.vector
        if vec is None:
            vec_repr = None
        elif isinstance(vec, (list, tuple)):
            vec_repr = {"dim": len(vec), "head": list(vec[:4])}
        else:
            # PG Vector 对象的 str repr 是 '[0.1,0.2,...]'
            try:
                parsed = [float(x) for x in str(vec).strip("[]").split(",")]
                vec_repr = {"dim": len(parsed), "head": parsed[:4]}
            except Exception:
                vec_repr = {"raw": str(vec)[:80]}
        return {
            "id": self.id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "model": self.model,
            "vector_summary": vec_repr,
            "metadata": self.meta or {},
            "chunk_text": (self.chunk_text or "")[:500],
            "extra": self.extra or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


__all__ = ["Embedding", "DEFAULT_VECTOR_DIM"]
