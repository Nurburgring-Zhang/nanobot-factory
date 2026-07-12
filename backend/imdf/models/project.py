"""P5-R1-T1 ProjectCenter models — Project 扩展 + ProjectMember 关联表 + ProjectTimelineEvent 时间线。

设计要点:
- 复用 ``imdf.db.Base`` (PG/SQLite 双模) — 所有字段跨方言兼容
- Project 在原 ``models/__init__.py:Project`` 基础上扩展 4 字段 (priority / tags / start_date / due_date)
  全部 ``default=""`` / nullable, 不破坏 legacy p1_c_w1 数据
- ProjectMember: 多对多关联表, (project_id, user_id) 唯一, 含 role + joined_at
- ProjectTimelineEvent: 不可变 append-only 事件流, project_id + ts 索引
- ``from models.project import Project, ProjectMember, ProjectTimelineEvent``
  + 在 ``models/__init__.py`` 注册后即可被 ``Base.metadata`` 跟踪, Alembic 也能 reflect

调用方::
    from models import Project, ProjectMember, ProjectTimelineEvent
    from db import SessionLocal

    db = SessionLocal()
    proj = db.query(Project).filter(Project.id == pid).first()
    members = db.query(ProjectMember).filter(ProjectMember.project_id == pid).all()
    timeline = db.query(ProjectTimelineEvent).filter(ProjectTimelineEvent.project_id == pid)
        .order_by(ProjectTimelineEvent.ts.desc()).all()
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from db.postgres import get_jsonb_column


def _now() -> datetime:
    """UTC now (naive — SQLite 默认无时区)。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ─────────────────────────────────────────────────────────────────────────────
# Project — 扩展版 (继承原有 Project 表, 新增 priority/tags/start_date/due_date)
# ─────────────────────────────────────────────────────────────────────────────
# 注意: 此处**不**新建 __tablename__ = "projects", 而是 import 原 models.Project 后
# 直接扩展其字段。但 SQLAlchemy declarative 不允许多次 __tablename__, 所以我们
# 这里只新增 ProjectMember + ProjectTimelineEvent 两张**新**表; Project 的新字段
# 在 ``models/__init__.py:Project`` 里直接加列 (见该文件)。


# ─────────────────────────────────────────────────────────────────────────────
# ProjectMember — 项目成员关联表
# ─────────────────────────────────────────────────────────────────────────────
class ProjectMember(Base):
    """项目成员关联表 (多对多 project ↔ user)。

    - 复合唯一约束: ``(project_id, user_id)`` 防止重复添加
    - role: owner / admin / member / viewer (默认 member)
    - joined_at: ISO 时间戳
    - 与 ``Project.members`` (JSON) 是冗余关系 — JSON 用于快速读, 此表用于精确查询 / 角色管理
    """

    __tablename__ = "project_members"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        Index("ix_project_members_project", "project_id"),
        Index("ix_project_members_user", "user_id"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "role": self.role,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# ProjectTimelineEvent — 项目事件流 (append-only)
# ─────────────────────────────────────────────────────────────────────────────
class ProjectTimelineEvent(Base):
    """项目时间线事件表 (append-only, 用于审计 + UI 时间线)。

    event_type:
      - created          项目创建
      - updated          任意字段更新
      - status_changed   状态机转换
      - member_added     添加成员
      - member_removed   移除成员

    payload: JSON 快照 (变更前/后, 由调用方写入)
    """

    __tablename__ = "project_timeline_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(get_jsonb_column(), default=dict, nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, default="")

    __table_args__ = (
        Index("ix_project_timeline_project_ts", "project_id", "ts"),
        Index("ix_project_timeline_event_type", "event_type"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "ts": self.ts.isoformat() if self.ts else None,
            "payload": self.payload or {},
            "message": self.message or "",
        }


__all__ = ["ProjectMember", "ProjectTimelineEvent"]