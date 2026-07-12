"""P5-R1-T6: 内部质检 API — /api/v1/qc/*
====================================

4 种抽样模式 (full/sample/aql/stratified) + 查询 + 报告导出 + rerun
"""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
import logging

from api._common.body_schemas import (
    QCFullRequest, QCSampleRequest, QCAQLRequest,
    QCStratifiedRequest, QCRerunRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/qc", tags=["qc-internal"])


def _get_engine():
    from engines.internal_qc_engine import get_qc_engine
    return get_qc_engine()


@router.get("/records")
async def list_records(
    dataset_id: Optional[str] = Query(None, max_length=128),
    project_id: Optional[str] = Query(None, max_length=64),
    result: Optional[str] = Query(None, pattern=r"^(passed|failed)$"),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=200),
):
    """列出 QC 记录"""
    eng = _get_engine()
    items, total = eng.list_qc_records(
        dataset_id=dataset_id, project_id=project_id, result=result,
        page=page, page_size=page_size,
    )
    return {
        "success": True,
        "data": {
            "items": [r.to_dict() for r in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        },
        "error": None,
        "message": "ok",
    }


@router.post("/full")
async def full_check(req: QCFullRequest):
    """全量质检"""
    eng = _get_engine()
    try:
        record = eng.full_check(
            dataset_id=req.dataset_id,
            qcer_id=req.qcer_id,
            project_id=req.project_id,
            requirement_id=req.requirement_id,
            pack_id=req.pack_id,
            severity_bias=req.severity_bias,
            notes=req.notes,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"全量质检失败: {e}")
    return {
        "success": True,
        "data": record.to_dict(),
        "error": None,
        "message": f"全量质检完成, 抽样 {record.sample_size}, 缺陷 {record.issue_count}",
    }


@router.post("/sample")
async def sample_check(req: QCSampleRequest):
    """简单抽检"""
    eng = _get_engine()
    try:
        record = eng.sample_check(
            dataset_id=req.dataset_id,
            sample_rate=req.sample_rate,
            qcer_id=req.qcer_id,
            project_id=req.project_id,
            requirement_id=req.requirement_id,
            pack_id=req.pack_id,
            severity_bias=req.severity_bias,
            notes=req.notes,
            seed=req.seed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"抽检失败: {e}")
    return {
        "success": True,
        "data": record.to_dict(),
        "error": None,
        "message": f"抽检完成, 抽样 {record.sample_size}/{record.total_assets}, "
                   f"缺陷 {record.issue_count}",
    }


@router.post("/aql")
async def aql_sample(req: QCAQLRequest):
    """AQL 抽检 (ISO 2859-1)"""
    eng = _get_engine()
    try:
        record = eng.aql_sample(
            dataset_id=req.dataset_id,
            aql_level=req.aql_level,
            lot_size=req.lot_size,
            qcer_id=req.qcer_id,
            project_id=req.project_id,
            requirement_id=req.requirement_id,
            pack_id=req.pack_id,
            severity_bias=req.severity_bias,
            notes=req.notes,
            seed=req.seed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AQL 抽样失败: {e}")
    return {
        "success": True,
        "data": record.to_dict(),
        "error": None,
        "message": f"AQL={req.aql_level} 完成, Ac/Re 详见 notes",
    }


@router.post("/stratified")
async def stratified_sample(req: QCStratifiedRequest):
    """分层抽样"""
    eng = _get_engine()
    try:
        record = eng.stratified_sample(
            dataset_id=req.dataset_id,
            strata=req.strata,
            sample_size=req.sample_size,
            qcer_id=req.qcer_id,
            project_id=req.project_id,
            requirement_id=req.requirement_id,
            pack_id=req.pack_id,
            severity_bias=req.severity_bias,
            notes=req.notes,
            seed=req.seed,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分层抽样失败: {e}")
    return {
        "success": True,
        "data": record.to_dict(),
        "error": None,
        "message": f"分层抽样完成, 样本 {record.sample_size}",
    }


@router.get("/{qc_id}")
async def get_qc_record(qc_id: str):
    """获取 QC 记录详情"""
    eng = _get_engine()
    record = eng.get_qc_record(qc_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"QC 记录不存在: {qc_id}")
    return {
        "success": True,
        "data": record.to_dict(),
        "error": None,
        "message": "ok",
    }


@router.get("/{qc_id}/stats")
async def get_qc_stats(qc_id: str):
    """获取 QC 统计 (缺陷率/按严重度/按类型)"""
    eng = _get_engine()
    stats = eng.get_qc_stats(qc_id)
    if "error" in stats:
        raise HTTPException(status_code=404, detail=stats["error"])
    return {
        "success": True,
        "data": stats,
        "error": None,
        "message": "ok",
    }


@router.get("/{qc_id}/report")
async def export_report(
    qc_id: str,
    format: str = Query("json", pattern=r"^(json|csv|pdf)$"),
):
    """导出 QC 报告 (json/csv/pdf/html)"""
    eng = _get_engine()
    try:
        path = eng.export_qc_report(qc_id, format=format)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {e}")
    return {
        "success": True,
        "data": {"file_path": path, "format": format, "qc_id": qc_id},
        "error": None,
        "message": f"报告已导出: {path}",
    }


@router.post("/{qc_id}/rerun")
async def rerun_qc(qc_id: str, req: QCRerunRequest = QCRerunRequest()):
    """重跑 QC"""
    eng = _get_engine()
    try:
        record = eng.rerun_qc(qc_id, severity_bias=req.severity_bias)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重跑失败: {e}")
    return {
        "success": True,
        "data": record.to_dict(),
        "error": None,
        "message": f"QC 重跑完成: {record.id}",
    }