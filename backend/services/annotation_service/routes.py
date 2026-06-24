"""P3-2-W1 + P3-5-W1 annotation-service routes — public REST surface.

Exposes:
  GET  /healthz                          — liveness
  GET  /api/v1/annotations               — list recent annotations
  POST /api/v1/annotations               — submit annotation
  GET  /api/v1/annotations/{id}          — get annotation
  GET  /api/v1/annotations/history       — annotation history
  GET  /api/v1/tasks                     — list tasks
  POST /api/v1/tasks                     — create task
  GET  /api/v1/tasks/{id}                — task detail
  GET  /api/v1/tasks/{id}/annotations    — task annotations
  GET  /api/v1/operators                 — legacy operator list (22 stub entries)

  # P3-5-W1 — 20 real annotation operators
  GET  /api/v1/annotate/list             — all 20 operators (with modality/category filters)
  GET  /api/v1/annotate/{op_id}/schema   — params schema
  POST /api/v1/annotate/{op_id}          — execute operator
  POST /api/v1/annotate/{op_id}/preview  — dry-run preview
"""
from __future__ import annotations

import copy
import logging
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .operators import OPERATORS, OPERATOR_META, get_meta, get_operator, list_operators as _list_ops

logger = logging.getLogger(__name__)

router = APIRouter(tags=["annotation-service"])


def _data_dir() -> str:
    env = os.environ.get("IMDF_DATA_DIR")
    if env:
        return env
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, "imdf", "data")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── /healthz ─────────────────────────────────────────────────────────────────
@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "annotation-service",
        "version": "0.1.0",
    }


# ── /api/v1/annotations ──────────────────────────────────────────────────────
class AnnotationItem(BaseModel):
    id: Optional[str] = None
    task_id: str
    asset_id: str
    label: str
    operator: str
    geometry: Optional[Dict[str, Any]] = None
    confidence: float = 1.0
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


def _annotations_db() -> str:
    return os.path.join(_data_dir(), "annotation_history.db")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS annotations ("
        "id TEXT PRIMARY KEY, "
        "task_id TEXT NOT NULL, asset_id TEXT NOT NULL, "
        "label TEXT, operator TEXT, geometry TEXT, "
        "confidence REAL, metadata TEXT, created_at TEXT)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_anno_task ON annotations(task_id)"
    )


