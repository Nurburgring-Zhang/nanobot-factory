"""Depth-7 — ``Requirement`` + ``Task`` ORM models.

背景: P5-R1-T2 / P5-R2-T2 之前, ``RequirementEngine`` 用纯 in-memory dict
(``self.requirements: Dict[str, Requirement]``),跨进程 / 跨重启会全丢,
所有数据流项目统计 (project stats) 实际只对单进程单实例有意义.

修复: 把 in-memory dataclass 升级成 SQLAlchemy ORM 行, ``RequirementEngine``
走 write-through cache (内存 dict + DB row),``init_db()`` 启动时
``load_from_db()`` 把已有 row 拉回内存 dict (rehydrate),确保:

- 跨进程持久 — 重启后 ``get_requirement()`` / ``count_*`` 仍然正确
- 跨 instance 一致 — 多个 worker 共享同一份 SQLite / Postgres
- 跨 DB 兼容 — ``db.postgres.get_jsonb_column()`` 在 PG → JSONB, SQLite → JSON
- legacy 兼容 — ``RequirementEngine`` 公共 API 完全不变

调用方::

    from models.requirement import RequirementRow, TaskRow
    from db import Base, init_db
    init_db()  # 自动 create_all
    s.add(RequirementRow(id=..., title=..., ...))
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


def _now() -> datetime:
    """UTC now (naive — SQLite 默认无时区)。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RequirementRow(Base):
    """需求表 — 业务侧 ID 为 ``req_<8-hex>``。

    与 ``engines.requirement_engine.Requirement`` dataclass 一一对应,
    但走 SQLAlchemy ORM, 跨进程持久。
    """

    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    type: Mapped[str] = mapped_column(String(50), default="data_annotation", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    priority: Mapped[str] = mapped_column(String(8), default="P2", nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(Text, default="")
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    closed_at: Mapped[Optional[str]] = mapped_column(String(64), default="")

    # ── 跨子系统关联字段 (P5-R1-T2) ────────────────────────────────────────
    project_id: Mapped[Optional[str]] = mapped_column(String(64), default=None, index=True)
    pack_id: Mapped[Optional[str]] = mapped_column(String(64), default=None, index=True)
    qc_status: Mapped[Optional[str]] = mapped_column(String(20), default=None)
    delivery_id: Mapped[Optional[str]] = mapped_column(String(64), default=None, index=True)
    due_date: Mapped[Optional[str]] = mapped_column(String(32), default="")
    owner: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)

    __table_args__ = (
        Index("ix_requirements_status", "status"),
        Index("ix_requirements_priority", "priority"),
        Index("ix_requirements_type", "type"),
        Index("ix_requirements_created_by", "created_by"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "status": self.status,
            "priority": self.priority,
            "created_by": self.created_by,
            "description": self.description or "",
            "acceptance_criteria": self.acceptance_criteria or "",
            "tags": list(self.tags or []),
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
            "closed_at": self.closed_at or "",
            "project_id": self.project_id,
            "pack_id": self.pack_id,
            "qc_status": self.qc_status,
            "delivery_id": self.delivery_id,
            "due_date": self.due_date or "",
            "owner": self.owner,
        }


class TaskRow(Base):
    """任务表 — 业务侧 ID 为 ``task_<8-hex>`` (与 models.Task 业务对齐)。

    注意: 这是 ``RequirementEngine`` 内部的 ``Task`` dataclass 对应表,
    与 ``models.Task`` (通用任务) 是两套表, 避免在多引擎间争夺同一个表。
    业务字段一致, 表名不同, 跨子引擎统计不互相污染。
    """

    __tablename__ = "requirement_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    requirement_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    assignee: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(Text, default="")
    estimated_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_hours: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    priority: Mapped[str] = mapped_column(String(8), default="P2", nullable=False)
    created_at: Mapped[Optional[str]] = mapped_column(String(64), default="")
    completed_at: Mapped[Optional[str]] = mapped_column(String(64), default="")
    notes: Mapped[Optional[str]] = mapped_column(Text, default="")

    __table_args__ = (
        Index("ix_requirement_tasks_status", "status"),
        Index("ix_requirement_tasks_priority", "priority"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "requirement_id": self.requirement_id,
            "title": self.title,
            "assignee": self.assignee,
            "status": self.status,
            "acceptance_criteria": self.acceptance_criteria or "",
            "estimated_hours": self.estimated_hours,
            "actual_hours": self.actual_hours,
            "priority": self.priority,
            "created_at": self.created_at or "",
            "completed_at": self.completed_at or "",
            "notes": self.notes or "",
        }


__all__ = ["RequirementRow", "TaskRow"]
