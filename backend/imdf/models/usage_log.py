"""UsageLog 表 — P2-3-W2, 拆出来到独立文件 — P3-1-W1 整合。

历史:
- P2-3-W2 直接写在 ``models/__init__.py`` 里 (单文件 320 行, 太长)
- P3-1 拆出到本文件, models/__init__.py 通过 ``from models.usage_log import UsageLog`` 重新导出
  (跟旧 import 路径 ``from models import UsageLog`` 兼容)

字段含义 / 索引策略 / 计费公式见 docstring, 跟 P2-3-W2 保持一致。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from db.postgres import get_jsonb_column


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class UsageLog(Base):
    """AI provider 调用日志 + 计费。

    - 业务侧 ID: ``ul_<12-hex>``
    - 必填字段: ``user_id`` / ``provider_id`` / ``protocol`` / ``kind`` / ``status``
    - 可选字段: ``org_id`` / ``model`` / tokens / cost / latency / error_*
    - 复合索引 ``(user_id, created_at)`` 覆盖"用户本月消耗"查询。
    - 跨 DB: PG 上 extra 是 JSONB, SQLite 走 JSON (走 get_jsonb_column 自动适配)。
    """

    __tablename__ = "usage_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    org_id: Mapped[Optional[str]] = mapped_column(String(64), default="")
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    protocol: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(240), default="")
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # chat/image/video/embedding
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")  # ok/error
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(String(60), default="")
    error_message: Mapped[Optional[str]] = mapped_column(Text, default="")
    # 跨 DB JSON: PG → JSONB, SQLite → JSON
    extra: Mapped[Dict[str, Any]] = mapped_column(get_jsonb_column(), default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)

    __table_args__ = (
        Index("ix_usage_logs_user_created", "user_id", "created_at"),
        Index("ix_usage_logs_org_created", "org_id", "created_at"),
        Index("ix_usage_logs_provider", "provider_id"),
        Index("ix_usage_logs_status", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "org_id": self.org_id or "",
            "provider_id": self.provider_id,
            "protocol": self.protocol,
            "model": self.model or "",
            "kind": self.kind,
            "status": self.status,
            "prompt_tokens": int(self.prompt_tokens or 0),
            "completion_tokens": int(self.completion_tokens or 0),
            "total_tokens": int(self.total_tokens or 0),
            "cost_usd": float(self.cost_usd or 0.0),
            "latency_ms": int(self.latency_ms or 0),
            "error_code": self.error_code or "",
            "error_message": self.error_message or "",
            "extra": self.extra or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


__all__ = ["UsageLog"]
