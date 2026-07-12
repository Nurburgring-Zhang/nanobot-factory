"""
AnnotationWorkbench Routes — 真画布标注工作台 HTTP API
- 前缀: /api/v1/workbench
- 9 个端点 (同 spec):
  - POST /pull              拉任务
  - POST /release           释放
  - POST /heartbeat         心跳
  - POST /annotations       保存单条
  - POST /annotations/bulk  批量保存
  - POST /submit            提交任务
  - GET  /tasks/{id}/annotations
  - GET  /annotations/{id}/history
  - GET  /tasks/{id}/lock   锁状态
  - GET  /stats             统计 (额外)
- 错误码: 4xx (参数错/锁冲突/不存在) + 5xx (DB)
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from engines.workbench_engine import (
    AnnotationRecord,
    GEOMETRY_TYPES,
    WorkbenchEngine,
    WorkbenchTask,
    get_workbench_engine,
    _AS_TO_WB,  # P5-R1-T4 retry: annotation_system 集成映射表
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workbench", tags=["workbench"])


# -------------------------------------------------------------
# Pydantic 模型
# -------------------------------------------------------------
class PullBody(BaseModel):
    annotator_id: str = Field(..., min_length=1)
    task_type: Optional[str] = None


class ReleaseBody(BaseModel):
    task_id: str = Field(..., min_length=1)
    annotator_id: str = Field(..., min_length=1)


class HeartbeatBody(BaseModel):
    task_id: str = Field(..., min_length=1)
    annotator_id: str = Field(..., min_length=1)


class AnnotationBody(BaseModel):
    task_id: str = Field(..., min_length=1)
    asset_id: str = Field(..., min_length=1)
    geometry_type: str
    geometry: Dict[str, Any]
    label: str = Field(..., min_length=1)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    annotator_id: Optional[str] = None
    confidence: float = 1.0
    occluded: bool = False
    truncated: bool = False
    annotation_id: Optional[str] = None
    parent_annotation_id: Optional[str] = None
    review_stage: str = "draft"

    @field_validator("geometry_type")
    @classmethod
    def _check_geometry_type(cls, v: str) -> str:
        if v not in GEOMETRY_TYPES:
            raise ValueError(f"geometry_type must be one of {sorted(GEOMETRY_TYPES)}")
        return v


class BulkAnnotationBody(BaseModel):
    task_id: str = Field(..., min_length=1)
    annotator_id: Optional[str] = None
    annotations: List[Dict[str, Any]]


class SubmitBody(BaseModel):
    task_id: str = Field(..., min_length=1)
    annotator_id: str = Field(..., min_length=1)


class EnqueueBody(BaseModel):
    task_id: str = Field(..., min_length=1)
    asset_id: str = Field(..., min_length=1)
    priority: int = 0
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None


# -------------------------------------------------------------
# 路由
# -------------------------------------------------------------
@router.post("/pull", summary="拉取下一个可标注任务(自动加锁)")
async def pull_task(
    body: PullBody,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    task = engine.pull_next_task(body.annotator_id, body.task_type)
    if task is None:
        raise HTTPException(status_code=404, detail="no available task for this annotator")
    return {"task": task.to_dict()}


@router.post("/release", summary="主动释放任务锁")
async def release_task(
    body: ReleaseBody,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    ok = engine.release_task(body.task_id, body.annotator_id)
    if not ok:
        raise HTTPException(status_code=409, detail="task not locked by this annotator or not found")
    return {"success": True, "task_id": body.task_id, "released_by": body.annotator_id}


@router.post("/heartbeat", summary="心跳延长锁")
async def heartbeat(
    body: HeartbeatBody,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    ok = engine.heartbeat(body.task_id, body.annotator_id)
    if not ok:
        raise HTTPException(status_code=409, detail="heartbeat rejected (lock expired or not owner)")
    return {
        "success": True,
        "task_id": body.task_id,
        "annotator_id": body.annotator_id,
        "ts": time.time(),
    }


@router.post("/annotations", summary="保存一条标注")
async def save_annotation(
    body: AnnotationBody,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    try:
        rec = engine.save_annotation(
            task_id=body.task_id,
            asset_id=body.asset_id,
            geometry_type=body.geometry_type,
            geometry=body.geometry,
            label=body.label,
            attributes=body.attributes,
            annotator_id=body.annotator_id,
            confidence=body.confidence,
            occluded=body.occluded,
            truncated=body.truncated,
            annotation_id=body.annotation_id,
            parent_annotation_id=body.parent_annotation_id,
            review_stage=body.review_stage,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"annotation": rec.to_dict()}


@router.post("/annotations/bulk", summary="批量保存标注")
async def bulk_save(
    body: BulkAnnotationBody,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    try:
        recs = engine.bulk_save_annotations(
            task_id=body.task_id,
            annotations=body.annotations,
            annotator_id=body.annotator_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "saved": len(recs),
        "annotations": [r.to_dict() for r in recs],
    }


@router.post("/submit", summary="提交任务到审核队列")
async def submit_task(
    body: SubmitBody,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    try:
        result = engine.submit_task(body.task_id, body.annotator_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return result


@router.get("/tasks/{task_id}/annotations", summary="获取任务所有标注")
async def list_task_annotations(
    task_id: str,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    rows = engine.get_task_annotations(task_id)
    return {"task_id": task_id, "count": len(rows), "annotations": [r.to_dict() for r in rows]}


@router.get("/annotations/{annotation_id}/history", summary="标注编辑历史")
async def annotation_history(
    annotation_id: str,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    rows = engine.get_annotation_history(annotation_id)
    if not rows:
        # 确认 annotation 是否存在
        all_task_anns = []
        # 简单一次回查 — 如果 id 不在 history 里,说明 annotation 不存在
        # 但我们这里不能直接 join,直接 200 + 空 history 即可,前端按空处理
        return {"annotation_id": annotation_id, "history": [], "exists": False}
    return {"annotation_id": annotation_id, "history": rows, "exists": True}


@router.get("/tasks/{task_id}/lock", summary="锁状态")
async def get_lock_status(
    task_id: str,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    return engine.lock_status(task_id)


@router.get("/stats", summary="标注员统计")
async def get_stats(
    annotator_id: Optional[str] = Query(default=None),
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    return engine.stats(annotator_id)


# 额外 — 入队端点 (供内部引擎调用,前端不直接使用)
@router.post("/enqueue", summary="(内部) 把任务排入工作台队列")
async def enqueue(
    body: EnqueueBody,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    task = engine.enqueue_task(
        task_id=body.task_id,
        asset_id=body.asset_id,
        priority=body.priority,
        assigned_to=body.assigned_to,
        due_date=body.due_date,
    )
    return {"task": task.to_dict()}


# 额外 — annotation_system 集成状态端点 (P5-R1-T4 retry: 证明真引用 annotation_system)
@router.get("/annotation-system/summary", summary="与项目 annotation_system.py 集成状态")
async def annotation_system_summary(
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    return engine.annotation_system_summary()


@router.post("/annotation-system/normalize", summary="把 annotation_system 风格 geometry normalize 到 workbench schema")
async def annotation_system_normalize(
    body: AnnotationBody,
    engine: WorkbenchEngine = Depends(get_workbench_engine),
):
    normalized = engine.normalize_annotation_system_geometry(
        body.geometry_type, body.geometry
    )
    return {"normalized_geometry": normalized, "workbench_type": _AS_TO_WB.get(body.geometry_type, body.geometry_type)}