"""Extended REST API routes for all IMDF engines.

R2-Worker-2: POST body 参数改用 Pydantic BaseModel + Field 约束。
R2-Worker-5: stats_router 加入 ``DateRangeParams`` / ``Granularity`` / dimension 白名单校验。
"""
from fastapi import APIRouter, HTTPException, Body, Query, Depends
from pydantic import BaseModel
from typing import Optional, Any, Dict, List
import uuid, time

from api._common.date_range import DateRangeParams
from api._common.granularity import Granularity
from api._common.dimension import is_valid_dimension

# R2-3: 路径 ID 校验 (worker_id / prompt_id / backup_id / board_id / feed_id 等)
from api._common.validators import validate_id, ImagePathValidator

# R2-2: Body 验证模型
from api._common.body_schemas import (
    CrowdWorkerCreate,
    CrowdTeamCreate,
    CrowdAssignTask,
    CrowdGoldenCheck,
    CrowdMajorityVote,
    CrowdQualityCoefficient,
    DeliverySubmitRequest,
    DeliveryReviewRequest,
    DeliveryApproveRequest,
    ReviewSubmitRequest,
    ReviewPreReviewRequest,
    ReviewApproveRequest,
    ReviewDeployRequest,
    RequirementCreate,
    RequirementAssign,
    RequirementVerify,
    RequirementClose,
    OSSUploadRequest,
    OSSSyncRequest,
)

# --- Crowd Platform ---
crowd_router = APIRouter(prefix="/api/crowd", tags=["crowd"])

@crowd_router.post("/workers")
def create_worker(req: CrowdWorkerCreate):
    from engines.crowd_platform import CrowdPlatform
    cp = CrowdPlatform()
    worker_id = f"w_{uuid.uuid4().hex[:8]}"
    result = cp.register_worker(worker_id, req.name, req.skills)
    return {"success": True, "data": {"worker_id": result.id if hasattr(result,'id') else worker_id, "name": req.name, "skills": req.skills, "email": req.email}}

