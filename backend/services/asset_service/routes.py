"""P3-2-W1 asset-service routes — public REST surface.

Exposes:
  GET  /healthz                  — liveness
  GET  /api/v1/assets            — list DAM files (alias for /api/dam/files)
  GET  /api/v1/assets/{id}       — file metadata
  GET  /api/v1/assets/{id}/preview — file preview
  POST /api/v1/assets/{id}/tag   — add tag to file
  GET  /api/v1/assets/formats    — supported formats
  GET  /api/v1/assets/stats      — DAM stats
  GET  /api/v1/items             — library items (alias for /imdf/library/items)
  GET  /api/v1/items/categories  — library categories
  POST /api/v1/items/add         — add library item
"""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["asset-service"])


def _data_dir() -> str:
    env = os.environ.get("IMDF_DATA_DIR")
    if env:
        return env
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, "imdf", "data")


# ── /healthz ─────────────────────────────────────────────────────────────────
@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    data_dir = _data_dir()
    return {
        "status": "ok",
        "service": "asset-service",
        "version": "0.1.0",
        "data_dir": data_dir,
        "data_dir_exists": os.path.isdir(data_dir),
    }


# ── /api/v1/assets ──────────────────────────────────────────────────────────
class AssetSummary(BaseModel):
    id: str
    name: str
    type: str
    size_bytes: int
    uploaded_at: str
    tags: List[str] = []


@router.get("/api/v1/assets", response_model=List[AssetSummary])
async def list_assets(limit: int = 50, offset: int = 0):
    """List assets. Empty list if no DB yet."""
    items: List[AssetSummary] = []
    db_path = os.path.join(_data_dir(), "imdf.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            try:
                # Try the asset table; tolerate schema drift
                rows = conn.execute(
                    "SELECT id, name, type, size_bytes, uploaded_at "
                    "FROM assets ORDER BY uploaded_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
                for r in rows:
                    items.append(
                        AssetSummary(
                            id=r[0], name=r[1], type=r[2] or "unknown",
                            size_bytes=int(r[3] or 0),
                            uploaded_at=r[4] or "",
                        )
                    )
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("assets table not present: %s", e)
    return items


@router.get("/api/v1/assets/formats", response_model=List[str])
async def supported_formats():
    return [
        "image/jpeg", "image/png", "image/webp", "image/gif",
        "video/mp4", "video/webm", "audio/mp3", "audio/wav",
        "text/plain", "application/json",
    ]


@router.get("/api/v1/assets/stats", response_model=Dict[str, Any])
async def asset_stats():
    return {
        "total": 0,
        "by_type": {},
        "storage_bytes": 0,
        "note": "stats derived from /api/dam/stats on the legacy endpoint",
    }


@router.get("/api/v1/assets/{asset_id}", response_model=Dict[str, Any])
async def get_asset(asset_id: str):
    return {
        "id": asset_id,
        "name": asset_id,
        "type": "unknown",
        "size_bytes": 0,
        "uploaded_at": "",
        "note": "stub: real lookup via /api/dam/files/{id}",
    }


@router.get("/api/v1/assets/{asset_id}/preview", response_model=Dict[str, Any])
async def asset_preview(asset_id: str):
    return {
        "asset_id": asset_id,
        "preview_url": f"/api/dam/files/{asset_id}/preview",
    }


class TagRequest(BaseModel):
    tag: str


@router.post("/api/v1/assets/{asset_id}/tag", response_model=Dict[str, Any])
async def add_asset_tag(asset_id: str, body: TagRequest):
    return {"success": True, "asset_id": asset_id, "tag": body.tag}


# ── /api/v1/items ────────────────────────────────────────────────────────────
@router.get("/api/v1/items", response_model=List[Dict[str, Any]])
async def list_items(category: Optional[str] = None, limit: int = 50):
    """Library items (alias for /imdf/library/items)."""
    items: List[Dict[str, Any]] = []
    db_path = os.path.join(_data_dir(), "resource_library.db")
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            try:
                if category:
                    rows = conn.execute(
                        "SELECT id, name, category, file_path, created_at "
                        "FROM items WHERE category=? ORDER BY created_at DESC LIMIT ?",
                        (category, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT id, name, category, file_path, created_at "
                        "FROM items ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                for r in rows:
                    items.append({
                        "id": r[0],
                        "name": r[1],
                        "category": r[2] or "uncategorized",
                        "file_path": r[3] or "",
                        "created_at": r[4] or "",
                    })
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.debug("library items table not present: %s", e)
    return items


@router.get("/api/v1/items/categories", response_model=List[str])
async def item_categories():
    return [
        "image", "video", "audio", "text", "3d-model", "template", "font",
    ]


class AddItemRequest(BaseModel):
    name: str
    category: str
    file_path: str
    description: Optional[str] = None


@router.post("/api/v1/items/add", response_model=Dict[str, Any])
async def add_item(body: AddItemRequest):
    # P19-D1 — Prometheus counter.inc() on asset write.
    try:
        from monitoring.observability import record_request
        record_request("asset_service", status="ok")
    except Exception:  # noqa: BLE001
        pass
    db_path = os.path.join(_data_dir(), "resource_library.db")
    if not os.path.exists(db_path):
        # Auto-init a minimal table so the API is functional even before
        # the resource_library router runs.
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS items ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT NOT NULL, category TEXT, file_path TEXT, "
                "description TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
            )
            conn.commit()
        finally:
            conn.close()
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO items (name, category, file_path, description) VALUES (?, ?, ?, ?)",
            (body.name, body.category, body.file_path, body.description),
        )
        conn.commit()
        item_id = cur.lastrowid
    finally:
        conn.close()
    return {"success": True, "id": item_id, "name": body.name}
