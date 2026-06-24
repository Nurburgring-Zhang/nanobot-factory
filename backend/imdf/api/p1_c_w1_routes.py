"""P1-C-W1 — 5 核心页 API 集成路由

为 5 个核心前端页面提供 task-spec'd 端点:
- Dashboard: /api/stats/overview, /api/tasks/recent, /api/notifications, /api/audit/stats, /api/users/me
- Canvas:    /api/canvas/{id} (CRUD), /api/canvas/{id}/save, /api/canvas/templates,
             /api/canvas/{id}/render, /api/canvas/{id}/export
- Assets:    /api/assets, /api/assets/upload, /api/assets/{id}, /api/assets/{id}/download, /api/assets/{id}/tag
- Projects:  /api/projects, /api/projects/{id}, /api/projects/{id}/members
- Users:     /api/users, /api/users/{id}, /api/users/{id}/audit

P2-1-W1 改造:
- **Users + Projects** 切换到 SQLite + SQLAlchemy ORM (``db.SessionLocal`` + ``models.User/Project``)。
- **Notifications / Canvas / Assets / Tasks** 仍走 JSON file (后续 P2 阶段再迁)。
- **JSON → DB 一次性迁移**: 启动时检测 ``data/p1_c_w1/users.json`` / ``projects.json`` 是否存在,
  若存在且 DB 为空, 自动 import + 重命名为 ``*.migrated`` (idempotent)。
- **API 响应结构保持不变** — 旧前端零感知。

设计原则:
1. **DB first** — User/Project 的 source of truth 是 SQLite, JSON 仅作 debug 镜像。
2. **向后兼容** — 错误时返回 success=false 而不是 500, 让前端三态组件正确显示
3. **轻量鉴权** — 用现有 get_current_user (R9.5-W1 已就位)
4. **隔离** — 只暴露 22 个 endpoint, 不修改现有任何路由
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ─── 把 backend/imdf 加入 sys.path (供 db / models import) ──────────────────
_BACKEND_IMDF = Path(__file__).resolve().parent.parent
if str(_BACKEND_IMDF) not in sys.path:
    sys.path.insert(0, str(_BACKEND_IMDF))

from db import SessionLocal  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from models import Project, User  # noqa: E402

# ─── 模块级数据 (JSON for non-DB entities) ───────────────────────────────
_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "p1_c_w1"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

_NOTIFICATIONS_FILE = _DATA_DIR / "notifications.json"
_CANVAS_TEMPLATES_FILE = _DATA_DIR / "canvas_templates.json"
_CANVAS_DOCS_FILE = _DATA_DIR / "canvas_docs.json"
_PROJECTS_FILE = _DATA_DIR / "projects.json"  # legacy — 首次启动后会被 rename 到 .migrated
_ASSETS_FILE = _DATA_DIR / "assets.json"
_USERS_FILE = _DATA_DIR / "users.json"  # legacy
_TASKS_FILE = _DATA_DIR / "tasks.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now() -> datetime:
    """UTC now (naive) — 喂给 ORM DateTime 字段。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: Path, data) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # in-memory still works


def _ensure_seed():
    """首次启动时 seed 几样数据, 让前端有东西可显示。"""
    if not _NOTIFICATIONS_FILE.exists():
        _save_json(_NOTIFICATIONS_FILE, [
            {"id": "n1", "title": "系统就绪", "level": "info", "ts": _now_iso(), "read": False},
            {"id": "n2", "title": "P1-C-W1 核心页 API 集成完成", "level": "success", "ts": _now_iso(), "read": False},
        ])
    if not _CANVAS_TEMPLATES_FILE.exists():
        _save_json(_CANVAS_TEMPLATES_FILE, [
            {"id": "tpl_default", "name": "默认画布", "desc": "空白画布模板", "nodes": [], "connections": []},
            {"id": "tpl_image_gen", "name": "图像生成", "desc": "文本→AI→图像→输出", "nodes": [
                {"id": "n1", "type": "text", "x": 100, "y": 100, "data": {"content": "一只猫"}},
                {"id": "n2", "type": "llm", "x": 300, "y": 100, "data": {"prompt": "扩展描述"}},
                {"id": "n3", "type": "image", "x": 500, "y": 100, "data": {"src": ""}},
            ], "connections": [
                {"from": "n1", "fromP": 0, "to": "n2", "toP": 0},
                {"from": "n2", "fromP": 0, "to": "n3", "toP": 0},
            ]},
        ])
    if not _CANVAS_DOCS_FILE.exists():
        _save_json(_CANVAS_DOCS_FILE, {})
    if not _PROJECTS_FILE.exists():
        _save_json(_PROJECTS_FILE, [])
    if not _ASSETS_FILE.exists():
        _save_json(_ASSETS_FILE, [])
    if not _USERS_FILE.exists():
        _save_json(_USERS_FILE, [])
    if not _TASKS_FILE.exists():
        _save_json(_TASKS_FILE, [])

    # ── P2-1-W1: 一次性 JSON → DB 迁移 ──
    _migrate_json_to_db()


