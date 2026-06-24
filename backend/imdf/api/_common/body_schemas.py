"""R2-Worker-2: Body 参数验证共享模型
====================================

R2 阶段在 `backend/imdf/api/_common/validators.py` 基础上, 为 create/update
类 POST/PUT/PATCH 端点提供统一的 Pydantic BaseModel。

设计要点 (见 `reports/r2_design.md` §4.1 模式 B):
    - 所有字符串字段: `min_length=1, max_length=4096` (按需调整)
    - 所有列表字段: `min_length=1, max_length=10000` (按需调整)
    - 所有数值字段: `ge=0, le=...` 显式范围
    - 枚举字段: 用 ``Literal["a", "b"]`` 不用裸 ``str``
    - 业务级校验: ``@field_validator``
    - 中文化错误信息: `description` 用中文

使用示例:
    from api._common.body_schemas import DeliverySubmitRequest

    @router.post("/submit")
    def submit_delivery(req: DeliverySubmitRequest):
        ...
"""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ============================================================================
# 通用工具模型
# ============================================================================

class IdPayload(BaseModel):
    """纯 ID 列表载荷 — 用于批量操作。"""
    ids: List[str] = Field(
        ..., min_length=1, max_length=1000,
        description="ID 列表, 1-1000 个",
    )

    @field_validator("ids")
    @classmethod
    def _check_ids(cls, v: List[str]) -> List[str]:
        import re
        pat = re.compile(r"^[a-zA-Z0-9_\-]{1,128}$")
        for x in v:
            if not isinstance(x, str) or not pat.match(x):
                raise ValueError(f"非法 id: {x!r}, 必须匹配 ^[a-zA-Z0-9_-]{{1,128}}$")
        return v


class ConfirmPayload(BaseModel):
    """带确认标志的空操作载荷 — 用于 bench-reset / cleanup 等。"""
    confirm: bool = Field(False, description="必须为 true 才执行")
    note: Optional[str] = Field(None, max_length=512, description="可选备注")


# ============================================================================
# Crowd — 众包 (routes_extended.py + crowd_settlement_routes.py)
# ============================================================================

class CrowdWorkerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="工人姓名")
    skills: List[str] = Field(default_factory=list, max_length=32, description="技能标签列表")
    email: Optional[str] = Field(None, max_length=128, description="邮箱 (可选)")


class CrowdTeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="团队名")
    leader: str = Field("", max_length=64, description="负责人")
    members: List[str] = Field(default_factory=list, max_length=200, description="成员列表")


class CrowdAssignTask(BaseModel):
    task_id: str = Field(..., min_length=1, max_length=128, description="任务 ID")
    required_skills: List[str] = Field(default_factory=list, max_length=32, description="所需技能")


class CrowdGoldenCheck(BaseModel):
    action: Literal["create", "check", "stats"] = Field("check", description="操作类型")
    golden_id: Optional[str] = Field(None, min_length=1, max_length=128, description="金标准 ID")
    task_id: Optional[str] = Field(None, max_length=128, description="关联任务 ID")
    worker_id: Optional[str] = Field(None, max_length=128, description="工人 ID")
    worker_answer: Optional[str] = Field(None, max_length=4096, description="工人回答")
    correct_answer: Optional[str] = Field(None, max_length=4096, description="正确答案")
    field_name: Optional[str] = Field("label", max_length=64, description="字段名")
    metadata: Optional[Dict[str, str]] = Field(None, description="扩展元数据")


class CrowdMajorityVote(BaseModel):
    action: Literal["vote", "result"] = Field("result", description="投票 / 查询结果")
    task_id: str = Field("", max_length=128, description="任务 ID")
    worker_id: Optional[str] = Field(None, max_length=128, description="工人 ID")
    field_name: Optional[str] = Field("label", max_length=64, description="字段名")
    answer: Optional[str] = Field(None, max_length=4096, description="投票答案")
    min_voters: int = Field(2, ge=1, le=1000, description="最少投票人数")


class CrowdQualityCoefficient(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=128, description="工人 ID")
    coefficient: float = Field(1.0, ge=0.0, le=10.0, description="质检系数 0-10")


# ============================================================================
# Delivery — 交付 (delivery_routes.py + routes_extended.py + canvas_web.py)
# ============================================================================

class DeliveryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="交付包名称")
    format: Literal["json", "csv", "parquet", "coco", "voc", "yolo"] = Field("json", description="数据格式")
    items: List[str] = Field(default_factory=list, max_length=10000, description="条目 ID 列表")


class DeliverySubmitRequest(BaseModel):
    delivery_id: str = Field(..., min_length=1, max_length=128, description="交付包 ID")
    content: str = Field("", max_length=10_000_000, description="交付内容")


class DeliveryReviewRequest(BaseModel):
    delivery_id: str = Field(..., min_length=1, max_length=128, description="交付包 ID")
    reviewer: str = Field(..., min_length=1, max_length=64, description="审核人")
    verdict: Literal["approved", "rejected", "needs_changes"] = Field("approved", description="审核结论")
    comments: Optional[str] = Field(None, max_length=4096, description="审核备注")


class DeliveryApproveRequest(BaseModel):
    delivery_id: str = Field(..., min_length=1, max_length=128, description="交付包 ID")
    reviewer: str = Field(..., min_length=1, max_length=64, description="批准人")


class DeliverySnapshotRequest(BaseModel):
    delivery_id: str = Field(..., min_length=1, max_length=128, description="交付包 ID")
    snapshot_type: Literal["baseline", "delta", "release"] = Field("baseline", description="快照类型")
    notes: Optional[str] = Field(None, max_length=2048, description="备注")


