"""P1-A3-W2: 众包任务定价 + 结算 API (使用 CrowdSettlementEngine 引擎)

端点 (P1-A3 新增, 路径以 /api/v1/crowd/... 区分既有 crowd_settlement_routes.py 的 /api/crowd/settlement/...):
- POST /api/v1/crowd/price                       — 任务定价
- POST /api/v1/crowd/tasks                      — 创建任务
- POST /api/v1/crowd/tasks/{id}/lock            — 接单锁价
- POST /api/v1/crowd/tasks/{id}/settle          — 结算
- GET  /api/v1/crowd/wallet/{worker_id}         — 钱包余额
- POST /api/v1/crowd/withdraw                   — 提现
- GET  /api/v1/crowd/withdraw/history/{worker_id} — 提现历史

注意: 本文件路径前缀是 /api/v1/crowd, 与既有 api/crowd_settlement_routes.py 的
/api/crowd/settlement 不冲突.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field, field_validator

from engines.crowd_settlement import CrowdSettlementEngine, DIFFICULTY_MIN, DIFFICULTY_MAX

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/crowd", tags=["crowd_settlement_v2"])

# 单例 engine
_engine = CrowdSettlementEngine()


# ── Pydantic models ────────────────────────────────────────────────────────

class PriceRequest(BaseModel):
    task_type: str = Field(..., min_length=1, max_length=64)
    difficulty: int = Field(..., ge=DIFFICULTY_MIN, le=DIFFICULTY_MAX)
    deadline_hours: float = Field(..., ge=0.0, le=8760.0)


class CreateTaskRequest(PriceRequest):
    task_id: Optional[str] = Field(default=None, max_length=64)


class LockRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=128)

    @field_validator("worker_id")
    @classmethod
    def _check(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("worker_id 只能包含字母/数字/下划线/连字符")
        return v


class SettleRequest(BaseModel):
    passed: bool = Field(..., description="审核是否通过")
    reviewer: str = Field(default="system", max_length=64)


class WithdrawRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=128)
    amount: float = Field(..., gt=0.0, le=1_000_000.0, description="提现金额, 必须 > 0")

    @field_validator("worker_id")
    @classmethod
    def _check_wid(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("worker_id 只能包含字母/数字/下划线/连字符")
        return v


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/price")
async def price_task(req: PriceRequest):
    """任务定价 (不创建任务, 仅返回价格)."""
    try:
        price = _engine.price_task(req.task_type, req.difficulty, req.deadline_hours)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "ok": True,
        "data": {
            "task_type": req.task_type,
            "difficulty": req.difficulty,
            "deadline_hours": req.deadline_hours,
            "price": price,
        },
    }


@router.post("/tasks", status_code=201)
async def create_task(req: CreateTaskRequest):
    """创建任务 (同步定价)."""
    try:
        task = _engine.create_task(
            task_type=req.task_type,
            difficulty=req.difficulty,
            deadline_hours=req.deadline_hours,
            task_id=req.task_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {
        "ok": True,
        "data": {
            "task_id": task.task_id,
            "task_type": task.task_type,
            "difficulty": task.difficulty,
            "deadline_hours": task.deadline_hours,
            "price": task.price,
            "status": task.status,
        },
    }


@router.post("/tasks/{task_id}/lock")
async def lock_task(task_id: str, req: LockRequest):
    """标注员接单, 锁定价格."""
    try:
        result = _engine.lock_price(task_id, req.worker_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True, "data": result}


@router.post("/tasks/{task_id}/settle")
async def settle_task(task_id: str, req: SettleRequest):
    """结算任务."""
    try:
        result = _engine.settle(task_id, req.passed, req.reviewer)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"ok": True, "data": result}


@router.get("/wallet/{worker_id}")
async def get_wallet(worker_id: str):
    """查询 worker 钱包余额."""
    return {"ok": True, "data": _engine.get_wallet(worker_id)}


@router.post("/withdraw")
async def withdraw(req: WithdrawRequest):
    """提现申请."""
    try:
        result = _engine.withdraw(req.worker_id, req.amount)
    except ValueError as e:
        msg = str(e)
        if "insufficient" in msg:
            raise HTTPException(status_code=422, detail=msg)
        if "positive" in msg:
            raise HTTPException(status_code=422, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "data": result}


@router.get("/withdraw/history/{worker_id}")
async def withdraw_history(worker_id: str):
    """提现历史."""
    history = _engine.withdraw_history(worker_id)
    return {
        "ok": True,
        "data": {
            "worker_id": worker_id,
            "history": history,
            "total": len(history),
        },
    }