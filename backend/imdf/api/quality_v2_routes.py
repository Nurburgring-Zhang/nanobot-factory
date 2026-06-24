"""
商用级数据生产质量API路由 — 5环节全覆盖
寻源/采集/清洗/筛选/审核

R2-Worker-5: /review/queue-stats 与 /summary 加入 DateRangeParams / Granularity / dimension 白名单。
"""
from fastapi import APIRouter, Query, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Tuple
import json

from api._common.date_range import DateRangeParams
from api._common.granularity import Granularity
from api._common.dimension import is_valid_dimension

router = APIRouter(prefix="/api/quality/v2", tags=["production_quality"])

# 质量模块允许的聚合维度
QUALITY_ALLOWED_DIMENSIONS = ("category", "industry", "format", "score", "stage", "date")


# ═══════════════════════════════════════════════════════════════
# 1. 寻源质量 (Discovery Quality)
# ═══════════════════════════════════════════════════════════════

class SourceScoreRequest(BaseModel):
    sources: List[Dict] = Field(..., description="数据源列表")

class SourcePreviewRequest(BaseModel):
    preview_data: List[Dict]
    expected_schema: Optional[Dict] = None

class CredibilityRequest(BaseModel):
    source: Dict
    cross_validation: Optional[List[Dict]] = None

class CrossValidationRequest(BaseModel):
    sources_data: Dict[str, List[Dict]]  # {"source_A": [...], "source_B": [...]}
    key_field: str = "label"

class LLMSourceEvalRequest(BaseModel):
    source: Dict
    criteria: Optional[List[str]] = None


@router.post("/discovery/score")
async def score_sources(req: SourceScoreRequest):
    """批量评估数据源质量(A/B/C/D分级)"""
    from engines.discovery_quality import get_discovery_quality
    engine = get_discovery_quality()
    scores = engine.batch_score(req.sources)
    report = engine.quality_report(req.sources)
    return {
        "success": True,
        "scores": [
            {
                "source_id": s.source_id,
                "reliability": s.reliability,
                "freshness": s.freshness,
                "license_compliance": s.license_compliance,
                "community_activity": s.community_activity,
                "overall": s.overall,
                "tier": s.tier
            }
            for s in scores
        ],
        "report": report
    }


@router.post("/discovery/score-single")
async def score_single_source(req: CredibilityRequest):
    """单个数据源质量评分"""
    from engines.discovery_quality import get_discovery_quality
    score = get_discovery_quality().score_source(req.source)
    return {
        "success": True,
        "score": {
            "source_id": score.source_id,
            "reliability": score.reliability,
            "freshness": score.freshness,
            "license_compliance": score.license_compliance,
            "community_activity": score.community_activity,
            "overall": score.overall,
            "tier": score.tier
        }
    }


@router.post("/discovery/preview-quality")
async def check_preview_quality(req: SourcePreviewRequest):
    """源数据预览质量检查"""
    from engines.discovery_quality import get_preview_checker
    result = get_preview_checker().check_preview_quality(
        req.preview_data, req.expected_schema
    )
    return {"success": True, "result": result}


@router.post("/discovery/credibility")
async def assess_credibility(req: CredibilityRequest):
    """数据源可信度评估(A/B/C/D)"""
    from engines.discovery_quality import get_credibility_tier
    result = get_credibility_tier().assess_credibility(req.source, req.cross_validation)
    return {"success": True, "result": result}


@router.post("/discovery/cross-validation")
async def cross_validate_sources(req: CrossValidationRequest):
    """多源交叉验证一致性(IAA)"""
    from engines.discovery_quality import get_cross_validator
    result = get_cross_validator().compute_multi_source_agreement(
        req.sources_data, req.key_field
    )
    return {"success": True, "result": result}


@router.post("/discovery/cross-validation/anomalies")
async def detect_source_anomalies(req: CrossValidationRequest):
    """检测多源数据中的异常/冲突"""
    from engines.discovery_quality import get_cross_validator
    anomalies = get_cross_validator().detect_anomalies(
        req.sources_data, req.key_field
    )
    return {"success": True, "anomalies": anomalies, "count": len(anomalies)}


@router.post("/discovery/llm-evaluate")
async def llm_evaluate_source(req: LLMSourceEvalRequest):
    """LLM辅助评估数据源质量"""
    from engines.discovery_quality import LLMSourceEvaluator
    result = LLMSourceEvaluator.evaluate_source_with_llm(req.source, req.criteria)
    return {"success": True, "result": result}


# ═══════════════════════════════════════════════════════════════
# 2. 采集质量 (Collection Quality)
# ═══════════════════════════════════════════════════════════════

