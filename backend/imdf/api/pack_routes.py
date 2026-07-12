"""Pack API router (P5-R1-T3) — mount at /api/v1/packs

8 端点:
- GET    /packs                          列表
- POST   /packs                          创建 (body: name/type/has_data/...)
- GET    /packs/{id}                     详情
- PUT    /packs/{id}                     更新 (name/status/metadata)
- DELETE /packs/{id}                     删除
- POST   /packs/{id}/route               智能路由 (空包 → collection, 含数据 → annotation)
- POST   /packs/{id}/link-dataset        关联数据集
- GET    /packs/{id}/stats               统计 (含 progress%, completion_rate)
- POST   /packs/{id}/transition          状态转换

设计原则:
- 所有写操作走 Pydantic 校验
- 错误统一返回 4xx (不返回 500)
- 内部异常用 HTTPException(400/404)
- 状态机非法转换 → 400 with allowed transitions
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from engines.pack_engine import (
    PackEngine, PackStore, PackType, PackSource, PackStatus,
    InvalidPackTransitionError, get_engine,
)
from api._common.validators import validate_id

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/packs", tags=["packs"])


# ============================================================
# Pydantic schemas
# ============================================================

PACK_TYPES = [t.value for t in PackType]
PACK_SOURCES = [s.value for s in PackSource]
PACK_STATUSES = [s.value for s in PackStatus]
TASK_TYPES = ["annotation", "cleaning", "scoring", "review", "augmentation", "evaluation"]


class PackCreateRequest(BaseModel):
    """创建 pack 通用请求体."""
    name: str = Field(..., min_length=1, max_length=128)
    type: str = Field(..., description="data_pack / task_pack")
    has_data: Optional[bool] = Field(None, description="可选, 不传则按 type 自动推断")
    source: Optional[str] = Field(None, description="upload/collection/transfer/generation")
    requirement_id: str = Field("", max_length=64)
    project_id: str = Field("", max_length=64)
    asset_ids: Optional[List[str]] = Field(None, max_length=10000)
    asset_type: str = Field("image", max_length=20)
    task_type: Optional[str] = Field(None, description="task_pack 时必填")
    asset_count: int = Field(0, ge=0, le=10_000_000)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PackUpdateRequest(BaseModel):
    """更新 pack."""
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    status: Optional[str] = Field(None)
    metadata: Optional[Dict[str, Any]] = None
    asset_count: Optional[int] = Field(None, ge=0, le=10_000_000)


class PackTransitionRequest(BaseModel):
    """状态转换请求."""
    new_status: str = Field(..., min_length=1, max_length=20)
    reason: str = Field("", max_length=256)


class PackLinkDatasetRequest(BaseModel):
    """关联数据集请求."""
    dataset_id: str = Field(..., min_length=1, max_length=64)


def _pack_to_dict(p) -> Dict[str, Any]:
    return p.to_dict() if hasattr(p, "to_dict") else dict(p)


def _list_response(items: List, total: int, page: int, page_size: int) -> Dict[str, Any]:
    return {
        "success": True,
        "items": [_pack_to_dict(x) for x in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ============================================================
# 端点
# ============================================================

@router.get("")
async def list_packs(
    requirement_id: Optional[str] = Query(None, max_length=64),
    project_id: Optional[str] = Query(None, max_length=64),
    type: Optional[str] = Query(None, description="data_pack/task_pack"),
    status: Optional[str] = Query(None, description="created/ready/..."),
    keyword: Optional[str] = Query(None, max_length=128, description="name LIKE 模糊查询"),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=200),
):
    """列出 pack, 支持 5 维过滤 (req/project/type/status/keyword) + 分页.

    P0 修复: 加 keyword 后端支持 (前端 PackManager.vue 已经发 keyword)
    """
    if type and type not in PACK_TYPES:
        raise HTTPException(400, f"type 取值非法: {type!r}")
    if status and status not in PACK_STATUSES:
        raise HTTPException(400, f"status 取值非法: {status!r}")
    eng = get_engine()
    items, total = eng.list_packs(
        requirement_id=requirement_id or None,
        project_id=project_id or None,
        type=type or None,
        status=status or None,
        keyword=keyword or None,
        page=page, page_size=page_size,
    )
    return _list_response(items, total, page, page_size)


@router.post("", status_code=201)
async def create_pack(req: PackCreateRequest):
    """创建 pack — 根据 type 分发到 data_pack / task_pack."""
    if req.type not in PACK_TYPES:
        raise HTTPException(400, f"type 取值非法: {req.type!r}, 应为 data_pack/task_pack")
    source = req.source or PackSource.UPLOAD.value
    if source not in PACK_SOURCES:
        raise HTTPException(400, f"source 取值非法: {source!r}")

    eng = get_engine()
    if req.type == PackType.DATA_PACK.value:
        asset_ids = req.asset_ids or []
        if len(asset_ids) > 10000:
            raise HTTPException(400, f"asset_ids 超过上限 10000 (当前 {len(asset_ids)})")
        pack = eng.create_data_pack(
            name=req.name,
            asset_ids=asset_ids,
            requirement_id=req.requirement_id,
            project_id=req.project_id,
            source=source,
            metadata=req.metadata,
        )
    else:  # task_pack
        if not req.task_type:
            raise HTTPException(400, "task_pack 必须填写 task_type")
        if req.task_type not in TASK_TYPES:
            raise HTTPException(400, f"task_type 取值非法: {req.task_type!r}")
        pack = eng.create_task_pack(
            name=req.name,
            task_type=req.task_type,
            asset_count=req.asset_count,
            requirement_id=req.requirement_id,
            project_id=req.project_id,
            metadata=req.metadata,
        )

    return {"success": True, "data": _pack_to_dict(pack)}


@router.get("/{pack_id}")
async def get_pack(pack_id: str):
    """获取 pack 详情."""
    validate_id(pack_id, "pack_id")
    eng = get_engine()
    pack = eng.get_pack(pack_id)
    if not pack:
        raise HTTPException(404, f"pack 不存在: {pack_id}")
    return {"success": True, "data": _pack_to_dict(pack)}


@router.put("/{pack_id}")
async def update_pack(pack_id: str, req: PackUpdateRequest):
    """更新 pack — name/metadata/asset_count (不允许直接改 status, 走 transition)."""
    validate_id(pack_id, "pack_id")
    eng = get_engine()
    pack = eng.get_pack(pack_id)
    if not pack:
        raise HTTPException(404, f"pack 不存在: {pack_id}")

    fields: Dict[str, Any] = {}
    if req.name is not None:
        fields["name"] = req.name
    if req.metadata is not None:
        fields["metadata"] = req.metadata
    if req.asset_count is not None:
        fields["asset_count"] = req.asset_count
    if req.status is not None:
        # 通过 transition 校验
        try:
            updated = eng.update_pack_status(pack_id, req.status)
            return {"success": True, "data": _pack_to_dict(updated)}
        except ValueError as e:
            raise HTTPException(400, str(e))

    if not fields:
        return {"success": True, "data": _pack_to_dict(pack)}

    # 透传到 store
    updated = eng.store.update(pack_id, fields)
    if not updated:
        raise HTTPException(404, f"pack 不存在: {pack_id}")
    return {"success": True, "data": _pack_to_dict(updated)}


@router.delete("/{pack_id}")
async def delete_pack(pack_id: str):
    """删除 pack (级联 pack_assets)."""
    validate_id(pack_id, "pack_id")
    eng = get_engine()
    ok = eng.delete_pack(pack_id)
    if not ok:
        raise HTTPException(404, f"pack 不存在: {pack_id}")
    return {"success": True, "message": f"pack {pack_id} 已删除"}


@router.post("/{pack_id}/route")
async def route_pack(pack_id: str):
    """智能路由 — 根据 has_data 决定 annotation / collection 目标."""
    validate_id(pack_id, "pack_id")
    eng = get_engine()
    try:
        result = eng.route_pack(pack_id)
    except InvalidPackTransitionError as e:
        # P0 修复: 非法状态机转换 → 400 + 详细允许列表
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_transition",
                "current": e.current,
                "target": e.target,
                "allowed": e.allowed,
                "message": str(e),
            },
        )
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"success": True, "data": result}


@router.post("/{pack_id}/link-dataset")
async def link_dataset(pack_id: str, req: PackLinkDatasetRequest):
    """关联 pack 到 dataset."""
    validate_id(pack_id, "pack_id")
    validate_id(req.dataset_id, "dataset_id")
    eng = get_engine()
    try:
        pack = eng.link_to_dataset(pack_id, req.dataset_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"success": True, "data": _pack_to_dict(pack)}


@router.get("/{pack_id}/stats")
async def pack_stats(pack_id: str):
    """统计 — progress% + completion_rate + 资产数 + 路由次数."""
    validate_id(pack_id, "pack_id")
    eng = get_engine()
    try:
        stats = eng.get_pack_stats(pack_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"success": True, "data": stats}


@router.post("/{pack_id}/transition")
async def transition_pack(pack_id: str, req: PackTransitionRequest):
    """状态机驱动转换 — 校验合法性."""
    validate_id(pack_id, "pack_id")
    eng = get_engine()
    try:
        pack = eng.transition(pack_id, req.new_status, reason=req.reason)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"success": True, "data": _pack_to_dict(pack)}


# ============================================================
# 健康检查端点 (供 collector service / workflow 集成)
# ============================================================

@router.get("/_/health")
async def packs_health():
    return {"success": True, "module": "packs", "status": "ok"}