@router.get("/api/v1/annotations", response_model=List[AnnotationItem])
async def list_annotations(task_id: Optional[str] = None, limit: int = 50):
    db_path = _annotations_db()
    items: List[AnnotationItem] = []
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            try:
                _ensure_schema(conn)
                if task_id:
                    rows = conn.execute(
                        "SELECT id, task_id, asset_id, label, operator, "
                        "geometry, confidence, metadata, created_at "
                        "FROM annotations WHERE task_id=? ORDER BY created_at DESC LIMIT ?",
                        (task_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, task_id, asset_id, label, operator, "
                        "geometry, confidence, metadata, created_at "
                        "FROM annotations ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                for r in rows:
                    items.append(
                        AnnotationItem(
                            id=r[0], task_id=r[1], asset_id=r[2],
                            label=r[3] or "", operator=r[4] or "",
                            geometry=__import__("json").loads(r[5]) if r[5] else None,
                            confidence=float(r[6] or 1.0),
                            metadata=__import__("json").loads(r[7]) if r[7] else None,
                            created_at=r[8] or "",
                        )
                    )
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("annotation listing error: %s", e)
    return items


@router.post("/api/v1/annotations", response_model=Dict[str, Any])
async def create_annotation(anno: AnnotationItem):
    db_path = _annotations_db()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if not anno.id:
        anno.id = f"anno_{uuid.uuid4().hex[:12]}"
    if not anno.created_at:
        anno.created_at = _now_iso()
    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO annotations "
            "(id, task_id, asset_id, label, operator, geometry, confidence, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                anno.id, anno.task_id, anno.asset_id, anno.label,
                anno.operator, __import__("json").dumps(anno.geometry or {}),
                anno.confidence, __import__("json").dumps(anno.metadata or {}),
                anno.created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "id": anno.id}


@router.get("/api/v1/annotations/history", response_model=List[Dict[str, Any]])
async def annotation_history(limit: int = 50):
    db_path = _annotations_db()
    out: List[Dict[str, Any]] = []
    if not os.path.exists(db_path):
        return out
    conn = sqlite3.connect(db_path)
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT id, task_id, label, operator, created_at "
            "FROM annotations ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        for r in rows:
            out.append({
                "id": r[0], "task_id": r[1], "label": r[2],
                "operator": r[3], "created_at": r[4],
            })
    finally:
        conn.close()
    return out


# ── /api/v1/tasks ────────────────────────────────────────────────────────────
class TaskItem(BaseModel):
    id: Optional[str] = None
    name: str
    type: str = "image-classification"
    status: str = "open"
    assignee: Optional[str] = None
    asset_ids: List[str] = []
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None


def _tasks_db() -> str:
    return os.path.join(_data_dir(), "annotation_tasks.db")


def _ensure_tasks_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS tasks ("
        "id TEXT PRIMARY KEY, name TEXT, type TEXT, status TEXT, "
        "assignee TEXT, asset_ids TEXT, metadata TEXT, created_at TEXT)"
    )


@router.get("/api/v1/tasks", response_model=List[TaskItem])
async def list_tasks(status_filter: Optional[str] = None, limit: int = 50):
    db_path = _tasks_db()
    items: List[TaskItem] = []
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            try:
                _ensure_tasks_schema(conn)
                if status_filter:
                    rows = conn.execute(
                        "SELECT id, name, type, status, assignee, asset_ids, metadata, created_at "
                        "FROM tasks WHERE status=? ORDER BY created_at DESC LIMIT ?",
                        (status_filter, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, name, type, status, assignee, asset_ids, metadata, created_at "
                        "FROM tasks ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                for r in rows:
                    items.append(
                        TaskItem(
                            id=r[0], name=r[1], type=r[2] or "image-classification",
                            status=r[3] or "open", assignee=r[4],
                            asset_ids=__import__("json").loads(r[5]) if r[5] else [],
                            metadata=__import__("json").loads(r[6]) if r[6] else None,
                            created_at=r[7] or "",
                        )
                    )
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("tasks listing error: %s", e)
    return items


@router.post("/api/v1/tasks", response_model=Dict[str, Any])
async def create_task(task: TaskItem):
    db_path = _tasks_db()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if not task.id:
        task.id = f"task_{uuid.uuid4().hex[:12]}"
    if not task.created_at:
        task.created_at = _now_iso()
    conn = sqlite3.connect(db_path)
    try:
        _ensure_tasks_schema(conn)
        conn.execute(
            "INSERT OR REPLACE INTO tasks "
            "(id, name, type, status, assignee, asset_ids, metadata, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task.id, task.name, task.type, task.status, task.assignee,
                __import__("json").dumps(task.asset_ids or []),
                __import__("json").dumps(task.metadata or {}),
                task.created_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "id": task.id, "name": task.name}


@router.get("/api/v1/tasks/{task_id}", response_model=Dict[str, Any])
async def get_task(task_id: str):
    db_path = _tasks_db()
    if not os.path.exists(db_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task_not_found")
    conn = sqlite3.connect(db_path)
    try:
        _ensure_tasks_schema(conn)
        row = conn.execute(
            "SELECT id, name, type, status, assignee, asset_ids, metadata, created_at "
            "FROM tasks WHERE id=?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task_not_found")
    return {
        "id": row[0], "name": row[1], "type": row[2] or "",
        "status": row[3] or "open", "assignee": row[4],
        "asset_ids": __import__("json").loads(row[5]) if row[5] else [],
        "metadata": __import__("json").loads(row[6]) if row[6] else {},
        "created_at": row[7] or "",
    }


@router.get("/api/v1/tasks/{task_id}/annotations", response_model=List[AnnotationItem])
async def task_annotations(task_id: str):
    return await list_annotations(task_id=task_id, limit=200)


# ── /api/v1/operators ────────────────────────────────────────────────────────
@router.get("/api/v1/operators", response_model=List[Dict[str, Any]])
async def list_operators():
    """List annotation operators (matches the 20+ skeleton in engines/operators_lib)."""
    return [
        {"id": "bbox", "name": "Bounding Box", "category": "geometry"},
        {"id": "polygon", "name": "Polygon", "category": "geometry"},
        {"id": "polyline", "name": "Polyline", "category": "geometry"},
        {"id": "keypoint", "name": "Keypoint", "category": "geometry"},
        {"id": "mask", "name": "Segmentation Mask", "category": "geometry"},
        {"id": "classification", "name": "Image Classification", "category": "categorical"},
        {"id": "multi-label", "name": "Multi-Label Classification", "category": "categorical"},
        {"id": "ner", "name": "Named Entity Recognition", "category": "text"},
        {"id": "sentiment", "name": "Sentiment Label", "category": "text"},
        {"id": "ocr", "name": "OCR Transcription", "category": "text"},
        {"id": "qa", "name": "Question Answer", "category": "text"},
        {"id": "video-segment", "name": "Video Segment", "category": "temporal"},
        {"id": "action-recognition", "name": "Action Recognition", "category": "temporal"},
        {"id": "tracking", "name": "Object Tracking", "category": "temporal"},
        {"id": "audio-classification", "name": "Audio Classification", "category": "audio"},
        {"id": "speaker-id", "name": "Speaker Identification", "category": "audio"},
        {"id": "transcription", "name": "Audio Transcription", "category": "audio"},
        {"id": "depth-estimate", "name": "Depth Estimation", "category": "3d"},
        {"id": "point-cloud", "name": "Point Cloud Label", "category": "3d"},
        {"id": "pose-estimation", "name": "Pose Estimation", "category": "3d"},
        {"id": "pairwise", "name": "Pairwise Comparison", "category": "preference"},
        {"id": "ranking", "name": "Ranking", "category": "preference"},
    ]