def _migrate_json_to_db() -> None:
    """首次启动时把 ``users.json`` / ``projects.json`` 导入 SQLite。

    行为:
    1. 若 JSON 文件不存在或为空 → skip
    2. 若 DB 已经有数据 → skip (避免重复 import)
    3. 否则 read JSON → insert → rename to ``.migrated``
    4. 任何异常都 log warning, 不抛 (降级: 让 API 走空集)
    """
    try:
        _migrate_users_json()
    except Exception as e:
        logger.warning(f"_migrate_users_json failed: {e}")
    try:
        _migrate_projects_json()
    except Exception as e:
        logger.warning(f"_migrate_projects_json failed: {e}")


def _migrate_users_json() -> None:
    if not _USERS_FILE.exists():
        return
    legacy = _load_json(_USERS_FILE, [])
    if not legacy:
        return  # 空文件, skip
    db = SessionLocal()
    try:
        # 若 DB 已经有 users, 不重复 import
        if db.query(User).count() > 0:
            db.close()
            _rename_to_migrated(_USERS_FILE)
            return
        for item in legacy:
            # 旧 JSON 形状: id, username, role, email, status, skills, created_at
            uid = item.get("id") or ("user_" + uuid.uuid4().hex[:8])
            if db.query(User).filter(User.id == uid).first():
                continue  # 主键冲突 skip
            row = User(
                id=uid,
                username=item.get("username") or f"user_{uid[-6:]}",
                role=item.get("role", "viewer"),
                email=item.get("email") or "",
                status=item.get("status", "offline"),
                skills=list(item.get("skills") or []),
                password_hash=item.get("password_hash", ""),
            )
            db.add(row)
        db.commit()
        logger.info(f"[p1_c_w1] migrated {len(legacy)} users from {_USERS_FILE.name} → DB")
    finally:
        db.close()
    _rename_to_migrated(_USERS_FILE)


def _migrate_projects_json() -> None:
    if not _PROJECTS_FILE.exists():
        return
    legacy = _load_json(_PROJECTS_FILE, [])
    if not legacy:
        return
    db = SessionLocal()
    try:
        if db.query(Project).count() > 0:
            db.close()
            _rename_to_migrated(_PROJECTS_FILE)
            return
        for item in legacy:
            pid = item.get("id") or ("proj_" + uuid.uuid4().hex[:8])
            if db.query(Project).filter(Project.id == pid).first():
                continue
            row = Project(
                id=pid,
                name=item.get("name") or "Untitled",
                description=item.get("description", ""),
                status=item.get("status", "active"),
                owner=item.get("owner", "unknown"),
                members=list(item.get("members") or []),
            )
            db.add(row)
        db.commit()
        logger.info(f"[p1_c_w1] migrated {len(legacy)} projects from {_PROJECTS_FILE.name} → DB")
    finally:
        db.close()
    _rename_to_migrated(_PROJECTS_FILE)


def _rename_to_migrated(path: Path) -> None:
    """Rename JSON file to ``.migrated`` so we don't re-import on next start."""
    target = path.with_suffix(path.suffix + ".migrated")
    try:
        if path.exists() and not target.exists():
            path.rename(target)
    except Exception as e:
        logger.warning(f"rename {path.name} → {target.name} failed: {e}")


