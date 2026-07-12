"""AuditChainEntry 表 — ``engines/audit_chain.py`` 的 SQLAlchemy 镜像 — P3-1-W1。

历史背景:
- P2-1 之前, ``audit_chain.py`` 自己用 ``sqlite3`` 写 ``data/audit_chain.db`` 文件, 跟主 DB 分离。
- P3-1 升级到 PostgreSQL+pgvector, 把 audit chain 拉进主 DB, 统一备份 / 监控 / 事务。
- **重要**: 旧的 ``audit_chain.py`` 写自己的 SQLite 文件逻辑**保留** (兼容), 新代码用本 ORM
  表 + Celery 后台 task 把 ``audit_chain.db`` 同步到 PG (双写 → 单写 渐进式迁移)。

设计:
- 业务侧 ID: ``ace_<20-dec>`` (对应原来的 autoincrement id, 保留数值)
- 链结构字段: ``prev_hash`` / ``entry_hash`` / ``signature`` (HMAC-SHA256)
- 索引: ``seq`` UNIQUE, ``(method, path)`` 覆盖查询, ``timestamp`` 时间序列
- 跟 ``engines/audit_chain.py`` 的 ``ChainEntry`` dataclass 字段一一对应。

双写策略:
- 阶段 1 (当前): ``audit_chain.append()`` 写老 SQLite; 同时**异步** enqueue
  ``AgentTask(agent_type='audit_sync')`` 把同条 entry 写到本表。
- 阶段 2 (P3+): 关掉老 SQLite, 只走本表 + verify_chain() from PG。

注意:
- 本表是 HMAC 链的"另一份记录", 不是替代。链式校验仍以老 SQLite 的 seq 顺序为准
  (verify_chain 实现跟存储解耦, 可走本表)。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from db.postgres import get_jsonb_column


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuditChainEntry(Base):
    """Audit chain 单条记录 (PostgreSQL mirror of ``engines/audit_chain.ChainEntry``)。"""

    __tablename__ = "audit_chain_entries"

    # 主键: 自增, 但保留 audit_chain 的原始 id (防止 seq 重排导致链校验失败)
    # 跨 DB: PG 用 BIGSERIAL, SQLite 用 INTEGER PRIMARY KEY (ROWID alias 自动自增)
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True, autoincrement=True,
    )
    # 链序号: 全局严格递增, 跟 signature 绑定 → UNIQUE
    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        nullable=False, unique=True, index=True,
    )
    # ISO8601 时间戳 (UTC)
    timestamp: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    # 真实发生时间 (PG 可用 TIMESTAMPTZ, SQLite 降级 DATETIME; 用字符串省心)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)

    # HTTP / API 上下文
    method: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    user: Mapped[str] = mapped_column(String(120), default="", index=True)
    body_hash: Mapped[str] = mapped_column(String(80), default="")
    status_code: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        default=0, nullable=False,
    )
    # actor 兼容 P2 audit_log 的 actor 字段 (合并写入 user)
    actor: Mapped[Optional[str]] = mapped_column(String(120), default="")

    # 链式哈希
    prev_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(80), nullable=False)
    # HMAC-SHA256 signature (64 hex chars = 256 bits)
    signature: Mapped[str] = mapped_column(String(80), nullable=False)

    # 元数据 (请求 IP / 客户端 / trace_id)
    # P21 P2 P1: was `Text` (inconsistent with p13_c1_p99_db GIN jsonb_path_ops index).
    # Now uses `get_jsonb_column()` — PG → JSONB, SQLite → JSON — so the GIN index
    # in p13_c1_p99_db.py:97-100 (``ix_audit_chain_extra_gin``) becomes a real,
    # queryable index instead of a dead-code one. The default is a dict literal
    # (``{}``) to match the new JSON shape; legacy rows that were stored as
    # ``''`` (empty text) still read back as an empty string under SQLAlchemy's
    # ``JSON`` type, but new code should always write a dict.
    extra: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        get_jsonb_column(), nullable=True, default=dict
    )

    __table_args__ = (
        Index("ix_audit_chain_method_path", "method", "path"),
        Index("ix_audit_chain_user_time", "user", "timestamp"),
    )

    def to_dict(self) -> dict:
        return {
            "id": int(self.id),
            "seq": int(self.seq),
            "timestamp": self.timestamp,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
            "method": self.method,
            "path": self.path,
            "user": self.user or "",
            "body_hash": self.body_hash or "",
            "status_code": int(self.status_code or 0),
            "actor": self.actor or "",
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
            "signature": self.signature,
            "extra": self.extra or "",
        }


__all__ = ["AuditChainEntry"]
