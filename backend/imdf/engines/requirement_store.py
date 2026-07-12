"""Depth-7 — ``RequirementStore``: write-through cache (内存 dict + DB row).

设计要点:
1. **in-memory dict 仍然保留** — 满足 ``O(1) get / O(n) list`` 的高频访问。
2. **DB row 同步写入** — 每次 ``create_requirement`` / ``create_task`` /
   ``update_status`` 都同时写 SQLite / Postgres 行。
3. **rehydrate** — ``init_db()`` 之后调用 ``rehydrate()``, 把 DB 现有行
   拉回内存 dict, 完成"重启可恢复"目标。
4. **失败回退** — DB 写失败时 log + 内存 dict 仍保留, 不阻塞上层调用
   (生产部署时上层可加 ``IMDF_REQUIRE_REAL_ENGINES=1`` 阻断)。
5. **legacy 兼容** — ``store.upsert(req: Requirement)`` / ``store.list()``
   接受原 dataclass, 内部 ``to_dict()`` / ``from_dict()`` 转换。
6. **跨 DB** — 走 ``db.postgres.get_jsonb_column()``, PG → JSONB,
   SQLite → JSON, 与既有 12 个 ORM 模型保持一致。

调用::

    store = get_requirement_store()
    store.upsert(req_dataclass)  # 写内存 + DB
    rows = store.list()           # 走内存 dict
    store.rehydrate()             # 启动时调, 拉 DB → 内存
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def _should_persist() -> bool:
    """DB 持久化开关 — 默认开启, ``IMDF_REQUIRE_NO_DB=1`` 时关闭 (纯 in-memory 模式)。"""
    return os.environ.get("IMDF_REQUIRE_NO_DB", "").strip() not in ("1", "true", "yes")


class RequirementStore:
    """RequirementEngine 的 write-through 缓存层。

    三段职责:
    - 内存 dict: ``self._reqs`` / ``self._tasks`` (兼容 legacy)
    - DB row:    ``RequirementRow`` / ``TaskRow`` (持久)
    - rehydrate: 启动时把 DB 拉回内存
    """

    def __init__(self) -> None:
        self._reqs: Dict[str, "object"] = {}  # id → Requirement (dataclass)
        self._tasks: Dict[str, "object"] = {}  # id → Task (dataclass)
        self._lock = threading.Lock()
        self._rehydrated = False

    # ── rehydrate ─────────────────────────────────────────────────────────
    def rehydrate(self, engine=None) -> int:
        """把 DB 现有行拉回内存 dict。返回 rehydrate 数量。

        Args:
            engine: SQLAlchemy Engine (None → use default ``db.engine``)
        """
        if not _should_persist():
            self._rehydrated = True
            return 0

        try:
            from sqlalchemy.orm import Session
            from models import RequirementRow, TaskRow  # type: ignore
        except Exception as e:  # pragma: no cover
            logger.warning(f"rehydrate: import 失败, 跳过 ({e})")
            return 0

        try:
            from db import engine as default_engine
        except Exception:  # pragma: no cover
            default_engine = None
        eng = engine or default_engine
        if eng is None:
            return 0

        n_req = n_task = 0
        try:
            with Session(eng) as s:
                # ── 1. requirements → 内存 dict ──
                try:
                    from engines.requirement_engine import Requirement
                    for row in s.query(RequirementRow).all():
                        d = row.to_dict()
                        d["type"] = d["type"]  # str, 从 DB 读出来就是 str
                        d["status"] = d["status"]
                        d["priority"] = d["priority"]
                        self._reqs[row.id] = Requirement.from_dict(d)
                        n_req += 1
                except Exception as e:  # pragma: no cover
                    logger.warning(f"rehydrate requirements 失败: {e}")

                # ── 2. requirement_tasks → 内存 dict ──
                try:
                    from engines.requirement_engine import Task
                    for row in s.query(TaskRow).all():
                        d = row.to_dict()
                        d["status"] = d["status"]
                        d["priority"] = d["priority"]
                        self._tasks[row.id] = Task.from_dict(d)
                        n_task += 1
                except Exception as e:  # pragma: no cover
                    logger.warning(f"rehydrate tasks 失败: {e}")
        except Exception as e:  # pragma: no cover
            logger.warning(f"rehydrate: DB session 失败 ({e})")
            return 0

        self._rehydrated = True
        logger.info(f"RequirementStore.rehydrate 完成: {n_req} reqs, {n_task} tasks")
        return n_req + n_task

    # ── write-through ─────────────────────────────────────────────────────
    def upsert_requirement(self, req: "object") -> bool:
        """写内存 + DB。返回 DB 写入是否成功。"""
        req_id = getattr(req, "id", None)
        if not req_id:
            return False
        with self._lock:
            self._reqs[req_id] = req

        if not _should_persist():
            return True

        try:
            from sqlalchemy.orm import Session
            from models import RequirementRow
            from db import engine
            d = req.to_dict() if hasattr(req, "to_dict") else {}
            with Session(engine) as s:
                row = s.get(RequirementRow, req_id)
                if row is None:
                    row = RequirementRow(id=req_id)
                row.title = d.get("title", "") or ""
                row.type = d.get("type", "data_annotation") or "data_annotation"
                row.status = d.get("status", "draft") or "draft"
                row.priority = d.get("priority", "P2") or "P2"
                row.created_by = d.get("created_by", "") or ""
                row.description = d.get("description", "") or ""
                row.acceptance_criteria = d.get("acceptance_criteria", "") or ""
                row.tags = list(d.get("tags", []) or [])
                row.created_at = d.get("created_at", "") or ""
                row.updated_at = d.get("updated_at", "") or ""
                row.closed_at = d.get("closed_at", "") or None
                row.project_id = d.get("project_id")
                row.pack_id = d.get("pack_id")
                row.qc_status = d.get("qc_status")
                row.delivery_id = d.get("delivery_id")
                row.due_date = d.get("due_date", "") or ""
                row.owner = d.get("owner", "") or ""
                s.add(row)
                s.commit()
            return True
        except Exception as e:  # pragma: no cover
            logger.warning(f"upsert_requirement DB 写失败 (in-memory 仍保留): {e}")
            return False

    def upsert_task(self, task: "object") -> bool:
        """写内存 + DB。"""
        task_id = getattr(task, "id", None)
        if not task_id:
            return False
        with self._lock:
            self._tasks[task_id] = task

        if not _should_persist():
            return True

        try:
            from sqlalchemy.orm import Session
            from models import TaskRow
            from db import engine
            d = task.to_dict() if hasattr(task, "to_dict") else {}
            with Session(engine) as s:
                row = s.get(TaskRow, task_id)
                if row is None:
                    row = TaskRow(id=task_id)
                row.requirement_id = d.get("requirement_id", "") or ""
                row.title = d.get("title", "") or ""
                row.assignee = d.get("assignee", "") or ""
                row.status = d.get("status", "pending") or "pending"
                row.acceptance_criteria = d.get("acceptance_criteria", "") or ""
                row.estimated_hours = float(d.get("estimated_hours", 0.0) or 0.0)
                row.actual_hours = float(d.get("actual_hours", 0.0) or 0.0)
                row.priority = d.get("priority", "P2") or "P2"
                row.created_at = d.get("created_at", "") or ""
                row.completed_at = d.get("completed_at", "") or ""
                row.notes = d.get("notes", "") or ""
                s.add(row)
                s.commit()
            return True
        except Exception as e:  # pragma: no cover
            logger.warning(f"upsert_task DB 写失败 (in-memory 仍保留): {e}")
            return False

    # ── legacy 兼容: 直接操作 dict ────────────────────────────────────────
    def get_requirement(self, req_id: str):
        return self._reqs.get(req_id)

    def get_task(self, task_id: str):
        return self._tasks.get(task_id)

    def list_requirements(self) -> List["object"]:
        return list(self._reqs.values())

    def list_tasks(self) -> List["object"]:
        return list(self._tasks.values())

    def list_requirements_by_project(self, project_id: str) -> List["object"]:
        return [r for r in self._reqs.values() if getattr(r, "project_id", None) == project_id]

    def list_tasks_by_requirement(self, requirement_id: str) -> List["object"]:
        return [t for t in self._tasks.values() if getattr(t, "requirement_id", None) == requirement_id]

    def list_tasks_by_project(self, project_id: str) -> List["object"]:
        """跨 req join — 需求 → 任务。"""
        req_ids = {r.id for r in self.list_requirements_by_project(project_id)}
        return [t for t in self._tasks.values() if getattr(t, "requirement_id", None) in req_ids]

    def count_requirements_by_project(self, project_id: str) -> int:
        if not project_id:
            return 0
        return sum(1 for r in self._reqs.values() if getattr(r, "project_id", None) == project_id)

    def count_tasks_by_project(self, project_id: str) -> int:
        if not project_id:
            return 0
        req_ids = {r.id for r in self._reqs.values() if getattr(r, "project_id", None) == project_id}
        if not req_ids:
            return 0
        return sum(1 for t in self._tasks.values() if getattr(t, "requirement_id", None) in req_ids)

    def count_done_tasks_by_project(self, project_id: str) -> int:
        if not project_id:
            return 0
        req_ids = {r.id for r in self._reqs.values() if getattr(r, "project_id", None) == project_id}
        if not req_ids:
            return 0
        return sum(
            1 for t in self._tasks.values()
            if getattr(t, "requirement_id", None) in req_ids
            and getattr(t, "status", None) is not None
            and getattr(t.status, "value", t.status) == "approved"
        )

    # ── 维护 ──────────────────────────────────────────────────────────────
    def reset(self) -> None:
        """清空内存 + DB (测试用)。"""
        with self._lock:
            self._reqs.clear()
            self._tasks.clear()

        if not _should_persist():
            return

        try:
            from sqlalchemy.orm import Session
            from models import RequirementRow, TaskRow
            from db import engine
            with Session(engine) as s:
                s.query(TaskRow).delete()
                s.query(RequirementRow).delete()
                s.commit()
        except Exception as e:  # pragma: no cover
            logger.warning(f"reset: DB 清空失败 ({e})")


# ── 模块级单例 ─────────────────────────────────────────────────────────────
_STORE_SINGLETON: Optional[RequirementStore] = None
_STORE_LOCK = threading.Lock()


def get_requirement_store() -> RequirementStore:
    """获取 (或懒创建) 模块级 RequirementStore 单例。"""
    global _STORE_SINGLETON
    with _STORE_LOCK:
        if _STORE_SINGLETON is None:
            _STORE_SINGLETON = RequirementStore()
        return _STORE_SINGLETON


def reset_requirement_store_for_test() -> None:
    """测试钩子 — 重置单例 (注意不重 DB, 调用方按需手动 clear)。"""
    global _STORE_SINGLETON
    with _STORE_LOCK:
        _STORE_SINGLETON = None


__all__ = [
    "RequirementStore",
    "get_requirement_store",
    "reset_requirement_store_for_test",
]
