"""P3-3-W1: In-memory + SQLite task store for AgentTask.

Stores the lifecycle of every ``agent_task`` submitted to the dispatch
framework.  Uses SQLite as the source of truth (best-effort, append-only)
plus an in-process dict for hot look-ups.

This module does NOT own the executor; it only persists the task record and
its status transitions.  The :mod:`scheduler` writes here, and the
:mod:`executor` reads + mutates.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from .agents import AgentType, ExecutionMode

logger = logging.getLogger(__name__)


# ── Task status enum ────────────────────────────────────────────────────────
class TaskStatus(str, Enum):
    """Lifecycle states for an AgentTask.

    Allowed transitions:
        PENDING      → RUNNING / CANCELLED
        RUNNING      → SUCCEEDED / FAILED / CANCELLED
        FAILED       → PENDING (retry) / CANCELLED
        SUCCEEDED    → (terminal)
        CANCELLED    → (terminal)
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Task record ─────────────────────────────────────────────────────────────
@dataclass
class AgentTask:
    """A single agent task record."""

    task_id: str
    agent_type: str
    mode: str
    payload: Dict[str, Any]
    status: str = TaskStatus.PENDING.value
    priority: int = 5
    max_retries: int = 2
    retry_count: int = 0
    timeout_seconds: int = 600
    submitted_by: str = "anonymous"
    created_at: str = field(default_factory=lambda: _now_iso())
    updated_at: str = field(default_factory=lambda: _now_iso())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    parent_task_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def touch(self) -> None:
        self.updated_at = _now_iso()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Store ────────────────────────────────────────────────────────────────────
class AgentTaskStore:
    """Thread-safe in-process store with optional SQLite persistence.

    Designed for both TestClient hermetic tests (no DB) and live uvicorn
    (SQLite in :data:`IMDF_DATA_DIR`).
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._tasks: Dict[str, AgentTask] = {}
        self._db_path = db_path
        if db_path:
            self._init_db(db_path)

    # ── DB helpers ──────────────────────────────────────────────────────────
    def _init_db(self, path: str) -> None:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:  # noqa: BLE001
            pass
        with sqlite3.connect(path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    task_id TEXT PRIMARY KEY,
                    agent_type TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 5,
                    max_retries INTEGER NOT NULL DEFAULT 2,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    timeout_seconds INTEGER NOT NULL DEFAULT 600,
                    submitted_by TEXT NOT NULL DEFAULT 'anonymous',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    result TEXT,
                    error TEXT,
                    parent_task_id TEXT,
                    metadata TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_agent_tasks_status ON agent_tasks(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_agent_tasks_type ON agent_tasks(agent_type)"
            )
            conn.commit()

    def _persist(self, task: AgentTask) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO agent_tasks (
                        task_id, agent_type, mode, payload, status, priority,
                        max_retries, retry_count, timeout_seconds, submitted_by,
                        created_at, updated_at, started_at, finished_at,
                        result, error, parent_task_id, metadata
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        task.task_id,
                        task.agent_type,
                        task.mode,
                        json.dumps(task.payload, ensure_ascii=False),
                        task.status,
                        task.priority,
                        task.max_retries,
                        task.retry_count,
                        task.timeout_seconds,
                        task.submitted_by,
                        task.created_at,
                        task.updated_at,
                        task.started_at,
                        task.finished_at,
                        json.dumps(task.result, ensure_ascii=False) if task.result else None,
                        task.error,
                        task.parent_task_id,
                        json.dumps(task.metadata, ensure_ascii=False),
                    ),
                )
                conn.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("persist task %s failed: %s", task.task_id, e)

    # ── CRUD ────────────────────────────────────────────────────────────────
    def create(
        self,
        agent_type: str | AgentType,
        payload: Dict[str, Any],
        *,
        mode: str | ExecutionMode = ExecutionMode.FULL_AUTO,
        priority: int = 5,
        max_retries: int = 2,
        timeout_seconds: int = 600,
        submitted_by: str = "anonymous",
        parent_task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentTask:
        at = agent_type.value if isinstance(agent_type, AgentType) else str(agent_type)
        m = mode.value if isinstance(mode, ExecutionMode) else str(mode)
        task = AgentTask(
            task_id=f"agt-{uuid.uuid4().hex[:12]}",
            agent_type=at,
            mode=m,
            payload=dict(payload or {}),
            priority=int(priority),
            max_retries=int(max_retries),
            timeout_seconds=int(timeout_seconds),
            submitted_by=submitted_by,
            parent_task_id=parent_task_id,
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._tasks[task.task_id] = task
            self._persist(task)
        logger.info("task created %s agent=%s mode=%s", task.task_id, task.agent_type, task.mode)
        return task

    def get(self, task_id: str) -> Optional[AgentTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def list(
        self,
        *,
        status: Optional[str] = None,
        agent_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[AgentTask]:
        with self._lock:
            items = list(self._tasks.values())
        if status:
            items = [t for t in items if t.status == status]
        if agent_type:
            items = [t for t in items if t.agent_type == agent_type]
        # Newest first
        items.sort(key=lambda t: t.created_at, reverse=True)
        return items[: max(0, limit)]

    def stats(self) -> Dict[str, int]:
        with self._lock:
            items = list(self._tasks.values())
        out: Dict[str, int] = {s.value: 0 for s in TaskStatus}
        for t in items:
            out[t.status] = out.get(t.status, 0) + 1
        out["total"] = len(items)
        return out

    def update(self, task: AgentTask) -> None:
        task.touch()
        with self._lock:
            self._tasks[task.task_id] = task
            self._persist(task)

    def transition(self, task_id: str, new_status: str, **fields: Any) -> Optional[AgentTask]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            task.status = new_status
            if "result" in fields:
                task.result = fields["result"]
            if "error" in fields:
                task.error = fields["error"]
            if "retry_count" in fields:
                task.retry_count = fields["retry_count"]
            if new_status == TaskStatus.RUNNING.value and not task.started_at:
                task.started_at = _now_iso()
            if new_status in (
                TaskStatus.SUCCEEDED.value,
                TaskStatus.FAILED.value,
                TaskStatus.CANCELLED.value,
            ):
                task.finished_at = _now_iso()
            task.touch()
            self._persist(task)
        return task

    def reset_for_test(self) -> None:
        """Clear in-memory state (used by TestClient fixtures)."""
        with self._lock:
            self._tasks.clear()


# ── Module-level singleton ───────────────────────────────────────────────────
_store_singleton: Optional[AgentTaskStore] = None
_store_lock = threading.Lock()


def get_store(db_path: Optional[str] = None) -> AgentTaskStore:
    """Lazy-init singleton (so TestClient doesn't need a real DB)."""
    global _store_singleton
    with _store_lock:
        if _store_singleton is None:
            if db_path is None:
                # Try the env var, then the default imdf data dir
                env = os.environ.get("IMDF_DATA_DIR")
                if env:
                    db_path = os.path.join(env, "agent_tasks.db")
            _store_singleton = AgentTaskStore(db_path=db_path)
        return _store_singleton


def reset_store_singleton() -> None:
    """Force the singleton to be re-created on next :func:`get_store` call."""
    global _store_singleton
    with _store_lock:
        _store_singleton = None


__all__ = [
    "AgentTask",
    "TaskStatus",
    "AgentTaskStore",
    "get_store",
    "reset_store_singleton",
]
