"""OSS / MinIO API 路由 (P2-1-W3)

端点 (全挂在 ``/api/v1/oss`` 前缀下):
- POST   /api/v1/oss/upload            — multipart 上传, key 由 path 生成或客户端指定
- GET    /api/v1/oss/download/{key:path} — 拉取对象 (path param 含 ``/``)
- DELETE /api/v1/oss/object/{key:path}  — 删除对象
- GET    /api/v1/oss/sign/{key:path}    — 生成签名 URL (GET 默认 3600s)
- POST   /api/v1/oss/sign/{key:path}    — 生成 PUT 签名 URL
- GET    /api/v1/oss/list                — 按 prefix 列举对象
- HEAD   /api/v1/oss/head/{key:path}     — 取对象元数据
- GET    /api/v1/oss/health              — 后端健康检查

设计原则
========

1. **后端透明**: 调用方不需要知道后端是 mock / oss2 / minio, 接口语义完全一致。
2. **冷启动 fallback**: 无凭证时, 后端自动降级 mock, 端点依旧能返回 200 (数据存内存)。
3. **路径安全**: key 中可能的 ``..`` 会被拒绝 (防止 SSRF-like 任意 key 读取)。
4. **复用 manager**: 直接 ``get_default_manager()`` 拿到进程单例, 不重复创建 SDK 客户端。
5. **向后兼容**: 不修改 canvas_web.py 任何已有端点。

环境变量 (与 ``oss_triple_bucket.py`` 一致):
- ``OSS_BACKEND`` : ``oss2`` / ``minio`` / ``mock`` (默认自动检测)
- ``OSS_ACCESS_KEY_ID`` / ``OSS_ACCESS_KEY_SECRET`` / ``OSS_ENDPOINT`` / ``OSS_BUCKET`` / ``OSS_REGION``
- ``MINIO_ENDPOINT`` / ``MINIO_ACCESS_KEY`` / ``MINIO_SECRET_KEY`` / ``MINIO_BUCKET``
"""
from __future__ import annotations

import logging
import os
import re
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

logger = logging.getLogger(__name__)

# ── 路由声明 ────────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/v1/oss", tags=["oss"])


# ── 工具函数 ────────────────────────────────────────────────────────────

_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9._\-/]+$")
_MAX_KEY_LEN = 1024
_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB, 防止 OOM


def _validate_key(key: str) -> str:
    """校验对象 key 合法性 — 防止 ``..`` 路径穿越 / 控制字符注入。"""
    if not key:
        raise HTTPException(status_code=400, detail="key is required")
    if len(key) > _MAX_KEY_LEN:
        raise HTTPException(status_code=400, detail=f"key too long (>{_MAX_KEY_LEN})")
    if ".." in key:
        raise HTTPException(status_code=400, detail="key must not contain '..'")
    if key.startswith("/") or key.endswith("/"):
        raise HTTPException(status_code=400, detail="key must not start/end with '/'")
    if not _SAFE_KEY_RE.match(key):
        raise HTTPException(status_code=400,
                            detail="key may only contain letters, digits, '.', '_', '-', '/'")
    return key


def _manager():
    """懒加载 oss manager — 避免 import 时副作用。"""
    from engines.oss_triple_bucket import get_default_manager
    return get_default_manager()


def _normalize_key(raw: str) -> str:
    """兼容 ``/`` 开头 (前端常见), 自动 strip"""
    return raw.lstrip("/").rstrip("/")


# ── 端点实现 ────────────────────────────────────────────────────────────

@router.get("/health")
async def oss_health() -> Dict[str, Any]:
    """OSS 后端健康检查 — 返回 backend 类型 / endpoint / bucket / 状态。"""
    mgr = _manager()
    health = mgr.health_check()
    return {
        "success": health.get("status") == "ok",
        "backend": mgr.get_backend_name(),
        "data": health,
    }


@router.get("/list")
async def oss_list(
    prefix: str = Query("", max_length=256, description="对象 key 前缀过滤"),
    limit: int = Query(1000, ge=1, le=10000, description="最多返回条数 (1..10000)"),
) -> Dict[str, Any]:
    """按 prefix 列对象 — 用于资产浏览器 / 调试。"""
    if prefix:
        _validate_key(prefix + "x")  # 复用校验规则 (允许 prefix 末尾 / 中间有 /)
    mgr = _manager()
    keys = mgr.list_object_bucket(prefix=prefix)
    keys = keys[:limit]
    return {
        "success": True,
        "backend": mgr.get_backend_name(),
        "data": {
            "prefix": prefix,
            "keys": keys,
            "count": len(keys),
            "truncated": len(mgr.list_object_bucket(prefix=prefix)) > limit,
        },
    }