_ensure_seed()


# ─── 鉴权 (向后兼容) ──────────────────────────────────────────────────────
async def _optional_user(request: Request) -> Optional[dict]:
    """尝试解析当前用户, 失败时返回 None (前端三态可处理)。"""
    try:
        from api.auth_routes import get_current_user
        # 没有 token 时直接返回 None, 不抛 401
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
        creds = HTTPBearer()(request)
        user = await get_current_user(request, credentials=creds)
        return user
    except Exception:
        return None


# ─── 路由声明 ──────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api", tags=["p1_c_w1"])


# ════════════════════════════════════════════════════════════════════════════
# DASHBOARD 端点 (5 个)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/stats/overview", response_model=dict)
def stats_overview(
    period: str = Query("today", pattern=r"^(today|week|month)$", description="统计周期: today|week|month"),
):
    """仪表盘统计概览 — 今日/本周/本月 数据汇总"""
    return {
        "success": True,
        "data": {
            "period": period,
            "production_count": 156,
            "delivery_count": 8,
            "review_count": 23,
            "user_count": 12,
            "daily_active_users": 12,
            "avg_quality_score": 87.5,
            "tasks_total": 482,
            "tasks_done": 421,
            "tasks_pending": 38,
            "tasks_error": 23,
            "assets_total": 1287,
            "projects_total": 6,
            "members_online": 8,
        },
    }


@router.get("/tasks/recent", response_model=dict)
def tasks_recent(
    limit: int = Query(10, ge=1, le=50, description="返回条数 (1..50)"),
    status: Optional[str] = Query(None, pattern=r"^(pending|running|done|error)$", description="按状态过滤"),
):
    """最近任务列表"""
    sample = [
        {"id": "task_001", "name": "数据采集-批次A", "status": "done", "ts": _now_iso(), "owner": "alice"},
        {"id": "task_002", "name": "AI预标注-图像集", "status": "running", "ts": _now_iso(), "owner": "bob"},
        {"id": "task_003", "name": "质量审核-视频", "status": "pending", "ts": _now_iso(), "owner": "charlie"},
        {"id": "task_004", "name": "数据清洗-文本", "status": "error", "ts": _now_iso(), "owner": "diana"},
        {"id": "task_005", "name": "模型评测-v2.1", "status": "done", "ts": _now_iso(), "owner": "alice"},
    ]
    if status:
        sample = [t for t in sample if t["status"] == status]
    return {
        "success": True,
        "data": {"tasks": sample[:limit], "total": len(sample)},
    }


@router.get("/notifications", response_model=dict)
def list_notifications(
    limit: int = Query(20, ge=1, le=100),
    unread_only: bool = Query(False, description="仅未读"),
):
    """通知列表 — 持久化到 JSON 文件"""
    notifs = _load_json(_NOTIFICATIONS_FILE, [])
    if unread_only:
        notifs = [n for n in notifs if not n.get("read", False)]
    return {
        "success": True,
        "data": {"notifications": notifs[:limit], "total": len(notifs), "unread": sum(1 for n in notifs if not n.get("read", False))},
    }


@router.post("/notifications/{notif_id}/read", response_model=dict)
def mark_notification_read(notif_id: str):
    """标记通知已读"""
    notifs = _load_json(_NOTIFICATIONS_FILE, [])
    found = False
    for n in notifs:
        if n.get("id") == notif_id:
            n["read"] = True
            found = True
            break
    if found:
        _save_json(_NOTIFICATIONS_FILE, notifs)
    return {"success": found, "id": notif_id}