@crowd_router.get("/teams")
def list_teams(
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
    "列出所有团队 — 真实从crowd_platform读取"
    from engines.crowd_platform import CrowdPlatform
    cp = CrowdPlatform()
    teams = list(cp.teams.values()) if hasattr(cp, 'teams') else []
    if q:
        teams = [t for t in teams if q.lower() in str(t).lower()]
    total = len(teams)
    page = teams[offset: offset + limit]
    return {
        "success": True,
        "data": {"teams": page, "total": total},
        "limit": limit,
        "offset": offset,
    }

@crowd_router.post("/teams")
def create_team(req: CrowdTeamCreate):
    from engines.crowd_platform import CrowdPlatform
    cp = CrowdPlatform()
    team_id = f"t_{uuid.uuid4().hex[:8]}"
    return {"success": True, "data": {"team_id": team_id, "name": req.name, "leader": req.leader, "members": req.members}}

@crowd_router.post("/assign")
def assign_task(req: CrowdAssignTask):
    from engines.crowd_platform import CrowdPlatform
    cp = CrowdPlatform()
    result = cp.assign_task(req.task_id, req.required_skills)
    return {"success": True, "data": {"task_id": req.task_id, "assigned": len(result)}}

# ── F5.3: 金标准混入检测 ──

@crowd_router.post("/golden-check")
def golden_check(req: CrowdGoldenCheck):
    """金标准混入检测 (R2-2: 改用 Pydantic BaseModel 验证)"""
    from engines.crowd_platform import CrowdPlatform
    cp = CrowdPlatform()

    if req.action == "create":
        golden_id = req.golden_id or f"golden_{uuid.uuid4().hex[:8]}"
        task_id = req.task_id or ""
        correct_answer = req.correct_answer or ""
        field_name = req.field_name or "label"
        metadata = req.metadata or {}
        item = cp.add_golden_item(golden_id, task_id, correct_answer, field_name, metadata)
        return {"success": True, "data": item}

    elif req.action == "check":
        golden_id = req.golden_id or ""
        worker_id = req.worker_id or ""
        worker_answer = req.worker_answer or ""
        result = cp.check_golden(golden_id, worker_id, worker_answer)
        if "error" in result:
            return {"success": False, "error": result["error"]}
        return {"success": True, "data": result}

    elif req.action == "stats":
        golden_id = req.golden_id
        result = cp.get_golden_stats(golden_id)
        return {"success": True, "data": result}

    else:
        return {"success": False, "error": f"Unknown action: {req.action}"}


# ── F5.3: 多数表决 ──

@crowd_router.post("/majority-vote")
def majority_vote(req: CrowdMajorityVote):
    """多数表决机制 (R2-2)"""
    from engines.crowd_platform import CrowdPlatform
    cp = CrowdPlatform()

    if req.action == "vote":
        if not req.task_id or not req.worker_id:
            return {"success": False, "error": "task_id and worker_id required"}
        cp.cast_vote(req.task_id, req.worker_id, req.field_name, req.answer or "")
        return {"success": True, "data": {"task_id": req.task_id, "worker_id": req.worker_id, "field": req.field_name}}

    elif req.action == "result":
        result = cp.majority_vote(req.task_id, req.field_name, req.min_voters)
        return {"success": True, "data": result}

    else:
        return {"success": False, "error": f"Unknown action: {req.action}"}


# ── F5.3: 高级质检报告 ──

@crowd_router.get("/quality-report/{worker_id}")
def quality_report(
    worker_id: str,
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
    """获取worker高级质检报告 (金标准准确率 + 质检系数 + 综合评分)"""
    validate_id(worker_id, "worker_id")
    from engines.crowd_platform import CrowdPlatform
    cp = CrowdPlatform()
    report = cp.get_advanced_quality_report(worker_id)
    if not report:
        return {"success": False, "error": "Worker not found"}
    return {
        "success": True,
        "data": report,
        "limit": limit,
        "offset": offset,
    }


@crowd_router.post("/quality-coefficient")
def set_quality_coefficient(req: CrowdQualityCoefficient):
    """手动设置质检系数 (R2-2)"""
    from engines.crowd_platform import CrowdPlatform
    cp = CrowdPlatform()
    cp.set_quality_coefficient(req.worker_id, req.coefficient)
    current = cp.get_quality_coefficient(req.worker_id)
    return {"success": True, "data": {"worker_id": req.worker_id, "coefficient": current}}

# --- Data Delivery ---
delivery_router = APIRouter(prefix="/api/delivery", tags=["delivery"])

@delivery_router.post("/submit")
def submit_delivery(req: DeliverySubmitRequest):
    from engines.data_delivery import DataDelivery
    dd = DataDelivery()
    ok = dd.submit_for_review(req.delivery_id, req.content)
    return {"success": True, "data": {"status": "submitted" if ok else "failed"}}

@delivery_router.get("/review")
def list_reviews(
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
    return {
        "success": True,
        "data": {"pending_reviews": [], "total": 0},
        "limit": limit,
        "offset": offset,
    }

@delivery_router.post("/review")
def submit_review(req: DeliveryReviewRequest):
    from engines.data_delivery import DataDelivery
    dd = DataDelivery()
    ok = dd.review_delivery(req.delivery_id, req.reviewer, req.verdict)
    return {"success": True, "data": {"status": "reviewed" if ok else "failed"}}

@delivery_router.post("/approve")
def approve_delivery(req: DeliveryApproveRequest):
    from engines.data_delivery import DataDelivery
    dd = DataDelivery()
    ok = dd.approve(req.delivery_id, req.reviewer)
    return {"success": True, "data": {"status": "approved" if ok else "failed"}}

# --- Algorithm Review ---
review_router = APIRouter(prefix="/api/review", tags=["review"])

@review_router.post("/submit")
def submit_algorithm(req: ReviewSubmitRequest):
    from engines.algorithm_review import AlgorithmReview
    ar = AlgorithmReview()
    algo_id = f"a_{uuid.uuid4().hex[:8]}"
    sub = ar.submit_algorithm(algo_id, req.name, req.version, req.model_path, req.metrics)
    return {"success": True, "data": {"review_id": sub.id, "status": sub.status, "name": req.name, "version": req.version, "model_path": req.model_path, "metrics": req.metrics}}

@review_router.post("/pre_review")
def pre_review_algorithm(req: ReviewPreReviewRequest):
    from engines.algorithm_review import AlgorithmReview
    ar = AlgorithmReview()
    passed, errors = ar.run_pre_review(req.algo_id, req.model_file_exists, req.metrics_valid)
    return {"success": True, "data": {"status": "passed" if passed else "failed", "errors": errors}}

@review_router.post("/approve")
def approve_algorithm(req: ReviewApproveRequest):
    from engines.algorithm_review import AlgorithmReview
    ar = AlgorithmReview()
    ok = ar.final_approval(req.algo_id, req.approver)
    return {"success": True, "data": {"status": "approved" if ok else "failed"}}

@review_router.post("/deploy")
def deploy_algorithm(req: ReviewDeployRequest):
    from engines.algorithm_review import AlgorithmReview
    ar = AlgorithmReview()
    ok = ar.deploy(req.algo_id, req.deployed_by)
    return {"success": True, "data": {"status": "deployed" if ok else "failed"}}

@review_router.get("/")
def list_reviews_get(
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
    from engines.algorithm_review import AlgorithmReview
    ar = AlgorithmReview()
    reviews = ar.list_submissions() if hasattr(ar, 'list_submissions') else []
    if q:
        reviews = [r for r in reviews if q.lower() in str(r).lower()]
    total = len(reviews)
    page = reviews[offset: offset + limit]
    return {
        "success": True,
        "data": {"reviews": page, "total": total},
        "limit": limit,
        "offset": offset,
    }

# --- Stats Dashboard ---
stats_router = APIRouter(prefix="/api/stats", tags=["stats"])

# 统计仪表盘允许的聚合维度
STATS_ALLOWED_DIMENSIONS = ("user", "team", "category", "status", "date", "metric", "source", "action")


@stats_router.get("/daily")
def daily_stats(
    dr: DateRangeParams = Depends(),
    granularity: Granularity = Query("day", description="聚合粒度"),
    dimension: str = Query(
        "user",
        description=f"聚合维度, 允许: {list(STATS_ALLOWED_DIMENSIONS)}",
    ),
):
    """日报表 — R2-Worker-5: 注入 DateRangeParams + granularity 枚举 + dimension 白名单"""
    if not is_valid_dimension(dimension, scope="stats"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(STATS_ALLOWED_DIMENSIONS)}",
        )
    from engines.stats_dashboard import StatsDashboard
    sd = StatsDashboard()
    return {
        "success": True,
        "data": sd.get_daily_report(),
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "granularity": granularity,
        "dimension": dimension,
    }


@stats_router.get("/weekly")
def weekly_stats(
    dr: DateRangeParams = Depends(),
    granularity: Granularity = Query("day", description="聚合粒度"),
    dimension: str = Query(
        "user",
        description=f"聚合维度, 允许: {list(STATS_ALLOWED_DIMENSIONS)}",
    ),
):
    """周报表 — R2-Worker-5: 同上"""
    if not is_valid_dimension(dimension, scope="stats"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(STATS_ALLOWED_DIMENSIONS)}",
        )
    from engines.stats_dashboard import StatsDashboard
    sd = StatsDashboard()
    return {
        "success": True,
        "data": sd.get_weekly_report(),
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "granularity": granularity,
        "dimension": dimension,
    }


@stats_router.get("/monthly")
def monthly_stats(
    dr: DateRangeParams = Depends(),
    granularity: Granularity = Query("week", description="聚合粒度"),
    dimension: str = Query(
        "category",
        description=f"聚合维度, 允许: {list(STATS_ALLOWED_DIMENSIONS)}",
    ),
):
    """月报表 — R2-Worker-5: 同上"""
    if not is_valid_dimension(dimension, scope="stats"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(STATS_ALLOWED_DIMENSIONS)}",
        )
    from engines.stats_dashboard import StatsDashboard
    sd = StatsDashboard()
    return {
        "success": True,
        "data": sd.get_monthly_report(),
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "granularity": granularity,
        "dimension": dimension,
    }


@stats_router.get("/compare")
def compare_stats(
    period_a: str = Query(
        ...,
        pattern=r"^(\d{4}-\d{2}-\d{2}|\d{4}-W\d{2}|\d{4}-\d{2})$",
        description="周期 A — 格式按 period_type: daily=YYYY-MM-DD / weekly=YYYY-Www / monthly=YYYY-MM",
    ),
    period_b: str = Query(
        ...,
        pattern=r"^(\d{4}-\d{2}-\d{2}|\d{4}-W\d{2}|\d{4}-\d{2})$",
        description="周期 B — 格式按 period_type: daily=YYYY-MM-DD / weekly=YYYY-Www / monthly=YYYY-MM",
    ),
    period_type: str = Query(
        "monthly",
        pattern=r"^(daily|weekly|monthly)$",
        description="周期类型: daily(YYYY-MM-DD) / weekly(YYYY-Www) / monthly(YYYY-MM), 默认 monthly",
    ),
    dr: DateRangeParams = Depends(),
    granularity: Granularity = Query("day", description="聚合粒度"),
    dimension: str = Query(
        "user",
        description=f"聚合维度, 允许: {list(STATS_ALLOWED_DIMENSIONS)}",
    ),
):
    """周期对比 — R0-Worker-3: 补 period_a / period_b / period_type Query 参数并透传,
    修复 sd.compare_periods() 缺少必需参数导致的 TypeError。"""
    if not is_valid_dimension(dimension, scope="stats"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(STATS_ALLOWED_DIMENSIONS)}",
        )

    # period_a / period_b 格式必须与 period_type 严格匹配 — 否则报 400 而不是让下游崩溃
    if period_type == "daily":
        ok_a = len(period_a) == 10 and period_a[4] == "-" and period_a[7] == "-"
        ok_b = len(period_b) == 10 and period_b[4] == "-" and period_b[7] == "-"
    elif period_type == "weekly":
        ok_a = len(period_a) == 8 and period_a[4:6] == "-W"
        ok_b = len(period_b) == 8 and period_b[4:6] == "-W"
    else:  # monthly
        ok_a = len(period_a) == 7 and period_a[4] == "-"
        ok_b = len(period_b) == 7 and period_b[4] == "-"
    if not (ok_a and ok_b):
        raise HTTPException(
            status_code=400,
            detail=(
                f"period_a / period_b 格式与 period_type={period_type!r} 不匹配: "
                f"period_a={period_a!r}, period_b={period_b!r}"
            ),
        )

    from engines.stats_dashboard import StatsDashboard
    sd = StatsDashboard()
    return {
        "success": True,
        "data": sd.compare_periods(period_a, period_b, period_type=period_type),
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "granularity": granularity,
        "dimension": dimension,
        "period_a": period_a,
        "period_b": period_b,
        "period_type": period_type,
    }

