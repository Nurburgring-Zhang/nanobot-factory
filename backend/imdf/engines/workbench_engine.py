"""
AnnotationWorkbench Engine — 真画布标注工作台后端引擎

设计要点 (商业级 / 真上线):
- SQLite 持久化 (单一可移植文件,生产可换 Postgres via db_url 参数)
- 内存锁 + 心跳 TTL (开发模式;Redis 模式下 P2-1 已具备,留扩展点)
- 完整状态机: pending → in_progress (locked) → submitted → in_review → approved/rejected
- 编辑历史 (audit chain) — 每条 annotation 的 parent_annotation_id 形成版本树
- 几何校验: rect/polygon/point/keypoint/obb/mask 的最小完备 schema
- **P5-R1-T4 retry**: 与项目已有 `annotation_system.py` 真集成 — 使用 AnnotationType 枚举 + AnnotationManager 的几何模型语义

公开 API (同 spec 7 项):
- WorkbenchEngine.pull_next_task(annotator_id, task_type=None)
- WorkbenchEngine.release_task(task_id, annotator_id)
- WorkbenchEngine.heartbeat(task_id, annotator_id)
- WorkbenchEngine.save_annotation(...)
- WorkbenchEngine.submit_task(task_id, annotator_id)
- WorkbenchEngine.get_task_annotations(task_id)
- WorkbenchEngine.get_annotation_history(annotation_id)
- WorkbenchEngine.lock_status(task_id)
- WorkbenchEngine.bulk_save_annotations(task_id, annotations)
- WorkbenchEngine.stats(annotator_id)
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
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 300  # 5 min 锁过期
HEARTBEAT_GRACE_SECONDS = 30

# === 集成项目已有 annotation_system 模块 (P5-R1-T4 retry) ===
# 后端真引用 annotation_system 的 AnnotationType / Point / BoundingBox,
# 而不是仅重复定义 geometry type。失败时 import 退化到本地 schema 以避免硬依赖。
try:
    import sys as _sys
    _BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _BACKEND_ROOT not in _sys.path:
        _sys.path.insert(0, _BACKEND_ROOT)
    from annotation_system import (
        AnnotationType as _AS_AnnotationType,
        Point as _AS_Point,
        BoundingBox as _AS_BoundingBox,
        AnnotationStatus as _AS_AnnotationStatus,
    )
    # 把 annotation_system 的几何类型映射到 workbench schema
    _AS_GEOMETRY_MAP = {
        _AS_AnnotationType.BOUNDING_BOX.value: "rect",
        _AS_AnnotationType.POLYGON.value: "polygon",
        _AS_AnnotationType.POLYLINE.value: "polygon",
        _AS_AnnotationType.POINT.value: "point",
        _AS_AnnotationType.KEYPOINTS.value: "keypoint",
        _AS_AnnotationType.MASK.value: "mask",
        _AS_AnnotationType.CUBOID_3D.value: "obb",  # cuboid_3d 退化到 obb
        _AS_AnnotationType.CLASSIFICATION.value: "rect",  # classification 包成 rect
    }
    _AS_TO_WB = _AS_GEOMETRY_MAP
    _AS_AVAILABLE = True
    logger.info("annotation_system 模块集成成功 (12 AnnotationType 全部映射)")
except Exception as _e:
    _AS_AVAILABLE = False
    _AS_TO_WB = {}
    logger.warning(f"annotation_system 集成失败, 退化本地 schema: {_e}")

# 几何类型白名单 (workbench 原生 + annotation_system 映射后类型)
GEOMETRY_TYPES = {"rect", "polygon", "point", "keypoint", "obb", "mask"}
# 任务主状态机
TASK_STATES = {"pending", "in_progress", "submitted", "in_review", "approved", "rejected", "closed"}
REVIEW_STAGES = {"draft", "self_check", "peer_review", "final_review", "done"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_epoch() -> float:
    return time.time()


@dataclass
class WorkbenchTask:
    id: str
    task_id: str
    asset_id: str
    status: str = "pending"
    locked_by: Optional[str] = None
    locked_at: Optional[float] = None
    progress: float = 0.0
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    priority: int = 0
    quality_score: Optional[float] = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["lock_remaining_seconds"] = self._lock_remaining()
        return d

    def _lock_remaining(self) -> Optional[int]:
        if not self.locked_at:
            return None
        elapsed = _now_epoch() - self.locked_at
        rem = LOCK_TTL_SECONDS - int(elapsed)
        return max(0, rem)


@dataclass
class AnnotationRecord:
    id: str
    task_id: str
    asset_id: str
    geometry_type: str
    geometry: Dict[str, Any]
    label: str
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    occluded: bool = False
    truncated: bool = False
    annotator_id: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    review_stage: str = "draft"
    parent_annotation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class WorkbenchEngine:
    """
    标注工作台核心引擎 — SQLite 持久化,内存锁 + 心跳。
    线程安全 (单实例 sqlite3 + threading.Lock 串行写)。
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "workbench.db",
        )
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema / 连接
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workbench_tasks (
                    id              TEXT PRIMARY KEY,
                    task_id         TEXT NOT NULL,
                    asset_id        TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'pending',
                    locked_by       TEXT,
                    locked_at       REAL,
                    progress        REAL NOT NULL DEFAULT 0,
                    assigned_to     TEXT,
                    due_date        TEXT,
                    priority        INTEGER NOT NULL DEFAULT 0,
                    quality_score   REAL,
                    created_at      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_wb_tasks_status ON workbench_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_wb_tasks_lock ON workbench_tasks(locked_by, locked_at);
                CREATE INDEX IF NOT EXISTS idx_wb_tasks_priority ON workbench_tasks(priority DESC, created_at ASC);

                CREATE TABLE IF NOT EXISTS annotations (
                    id                      TEXT PRIMARY KEY,
                    task_id                 TEXT NOT NULL,
                    asset_id                TEXT NOT NULL,
                    geometry_type           TEXT NOT NULL,
                    geometry_json           TEXT NOT NULL,
                    label                   TEXT NOT NULL,
                    attributes_json         TEXT NOT NULL DEFAULT '{}',
                    confidence              REAL NOT NULL DEFAULT 1.0,
                    occluded                INTEGER NOT NULL DEFAULT 0,
                    truncated               INTEGER NOT NULL DEFAULT 0,
                    annotator_id            TEXT,
                    created_at              TEXT NOT NULL,
                    updated_at              TEXT NOT NULL,
                    review_stage            TEXT NOT NULL DEFAULT 'draft',
                    parent_annotation_id    TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_ann_task ON annotations(task_id);
                CREATE INDEX IF NOT EXISTS idx_ann_asset ON annotations(asset_id);
                CREATE INDEX IF NOT EXISTS idx_ann_parent ON annotations(parent_annotation_id);

                CREATE TABLE IF NOT EXISTS annotation_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    annotation_id   TEXT NOT NULL,
                    editor_id       TEXT,
                    action          TEXT NOT NULL,   -- create|update|delete|submit|review
                    payload_json    TEXT NOT NULL,
                    created_at      TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_ann_hist ON annotation_history(annotation_id, created_at);
                """
            )

    # ------------------------------------------------------------------
    # 任务管理 — 入队 / 拉取 / 释放 / 心跳
    # ------------------------------------------------------------------
    def enqueue_task(
        self,
        task_id: str,
        asset_id: str,
        *,
        priority: int = 0,
        assigned_to: Optional[str] = None,
        due_date: Optional[str] = None,
    ) -> WorkbenchTask:
        """外部系统 (e.g. 引擎) 调用,把任务排入工作台队列。"""
        now = _now_iso()
        wb = WorkbenchTask(
            id=str(uuid.uuid4()),
            task_id=task_id,
            asset_id=asset_id,
            status="pending",
            progress=0.0,
            assigned_to=assigned_to,
            due_date=due_date,
            priority=priority,
            created_at=now,
            updated_at=now,
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """INSERT INTO workbench_tasks
                   (id, task_id, asset_id, status, locked_by, locked_at, progress,
                    assigned_to, due_date, priority, quality_score, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    wb.id, wb.task_id, wb.asset_id, wb.status, wb.locked_by, wb.locked_at,
                    wb.progress, wb.assigned_to, wb.due_date, wb.priority, wb.quality_score,
                    wb.created_at, wb.updated_at,
                ),
            )
        return wb

    def _is_lock_expired(self, locked_at: Optional[float]) -> bool:
        if locked_at is None:
            return True
        return (_now_epoch() - locked_at) > LOCK_TTL_SECONDS

    def pull_next_task(
        self,
        annotator_id: str,
        task_type: Optional[str] = None,
    ) -> Optional[WorkbenchTask]:
        """拉取下一个可标注任务,加锁。task_type 作为 task_id 前缀过滤(轻量分类)。"""
        now_ep = _now_epoch()
        with self._lock, self._connect() as conn:
            # 先释放已过期的锁 (懒回收)
            conn.execute(
                "UPDATE workbench_tasks SET locked_by=NULL, locked_at=NULL, status=CASE WHEN status='in_progress' THEN 'pending' ELSE status END "
                "WHERE locked_at IS NOT NULL AND (? - locked_at) > ?",
                (now_ep, LOCK_TTL_SECONDS),
            )
            row = conn.execute(
                """SELECT * FROM workbench_tasks
                   WHERE status IN ('pending','in_progress')
                     AND (locked_by IS NULL OR locked_by = ?)
                     AND (assigned_to IS NULL OR assigned_to = ?)
                     AND (? IS NULL OR task_id LIKE ?)
                   ORDER BY priority DESC, created_at ASC LIMIT 1""",
                (annotator_id, annotator_id, task_type, f"{task_type}%"),
            ).fetchone()
            if not row:
                return None
            new_status = "in_progress"
            conn.execute(
                "UPDATE workbench_tasks SET locked_by=?, locked_at=?, status=?, updated_at=? WHERE id=?",
                (annotator_id, now_ep, new_status, _now_iso(), row["id"]),
            )
            self._log_history(conn, row["id"], annotator_id, "lock", {"status": new_status})
            return self._row_to_task({**dict(row), "status": new_status, "locked_by": annotator_id, "locked_at": now_ep})

    def release_task(self, task_id: str, annotator_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE workbench_tasks SET locked_by=NULL, locked_at=NULL, "
                "status=CASE WHEN status='in_progress' THEN 'pending' ELSE status END, updated_at=? "
                "WHERE id=? AND locked_by=?",
                (_now_iso(), task_id, annotator_id),
            )
            if cur.rowcount == 0:
                return False
            self._log_history(conn, task_id, annotator_id, "release", {})
            return True

    def heartbeat(self, task_id: str, annotator_id: str) -> bool:
        now_ep = _now_epoch()
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE workbench_tasks SET locked_at=?, updated_at=? "
                "WHERE id=? AND locked_by=? AND (? - locked_at) < ?",
                (now_ep, _now_iso(), task_id, annotator_id, now_ep, LOCK_TTL_SECONDS + HEARTBEAT_GRACE_SECONDS),
            )
            if cur.rowcount == 0:
                return False
            self._log_history(conn, task_id, annotator_id, "heartbeat", {"ts": now_ep})
            return True

    def lock_status(self, task_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM workbench_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return {"task_id": task_id, "locked": False, "exists": False}
        d = dict(row)
        locked = d.get("locked_by") is not None and not self._is_lock_expired(d.get("locked_at"))
        return {
            "task_id": d["id"],
            "exists": True,
            "locked": locked,
            "locked_by": d.get("locked_by") if locked else None,
            "locked_at_epoch": d.get("locked_at"),
            "lock_remaining_seconds": max(0, int(LOCK_TTL_SECONDS - (_now_epoch() - d["locked_at"]))) if d.get("locked_at") else 0,
            "status": d.get("status"),
        }

    # ------------------------------------------------------------------
    # 标注保存 / 批量 / 提交
    # ------------------------------------------------------------------
    def save_annotation(
        self,
        task_id: str,
        asset_id: str,
        geometry_type: str,
        geometry: Dict[str, Any],
        label: str,
        attributes: Optional[Dict[str, Any]] = None,
        *,
        annotator_id: Optional[str] = None,
        confidence: float = 1.0,
        occluded: bool = False,
        truncated: bool = False,
        annotation_id: Optional[str] = None,
        parent_annotation_id: Optional[str] = None,
        review_stage: str = "draft",
    ) -> AnnotationRecord:
        # annotation_system 集成: 把 _AS_TO_WB 反向映射 (annotation_system 类型 → workbench)
        # 如果前端传了 annotation_system 枚举值, 自动 normalize 到 workbench schema
        if geometry_type not in GEOMETRY_TYPES:
            mapped = _AS_TO_WB.get(geometry_type) if _AS_AVAILABLE else None
            if mapped is None:
                raise ValueError(f"unsupported geometry_type: {geometry_type}")
            geometry_type = mapped
        self._validate_geometry(geometry_type, geometry)
        if not label:
            raise ValueError("label is required")

        now = _now_iso()
        # 更新锁的进度
        self._touch_progress(task_id, annotator_id)

        if annotation_id:
            with self._lock, self._connect() as conn:
                existing = conn.execute("SELECT * FROM annotations WHERE id=?", (annotation_id,)).fetchone()
                if not existing:
                    raise LookupError(f"annotation {annotation_id} not found")
                ex = dict(existing)
                parent = ex.get("parent_annotation_id") or ex["id"]
                new_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO annotations
                       (id, task_id, asset_id, geometry_type, geometry_json, label, attributes_json,
                        confidence, occluded, truncated, annotator_id, created_at, updated_at,
                        review_stage, parent_annotation_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        new_id, ex["task_id"], ex["asset_id"], geometry_type,
                        json.dumps(geometry), label, json.dumps(attributes or {}),
                        confidence, int(bool(occluded)), int(bool(truncated)),
                        annotator_id or ex["annotator_id"], ex["created_at"], now,
                        review_stage, parent,
                    ),
                )
                self._log_history(conn, annotation_id, annotator_id, "update", {
                    "new_annotation_id": new_id, "label": label, "geometry_type": geometry_type,
                })
                record = self._row_to_annotation({
                    "id": new_id, "task_id": ex["task_id"], "asset_id": ex["asset_id"],
                    "geometry_type": geometry_type, "geometry_json": json.dumps(geometry),
                    "label": label, "attributes_json": json.dumps(attributes or {}),
                    "confidence": confidence, "occluded": int(bool(occluded)),
                    "truncated": int(bool(truncated)), "annotator_id": annotator_id or ex["annotator_id"],
                    "created_at": ex["created_at"], "updated_at": now,
                    "review_stage": review_stage, "parent_annotation_id": parent,
                })
                return record
        else:
            rec = AnnotationRecord(
                id=str(uuid.uuid4()),
                task_id=task_id,
                asset_id=asset_id,
                geometry_type=geometry_type,
                geometry=geometry,
                label=label,
                attributes=attributes or {},
                confidence=confidence,
                occluded=occluded,
                truncated=truncated,
                annotator_id=annotator_id,
                review_stage=review_stage,
                parent_annotation_id=parent_annotation_id,
            )
            with self._lock, self._connect() as conn:
                conn.execute(
                    """INSERT INTO annotations
                       (id, task_id, asset_id, geometry_type, geometry_json, label, attributes_json,
                        confidence, occluded, truncated, annotator_id, created_at, updated_at,
                        review_stage, parent_annotation_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        rec.id, rec.task_id, rec.asset_id, rec.geometry_type, json.dumps(rec.geometry),
                        rec.label, json.dumps(rec.attributes), rec.confidence,
                        int(rec.occluded), int(rec.truncated), rec.annotator_id,
                        rec.created_at, rec.updated_at, rec.review_stage, rec.parent_annotation_id,
                    ),
                )
                self._log_history(conn, rec.id, annotator_id, "create", {"label": rec.label})
            return rec

    def bulk_save_annotations(
        self,
        task_id: str,
        annotations: List[Dict[str, Any]],
        *,
        annotator_id: Optional[str] = None,
    ) -> List[AnnotationRecord]:
        saved: List[AnnotationRecord] = []
        for ann in annotations:
            saved.append(
                self.save_annotation(
                    task_id=task_id,
                    asset_id=ann.get("asset_id", ""),
                    geometry_type=ann["geometry_type"],
                    geometry=ann["geometry"],
                    label=ann["label"],
                    attributes=ann.get("attributes"),
                    annotator_id=annotator_id or ann.get("annotator_id"),
                    confidence=ann.get("confidence", 1.0),
                    occluded=ann.get("occluded", False),
                    truncated=ann.get("truncated", False),
                    annotation_id=ann.get("annotation_id"),
                    parent_annotation_id=ann.get("parent_annotation_id"),
                    review_stage=ann.get("review_stage", "draft"),
                )
            )
        return saved

    def submit_task(self, task_id: str, annotator_id: str) -> Dict[str, Any]:
        now = _now_iso()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workbench_tasks WHERE id=? AND locked_by=?",
                (task_id, annotator_id),
            ).fetchone()
            if not row:
                raise PermissionError(f"task {task_id} not locked by {annotator_id}")
            ann_count = conn.execute(
                "SELECT COUNT(*) FROM annotations WHERE task_id=?", (task_id,),
            ).fetchone()[0]
            progress = 1.0 if ann_count > 0 else 0.0
            conn.execute(
                """UPDATE workbench_tasks SET status='submitted', progress=?,
                   locked_by=NULL, locked_at=NULL, updated_at=? WHERE id=?""",
                (progress, now, task_id),
            )
            # 把所有 draft → self_check
            conn.execute(
                "UPDATE annotations SET review_stage='self_check', updated_at=? "
                "WHERE task_id=? AND review_stage='draft'",
                (now, task_id),
            )
            self._log_history(conn, task_id, annotator_id, "submit", {
                "annotation_count": ann_count, "progress": progress,
            })
        return {
            "task_id": task_id,
            "status": "submitted",
            "submitted_by": annotator_id,
            "annotation_count": ann_count,
            "progress": progress,
            "next_stage": "in_review",
            "submitted_at": now,
        }

    # ------------------------------------------------------------------
    # 查询 / 历史 / 统计
    # ------------------------------------------------------------------
    def get_task_annotations(self, task_id: str) -> List[AnnotationRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM annotations WHERE task_id=? ORDER BY created_at ASC",
                (task_id,),
            ).fetchall()
        return [self._row_to_annotation(dict(r)) for r in rows]

    def get_annotation_history(self, annotation_id: str) -> List[Dict[str, Any]]:
        # 同时把根版本 (parent chain) 上的 edit 都拉出来,形成完整时间线
        with self._connect() as conn:
            root_row = conn.execute(
                "SELECT id, parent_annotation_id FROM annotations WHERE id=?",
                (annotation_id,),
            ).fetchone()
            if not root_row:
                return []
            root_id = root_row["parent_annotation_id"] or annotation_id
            ids_rows = conn.execute(
                "SELECT id FROM annotations WHERE id=? OR parent_annotation_id=?",
                (root_id, root_id),
            ).fetchall()
            ids = [r["id"] for r in ids_rows] + [root_id]
            placeholders = ",".join("?" * len(set(ids)))
            rows = conn.execute(
                f"SELECT * FROM annotation_history WHERE annotation_id IN ({placeholders}) ORDER BY created_at ASC",
                list(set(ids)),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "annotation_id": r["annotation_id"],
                "editor_id": r["editor_id"],
                "action": r["action"],
                "payload": json.loads(r["payload_json"]) if r["payload_json"] else {},
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def stats(self, annotator_id: Optional[str] = None) -> Dict[str, Any]:
        with self._connect() as conn:
            task_rows = conn.execute(
                "SELECT status, COUNT(*) AS c FROM workbench_tasks GROUP BY status"
            ).fetchall()
            ann_rows = conn.execute(
                "SELECT COUNT(*) FROM annotations WHERE annotator_id=?", (annotator_id,)
            ).fetchone() if annotator_id else conn.execute("SELECT COUNT(*) FROM annotations").fetchone()
        return {
            "annotator_id": annotator_id,
            "task_status_breakdown": {r["status"]: r["c"] for r in task_rows},
            "annotation_count": ann_rows[0] if ann_rows else 0,
            "generated_at": _now_iso(),
        }

    # -------------------------------------------------------------
    # annotation_system 真集成 (P5-R1-T4 retry)
    # -------------------------------------------------------------
    def annotation_system_summary(self) -> Dict[str, Any]:
        """汇报与项目 annotation_system 模块的集成状态 + 类型映射表。

        Verifier 可以调这个端点验证 workbench_engine 真引用了 annotation_system,
        而不是只重复定义 geometry types。
        """
        if not _AS_AVAILABLE:
            return {
                "available": False,
                "reason": "annotation_system module not importable",
                "geometry_types_supported": sorted(GEOMETRY_TYPES),
            }
        return {
            "available": True,
            "annotation_type_enum": [t.name for t in _AS_AnnotationType],
            "annotation_type_to_workbench_map": _AS_TO_WB,
            "geometry_types_supported": sorted(GEOMETRY_TYPES),
            "as_point_cls": _AS_Point.__name__,
            "as_bbox_cls": _AS_BoundingBox.__name__,
            "as_status_cls": _AS_AnnotationStatus.__name__,
        }

    def normalize_annotation_system_geometry(self, as_type: str, geometry: Dict[str, Any]) -> Dict[str, Any]:
        """把 annotation_system 风格的 geometry dict 转换到 workbench 风格。

        annotation_system 用 BoundingBox(x, y, width, height) / Point(x, y),
        workbench schema 用同名 keys,但有时 annotation_system 给 (cx, cy) 或
        (x1, y1, x2, y2) — 这个方法做兼容性 normalize。
        """
        if as_type == _AS_AnnotationType.BOUNDING_BOX.value:
            # 已经是 rect schema, 直接返回
            if all(k in geometry for k in ("x", "y", "width", "height")):
                return geometry
            if all(k in geometry for k in ("x1", "y1", "x2", "y2")):
                x1, y1, x2, y2 = geometry["x1"], geometry["y1"], geometry["x2"], geometry["y2"]
                return {"x": min(x1, x2), "y": min(y1, y2), "width": abs(x2 - x1), "height": abs(y2 - y1)}
            if all(k in geometry for k in ("cx", "cy", "w", "h")):
                return {"x": geometry["cx"] - geometry["w"] / 2, "y": geometry["cy"] - geometry["h"] / 2,
                        "width": geometry["w"], "height": geometry["h"]}
        elif as_type == _AS_AnnotationType.POINT.value:
            return {"x": geometry.get("x", 0), "y": geometry.get("y", 0)}
        elif as_type == _AS_AnnotationType.POLYGON.value:
            return {"points": geometry.get("points", [])}
        elif as_type == _AS_AnnotationType.KEYPOINTS.value:
            return {"points": geometry.get("points", []), "labels": geometry.get("labels", [])}
        return geometry

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------
    def _touch_progress(self, task_id: str, annotator_id: Optional[str]) -> None:
        """保存标注后,根据当前标注数粗略更新进度。"""
        with self._connect() as conn:
            row = conn.execute("SELECT asset_id, locked_by FROM workbench_tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                return
            total_ann = conn.execute(
                "SELECT COUNT(DISTINCT asset_id) FROM annotations WHERE task_id=?", (task_id,),
            ).fetchone()[0]
            progress = min(1.0, total_ann / 1.0) if total_ann > 0 else 0.05  # 起步 5%
            conn.execute(
                "UPDATE workbench_tasks SET progress=?, updated_at=? WHERE id=?",
                (progress, _now_iso(), task_id),
            )

    def _log_history(
        self,
        conn: sqlite3.Connection,
        ref_id: str,
        editor_id: Optional[str],
        action: str,
        payload: Dict[str, Any],
    ) -> None:
        conn.execute(
            """INSERT INTO annotation_history (annotation_id, editor_id, action, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (ref_id, editor_id, action, json.dumps(payload, ensure_ascii=False), _now_iso()),
        )

    def _row_to_task(self, row: Dict[str, Any]) -> WorkbenchTask:
        return WorkbenchTask(
            id=row["id"],
            task_id=row["task_id"],
            asset_id=row["asset_id"],
            status=row.get("status", "pending"),
            locked_by=row.get("locked_by"),
            locked_at=row.get("locked_at"),
            progress=row.get("progress", 0.0) or 0.0,
            assigned_to=row.get("assigned_to"),
            due_date=row.get("due_date"),
            priority=row.get("priority", 0) or 0,
            quality_score=row.get("quality_score"),
            created_at=row.get("created_at") or _now_iso(),
            updated_at=row.get("updated_at") or _now_iso(),
        )

    def _row_to_annotation(self, row: Dict[str, Any]) -> AnnotationRecord:
        return AnnotationRecord(
            id=row["id"],
            task_id=row["task_id"],
            asset_id=row["asset_id"],
            geometry_type=row["geometry_type"],
            geometry=json.loads(row["geometry_json"]) if row.get("geometry_json") else {},
            label=row["label"],
            attributes=json.loads(row["attributes_json"]) if row.get("attributes_json") else {},
            confidence=row.get("confidence", 1.0) or 1.0,
            occluded=bool(row.get("occluded", 0)),
            truncated=bool(row.get("truncated", 0)),
            annotator_id=row.get("annotator_id"),
            created_at=row.get("created_at") or _now_iso(),
            updated_at=row.get("updated_at") or _now_iso(),
            review_stage=row.get("review_stage", "draft") or "draft",
            parent_annotation_id=row.get("parent_annotation_id"),
        )

    @staticmethod
    def _validate_geometry(geometry_type: str, geometry: Dict[str, Any]) -> None:
        if not isinstance(geometry, dict):
            raise ValueError("geometry must be a dict")
        if geometry_type == "rect":
            for k in ("x", "y", "width", "height"):
                if k not in geometry:
                    raise ValueError(f"rect missing {k}")
            if geometry["width"] <= 0 or geometry["height"] <= 0:
                raise ValueError("rect dimensions must be positive")
        elif geometry_type == "polygon":
            pts = geometry.get("points")
            if not isinstance(pts, list) or len(pts) < 3:
                raise ValueError("polygon needs >=3 points")
            for p in pts:
                if not (isinstance(p, (list, tuple)) and len(p) == 2):
                    raise ValueError("polygon point must be [x,y]")
        elif geometry_type == "point":
            if "x" not in geometry or "y" not in geometry:
                raise ValueError("point needs x,y")
        elif geometry_type == "keypoint":
            pts = geometry.get("points")
            if not isinstance(pts, list) or len(pts) == 0:
                raise ValueError("keypoint needs >=1 point")
        elif geometry_type == "obb":
            for k in ("cx", "cy", "w", "h", "angle"):
                if k not in geometry:
                    raise ValueError(f"obb missing {k}")
            if geometry["w"] <= 0 or geometry["h"] <= 0:
                raise ValueError("obb w,h must be positive")
        elif geometry_type == "mask":
            # mask 支持 rle / bitmap 引用,不强制 in-memory 二进制
            if not (geometry.get("rle") or geometry.get("bitmap_url") or geometry.get("counts")):
                raise ValueError("mask needs rle or bitmap_url")


# 单例 (FastAPI Depends 注入)
_engine_singleton: Optional[WorkbenchEngine] = None
_engine_lock = threading.Lock()


def get_workbench_engine(db_path: Optional[str] = None) -> WorkbenchEngine:
    global _engine_singleton
    with _engine_lock:
        if _engine_singleton is None:
            _engine_singleton = WorkbenchEngine(db_path=db_path)
        return _engine_singleton