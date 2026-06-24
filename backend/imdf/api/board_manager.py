"""
Canvas Data Manager — Port of Penguin Canvas routes/canvas.js
===========================================================
Canvas CRUD: list/create/read/update/auto-save/delete/rename
"""
import os
import re
import json
import time
import uuid
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import logging

logger = logging.getLogger(__name__)

# R2-3: 路径 ID 校验 — 防 SQL 注入 / path traversal / 超长输入
from api._common.validators import validate_id

from config.platform_config import (
    get_data_dir, get_canvas_list_file, get_settings_file,
    get_default_canvas_auto_save_dir,
)

DATA_DIR = get_data_dir()
CANVAS_FILE = get_canvas_list_file()
SETTINGS_FILE = get_settings_file()
DEFAULT_CANVAS_AUTO_SAVE_DIR = get_default_canvas_auto_save_dir()

router = APIRouter(prefix="/imdf/canvas", tags=["canvas"])


# ═══════════════════════════════════════════════════════════════════════════════
# Internal utilities
# ═══════════════════════════════════════════════════════════════════════════════

def _now_ms() -> int:
    return int(time.time() * 1000)


def _read_json(path: str):
    """Read and clean BOM/NUL characters"""
    with open(path, "r", encoding="utf-8-sig") as f:
        content = f.read().replace("\0", "")
    return json.loads(content)


def _canvas_id_from_ts(ts_str: str) -> int:
    m = re.match(r"^board-(\d+)-", str(ts_str or ""))
    if m:
        parsed = int(m.group(1))
        return parsed if parsed > 0 else 0
    return 0


def _safe_filename(value: str, fallback: str = "board") -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', "_", str(value or fallback))
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned[:80] or fallback


