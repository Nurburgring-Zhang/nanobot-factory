"""P5-R1-T6: 需求方验收 API — /api/v1/requester/*
==================================================
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
import logging

from api._common.body_schemas import (
    AcceptanceCreateRequest, AcceptanceSubmitRequest,
    AcceptanceRevisionRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/requester", tags=["requester-acceptance"])


def _get_engine():
    from engines.requester_acceptance_engine import get_requester_engine
    return get_requester_engine()


@router.get("/pending")
async def list_pending(
    requester_id: str = Query(..., min_length=1, max_length=64),
):
    """列出待我验收的交付物"""
    eng = _get_engine()
    records = eng.list_pending_for_requester(requester_id)
    return {
        "success": True,
        "data": {
            "items": [r.to_dict() for r in records],
            "total": len(records),
        },
        "error": None,
        "message": "ok",
    }


@router.get("/acceptances")
async def list_acceptances(
    requester_id: str = Query(..., min_length=1, max_length=64),
    status: Optional[str] = Query(
        None, pattern=r"^(pending|accepted|rejected|needs_revision)$"
    ),
):
    """列出我参与的所有验收"""
    eng = _get_engine()
    records = eng.list_for_requester(requester_id, status=status)
    return {
        "success": True,
        "data": {
            "items": [r.to_dict() for r in records],
            "total": len(records),
        },
        "error": None,
        "message": "ok",
    }


@router.post("/acceptances")
async def create_acceptance(req: AcceptanceCreateRequest):
    """创建验收任务"""
    eng = _get_engine()
    try:
        record = eng.create_acceptance(
            delivery_id=req.delivery_id,
            requester_id=req.requester_id,
            sample_rate=req.sample_rate,
            metadata=req.metadata,
            seed=req.seed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {e}")
    return {
        "success": True,
        "data": record.to_dict(),
        "error": None,
        "message": f"已创建验收任务, 抽样 {record.sampled_count}",
    }


@router.get("/acceptances/{acceptance_id}")
async def get_acceptance(acceptance_id: str):
    """获取验收详情"""
    eng = _get_engine()
    record = eng.get_acceptance(acceptance_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"验收记录不存在: {acceptance_id}")
    return {
        "success": True,
        "data": record.to_dict(),
        "error": None,
        "message": "ok",
    }


@router.get("/acceptances/{acceptance_id}/stats")
async def get_acceptance_stats(acceptance_id: str):
    """获取验收统计"""
    eng = _get_engine()
    stats = eng.get_acceptance_stats(acceptance_id)
    if "error" in stats:
        raise HTTPException(status_code=404, detail=stats["error"])
    return {
        "success": True,
        "data": stats,
        "error": None,
        "message": "ok",
    }


@router.post("/acceptances/{acceptance_id}/submit")
async def submit_acceptance(acceptance_id: str, req: AcceptanceSubmitRequest):
    """提交验收决定"""
    eng = _get_engine()
    try:
        record = eng.submit_acceptance(
            acceptance_id=acceptance_id,
            status=req.status,
            comments=req.comments,
            accepted_assets=req.accepted_assets,
            rejected_assets=req.rejected_assets,
            issues=req.issues,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交失败: {e}")
    return {
        "success": True,
        "data": record.to_dict(),
        "error": None,
        "message": f"验收已提交: {record.status}",
    }


@router.post("/acceptances/{acceptance_id}/request-revision")
async def request_revision(acceptance_id: str, req: AcceptanceRevisionRequest):
    """退回生产"""
    eng = _get_engine()
    try:
        record = eng.request_revision(
            acceptance_id=acceptance_id,
            reason=req.reason,
            issues=req.issues,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"退回失败: {e}")
    return {
        "success": True,
        "data": record.to_dict(),
        "error": None,
        "message": "已退回生产",
    }


@router.get("/by-delivery/{delivery_id}")
async def list_by_delivery(delivery_id: str):
    """查询某交付物的所有验收记录"""
    eng = _get_engine()
    records = eng.get_acceptance_by_delivery(delivery_id)
    return {
        "success": True,
        "data": {
            "items": [r.to_dict() for r in records],
            "total": len(records),
        },
        "error": None,
        "message": "ok",
    }