# ============================================================================
# Quality — 质量 (quality_routes.py)
# ============================================================================

class IAAReportRequest(BaseModel):
    annotations: List[Dict] = Field(
        ..., min_length=1, max_length=100_000,
        description="标注列表, ≥1 条",
    )


class CohenKappaRequest(BaseModel):
    rater1: List[str] = Field(..., min_length=2, max_length=10000, description="评分者1 标签")
    rater2: List[str] = Field(..., min_length=2, max_length=10000, description="评分者2 标签")

    @field_validator("rater1", "rater2")
    @classmethod
    def _check_labels(cls, v: List[str]) -> List[str]:
        for label in v:
            if not isinstance(label, str) or len(label) > 1024:
                raise ValueError("标签必须为字符串且 ≤1024 字符")
        return v


class FleissKappaRequest(BaseModel):
    ratings: List[List[int]] = Field(..., min_length=2, max_length=10000, description="评分矩阵")
    n_categories: int = Field(..., ge=2, le=1000, description="类别数 ≥2")


class GoldAddRequest(BaseModel):
    item: Dict = Field(..., description="金标准条目")
    ground_truth: Dict = Field(..., description="金标准答案")


class GoldValidateRequest(BaseModel):
    annotations: List[Dict] = Field(
        ..., min_length=1, max_length=100_000,
        description="待校验标注",
    )


class PEJudgeRequest(BaseModel):
    pe_text: str = Field(..., min_length=1, max_length=4096, description="待评判文本")
    eval_type: Literal["annotation", "summary", "translation"] = Field("annotation", description="评估类型")


class ABTestRequest(BaseModel):
    pe_a: str = Field(..., min_length=1, max_length=4096, description="版本 A 文本")
    pe_b: str = Field(..., min_length=1, max_length=4096, description="版本 B 文本")
    test_cases: List[Dict] = Field(default_factory=list, max_length=1000, description="测试用例")


class PipelineRunRequest(BaseModel):
    items: List[Dict] = Field(..., min_length=1, max_length=10000, description="流水线输入")
    pe_id: Optional[str] = Field(None, max_length=128, description="PE 模型 ID")


class EvalResultsRequest(BaseModel):
    results: List[Dict] = Field(..., min_length=1, max_length=10000, description="评测结果列表")
    benchmark: str = Field("", max_length=64, description="Benchmark 名")


class EvalConsistencyRequest(BaseModel):
    results: List[Dict] = Field(..., min_length=1, max_length=10000, description="多次评测结果")
    n_runs: int = Field(3, ge=2, le=100, description="重复次数 ≥2")


class LLMJudgeRequest(BaseModel):
    items: List[Dict] = Field(..., min_length=1, max_length=1000, description="待评判项")


class ABEvalRequest(BaseModel):
    test_name: str = Field(..., min_length=1, max_length=128, description="测试名")
    variant_a: str = Field(..., min_length=1, max_length=64, description="变体 A 名")
    variant_b: str = Field(..., min_length=1, max_length=64, description="变体 B 名")
    results_a: List[Dict] = Field(..., min_length=1, max_length=10000, description="A 结果")
    results_b: List[Dict] = Field(..., min_length=1, max_length=10000, description="B 结果")
    benchmark: Literal["mmlu", "gsm8k", "hellaswag", "truthfulqa", "ceval"] = Field("mmlu", description="Benchmark")


class AccuracyRequest(BaseModel):
    predictions: Dict[str, str] = Field(..., description="预测 {id: label}")
    ground_truth: Dict[str, str] = Field(..., description="真值 {id: label}")


class ReliabilityRequest(BaseModel):
    predictions: List[Dict] = Field(..., min_length=1, max_length=10000, description="分类预测含置信度")


class LLMClassifyVerifyRequest(BaseModel):
    items: List[Dict] = Field(..., min_length=1, max_length=10000, description="待验证项")
    predictions: List[Dict] = Field(..., min_length=1, max_length=10000, description="预测")
    ground_truths: Optional[List[Dict]] = Field(None, max_length=10000, description="真值")


class SearchMetricRequest(BaseModel):
    queries: List[Dict] = Field(..., min_length=1, max_length=10000, description="查询列表")
    k_values: Optional[List[int]] = Field(None, max_length=20, description="K 值列表")

    @field_validator("k_values")
    @classmethod
    def _check_k(cls, v):
        if v is not None:
            for k in v:
                if not (1 <= k <= 10000):
                    raise ValueError(f"K 值必须在 1-10000 之间, 收到 {k}")
        return v


class DedupRequest(BaseModel):
    results: List[Dict] = Field(..., min_length=1, max_length=10000, description="检索结果")
    text_field: str = Field("content", min_length=1, max_length=64, description="去重字段")
    threshold: float = Field(0.9, ge=0.0, le=1.0, description="相似度阈值")


class RelevanceCompareRequest(BaseModel):
    human_scores: Dict[str, float] = Field(..., description="人工评分 {id: score}")
    model_scores: Dict[str, float] = Field(..., description="模型评分 {id: score}")


class SearchLLMVerifyRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096, description="查询")
    results: List[Dict] = Field(..., min_length=1, max_length=1000, description="检索结果")
    sample_size: int = Field(10, ge=1, le=1000, description="抽样数")


class PreviewValidateRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=4096, description="文件路径")


class TransferVerifyRequest(BaseModel):
    source_path: str = Field(..., min_length=1, max_length=4096, description="源路径")
    dest_path: str = Field(..., min_length=1, max_length=4096, description="目标路径")
    hash_type: Literal["sha256", "md5", "sha1", "blake2b"] = Field("sha256", description="哈希算法")


