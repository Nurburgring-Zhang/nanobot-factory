"""
Resource Library Manager — 复刻 Penguin Canvas routes/resources.js
===================================================================
资源库管理: 分类 CRUD、素材 CRUD、素材集、姿势大师、工作流
"""
import os
import re
import json
import hashlib
import time
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Set, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field

import logging

logger = logging.getLogger(__name__)

from config.global_config import (
    DEFAULT_RESOURCE_LIBRARY_DIR, SETTINGS_FILE,
    OUTPUT_DIR, INPUT_DIR, RESOURCE_LIBRARY_DB,
    MIME_BY_EXT,
)

router = APIRouter(prefix="/imdf/library", tags=["resource_library"])

# ─── 常量 ───────────────────────────────────────────────────────────────────
KINDS = frozenset(["image", "video", "audio", "panorama", "set", "pose", "workflow"])
ADDABLE_KINDS = frozenset(["image", "video", "audio", "panorama"])
SET_ITEM_KINDS = frozenset(["text", "image", "video", "audio"])
THUMB_DIR = "_thumbs"
REMOTE_FETCH_TIMEOUT = 30
REMOTE_MAX_BYTES = 512 * 1024 * 1024

DEFAULT_CATEGORY_NAMES = {
    "image": ["未分类", "角色", "场景", "风格参考", "成品"],
    "video": ["未分类", "镜头", "动作", "成片"],
    "audio": ["未分类", "音乐", "人声", "音效"],
    "panorama": ["未分类", "室内", "室外", "自然", "城市", "奇幻"],
    "set": ["未分类", "图像集", "视频集", "音频集", "文本集"],
    "pose": ["未分类", "常用姿势", "动作参考", "分镜姿势"],
    "workflow": ["未分类", "常用工作流", "图像流程", "视频流程", "工具链"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════════════════════

class CategoryCreate(BaseModel):
    kind: str
    name: str

class CategoryUpdate(BaseModel):
    name: str

class ItemUpdate(BaseModel):
    title: Optional[str] = None
    favorite: Optional[bool] = None
    tags: Optional[List[str]] = None
    category_id: Optional[str] = None
    touch: bool = False

class ItemAdd(BaseModel):
    url: str = ""
    kind: Optional[str] = None
    title: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[List[str]] = None
    favorite: bool = False
    source_node_id: Optional[str] = None
    source_canvas_id: Optional[str] = None

class SetAdd(BaseModel):
    material_set_kind: str = ""
    material_set_items: List[Dict[str, Any]] = []
    title: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[List[str]] = None
    favorite: bool = False
    source_node_id: Optional[str] = None
    source_canvas_id: Optional[str] = None

class PoseAdd(BaseModel):
    pose_backup: Dict[str, Any] = {}
    title: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[List[str]] = None
    favorite: bool = False

class WorkflowAdd(BaseModel):
    workflow_fragment: Dict[str, Any] = {}
    title: Optional[str] = None
    category_id: Optional[str] = None
    tags: Optional[List[str]] = None
    favorite: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# 内部数据层
# ═══════════════════════════════════════════════════════════════════════════════

def _current_ms() -> int:
    return int(time.time() * 1000)


def _generate_id(prefix: str = "lib") -> str:
    return f"{prefix}_{_current_ms()}_{uuid.uuid4().hex[:8]}"


def _sanitize_text(value, fallback="", maxlen=200) -> str:
    return str(value or fallback).strip()[:maxlen]


def _sanitize_filename(value, fallback="asset") -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]', '_', str(value or fallback))
    cleaned = re.sub(r'\s+', '_', cleaned)
    cleaned = re.sub(r'_+', '_', cleaned)
    return cleaned[:120] or fallback


def _normalize_kind(kind: str) -> str:
    k = str(kind or "").lower().strip()
    return k if k in KINDS else ""


def _normalize_set_item_kind(kind: str) -> str:
    k = str(kind or "").lower().strip()
    return k if k in SET_ITEM_KINDS else ""


def _mime_from_ext(ext: str) -> str:
    return MIME_BY_EXT.get(ext.lower().lstrip("."), "application/octet-stream")


def _ext_from_mime(mime: str) -> str:
    m = str(mime or "").lower().split(";")[0].strip()
    for ext, mt in MIME_BY_EXT.items():
        if mt == m:
            return ext.lstrip(".") if ext != ".jpeg" else "jpg"
    return ""


def _kind_from_ext(ext: str) -> str:
    e = ext.lower().lstrip(".")
    if e in ("png", "jpg", "jpeg", "webp", "gif", "bmp", "avif"):
        return "image"
    if e in ("mp4", "webm", "mov", "m4v", "mkv", "avi"):
        return "video"
    if e in ("mp3", "wav", "ogg", "m4a", "flac", "aac"):
        return "audio"
    return ""


def _resolve_library_root() -> str:
    root = ""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                s = json.load(f)
            root = str(s.get("resourceLibraryPath", "")).strip()
        except Exception as e:
            logger.error(f"Operation failed: {e}")
    if not root:
        root = DEFAULT_RESOURCE_LIBRARY_DIR
    os.makedirs(root, exist_ok=True)
    for k in KINDS:
        os.makedirs(os.path.join(root, k), exist_ok=True)
    os.makedirs(os.path.join(root, THUMB_DIR), exist_ok=True)
    return root


def _default_categories() -> List[Dict]:
    out = []
    for kind, names in DEFAULT_CATEGORY_NAMES.items():
        for idx, name in enumerate(names):
            out.append({
                "id": f"{kind}_uncategorized" if idx == 0 else f"{kind}_{idx}_{name}",
                "kind": kind, "name": name, "order": idx,
                "system": idx == 0, "createdAt": 0,
            })
    return out


def _normalize_db(raw: Optional[Dict]) -> Dict:
    db = raw if raw and isinstance(raw, dict) else {}
    defaults = _default_categories()
    raw_cats = db.get("categories", []) if isinstance(db.get("categories"), list) else []
    raw_items = db.get("items", []) if isinstance(db.get("items"), list) else []

    cat_map = {}
    for c in defaults + raw_cats:
        kind = _normalize_kind(c.get("kind"))
        name = _sanitize_text(c.get("name"))
        if not kind or not name:
            continue
        cid = str(c.get("id", _generate_id("libcat")))[:96]
        if cid in cat_map:
            continue
        cat_map[cid] = {
            "id": cid, "kind": kind, "name": name,
            "order": int(c.get("order", len(cat_map))),
            "system": bool(c.get("system", cid.endswith("_uncategorized"))),
            "createdAt": int(c.get("createdAt", _current_ms())),
        }

    categories = sorted(cat_map.values(), key=lambda x: (x["kind"], x["order"]))
    cat_kind_map = {c["id"]: c["kind"] for c in categories}

    # 兼容旧版 panorama 分类
    legacy_pano_ids = set()
    for c in categories:
        n = c["name"].strip().lower().replace(" ", "")
        if c["kind"] == "image" and n in ("3d全景", "全景", "vr全景", "720全景"):
            legacy_pano_ids.add(c["id"])

    items = []
    seen = set()
    for item in raw_items:
        kind = _normalize_kind(item.get("kind"))
        if kind == "image":
            # 检查是否应归入 panorama
            cid = str(item.get("categoryId", ""))
            title = str(item.get("title", "")).lower()
            tags = [str(t).lower().replace(" ", "") for t in (item.get("tags") or [])]
            if cid in legacy_pano_ids or any(kw in title for kw in ("3d全景", "全景贴图", "720vr", "panorama")) or \
               any(t in ("3d全景", "全景", "panorama", "vr", "720vr") for t in tags):
                kind = "panorama"
        if not kind:
            continue
        item_id = str(item.get("id", _generate_id("lib")))[:96]
        if item_id in seen:
            continue
        seen.add(item_id)
        file_rel = str(item.get("fileRel", "")).strip()
        if not file_rel:
            continue

        material_set_kind = ""
        material_set_items = []
        if kind == "set":
            material_set_kind = _normalize_set_item_kind(item.get("materialSetKind"))
            material_set_items = _normalize_set_items(item.get("materialSetItems", []), material_set_kind)
            if not material_set_kind or not material_set_items:
                continue

        fallback_cat = f"{kind}_uncategorized"
        req_cat = str(item.get("categoryId", ""))
        cat_id = req_cat if cat_kind_map.get(req_cat) == kind else fallback_cat

        items.append({
            "id": item_id, "kind": kind, "categoryId": cat_id,
            "title": _sanitize_text(item.get("title"), item.get("originalName") or item_id, 200),
            "originalName": _sanitize_text(item.get("originalName"), ""),
            "fileRel": file_rel,
            "thumbRel": _sanitize_text(item.get("thumbRel"), ""),
            "mime": _sanitize_text(item.get("mime"), _mime_from_ext(os.path.splitext(file_rel)[1])),
            "size": int(item.get("size", 0)),
            "sha256": str(item.get("sha256", "")),
            "tags": [str(t)[:80] for t in (item.get("tags") or []) if str(t).strip()][:20],
            "favorite": bool(item.get("favorite")),
            "sourceUrl": str(item.get("sourceUrl", "")),
            "sourceNodeId": str(item.get("sourceNodeId", "")),
            "sourceCanvasId": str(item.get("sourceCanvasId", "")),
            "materialSetKind": material_set_kind,
            "materialSetItems": material_set_items,
            "workflowNodeCount": int(item.get("workflowNodeCount", 0) or item.get("nodeCount", 0)) if kind == "workflow" else 0,
            "workflowEdgeCount": int(item.get("workflowEdgeCount", 0) or item.get("edgeCount", 0)) if kind == "workflow" else 0,
            "workflowNodeTypes": (item.get("workflowNodeTypes") or [])[:24] if kind == "workflow" else [],
            "workflowPreview": item.get("workflowPreview") if kind == "workflow" else None,
            "createdAt": int(item.get("createdAt", _current_ms())),
            "updatedAt": int(item.get("updatedAt", item.get("createdAt", _current_ms()))),
            "lastUsedAt": int(item.get("lastUsedAt", 0)),
        })

    # 清理孤立旧版全景分类
    used_cat_ids = {it["categoryId"] for it in items}
    final_cats = [c for c in categories if not (c["kind"] == "image" and c["id"] in legacy_pano_ids and c["id"] not in used_cat_ids)]

    return {
        "schema": "imdf-resource-library",
        "version": 1,
        "updatedAt": str(db.get("updatedAt", "")),
        "categories": final_cats,
        "items": items,
    }


def _normalize_set_items(raw, fallback_kind: str) -> List[Dict]:
    kind = _normalize_set_item_kind(fallback_kind)
    if not kind or not isinstance(raw, list):
        return []
    result = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        item_kind = _normalize_set_item_kind(item.get("kind")) or kind
        if item_kind != kind:
            continue
        if kind == "text":
            text = str(item.get("text") or item.get("url") or "")
            if not text:
                continue
            result.append({
                "id": str(item.get("id", f"set_item_{idx+1}"))[:96],
                "kind": kind, "text": text,
                "name": str(item.get("name", text[:24])),
                "size": int(item.get("size", 0)),
                "mime": str(item.get("mime", "text/plain")),
            })
        else:
            url = str(item.get("url") or item.get("fileRel") or "")
            file_rel = str(item.get("fileRel") or "")
            if not url and not file_rel:
                continue
            result.append({
                "id": str(item.get("id", f"set_item_{idx+1}"))[:96],
                "kind": kind, "fileRel": file_rel or url,
                "url": url or file_rel,
                "name": str(item.get("name", os.path.basename(file_rel or url))),
                "size": int(item.get("size", 0)),
                "mime": str(item.get("mime", _mime_from_ext(os.path.splitext(file_rel or url)[1]))),
            })
    return result[:500]


def _read_db() -> Tuple[str, Dict]:
    root = _resolve_library_root()
    db_path = os.path.join(root, RESOURCE_LIBRARY_DB)
    raw = None
    try:
        if os.path.exists(db_path):
            with open(db_path, "r") as f:
                raw = json.load(f)
    except Exception:
        raw = None
    db = _normalize_db(raw)
    # 自动保存规范化后的数据
    if raw is None or json.dumps(raw, sort_keys=True) != json.dumps(db, sort_keys=True):
        _write_db(root, db)
    return root, db


def _write_db(root: str, db: Dict):
    db["updatedAt"] = __import__("datetime").datetime.now().isoformat()
    db_path = os.path.join(root, RESOURCE_LIBRARY_DB)
    tmp = db_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    os.replace(tmp, db_path)


def _assert_inside(root: str, target: str) -> str:
    r = os.path.realpath(root)
    t = os.path.realpath(target)
    if t != r and not t.startswith(r + os.sep):
        raise ValueError("非法资源路径")
    return t


def _is_private_ip(host: str) -> bool:
    import ipaddress
    try:
        addr = ipaddress.ip_address(host)
        return addr.is_private or addr.is_loopback or addr.is_unspecified
    except ValueError:
        return False


async def _fetch_remote(url: str) -> Tuple[bytes, str, str]:
    """拉取远端资源，返回 (buffer, original_name, mime)"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("不支持的资源 URL")
    host = parsed.hostname.lower()
    if _is_private_ip(host) or host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost"):
        raise ValueError("不允许从内网地址拉取远端资源")
    async with httpx.AsyncClient(timeout=REMOTE_FETCH_TIMEOUT) as client:
        resp = await client.get(url, follow_redirects=True)
        resp.raise_for_status()
        c_len = int(resp.headers.get("content-length", 0))
        if c_len > REMOTE_MAX_BYTES:
            raise ValueError("远端资源过大")
        buf = resp.content
        if len(buf) > REMOTE_MAX_BYTES:
            raise ValueError("远端资源过大")
        original_name = os.path.basename(parsed.path) or "remote_asset"
        mime = resp.headers.get("content-type", "") or _mime_from_ext(os.path.splitext(original_name)[1])
        return buf, original_name, mime


def _resolve_source(url: str, root: str, db: Dict) -> Tuple[bytes, str, str]:
    """从 URL 获取资源二进制"""
    clean = url.split("?")[0].split("#")[0]
    # 本地 output
    if clean.startswith("/imdf/media/output/"):
        rel = clean[len("/imdf/media/output/"):].lstrip("/")
        fp = os.path.normpath(os.path.join(OUTPUT_DIR, rel))
        fp = _assert_inside(OUTPUT_DIR, fp)
        with open(fp, "rb") as f:
            return f.read(), os.path.basename(rel), _mime_from_ext(os.path.splitext(rel)[1])
    # 本地 input
    if clean.startswith("/imdf/media/input/"):
        rel = clean[len("/imdf/media/input/"):].lstrip("/")
        fp = os.path.normpath(os.path.join(INPUT_DIR, rel))
        fp = _assert_inside(INPUT_DIR, fp)
        with open(fp, "rb") as f:
            return f.read(), os.path.basename(rel), _mime_from_ext(os.path.splitext(rel)[1])
    # 资源库素材
    m = re.match(r"^/imdf/library/file/([^/?#]+)", clean)
    if m:
        item_id = m.group(1)
        item = next((x for x in db["items"] if x["id"] == item_id), None)
        if not item:
            raise ValueError("资源库源文件不存在")
        fp = os.path.normpath(os.path.join(root, item["fileRel"]))
        fp = _assert_inside(root, fp)
        with open(fp, "rb") as f:
            return f.read(), item.get("originalName") or os.path.basename(item["fileRel"]), item.get("mime", _mime_from_ext(os.path.splitext(item["fileRel"])[1]))
    # 远端
    if re.match(r"^https?://", url, re.I):
        # 用 asyncio.run() 或在异步路由中直接用 await
        try:
            import asyncio
            loop = asyncio.get_running_loop()
            # 有运行中的循环 → 创建新任务
            fut = asyncio.run_coroutine_threadsafe(_fetch_remote(url), loop)
            return fut.result()
        except RuntimeError:
            # 无运行中的循环
            return asyncio.run(_fetch_remote(url))
    raise ValueError("不支持的资源 URL")


def _make_thumbnail(buf: bytes, root: str, item_id: str) -> str:
    """用 Pillow 生成 webp 缩略图"""
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(buf))
        img = img.convert("RGB")
        img.thumbnail((420, 420), Image.LANCZOS)
        rel = os.path.join(THUMB_DIR, f"{item_id}.webp")
        target = os.path.join(root, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        img.save(target, "WEBP", quality=82)
        return rel.replace("\\", "/")
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# 装饰器: 为资源项添加 URL 字段
# ═══════════════════════════════════════════════════════════════════════════════

def _decorate_item(item: Dict) -> Dict:
    base = dict(item)
    if base["kind"] == "set":
        base["fileUrl"] = f"/imdf/library/set/{base['id']}"
        base["thumbUrl"] = f"/imdf/library/thumb/{base['id']}" if base["thumbRel"] else ""
        base["materialSetItems"] = [_decorate_set_child(base["id"], x, idx) for idx, x in enumerate(base.get("materialSetItems", []))]
    else:
        base["fileUrl"] = f"/imdf/library/file/{base['id']}"
        base["thumbUrl"] = f"/imdf/library/thumb/{base['id']}" if base["thumbRel"] else ""
    return base


def _decorate_set_child(parent_id: str, raw: Dict, index: int) -> Dict:
    return {
        **raw,
        "url": f"/imdf/library/set-file/{parent_id}/{index}" if raw.get("kind") != "text" else raw.get("text", ""),
        "id": raw.get("id") or f"set_item_{index+1}",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 分类 API
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/categories")
async def list_categories(
    kind: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="分类类型 (白名单字符)",
    ),
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
    _, db = _read_db()
    cats = [c for c in db["categories"] if not kind or c["kind"] == kind]
    cats.sort(key=lambda x: (x["order"] or 0))
    if q:
        cats = [c for c in cats if q.lower() in str(c.get("name", "")).lower()]
    total = len(cats)
    page = cats[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/categories")
async def create_category(req: CategoryCreate):
    kind = _normalize_kind(req.kind)
    name = _sanitize_text(req.name)
    if not kind or not name:
        raise HTTPException(status_code=400, detail="缺少分类类型或名称")
    root, db = _read_db()
    order = len([c for c in db["categories"] if c["kind"] == kind])
    item = {"id": _generate_id("libcat"), "kind": kind, "name": name,
            "order": order, "system": False, "createdAt": _current_ms()}
    db["categories"].append(item)
    _write_db(root, db)
    return {"success": True, "data": item}


# ═══════════════════════════════════════════════════════════════════════════════
# 素材 API
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/items")
async def list_items(
    kind: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="素材类型 (白名单字符)",
    ),
    category_id: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="分类 ID (白名单字符)",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
    favorite: bool = Query(False, description="仅收藏"),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
):
    _, db = _read_db()
    items = list(db["items"])
    if kind:
        items = [it for it in items if it["kind"] == kind]
    if category_id and category_id != "all":
        items = [it for it in items if it["categoryId"] == category_id]
    if favorite:
        items = [it for it in items if it["favorite"]]
    if q:
        ql = q.lower()
        items = [it for it in items if ql in f"{it['title']} {it['originalName']} {' '.join(it['tags'])} {it['mime']}".lower()]
    items.sort(key=lambda x: (0 if x["favorite"] else 1, -(x["updatedAt"] or x["createdAt"])))
    total = len(items)
    page = items[offset: offset + limit]
    return {
        "success": True,
        "data": [_decorate_item(it) for it in page],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/items/add")
async def add_item(req: ItemAdd):
    if not req.url:
        raise HTTPException(status_code=400, detail="缺少 url")
    root, db = _read_db()
    buf, original_name, src_mime = _resolve_source(req.url, root, db)
    ext = os.path.splitext(original_name)[1].lower().lstrip(".") or _ext_from_mime(src_mime) or "bin"
    detected_kind = _kind_from_ext(ext) or _kind_from_ext(_ext_from_mime(src_mime))
    kind = _normalize_kind(req.kind) or detected_kind
    if not kind or kind not in ADDABLE_KINDS:
        raise HTTPException(status_code=400, detail="资源类型仅支持图像/视频/音频/全景")
    if kind == "panorama" and detected_kind != "image":
        raise HTTPException(status_code=400, detail="全景资源只能保存图像文件")
    if kind != "panorama" and detected_kind and detected_kind != kind:
        raise HTTPException(status_code=400, detail=f"素材类型不匹配: 需要 {kind}")

    sha256 = hashlib.sha256(buf).hexdigest()
    existing = next((x for x in db["items"] if x["kind"] == kind and x["sha256"] == sha256), None)
    req_cat = _sanitize_text(req.category_id)
    cat_ok = any(c["id"] == req_cat and c["kind"] == kind for c in db["categories"])

    if existing:
        if cat_ok:
            existing["categoryId"] = req_cat
        existing["updatedAt"] = _current_ms()
        existing["lastUsedAt"] = _current_ms()
        _write_db(root, db)
        return {"success": True, "duplicate": True, "data": _decorate_item(existing)}

    item_id = _generate_id("lib")
    safe_orig = _sanitize_filename(original_name, f"{kind}.{ext}")
    file_rel = os.path.join(kind, f"{item_id}.{ext}").replace("\\", "/")
    target = _assert_inside(root, os.path.join(root, file_rel))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f:
        f.write(buf)
    thumb_rel = _make_thumbnail(buf, root, item_id) if kind in ("image", "panorama") else ""

    item = {
        "id": item_id, "kind": kind,
        "categoryId": req_cat if cat_ok else f"{kind}_uncategorized",
        "title": _sanitize_text(req.title, os.path.splitext(safe_orig)[0]),
        "originalName": safe_orig, "fileRel": file_rel, "thumbRel": thumb_rel,
        "mime": _sanitize_text(src_mime, _mime_from_ext(ext)),
        "size": len(buf), "sha256": sha256,
        "tags": [str(t)[:80] for t in (req.tags or []) if str(t).strip()][:20],
        "favorite": req.favorite, "sourceUrl": req.url,
        "sourceNodeId": _sanitize_text(req.source_node_id),
        "sourceCanvasId": _sanitize_text(req.source_canvas_id),
        "createdAt": _current_ms(), "updatedAt": _current_ms(), "lastUsedAt": 0,
    }
    db["items"].append(item)
    _write_db(root, db)
    return {"success": True, "duplicate": False, "data": _decorate_item(item)}


# ═══════════════════════════════════════════════════════════════════════════════
# 文件服务路由 (用于 serve 文件)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/file/{item_id}")
async def serve_file(item_id: str, request: Request):
    root, db = _read_db()
    item = next((x for x in db["items"] if x["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="资源不存在")
    fp = _assert_inside(root, os.path.join(root, item["fileRel"]))
    if not os.path.exists(fp):
        raise HTTPException(status_code=404, detail="文件不存在")
    from fastapi.responses import FileResponse
    return FileResponse(fp, media_type=item.get("mime", _mime_from_ext(os.path.splitext(item["fileRel"])[1])))


@router.get("/thumb/{item_id}")
async def serve_thumb(item_id: str, request: Request):
    root, db = _read_db()
    item = next((x for x in db["items"] if x["id"] == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="资源不存在")
    rel = item["thumbRel"] or item["fileRel"]
    fp = _assert_inside(root, os.path.join(root, rel))
    if not os.path.exists(fp):
        raise HTTPException(status_code=404, detail="缩略图不存在")
    from fastapi.responses import FileResponse
    return FileResponse(fp, media_type="image/webp" if item["thumbRel"] else item.get("mime", "application/octet-stream"))
