"""AgentTask 表 — AI Agent 异步任务调度 (LLM 推理 / 决策 / 工具调用) — P3-1-W1。

设计:
- 业务侧 ID: ``at_<16-hex>``
- ``agent_type``: 类型化分桶 — ``llm_chat`` / ``llm_embed`` / ``decision`` /
  ``tool_call`` / ``workflow_run`` / ``semantic_search``
- ``payload``: 输入 — prompt / tool spec / 上下文
- ``result``: 输出 — LLM response / tool result (异步填)
- ``status``: queued / running / done / error / timeout / cancelled
- ``priority``: 0-9, 数字越小优先级越高 (走 Celery 队列)
- ``parent_id``: 任务嵌套 (父 → 子), 用于 workflow 拆分
- ``trace_id``: 关联 audit_chain + 用量追踪 + 日志

调度链::

    API request
      → AgentTask(id, status=queued)
        → Celery worker (consumer)
          → status=running, started_at=now
            → LLM call / tool exec
              → status=done, finished_at=now, result={...}
                → 触发下游 AgentTask (parent_id=this.id)

调用方: ``engines/agent.py`` / ``engines/task_queue.py``
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import (
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


class AgentTask(Base):
    """Agent 异步任务表 — LLM / tool / workflow 调度的统一入口。"""

    __tablename__ = "agent_tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False, index=True)

    # 业务上下文
    user_id: Mapped[Optional[str]] = mapped_column(String(64), default="", index=True)
    org_id: Mapped[Optional[str]] = mapped_column(String(64), default="", index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), default="", index=True)
    workflow_id: Mapped[Optional[str]] = mapped_column(String(64), default="", index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(String(64), default="", index=True)

    # 输入 / 输出 — PG → JSONB, SQLite → JSON
    payload: Mapped[Dict[str, Any]] = mapped_column(get_jsonb_column(), default=dict, nullable=False)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(get_jsonb_column(), nullable=True)
    error: Mapped[Optional[Dict[str, Any]]] = mapped_column(get_jsonb_column(), nullable=True)

    # 关联 / 追踪
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), default="", index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(80), default="", index=True)
    # Celery task_id (跟 P2-1-W2 celery_app 配合)
    celery_task_id: Mapped[Optional[str]] = mapped_column(String(80), default="", index=True)

    # 调度 / 重试
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # 元数据: 跑哪个模型、用哪个 provider、cost 预估等
    meta: Mapped[Dict[str, Any]] = mapped_column(get_jsonb_column(), default=dict)

    # 时间戳
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 错误堆栈 (Text 限制长度)
    error_message: Mapped[Optional[str]] = mapped_column(Text, default="")

    __table_args__ = (
        Index("ix_agent_tasks_status_priority", "status", "priority"),
        Index("ix_agent_tasks_user_queued", "user_id", "queued_at"),
        Index("ix_agent_tasks_workflow", "workflow_id"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_type": self.agent_type,
            "status": self.status,
            "priority": int(self.priority or 0),
            "user_id": self.user_id or "",
            "org_id": self.org_id or "",
            "project_id": self.project_id or "",
            "workflow_id": self.workflow_id or "",
            "parent_id": self.parent_id or "",
            "payload": self.payload or {},
            "result": self.result,
            "error": self.error,
            "trace_id": self.trace_id or "",
            "idempotency_key": self.idempotency_key or "",
            "celery_task_id": self.celery_task_id or "",
            "retry_count": int(self.retry_count or 0),
            "max_retries": int(self.max_retries or 0),
            "meta": self.meta or {},
            "queued_at": self.queued_at.isoformat() if self.queued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "error_message": self.error_message or "",
        }


__all__ = ["AgentTask"]