class TransferVerifyBatchRequest(BaseModel):
    file_pairs: List[List[str]] = Field(..., min_length=1, max_length=1000, description="源-目标对列表")

    @field_validator("file_pairs")
    @classmethod
    def _check_pairs(cls, v):
        for p in v:
            if not isinstance(p, list) or len(p) != 2:
                raise ValueError("file_pairs 每项必须是 [src, dest] 双元素列表")
            for s in p:
                if not isinstance(s, str) or not s or len(s) > 4096:
                    raise ValueError("路径必须为非空字符串且 ≤4096 字符")
        return v


class SpeedRecordRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=4096, description="源")
    dest: str = Field(..., min_length=1, max_length=4096, description="目标")
    file_size: int = Field(..., ge=0, le=10**15, description="文件大小")
    duration_ms: float = Field(..., ge=0.0, le=10**10, description="耗时 ms")
    speed_mbps: float = Field(..., ge=0.0, le=10**6, description="速度 Mbps")
    protocol: Literal["http", "https", "ftp", "sftp", "rsync", "scp"] = Field("http", description="协议")


class URLAuditRequest(BaseModel):
    url: HttpUrl = Field(..., description="待审计 URL")


class URLAuditBatchRequest(BaseModel):
    urls: List[HttpUrl] = Field(..., min_length=1, max_length=1000, description="URL 列表")


# ============================================================================
# Search — 检索 (search_routes.py + search_advanced_routes.py)
# ============================================================================

class SearchRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=512, description="查询")
    fields: Optional[List[str]] = Field(None, max_length=64, description="检索字段")
    top_k: int = Field(10, ge=1, le=1000, description="返回数")
    threshold: float = Field(0.0, ge=0.0, le=1.0, description="相似度阈值")
    mode: Literal["vector", "fts5", "hybrid", "exact"] = Field("vector", description="检索模式")
    fuzzy: bool = Field(False, description="是否模糊匹配")


class ImageSearchRequest(BaseModel):
    image_path: str = Field(..., min_length=1, max_length=4096, description="图片路径")
    collection: str = Field("image_index", min_length=1, max_length=64, description="索引名")
    top_k: int = Field(5, ge=1, le=1000, description="返回数")


class HybridSearchRequest(BaseModel):
    text: str = Field("", max_length=4096, description="文本部分")
    vector: Optional[List[float]] = Field(None, max_length=4096, description="向量部分")
    top_k: int = Field(10, ge=1, le=1000, description="返回数")
    alpha: float = Field(0.5, ge=0.0, le=1.0, description="文本权重 0-1")


class IndexCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z][a-zA-Z0-9_\-]{0,63}$")
    dim: int = Field(..., ge=1, le=65536, description="向量维度")
    metric: Literal["cosine", "l2", "ip"] = Field("cosine", description="距离度量")


class IndexDeleteVectorsRequest(BaseModel):
    ids: List[str] = Field(..., min_length=1, max_length=10000, description="向量 ID 列表")


class IndexImageAddRequest(BaseModel):
    image_path: str = Field(..., min_length=1, max_length=4096, description="图片路径")
    metadata: Optional[Dict[str, str]] = Field(None, description="元数据")


class IndexTextAddRequest(BaseModel):
    doc_id: str = Field(..., min_length=1, max_length=128, description="文档 ID")
    text: str = Field(..., min_length=1, max_length=10_000_000, description="文档内容")
    metadata: Optional[Dict[str, str]] = Field(None, description="元数据")


class AdvancedFacetedRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=512, description="查询")
    facets: List[str] = Field(default_factory=list, max_length=20, description="分面字段")
    filters: Optional[Dict[str, str]] = Field(None, description="过滤条件")


class MultimodalSearchRequest(BaseModel):
    text: Optional[str] = Field(None, max_length=4096, description="文本查询")
    image_path: Optional[str] = Field(None, max_length=4096, description="图片路径")
    top_k: int = Field(10, ge=1, le=1000, description="返回数")


class SimilarSearchRequest(BaseModel):
    seed_id: str = Field(..., min_length=1, max_length=128, description="种子 ID")
    top_k: int = Field(10, ge=1, le=1000, description="返回数")


class NLQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096, description="自然语言查询")
    top_k: int = Field(10, ge=1, le=1000, description="返回数")


class CrossModalRequest(BaseModel):
    source_type: Literal["text", "image", "audio"] = Field("text", description="源模态")
    target_type: Literal["text", "image", "audio"] = Field("image", description="目标模态")
    content: str = Field(..., min_length=1, max_length=4096, description="源内容")
    top_k: int = Field(10, ge=1, le=1000, description="返回数")


class SemanticRerankRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512, description="查询")
    candidates: List[Dict] = Field(..., min_length=1, max_length=1000, description="候选列表")
    top_k: int = Field(10, ge=1, le=1000, description="返回数")


# ============================================================================
# 3D Canvas (canvas_3d.py + canvas_web.py + board_manager.py)
# ============================================================================

class CreateSceneRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="场景名")
    width: int = Field(2000, ge=64, le=16384, description="宽")
    height: int = Field(1000, ge=64, le=16384, description="高")


class UpdateSceneRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128, description="场景名")
    panorama_url: Optional[str] = Field(None, max_length=4096, description="全景图 URL")
    thumbnail_url: Optional[str] = Field(None, max_length=4096, description="缩略图 URL")
    viewer_position: Optional[str] = Field(None, max_length=128, description="观察位")
    view_center: Optional[str] = Field(None, max_length=128, description="观察中心")


class AddAvatarRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="角色名")
    color: str = Field("#4A90D9", pattern=r"^#[0-9A-Fa-f]{6}$", description="颜色 HEX")


class AddCameraRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="视角名")
    yaw: float = Field(0.0, ge=-360.0, le=360.0, description="偏航角")
    pitch: float = Field(0.0, ge=-90.0, le=90.0, description="俯仰角")
    fov: float = Field(90.0, ge=1.0, le=179.0, description="视场角")
    is_default: bool = Field(False, description="是否默认视角")


class AddHotspotRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=128, description="热点标签")
    yaw: float = Field(0.0, ge=-360.0, le=360.0, description="偏航角")
    pitch: float = Field(0.0, ge=-90.0, le=90.0, description="俯仰角")
    fov: Optional[float] = Field(None, ge=1.0, le=179.0, description="视场角")
    target_scene_id: Optional[str] = Field(None, max_length=128, description="目标场景 ID")


class AddKeyframeRequest(BaseModel):
    frame_index: int = Field(..., ge=0, le=1_000_000, description="帧序号")
    timestamp: float = Field(0.0, ge=0.0, le=10**9, description="时间戳 (秒)")
    avatar_states: Dict[str, str] = Field(default_factory=dict, description="角色状态字典")


class AddMaskRequest(BaseModel):
    avatar_id: str = Field(..., min_length=1, max_length=128, description="角色 ID")
    mask_type: Literal["box", "polygon", "freehand"] = Field("box", description="遮罩类型")


class InferPoseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096, description="自然语言描述")
    lang: Literal["zh", "en"] = Field("zh", description="语言")


class ParseActionRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096, description="动作描述")
    lang: Literal["zh", "en"] = Field("zh", description="语言")


class BuildKeyframesRequest(BaseModel):
    actions: List[Dict[str, str]] = Field(
        ..., min_length=1, max_length=1000, description="动作列表",
    )
    frame_count: int = Field(30, ge=1, le=10000, description="帧数")
    fps: float = Field(30.0, gt=0.0, le=240.0, description="帧率")


class CanvasElementRequest(BaseModel):
    element_type: str = Field(..., min_length=1, max_length=32, description="元素类型")
    data: Dict = Field(..., description="元素数据")
    x: float = Field(0.0, ge=-1e6, le=1e6, description="X 坐标")
    y: float = Field(0.0, ge=-1e6, le=1e6, description="Y 坐标")
    z_index: int = Field(0, ge=0, le=10000, description="层级")


class CanvasStateRequest(BaseModel):
    state: Dict = Field(..., description="画布状态 JSON")
    revision: Optional[int] = Field(None, ge=0, description="修订号")


class BoardAutoSaveRequest(BaseModel):
    state: Dict = Field(..., description="状态数据")
    revision: int = Field(..., ge=0, description="修订号")


class BoardNameUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="画板新名")


# ============================================================================
# IMDF Canvas (imdf_canvas routes)
# ============================================================================

class IMDFCanvasCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="画板名")
    width: int = Field(1920, ge=64, le=16384, description="宽")
    height: int = Field(1080, ge=64, le=16384, description="高")


class IMDFCanvasUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    state: Optional[Dict] = Field(None, description="画板状态")


# ============================================================================
# IMDF Config (imdf_config)
# ============================================================================

class IMDFConfigUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=64, description="配置键")
    value: Dict = Field(..., description="配置值")


class IMDFToolsImport(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=64, description="工具名")
    config: Dict = Field(..., description="工具配置")
    force: bool = Field(False, description="强制覆盖")


# ============================================================================
# ComfyUI (sdk_routes.py's /generate + dedicated comfyui routes)
# ============================================================================

class ComfyUIRunRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=10_000, description="工作流 prompt")
    workflow: Optional[str] = Field(None, max_length=64, description="工作流名")
    seed: Optional[int] = Field(None, ge=0, le=2**31 - 1, description="随机种子")
    steps: Optional[int] = Field(None, ge=1, le=200, description="步数")
    cfg: Optional[float] = Field(None, ge=0.0, le=30.0, description="CFG")


# ============================================================================
# Classify
# ============================================================================

class ClassifyInitDefaultsRequest(BaseModel):
    category: str = Field(..., min_length=1, max_length=64, description="类别名")
    labels: List[str] = Field(..., min_length=1, max_length=1000, description="标签列表")
    overwrite: bool = Field(False, description="覆盖已有")


class ClassifyRuleDeleteRequest(BaseModel):
    rule_id: str = Field(..., min_length=1, max_length=128, description="规则 ID")


# ============================================================================
# Backup
# ============================================================================

class BackupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="备份名")
    description: Optional[str] = Field(None, max_length=512, description="描述")
    include_logs: bool = Field(False, description="是否包含日志")


class BackupAutoRequest(BaseModel):
    schedule: Literal["daily", "weekly", "monthly"] = Field("daily", description="自动备份周期")
    retention_days: int = Field(30, ge=1, le=3650, description="保留天数")


class BackupRestoreRequest(BaseModel):
    backup_id: str = Field(..., min_length=1, max_length=128, description="备份 ID")
    target_path: Optional[str] = Field(None, max_length=4096, description="恢复目标")
    force: bool = Field(False, description="强制覆盖")


# ============================================================================
# Prompt Templates
# ============================================================================

class PromptTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    content: str = Field(..., min_length=1, max_length=100_000, description="模板内容")
    variables: List[str] = Field(default_factory=list, max_length=100, description="变量名列表")
    description: Optional[str] = Field(None, max_length=512, description="描述")


# ============================================================================
# Scheduler
# ============================================================================

class SchedulerJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="任务名")
    cron: str = Field(..., min_length=9, max_length=64, description="cron 表达式")
    handler: str = Field(..., min_length=1, max_length=64, description="处理器名")
    args: Optional[Dict[str, str]] = Field(None, description="任务参数")
    enabled: bool = Field(True, description="是否启用")


class SchedulerJobUpdate(BaseModel):
    cron: Optional[str] = Field(None, min_length=9, max_length=64)
    enabled: Optional[bool] = Field(None, description="启用状态")
    args: Optional[Dict[str, str]] = Field(None)


class SchedulerJobRun(BaseModel):
    job_id: str = Field(..., min_length=1, max_length=128, description="任务 ID")
    async_run: bool = Field(True, description="是否异步执行")


# ============================================================================
# Review / Algorithm Review
# ============================================================================

class ReviewSubmitRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="算法名")
    version: str = Field("1.0", max_length=32, description="版本号")
    model_path: str = Field("/models/default", max_length=4096, description="模型路径")
    metrics: Dict[str, float] = Field(default_factory=dict, description="评估指标")

    @field_validator("metrics")
    @classmethod
    def _check_metrics(cls, v):
        for k, val in v.items():
            if not isinstance(val, (int, float)):
                raise ValueError(f"指标 {k} 必须为数值, 收到 {type(val).__name__}")
        return v


class ReviewPreReviewRequest(BaseModel):
    algo_id: str = Field(..., min_length=1, max_length=128, description="算法 ID")
    model_file_exists: bool = Field(True, description="模型文件是否存在")
    metrics_valid: bool = Field(True, description="指标是否有效")


class ReviewApproveRequest(BaseModel):
    algo_id: str = Field(..., min_length=1, max_length=128, description="算法 ID")
    approver: str = Field(..., min_length=1, max_length=64, description="批准人")


class ReviewDeployRequest(BaseModel):
    algo_id: str = Field(..., min_length=1, max_length=128, description="算法 ID")
    deployed_by: str = Field(..., min_length=1, max_length=64, description="部署人")


# ============================================================================
# Requirements
# ============================================================================

class RequirementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256, description="需求标题")
    type: Literal["general", "feature", "bug", "improvement"] = Field("general", description="类型")
    priority: Literal["low", "medium", "high", "critical"] = Field("medium", description="优先级")
    description: Optional[str] = Field(None, max_length=4096, description="详细描述")


class RequirementAssign(BaseModel):
    requirement_id: str = Field(..., min_length=1, max_length=128, description="需求 ID")
    assignee: str = Field(..., min_length=1, max_length=64, description="处理人")


class RequirementClose(BaseModel):
    requirement_id: str = Field(..., min_length=1, max_length=128, description="需求 ID")
    reason: Optional[str] = Field(None, max_length=512, description="关闭原因")


class RequirementVerify(BaseModel):
    requirement_id: str = Field(..., min_length=1, max_length=128, description="需求 ID")
    verified_by: str = Field(..., min_length=1, max_length=64, description="验收人")


# ============================================================================
# Ingest
# ============================================================================

class IngestAPIConfig(BaseModel):
    api_name: str = Field(..., min_length=1, max_length=64, description="API 名")
    url: HttpUrl = Field(..., description="API URL")
    auth_token: Optional[str] = Field(None, max_length=2048, description="认证 token")
    rate_limit: Optional[int] = Field(None, ge=1, le=10000, description="限速/分钟")


class IngestCrawlerRequest(BaseModel):
    url: HttpUrl = Field(..., description="目标 URL")
    depth: int = Field(1, ge=0, le=10, description="爬取深度")
    max_pages: int = Field(100, ge=1, le=100000, description="最大页数")
    pattern: Optional[str] = Field(None, max_length=512, description="URL 过滤正则")


class IngestCSVRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=4096, description="CSV 文件路径")
    delimiter: str = Field(",", max_length=1, description="分隔符")
    has_header: bool = Field(True, description="是否含表头")


class IngestExcelRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=4096, description="Excel 文件路径")
    sheet: Optional[str] = Field(None, max_length=64, description="Sheet 名")


class IngestImportRequest(BaseModel):
    source: Literal["csv", "excel", "json", "rss", "api"] = Field("csv", description="数据源类型")
    config: Dict = Field(..., description="导入配置")
    target_collection: str = Field(..., min_length=1, max_length=64, description="目标集合")


class IngestJSONRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=4096, description="JSON 文件路径")
    root_key: Optional[str] = Field(None, max_length=128, description="根键")


class IngestRSSRequest(BaseModel):
    feed_url: HttpUrl = Field(..., description="RSS URL")
    max_items: int = Field(100, ge=1, le=10000, description="最大条目数")


class IngestRSSRefreshRequest(BaseModel):
    feed_id: str = Field(..., min_length=1, max_length=128, description="RSS 源 ID")


class IngestRSSRefreshAllRequest(BaseModel):
    force: bool = Field(False, description="强制刷新")


# ============================================================================
# Discovery / Engine / Export / Cloud
# ============================================================================

class DiscoveryClearCacheRequest(BaseModel):
    cache_type: Literal["all", "search", "embeddings", "metadata"] = Field("all", description="缓存类型")
    confirm: bool = Field(True, description="确认操作")


class EnginePlanRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=4096, description="目标")
    context: Optional[Dict[str, str]] = Field(None, description="上下文")
    max_steps: int = Field(10, ge=1, le=100, description="最大步骤")


class ExportRequest(BaseModel):
    format: Literal["json", "csv", "parquet", "coco", "voc", "yolo", "xlsx"] = Field("json", description="导出格式")
    dataset_id: str = Field(..., min_length=1, max_length=128, description="数据集 ID")
    filters: Optional[Dict[str, str]] = Field(None, description="过滤条件")
    include_media: bool = Field(False, description="包含媒体")