@router.post("/upload")
async def oss_upload(
    request: Request,
    file: UploadFile = File(..., description="要上传的文件 (multipart)"),
    key: Optional[str] = Form(None, description="对象 key; 不填则用 uuid + 原始文件名"),
    prefix: str = Form("uploads/", description="默认 key 前缀 (key 未填时生效)"),
    metadata: str = Form("", description="可选自定义 meta, JSON 字符串"),
    public: bool = Form(False, description="(占位) 是否公开 — 签名 URL 优先"),
) -> Dict[str, Any]:
    """上传文件到 object 桶。

    返回 ``{success, backend, data: {key, etag, size, url, sign_url}}``。
    """
    # 1. 决定 key
    if key:
        key = _normalize_key(key)
        _validate_key(key)
    else:
        # 用 uuid + 原文件名 (防止路径穿越)
        raw_name = os.path.basename(file.filename or "upload.bin")
        # 清洗文件名, 仅保留安全字符
        safe_name = re.sub(r"[^A-Za-z0-9._\-]", "_", raw_name)[:128] or "upload.bin"
        prefix_norm = prefix.lstrip("/").rstrip("/")
        if prefix_norm and not prefix_norm.endswith("/"):
            prefix_norm += "/"
        key = f"{prefix_norm}{uuid.uuid4().hex[:12]}_{safe_name}"
        _validate_key(key)

    # 2. 解析 metadata
    meta_dict: Dict[str, str] = {}
    if metadata:
        try:
            import json as _json
            parsed = _json.loads(metadata)
            if isinstance(parsed, dict):
                meta_dict = {str(k): str(v) for k, v in parsed.items()}
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"metadata must be valid JSON: {e}")
    if file.content_type:
        meta_dict.setdefault("content_type", file.content_type)
    meta_dict.setdefault("uploaded_at", str(int(time.time())))

    # 3. 读流
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"file too large (>{_MAX_UPLOAD_BYTES} bytes)")
    if not content:
        raise HTTPException(status_code=400, detail="empty file")

    # 4. 上传
    mgr = _manager()
    try:
        etag = mgr.upload_to_object_bucket(key, content, meta_dict)
    except Exception as e:
        logger.exception(f"[oss_routes] upload {key} failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "backend": mgr.get_backend_name(),
                     "error": f"upload failed: {e}"},
        )

    # 5. 生成签名 URL
    sign_url = mgr.presign_url(key, expires=3600, method="GET")

    return {
        "success": True,
        "backend": mgr.get_backend_name(),
        "data": {
            "key": key,
            "etag": etag,
            "size": len(content),
            "content_type": file.content_type,
            "url": mgr.get_object_url(key),
            "sign_url": sign_url,
            "metadata": meta_dict,
            "uploaded_at": meta_dict["uploaded_at"],
        },
    }


@router.post("/upload-bytes")
async def oss_upload_bytes(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """JSON 体上传 — 适用于 SDK / 内部服务。

    body: ``{"key": "...", "data_b64": "...", "metadata": {...}, "prefix": "uploads/"}``
    """
    key = (payload.get("key") or "").strip()
    data_b64 = payload.get("data_b64") or payload.get("data") or ""
    metadata = payload.get("metadata") or {}
    prefix = (payload.get("prefix") or "uploads/").lstrip("/").rstrip("/") + "/"

    if not key:
        # 自动生成 key
        key = f"{prefix}{uuid.uuid4().hex[:12]}.bin"
    key = _normalize_key(key)
    _validate_key(key)

    # data_b64 解码
    if not isinstance(data_b64, str):
        raise HTTPException(status_code=400, detail="data_b64 must be a string")
    try:
        import base64
        raw = base64.b64decode(data_b64, validate=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"data_b64 decode failed: {e}")
    if not raw:
        raise HTTPException(status_code=400, detail="empty data")
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"data too large (>{_MAX_UPLOAD_BYTES} bytes)")

    meta_dict: Dict[str, str] = {}
    if isinstance(metadata, dict):
        meta_dict = {str(k): str(v) for k, v in metadata.items()}
    meta_dict.setdefault("uploaded_at", str(int(time.time())))

    mgr = _manager()
    try:
        etag = mgr.upload_to_object_bucket(key, raw, meta_dict)
    except Exception as e:
        logger.exception(f"[oss_routes] upload-bytes {key} failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "backend": mgr.get_backend_name(),
                     "error": f"upload failed: {e}"},
        )

    return {
        "success": True,
        "backend": mgr.get_backend_name(),
        "data": {
            "key": key,
            "etag": etag,
            "size": len(raw),
            "url": mgr.get_object_url(key),
            "sign_url": mgr.presign_url(key, expires=3600, method="GET"),
            "metadata": meta_dict,
        },
    }


