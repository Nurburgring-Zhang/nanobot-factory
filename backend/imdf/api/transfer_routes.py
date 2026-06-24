"""
F1.16 受控传输共享 API 路由 — Transfer Routes
=============================================
提供受控分享的 RESTful API:

  POST   /api/transfer/share       — 创建分享链接 (签名URL + 过期 + 密码 + 下载限制)
  GET    /api/transfer/list        — 我的分享列表
  GET    /api/transfer/list/all    — 列出所有分享 (管理员)
  GET    /api/transfer/find-by-resource — 按资源路径查找
  POST   /api/transfer/cleanup     — 清理过期分享
  GET    /api/transfer/{token}     — 访问分享 (验证签名+密码+过期+下载限制)
  DELETE /api/transfer/{id}        — 取消/撤销分享
"""

import os
import json
import time
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, HTTPException, Body, Query
from pydantic import BaseModel

from engines.transfer_engine import get_transfer_engine, TransferEngine, ShareAccessResult

router = APIRouter(prefix="/api/transfer", tags=["transfer"])

# 引擎实例
engine: TransferEngine = get_transfer_engine()

# ═══════════════════════════════════════════════════════════════════════════
# Request Models
# ═══════════════════════════════════════════════════════════════════════════

class ShareCreateRequest(BaseModel):
    """创建分享请求"""
    resource_path: str                       # 待分享文件/目录路径
    resource_type: str = "file"              # file | directory | dataset
    password: Optional[str] = None           # 可选密码
    expiry_hours: int = 24                   # 有效时长 (小时)
    max_downloads: int = 0                   # 最大下载次数 (0=无限制)
    note: str = ""                           # 备注


class ShareBatchCreateRequest(BaseModel):
    """批量创建分享请求"""
    items: List[ShareCreateRequest]          # 批量项目