class CloudStorageSettings(BaseModel):
    provider: Literal["s3", "oss", "cos", "azure", "gcs", "minio"] = Field("s3", description="存储提供方")
    endpoint: Optional[HttpUrl] = Field(None, description="端点 URL")
    bucket: str = Field(..., min_length=1, max_length=64, description="桶名")
    access_key: Optional[str] = Field(None, max_length=256, description="AK")
    secret_key: Optional[str] = Field(None, max_length=256, description="SK")
    region: Optional[str] = Field(None, max_length=32, description="区域")


# ============================================================================
# Chat / API-Keys / Migrations
# ============================================================================

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32000, description="用户消息")
    session_id: Optional[str] = Field(None, max_length=128, description="会话 ID")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="温度")
    max_tokens: int = Field(2048, ge=1, le=32000, description="最大 token")


class APIKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Key 名称")
    scopes: List[str] = Field(default_factory=list, max_length=32, description="权限范围")
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650, description="有效期")


class MigrationApplyRequest(BaseModel):
    migration_id: str = Field(..., min_length=1, max_length=128, description="迁移 ID")
    target_db: Optional[str] = Field(None, max_length=64, description="目标 DB")
    dry_run: bool = Field(False, description="演练模式")


# ============================================================================
# DAM / Webhook / External
# ============================================================================

class DAMFilesTagAllRequest(BaseModel):
    tag: str = Field(..., min_length=1, max_length=64, description="标签名")
    file_ids: List[str] = Field(..., min_length=1, max_length=10000, description="文件 ID 列表")
    overwrite: bool = Field(False, description="覆盖已有标签")


class WebhookCreateRequest(BaseModel):
    url: HttpUrl = Field(..., description="回调 URL")
    events: List[str] = Field(..., min_length=1, max_length=50, description="订阅事件列表")
    secret: Optional[str] = Field(None, max_length=256, description="签名密钥")
    active: bool = Field(True, description="启用状态")


class WebhookUpdateRequest(BaseModel):
    url: Optional[HttpUrl] = Field(None, description="回调 URL")
    events: Optional[List[str]] = Field(None, max_length=50, description="订阅事件列表")
    active: Optional[bool] = Field(None, description="启用状态")


class WebhookTestRequest(BaseModel):
    payload: Optional[Dict[str, str]] = Field(None, description="测试载荷")


# ============================================================================
# Media / Image / Video / PPT / Figma / Privacy / Copyright
# ============================================================================

class MediaInfoRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=4096, description="文件路径")


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4096, description="图像描述")
    width: int = Field(1024, ge=64, le=8192, description="宽")
    height: int = Field(1024, ge=64, le=8192, description="高")
    seed: Optional[int] = Field(None, ge=0, le=2**31 - 1, description="种子")
    negative_prompt: Optional[str] = Field(None, max_length=4096, description="反向提示")


class VideoGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4096, description="视频描述")
    duration_sec: int = Field(5, ge=1, le=300, description="时长 (秒)")
    fps: int = Field(24, ge=1, le=120, description="帧率")
    width: int = Field(1280, ge=64, le=4096)
    height: int = Field(720, ge=64, le=4096)


class PPTGenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=256, description="PPT 主题")
    slides: int = Field(10, ge=1, le=200, description="幻灯片数")
    template: Optional[str] = Field(None, max_length=64, description="模板名")


class FigmaImportRequest(BaseModel):
    figma_url: HttpUrl = Field(..., description="Figma 文件 URL")
    token: Optional[str] = Field(None, max_length=512, description="Figma PAT")
    format: Literal["json", "svg", "png"] = Field("json", description="导出格式")


class PIIDetectRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1_000_000, description="待检测文本")
    entity_types: Optional[List[str]] = Field(None, max_length=32, description="要检测的实体类型")


class PIIMaskRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1_000_000, description="原文")
    mask_char: str = Field("*", max_length=1, description="掩码字符")


class DSARExportRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, description="用户 ID")
    format: Literal["json", "csv", "xml"] = Field("json", description="导出格式")


class DSARDeleteRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, description="用户 ID")
    confirm: bool = Field(True, description="确认删除")


class ConsentRecordRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128, description="用户 ID")
    purpose: str = Field(..., min_length=1, max_length=256, description="用途")
    granted: bool = Field(..., description="是否同意")


class CopyrightSignRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10_000_000, description="内容")
    author: str = Field(..., min_length=1, max_length=128, description="作者")
    timestamp: Optional[int] = Field(None, ge=0, description="时间戳")


class CopyrightVerifyRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10_000_000, description="内容")
    signature: str = Field(..., min_length=1, max_length=4096, description="签名")


class CopyrightEmbedRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=4096, description="文件路径")
    watermark: str = Field(..., min_length=1, max_length=4096, description="水印文本")


class CopyrightDetectRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=4096, description="文件路径")


class CopyrightSimilarityRequest(BaseModel):
    file_a: str = Field(..., min_length=1, max_length=4096, description="文件 A 路径")
    file_b: str = Field(..., min_length=1, max_length=4096, description="文件 B 路径")


class CopyrightAttributionRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10_000_000, description="内容")
    reference_db: Optional[str] = Field(None, max_length=64, description="参考库")


# ============================================================================
# Privacy (utility)
# ============================================================================

class PrivacySeedRequest(BaseModel):
    count: int = Field(10, ge=1, le=10000, description="种子数量")
    overwrite: bool = Field(False, description="覆盖已有")


# ============================================================================
# Workflow Contract
# ============================================================================

class WorkflowDefineRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="工作流名")
    steps: List[Dict] = Field(..., min_length=1, max_length=100, description="步骤列表")
    triggers: Optional[List[str]] = Field(None, max_length=20, description="触发器列表")


class WorkflowValidateRequest(BaseModel):
    workflow: Dict = Field(..., description="工作流定义")
    strict: bool = Field(True, description="严格模式")


class WorkflowValidateWorkflowRequest(BaseModel):
    workflow_id: str = Field(..., min_length=1, max_length=128, description="工作流 ID")
    sample_inputs: Optional[List[Dict]] = Field(None, max_length=100, description="样本输入")


class WorkflowCheckConflictsRequest(BaseModel):
    workflows: List[str] = Field(..., min_length=2, max_length=100, description="工作流 ID 列表")


class WorkflowInferRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=4096, description="目标")
    context: Optional[Dict[str, str]] = Field(None, description="上下文")


class WorkflowExecuteRequest(BaseModel):
    workflow_id: str = Field(..., min_length=1, max_length=128, description="工作流 ID")
    inputs: Optional[Dict[str, str]] = Field(None, description="输入参数")


# ============================================================================
# Media Manager (media_manager.py)
# ============================================================================

class MediaUploadRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=256, description="文件名")
    content_type: str = Field(..., min_length=1, max_length=128, description="Content-Type")
    size: int = Field(..., ge=0, le=10**12, description="字节数")


class MediaUploadBase64Request(BaseModel):
    filename: str = Field(..., min_length=1, max_length=256, description="文件名")
    data: str = Field(..., min_length=1, max_length=100_000_000, description="Base64 数据")


class MediaDuckDecodeRequest(BaseModel):
    file_path: str = Field(..., min_length=1, max_length=4096, description="文件路径")


class MediaSaveToDiskRequest(BaseModel):
    file_id: str = Field(..., min_length=1, max_length=128, description="文件 ID")
    target_path: str = Field(..., min_length=1, max_length=4096, description="目标路径")


# ============================================================================
# External / External Providers
# ============================================================================

class ExternalRegisterRequest(BaseModel):
    agent_name: str = Field(..., min_length=1, max_length=64, description="Agent 名")
    endpoint: HttpUrl = Field(..., description="Agent 端点")
    capabilities: List[str] = Field(default_factory=list, max_length=32, description="能力列表")
    api_key: Optional[str] = Field(None, max_length=512, description="API Key")


class ExternalHealthCheckRequest(BaseModel):
    detailed: bool = Field(False, description="详细检查")


class ExternalInvokeRequest(BaseModel):
    capability: str = Field(..., min_length=1, max_length=64, description="能力")
    inputs: Dict = Field(..., description="输入参数")
    timeout_sec: int = Field(30, ge=1, le=600, description="超时 (秒)")


class ExternalProviderTestRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4096, description="测试 prompt")


class ExternalProviderLLMRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=32000, description="prompt")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(1024, ge=1, le=32000)


class ExternalProviderImageRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4096)
    width: int = Field(1024, ge=64, le=8192)
    height: int = Field(1024, ge=64, le=8192)


class ExternalProviderVideoRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4096)
    duration_sec: int = Field(5, ge=1, le=300)


# ============================================================================
# Annotation / Theme / System Config
# ============================================================================

class AnnotationSaveRequest(BaseModel):
    image_id: str = Field(..., min_length=1, max_length=128, description="图片 ID")
    annotations: List[Dict] = Field(..., min_length=1, max_length=10000, description="标注列表")
    annotator: Optional[str] = Field(None, max_length=64, description="标注者")


class ThemeTemplateImport(BaseModel):
    template_id: str = Field(..., min_length=1, max_length=128, description="模板 ID")
    force: bool = Field(False, description="覆盖")


class ThemeTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    config: Optional[Dict] = Field(None)


class SystemConfigUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=64, description="配置键")
    value: Dict = Field(..., description="配置值")


class SystemToolCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="类目名")
    icon: Optional[str] = Field(None, max_length=64, description="图标")
    order: int = Field(0, ge=0, le=10000)


class SystemToolCategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    icon: Optional[str] = Field(None, max_length=64)
    order: Optional[int] = Field(None, ge=0, le=10000)


class SystemToolCategoryReorder(BaseModel):
    order: List[str] = Field(..., min_length=1, max_length=100, description="类目 ID 顺序列表")


class SystemToolAppCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="应用名")
    category_id: str = Field(..., min_length=1, max_length=128, description="类目 ID")
    config: Dict = Field(..., description="应用配置")
    icon: Optional[str] = Field(None, max_length=64)


class SystemToolAppUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=64)
    config: Optional[Dict] = None
    icon: Optional[str] = Field(None, max_length=64)


class SystemToolAppReorder(BaseModel):
    category_id: str = Field(..., min_length=1, max_length=128)
    order: List[str] = Field(..., min_length=1, max_length=100)


class SystemToolsImport(BaseModel):
    source: Literal["registry", "git", "zip", "url"] = Field("registry")
    config: Dict = Field(..., description="导入配置")


# ============================================================================
# Resource Library
# ============================================================================

class ResourceCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64, description="类目名")
    description: Optional[str] = Field(None, max_length=512)


class ResourceItemAdd(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="资源名")
    category_id: str = Field(..., min_length=1, max_length=128, description="类目 ID")
    url: Optional[HttpUrl] = Field(None, description="资源 URL")
    metadata: Optional[Dict[str, str]] = Field(None)


# ============================================================================
# Image Processor
# ============================================================================

class ImageResizeRequest(BaseModel):
    image_path: str = Field(..., min_length=1, max_length=4096, description="图片路径")
    width: int = Field(..., ge=1, le=16384, description="目标宽")
    height: int = Field(..., ge=1, le=16384, description="目标高")
    keep_aspect: bool = Field(False, description="保持纵横比")