def _atomic_write(path: str, data):
    """Atomic JSON write"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _load_settings() -> Dict:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Operation failed: {e}")
    return {}


def _get_auto_save_dir() -> str:
    s = _load_settings()
    base = (s.get("canvasAutoSavePath") or DEFAULT_CANVAS_AUTO_SAVE_DIR or "").strip()
    if not base:
        return ""
    return os.path.join(base, "IMDF-canvas", "boards")


def _recover_list_from_files() -> List[Dict]:
    """从单画布文件恢复列表"""
    if not os.path.exists(DATA_DIR):
        return []
    items = []
    pattern = re.compile(r"^board_board-[\w-]+\.json$")
    for fname in os.listdir(DATA_DIR):
        fpath = os.path.join(DATA_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        if not pattern.match(fname):
            continue
        board_id = fname.replace("board_", "").replace(".json", "")
        try:
            data = _read_json(fpath)
            if not isinstance(data.get("nodes"), list) or not isinstance(data.get("edges"), list):
                continue
            stat = os.stat(fpath)
            updated = max(1, int(stat.st_mtime * 1000))
            items.append({
                "id": board_id,
                "name": board_id,
                "nodeCount": len(data["nodes"]),
                "createdAt": _canvas_id_from_ts(board_id) or updated,
                "updatedAt": updated,
            })
        except Exception as e:
            logger.error(f"Operation failed: {e}")
    items.sort(key=lambda x: x["createdAt"])
    return items


def _load_list() -> List[Dict]:
    if not os.path.exists(CANVAS_FILE):
        return _recover_list_from_files()
    try:
        data = _read_json(CANVAS_FILE)
        return data if isinstance(data, list) else _recover_list_from_files()
    except Exception:
        return _recover_list_from_files()


def _save_list(lst: List[Dict]):
    _atomic_write(CANVAS_FILE, lst)


def _board_file(board_id: str) -> str:
    return os.path.join(DATA_DIR, f"board_{board_id}.json")


def _parse_serial_id(value) -> int:
    raw = str(value or "").strip().lstrip("#").strip()
    if not raw.isdigit():
        return 0
    parsed = int(raw)
    return parsed if parsed > 0 else 0


def _derive_next_serial(nodes: List[Dict], incoming_next) -> int:
    requested = _parse_serial_id(incoming_next)
    max_serial = 0
    for node in (nodes or []):
        max_serial = max(max_serial, _parse_serial_id(node.get("data", {}).get("nodeSerialId")))
    return max(1, requested or 1, max_serial + 1)


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════════════════════

class CanvasCreate(BaseModel):
    name: str = "未命名画布"


class CanvasUpdate(BaseModel):
    nodes: List[Dict] = []
    edges: List[Dict] = []
    viewport: Dict = {"x": 0, "y": 0, "zoom": 1}
    nextNodeSerialId: Optional[int] = None
    allowEmpty: bool = False


class AutoSaveRequest(BaseModel):
    nodes: List[Dict] = []
    edges: List[Dict] = []
    viewport: Dict = {"x": 0, "y": 0, "zoom": 1}
    nextNodeSerialId: Optional[int] = None


class RenameRequest(BaseModel):
    name: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def list_boards():
    """获取画布列表"""
    return {"success": True, "data": _load_list()}


@router.post("")
async def create_board(req: CanvasCreate):
    """创建新画布"""
    lst = _load_list()
    board_id = f"board-{_now_ms()}-{uuid.uuid4().hex[:6]}"
    now = _now_ms()
    entry = {"id": board_id, "name": req.name, "nodeCount": 0, "createdAt": now, "updatedAt": now}
    lst.append(entry)
    _save_list(lst)
    _atomic_write(_board_file(board_id), {
        "nodes": [], "edges": [], "viewport": {"x": 0, "y": 0, "zoom": 1}, "nextNodeSerialId": 1,
    })
    return {"success": True, "data": entry}


@router.get("/{board_id}")
async def get_board(board_id: str):
    """获取单个画布数据"""
    fpath = _board_file(board_id)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="画布不存在")
    try:
        data = _read_json(fpath)
        return {"success": True, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取失败: {e}")


@router.put("/{board_id}")
async def update_board(board_id: str, req: CanvasUpdate):
    """更新画布数据(防空数据覆盖)"""
    validate_id(board_id, "board_id")
    fpath = _board_file(board_id)
    allow_empty = req.allowEmpty

    # 防空数据覆盖
    if not req.nodes and not allow_empty and os.path.exists(fpath):
        try:
            existing = _read_json(fpath)
            if existing.get("nodes") and len(existing["nodes"]) > 0:
                raise HTTPException(status_code=400, detail="拒绝空数据覆盖")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Operation failed: {e}")

    persisted = {
        "nodes": req.nodes or [],
        "edges": req.edges or [],
        "viewport": req.viewport or {"x": 0, "y": 0, "zoom": 1},
        "nextNodeSerialId": _derive_next_serial(req.nodes, req.nextNodeSerialId),
    }
    _atomic_write(fpath, persisted)

    lst = _load_list()
    entry = next((x for x in lst if x["id"] == board_id), None)
    if entry:
        entry["nodeCount"] = len(persisted["nodes"])
        entry["updatedAt"] = _now_ms()
        _save_list(lst)
    return {"success": True}


@router.post("/{board_id}/auto-save")
async def auto_save_board(board_id: str, req: AutoSaveRequest):
    """镜像保存到用户配置的本地目录"""
    validate_id(board_id, "board_id")
    save_dir = _get_auto_save_dir()
    if not save_dir:
        raise HTTPException(status_code=400, detail="未配置 canvasAutoSavePath")

    lst = _load_list()
    entry = next((x for x in lst if x["id"] == board_id), None)
    name = entry["name"] if entry else board_id
    short_id = board_id.replace("board-", "")[:24]
    fname = f"{_safe_filename(name)}-{_safe_filename(short_id)}.json"
    target = os.path.join(save_dir, fname)
    now = _now_ms()
    payload = {
        "schema": "imdf-canvas-autosave",
        "version": 1,
        "autoSavedAt": __import__("datetime").datetime.now().isoformat(),
        "canvas": {
            "id": board_id, "name": name,
            "nodeCount": len(req.nodes), "edgeCount": len(req.edges),
            "createdAt": entry.get("createdAt") if entry else None,
            "updatedAt": entry.get("updatedAt") if entry else now,
        },
        "nodes": req.nodes,
        "edges": req.edges,
        "viewport": req.viewport or {"x": 0, "y": 0, "zoom": 1},
        "nextNodeSerialId": _derive_next_serial(req.nodes, req.nextNodeSerialId),
    }
    _atomic_write(target, payload)
    return {
        "success": True,
        "data": {"path": target, "nodeCount": len(req.nodes), "edgeCount": len(req.edges)},
    }


@router.delete("/{board_id}")
async def delete_board(board_id: str):
    """删除画布"""
    validate_id(board_id, "board_id")
    lst = _load_list()
    lst = [x for x in lst if x["id"] != board_id]
    _save_list(lst)
    fpath = _board_file(board_id)
    if os.path.exists(fpath):
        os.remove(fpath)
    return {"success": True}


@router.patch("/{board_id}/name")
async def rename_board(board_id: str, req: RenameRequest):
    """重命名画布"""
    validate_id(board_id, "board_id")
    lst = _load_list()
    entry = next((x for x in lst if x["id"] == board_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="画布不存在")
    entry["name"] = req.name or entry["name"]
    entry["updatedAt"] = _now_ms()
    _save_list(lst)
    return {"success": True, "data": entry}
