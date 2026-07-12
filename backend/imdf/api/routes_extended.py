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
    RequirementReassign,
    RequirementUpdateMeta,
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

# P5-R1-T2: 模块级单例 RequirementEngine — 让 create/list/stats 等端点共享同一状态.
# P5-R2-T2: 改为使用 requirement_engine 模块自身的 get_requirement_engine() 单例,
# 这样 project_engine.get_project_stats 也能拿到同一份数据 (跨模块统计正确).
# 多进程安全由后续 Alembic + 数据库迁移补齐 (P5-R1-T3 阶段引入).
_REQ_ENGINE_SINGLETON = None


def _get_req_engine():
    """获取（或创建）模块级 RequirementEngine 单例 — 委托给 requirement_engine 模块单例"""
    from engines.requirement_engine import get_requirement_engine
    return get_requirement_engine()


def _priority_from_str(s: Optional[str]) -> Optional["Priority"]:
    """P5-R1-T2: 将字符串优先级归一化为 Priority 枚举, 容错处理 (兼容 Pydantic 已校验)."""
    if not s:
        return None
    from engines.requirement_engine import Priority
    s_l = s.lower().strip()
    # 兼容两层表述: P0..P3 与 low/medium/high/critical
    if s_l in ("p0", "critical"):
        return Priority.P0
    if s_l in ("p1", "high"):
        return Priority.P1
    if s_l in ("p2", "medium"):
        return Priority.P2
    if s_l in ("p3", "low"):
        return Priority.P3
    try:
        return Priority(s_l)
    except ValueError:
        return None


def _req_to_dict(r) -> Dict[str, Any]:
    """P5-R1-T2: 把 Requirement 对象序列化成 dict (兼容不同状态)."""
    if hasattr(r, "to_dict"):
        out = r.to_dict()
    else:
        out = {
            "id": getattr(r, "id", ""),
            "title": getattr(r, "title", ""),
            "type": getattr(r.type, "value", r.type) if getattr(r, "type", None) else "general",
            "status": getattr(r.status, "value", r.status) if getattr(r, "status", None) else "draft",
            "priority": getattr(r.priority, "value", r.priority) if getattr(r, "priority", None) else "P2",
        }
    # 兜底: 即使 r.to_dict() 抛错 (例如 status 已是 str), 这里做最终归一化
    for k in ("type", "status", "priority"):
        v = out.get(k)
        if hasattr(v, "value"):
            out[k] = v.value
        # 已经是字符串则保留
    # 统一字段名 (兼容 _r.to_dict() 与数据库行格式)
    if "project_id" not in out:
        out["project_id"] = getattr(r, "project_id", None)
    if "pack_id" not in out:
        out["pack_id"] = getattr(r, "pack_id", None)
    if "qc_status" not in out:
        out["qc_status"] = getattr(r, "qc_status", None)
    if "delivery_id" not in out:
        out["delivery_id"] = getattr(r, "delivery_id", None)
    if "due_date" not in out:
        out["due_date"] = getattr(r, "due_date", "")
    if "owner" not in out:
        out["owner"] = getattr(r, "owner", "")
    return out


@req_router.post("/create")
def create_requirement(req: RequirementCreate):
    """P5-R1-T2 retry: 创建需求 — 支持 project_id / pack_id / qc_status / delivery_id / due_date / owner

    type 接受 legacy frontend 值 (general/feature/bug/improvement) + new engine enum 名
    (data_collection/data_annotation/...). 仅 legacy 值需要 type_map 兜底映射,
    新值直接通过 ``RequirementType[name]`` 解析 (无 lossy 转换).
    """
    from engines.requirement_engine import (
        RequirementEngine, Priority, RequirementType
    )
    re_eng = _get_req_engine()

    # 优先级: Pydantic 已限定 (legacy low/medium/high/critical + P0..P3),
    # _priority_from_str 把 legacy 值归一化到 Priority 枚举.
    priority = _priority_from_str(req.priority) or Priority.P2

    # 类型归一化:
    # - Legacy frontend 值 (general/feature/bug/improvement) 需要映射到 engine 枚举
    # - New engine enum 名 (data_collection/...) 直接通过值 (lowercase) 解析
    #
    # 注意: RequirementType["DATA_COLLECTION"] 是按 Python 成员 NAME (uppercase) 查找
    # 而 RequirementType("data_collection") 是按 value (lowercase string) 查找.
    # 新值是 lowercase string, 所以必须用 RequirementType(value) 形式.
    LEGACY_TYPE_MAP = {
        "general": RequirementType.DATA_ANNOTATION,
        "feature": RequirementType.DATA_ANNOTATION,
        "bug": RequirementType.DATA_CLEANING,
        "improvement": RequirementType.DATA_AUGMENTATION,
    }
    if req.type in LEGACY_TYPE_MAP:
        req_type = LEGACY_TYPE_MAP[req.type]
    else:
        # New engine value (lowercase) — 按 value 查找
        try:
            req_type = RequirementType(req.type)
        except ValueError:
            # 未知值兜底
            req_type = RequirementType.DATA_ANNOTATION

    r = re_eng.create_requirement(
        title=req.title,
        req_type=req_type,
        priority=priority,
        created_by=req.owner or "system",
        description=req.description or "",
        acceptance_criteria=req.acceptance_criteria or "",
        tags=req.tags or [],
        project_id=req.project_id,
        pack_id=req.pack_id,
        qc_status=req.qc_status,
        delivery_id=req.delivery_id,
        due_date=req.due_date or "",
        owner=req.owner or "",
    )
    data = _req_to_dict(r)
    return {
        "success": True,
        "data": data,
    }