class ImageCropRequest(BaseModel):
    image_path: str = Field(..., min_length=1, max_length=4096, description="图片路径")
    x: int = Field(..., ge=0, le=100000, description="X")
    y: int = Field(..., ge=0, le=100000, description="Y")
    width: int = Field(..., ge=1, le=16384, description="宽")
    height: int = Field(..., ge=1, le=16384, description="高")


class ImageGridComposeRequest(BaseModel):
    image_paths: List[str] = Field(..., min_length=2, max_length=100, description="图片路径列表")
    cols: int = Field(2, ge=1, le=20, description="列数")
    rows: int = Field(2, ge=1, le=20, description="行数")
    output_path: str = Field(..., min_length=1, max_length=4096, description="输出路径")


class ImageCompareRequest(BaseModel):
    image_a: str = Field(..., min_length=1, max_length=4096, description="图片 A")
    image_b: str = Field(..., min_length=1, max_length=4096, description="图片 B")


# ============================================================================
# Pre-label
# ============================================================================

class PreLabelRequest(BaseModel):
    image_path: str = Field(..., min_length=1, max_length=4096, description="图片路径")
    model: Optional[str] = Field(None, max_length=64, description="模型名")


# ============================================================================
# Cloud (cloud_storage.py)
# ============================================================================

class CloudStorageSettingsRequest(BaseModel):
    provider: Literal["s3", "oss", "cos", "azure", "gcs", "minio"] = Field("s3")
    bucket: str = Field(..., min_length=1, max_length=64)
    access_key: Optional[str] = Field(None, max_length=256)
    secret_key: Optional[str] = Field(None, max_length=256)
    region: Optional[str] = Field(None, max_length=32)


# ============================================================================
# Quality v2 collection
# ============================================================================

class CollectionDedupClearRequest(BaseModel):
    confirm: bool = Field(False, description="确认清空")
    collection: Optional[str] = Field(None, max_length=64, description="限定集合")


class CollectionDedupStatsRequest(BaseModel):
    collection: Optional[str] = Field(None, max_length=64, description="集合名")


class CollectionLLMEvalRequest(BaseModel):
    items: List[Dict] = Field(..., min_length=1, max_length=1000, description="待评估项")
    rubric: Optional[str] = Field(None, max_length=4096, description="评分标准")


class CollectionMonitorStartRequest(BaseModel):
    collection: str = Field(..., min_length=1, max_length=64, description="集合名")
    interval_sec: int = Field(60, ge=10, le=86400, description="监控间隔")


# ============================================================================
# Drama
# ============================================================================

class DramaGenerateRequest(BaseModel):
    theme: str = Field(..., min_length=1, max_length=256, description="主题")
    episodes: int = Field(1, ge=1, le=100, description="集数")
    style: Optional[str] = Field(None, max_length=64, description="风格")


class DramaScriptRequest(BaseModel):
    drama_id: str = Field(..., min_length=1, max_length=128, description="剧 ID")
    episode: int = Field(1, ge=1, le=10000, description="集")
    outline: Optional[str] = Field(None, max_length=4096, description="大纲")


# ============================================================================
# Aesthetic
# ============================================================================

class AestheticScoreRequest(BaseModel):
    image_path: str = Field(..., min_length=1, max_length=4096, description="图片路径")
    model: Optional[str] = Field(None, max_length=64, description="评分模型")


class AestheticScoreBatchRequest(BaseModel):
    image_paths: List[str] = Field(..., min_length=1, max_length=100, description="图片路径列表")
    model: Optional[str] = Field(None, max_length=64)


class AestheticEloCompareRequest(BaseModel):
    image_a: str = Field(..., min_length=1, max_length=4096, description="图片 A")
    image_b: str = Field(..., min_length=1, max_length=4096, description="图片 B")
    winner: Literal["a", "b", "draw"] = Field(..., description="胜方")


class AestheticEloRegisterRequest(BaseModel):
    image_path: str = Field(..., min_length=1, max_length=4096, description="图片路径")
    initial_rating: float = Field(1500.0, ge=0.0, le=5000.0, description="初始分")


# ============================================================================
# Admin
# ============================================================================

class AdminUserRoleUpdate(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    role: Literal["viewer", "annotator", "reviewer", "admin"] = Field(..., description="新角色")


class AdminUserDisable(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    reason: Optional[str] = Field(None, max_length=512)


class AdminUserQuota(BaseModel):
    username: str = Field(..., min_length=1, max_length=64, description="用户名")
    quota_mb: int = Field(..., ge=0, le=10**9, description="配额 (MB)")


# ============================================================================
# Auth
# ============================================================================

class AuthRegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_\-]+$")
    password: str = Field(..., min_length=8, max_length=128, description="密码")
    role: Literal["viewer", "annotator", "reviewer", "admin"] = Field("viewer")


class AuthLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class AuthRefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=4096)


class AuthPasswordChange(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


# ============================================================================
# OSS
# ============================================================================

class OSSUploadRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=256, description="对象键")
    content: str = Field("", max_length=100_000_000, description="内容")
    metadata: Optional[Dict[str, str]] = Field(None, description="元数据")


class OSSSyncRequest(BaseModel):
    target: Literal["object", "vector", "table", "all"] = Field("all", description="同步目标")


# ============================================================================
# Transfer cleanup
# ============================================================================

class TransferCleanupRequest(BaseModel):
    older_than_days: int = Field(30, ge=0, le=3650, description="清理多少天前的")
    confirm: bool = Field(False, description="确认")