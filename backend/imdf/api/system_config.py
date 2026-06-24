"""
System Configuration Manager — 复刻 Penguin Canvas routes/settings.js
======================================================================
API Key设置、路径配置、RH工具节点管理(分类+应用)
"""
import os
import re
import json
import time
import uuid
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import logging

logger = logging.getLogger(__name__)

from config.global_config import (
    SETTINGS_FILE, DEFAULT_LOCAL_SAVE_DIR, DEFAULT_CANVAS_AUTO_SAVE_DIR,
    DEFAULT_RESOURCE_LIBRARY_DIR, DEFAULT_THEME_TEMPLATE_DIR,
    DEFAULT_EAGLE_API_BASE, DATA_ROOT,
)

router = APIRouter(prefix="/imdf/config", tags=["settings"])

# ─── 文件路径 ───────────────────────────────────────────────────────────────
RH_TOOL_CATEGORIES_FILE = str(DATA_ROOT / "settings" / "rh_tool_categories.json")
RH_TOOL_APPS_FILE = str(DATA_ROOT / "settings" / "rh_tool_apps.json")

# ─── 默认设置结构 ───────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "primaryApiKey": "",
    "primaryBaseUrl": "https://ai.t8star.org",
    "secondaryApiKey": "",
    "secondaryBaseUrl": "https://rh.t8star.org",
    "llmApiKey": "",
    "llmBaseUrl": "https://ai.t8star.org",

    # 分类 API Key (fallback -> primaryApiKey)
    "gptImageApiKey": "",
    "nanoBananaApiKey": "",
    "mjApiKey": "",
    "veoApiKey": "",
    "soraApiKey": "",
    "grokApiKey": "",
    "seedanceApiKey": "",
    "sunoApiKey": "",

    # 路径
    "fileSavePath": DEFAULT_LOCAL_SAVE_DIR,
    "canvasAutoSavePath": DEFAULT_CANVAS_AUTO_SAVE_DIR,
    "resourceLibraryPath": DEFAULT_RESOURCE_LIBRARY_DIR,
    "themeTemplatePath": DEFAULT_THEME_TEMPLATE_DIR,
    "eagleApiBase": DEFAULT_EAGLE_API_BASE,

    # 扩展平台 (空列表 = 默认禁用卡片)
    "providerExtensions": [],
    "cloudUploadTargets": [],

    "preferences": {
        "theme": "dark",
        "language": "zh-CN",
    },
}