# ═══════════════════════════════════════════════════════════════════════════
# Route: 创建分享
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/share")
async def create_share(req: ShareCreateRequest):
    """创建受控分享链接

    生成带HMAC签名的临时URL, 支持:
      - 签名防篡改
      - 密码保护 (SHA-256哈希)
      - 下载次数限制
      - 自动过期

    请求示例:
    {
        "resource_path": "/data/images/photo.jpg",
        "resource_type": "file",
        "password": "secret123",
        "expiry_hours": 48,
        "max_downloads": 10,
        "note": "项目资料分享"
    }
    """
    try:
        result = engine.create_share(
            resource_path=req.resource_path,
            resource_type=req.resource_type,
            password=req.password,
            expiry_hours=req.expiry_hours,
            max_downloads=req.max_downloads,
            note=req.note,
        )
        return {
            "success": True,
            "data": result,
            "message": "分享链接创建成功",
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建分享失败: {str(e)}")


@router.post("/share/batch")
async def batch_create_shares(req: ShareBatchCreateRequest):
    """批量创建分享链接"""
    results = []
    errors = []

    for i, item in enumerate(req.items):
        try:
            result = engine.create_share(
                resource_path=item.resource_path,
                resource_type=item.resource_type,
                password=item.password,
                expiry_hours=item.expiry_hours,
                max_downloads=item.max_downloads,
                note=item.note,
            )
            results.append(result)
        except Exception as e:
            errors.append({"index": i, "error": str(e)})

    return {
        "success": len(errors) == 0,
        "data": {
            "created": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        },
        "message": f"批量创建完成: {len(results)} 成功, {len(errors)} 失败",
    }


# ═══════════════════════════════════════════════════════════════════════════
# IMPORTANT: 具体路径必须在 /{token} 之前定义, 否则会被 /{token} 捕获
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/list")
async def list_shares(
    creator: str = Query(
        "", max_length=128, pattern=r"^[a-zA-Z0-9_\-]{0,128}$",
        description="按创建者过滤 (白名单字符, ≤128 字符)",
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
    """获取我的分享列表

    返回所有活跃的分享链接, 包含:
      - token / 资源路径 / 过期时间
      - 密码保护状态 / 下载统计
    """
    shares = engine.list_shares(creator=creator)
    if q:
        q_lower = q.lower()
        shares = [s for s in shares if q_lower in str(s.get("resource_path", "")).lower() or q_lower in str(s.get("note", "")).lower()]
    total = len(shares)
    page = shares[offset: offset + limit]
    return {
        "success": True,
        "data": {
            "shares": page,
            "total": total,
        },
        "message": "ok",
        "limit": limit,
        "offset": offset,
    }


@router.get("/list/all")
async def list_all_shares(
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
    """列出所有分享 (管理员视图, 包含已过期)"""
    shares = engine._load()
    all_shares = []
    for token, s in shares.items():
        all_shares.append({
            "token": token,
            "resource_path": s.get("resource_path", ""),
            "resource_type": s.get("resource_type", "file"),
            "created_at": s.get("created_at", ""),
            "expires_at": s.get("expires_at_iso", ""),
            "has_password": s.get("password_hash") is not None,
            "downloads_used": s.get("downloads_used", 0),
            "max_downloads": s.get("max_downloads", 0),
            "is_active": s.get("is_active", False),
            "note": s.get("note", ""),
            "creator": s.get("creator", ""),
        })
    if q:
        q_lower = q.lower()
        all_shares = [s for s in all_shares if q_lower in str(s.get("resource_path", "")).lower() or q_lower in str(s.get("note", "")).lower()]
    total = len(all_shares)
    page = all_shares[offset: offset + limit]
    return {
        "success": True,
        "data": {
            "shares": page,
            "total": total,
            "active_count": sum(1 for s in page if s["is_active"]),
            "expired_count": sum(1 for s in page if not s["is_active"]),
        },
        "message": "ok",
        "limit": limit,
        "offset": offset,
    }


@router.get("/find-by-resource")
async def find_shares_by_resource(
    resource_path: str = Query(
        ..., min_length=1, max_length=2048,
        pattern=r"^[a-zA-Z0-9_./\\:\-]{1,2048}$",
        description="资源路径 (白名单字符, 1..2048 字符)",
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
    """通过资源路径查找所有活跃分享 (R2.5-W1: Pydantic Query 验证)"""
    shares = engine.find_by_resource(resource_path)
    total = len(shares)
    page = shares[offset: offset + limit]
    return {
        "success": True,
        "data": {
            "shares": page,
            "total": total,
            "resource_path": resource_path,
        },
        "message": "ok",
        "limit": limit,
        "offset": offset,
    }


@router.post("/cleanup")
async def cleanup_expired():
    """手动触发过期分享清理"""
    count = engine.cleanup_expired()
    return {
        "success": True,
        "data": {"cleaned": count},
        "message": f"清理了 {count} 条过期分享",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Route: 访问分享  — /{token} 必须在所有具体路径之后
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/{token}")
async def access_share(
    token: str,
    sig: str = Query("", description="签名 (防篡改校验)"),
    password: str = Query("", description="访问密码"),
):
    """访问分享内容

    验证流程:
      1. 检查分享是否存在且活跃
      2. 验证签名 (防URL篡改)
      3. 检查是否过期
      4. 如设置密码, 验证密码
      5. 检查下载次数限制

    成功访问后下载计数 +1
    """
    result: ShareAccessResult = engine.access_share(
        token=token,
        signature=sig,
        password=password,
        increment_download=True,
    )

    if not result.granted:
        status_map = {
            "分享不存在或已过期": 404,
            "分享已被撤销": 403,
            "分享链接已过期": 410,
            "签名无效": 403,
            "需要密码访问": 401,
            "密码错误": 403,
            "已达到下载次数上限": 429,
        }
        status = status_map.get(result.error, 403)
        raise HTTPException(status_code=status, detail=result.error)

    share = result.share
    return {
        "success": True,
        "data": {
            "token": token,
            "resource_path": share.get("resource_path", ""),
            "resource_type": share.get("resource_type", "file"),
            "file_info": result.file_info,
            "downloads_remaining": result.downloads_remaining,
            "downloads_used": share.get("downloads_used", 0),
            "max_downloads": share.get("max_downloads", 0),
            "created_at": share.get("created_at", ""),
            "expires_at": share.get("expires_at_iso", ""),
            "note": share.get("note", ""),
            "creator": share.get("creator", ""),
        },
        "message": "分享访问成功",
    }


@router.get("/{token}/preview")
async def preview_share(
    token: str,
    sig: str = Query("", description="签名"),
    password: str = Query("", description="访问密码"),
):
    """预览分享 (不增加下载计数)"""
    result: ShareAccessResult = engine.access_share(
        token=token,
        signature=sig,
        password=password,
        increment_download=False,           # 预览不计数
    )

    if not result.granted:
        raise HTTPException(status_code=403, detail=result.error)

    return {
        "success": True,
        "data": {
            "token": token,
            "resource_path": result.share.get("resource_path", ""),
            "file_info": result.file_info,
            "downloads_remaining": result.downloads_remaining,
            "requires_password": result.requires_password,
        },
        "message": "预览访问成功 (未扣减下载次数)",
    }


@router.get("/{share_id}/info")
async def get_share_info(share_id: str):
    """获取分享详细信息 (不触发下载)"""
    share = engine.find_by_id(share_id)
    if not share:
        raise HTTPException(status_code=404, detail=f"分享不存在: {share_id}")

    return {
        "success": True,
        "data": {
            "token": share.get("token", ""),
            "resource_path": share.get("resource_path", ""),
            "resource_type": share.get("resource_type", "file"),
            "created_at": share.get("created_at", ""),
            "expires_at": share.get("expires_at_iso", ""),
            "has_password": share.get("password_hash") is not None,
            "downloads_used": share.get("downloads_used", 0),
            "max_downloads": share.get("max_downloads", 0),
            "is_active": share.get("is_active", False),
            "note": share.get("note", ""),
            "creator": share.get("creator", ""),
        },
        "message": "ok",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Route: 取消/撤销分享
# ═══════════════════════════════════════════════════════════════════════════

@router.delete("/{share_id}")
async def revoke_share(share_id: str):
    """撤销分享链接

    将分享设为 inactive (软删除), 数据仍保留
    """
    ok = engine.revoke_share(share_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"分享不存在: {share_id}")

    return {
        "success": True,
        "data": {
            "token": share_id,
            "status": "revoked",
        },
        "message": f"分享 {share_id} 已撤销",
    }


@router.delete("/{share_id}/permanent")
async def delete_share_permanent(share_id: str):
    """永久删除分享记录"""
    ok = engine.delete_share(share_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"分享不存在: {share_id}")

    return {
        "success": True,
        "data": {
            "token": share_id,
            "status": "deleted",
        },
        "message": f"分享 {share_id} 已永久删除",
    }