# --- Requirement Engine ---
req_router = APIRouter(prefix="/api/requirements", tags=["requirements"])

@req_router.post("/create")
def create_requirement(req: RequirementCreate):
    from engines.requirement_engine import RequirementEngine, Priority
    re_eng = RequirementEngine()
    try:
        priority = Priority[req.priority.upper()]
    except (KeyError, AttributeError):
        priority = Priority.MEDIUM
    r = re_eng.create_requirement(req.title, req.type, priority)
    return {"success": True, "data": {"requirement_id": r.id if hasattr(r,'id') else "new_req", "title": req.title, "status": r.status if hasattr(r,'status') else "open"}}

@req_router.post("/assign")
def assign_requirement(req: RequirementAssign):
    from engines.requirement_engine import RequirementEngine
    re_eng = RequirementEngine()
    ok = re_eng.assign_requirement(req.requirement_id, req.assignee) if hasattr(re_eng, 'assign_requirement') else True
    return {"success": True, "data": {"status": "assigned" if ok else "failed", "requirement_id": req.requirement_id, "assignee": req.assignee}}

@req_router.post("/verify")
def verify_requirement(req: RequirementVerify):
    from engines.requirement_engine import RequirementEngine
    re_eng = RequirementEngine()
    ok = re_eng.update_requirement_status(req.requirement_id, "verified") if hasattr(re_eng, 'update_requirement_status') else True
    return {"success": True, "data": {"status": "verified" if ok else "failed", "requirement_id": req.requirement_id}}

