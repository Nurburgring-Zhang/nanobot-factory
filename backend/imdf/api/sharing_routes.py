"""
F1.16 受控共享 API 路由
=======================
POST /api/sharing/create      — 创建分享链接 (签名URL + 过期时间)
GET  /api/sharing/{token}     — 访问分享内容 (验证签名+密码)
GET  /api/sharing/list        — 列出所有活跃分享
DELETE /api/sharing/{token}   — 撤销分享
"""

import os
import json
import hmac
import hashlib
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Body, Query, Request
from pydantic import BaseModel

# R2-3: 路径 ID 校验 (分享 token)
from api._common.validators import validate_id

router = APIRouter(prefix="/api/sharing", tags=["sharing"])

# 存储分享元数据
SHARING_STORE = Path("data/sharing")
SHARING_STORE.mkdir(parents=True, exist_ok=True)
SHARING_META_FILE = SHARING_STORE / "shares.json"

# 签名密钥 (生产环境应从环境变量读取)
SHARING_SECRET = os.environ.get("IMDF_SHARING_SECRET", "imdf-sharing-secret-key-2024")


class ShareCreateRequest(BaseModel):
    """创建分享请求"""
    resource_path: str = ""           # 待分享文件/目录路径
    resource_type: str = "file"      # file / directory / dataset
    password: Optional[str] = None   # 可选密码保护
    expiry_hours: int = 24           # 过期时间(小时)
    max_downloads: int = 0           # 最大下载次数 (0=无限制)
    note: str = ""                   # 备注


class ShareInfo(BaseModel):
    """分享信息"""
    token: str = ""
    resource_path: str = ""
    resource_type: str = "file"
    created_at: str = ""
    expires_at: str = ""
    has_password: bool = False
    downloads_used: int = 0
    max_downloads: int = 0
    is_active: bool = True
    note: str = ""


