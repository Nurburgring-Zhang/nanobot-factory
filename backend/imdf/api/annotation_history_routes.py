"""
标注历史路由
------------
- GET  /api/v1/annotations/history — 标注历史查询
- POST /api/v1/annotations/log    — 记录标注操作
"""

import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/annotations", tags=["annotations"])

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "annotation_history.db"
)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS annotation_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            dataset_id      TEXT NOT NULL,
            element_id      TEXT,
            action          TEXT NOT NULL,
            label           TEXT,
            labeler_id      TEXT DEFAULT 'system',
            confidence      REAL DEFAULT 1.0,
            metadata        TEXT DEFAULT '{}',
            created_at      TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_anno_dataset ON annotation_log(dataset_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_anno_created ON annotation_log(created_at)"
    )
    conn.commit()
    conn.close()


class LogAnnotationRequest(BaseModel):
    dataset_id: str = ""
    element_id: Optional[str] = None
    action: str = "label"
    label: Optional[str] = None
    labeler_id: str = "system"
    confidence: float = 1.0
    metadata: Dict[str, Any] = {}


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("/history")
async def get_annotation_history(
    dataset_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    labeler_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
):
    """查询标注历史"""
    conn = get_db()
    conditions = []
    params = []
    if dataset_id:
        conditions.append("dataset_id = ?")
        params.append(dataset_id)
    if action:
        conditions.append("action = ?")
        params.append(action)
    if labeler_id:
        conditions.append("labeler_id = ?")
        params.append(labeler_id)
    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM annotation_log{where_clause}", params
    ).fetchone()[0]

    offset = (page - 1) * size
    rows = conn.execute(
        f"SELECT * FROM annotation_log{where_clause} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [size, offset],
    ).fetchall()
    conn.close()

    items = []
    for row in rows:
        md = row["metadata"]
        try:
            md = json.loads(md) if isinstance(md, str) else md
        except (json.JSONDecodeError, TypeError):
            md = {}
        items.append({
            "id": row["id"],
            "dataset_id": row["dataset_id"],
            "element_id": row["element_id"],
            "action": row["action"],
            "label": row["label"],
            "labeler_id": row["labeler_id"],
            "confidence": row["confidence"],
            "metadata": md,
            "created_at": row["created_at"],
        })

    pages = max(1, (total + size - 1) // size)
    return {
        "success": True,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        },
        "message": "ok",
    }


@router.post("/log")
async def log_annotation(req: LogAnnotationRequest):
    """记录标注操作"""
    if not req.dataset_id:
        raise HTTPException(status_code=400, detail="dataset_id is required")
    if not req.action:
        raise HTTPException(status_code=400, detail="action is required")

    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO annotation_log (dataset_id, element_id, action, label, labeler_id, confidence, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            req.dataset_id,
            req.element_id,
            req.action,
            req.label,
            req.labeler_id,
            req.confidence,
            json.dumps(req.metadata),
            now,
        ),
    )
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()

    return {
        "success": True,
        "data": {
            "id": new_id,
            "dataset_id": req.dataset_id,
            "action": req.action,
            "created_at": now,
        },
        "message": "Annotation logged",
    }


# 初始化数据库
init_db()