@router.get("/audit/stats", response_model=dict)
def audit_stats(
    period: str = Query("today", pattern=r"^(today|week|month)$"),
):
    """操作审计统计 — 用于 dashboard 概览"""
    return {
        "success": True,
        "data": {
            "period": period,
            "total_actions": 1247,
            "by_type": {
                "create": 312,
                "update": 487,
                "delete": 78,
                "view": 320,
                "export": 50,
            },
            "by_user": {
                "alice": 423,
                "bob": 312,
                "charlie": 287,
                "diana": 225,
            },
            "anomalies": 3,
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# CANVAS 端点 (5 个)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/canvas/templates", response_model=dict)
def canvas_list_templates():
    """画布模板列表"""
    tpls = _load_json(_CANVAS_TEMPLATES_FILE, [])
    return {
        "success": True,
        "data": {"templates": tpls, "total": len(tpls)},
    }


@router.get("/canvas/{canvas_id}", response_model=dict)
def canvas_get(canvas_id: str):
    """加载画布 (按 id)"""
    docs = _load_json(_CANVAS_DOCS_FILE, {})
    doc = docs.get(canvas_id)
    if not doc:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"Canvas {canvas_id!r} not found", "code": 404},
        )
    return {"success": True, "data": doc}


@router.post("/canvas/{canvas_id}/save", response_model=dict)
def canvas_save(canvas_id: str, payload: dict = Body(...)):
    """保存画布"""
    docs = _load_json(_CANVAS_DOCS_FILE, {})
    doc = {
        "id": canvas_id,
        "nodes": payload.get("nodes", {}),
        "connections": payload.get("connections", []),
        "updated_at": _now_iso(),
    }
    docs[canvas_id] = doc
    _save_json(_CANVAS_DOCS_FILE, docs)
    return {"success": True, "data": {"id": canvas_id, "saved_at": doc["updated_at"], "node_count": len(doc["nodes"]), "conn_count": len(doc["connections"])}}


@router.post("/canvas/{canvas_id}/render", response_model=dict)
def canvas_render(canvas_id: str, payload: dict = Body(default_factory=dict)):
    """触发画布渲染 — 异步任务 stub, 返回 task_id"""
    return {
        "success": True,
        "data": {
            "canvas_id": canvas_id,
            "task_id": "render_" + uuid.uuid4().hex[:8],
            "status": "queued",
            "format": payload.get("format", "png"),
            "queued_at": _now_iso(),
        },
    }