class IntegrityRequest(BaseModel):
    file_pairs: List[Tuple[str, str]]  # [(original, collected), ...]

class ResumeCheckRequest(BaseModel):
    download_dir: str
    expected_files: List[str]

class CollectionDedupRequest(BaseModel):
    filepaths: List[str]
    check_levels: Optional[List[str]] = ["md5", "phash"]

class CollectionSessionStart(BaseModel):
    session_id: str = ""
    metadata: Optional[Dict] = None

class CollectionItemRecord(BaseModel):
    session_id: str
    item_result: Dict


@router.post("/collection/integrity/verify")
async def verify_integrity(req: IntegrityRequest):
    """批量校验采集文件完整性(bytes/MD5/SHA256)"""
    from engines.collection_quality import get_integrity_checker
    result = get_integrity_checker().batch_verify(req.file_pairs)
    return {"success": True, "result": result}


@router.post("/collection/integrity/single")
async def verify_single_integrity(original_path: str, collected_path: str):
    """单文件完整性校验"""
    from engines.collection_quality import get_integrity_checker
    result = get_integrity_checker().verify_file_integrity(original_path, collected_path)
    return {"success": True, "result": result}


@router.post("/collection/resume/check")
async def check_resume_state(req: ResumeCheckRequest):
    """检查断点续传状态"""
    from engines.collection_quality import get_resume_verifier
    state = get_resume_verifier().check_resume_state(req.download_dir, req.expected_files)
    return {"success": True, "state": state}


@router.post("/collection/resume/plan")
async def generate_resume_plan(req: ResumeCheckRequest):
    """生成断点续传计划"""
    from engines.collection_quality import get_resume_verifier
    state = get_resume_verifier().check_resume_state(req.download_dir, req.expected_files)
    plan = get_resume_verifier().generate_resume_plan(state)
    return {"success": True, "state": state, "plan": plan}


@router.post("/collection/dedup/check")
async def check_collection_duplicates(req: CollectionDedupRequest):
    """采集阶段重复检测"""
    from engines.collection_quality import get_collection_dedup
    engine = get_collection_dedup()
    results = [engine.check_duplicate(fp, req.check_levels) for fp in req.filepaths]
    duplicates = [r for r in results if r["is_duplicate"]]
    return {
        "success": True,
        "total": len(req.filepaths),
        "duplicates": len(duplicates),
        "dup_rate": round(len(duplicates) / len(req.filepaths), 4) if req.filepaths else 0,
        "results": results
    }


@router.post("/collection/dedup/stats")
async def collection_dedup_stats():
    """采集去重缓存统计"""
    from engines.collection_quality import get_collection_dedup
    stats = get_collection_dedup().get_stats()
    return {"success": True, "stats": stats}


@router.post("/collection/dedup/clear")
async def clear_dedup_cache():
    """清空采集去重缓存"""
    from engines.collection_quality import get_collection_dedup
    get_collection_dedup().clear()
    return {"success": True, "message": "去重缓存已清空"}


@router.post("/collection/monitor/start")
async def start_collection_session(req: CollectionSessionStart):
    """开始采集监控会话"""
    from engines.collection_quality import get_collection_monitor
    import uuid
    sid = req.session_id or str(uuid.uuid4())[:8]
    sid = get_collection_monitor().start_session(sid, req.metadata)
    return {"success": True, "session_id": sid}


@router.post("/collection/monitor/record")
async def record_collection_item(req: CollectionItemRecord):
    """记录采集条目结果"""
    from engines.collection_quality import get_collection_monitor
    get_collection_monitor().record_item(req.session_id, req.item_result)
    return {"success": True}


@router.post("/collection/monitor/end")
async def end_collection_session(session_id: str = Query(...)):
    """结束采集会话并生成报告"""
    from engines.collection_quality import get_collection_monitor
    report = get_collection_monitor().end_session(session_id)
    return {"success": True, "report": report}