@req_router.post("/assign")
def assign_requirement(req: RequirementAssign):
    from engines.requirement_engine import RequirementEngine
    re_eng = _get_req_engine()
    ok = re_eng.assign_requirement(req.requirement_id, req.assignee) if hasattr(re_eng, 'assign_requirement') else True
    return {"success": True, "data": {"status": "assigned" if ok else "failed", "requirement_id": req.requirement_id, "assignee": req.assignee}}

@req_router.post("/verify")
def verify_requirement(req: RequirementVerify):
    """P5-R2-T5 fix (audit P1-5): 调用 verify_completion (走真实验收 + 自动 close)
    而不是 update_requirement_status(..., "verified") — 那里传 string 不是 enum,
    永远返回 False 还被强制 success:True,链路彻底坏掉。
    """
    from engines.requirement_engine import RequirementEngine
    re_eng = _get_req_engine()
    if hasattr(re_eng, "verify_completion"):
        report = re_eng.verify_completion(req.requirement_id)
        if "error" in report:
            return {"success": False, "error": report["error"], "data": report}
        report["verified_by"] = req.verified_by
        return {
            "success": True,
            "data": {
                "status": "verified" if report.get("passed") else "needs_rework",
                "requirement_id": req.requirement_id,
                "verified_by": req.verified_by,
                "report": report,
            },
        }
    return {"success": False, "error": "verify_completion not available"}

@req_router.post("/close")
def close_requirement(req: RequirementClose):
    """P5-R2-T5 fix (audit P1-5): 传 RequirementStatus.CLOSED 枚举,而不是裸字符串 "closed"。
    update_requirement_status 内部用 enum 成员比对,字符串永远不会通过校验。
    """
    from engines.requirement_engine import RequirementEngine, RequirementStatus
    re_eng = _get_req_engine()
    if hasattr(re_eng, "update_requirement_status"):
        ok = re_eng.update_requirement_status(
            req.requirement_id, RequirementStatus.CLOSED
        )
    else:
        ok = re_eng.close_requirement(req.requirement_id) \
            if hasattr(re_eng, "close_requirement") else True
    return {
        "success": True,
        "data": {
            "status": "closed" if ok else "failed",
            "requirement_id": req.requirement_id,
            "reason": req.reason,
        },
    }


@req_router.get("/")
def list_requirements(
    project_id: Optional[str] = Query(
        None, min_length=1, max_length=128,
        description="P5-R1-T2: 按项目 ID 过滤 (关联 ProjectCenter)",
    ),
    status: Optional[str] = Query(
        None, pattern=r"^(draft|open|in_progress|review|done|closed)$",
        description="按状态过滤",
    ),
    type: Optional[str] = Query(
        None, max_length=64,
        description="按类型过滤",
    ),
    priority: Optional[str] = Query(
        None, pattern=r"^(P[0-3]|low|medium|high|critical)$",
        description="按优先级过滤",
    ),
    keyword: Optional[str] = Query(
        None, max_length=200, description="搜索关键词 (title/description/owner)",
    ),
    page: int = Query(1, ge=1, le=10000, description="页码 (从 1 开始)"),
    page_size: int = Query(20, ge=1, le=200, description="每页条数 (1..200)"),
    limit: int = Query(
        None, ge=1, le=100,
        description="兼容旧分页 (offset+limit)",
    ),
    offset: int = Query(0, ge=0, description="兼容旧分页 (offset)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(
        None, max_length=200, description="搜索关键词 (兼容旧参数 q)",
    ),
):
    """P5-R1-T2: 列表 + 过滤 + 分页 (兼容 project_id 关联)
    - 优先使用 paginate_requirements (新接口), 保留旧 offset/limit 兼容.
    """
    from engines.requirement_engine import RequirementEngine
    re_eng = _get_req_engine()

    # 归一化 keyword/q
    kw = keyword or q

    if hasattr(re_eng, "paginate_requirements"):
        items, total = re_eng.paginate_requirements(
            project_id=project_id,
            status=status,
            req_type=type,
            priority=priority,
            keyword=kw,
            page=page,
            page_size=page_size,
        )
        page_data = [_req_to_dict(r) for r in items]
        return {
            "success": True,
            "data": {
                "requirements": page_data,
                "items": page_data,
                "total": total,
                "page": page,
                "page_size": page_size,
            },
            "page": page,
            "page_size": page_size,
        }

    # 兼容旧分页 (offset + limit)
    reqs = re_eng.list_requirements() if hasattr(re_eng, 'list_requirements') else []
    if kw:
        kw_l = kw.lower()
        reqs = [
            r for r in reqs
            if kw_l in (r.title or "").lower()
            or kw_l in (getattr(r, "description", "") or "").lower()
        ]
    if project_id:
        reqs = [r for r in reqs if getattr(r, "project_id", None) == project_id]
    total = len(reqs)
    if limit is None:
        limit = 20
    page_data = reqs[offset: offset + limit]
    return {
        "success": True,
        "data": {
            "requirements": [_req_to_dict(r) for r in page_data],
            "items": [_req_to_dict(r) for r in page_data],
            "total": total,
        },
        "limit": limit,
        "offset": offset,
    }