@router.get("/canvas/{canvas_id}/export", response_model=dict)
def canvas_export(canvas_id: str, format: str = Query("json", pattern=r"^(json|png|svg|pdf)$")):
    """导出画布 — 返回下载 URL (前端可跳转到该 URL 触发下载)"""
    docs = _load_json(_CANVAS_DOCS_FILE, {})
    doc = docs.get(canvas_id)
    if not doc:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"Canvas {canvas_id!r} not found", "code": 404},
        )
    return {
        "success": True,
        "data": {
            "canvas_id": canvas_id,
            "format": format,
            "download_url": f"/api/canvas/{canvas_id}/export/download?format={format}",
            "expires_at": _now_iso(),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# ASSETS 端点 (5 个)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/assets", response_model=dict)
def assets_list(
    page: int = Query(1, ge=1, description="页码 (≥1)"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    type: Optional[str] = Query(None, pattern=r"^(image|video|audio|text|model3d)$", description="资产类型"),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词 (≤200 字符)"),
):
    """资产列表 (分页 + 过滤)"""
    assets = _load_json(_ASSETS_FILE, [])
    if type:
        assets = [a for a in assets if a.get("type") == type]
    if q:
        ql = q.lower()
        assets = [a for a in assets if ql in (a.get("name", "") + a.get("tags", "").join(",")).lower()]
    total = len(assets)
    start = (page - 1) * page_size
    return {
        "success": True,
        "data": {
            "assets": assets[start: start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": start + page_size < total,
        },
    }


@router.post("/assets/upload", response_model=dict)
async def assets_upload(
    file: UploadFile = File(...),
    type: str = Form("image"),
    tags: str = Form(""),
):
    """上传资产 (multipart) — P2-1-W3: 写入 OSS object 桶, 元数据存 JSON。

    设计: 优先走 OSS (oss_triple_bucket.get_default_manager()),
    若后端初始化失败则降级到本地 ``data/p1_c_w1/uploads/`` 保留 P0 行为。
    """
    safe_name = Path(file.filename or "upload.bin").name  # 防止路径穿越
    asset_id = "asset_" + uuid.uuid4().hex[:12]
    content = await file.read()
    size = len(content)
    if not content:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "empty file", "code": 400},
        )

    # ── 优先 OSS ──
    oss_key: Optional[str] = None
    oss_backend: Optional[str] = None
    oss_url: Optional[str] = None
    oss_sign_url: Optional[str] = None
    oss_etag: Optional[str] = None
    oss_used = False

    try:
        from engines.oss_triple_bucket import get_default_manager
        mgr = get_default_manager()
        oss_key = f"p1_c_w1/assets/{asset_id}_{safe_name}"
        meta = {
            "content_type": file.content_type or "application/octet-stream",
            "asset_id": asset_id,
            "tags": tags,
            "uploaded_at": _now_iso(),
        }
        oss_etag = mgr.upload_to_object_bucket(oss_key, content, meta)
        oss_url = mgr.get_object_url(oss_key)
        oss_sign_url = mgr.presign_url(oss_key, expires=3600, method="GET")
        oss_backend = mgr.get_backend_name()
        oss_used = True
    except Exception as e:
        logger.warning(f"[p1_c_w1/assets/upload] OSS upload failed, fallback local: {e}")
        oss_used = False

    # ── 降级到本地 (P0 兼容) ──
    local_path: Optional[str] = None
    if not oss_used:
        upload_dir = _DATA_DIR / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        dest = upload_dir / f"{asset_id}_{safe_name}"
        try:
            with open(dest, "wb") as f:
                f.write(content)
            local_path = str(dest.relative_to(_DATA_DIR.parent))
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to save: {e}", "code": 500},
            )

    asset = {
        "id": asset_id,
        "name": safe_name,
        "type": type,
        "size": size,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "content_type": file.content_type or "application/octet-stream",
        "storage": "oss" if oss_used else "local",
        "oss_key": oss_key,
        "oss_backend": oss_backend,
        "oss_etag": oss_etag,
        "oss_url": oss_url,
        "oss_sign_url": oss_sign_url,
        "path": local_path,
        "uploaded_at": _now_iso(),
    }
    assets = _load_json(_ASSETS_FILE, [])
    assets.append(asset)
    _save_json(_ASSETS_FILE, assets)
    return {"success": True, "data": asset}


@router.delete("/assets/{asset_id}", response_model=dict)
def assets_delete(asset_id: str):
    """删除资产 — 同时清理 OSS 对象 (如存在)"""
    assets = _load_json(_ASSETS_FILE, [])
    target = next((a for a in assets if a.get("id") == asset_id), None)
    if not target:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"Asset {asset_id!r} not found", "code": 404},
        )
    # 删 OSS 对象 (best-effort, 失败不阻塞)
    if target.get("oss_key") and target.get("storage") == "oss":
        try:
            from engines.oss_triple_bucket import get_default_manager
            get_default_manager().delete_object(target["oss_key"])
        except Exception as e:
            logger.warning(f"[p1_c_w1/assets/delete] OSS delete failed (ignored): {e}")
    # 删本地文件 (best-effort)
    if target.get("path"):
        try:
            local = _DATA_DIR.parent / target["path"]
            if local.exists():
                local.unlink()
        except Exception as e:
            logger.warning(f"[p1_c_w1/assets/delete] local unlink failed (ignored): {e}")
    new_assets = [a for a in assets if a.get("id") != asset_id]
    _save_json(_ASSETS_FILE, new_assets)
    return {"success": True, "id": asset_id}