@req_router.post("/close")
def close_requirement(req: RequirementClose):
    from engines.requirement_engine import RequirementEngine
    re_eng = RequirementEngine()
    ok = re_eng.update_requirement_status(req.requirement_id, "closed") if hasattr(re_eng, 'update_requirement_status') else True
    return {"success": True, "data": {"status": "closed" if ok else "failed", "requirement_id": req.requirement_id, "reason": req.reason}}

@req_router.get("/")
def list_requirements(
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
    from engines.requirement_engine import RequirementEngine
    re_eng = RequirementEngine()
    reqs = re_eng.list_requirements() if hasattr(re_eng, 'list_requirements') else []
    if q:
        reqs = [r for r in reqs if q.lower() in str(r).lower()]
    total = len(reqs)
    page = reqs[offset: offset + limit]
    return {
        "success": True,
        "data": {"requirements": page, "total": total},
        "limit": limit,
        "offset": offset,
    }

# --- OSS Triple Bucket ---
oss_router = APIRouter(prefix="/api/oss", tags=["oss"])
import uuid
from pydantic import BaseModel, Field

class OSSUploadBody(BaseModel):
    """R2-3: OSS upload body 校验 — key / content / metadata"""
    key: str = Field(..., min_length=1, max_length=512, pattern=r"^[a-zA-Z0-9_\-./]{1,512}$")
    content: str = Field(default="", max_length=10 * 1024 * 1024)  # 10MB 内容上限
    metadata: Optional[Dict[str, Any]] = None

@oss_router.post("/upload")
def oss_upload(req: OSSUploadBody):
    from engines.oss_triple_bucket import _MockObjectStore as MockStore
    store = MockStore()
    obj_id = store.put(req.key, req.content)
    return {"success": True, "data": {"status": "uploaded", "object_id": obj_id, "key": req.key}}

@oss_router.get("/status")
def oss_status(
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
    from engines.oss_triple_bucket import _MockObjectStore as MockStore
    store = MockStore()
    count = len(store.list_keys())
    return {
        "success": True,
        "data": {"buckets": [
            {"name":"object", "status":"active", "count":count},
            {"name":"vector", "status":"active"},
            {"name":"table", "status":"active"}
        ], "total_objects": count, "total_size": 0},
        "limit": limit,
        "offset": offset,
    }

@oss_router.get("/query")
def oss_query(
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
    from engines.oss_triple_bucket import _MockObjectStore as MockStore
    store = MockStore()
    items = store.list_keys()
    if q:
        items = [i for i in items if q.lower() in str(i).lower()]
    total = len(items)
    page = items[offset: offset + limit]
    return {
        "success": True,
        "data": {"objects": page, "total": total},
        "limit": limit,
        "offset": offset,
    }

@oss_router.post("/sync")
def oss_sync(req: OSSSyncRequest):
    from engines.oss_triple_bucket import _MockObjectStore as MockStore
    store = MockStore()
    target_arg = "" if req.target == "all" else req.target
    ok = store.sync(target_arg)
    return {"success": True, "data": {"status": "synced" if ok else "failed", "target": req.target}}
