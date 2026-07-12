"""
数据包/任务包引擎 — Pack Engine (P5-R1-T3)
==========================================

设计目标
--------
1. Pack 是 数据/任务 的"打包单元", 是 requirement → asset 的中间层
2. PackStatus 状态机: created → ready → in_annotation → annotated → reviewed → qc_passed → delivered
3. PackEngine 提供 pack 生命周期管理 (create / list / update / transition / route)
4. route_pack(): 根据 has_data 智能路由
   - has_data=True  → annotation 标注流
   - has_data=False → collection 采集流 (空包 → 触发采集)

持久化
------
- SQLite (imdf.db) + Alembic 迁移
- 主表: packs / pack_assets / pack_route_history
- 与 data_collection_engine.py 的 JSON 持久化解耦 (Pack 全部走 SQLite)

状态机
------
  ┌───────┐
  │ created│ (新创建)
  └───┬───┘
      ↓
  ┌───────┐
  │ ready │ (资产就绪)
  └───┬───┘
      ↓
  ┌──────────────┐
  │ in_annotation│ (标注中)
  └───┬──────────┘
      ↓
  ┌──────────┐
  │ annotated│ (标注完成)
  └───┬──────┘
      ↓
  ┌─────────┐
  │ reviewed│ (审核)
  └───┬─────┘
      ↓
  ┌──────────┐
  │qc_passed │ (质检通过)
  └───┬──────┘
      ↓
  ┌──────────┐
  │ delivered│ (交付)
  └──────────┘
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 1. 常量 / 枚举
# ============================================================

class PackType(str, Enum):
    DATA_PACK = "data_pack"
    TASK_PACK = "task_pack"


class PackSource(str, Enum):
    UPLOAD = "upload"
    COLLECTION = "collection"
    TRANSFER = "transfer"
    GENERATION = "generation"


class PackStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    IN_ANNOTATION = "in_annotation"
    ANNOTATED = "annotated"
    REVIEWED = "reviewed"
    QC_PASSED = "qc_passed"
    DELIVERED = "delivered"


class InvalidPackTransitionError(Exception):
    """P0 修复: 路由/转换遇到非法状态机跳转时显式抛出, 而非静默失败.

    携带 current/target/allowed 三元组, API 层可结构化返回 400.
    """
    def __init__(self, current: str, target: str, allowed: List[str]):
        self.current = current
        self.target = target
        self.allowed = allowed
        super().__init__(
            f"非法状态转换: {current} → {target}; 允许: {allowed}"
        )


# 状态机合法转换图 (from → {to})
PACK_TRANSITIONS: Dict[PackStatus, set] = {
    PackStatus.CREATED: {PackStatus.READY, PackStatus.IN_ANNOTATION},
    PackStatus.READY: {PackStatus.IN_ANNOTATION, PackStatus.ANNOTATED},
    PackStatus.IN_ANNOTATION: {PackStatus.ANNOTATED, PackStatus.READY},
    PackStatus.ANNOTATED: {PackStatus.REVIEWED, PackStatus.IN_ANNOTATION},
    PackStatus.REVIEWED: {PackStatus.QC_PASSED, PackStatus.ANNOTATED},
    PackStatus.QC_PASSED: {PackStatus.DELIVERED, PackStatus.REVIEWED},
    PackStatus.DELIVERED: set(),  # 终态
}

# 进度映射 (状态 → 0-100)
STATUS_PROGRESS: Dict[PackStatus, int] = {
    PackStatus.CREATED: 0,
    PackStatus.READY: 10,
    PackStatus.IN_ANNOTATION: 30,
    PackStatus.ANNOTATED: 55,
    PackStatus.REVIEWED: 75,
    PackStatus.QC_PASSED: 90,
    PackStatus.DELIVERED: 100,
}


# ============================================================
# 2. 数据类
# ============================================================

@dataclass
class Pack:
    """数据包/任务包 — 状态机驱动的中间容器"""
    id: str = ""
    name: str = ""
    type: str = PackType.DATA_PACK.value          # data_pack / task_pack
    has_data: bool = False
    source: str = PackSource.UPLOAD.value        # upload / collection / transfer / generation
    status: str = PackStatus.CREATED.value
    requirement_id: str = ""
    project_id: str = ""
    asset_count: int = 0
    dataset_id: str = ""                          # 关联数据集 (link_to_dataset)
    task_type: str = ""                          # task_pack 时填写 (annotation/cleaning/scoring/...)
    metadata: Dict[str, Any] = field(default_factory=dict)
    route_history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================
# 3. 持久化层 — SQLite
# ============================================================

def _data_dir() -> str:
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    os.makedirs(d, exist_ok=True)
    return d


def _db_path() -> str:
    return os.path.join(_data_dir(), "imdf.db")


_SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS packs (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL DEFAULT 'data_pack',
        has_data INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT 'upload',
        status TEXT NOT NULL DEFAULT 'created',
        requirement_id TEXT DEFAULT '',
        project_id TEXT DEFAULT '',
        asset_count INTEGER NOT NULL DEFAULT 0,
        dataset_id TEXT DEFAULT '',
        task_type TEXT DEFAULT '',
        metadata TEXT DEFAULT '{}',
        route_history TEXT DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pack_assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pack_id TEXT NOT NULL,
        asset_id TEXT NOT NULL,
        asset_type TEXT DEFAULT 'image',
        position INTEGER NOT NULL DEFAULT 0,
        added_at TEXT NOT NULL,
        UNIQUE(pack_id, asset_id),
        FOREIGN KEY (pack_id) REFERENCES packs(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_packs_requirement ON packs(requirement_id)",
    "CREATE INDEX IF NOT EXISTS ix_packs_project ON packs(project_id)",
    "CREATE INDEX IF NOT EXISTS ix_packs_type ON packs(type)",
    "CREATE INDEX IF NOT EXISTS ix_packs_status ON packs(status)",
    "CREATE INDEX IF NOT EXISTS ix_pack_assets_pack ON pack_assets(pack_id)",
]


class PackStore:
    """SQLite 持久化层 — thread-local connection."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or _db_path()
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                for stmt in _SCHEMA_SQL:
                    conn.execute(stmt)
            finally:
                conn.close()

    def _row_to_pack(self, row: sqlite3.Row) -> Pack:
        """SQLite row → Pack dataclass."""
        meta_raw = row["metadata"] or "{}"
        route_raw = row["route_history"] or "[]"
        try:
            meta = json.loads(meta_raw) if meta_raw else {}
        except json.JSONDecodeError:
            meta = {}
        try:
            route = json.loads(route_raw) if route_raw else []
        except json.JSONDecodeError:
            route = []
        return Pack(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            has_data=bool(row["has_data"]),
            source=row["source"],
            status=row["status"],
            requirement_id=row["requirement_id"] or "",
            project_id=row["project_id"] or "",
            asset_count=row["asset_count"] or 0,
            dataset_id=row["dataset_id"] or "",
            task_type=row["task_type"] or "",
            metadata=meta,
            route_history=route,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def insert(self, pack: Pack) -> Pack:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    """INSERT INTO packs (id, name, type, has_data, source, status,
                                         requirement_id, project_id, asset_count,
                                         dataset_id, task_type, metadata, route_history,
                                         created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        pack.id, pack.name, pack.type, int(pack.has_data),
                        pack.source, pack.status,
                        pack.requirement_id, pack.project_id, pack.asset_count,
                        pack.dataset_id, pack.task_type,
                        json.dumps(pack.metadata, ensure_ascii=False),
                        json.dumps(pack.route_history, ensure_ascii=False),
                        pack.created_at, pack.updated_at,
                    ),
                )
            finally:
                conn.close()
        return pack

    def update(self, pack_id: str, fields: Dict[str, Any]) -> Optional[Pack]:
        if not fields:
            return self.get(pack_id)
        # 过滤 + 序列化 dict 字段
        safe_fields: Dict[str, Any] = {}
        for k, v in fields.items():
            if k in ("metadata", "route_history"):
                safe_fields[k] = json.dumps(v, ensure_ascii=False)
            elif k == "has_data":
                safe_fields[k] = int(bool(v))
            else:
                safe_fields[k] = v
        safe_fields["updated_at"] = datetime.now().isoformat()

        cols = ", ".join(f"{k}=?" for k in safe_fields.keys())
        vals = list(safe_fields.values()) + [pack_id]
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(f"UPDATE packs SET {cols} WHERE id=?", vals)
            finally:
                conn.close()
        return self.get(pack_id)

    def get(self, pack_id: str) -> Optional[Pack]:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute("SELECT * FROM packs WHERE id=?", (pack_id,)).fetchone()
            finally:
                conn.close()
        if not row:
            return None
        return self._row_to_pack(row)

    def delete(self, pack_id: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute("DELETE FROM packs WHERE id=?", (pack_id,))
                # pack_assets ON DELETE CASCADE
                conn.execute("DELETE FROM pack_assets WHERE pack_id=?", (pack_id,))
                deleted = cur.rowcount > 0
            finally:
                conn.close()
        return deleted

    def list(self, requirement_id: Optional[str] = None,
             project_id: Optional[str] = None,
             type: Optional[str] = None,
             status: Optional[str] = None,
             keyword: Optional[str] = None,
             page: int = 1,
             page_size: int = 20) -> Tuple[List[Pack], int]:
        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))
        offset = (page - 1) * page_size

        where: List[str] = []
        params: List[Any] = []
        if requirement_id:
            where.append("requirement_id=?")
            params.append(requirement_id)
        if project_id:
            where.append("project_id=?")
            params.append(project_id)
        if type:
            where.append("type=?")
            params.append(type)
        if status:
            where.append("status=?")
            params.append(status)
        if keyword:
            # P0 修复: 支持 keyword 模糊查询 (name LIKE)
            where.append("name LIKE ?")
            params.append(f"%{keyword}%")
        where_clause = (" WHERE " + " AND ".join(where)) if where else ""

        with self._lock:
            conn = self._connect()
            try:
                total = conn.execute(f"SELECT COUNT(*) AS c FROM packs{where_clause}",
                                     params).fetchone()["c"]
                rows = conn.execute(
                    f"SELECT * FROM packs{where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    params + [page_size, offset],
                ).fetchall()
            finally:
                conn.close()

        return [self._row_to_pack(r) for r in rows], total

    # ---------- pack_assets 关联表 ----------

    def add_assets(self, pack_id: str, asset_ids: List[str],
                   asset_type: str = "image") -> int:
        """添加资产到包; 返回新增条数."""
        added = 0
        now = datetime.now().isoformat()
        with self._lock:
            conn = self._connect()
            try:
                # 查询当前 max position
                row = conn.execute(
                    "SELECT COALESCE(MAX(position),-1) AS m FROM pack_assets WHERE pack_id=?",
                    (pack_id,),
                ).fetchone()
                base_pos = (row["m"] if row else -1) + 1
                for i, aid in enumerate(asset_ids):
                    try:
                        conn.execute(
                            """INSERT OR IGNORE INTO pack_assets (pack_id, asset_id, asset_type, position, added_at)
                               VALUES (?,?,?,?,?)""",
                            (pack_id, aid, asset_type, base_pos + i, now),
                        )
                        added += 1
                    except sqlite3.IntegrityError:
                        pass
                # 同步 packs.asset_count
                count_row = conn.execute(
                    "SELECT COUNT(*) AS c FROM pack_assets WHERE pack_id=?", (pack_id,)
                ).fetchone()
                conn.execute(
                    "UPDATE packs SET asset_count=?, updated_at=? WHERE id=?",
                    (count_row["c"], now, pack_id),
                )
            finally:
                conn.close()
        return added

    def list_assets(self, pack_id: str, page: int = 1, page_size: int = 20) -> Tuple[List[Dict[str, Any]], int]:
        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))
        offset = (page - 1) * page_size
        with self._lock:
            conn = self._connect()
            try:
                total = conn.execute(
                    "SELECT COUNT(*) AS c FROM pack_assets WHERE pack_id=?", (pack_id,)
                ).fetchone()["c"]
                rows = conn.execute(
                    """SELECT asset_id, asset_type, position, added_at FROM pack_assets
                       WHERE pack_id=? ORDER BY position LIMIT ? OFFSET ?""",
                    (pack_id, page_size, offset),
                ).fetchall()
            finally:
                conn.close()
        items = [
            {"asset_id": r["asset_id"], "asset_type": r["asset_type"],
             "position": r["position"], "added_at": r["added_at"]}
            for r in rows
        ]
        return items, total


# ============================================================
# 4. PackEngine — 业务门面
# ============================================================

class PackEngine:
    """包管理门面 — 创建/查询/转换/路由."""

    def __init__(self, store: Optional[PackStore] = None):
        self.store = store or PackStore()

    # ---------- 创建 ----------

    def create_data_pack(self, name: str, asset_ids: List[str],
                         requirement_id: str = "", project_id: str = "",
                         source: str = PackSource.UPLOAD.value,
                         metadata: Optional[Dict[str, Any]] = None) -> Pack:
        """创建数据包 — has_data=True (asset_ids 非空)."""
        now = datetime.now().isoformat()
        pack = Pack(
            id=f"pack_{uuid.uuid4().hex[:12]}",
            name=name,
            type=PackType.DATA_PACK.value,
            has_data=bool(asset_ids),
            source=source,
            status=PackStatus.CREATED.value,
            requirement_id=requirement_id,
            project_id=project_id,
            asset_count=len(asset_ids),
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self.store.insert(pack)
        if asset_ids:
            self.store.add_assets(pack.id, asset_ids)
            # 自动 ready: 有资产即可就绪
            self._auto_transition(pack, PackStatus.READY)
        return self.store.get(pack.id) or pack

    def create_task_pack(self, name: str, task_type: str, asset_count: int,
                         requirement_id: str = "", project_id: str = "",
                         metadata: Optional[Dict[str, Any]] = None) -> Pack:
        """创建任务包 — has_data=False (待执行的任务单元)."""
        if task_type not in ("annotation", "cleaning", "scoring", "review", "augmentation", "evaluation"):
            raise ValueError(
                f"task_type 非法: {task_type!r}, 应为 annotation/cleaning/scoring/review/augmentation/evaluation"
            )
        now = datetime.now().isoformat()
        pack = Pack(
            id=f"pack_{uuid.uuid4().hex[:12]}",
            name=name,
            type=PackType.TASK_PACK.value,
            has_data=False,
            source=PackSource.UPLOAD.value,
            status=PackStatus.CREATED.value,
            requirement_id=requirement_id,
            project_id=project_id,
            asset_count=asset_count,
            task_type=task_type,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        self.store.insert(pack)
        # task_pack 无资产, 不自动 ready
        return pack

    def _auto_transition(self, pack: Pack, target: PackStatus) -> None:
        """自动状态转换 (绕过显式校验)."""
        try:
            self.store.update(pack.id, {"status": target.value})
        except Exception as e:
            logger.warning(f"_auto_transition failed for {pack.id}: {e}")

    # ---------- 查询 ----------

    def list_packs(self, requirement_id: Optional[str] = None,
                   project_id: Optional[str] = None,
                   type: Optional[str] = None,
                   status: Optional[str] = None,
                   keyword: Optional[str] = None,
                   page: int = 1, page_size: int = 20) -> Tuple[List[Pack], int]:
        return self.store.list(
            requirement_id=requirement_id, project_id=project_id,
            type=type, status=status, keyword=keyword,
            page=page, page_size=page_size,
        )

    def get_pack(self, pack_id: str) -> Optional[Pack]:
        return self.store.get(pack_id)

    # ---------- 状态转换 ----------

    def update_pack_status(self, pack_id: str, new_status: str) -> Pack:
        """状态机驱动转换 — 校验合法性."""
        pack = self.store.get(pack_id)
        if not pack:
            raise ValueError(f"pack 不存在: {pack_id}")

        try:
            target = PackStatus(new_status)
        except ValueError:
            raise ValueError(f"非法状态: {new_status!r}")

        current = PackStatus(pack.status)
        if target not in PACK_TRANSITIONS.get(current, set()):
            raise ValueError(
                f"非法状态转换: {current.value} → {target.value}; "
                f"允许: {[s.value for s in PACK_TRANSITIONS.get(current, set())]}"
            )

        updated = self.store.update(pack_id, {"status": target.value})
        return updated or pack

    def transition(self, pack_id: str, new_status: str, reason: str = "") -> Pack:
        """带审计的状态转换 (兼容老 API 命名)."""
        pack = self.update_pack_status(pack_id, new_status)
        if reason:
            history = list(pack.route_history or [])
            history.append({
                "action": "transition",
                "to_status": new_status,
                "reason": reason,
                "at": datetime.now().isoformat(),
            })
            # 截断 200 条
            if len(history) > 200:
                history = history[-200:]
            self.store.update(pack_id, {"route_history": history})
            pack.route_history = history
        return pack

    # ---------- 智能路由 ----------

    def route_pack(self, pack_id: str) -> Dict[str, Any]:
        """根据 has_data 决定路由:
        - has_data=True  → annotation 标注流
        - has_data=False → collection 采集流
        返回: {target_module, target_endpoint, reason, estimated_steps}
        """
        pack = self.store.get(pack_id)
        if not pack:
            raise ValueError(f"pack 不存在: {pack_id}")

        now = datetime.now().isoformat()
        if pack.has_data:
            target_module = "annotation"
            target_endpoint = "/api/v1/annotation/assign"
            reason = "数据包含数据, 进入标注流程"
            next_status = PackStatus.IN_ANNOTATION.value
        else:
            target_module = "collection"
            target_endpoint = "/api/v1/collection/jobs"
            reason = "空包, 触发采集流程"
            next_status = PackStatus.READY.value  # 触发采集后置 ready

        history = list(pack.route_history or [])
        history.append({
            "action": "route",
            "target_module": target_module,
            "target_endpoint": target_endpoint,
            "reason": reason,
            "at": now,
        })
        if len(history) > 200:
            history = history[-200:]

        # 校验状态机合法性
        current = PackStatus(pack.status)
        target_enum = PackStatus(next_status)
        allowed_set = PACK_TRANSITIONS.get(current, set())
        if target_enum in allowed_set:
            self.store.update(pack_id, {
                "status": next_status,
                "route_history": history,
            })
        else:
            # P0 修复: 非法转换必须显式失败, 不允许静默 return 200 OK
            allowed = sorted(s.value for s in allowed_set)
            raise InvalidPackTransitionError(
                current=current.value,
                target=target_enum.value,
                allowed=allowed,
            )

        return {
            "pack_id": pack.id,
            "target_module": target_module,
            "target_endpoint": target_endpoint,
            "reason": reason,
            "estimated_steps": ["ingest", "process", "verify", "finalize"],
            "routed_at": now,
        }

    # ---------- 数据集关联 ----------

    def link_to_dataset(self, pack_id: str, dataset_id: str) -> Pack:
        """关联 pack 到 dataset."""
        pack = self.store.get(pack_id)
        if not pack:
            raise ValueError(f"pack 不存在: {pack_id}")
        updated = self.store.update(pack_id, {"dataset_id": dataset_id})
        history = list(updated.route_history or [])
        history.append({
            "action": "link_dataset",
            "dataset_id": dataset_id,
            "at": datetime.now().isoformat(),
        })
        if len(history) > 200:
            history = history[-200:]
        self.store.update(pack_id, {"route_history": history})
        updated.route_history = history
        return updated

    # ---------- 统计 ----------

    def get_pack_stats(self, pack_id: str) -> Dict[str, Any]:
        """统计 — progress% + completion_rate + asset_distribution."""
        pack = self.store.get(pack_id)
        if not pack:
            raise ValueError(f"pack 不存在: {pack_id}")

        assets, _ = self.store.list_assets(pack_id, page=1, page_size=1)
        total_assets = pack.asset_count
        try:
            progress = STATUS_PROGRESS[PackStatus(pack.status)]
        except (KeyError, ValueError):
            progress = 0
        # completion_rate = 已完成阶段 / 总阶段
        completed_stages = sum(
            1 for s in [PackStatus.CREATED, PackStatus.READY, PackStatus.IN_ANNOTATION,
                        PackStatus.ANNOTATED, PackStatus.REVIEWED, PackStatus.QC_PASSED,
                        PackStatus.DELIVERED]
            if STATUS_PROGRESS[s] <= progress
        )
        completion_rate = completed_stages / 7.0

        return {
            "pack_id": pack.id,
            "name": pack.name,
            "type": pack.type,
            "status": pack.status,
            "progress_pct": progress,
            "completion_rate": round(completion_rate, 4),
            "asset_count": total_assets,
            "has_data": pack.has_data,
            "linked_dataset": pack.dataset_id or None,
            "route_count": len(pack.route_history or []),
            "created_at": pack.created_at,
            "updated_at": pack.updated_at,
        }

    # ---------- 删除 ----------

    def delete_pack(self, pack_id: str) -> bool:
        """删除 pack (含 pack_assets 级联)."""
        return self.store.delete(pack_id)


# ============================================================
# 5. 模块级默认实例
# ============================================================

_default_engine: Optional[PackEngine] = None
_engine_lock = threading.Lock()


def get_engine() -> PackEngine:
    global _default_engine
    if _default_engine is None:
        with _engine_lock:
            if _default_engine is None:
                _default_engine = PackEngine()
    return _default_engine


def reset_engine() -> None:
    """测试用 — 重置默认实例."""
    global _default_engine
    with _engine_lock:
        _default_engine = None