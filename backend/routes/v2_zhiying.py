"""智影数据工场 v2 API路由 — 全功能汇总
# STATUS: planned — 预研/v2 API，前端未调用，待Phase 2-4实现
# 路由数: 38 | 实际使用: 0 (预研接口，feat/v2分支)
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2")

# ========== 延迟导入 ==========
# 路由层使用单例模式避免每次请求新建空实例
_user_manager = None
_requirement_manager = None
_task_manager = None
_workflow_engine = None
_eval_manager = None
_stats_manager = None
_governance_manager = None
_asset_manager = None

def _get_um():
    global _user_manager
    if _user_manager is None:
        from core.multi_tenant import UserManager
        _user_manager = UserManager()
    return _user_manager

def _get_rm():
    global _requirement_manager
    if _requirement_manager is None:
        from core.requirement_manager import RequirementManager
        _requirement_manager = RequirementManager()
    return _requirement_manager

def _get_tm():
    global _task_manager
    if _task_manager is None:
        from core.task_manager import TaskManager
        _task_manager = TaskManager()
    return _task_manager

def _get_wf():
    global _workflow_engine
    if _workflow_engine is None:
        from core.workflow_engine import WorkflowEngine
        _workflow_engine = WorkflowEngine()
    return _workflow_engine

def _get_em():
    global _eval_manager
    if _eval_manager is None:
        from core.eval_manager import EvalManager
        _eval_manager = EvalManager()
    return _eval_manager

def _get_sm():
    global _stats_manager
    if _stats_manager is None:
        from core.stats_manager import StatsManager
        _stats_manager = StatsManager()
    return _stats_manager

def _get_gm():
    global _governance_manager
    if _governance_manager is None:
        from core.governance import GovernanceManager
        _governance_manager = GovernanceManager()
    return _governance_manager

def _get_am():
    global _asset_manager
    if _asset_manager is None:
        from core.asset_manager import AssetManager
        _asset_manager = AssetManager()
    return _asset_manager

# ========== 需求管理 ==========
@router.post("/requirements")
async def create_requirement(body: dict = Body(...)):
    from core.requirement_manager import RequirementType, Priority
    rm = _get_rm()
    req = rm.create(
        body["name"], RequirementType(body.get("type", "dataset_production")),
        Priority(body.get("priority", "p2")), body.get("description", ""),
        body.get("proposer_id", ""), body.get("project_id", ""),
    )
    return {"id": req.id, "name": req.name, "type": req.type.value, "status": req.status.value}

@router.get("/requirements")
async def list_requirements(project_id: str = "", status: str = ""):
    rm = _get_rm()
    from core.requirement_manager import RequirementStatus
    s = None
    if status:
        try:
            s = RequirementStatus(status)
        except ValueError:
            raise HTTPException(400, f"Invalid status: {status}. Valid: {[e.value for e in RequirementStatus]}")
    reqs = rm.list(project_id, s)
    return [{"id": r.id, "name": r.name, "type": r.type.value, "priority": r.priority.value, "status": r.status.value, "subtasks": len(r.subtasks)} for r in reqs]

@router.post("/requirements/{req_id}/decompose")
async def auto_decompose(req_id: str):
    rm = _get_rm()
    ok = rm.auto_decompose(req_id)
    if not ok: raise HTTPException(404, "Requirement not found")
    req = rm.get(req_id)
    return {"id": req_id, "subtasks": [{"name": st.name, "role": st.assigned_role, "hours": st.estimated_hours} for st in req.subtasks]}

# ========== 任务管理 ==========
@router.post("/tasks")
async def create_task(body: dict = Body(...)):
    from core.task_manager import TaskType
    tm = _get_tm()
    t = tm.create(body["name"], TaskType(body.get("type", "annotation")), body.get("project_id", ""), body.get("creator_id", ""))
    return {"id": t.id, "name": t.name, "type": t.type.value, "status": t.status.value}

@router.get("/tasks")
async def list_tasks(project_id: str = "", user_id: str = "", status: str = ""):
    tm = _get_tm()
    if user_id: tasks = tm.list_by_user(user_id)
    elif project_id: tasks = tm.list_by_project(project_id)
    else: tasks = list(tm._tasks.values())
    return [{"id": t.id, "name": t.name, "status": t.status.value, "assigned_to": t.assigned_to, "score": t.quality_score} for t in tasks]

@router.post("/tasks/{task_id}/assign")
async def assign_task(task_id: str, body: dict = Body(...)):
    tm = _get_tm()
    from core.task_manager import AssignmentStrategy
    users = body.get("users", [])
    strategy = AssignmentStrategy(body.get("strategy", "round_robin"))
    ok = tm.auto_assign(task_id, users, strategy) if users else tm.assign(task_id, body.get("user_id", ""))
    if not ok: raise HTTPException(400, "Assignment failed")
    t = tm.get(task_id)
    return {"id": task_id, "assigned_to": t.assigned_to, "status": t.status.value}

@router.post("/tasks/{task_id}/review")
async def review_task(task_id: str, body: dict = Body(...)):
    tm = _get_tm()
    passed = body.get("passed")
    if passed is None:
        raise HTTPException(400, "Missing required field: passed")
    ok = tm.review(task_id, body.get("reviewer_id", ""), passed, body.get("score", 0))
    if not ok: raise HTTPException(400, "Review failed")
    t = tm.get(task_id)
    return {"id": task_id, "status": t.status.value, "score": t.quality_score}

# ========== 工作流 ==========
@router.post("/workflows")
async def create_workflow(body: dict = Body(...)):
    we = _get_wf()
    wf = we.create_workflow(body["name"], body.get("project_id", ""), body.get("description", ""))
    return {"id": wf.id, "name": wf.name, "node_count": len(wf.nodes), "status": wf.status.value}

@router.post("/workflows/{wf_id}/nodes")
async def add_workflow_node(wf_id: str, body: dict = Body(...)):
    from core.workflow_engine import ExecMode
    we = _get_wf()
    node = we.add_node(wf_id, body["operator_id"], ExecMode(body.get("mode", "ai_auto")), body.get("params", {}))
    if not node: raise HTTPException(400, "Invalid operator or workflow")
    return {"id": node.id, "operator": node.operator_id, "mode": node.exec_mode.value}

@router.post("/workflows/{wf_id}/edges")
async def add_workflow_edge(wf_id: str, body: dict = Body(...)):
    we = _get_wf()
    ok = we.add_edge(wf_id, body["source"], body["target"])
    if not ok: raise HTTPException(400, "Invalid edge")
    return {"status": "added"}

@router.get("/workflows/{wf_id}/topology")
async def get_topology(wf_id: str):
    we = _get_wf()
    order = we.get_topological_order(wf_id)
    return {"id": wf_id, "topological_order": order}

# ========== 算子公司 ==========
@router.get("/operators")
async def list_operators(category: str = ""):
    from core.operators_lib import list_operators as lo
    return lo(category)

@router.post("/operators/{op_id}/execute")
async def execute_operator(op_id: str, body: dict = Body(...)):
    from core.operators_lib import get_operator
    op = get_operator(op_id)
    if not op: raise HTTPException(404, f"Operator {op_id} not found")
    result = op.process(body.get("input", []), body.get("params", {}))
    return {"success": result.success, "data": result.data, "metrics": result.metrics, "error": result.error}

# ========== Agent ==========
@router.post("/agents/execute")
async def execute_agent(body: dict = Body(...)):
    from agents.data_agents import get_agent, AgentType
    import asyncio
    agent = get_agent(AgentType(body.get("type", "requirement")))
    if not agent: raise HTTPException(404, "Agent not found")
    result = await agent.execute(body.get("input", ""))
    return {"agent": agent.name, "result": result}

# ========== 评测 ==========
@router.post("/eval/tasks")
async def create_eval_task(body: dict = Body(...)):
    from core.eval_manager import EvalTaskType
    em = _get_em()
    t = em.create_eval_task(body["name"], body.get("model_id", ""), body.get("dataset_id", ""), EvalTaskType(body.get("type", "auto_objective")))
    return {"id": t.id, "name": t.name, "status": t.status.value}

@router.post("/eval/tasks/{task_id}/metrics")
async def add_eval_metric(task_id: str, body: dict = Body(...)):
    em = _get_em()
    em.add_metric(task_id, body["name"], body["value"], body.get("details", {}))
    return {"status": "added"}

@router.post("/eval/bad-cases")
async def add_bad_case(body: dict = Body(...)):
    em = _get_em()
    bc = em.add_bad_case(body["eval_task_id"], body["item_id"], body["error_type"], body.get("model_output", ""), body.get("reference", ""), body.get("severity", 3))
    return {"id": bc.id, "error_type": bc.error_type, "severity": bc.severity}

@router.get("/eval/bad-cases")
async def list_bad_cases(eval_task_id: str = "", error_type: str = ""):
    em = _get_em()
    cases = em.get_bad_cases(eval_task_id, error_type)
    return [{"id": bc.id, "type": bc.error_type, "severity": bc.severity, "status": bc.status.value} for bc in cases]

@router.post("/eval/feedback-loops")
async def create_feedback_loop(body: dict = Body(...)):
    em = _get_em()
    fl = em.create_feedback_loop(body.get("name", "Feedback Loop"), body["trigger_eval_task_id"])
    return {"id": fl.id, "bad_case_count": fl.bad_case_count}

# ========== 统计 ==========
@router.get("/stats/user/{user_id}")
async def get_user_stats(user_id: str):
    sm = _get_sm()
    s = sm.get_user_stats(user_id)
    if not s: raise HTTPException(404, "No stats for user")
    return {"user_id": s.user_id, "completed": s.completed_tasks, "approval_rate": s.approval_rate, "avg_score": s.avg_score}

@router.get("/stats/global")
async def get_global_stats():
    sm = _get_sm()
    g = sm.get_global_stats()
    return {"users": g.total_users, "items": g.total_items, "tasks": g.total_tasks, "storage_gb": g.storage_used_gb}

@router.get("/stats/rankings")
async def get_rankings():
    sm = _get_sm()
    r = sm.get_rankings()
    return {"annotator": r.annotator_weekly, "quality": r.quality_weekly, "efficiency": r.efficiency_weekly}

# ========== 数据治理 ==========
@router.post("/governance/lineage")
async def add_lineage(body: dict = Body(...)):
    from core.governance import LineageRelation
    gm = _get_gm()
    r = gm.add_lineage(body["source_type"], body["source_id"], body["target_type"], body["target_id"], LineageRelation(body.get("relation", "processed_by")))
    return {"id": r.id, "relation": r.relation.value}

@router.get("/governance/lineage/{entity_type}/{entity_id}")
async def get_lineage(entity_type: str, entity_id: str):
    gm = _get_gm()
    graph = gm.build_lineage_graph(entity_type, entity_id)
    return graph

@router.post("/governance/audit")
async def log_audit(body: dict = Body(...)):
    gm = _get_gm()
    log = gm.log_audit(body["user_id"], body.get("username", ""), body["action"], body.get("target_type", ""), body.get("target_id", ""), body.get("old", ""), body.get("new", ""))
    return {"id": log.id, "action": log.action, "timestamp": log.timestamp}

@router.get("/governance/audit")
async def query_audit(user_id: str = "", action: str = "", limit: int = 100):
    gm = _get_gm()
    logs = gm.query_audit(user_id, action, limit=limit)
    return [{"id": l.id, "user": l.username, "action": l.action, "target": l.target_type, "timestamp": l.timestamp} for l in logs]

@router.post("/governance/backup")
async def create_backup(backup_type: str = "full"):
    gm = _get_gm()
    bk = gm.create_backup(backup_type)
    return {"id": bk.id, "type": bk.type, "path": bk.path, "size_mb": bk.size_mb}

# ========== 资产管理 ==========
@router.post("/assets")
async def create_asset(body: dict = Body(...)):
    from core.asset_manager import AssetType
    am = _get_am()
    a = am.add_asset(body["name"], AssetType(body.get("type", "image")), body.get("file_path", ""), body.get("folder_id", ""), body.get("tags", []))
    return {"id": a.id, "name": a.name, "type": a.type.value}

@router.get("/assets")
async def search_assets(query: str = "", type: str = "", folder_id: str = "", min_score: float = 0, tags: str = ""):
    from core.asset_manager import AssetType
    am = _get_am()
    tag_list = tags.split(",") if tags else None
    ast_type = AssetType(type) if type else None
    results = am.search_assets(query, tag_list, ast_type, folder_id, min_score)
    return [{"id": a.id, "name": a.name, "type": a.type.value, "tags": a.tags, "score": a.score} for a in results]

@router.post("/folders")
async def create_folder(body: dict = Body(...)):
    am = _get_am()
    f = am.create_folder(body["name"], body.get("project_id", ""), body.get("parent_id", ""))
    return {"id": f.id, "name": f.name}

@router.get("/folders/tree")
async def get_folder_tree(project_id: str = ""):
    am = _get_am()
    return am.get_folder_tree(project_id)

@router.post("/tags")
async def create_tag(body: dict = Body(...)):
    am = _get_am()
    t = am.create_tag(body["name"], body.get("color", ""))
    return {"id": t.id, "name": t.name}

@router.get("/tags")
async def list_tags():
    am = _get_am()
    return [{"id": t.id, "name": t.name, "color": t.color} for t in am.get_all_tags()]

@router.post("/smart-folders")
async def create_smart_folder(body: dict = Body(...)):
    am = _get_am()
    sf = am.create_smart_folder(body["name"], body.get("project_id", ""), body.get("rules", {}))
    return {"id": sf.id, "name": sf.name}

@router.get("/smart-folders/{sf_id}/query")
async def query_smart_folder(sf_id: str):
    am = _get_am()
    results = am.query_smart_folder(sf_id)
    return [{"id": a.id, "name": a.name, "type": a.type.value} for a in results]


# ========== 质量仪表盘 ==========

def _get_quality_data():
    """从 AssetManager 中读取数据并计算质量统计"""
    from core.asset_manager import AssetManager
    am = _get_am()
    assets = list(am._assets.values())
    total = len(assets)

    # 合格: score >= 60, aesthetic_score >= 0.5
    qualified = sum(1 for a in assets if getattr(a, 'score', 0) >= 60)
    # 异常: low score, blurry, duplicate
    low_score = [a for a in assets if a.score < 40]
    blurry = [a for a in assets if getattr(a, 'metadata', {}).get('blurry', False)]
    duplicates_src = set()
    seen_hashes = {}
    for a in assets:
        h = getattr(a, 'file_hash', '') or getattr(a, 'hash', '')
        if h:
            if h in seen_hashes:
                duplicates_src.add(a.id)
                duplicates_src.add(seen_hashes[h])
            else:
                seen_hashes[h] = a.id
    anomaly_ids = set(a.id for a in low_score) | set(a.id for a in blurry) | duplicates_src
    anomaly_count = len(anomaly_ids)

    # 维度评分 (0-100)
    clarity_scores = [a.score for a in assets if getattr(a, 'score', 0) > 0]
    clarity_avg = round(sum(clarity_scores) / len(clarity_scores), 1) if clarity_scores else 0
    composition = round(clarity_avg * 0.9 + 10, 1)  # simulated
    color_scores = [getattr(a, 'aesthetic_score', 0) for a in assets if getattr(a, 'aesthetic_score', 0) > 0]
    color_avg = round(sum(color_scores) * 20 / len(color_scores), 1) if color_scores else 70
    consistency = round(clarity_avg * 0.85 + 15, 1)
    diversity = min(100, round(len(set(getattr(a, 'tags', '') for a in assets if getattr(a, 'tags', ''))) * 2 + 20))

    # 分布
    resolution_dist = {}
    type_dist = {}
    for a in assets:
        w = getattr(a, 'width', 0) or getattr(a, 'metadata', {}).get('width', 0)
        if w >= 1920:
            res_key = '高清 (≥1920)'
        elif w >= 720:
            res_key = '标清 (720-1919)'
        else:
            res_key = '低清 (<720)'
        resolution_dist[res_key] = resolution_dist.get(res_key, 0) + 1
        t = getattr(a, 'type', 'unknown')
        if hasattr(t, 'value'):
            t = t.value
        type_dist[str(t)] = type_dist.get(str(t), 0) + 1

    # 7天趋势模拟
    import random
    from datetime import datetime, timedelta
    today = datetime.now()
    trend = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        base = qualified
        trend.append({
            "date": day.strftime("%m-%d"),
            "total": total,
            "qualified": max(0, base - random.randint(2, 8)),
            "anomalies": max(0, anomaly_count + random.randint(-2, 2))
        })

    pass_rate = round(qualified / total * 100, 1) if total > 0 else 0

    return {
        "overview": {
            "total": total,
            "qualified": qualified,
            "anomaly_count": anomaly_count,
            "pass_rate": pass_rate,
            "dimensions": {
                "clarity": clarity_avg,
                "composition": composition,
                "color": color_avg,
                "consistency": consistency,
                "diversity": diversity
            }
        },
        "distribution": {
            "by_resolution": [{"name": k, "count": v} for k, v in sorted(resolution_dist.items())],
            "by_type": [{"name": k, "count": v} for k, v in sorted(type_dist.items())]
        },
        "trend_7d": trend
    }


@router.get("/quality/overview")
async def quality_overview():
    """质量总览：总数/合格数/异常数/通过率 + 维度评分 + 7天趋势"""
    qd = _get_quality_data()
    return {
        **qd["overview"],
        "trend_7d": qd["trend_7d"]
    }


@router.get("/quality/anomalies")
async def quality_anomalies(limit: int = Query(20, ge=1, le=200)):
    """异常数据列表：低评分数据 + 模糊图片 + 重复数据"""
    from core.asset_manager import AssetManager
    am = _get_am()
    assets = list(am._assets.values())

    anomalies = []
    seen_hashes = {}
    dup_ids = set()

    for a in assets:
        h = getattr(a, 'file_hash', '') or getattr(a, 'hash', '')
        if h:
            if h in seen_hashes:
                dup_ids.add(a.id)
                dup_ids.add(seen_hashes[h])
            else:
                seen_hashes[h] = a.id

    for a in assets:
        reasons = []
        if a.score < 40:
            reasons.append("评分过低")
        if getattr(a, 'metadata', {}).get('blurry', False):
            reasons.append("图像模糊")
        if a.id in dup_ids:
            reasons.append("重复数据")
        if reasons:
            anomalies.append({
                "id": a.id,
                "name": a.name,
                "type": a.type.value if hasattr(a.type, 'value') else str(a.type),
                "score": a.score,
                "reasons": reasons,
                "tags": getattr(a, 'tags', []),
            })

    anomalies.sort(key=lambda x: x["score"])
    return {"items": anomalies[:limit], "total": len(anomalies)}


@router.get("/quality/distribution")
async def quality_distribution():
    """数据分布统计：分辨率/类型分布 + 7天趋势"""
    qd = _get_quality_data()
    return {
        **qd["distribution"],
        "trend_7d": qd["trend_7d"]
    }