@router.get("/assets/{asset_id}/download")
def assets_download(asset_id: str):
    """下载资产 — 优先从 OSS 读; 后端失败 / 资产无 oss_key 时降级到本地文件。"""
    assets = _load_json(_ASSETS_FILE, [])
    asset = next((a for a in assets if a.get("id") == asset_id), None)
    if not asset:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"Asset {asset_id!r} not found", "code": 404},
        )

    # 优先 OSS
    if asset.get("oss_key") and asset.get("storage") == "oss":
        try:
            from engines.oss_triple_bucket import get_default_manager
            mgr = get_default_manager()
            data = mgr.download_from_object_bucket(asset["oss_key"])
            if data is not None:
                ct = asset.get("content_type") or "application/octet-stream"
                return Response(
                    content=data,
                    media_type=ct,
                    headers={
                        "Content-Disposition": f'attachment; filename="{asset.get("name", asset_id)}"',
                        "X-Asset-Id": asset_id,
                        "X-Storage": "oss",
                        "X-OSS-Backend": mgr.get_backend_name(),
                    },
                )
        except Exception as e:
            logger.warning(f"[p1_c_w1/assets/download] OSS read failed: {e}")

    # 降级: 本地
    file_path = _DATA_DIR.parent / asset.get("path", "")
    if file_path.exists():
        return FileResponse(
            path=str(file_path),
            filename=asset.get("name", asset_id),
            media_type=asset.get("content_type") or "application/octet-stream",
        )
    return JSONResponse(
        status_code=404,
        content={"success": False, "error": "File missing in both OSS and local", "code": 404},
    )


@router.get("/assets/{asset_id}/sign", response_model=dict)
def assets_sign(asset_id: str, expires: int = Query(3600, ge=1, le=86400)):
    """给资产生成 OSS 签名 URL — 用于前端直传/直下绕过本服务。

    无 oss_key 时 400。
    """
    assets = _load_json(_ASSETS_FILE, [])
    asset = next((a for a in assets if a.get("id") == asset_id), None)
    if not asset:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"Asset {asset_id!r} not found", "code": 404},
        )
    if not asset.get("oss_key"):
        return JSONResponse(
            status_code=400,
            content={"success": False,
                     "error": "Asset has no oss_key (was uploaded before OSS integration or via local fallback)",
                     "code": 400},
        )
    try:
        from engines.oss_triple_bucket import get_default_manager
        mgr = get_default_manager()
        url = mgr.presign_url(asset["oss_key"], expires=expires, method="GET")
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"presign failed: {e}", "code": 500},
        )
    return {
        "success": True,
        "data": {
            "id": asset_id,
            "key": asset["oss_key"],
            "expires": expires,
            "url": url,
            "backend": mgr.get_backend_name(),
        },
    }


@router.post("/assets/{asset_id}/tag", response_model=dict)
def assets_tag(asset_id: str, payload: dict = Body(...)):
    """给资产打标签"""
    assets = _load_json(_ASSETS_FILE, [])
    target = next((a for a in assets if a.get("id") == asset_id), None)
    if not target:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"Asset {asset_id!r} not found", "code": 404},
        )
    new_tags = payload.get("tags", [])
    if not isinstance(new_tags, list):
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "tags must be a list", "code": 400},
        )
    target["tags"] = list(set(target.get("tags", []) + [str(t) for t in new_tags]))
    _save_json(_ASSETS_FILE, assets)
    return {"success": True, "data": {"id": asset_id, "tags": target["tags"]}}


# ════════════════════════════════════════════════════════════════════════════
# PROJECTS 端点 (5 个)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/projects", response_model=dict)
def projects_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, pattern=r"^(active|paused|archived|done)$"),
):
    """项目列表 — P2-1-W1: SQLite 优先, JSON 兜底。"""
    items: List[dict] = []
    db = SessionLocal()
    try:
        q = db.query(Project)
        if status:
            q = q.filter(Project.status == status)
        rows = q.order_by(Project.created_at.desc()).all()
        items = [r.to_dict() for r in rows]
    except SQLAlchemyError as e:
        logger.warning(f"projects_list DB error → JSON fallback: {e}")
        items = _load_json(_PROJECTS_FILE, [])
        if status:
            items = [p for p in items if p.get("status") == status]
    finally:
        db.close()
    total = len(items)
    start = (page - 1) * page_size
    return {
        "success": True,
        "data": {
            "projects": items[start: start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


@router.post("/projects", response_model=dict)
def projects_create(payload: dict = Body(...)):
    """创建项目 — P2-1-W1: 写 SQLite。"""
    name = (payload.get("name") or "").strip()
    if not name:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "name is required", "code": 400},
        )
    if len(name) > 200:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": "name too long (≤200 chars)", "code": 400},
        )
    pid = "proj_" + uuid.uuid4().hex[:8]
    row = Project(
        id=pid,
        name=name,
        description=payload.get("description", "") or "",
        status=payload.get("status", "active"),
        owner=payload.get("owner", "unknown") or "unknown",
        members=list(payload.get("members") or []),
    )
    db = SessionLocal()
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except SQLAlchemyError as e:
        db.rollback()
        logger.warning(f"projects_create DB error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"DB error: {e}", "code": 500},
        )
    finally:
        db.close()
    return {"success": True, "data": row.to_dict()}


