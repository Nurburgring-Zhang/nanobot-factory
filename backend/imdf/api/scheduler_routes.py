"""
Phase3: Scheduler API Routes — Agent主动驱动
=========================================
REST API for managing scheduled cron/interval jobs.

Endpoints:
  GET    /api/scheduler/jobs          — 任务列表
  POST   /api/scheduler/jobs          — 创建定时任务
  GET    /api/scheduler/jobs/{id}     — 任务详情
  DELETE /api/scheduler/jobs/{id}     — 删除任务
  POST   /api/scheduler/jobs/{id}/run — 手动触发
  POST   /api/scheduler/jobs/{id}/pause   — 暂停
  POST   /api/scheduler/jobs/{id}/resume  — 恢复
  GET    /api/scheduler/history       — 执行历史
  GET    /api/scheduler/history/{job_id}  — 特定任务历史
  GET    /api/scheduler/health        — 调度器状态

R2 改造:
  - 路径 ID 用 validate_task_id
  - cron 表达式校验 (R2-Worker-4)
  - Query 分页 + 时间范围 (R2-Worker-4)
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from api._common.cron_validator import validate_trigger_config
from api._common.task_id_validator import validate_task_id
from api._common.scheduler_validators import SchedulerHistoryParams

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


# ─── Request/Response Models ────────────────────────────────────────────────

class CreateJobRequest(BaseModel):
    """创建定时任务请求"""
    name: str = Field(..., min_length=1, max_length=128, description="任务名称")
    func_path: str = Field(
        ...,
        min_length=3,
        max_length=512,
        pattern=r"^[a-zA-Z_][a-zA-Z0-9_\.]*$",
        description="可调用路径, e.g. 'engines.scheduler_engine.task_health_check'",
    )
    trigger_type: str = Field("cron", pattern="^(cron|interval|date)$",
                              description="触发类型: cron / interval / date")
    trigger_config: dict = Field(
        default_factory=dict,
        description=(
            "触发配置: cron={cron_expression:'0 3 * * *'} "
            "或 interval={hours:2} "
            "或 date={run_date:'2025-01-01T00:00:00'}"
        ),
    )
    args: list = Field(default_factory=list, max_length=64)
    kwargs: dict = Field(default_factory=dict)
    enabled: bool = Field(True)
    max_retries: int = Field(3, ge=0, le=10)
    retry_delay: int = Field(60, ge=1, le=3600, description="重试间隔(秒)")
    notify_on_failure: bool = Field(True)


class JobResponse(BaseModel):
    """任务响应"""
    id: str = ""
    name: str = ""
    next_run: Optional[str] = None
    trigger: str = "cron"
    trigger_config: dict = {}
    enabled: bool = True
    max_retries: int = 3
    retry_delay: int = 60
    notify_on_failure: bool = True
    last_run: Optional[str] = None
    last_status: Optional[str] = None
    func_path: str = ""
    args: list = []
    kwargs: dict = {}
    created_at: str = ""


class HistoryItem(BaseModel):
    """历史记录项"""
    id: str = ""
    job_id: str = ""
    job_name: str = ""
    run_at: str = ""
    status: str = "running"
    result: str = ""
    error: str = ""
    retry_count: int = 0
    duration_ms: int = 0


# ─── Helpers ────────────────────────────────────────────────────────────────

def _get_scheduler():
    """获取调度器引擎单例"""
    from engines.scheduler_engine import get_scheduler
    return get_scheduler()


def _scheduler_ready():
    """检查调度器是否运行中"""
    try:
        sched = _get_scheduler()
        return sched.running
    except Exception:
        return False


# ─── Routes ─────────────────────────────────────────────────────────────────

@router.get("/health")
async def scheduler_health():
    """调度器健康状态"""
    sched = _get_scheduler()
    job_count = len(sched.list_jobs())
    return {
        "status": "ok" if sched.running else "stopped",
        "running": sched.running,
        "job_count": job_count,
        "db_path": sched._db_path,
    }


@router.get("/jobs")
async def list_jobs(
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
    """获取所有定时任务列表 (R2.5-W1: Pydantic Query 验证)"""
    sched = _get_scheduler()
    jobs = sched.list_jobs()
    if q:
        ql = q.lower()
        jobs = [j for j in jobs if ql in str(j).lower()]
    total = len(jobs)
    if sort_by:
        jobs.sort(
            key=lambda j: j.get(sort_by, "") if isinstance(j, dict) else "",
            reverse=(order == "desc"),
        )
    page = jobs[offset: offset + limit]
    return {"success": True, "data": page, "total": total, "limit": limit, "offset": offset}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """获取单个任务详情"""
    validate_task_id(job_id, "job_id")
    sched = _get_scheduler()
    job = sched.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return {"success": True, "data": job}


@router.post("/jobs")
async def create_job(req: CreateJobRequest):
    """创建新的定时任务"""
    from engines.scheduler_engine import JobDefinition

    # R2 改造: 委托给 validate_trigger_config, 拒绝非法 cron / interval / date 配置
    validate_trigger_config(req.trigger_type, req.trigger_config, "trigger_config")

    job_def = JobDefinition(
        name=req.name,
        func_path=req.func_path,
        trigger_type=req.trigger_type,
        trigger_config=req.trigger_config,
        args=req.args,
        kwargs=req.kwargs,
        enabled=req.enabled,
        max_retries=req.max_retries,
        retry_delay=req.retry_delay,
        notify_on_failure=req.notify_on_failure,
    )

    try:
        sched = _get_scheduler()
        job_id = sched.add_job(job_def)
        return {"success": True, "data": {"id": job_id, "name": req.name}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create job: {e}")


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """删除定时任务"""
    validate_task_id(job_id, "job_id")
    sched = _get_scheduler()
    # Prevent deleting preset jobs
    if job_id.startswith("preset_"):
        raise HTTPException(status_code=403,
            detail="Cannot delete preset jobs. Use pause instead.")
    if sched.remove_job(job_id):
        return {"success": True, "data": {"id": job_id, "deleted": True}}
    raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")


@router.post("/jobs/{job_id}/run")
async def run_job_now(job_id: str):
    """手动触发任务立即执行"""
    validate_task_id(job_id, "job_id")
    sched = _get_scheduler()
    result = sched.run_job_now(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return {
        "success": True,
        "data": {"job_id": job_id, "triggered": True},
        "message": f"Job '{job_id}' triggered. Check /api/scheduler/history/{job_id} for results."
    }


@router.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str):
    """暂停定时任务"""
    validate_task_id(job_id, "job_id")
    sched = _get_scheduler()
    if sched.pause_job(job_id):
        return {"success": True, "data": {"id": job_id, "paused": True}}
    raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")


@router.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str):
    """恢复定时任务"""
    validate_task_id(job_id, "job_id")
    sched = _get_scheduler()
    if sched.resume_job(job_id):
        return {"success": True, "data": {"id": job_id, "resumed": True}}
    raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")


@router.get("/history")
async def get_history(
    p: SchedulerHistoryParams = Depends(),
):
    """获取任务执行历史 — R2 改造: 用 SchedulerHistoryParams 校验 (job_id + 日期 + 状态 + 分页)"""
    sched = _get_scheduler()
    offset = p.skip
    items = sched.get_history(
        job_id=p.job_id, limit=p.limit, offset=offset,
        start=p.start.isoformat() if p.start else None,
        end=p.end.isoformat() if p.end else None,
        status=p.status,
    )
    total = sched.get_history_count(job_id=p.job_id)
    return {
        "success": True,
        "data": {
            "items": items,
            "total": total,
            "page": (p.skip // max(p.limit, 1)) + 1,
            "size": p.limit,
            "pages": max(1, (total + p.limit - 1) // p.limit),
        }
    }


@router.get("/history/{job_id}")
async def get_job_history(
    job_id: str,
    p: SchedulerHistoryParams = Depends(),
):
    """获取特定任务的执行历史"""
    validate_task_id(job_id, "job_id")
    sched = _get_scheduler()
    offset = p.skip
    items = sched.get_history(
        job_id=job_id, limit=p.limit, offset=offset,
        start=p.start.isoformat() if p.start else None,
        end=p.end.isoformat() if p.end else None,
        status=p.status,
    )
    total = sched.get_history_count(job_id=job_id)
    return {
        "success": True,
        "data": {
            "items": items,
            "total": total,
            "page": (p.skip // max(p.limit, 1)) + 1,
            "size": p.limit,
            "pages": max(1, (total + p.limit - 1) // p.limit),
        }
    }


@router.get("/presets")
async def list_presets():
    """列出预置任务模板"""
    from engines.scheduler_engine import PRESET_JOBS
    presets = []
    for jd in PRESET_JOBS:
        presets.append({
            "id": jd.id,
            "name": jd.name,
            "trigger_type": jd.trigger_type,
            "trigger_config": jd.trigger_config,
            "func_path": jd.func_path,
            "max_retries": jd.max_retries,
        })
    return {"success": True, "data": presets}