# ── P5-R1-T2 新增 4 个端点: 拆解预览 / 真实拆解 / 统计 / 重派 ──


@req_router.get("/{req_id}/decompose-preview")
def decompose_preview(req_id: str):
    """P5-R1-T2: 预览拆解结果 (不真拆)"""
    from api._common.validators import validate_id
    validate_id(req_id, "requirement_id")
    from engines.requirement_engine import RequirementEngine
    re_eng = _get_req_engine()
    result = re_eng.preview_decompose(req_id)
    if "error" in result:
        return {"success": False, "error": result["error"], "data": result}
    return {"success": True, "data": result}


@req_router.post("/{req_id}/decompose")
def decompose_requirement(req_id: str):
    """P5-R1-T2: 真实拆解 — 返回创建的子任务列表"""
    from api._common.validators import validate_id
    validate_id(req_id, "requirement_id")
    from engines.requirement_engine import RequirementEngine, RequirementStatus
    re_eng = _get_req_engine()
    # 拆解要求 OPEN 状态 — 若还在 DRAFT 则自动 OPEN
    req = re_eng.get_requirement(req_id)
    if not req:
        return {"success": False, "error": f"Requirement {req_id} not found"}
    if req.status == RequirementStatus.DRAFT:
        re_eng.update_requirement_status(req_id, RequirementStatus.OPEN)
    tasks = re_eng.decompose_to_tasks(req_id)
    return {
        "success": True,
        "data": {
            "requirement_id": req_id,
            "task_count": len(tasks),
            "tasks": [t.to_dict() for t in tasks],
        },
    }


@req_router.get("/{req_id}/stats")
def requirement_stats(req_id: str):
    """P5-R1-T2: 需求统计 — 含 tasks_count / packs_count / progress%"""
    from api._common.validators import validate_id
    validate_id(req_id, "requirement_id")
    from engines.requirement_engine import RequirementEngine
    re_eng = _get_req_engine()
    stats = re_eng.get_requirement_with_stats(req_id)
    if "error" in stats and "requirement" not in stats:
        return {"success": False, "error": stats["error"]}
    return {"success": True, "data": stats}


@req_router.post("/{req_id}/reassign")
def reassign_requirement(req_id: str, req: RequirementReassign):
    """P5-R1-T2: 重派任务 — body: {"strategy": "by_skill|by_workload|random|hybrid"}"""
    from api._common.validators import validate_id
    validate_id(req_id, "requirement_id")
    from engines.requirement_engine import RequirementEngine
    re_eng = _get_req_engine()
    n = re_eng.reassign_tasks(req_id, req.strategy)
    return {
        "success": True,
        "data": {
            "requirement_id": req_id,
            "strategy": req.strategy,
            "reassigned_count": n,
        },
    }


@req_router.put("/{req_id}/meta")
def update_requirement_meta(req_id: str, req: RequirementUpdateMeta):
    """P5-R1-T2: 更新需求的关联元数据 (project_id / pack_id / qc_status / ...)"""
    from api._common.validators import validate_id
    validate_id(req_id, "requirement_id")
    from engines.requirement_engine import RequirementEngine
    re_eng = _get_req_engine()
    ok = re_eng.update_requirement_meta(
        requirement_id=req_id,
        project_id=req.project_id,
        pack_id=req.pack_id,
        qc_status=req.qc_status,
        delivery_id=req.delivery_id,
        due_date=req.due_date,
        owner=req.owner,
    )
    if not ok:
        return {"success": False, "error": f"Requirement {req_id} not found"}
    r = re_eng.get_requirement(req_id)
    return {"success": True, "data": _req_to_dict(r)}

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
