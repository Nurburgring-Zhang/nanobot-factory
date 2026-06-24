"""Models package — P3-1-W1: 5 旧模型 + 5 新模型 = 10 个 ORM 表。

5 旧模型 (P2-1-W1 + P2-3-W2):
- User            — 用户 (admin/annotator/reviewer/viewer + skills)
- Project         — 项目 (含 owner + members 列表)
- Task            — 任务 (pending/running/done/error)
- Asset           — 资产 (image/video/audio/text/model3d)
- Dataset         — 数据集 (draft/active/archived)
- UsageLog        — AI provider 用量 + 计费 (P2-3-W2, 拆出到 usage_log.py)

5 新模型 (P3-1-W1):
- Embedding       — 向量化资产 / query, 走 pgvector (semantic search 锚点)
- Workflow        — DAG 编排定义 + 状态
- AgentTask       — AI Agent 异步任务 (LLM/tool/workflow_run/semantic_search)
- AuditChainEntry — audit_chain 链式条目的 PG mirror (HMAC-SHA256 签名链)

跨 DB 设计:
- 所有 ``JSON`` 字段走 ``db.postgres.get_jsonb_column()`` — PG → JSONB, SQLite → JSON
- Embedding 的 ``vector`` 走 ``db.postgres.get_vector_column(1024)`` — PG → pgvector Vector, SQLite → JSON

兼容性:
- ``from models import User, UsageLog`` 仍然有效 (老代码不破)
- ``from models.usage_log import UsageLog`` 也有效 (新拆分)
- ``from models.embedding import Embedding`` 走新文件
- 启动时 ``register_all()`` 确保所有 model 被 import → ``Base.metadata`` 注册完整

调用方::

    from db import Base, get_db, engine
    from models import User, Project, Task, Asset, Dataset, UsageLog
    from models import Embedding, Workflow, AgentTask, AuditChainEntry
    from fastapi import Depends
    from sqlalchemy.orm import Session

    @router.get("/embeddings/search")
    def search(q: str, db: Session = Depends(get_db)):
        # PG: 用 pgvector 的 <-> / <=> 算 cosine 距离
        # SQLite: 走纯 Python numpy (降级)
        ...
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db import Base
from db.postgres import get_jsonb_column


def _now() -> datetime:
    """UTC now (naive — SQLite 默认无时区)。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ════════════════════════════════════════════════════════════════════════════
# 5 旧模型 (User/Project/Task/Asset/Dataset) — P2-1-W1 原生
# ════════════════════════════════════════════════════════════════════════════
class User(Base):
    """用户表 — 业务侧 ID 为 ``user_<8-hex>``。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="viewer", nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="offline", nullable=False)
    skills: Mapped[List[str]] = mapped_column(JSON, default=list)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    __table_args__ = (
        Index("ix_users_role", "role"),
        Index("ix_users_status", "status"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "email": self.email or "",
            "status": self.status,
            "skills": list(self.skills or []),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Project(Base):
    """项目表 — 业务侧 ID 为 ``proj_<8-hex>``。"""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    owner: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)
    members: Mapped[List[str]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    __table_args__ = (
        Index("ix_projects_status", "status"),
        Index("ix_projects_owner", "owner"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "status": self.status,
            "owner": self.owner,
            "members": list(self.members or []),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Task(Base):
    """任务表 — 业务侧 ID 为 ``task_<8-hex>``。"""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="generic", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    owner: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_owner", "owner"),
        Index("ix_tasks_type", "type"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "status": self.status,
            "owner": self.owner,
            "payload": self.payload or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Asset(Base):
    """资产表 — 业务侧 ID 为 ``asset_<12-hex>``。"""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(20), default="image", nullable=False)
    size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    path: Mapped[Optional[str]] = mapped_column(String(1000), default="")
    owner: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    __table_args__ = (
        Index("ix_assets_type", "type"),
        Index("ix_assets_owner", "owner"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "size": self.size,
            "tags": list(self.tags or []),
            "path": self.path or "",
            "owner": self.owner,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Dataset(Base):
    """数据集表 — 业务侧 ID 为 ``ds_<8-hex>``。"""

    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(50), default="1.0.0", nullable=False)
    files_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    __table_args__ = (
        Index("ix_datasets_status", "status"),
        Index("ix_datasets_created_by", "created_by"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "files_count": self.files_count,
            "status": self.status,
            "description": self.description or "",
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


# ════════════════════════════════════════════════════════════════════════════
# UsageLog — 拆出到 usage_log.py, 这里 re-export 保持兼容
# ════════════════════════════════════════════════════════════════════════════
from models.usage_log import UsageLog  # noqa: E402,F401


# ════════════════════════════════════════════════════════════════════════════
# 5 新模型 (P3-1-W1) — 走独立文件, 这里 import 触发 Base.metadata 注册
# ════════════════════════════════════════════════════════════════════════════
from models.embedding import Embedding  # noqa: E402,F401
from models.workflow import Workflow  # noqa: E402,F401
from models.agent import AgentTask  # noqa: E402,F401
from models.audit_chain_entry import AuditChainEntry  # noqa: E402,F401


# ════════════════════════════════════════════════════════════════════════════
# register_all — 触发所有 model import
# ════════════════════════════════════════════════════════════════════════════
def register_all() -> None:
    """强制 import 所有 model, 让 ``Base.metadata`` 注册所有表。

    在 ``init_db()`` 和 ``alembic/env.py`` 里调用一次即可。
    本函数体为空 — 真正起作用的是模块被 import 这个事实。
    """
    return None


__all__ = [
    # 5 旧模型
    "User",
    "Project",
    "Task",
    "Asset",
    "Dataset",
    "UsageLog",
    # 5 新模型 (P3-1-W1)
    "Embedding",
    "Workflow",
    "AgentTask",
    "AuditChainEntry",
    # 注册
    "register_all",
]