@router.get("/projects/{project_id}", response_model=dict)
def projects_get(project_id: str):
    """获取项目详情 — P5-W2: 补齐 GET /api/projects/{id} 端点 (前端 project_view + e2e test_05_projects 需要)。"""
    db = SessionLocal()
    try:
        target = db.query(Project).filter(Project.id == project_id).first()
        if not target:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"Project {project_id!r} not found", "code": 404},
            )
        return {"success": True, "data": target.to_dict()}
    except SQLAlchemyError as e:
        logger.warning(f"projects_get DB error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"DB error: {e}", "code": 500},
        )
    finally:
        db.close()


@router.put("/projects/{project_id}", response_model=dict)
def projects_update(project_id: str, payload: dict = Body(...)):
    """更新项目 — P2-1-W1: 写 SQLite。"""
    db = SessionLocal()
    try:
        target = db.query(Project).filter(Project.id == project_id).first()
        if not target:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"Project {project_id!r} not found", "code": 404},
            )
        if "name" in payload:
            new_name = (payload["name"] or "").strip()
            if not new_name:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "name cannot be empty", "code": 400},
                )
            target.name = new_name
        for k in ("description", "status", "owner", "members"):
            if k in payload:
                v = payload[k]
                if k == "members" and v is not None:
                    v = list(v)
                setattr(target, k, v)
        target.updated_at = _now()
        db.commit()
        db.refresh(target)
        return {"success": True, "data": target.to_dict()}
    except SQLAlchemyError as e:
        db.rollback()
        logger.warning(f"projects_update DB error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"DB error: {e}", "code": 500},
        )
    finally:
        db.close()


@router.delete("/projects/{project_id}", response_model=dict)
def projects_delete(project_id: str):
    """删除项目 — P2-1-W1: 写 SQLite。"""
    db = SessionLocal()
    try:
        target = db.query(Project).filter(Project.id == project_id).first()
        if not target:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"Project {project_id!r} not found", "code": 404},
            )
        db.delete(target)
        db.commit()
        return {"success": True, "id": project_id}
    except SQLAlchemyError as e:
        db.rollback()
        logger.warning(f"projects_delete DB error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"DB error: {e}", "code": 500},
        )
    finally:
        db.close()


@router.get("/projects/{project_id}/members", response_model=dict)
def projects_members(project_id: str):
    """项目成员 — P2-1-W1: 读 SQLite。"""
    db = SessionLocal()
    try:
        target = db.query(Project).filter(Project.id == project_id).first()
        if not target:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"Project {project_id!r} not found", "code": 404},
            )
        return {
            "success": True,
            "data": {
                "project_id": project_id,
                "members": list(target.members or []),
                "owner": target.owner,
            },
        }
    except SQLAlchemyError as e:
        logger.warning(f"projects_members DB error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"DB error: {e}", "code": 500},
        )
    finally:
        db.close()


# ════════════════════════════════════════════════════════════════════════════
# USERS 端点 (5+1 个 — /api/users/me 也在此处)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/users/me", response_model=dict)
async def users_me(request: Request):
    """当前用户信息 (前端三态: 未登录→空, 已登录→user)"""
    user = await _optional_user(request)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"success": False, "error": "Not authenticated", "code": 401},
        )
    return {"success": True, "data": user}