CLASSIFIED_KEY_FIELDS = [
    "gptImageApiKey", "nanoBananaApiKey", "mjApiKey", "veoApiKey",
    "soraApiKey", "grokApiKey", "seedanceApiKey", "sunoApiKey",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Internal utilities
# ═══════════════════════════════════════════════════════════════════════════════

def _current_ms() -> int:
    return int(time.time() * 1000)


def _generate_id(prefix: str = "cfg") -> str:
    return f"{prefix}_{_current_ms()}_{uuid.uuid4().hex[:9]}"


def _sanitize_id(value: str, prefix: str) -> str:
    raw = re.sub(r'[^a-zA-Z0-9_-]', '', str(value or "").strip())[:96]
    return raw or _generate_id(prefix)


def _mask_key(k: str) -> str:
    return f"****{k[-4:]}" if k else ""


def _load_json(path: str, fallback=None):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Operation failed: {e}")
    return fallback if fallback is not None else []


def _save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# 设置读写
# ═══════════════════════════════════════════════════════════════════════════════

def load_settings() -> Dict:
    """加载设置，合并默认值"""
    data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Operation failed: {e}")
    merged = {**DEFAULT_SETTINGS, **data}
    # 强制 base URL
    merged["primaryBaseUrl"] = DEFAULT_SETTINGS["primaryBaseUrl"]
    merged["llmBaseUrl"] = DEFAULT_SETTINGS["llmBaseUrl"]
    # 规范化扩展平台
    merged["providerExtensions"] = merged.get("providerExtensions", [])
    merged["cloudUploadTargets"] = merged.get("cloudUploadTargets", [])
    return merged


def save_settings(settings: Dict):
    """保存设置"""
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# GET /imdf/config — 获取设置(脱敏)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("")
async def get_settings(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    s = load_settings()
    masked = {
        **s,
        "primaryApiKey": _mask_key(s.get("primaryApiKey", "")),
        "secondaryApiKey": _mask_key(s.get("secondaryApiKey", "")),
        "llmApiKey": _mask_key(s.get("llmApiKey", "")),
    }
    for f in CLASSIFIED_KEY_FIELDS:
        masked[f] = _mask_key(s.get(f, ""))
    return {
        "success": True,
        "data": masked,
        "limit": limit,
        "offset": offset,
    }


@router.get("/raw")
async def get_raw_settings(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """明文设置(内部使用)"""
    return {
        "success": True,
        "data": load_settings(),
        "limit": limit,
        "offset": offset,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PUT /imdf/config — 更新设置
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsUpdate(BaseModel):
    primaryApiKey: Optional[str] = None
    secondaryApiKey: Optional[str] = None
    llmApiKey: Optional[str] = None
    fileSavePath: Optional[str] = None
    canvasAutoSavePath: Optional[str] = None
    resourceLibraryPath: Optional[str] = None
    themeTemplatePath: Optional[str] = None
    providerExtensions: Optional[List[Any]] = None
    cloudUploadTargets: Optional[List[Any]] = None
    preferences: Optional[Dict] = None


@router.put("")
async def update_settings(req: SettingsUpdate):
    current = load_settings()
    incoming = req.dict(exclude_none=True)
    merged = {**current, **incoming}
    merged["primaryBaseUrl"] = DEFAULT_SETTINGS["primaryBaseUrl"]
    merged["llmBaseUrl"] = DEFAULT_SETTINGS["llmBaseUrl"]
    save_settings(merged)

    # 确保新路径存在
    for field in ("fileSavePath", "canvasAutoSavePath", "resourceLibraryPath", "themeTemplatePath"):
        val = incoming.get(field)
        if val and isinstance(val, str) and val.strip():
            try:
                os.makedirs(val.strip(), exist_ok=True)
            except Exception as e:
                logger.error(f"Operation failed: {e}")
    return {"success": True}


# ═══════════════════════════════════════════════════════════════════════════════
# RH 工具节点 — 分类管理
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/tool-categories")
async def list_tool_categories(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    data = _load_json(RH_TOOL_CATEGORIES_FILE, [])
    data.sort(key=lambda x: (x.get("order") or 0))
    if q:
        data = [c for c in data if q.lower() in (c.get("name", "") or "").lower()]
    total = len(data)
    page = data[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/tool-categories")
async def create_tool_category(req: "CategoryName"):
    name = str(getattr(req, "name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="分类名不能为空")
    items = _load_json(RH_TOOL_CATEGORIES_FILE, [])
    if any(c.get("name") == name for c in items):
        raise HTTPException(status_code=400, detail="分类名已存在")
    new_item = {"id": _generate_id("tcat"), "name": name, "order": len(items), "createdAt": _current_ms()}
    items.append(new_item)
    _save_json(RH_TOOL_CATEGORIES_FILE, items)
    return {"success": True, "data": new_item}


class CategoryName(BaseModel):
    name: str


class ReorderRequest(BaseModel):
    ids: List[str]


class ToolAppCreate(BaseModel):
    webapp_id: str = ""
    title: str = ""
    description: str = ""
    category_id: str = ""
    cover_url: str = ""


class ToolAppUpdate(BaseModel):
    webapp_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    cover_url: Optional[str] = None


@router.put("/tool-categories/{cat_id}")
async def update_tool_category(cat_id: str, req: CategoryName):
    name = str(req.name).strip()
    if not name:
        raise HTTPException(status_code=400, detail="分类名不能为空")
    items = _load_json(RH_TOOL_CATEGORIES_FILE, [])
    target = next((c for c in items if c.get("id") == cat_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="分类不存在")
    if any(c.get("id") != cat_id and c.get("name") == name for c in items):
        raise HTTPException(status_code=400, detail="分类名已存在")
    target["name"] = name
    _save_json(RH_TOOL_CATEGORIES_FILE, items)
    return {"success": True, "data": target}


@router.delete("/tool-categories/{cat_id}")
async def delete_tool_category(cat_id: str):
    items = _load_json(RH_TOOL_CATEGORIES_FILE, [])
    new_items = [c for c in items if c.get("id") != cat_id]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="分类不存在")
    _save_json(RH_TOOL_CATEGORIES_FILE, new_items)
    # 清空被删分类下的应用
    apps = _load_json(RH_TOOL_APPS_FILE, [])
    changed = False
    for a in apps:
        if a.get("categoryId") == cat_id:
            a["categoryId"] = ""
            changed = True
    if changed:
        _save_json(RH_TOOL_APPS_FILE, apps)
    return {"success": True}


@router.post("/tool-categories/reorder")
async def reorder_tool_categories(req: ReorderRequest):
    items = _load_json(RH_TOOL_CATEGORIES_FILE, [])
    idx_map = {cid: i for i, cid in enumerate(req.ids)}
    for item in items:
        if item["id"] in idx_map:
            item["order"] = idx_map[item["id"]]
        else:
            item["order"] = len(req.ids)
    items.sort(key=lambda x: x.get("order", 0))
    _save_json(RH_TOOL_CATEGORIES_FILE, items)
    return {"success": True, "data": items}


# ═══════════════════════════════════════════════════════════════════════════════
# RH 工具节点 — 应用管理
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/tool-apps")
async def list_tool_apps(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    data = _load_json(RH_TOOL_APPS_FILE, [])
    data.sort(key=lambda x: (x.get("order") or 0))
    if q:
        data = [a for a in data if q.lower() in (a.get("title", "") or "").lower() or q.lower() in (a.get("description", "") or "").lower()]
    total = len(data)
    page = data[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/tool-apps")
async def create_tool_app(req: ToolAppCreate):
    if not req.webapp_id or not req.title:
        raise HTTPException(status_code=400, detail="缺少必要参数 (webapp_id / title)")
    items = _load_json(RH_TOOL_APPS_FILE, [])
    new_app = {
        "id": _generate_id("tapp"),
        "webappId": req.webapp_id.strip(),
        "title": req.title.strip(),
        "description": req.description or "",
        "categoryId": req.category_id or "",
        "coverUrl": req.cover_url or "",
        "order": len(items),
        "addedAt": _current_ms(),
    }
    items.append(new_app)
    _save_json(RH_TOOL_APPS_FILE, items)
    return {"success": True, "data": new_app}


@router.put("/tool-apps/{app_id}")
async def update_tool_app(app_id: str, req: ToolAppUpdate):
    items = _load_json(RH_TOOL_APPS_FILE, [])
    app = next((a for a in items if a.get("id") == app_id), None)
    if not app:
        raise HTTPException(status_code=404, detail="应用不存在")
    if req.webapp_id is not None:
        app["webappId"] = req.webapp_id.strip()
    if req.title is not None:
        app["title"] = req.title.strip()
    if req.description is not None:
        app["description"] = req.description
    if req.category_id is not None:
        app["categoryId"] = req.category_id
    if req.cover_url is not None:
        app["coverUrl"] = req.cover_url
    _save_json(RH_TOOL_APPS_FILE, items)
    return {"success": True, "data": app}


@router.delete("/tool-apps/{app_id}")
async def delete_tool_app(app_id: str):
    items = _load_json(RH_TOOL_APPS_FILE, [])
    new_items = [a for a in items if a.get("id") != app_id]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="应用不存在")
    _save_json(RH_TOOL_APPS_FILE, new_items)
    return {"success": True}


@router.post("/tool-apps/reorder")
async def reorder_tool_apps(req: ReorderRequest):
    items = _load_json(RH_TOOL_APPS_FILE, [])
    idx_map = {aid: i for i, aid in enumerate(req.ids)}
    for item in items:
        if item["id"] in idx_map:
            item["order"] = idx_map[item["id"]]
        else:
            item["order"] = len(req.ids)
    items.sort(key=lambda x: x.get("order", 0))
    _save_json(RH_TOOL_APPS_FILE, items)
    return {"success": True, "data": items}


# ═══════════════════════════════════════════════════════════════════════════════
# RH 超市导出/导入
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/tools/export")
async def export_tools(
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    cats = _load_json(RH_TOOL_CATEGORIES_FILE, [])
    cats.sort(key=lambda x: (x.get("order") or 0))
    apps = _load_json(RH_TOOL_APPS_FILE, [])
    apps.sort(key=lambda x: (x.get("order") or 0))
    if q:
        cats = [c for c in cats if q.lower() in (c.get("name", "") or "").lower()]
        apps = [a for a in apps if q.lower() in (a.get("title", "") or "").lower()]
    return {
        "success": True,
        "data": {
            "schema": "imdf-rh-tools",
            "version": 1,
            "exportedAt": __import__("datetime").datetime.now().isoformat(),
            "categories": cats[offset: offset + limit],
            "tools": apps[offset: offset + limit],
        },
        "total_categories": len(cats),
        "total_tools": len(apps),
        "limit": limit,
        "offset": offset,
    }


class ToolsImport(BaseModel):
    categories: List[Dict] = []
    tools: List[Dict] = []
    mode: str = "replace"


@router.post("/tools/import")
async def import_tools(req: ToolsImport):
    normalized = _normalize_rh_tools_backup(req.dict())
    cats, apps = normalized["categories"], normalized["tools"]

    if req.mode == "merge":
        existing_cats = _load_json(RH_TOOL_CATEGORIES_FILE, [])
        existing_apps = _load_json(RH_TOOL_APPS_FILE, [])
        cat_by_name = {c["name"]: c for c in existing_cats}
        merged_cats = list(existing_cats)
        cat_id_map = {}
        for c in cats:
            if c["name"] in cat_by_name:
                cat_id_map[c["id"]] = cat_by_name[c["name"]]["id"]
            else:
                c["order"] = len(merged_cats)
                merged_cats.append(c)
                cat_id_map[c["id"]] = c["id"]
        app_by_webapp = {a["webappId"]: a for a in existing_apps}
        merged_apps = list(existing_apps)
        for a in apps:
            a["categoryId"] = cat_id_map.get(a.get("categoryId", ""), "")
            if a["webappId"] in app_by_webapp:
                existing = app_by_webapp[a["webappId"]]
                existing.update({k: v for k, v in a.items() if k != "id"})
                existing["id"] = a["id"]
            else:
                a["order"] = len(merged_apps)
                merged_apps.append(a)
        cats = [dict(c, order=idx) for idx, c in enumerate(merged_cats)]
        apps = [dict(a, order=idx) for idx, a in enumerate(merged_apps)]

    _save_json(RH_TOOL_CATEGORIES_FILE, cats)
    _save_json(RH_TOOL_APPS_FILE, apps)
    return {
        "success": True,
        "data": {
            "categories": cats, "tools": apps,
            "categoryCount": len(cats), "toolCount": len(apps),
        },
    }


def _normalize_rh_tools_backup(payload: Dict) -> Dict:
    raw_cats = payload.get("categories", []) or []
    raw_tools = payload.get("tools", []) or []
    used_cat_ids = set()
    categories = []
    for idx, c in enumerate(raw_cats):
        name = str(c.get("name", "")).strip()
        if not name:
            continue
        cid = _sanitize_id(c.get("id"), "tcat")
        while cid in used_cat_ids:
            cid = _generate_id("tcat")
        used_cat_ids.add(cid)
        categories.append({
            "id": cid, "name": name[:80],
            "order": int(c.get("order", idx)),
            "createdAt": int(c.get("createdAt", _current_ms())),
        })
    cat_ids = {c["id"] for c in categories}
    used_tool_ids = set()
    tools = []
    for idx, t in enumerate(raw_tools):
        webapp_id = str(t.get("webappId", "")).strip()
        title = str(t.get("title", "")).strip()
        if not webapp_id or not title:
            continue
        tid = _sanitize_id(t.get("id"), "tapp")
        while tid in used_tool_ids:
            tid = _generate_id("tapp")
        used_tool_ids.add(tid)
        tools.append({
            "id": tid, "webappId": webapp_id[:120],
            "title": title[:120],
            "description": str(t.get("description", ""))[:2000],
            "categoryId": str(t.get("categoryId", "")) if str(t.get("categoryId", "")) in cat_ids else "",
            "coverUrl": str(t.get("coverUrl", ""))[:2000],
            "order": int(t.get("order", idx)),
            "addedAt": int(t.get("addedAt", _current_ms())),
        })
    categories.sort(key=lambda x: x.get("order", 0))
    tools.sort(key=lambda x: x.get("order", 0))
    return {"categories": categories, "tools": tools}