def _generate_signature(token: str, expiry: int, resource: str) -> str:
    """生成HMAC签名"""
    message = f"{token}:{expiry}:{resource}"
    sig = hmac.new(SHARING_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()[:16]
    return sig


def _verify_signature(token: str, expiry: int, resource: str, signature: str) -> bool:
    """验证签名"""
    expected = _generate_signature(token, expiry, resource)
    return hmac.compare_digest(expected, signature)


def _load_shares() -> Dict[str, dict]:
    """加载所有分享记录"""
    if SHARING_META_FILE.exists():
        try:
            return json.loads(SHARING_META_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_shares(shares: Dict[str, dict]):
    """保存分享记录"""
    SHARING_META_FILE.write_text(json.dumps(shares, indent=2, ensure_ascii=False))


def _cleanup_expired():
    """清理过期分享"""
    shares = _load_shares()
    now = time.time()
    expired = [t for t, s in shares.items() if s.get("expires_at", 0) < now]
    for t in expired:
        del shares[t]
    if expired:
        _save_shares(shares)



# ── Routes (order matters: /list must come before /{token}) ────────────


@router.get("/")
@router.get("/list")
async def list_shares(
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
    """列出所有活跃分享 (R2.5-W1: Pydantic Query 验证)"""
    _cleanup_expired()
    shares = _load_shares()
    active = []

    for token, share in shares.items():
        if share.get("is_active", False):
            active.append({
                "token": token,
                "resource_path": share["resource_path"],
                "resource_type": share["resource_type"],
                "created_at": share["created_at"],
                "expires_at": share.get("expires_at_iso", ""),
                "has_password": share.get("password_hash") is not None,
                "downloads_used": share.get("downloads_used", 0),
                "max_downloads": share.get("max_downloads", 0),
                "note": share.get("note", ""),
            })
    if q:
        ql = q.lower()
        active = [a for a in active if ql in str(a.get("resource_path", "")).lower() or ql in str(a.get("note", "")).lower()]
    total = len(active)
    if sort_by:
        active.sort(
            key=lambda a: a.get(sort_by, "") if isinstance(a, dict) else "",
            reverse=(order == "desc"),
        )
    page = active[offset: offset + limit]
    return {
        "success": True,
        "data": {
            "shares": page,
            "total": total,
        },
        "limit": limit,
        "offset": offset,
        "message": "ok",
    }


@router.post("/create")
async def create_share(req: ShareCreateRequest):
    """创建受控分享链接

    生成带签名的临时URL, 支持密码保护和下载限制。
    返回分享token和完整访问URL。
    """
    resource_path = req.resource_path

    if not resource_path:
        raise HTTPException(status_code=400, detail="resource_path is required")

    # 检查资源是否存在
    full_path = Path(resource_path)
    if req.resource_type == "file" and not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Resource not found: {resource_path}")

    # 生成token
    token = uuid.uuid4().hex[:12]
    now = time.time()
    expiry_ts = now + req.expiry_hours * 3600

    # 生成签名
    signature = _generate_signature(token, int(expiry_ts), resource_path)

    # 如果有密码, hash存储
    password_hash = None
    if req.password:
        password_hash = hashlib.sha256(req.password.encode()).hexdigest()

    # 保存分享记录
    shares = _load_shares()
    shares[token] = {
        "token": token,
        "resource_path": resource_path,
        "resource_type": req.resource_type,
        "created_at": datetime.fromtimestamp(now).isoformat(),
        "expires_at": int(expiry_ts),
        "expires_at_iso": datetime.fromtimestamp(expiry_ts).isoformat(),
        "password_hash": password_hash,
        "max_downloads": req.max_downloads,
        "downloads_used": 0,
        "signature": signature,
        "is_active": True,
        "note": req.note,
    }
    _save_shares(shares)

    # 构造分享URL
    share_url = f"/api/sharing/{token}?sig={signature}&exp={int(expiry_ts)}"

    return {
        "success": True,
        "data": {
            "token": token,
            "share_url": share_url,
            "resource_path": resource_path,
            "expires_at": datetime.fromtimestamp(expiry_ts).isoformat(),
            "expires_in_hours": req.expiry_hours,
            "has_password": req.password is not None,
            "max_downloads": req.max_downloads,
        },
        "message": "Share link created successfully",
    }


@router.get("/{token}")
async def access_share(
    token: str,
    sig: str = Query("", description="Signature for verification"),
    exp: int = Query(0, description="Expiry timestamp"),
    password: str = Query("", description="Access password"),
):
    """访问分享内容

    验证签名、过期时间、密码和下载限制。
    返回资源元数据或文件内容。
    """
    validate_id(token, "token")
    shares = _load_shares()
    share = shares.get(token)

    if not share:
        raise HTTPException(status_code=404, detail="Share not found or expired")

    # 检查是否活跃
    if not share.get("is_active", False):
        raise HTTPException(status_code=403, detail="Share has been revoked")

    # 检查过期
    now = time.time()
    if share.get("expires_at", 0) < now:
        share["is_active"] = False
        _save_shares(shares)
        raise HTTPException(status_code=410, detail="Share link has expired")

    # 验证签名
    if not _verify_signature(token, share["expires_at"], share["resource_path"], sig):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # 密码验证
    if share.get("password_hash"):
        if not password:
            raise HTTPException(status_code=401, detail="Password required")
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        if not hmac.compare_digest(share["password_hash"], pwd_hash):
            raise HTTPException(status_code=403, detail="Invalid password")

    # 下载限制
    max_dl = share.get("max_downloads", 0)
    dl_used = share.get("downloads_used", 0)
    if max_dl > 0 and dl_used >= max_dl:
        raise HTTPException(status_code=429, detail="Download limit reached")

    # 更新下载计数
    share["downloads_used"] = dl_used + 1
    _save_shares(shares)

    # 返回资源信息
    resource_path = share["resource_path"]
    full_path = Path(resource_path)

    file_info = {}
    if full_path.exists():
        if full_path.is_file():
            stat = full_path.stat()
            file_info = {
                "name": full_path.name,
                "size": stat.st_size,
                "size_human": f"{stat.st_size / 1024:.1f} KB" if stat.st_size < 1024 * 1024 else f"{stat.st_size / 1024 / 1024:.1f} MB",
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "type": "file",
            }
        elif full_path.is_dir():
            children = list(full_path.iterdir())[:50]
            file_info = {
                "name": full_path.name,
                "type": "directory",
                "children_count": len(children),
                "children": [{"name": c.name, "type": "dir" if c.is_dir() else "file"} for c in children],
            }

    return {
        "success": True,
        "data": {
            "token": token,
            "resource_path": resource_path,
            "resource_type": share["resource_type"],
            "file_info": file_info,
            "downloads_remaining": max_dl - share["downloads_used"] if max_dl > 0 else "unlimited",
            "created_at": share["created_at"],
            "expires_at": share.get("expires_at_iso", ""),
            "note": share.get("note", ""),
        },
        "message": "Share access granted",
    }


@router.delete("/{token}")
async def revoke_share(token: str):
    """撤销/删除分享"""
    validate_id(token, "token")
    shares = _load_shares()
    if token not in shares:
        raise HTTPException(status_code=404, detail="Share not found")

    shares[token]["is_active"] = False
    _save_shares(shares)

    return {
        "success": True,
        "data": {"token": token, "status": "revoked"},
        "message": f"Share {token} has been revoked",
    }