@router.get("/download/{key:path}")
async def oss_download(key: str) -> Response:
    """下载对象 — 透传原始 bytes (content-type 由 head 取)"""
    key = _normalize_key(key)
    _validate_key(key)
    mgr = _manager()
    data = mgr.download_from_object_bucket(key)
    if data is None:
        raise HTTPException(status_code=404, detail=f"object {key!r} not found")
    meta = mgr.head_object(key) or {}
    ct = (meta.get("content_type") or "application/octet-stream")
    return Response(content=data, media_type=ct,
                    headers={"ETag": meta.get("etag", ""),
                             "X-Object-Key": key,
                             "X-Backend": mgr.get_backend_name()})


@router.get("/head/{key:path}")
@router.head("/head/{key:path}")
async def oss_head(key: str) -> Dict[str, Any]:
    """取对象元数据 — 大小 / ETag / content-type。同时支持 GET + HEAD。"""
    key = _normalize_key(key)
    _validate_key(key)
    mgr = _manager()
    meta = mgr.head_object(key)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"object {key!r} not found")
    return {
        "success": True,
        "backend": mgr.get_backend_name(),
        "data": {"key": key, **meta},
    }


@router.delete("/object/{key:path}")
async def oss_delete(key: str) -> Dict[str, Any]:
    """删除对象 — 不存在也返回 200 (幂等)。"""
    key = _normalize_key(key)
    _validate_key(key)
    mgr = _manager()
    try:
        deleted = mgr.delete_object(key)
    except Exception as e:
        logger.exception(f"[oss_routes] delete {key} failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "backend": mgr.get_backend_name(),
                     "error": f"delete failed: {e}"},
        )
    return {
        "success": True,
        "backend": mgr.get_backend_name(),
        "data": {"key": key, "deleted": deleted},
    }


@router.get("/sign/{key:path}")
async def oss_sign_get(
    key: str,
    expires: int = Query(3600, ge=1, le=86400, description="过期秒数 (1..86400)"),
) -> Dict[str, Any]:
    """生成 GET 签名 URL — 客户端可直接浏览器下载。"""
    key = _normalize_key(key)
    _validate_key(key)
    mgr = _manager()
    url = mgr.presign_url(key, expires=expires, method="GET")
    if not url:
        raise HTTPException(status_code=500, detail="presign failed (check backend config)")
    return {
        "success": True,
        "backend": mgr.get_backend_name(),
        "data": {
            "key": key,
            "method": "GET",
            "expires": expires,
            "url": url,
        },
    }


@router.post("/sign/{key:path}")
async def oss_sign_post(
    key: str,
    expires: int = Query(3600, ge=1, le=86400),
    method: str = Query("PUT", pattern=r"^(GET|PUT)$"),
) -> Dict[str, Any]:
    """生成 PUT 签名 URL — 客户端可绕过本服务直传对象存储。"""
    key = _normalize_key(key)
    _validate_key(key)
    mgr = _manager()
    url = mgr.presign_url(key, expires=expires, method=method)
    if not url:
        raise HTTPException(status_code=500, detail="presign failed (check backend config)")
    return {
        "success": True,
        "backend": mgr.get_backend_name(),
        "data": {
            "key": key,
            "method": method,
            "expires": expires,
            "url": url,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
# P1-C-W1 兼容: 旧 /api/assets/{id}/download 走 OSS 时需要的 key 转换
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/exists/{key:path}")
async def oss_exists(key: str) -> Dict[str, Any]:
    """对象是否存在 + 大小 — 用于 SDK 健康检查 / 前端可访问性探测。"""
    key = _normalize_key(key)
    _validate_key(key)
    mgr = _manager()
    meta = mgr.head_object(key)
    return {
        "success": True,
        "backend": mgr.get_backend_name(),
        "data": {
            "key": key,
            "exists": meta is not None,
            "size": (meta or {}).get("size"),
            "etag": (meta or {}).get("etag"),
        },
    }
