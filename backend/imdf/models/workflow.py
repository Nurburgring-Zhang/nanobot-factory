"""Workflow 表 — 编排 DAG (有向无环图) — P3-1-W1。

设计:
- 业务侧 ID: ``wf_<12-hex>``
- ``dag_json``: PG 上是 ``JSONB``, SQLite 是 ``JSON`` — 存 DAG 节点 + 边
- ``status``: draft / active / paused / archived
- ``owner`` / ``project_id`` 软引用
- ``steps_count`` / ``last_run_at`` 冗余字段, 避免每次都解析 dag_json

DAG JSON 格式示例::

    {
      "nodes": [
        {"id": "step1", "type": "ingest", "config": {...}},
        {"id": "step2", "type": "embed", "config": {...}}
      ],
      "edges": [
        {"from": "step1", "to": "step2"}
      ]
    }

调用方: ``engines/agent.py`` / ``workflows/`` 目录
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
    DateTime,
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


class Workflow(Base):
    """Workflow 表 — DAG 编排定义 + 状态。"""

    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), default="", index=True)

    # 关键: PG → JSONB, SQLite → JSON
    dag_json: Mapped[Dict[str, Any]] = mapped_column(get_jsonb_column(), default=dict, nullable=False)
    # 步骤数 (冗余, 避免每次 count)
    steps_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 最近一次执行时间
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # tags (用于搜索 / 分类)
    tags: Mapped[Dict[str, Any]] = mapped_column(get_jsonb_column(), default=list)
    # 配置 (调度周期、并发数、retry 策略等)
    config: Mapped[Dict[str, Any]] = mapped_column(get_jsonb_column(), default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now, nullable=False)

    def to_dict(self) -> dict:
        dag = self.dag_json or {}
        nodes = dag.get("nodes", []) if isinstance(dag, dict) else []
        edges = dag.get("edges", []) if isinstance(dag, dict) else []
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "status": self.status,
            "owner": self.owner,
            "project_id": self.project_id or "",
            "dag": dag,
            "node_count": len(nodes) if isinstance(nodes, list) else 0,
            "edge_count": len(edges) if isinstance(edges, list) else 0,
            "steps_count": int(self.steps_count or 0),
            "tags": self.tags or [],
            "config": self.config or {},
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


__all__ = ["Workflow"]