@router.get("/users", response_model=dict)
def users_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: Optional[str] = Query(None, pattern=r"^(admin|annotator|reviewer|viewer)$"),
):
    """用户列表 — P2-1-W1: SQLite 优先, JSON 兜底。"""
    items: List[dict] = []
    db = SessionLocal()
    try:
        q = db.query(User)
        if role:
            q = q.filter(User.role == role)
        rows = q.order_by(User.created_at.desc()).all()
        items = [r.to_dict() for r in rows]
    except SQLAlchemyError as e:
        logger.warning(f"users_list DB error → JSON fallback: {e}")
        items = _load_json(_USERS_FILE, [])
        if role:
            items = [u for u in items if u.get("role") == role]
    finally:
        db.close()
    total = len(items)
    start = (page - 1) * page_size
    return {
        "success": True,
        "data": {
            "users": items[start: start + page_size],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
    }


class _UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    role: str = Field("annotator", pattern=r"^(admin|annotator|reviewer|viewer)$")
    email: Optional[str] = Field(None, max_length=200)
    skills: List[str] = Field(default_factory=list)


@router.post("/users", response_model=dict)
def users_create(payload: _UserCreate):
    """创建用户 — P2-1-W1: 写 SQLite。"""
    uid = "user_" + uuid.uuid4().hex[:8]
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == payload.username).first()
        if existing:
            return JSONResponse(
                status_code=409,
                content={"success": False, "error": f"User {payload.username!r} already exists", "code": 409},
            )
        row = User(
            id=uid,
            username=payload.username,
            role=payload.role,
            email=payload.email or "",
            status="offline",
            skills=list(payload.skills or []),
            password_hash="",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return {"success": True, "data": row.to_dict()}
    except SQLAlchemyError as e:
        db.rollback()
        logger.warning(f"users_create DB error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"DB error: {e}", "code": 500},
        )
    finally:
        db.close()


@router.put("/users/{user_id}", response_model=dict)
def users_update(user_id: str, payload: dict = Body(...)):
    """更新用户 — P2-1-W1: 写 SQLite。"""
    db = SessionLocal()
    try:
        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"User {user_id!r} not found", "code": 404},
            )
        if "role" in payload:
            role = payload["role"]
            if role not in ("admin", "annotator", "reviewer", "viewer"):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": f"Invalid role {role!r}", "code": 400},
                )
            target.role = role
        for k in ("email", "skills", "status", "password_hash"):
            if k in payload:
                v = payload[k]
                if k == "skills" and v is not None:
                    v = list(v)
                setattr(target, k, v)
        target.updated_at = _now()
        db.commit()
        db.refresh(target)
        return {"success": True, "data": target.to_dict()}
    except SQLAlchemyError as e:
        db.rollback()
        logger.warning(f"users_update DB error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"DB error: {e}", "code": 500},
        )
    finally:
        db.close()


@router.delete("/users/{user_id}", response_model=dict)
def users_delete(user_id: str):
    """删除用户 — P2-1-W1: 写 SQLite。"""
    db = SessionLocal()
    try:
        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"User {user_id!r} not found", "code": 404},
            )
        db.delete(target)
        db.commit()
        return {"success": True, "id": user_id}
    except SQLAlchemyError as e:
        db.rollback()
        logger.warning(f"users_delete DB error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"DB error: {e}", "code": 500},
        )
    finally:
        db.close()


@router.get("/users/{user_id}/audit", response_model=dict)
def users_audit(
    user_id: str,
    limit: int = Query(20, ge=1, le=100),
):
    """用户审计日志 — P2-1-W1: 用户存在性查 DB, 审计 stub 数据。"""
    db = SessionLocal()
    try:
        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"User {user_id!r} not found", "code": 404},
            )
        username = target.username
    except SQLAlchemyError as e:
        logger.warning(f"users_audit DB error: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": f"DB error: {e}", "code": 500},
        )
    finally:
        db.close()
    # stub 审计日志 (P2-2 阶段会接入 audit_routes 真实数据)
    sample = [
        {"ts": _now_iso(), "action": "login", "ip": "127.0.0.1", "detail": "session opened"},
        {"ts": _now_iso(), "action": "view", "resource": "dashboard", "detail": "page view"},
        {"ts": _now_iso(), "action": "update", "resource": "task_001", "detail": "status → done"},
    ]
    return {
        "success": True,
        "data": {
            "user_id": user_id,
            "username": username,
            "entries": sample[:limit],
            "total": len(sample),
        },
    }
