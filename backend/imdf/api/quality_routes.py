"""
商用级5环节质量增强 API路由
===========================
覆盖: 模型评测 / 数据分类 / 检索 / 预览 / 传输

R2 改造: 全部 POST/PUT/PATCH 端点改用 Pydantic BaseModel + Field 约束,
失败 → HTTP 422 with structured errors。

路由:
  POST   /api/quality/eval/benchmark-report      — 模型评测综合报告
  POST   /api/quality/eval/ab-test                — A/B分流评测
  POST   /api/quality/eval/consistency            — 评测一致性
  POST   /api/quality/eval/llm-judge              — LLM-as-Judge评测
  GET    /api/quality/eval/benchmarks             — 支持的Benchmark列表

  POST   /api/quality/classify/accuracy           — 分类精度评估
  POST   /api/quality/classify/confusion          — 混淆矩阵
  POST   /api/quality/classify/reliability        — 分类可靠性评分
  POST   /api/quality/classify/llm-verify         — LLM验证分类
  GET    /api/quality/classify/industry           — 行业对标

  POST   /api/quality/search/metrics              — 检索质量指标
  POST   /api/quality/search/dedup               — 检索去重
  POST   /api/quality/search/relevance-compare   — 相关性对比
  POST   /api/quality/search/llm-verify          — LLM验证检索
  GET    /api/quality/search/latency             — 延迟监控
  GET    /api/quality/search/industry            — 行业对标

  GET    /api/quality/preview/formats             — 格式支持报告
  POST   /api/quality/preview/validate            — 预览质量验证
  GET    /api/quality/preview/perf                — 预览性能基准
  GET    /api/quality/preview/perf-by-format      — 按格式性能
  GET    /api/quality/preview/industry            — 行业对标
  POST   /api/quality/preview/bench-reset         — 重置性能基准

  POST   /api/quality/transfer/verify             — 传输完整性验证
  POST   /api/quality/transfer/verify-batch       — 批量验证
  POST   /api/quality/transfer/speed-record       — 记录传输速度
  GET    /api/quality/transfer/speed-stats        — 传输速度统计
  GET    /api/quality/transfer/checkpoints        — 断点续传列表
  POST   /api/quality/transfer/url-audit          — URL安全审计
  POST   /api/quality/transfer/url-audit-batch    — 批量URL审计
  GET    /api/quality/transfer/industry           — 行业对标
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

# R2-3: 路径 ID 校验 (industry 等)
from api._common.validators import validate_id

from api._common.body_schemas import (
    IAAReportRequest as IARequest,
    CohenKappaRequest,
    FleissKappaRequest,
    GoldAddRequest as GoldItem,
    GoldValidateRequest,
    PEJudgeRequest,
    ABTestRequest,
    PipelineRunRequest as PipelineRequest,
    EvalResultsRequest,
    EvalConsistencyRequest,
    LLMJudgeRequest,
    ABEvalRequest,
    AccuracyRequest,
    ReliabilityRequest,
    LLMClassifyVerifyRequest,
    SearchMetricRequest,
    DedupRequest,
    RelevanceCompareRequest,
    SearchLLMVerifyRequest,
    PreviewValidateRequest,
    TransferVerifyRequest,
    TransferVerifyBatchRequest,
    SpeedRecordRequest,
    URLAuditRequest,
    URLAuditBatchRequest,
    ConfirmPayload,
)

router = APIRouter(prefix="/api/quality", tags=["quality"])

# ============================================================
# ─── 原有标注质量路由 (保留向后兼容) ──────────────────────────
# ============================================================

@router.post("/iaa/report")
async def iaa_report(req: IARequest):
    from engines.annotation_quality import get_iaa
    return {"success": True, "report": get_iaa().agreement_report(req.annotations)}

@router.post("/iaa/cohen-kappa")
async def cohen_kappa(req: CohenKappaRequest):
    from engines.annotation_quality import get_iaa
    k = get_iaa().cohen_kappa(req.rater1, req.rater2)
    quality = "excellent" if k > 0.81 else "good" if k > 0.61 else "moderate" if k > 0.41 else "fair" if k > 0.21 else "poor"
    return {"success": True, "kappa": round(k, 4), "quality": quality}

@router.post("/iaa/fleiss-kappa")
async def fleiss_kappa(req: FleissKappaRequest):
    from engines.annotation_quality import get_iaa
    k = get_iaa().fleiss_kappa(req.ratings, req.n_categories)
    return {"success": True, "kappa": round(k, 4)}

@router.post("/gold/add")
async def add_gold_item(req: GoldItem):
    from engines.annotation_quality import get_gold
    get_gold().add_gold_item(req.item, req.ground_truth)
    return {"success": True}

@router.post("/gold/validate")
async def validate_annotator(req: GoldValidateRequest):
    from engines.annotation_quality import get_gold
    return {"success": True, "result": get_gold().validate_annotator(req.annotations)}

@router.post("/judge/pe")
async def judge_pe(req: PEJudgeRequest):
    from engines.annotation_quality import LLMJudgeEngine
    return {"success": True, "judgment": LLMJudgeEngine.judge_single_pe(req.pe_text, req.eval_type)}

@router.post("/judge/ab-test")
async def ab_test(req: ABTestRequest):
    from engines.annotation_quality import LLMJudgeEngine
    return {"success": True, "result": LLMJudgeEngine.ab_test_pe(req.pe_a, req.pe_b, req.test_cases)}

@router.post("/pipeline/run")
async def run_pipeline(req: PipelineRequest):
    from engines.annotation_quality import get_pipeline
    pl = get_pipeline()
    results = {"items": req.items, "stages": {}}
    pre_annotated = [pl.pre_annotate(item, {}) for item in req.items]
    results["stages"]["pre_annotate"] = len(pre_annotated)
    reviewed = pl.review(pre_annotated, {})
    results["stages"]["review"] = {"total": len(reviewed), "flagged": sum(1 for r in reviewed if r.get("status") == "flagged")}
    flagged = [r for r in reviewed if r.get("status") == "flagged"]
    adjudicated = pl.adjudicate(flagged)
    results["stages"]["adjudicate"] = len(adjudicated)
    audit = pl.audit(results)
    results["stages"]["audit"] = audit
    feedback = pl.feedback_loop(audit)
    results["stages"]["feedback"] = feedback
    return {"success": True, "pipeline": results}

@router.get("/schemas")
async def list_schemas(
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
    from engines.annotation_quality import INDUSTRY_SCHEMAS
    schemas = {k: {"name": v["name"], "standard": v["standard"]} for k, v in INDUSTRY_SCHEMAS.items()}
    if q:
        schemas = {k: v for k, v in schemas.items() if q.lower() in k.lower() or q.lower() in (v.get("name", "") or "").lower()}
    total = len(schemas)
    items = list(schemas.items())
    if sort_by == "name":
        items.sort(key=lambda kv: kv[1].get("name", ""), reverse=(order == "desc"))
    page = dict(items[offset: offset + limit])
    return {
        "success": True,
        "schemas": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@router.get("/schemas/{industry}")
async def get_schema(
    industry: str,
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
    validate_id(industry, "industry")
    from engines.annotation_quality import INDUSTRY_SCHEMAS
    schema = INDUSTRY_SCHEMAS.get(industry)
    if not schema:
        return {"success": False, "error": f"行业 {industry} 不存在。可用: {list(INDUSTRY_SCHEMAS.keys())}"}
    return {
        "success": True,
        "schema": schema,
        "limit": limit,
        "offset": offset,
    }


# ============================================================
# ─── 1. 模型评测 (Model Eval) ───────────────────────────────
# ============================================================


@router.post("/eval/benchmark-report")
async def eval_benchmark_report(req: EvalResultsRequest):
    """综合评测报告 (包含Benchmark评估+一致性+LLM评判)"""
    from engines.eval_quality import get_eval_reporter, EvalQualityReporter
    report = EvalQualityReporter.generate_report(
        results=req.results,
        benchmark=req.benchmark,
        include_consistency=len(req.results) > 50,
        include_llm_judge=True,
    )
    return {"success": True, "report": report}

@router.post("/eval/ab-test")
async def eval_ab_test(req: ABEvalRequest):
    """A/B分流评测"""
    from engines.eval_quality import ABTestConfig, get_ab_test_engine
    config = ABTestConfig(
        test_name=req.test_name,
        variant_a=req.variant_a,
        variant_b=req.variant_b,
        benchmark=req.benchmark,
    )
    result = get_ab_test_engine().run_ab_test(req.results_a, req.results_b, config)
    return {"success": True, "result": result}

@router.post("/eval/consistency")
async def eval_consistency(req: EvalConsistencyRequest):
    """评测一致性分析"""
    from engines.eval_quality import get_eval_consistency
    report = get_eval_consistency().consistency_report(req.results, req.n_runs)
    return {"success": True, "report": report}

@router.post("/eval/llm-judge")
async def eval_llm_judge(req: LLMJudgeRequest):
    """LLM-as-Judge自动评测"""
    from engines.eval_quality import get_llm_judge
    judgment = get_llm_judge().judge_batch(req.items)
    return {"success": True, "judgment": judgment}

@router.get("/eval/benchmarks")
async def eval_list_benchmarks(
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
    """获取支持的Benchmark列表"""
    from engines.eval_quality import BenchmarkRunner, BENCHMARK_CONFIGS, INDUSTRY_EVAL
    benchmarks = BenchmarkRunner.list_benchmarks()
    if q:
        benchmarks = [b for b in benchmarks if q.lower() in b.lower()]
    total = len(benchmarks)
    if sort_by:
        benchmarks = sorted(benchmarks, reverse=(order == "desc"))
    page = benchmarks[offset: offset + limit]
    return {
        "success": True,
        "benchmarks": page,
        "total": total,
        "industry_eval": INDUSTRY_EVAL,
        "limit": limit,
        "offset": offset,
    }


# ============================================================
# ─── 2. 数据分类 (Classification) ───────────────────────────
# ============================================================


@router.post("/classify/accuracy")
async def classify_accuracy(req: AccuracyRequest):
    """分类精度评估 (Accuracy/Precision/Recall/F1/mAP)"""
    from engines.classification_engine import ClassificationQualityEngine
    result = ClassificationQualityEngine.precision_recall_f1(req.predictions, req.ground_truth)
    return {"success": True, "metrics": result}

@router.post("/classify/confusion")
async def classify_confusion(req: AccuracyRequest):
    """混淆矩阵分析"""
    from engines.classification_engine import ClassificationQualityEngine
    result = ClassificationQualityEngine.confusion_matrix(req.predictions, req.ground_truth)
    return {"success": True, "confusion_matrix": result}

@router.post("/classify/reliability")
async def classify_reliability(req: ReliabilityRequest):
    """分类器可靠性评分 (ECE校准)"""
    from engines.classification_engine import ClassificationQualityEngine
    result = ClassificationQualityEngine.reliability_score(req.predictions)
    return {"success": True, "reliability": result}

@router.post("/classify/llm-verify")
async def classify_llm_verify(req: LLMClassifyVerifyRequest):
    """LLM验证分类结果"""
    from engines.classification_engine import LLMClassificationVerifier
    result = LLMClassificationVerifier.verify_batch(req.items, req.predictions, req.ground_truths)
    return {"success": True, "verification": result}

@router.get("/classify/industry")
async def classify_industry(
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
    """行业对标"""
    from engines.classification_engine import INDUSTRY_CLASSIFICATION
    industry = INDUSTRY_CLASSIFICATION
    if q:
        q_lower = q.lower()
        if isinstance(industry, dict):
            industry = {k: v for k, v in industry.items() if q_lower in str(k).lower() or q_lower in str(v).lower()}
        elif isinstance(industry, list):
            industry = [x for x in industry if q_lower in str(x).lower()]
    total = len(industry) if hasattr(industry, "__len__") else 0
    if sort_by and isinstance(industry, dict):
        items = sorted(
            industry.items(), key=lambda kv: str(kv[1]),
            reverse=(order == "desc"),
        )
        industry = dict(items[offset: offset + limit])
    elif isinstance(industry, list):
        industry = industry[offset: offset + limit]
    return {
        "success": True,
        "industry": industry,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ============================================================
# ─── 3. 检索 (Search) ───────────────────────────────────────
# ============================================================


@router.post("/search/metrics")
async def search_metrics(req: SearchMetricRequest):
    """检索精度评估 (Recall@K/MRR/NDCG/MAP)"""
    from engines.search_quality import get_retrieval_metrics
    result = get_retrieval_metrics().comprehensive_eval(req.queries, req.k_values)
    return {"success": True, "metrics": result}

@router.post("/search/dedup")
async def search_dedup(req: DedupRequest):
    """检索结果去重"""
    from engines.search_quality import get_dedup_engine
    original_count = len(req.results)
    deduped = get_dedup_engine().text_dedup(req.results, req.text_field, req.threshold)
    rate = get_dedup_engine().compute_dedup_rate(original_count, len(deduped))
    return {"success": True, "result": deduped, "dedup_stats": rate}

@router.post("/search/relevance-compare")
async def search_relevance_compare(req: RelevanceCompareRequest):
    """人工评分 vs 模型评分对比"""
    from engines.search_quality import get_relevance_comparator
    result = get_relevance_comparator().compare_scores(req.human_scores, req.model_scores)
    return {"success": True, "comparison": result}

@router.post("/search/llm-verify")
async def search_llm_verify(req: SearchLLMVerifyRequest):
    """LLM验证检索质量"""
    from engines.search_quality import get_llm_search_verifier
    result = get_llm_search_verifier().verify_search_results(req.query, req.results, req.sample_size)
    return {"success": True, "verification": result}

@router.get("/search/latency")
async def search_latency(
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
    """检索延迟监控统计"""
    from engines.search_quality import get_latency_monitor
    stats = get_latency_monitor().get_stats()
    return {
        "success": True,
        "latency": stats,
        "limit": limit,
        "offset": offset,
    }

@router.get("/search/industry")
async def search_industry(
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
    """行业对标"""
    from engines.search_quality import INDUSTRY_SEARCH
    industry = INDUSTRY_SEARCH
    if q:
        q_lower = q.lower()
        if isinstance(industry, dict):
            industry = {k: v for k, v in industry.items() if q_lower in str(k).lower() or q_lower in str(v).lower()}
        elif isinstance(industry, list):
            industry = [x for x in industry if q_lower in str(x).lower()]
    total = len(industry) if hasattr(industry, "__len__") else 0
    if isinstance(industry, list):
        industry = industry[offset: offset + limit]
    return {
        "success": True,
        "industry": industry,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ============================================================
# ─── 4. 预览 (Preview) ──────────────────────────────────────
# ============================================================


@router.get("/preview/formats")
async def preview_formats(
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
    """104+格式支持报告"""
    from engines.preview_engine import PreviewEngine
    formats = PreviewEngine.get_format_support_report()
    return {
        "success": True,
        "formats": formats,
        "limit": limit,
        "offset": offset,
    }

@router.post("/preview/validate")
async def preview_validate(req: PreviewValidateRequest):
    """预览质量验证"""
    from engines.preview_engine import PreviewEngine
    result = PreviewEngine.validate_preview(req.file_path)
    return {"success": True, "validation": result}

@router.get("/preview/perf")
async def preview_performance(
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
    """预览性能基准"""
    from engines.preview_engine import PreviewEngine
    stats = PreviewEngine.get_performance_benchmarks()
    return {
        "success": True,
        "performance": stats,
        "limit": limit,
        "offset": offset,
    }

@router.get("/preview/perf-by-format")
async def preview_performance_by_format(
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
    """按格式性能统计"""
    from engines.preview_engine import PreviewEngine
    stats = PreviewEngine.get_performance_by_format()
    return {
        "success": True,
        "by_format": stats,
        "limit": limit,
        "offset": offset,
    }

@router.get("/preview/industry")
async def preview_industry(
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
    """行业对标"""
    from engines.preview_engine import INDUSTRY_PREVIEW
    industry = INDUSTRY_PREVIEW
    if q:
        q_lower = q.lower()
        if isinstance(industry, dict):
            industry = {k: v for k, v in industry.items() if q_lower in str(k).lower() or q_lower in str(v).lower()}
        elif isinstance(industry, list):
            industry = [x for x in industry if q_lower in str(x).lower()]
    total = len(industry) if hasattr(industry, "__len__") else 0
    if isinstance(industry, list):
        industry = industry[offset: offset + limit]
    return {
        "success": True,
        "industry": industry,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@router.post("/preview/bench-reset")
async def preview_bench_reset(req: ConfirmPayload = ConfirmPayload()):
    """重置预览性能基准 (R2: 加 confirm 字段防误操作)"""
    from engines.preview_engine import PreviewEngine
    if not req.confirm:
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=400, detail="需要 confirm=true 才能重置性能基准")
    PreviewEngine.reset_performance_benchmarks()
    return {"success": True, "message": "性能基准已重置"}


# ============================================================
# ─── 5. 传输 (Transfer) ─────────────────────────────────────
# ============================================================


@router.post("/transfer/verify")
async def transfer_verify(req: TransferVerifyRequest):
    """传输完整性验证 (SHA256/MD5)"""
    from engines.transfer_quality import get_integrity_verifier
    result = get_integrity_verifier().verify_file(req.source_path, req.dest_path, req.hash_type)
    return {"success": True, "verification": result}

@router.post("/transfer/verify-batch")
async def transfer_verify_batch(req: TransferVerifyBatchRequest):
    """批量传输完整性验证"""
    from engines.transfer_quality import get_integrity_verifier
    pairs = [(p[0], p[1]) for p in req.file_pairs]
    result = get_integrity_verifier().batch_verify(pairs)
    return {"success": True, "verification": result}

@router.post("/transfer/speed-record")
async def transfer_speed_record(req: SpeedRecordRequest):
    """记录传输速度"""
    from engines.transfer_quality import get_speed_monitor, SpeedRecord
    sr = SpeedRecord(
        source=req.source, dest=req.dest,
        file_size=req.file_size, duration_ms=req.duration_ms,
        speed_mbps=req.speed_mbps, protocol=req.protocol,
    )
    get_speed_monitor().record(sr)
    return {"success": True, "message": "速度记录已保存"}

@router.get("/transfer/speed-stats")
async def transfer_speed_stats(
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
    """传输速度统计"""
    from engines.transfer_quality import get_speed_monitor
    stats = get_speed_monitor().get_stats()
    return {
        "success": True,
        "stats": stats,
        "limit": limit,
        "offset": offset,
    }

@router.get("/transfer/checkpoints")
async def transfer_checkpoints(
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
    """断点续传检查点列表"""
    from engines.transfer_quality import get_resume_engine
    checkpoints = get_resume_engine().list_checkpoints()
    if q:
        checkpoints = [c for c in checkpoints if q.lower() in str(c).lower()]
    total = len(checkpoints)
    if sort_by:
        checkpoints = sorted(
            checkpoints, key=lambda c: c.get(sort_by, "") if isinstance(c, dict) else "",
            reverse=(order == "desc"),
        )
    page = checkpoints[offset: offset + limit]
    return {
        "success": True,
        "checkpoints": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@router.post("/transfer/url-audit")
async def transfer_url_audit(req: URLAuditRequest):
    """签名URL安全审计"""
    from engines.transfer_quality import get_url_auditor
    result = get_url_auditor().audit_url(req.url)
    return {"success": True, "audit": result}

@router.post("/transfer/url-audit-batch")
async def transfer_url_audit_batch(req: URLAuditBatchRequest):
    """批量URL安全审计"""
    from engines.transfer_quality import get_url_auditor
    result = get_url_auditor().batch_audit(req.urls)
    return {"success": True, "audit": result}

@router.get("/transfer/industry")
async def transfer_industry(
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
    """行业对标"""
    from engines.transfer_quality import INDUSTRY_TRANSFER
    industry = INDUSTRY_TRANSFER
    if q:
        q_lower = q.lower()
        if isinstance(industry, dict):
            industry = {k: v for k, v in industry.items() if q_lower in str(k).lower() or q_lower in str(v).lower()}
        elif isinstance(industry, list):
            industry = [x for x in industry if q_lower in str(x).lower()]
    total = len(industry) if hasattr(industry, "__len__") else 0
    if isinstance(industry, list):
        industry = industry[offset: offset + limit]
    return {
        "success": True,
        "industry": industry,
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@router.post("/transfer/estimate-time")
async def transfer_estimate_time(req: SpeedRecordRequest):
    """预估传输时间"""
    from engines.transfer_quality import get_speed_monitor
    estimate = get_speed_monitor().estimate_transfer_time(req.file_size, req.protocol)
    return {"success": True, "estimate": estimate}