@router.get("/collection/monitor/current")
async def current_collection_stats(
    session_id: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="会话 ID (白名单字符)",
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
    """获取当前采集实时统计"""
    from engines.collection_quality import get_collection_monitor
    stats = get_collection_monitor().get_current_stats(session_id)
    return {
        "success": True,
        "stats": stats,
        "session_id": session_id,
        "limit": limit,
        "offset": offset,
    }


@router.get("/collection/monitor/history")
async def collection_history(
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
    """获取采集监控历史"""
    from engines.collection_quality import get_collection_monitor
    history = get_collection_monitor().get_history(limit)
    if q:
        history = [h for h in history if q.lower() in str(h).lower()]
    total = len(history)
    if sort_by:
        history = sorted(
            history, key=lambda h: h.get(sort_by, "") if isinstance(h, dict) else "",
            reverse=(order == "desc"),
        )
    page = history[offset:]
    return {
        "success": True,
        "history": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/collection/llm-evaluate")
async def llm_evaluate_collection(collection_report: Dict):
    """LLM辅助评估采集质量"""
    from engines.collection_quality import LLMCollectionEvaluator
    result = LLMCollectionEvaluator.evaluate_collection_quality(collection_report)
    return {"success": True, "result": result}


# ═══════════════════════════════════════════════════════════════
# 3. 清洗质量 (Cleaning Quality)
# ═══════════════════════════════════════════════════════════════

class CleaningQualityRequest(BaseModel):
    filepaths: List[str]
    level: str = "perceptual"  # exact / perceptual / semantic

class GoldenPairsRequest(BaseModel):
    filepaths: List[str]
    golden_pairs: List[Dict]  # [{"file_a":..., "file_b":..., "should_dedup": bool}, ...]

class CleaningAuditRequest(BaseModel):
    before_files: List[str]
    after_files: List[str]
    sample_pairs: int = 5


@router.post("/cleaning/quality-report")
async def cleaning_quality_report(req: CleaningQualityRequest):
    """生成清洗质量报告(清洗率/各层效果)"""
    from engines.enhanced_engines import DedupEngine, DedupLevel
    engine = DedupEngine()
    level_map = {"exact": DedupLevel.EXACT, "perceptual": DedupLevel.PERCEPTUAL, "semantic": DedupLevel.SEMANTIC}
    level = level_map.get(req.level, DedupLevel.PERCEPTUAL)
    report = engine.cleaning_quality_report(req.filepaths, level)
    return {"success": True, "report": report}


@router.post("/cleaning/golden-validate")
async def validate_with_golden(req: GoldenPairsRequest):
    """Golden data校验清洗效果(Precision/Recall/F1)"""
    from engines.enhanced_engines import DedupEngine
    engine = DedupEngine()
    pairs = [(g["file_a"], g["file_b"], g["should_dedup"]) for g in req.golden_pairs]
    result = engine.validate_with_golden(req.filepaths, pairs)
    return {"success": True, "result": result}


@router.post("/cleaning/audit")
async def cleaning_audit(req: CleaningAuditRequest):
    """清洗前后对比审计"""
    from engines.enhanced_engines import DedupEngine
    engine = DedupEngine()
    audit = engine.cleaning_audit(req.before_files, req.after_files, req.sample_pairs)
    return {"success": True, "audit": audit}


# ═══════════════════════════════════════════════════════════════
# 4. 筛选质量 (Filter Quality)
# ═══════════════════════════════════════════════════════════════

class GoldenSetLoadRequest(BaseModel):
    items: List[Dict]  # [{"item": {...}, "expected_pass": bool, "filter_name": "..."}]

class EvaluateFilterRequest(BaseModel):
    predictions: List[bool]
    ground_truth: List[bool]

class MultiDimEvalRequest(BaseModel):
    filter_results: Dict[str, List[bool]]  # {"resolution_check": [...], ...}
    ground_truth: List[bool]

class ABTestStartRequest(BaseModel):
    test_id: str
    filter_a_config: Dict
    filter_b_config: Dict
    test_items: List[Dict]

class ABTestRecordRequest(BaseModel):
    test_id: str
    result_a: bool
    result_b: bool
    item_id: str = ""
    ground_truth: Optional[bool] = None

class LLMJudgeFilterRequest(BaseModel):
    filter_name: str
    items: List[Dict]
    results: List[bool]
    sample_size: int = 10

class LLMCompareRulesRequest(BaseModel):
    rules_a: str
    rules_b: str
    sample_items: List[Dict]


@router.post("/filter/golden/load")
async def load_golden_set(req: GoldenSetLoadRequest):
    """加载金标准筛选数据集"""
    from engines.filter_quality import get_filter_quality
    get_filter_quality().load_golden_set(req.items)
    return {"success": True, "count": len(req.items)}


@router.get("/filter/golden/list")
async def list_golden_set(
    filter_name: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="筛选器名 (白名单字符)",
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
    """列出金标准筛选数据"""
    from engines.filter_quality import get_filter_quality
    items = get_filter_quality().get_golden_set(filter_name)
    if q:
        items = [it for it in items if q.lower() in str(it).lower()]
    total = len(items)
    page = items[offset: offset + limit]
    return {
        "success": True,
        "count": total,
        "items": page,
        "filter_name": filter_name,
        "limit": limit,
        "offset": offset,
    }


@router.post("/filter/evaluate")
async def evaluate_filter(req: EvaluateFilterRequest):
    """计算筛选精度(Precision/Recall/F1/Specificity)"""
    from engines.filter_quality import get_filter_quality
    metrics = get_filter_quality().evaluate_filter(req.predictions, req.ground_truth)
    return {"success": True, "metrics": metrics.to_dict()}


@router.post("/filter/multi-dimension")
async def multi_dimension_evaluate(req: MultiDimEvalRequest):
    """多维度筛选评估"""
    from engines.filter_quality import FilterQualityEngine
    result = FilterQualityEngine.multi_dimension_evaluate(
        req.filter_results, req.ground_truth
    )
    return {"success": True, "result": result}


@router.post("/filter/ab-test/start")
async def start_ab_test(req: ABTestStartRequest):
    """启动筛选规则A/B测试"""
    from engines.filter_quality import get_filter_quality
    tid = get_filter_quality().start_ab_test(
        req.test_id, req.filter_a_config, req.filter_b_config, req.test_items
    )
    return {"success": True, "test_id": tid}


@router.post("/filter/ab-test/record")
async def record_ab_test(req: ABTestRecordRequest):
    """记录A/B测试结果"""
    from engines.filter_quality import get_filter_quality
    get_filter_quality().record_ab_result(
        req.test_id, req.result_a, req.result_b, req.item_id, req.ground_truth
    )
    return {"success": True}


@router.post("/filter/ab-test/conclude")
async def conclude_ab_test(test_id: str = Query(...),
                           ground_truth: Optional[List[bool]] = None):
    """结束A/B测试并生成对比报告"""
    from engines.filter_quality import get_filter_quality
    result = get_filter_quality().conclude_ab_test(test_id, ground_truth)
    return {"success": True, "result": result}


@router.post("/filter/llm-judge")
async def llm_judge_filter(req: LLMJudgeFilterRequest):
    """LLM评估筛选结果"""
    from engines.filter_quality import LLMFilterJudge
    result = LLMFilterJudge.judge_filter_results(
        req.filter_name, req.items, req.results, req.sample_size
    )
    return {"success": True, "result": result}


@router.post("/filter/llm-compare-rules")
async def llm_compare_filter_rules(req: LLMCompareRulesRequest):
    """LLM比较两套筛选规则"""
    from engines.filter_quality import LLMFilterJudge
    result = LLMFilterJudge.compare_filter_rules(
        req.rules_a, req.rules_b, req.sample_items
    )
    return {"success": True, "result": result}


@router.post("/filter/report")
async def generate_filter_report(filter_name: str = Query(...),
                                 golden_eval: Optional[Dict] = None,
                                 ab_test_result: Optional[Dict] = None,
                                 llm_judgment: Optional[Dict] = None,
                                 dimension_eval: Optional[Dict] = None):
    """生成筛选质量综合报告"""
    from engines.filter_quality import get_filter_reporter
    report = get_filter_reporter().generate_report(
        filter_name, golden_eval, ab_test_result, llm_judgment, dimension_eval
    )
    return {"success": True, "report": report}


# ═══════════════════════════════════════════════════════════════
# 5. 审核质量 (Review Quality)
# ═══════════════════════════════════════════════════════════════

class SubmitReviewRequest(BaseModel):
    item: Dict
    priority: int = 2
    reviewer_id: Optional[str] = None

class ProcessReviewRequest(BaseModel):
    item_id: str
    reviewer_id: str
    decision: str  # approve / reject / return
    comments: str = ""
    decision_data: Optional[Dict] = None

class ReviewerAgreementRequest(BaseModel):
    reviewer_decisions: Dict[str, List[str]]

class LLMFlagRequest(BaseModel):
    annotations: List[Dict]
    criteria: Optional[List[str]] = None


@router.post("/review/submit")
async def submit_for_review(req: SubmitReviewRequest):
    """提交标注到多级审核队列(初审→复审→终审)"""
    from engines.annotation_quality import get_pipeline
    result = get_pipeline().submit_for_review(
        req.item, req.priority, req.reviewer_id
    )
    return {"success": True, "result": result}


@router.post("/review/process")
async def process_review(req: ProcessReviewRequest):
    """处理审核(通过/驳回/退回修改)"""
    from engines.annotation_quality import get_pipeline
    result = get_pipeline().process_review(
        req.item_id, req.reviewer_id, req.decision,
        req.comments, req.decision_data
    )
    return {"success": result.get("success", False), "result": result}


@router.get("/review/queue-stats")
async def review_queue_stats(
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
    dr: DateRangeParams = Depends(),
    granularity: Granularity = Query("day", description="聚合粒度"),
    dimension: str = Query(
        "stage",
        description=f"聚合维度, 允许: {list(QUALITY_ALLOWED_DIMENSIONS)}",
    ),
):
    """审核队列统计(积压/流转状态)

    R2-Worker-5: 注入 DateRangeParams + granularity 枚举 + dimension 白名单 (保留 R2-1 已加的
    分页/排序/搜索参数)。
    """
    if not is_valid_dimension(dimension, scope="quality"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(QUALITY_ALLOWED_DIMENSIONS)}",
        )
    from engines.annotation_quality import get_pipeline
    stats = get_pipeline().get_review_queue_stats()
    return {
        "success": True,
        "stats": stats,
        "limit": limit,
        "offset": offset,
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "granularity": granularity,
        "dimension": dimension,
    }


@router.post("/review/reviewer-agreement")
async def reviewer_agreement(req: ReviewerAgreementRequest):
    """审核员一致性(Kappa)"""
    from engines.annotation_quality import AnnotationPipeline
    result = AnnotationPipeline.reviewer_agreement(req.reviewer_decisions)
    return {"success": True, "result": result}


@router.get("/review/efficiency")
async def review_efficiency(
    reviewer_id: Optional[str] = Query(
        None, pattern=r"^[a-zA-Z0-9_\-]{1,64}$", description="审核员 ID (白名单字符)",
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
    """审核效率统计(审核速度/通过率/积压量)"""
    from engines.annotation_quality import get_pipeline
    report = get_pipeline().efficiency_report(reviewer_id)
    return {
        "success": True,
        "report": report,
        "reviewer_id": reviewer_id,
        "limit": limit,
        "offset": offset,
    }


@router.post("/review/llm-flag")
async def llm_flag_suspicious(req: LLMFlagRequest):
    """LLM辅助审核: 自动标记可疑标注"""
    from engines.annotation_quality import AnnotationPipeline
    result = AnnotationPipeline.llm_flag_suspicious(req.annotations, req.criteria)
    return {"success": True, "result": result}


# ═══════════════════════════════════════════════════════════════
# 综合报告
# ═══════════════════════════════════════════════════════════════

@router.get("/summary")
async def quality_summary(
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
    dr: DateRangeParams = Depends(),
    granularity: Granularity = Query("day", description="聚合粒度"),
    dimension: str = Query(
        "stage",
        description=f"聚合维度, 允许: {list(QUALITY_ALLOWED_DIMENSIONS)}",
    ),
):
    """数据生产全链路质量概览

    R2-Worker-5: 注入 DateRangeParams + granularity 枚举 + dimension 白名单 (保留 R2-1 已加的
    分页/排序/搜索参数)。
    """
    if not is_valid_dimension(dimension, scope="quality"):
        raise HTTPException(
            status_code=400,
            detail=f"dimension {dimension!r} 不在白名单, 允许: {list(QUALITY_ALLOWED_DIMENSIONS)}",
        )
    return {
        "success": True,
        "pipeline_stages": {
            "discovery": {
                "endpoint_prefix": "/api/quality/v2/discovery",
                "capabilities": ["质量评分", "预览检查", "可信度分级", "多源交叉验证", "LLM评估"],
                "metrics": ["源可靠性", "更新频率", "许可证合规", "社区活跃度", "IAA一致性"]
            },
            "collection": {
                "endpoint_prefix": "/api/quality/v2/collection",
                "capabilities": ["完整性校验", "断点续传", "重复检测", "速度监控"],
                "metrics": ["bytes对比", "checksum", "成功率", "吞吐量", "P95延迟"]
            },
            "cleaning": {
                "endpoint_prefix": "/api/quality/v2/cleaning",
                "capabilities": ["质量报告", "Golden校验", "清洗审计"],
                "metrics": ["清洗率", "Precision", "Recall", "F1", "误清洗率"]
            },
            "filtering": {
                "endpoint_prefix": "/api/quality/v2/filter",
                "capabilities": ["精度评估", "A/B Test", "LLM评估", "多维评估"],
                "metrics": ["Precision", "Recall", "F1", "Specificity", "Accuracy"]
            },
            "review": {
                "endpoint_prefix": "/api/quality/v2/review",
                "capabilities": ["多级审核", "一致性(Kappa)", "效率统计", "LLM标记"],
                "metrics": ["Cohen Kappa", "通过率", "审核速度", "积压量"]
            }
        },
        "limit": limit,
        "offset": offset,
        "range": {"start": str(dr.start), "end": str(dr.end)},
        "granularity": granularity,
        "dimension": dimension,
    }
