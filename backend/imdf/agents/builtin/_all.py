"""All 23 built-in concrete agent classes.

We keep every concrete agent in a single module so the import
order in :mod:`builtin` is deterministic and so the unit tests can
``importlib.reload`` the whole bundle in one shot.  Each class is
intentionally minimal:

  * it sets the metadata class attributes from
    ``AGENT_REGISTRY``'s entry (single source of truth)
  * it implements :meth:`execute` to return a structural result
    that mirrors ``AgentExecutor._run_full_auto``'s output

The :class:`AgentType` enum is imported lazily inside
:meth:`execute` to avoid the circular import between
``imdf.agents`` and ``services.agent_service.agents``.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from ..base import AgentContext, AgentResult, BaseAgent


# ── Local helper: import the canonical AgentType lazily ───────────────────
def _agent_type_enum():
    """Return the :class:`AgentType` enum from
    ``services.agent_service.agents`` (lazy import)."""
    from services.agent_service.agents import AgentType  # type: ignore
    return AgentType


def _make_step_list(slug: str) -> List[str]:
    """Return the canonical step list for an agent slug.

    Mirrors the static ``AGENT_SKELETONS`` dict in
    ``services/agent_service/executor.py`` so a registered agent's
    plan matches what the executor would have produced for the same
    task.
    """
    # The keys here match the slug values in AgentType.
    table: Dict[str, List[str]] = {
        "requirement_parser": [
            "extract_content_type",
            "extract_style_prefs",
            "estimate_volume",
            "build_production_plan",
        ],
        "data_collection": [
            "deduplicate_sources", "fetch_batch", "store_in_dam",
        ],
        "cleaning": [
            "dedup", "nsfw_filter", "blur_filter", "ocr_normalize", "tag",
        ],
        "prelabel": [
            "select_model", "run_inference", "store_prelabels",
        ],
        "fine_annotation": [
            "assign_annotators", "collect_labels", "consensus",
        ],
        "review": [
            "queue_for_review", "reviewer_decision", "publish",
        ],
        "scoring": ["aesthetic", "quality", "compose"],
        "filtering": ["load_thresholds", "apply", "emit"],
        "export": ["pick_format", "write", "verify"],
        "evaluation": ["load_dataset", "run_model", "aggregate_metrics"],
        "badcase_analysis": ["cluster", "summarise", "tag_root_cause"],
        "feedback": ["collect_signals", "rank", "schedule"],
        "memory": ["lookup_scope", "upsert"],
        "scheduling": ["decompose", "enqueue", "wait_for_completion"],
        "quality": ["sla", "accuracy", "consistency"],
        "generation_director": [
            "parse_brief", "schedule_workers", "fan_out",
        ],
        "generation_storyboard": [
            "split_script", "build_scenes", "allocate_shots",
        ],
        "generation_character": [
            "lookup_pool", "lock_consistency", "embed",
        ],
        "generation_image": [
            "txt2img", "img2img", "controlnet",
        ],
        "generation_video": [
            "img2vid", "interpolate_frames", "apply_camera_motion",
        ],
        "generation_voice": [
            "tts", "music_gen", "lip_sync",
        ],
        "generation_qa": [
            "clip_score", "aesthetic", "nsfw", "consistency",
        ],
        "skill_orchestrator": [
            "auto_route", "run_skill", "chain_or_fallback",
        ],
    }
    return list(table.get(slug, []))


def _run(agent: BaseAgent, context: AgentContext) -> AgentResult:
    """Default ``execute`` body used by every concrete agent.

    Mirrors ``AgentExecutor._run_full_auto``'s output shape so the
    executor can switch from metadata-lookup to class-lookup without
    any consumer-visible difference.  The agent's :attr:`plan` is
    the source of the step list — concrete agents override
    :meth:`plan` only when their default is wrong.
    """
    err = agent.validate(context)
    if err is not None:
        return AgentResult(
            ok=False,
            task_id=context.task_id,
            agent_type=agent.get_agent_type_slug(),
            output={},
            plan=[],
            error=err,
            error_source="validate",
        )
    steps = agent.plan(context) or _make_step_list(agent.get_agent_type_slug())
    return AgentResult(
        ok=True,
        task_id=context.task_id,
        agent_type=agent.get_agent_type_slug(),
        output={
            "agent_name": agent.name,
            "mode": context.mode,
            "downstream_service": agent.downstream_service,
            "capabilities": list(agent.capabilities),
            "metadata": dict(context.metadata),
            "input": dict(context.input),
            "executed_at": time.time(),
        },
        plan=steps,
        error=None,
        error_source=None,
    )


# ── Helpers to build the 23 classes with shared boilerplate ───────────────
def _make_agent_class(
    *,
    slug: str,
    cls_name: str,
    name: str,
    description: str,
    default_mode: str,
    default_priority: int,
    max_retries: int,
    timeout_seconds: int,
    downstream_service: str | None,
    capabilities: List[str],
) -> type:
    """Build a concrete :class:`BaseAgent` subclass with the given
    metadata.  The class' ``execute`` method is bound to the shared
    ``_run`` helper via a closure."""

    def execute(self, context: AgentContext) -> AgentResult:  # type: ignore[override]
        return _run(self, context)

    attrs: Dict[str, Any] = {
        "__doc__": f"{name} ({slug}) — concrete BaseAgent.",
        "__module__": __name__,  # so repr/pickle don't leak the base class
        "name": name,
        "description": description,
        "capabilities": list(capabilities),
        "default_mode": default_mode,
        "default_priority": int(default_priority),
        "max_retries": int(max_retries),
        "timeout_seconds": int(timeout_seconds),
        "downstream_service": downstream_service,
        "agent_type": slug,
        "execute": execute,
    }
    return type(cls_name, (BaseAgent,), attrs)


# ── The 23 concrete agent classes ──────────────────────────────────────────
# Metadata here mirrors ``AGENT_REGISTRY`` in
# ``services/agent_service/agents.py`` verbatim — the loader
# asserts on equality via the test suite.
AGENT_META: List[Dict[str, Any]] = [
    dict(slug="requirement_parser", cls_name="RequirementParserAgent",
         name="Requirement Parser", description="需求解析",
         default_mode="semi_auto", default_priority=8, max_retries=2,
         timeout_seconds=60, downstream_service="user-service",
         capabilities=["nlp", "intent_classification", "schema_extraction"]),
    dict(slug="data_collection", cls_name="DataCollectionAgent",
         name="Data Collection", description="采集",
         default_mode="full_auto", default_priority=7, max_retries=3,
         timeout_seconds=1800, downstream_service="asset-service",
         capabilities=["crawler", "scraper", "synthetic_generation"]),
    dict(slug="cleaning", cls_name="CleaningAgent",
         name="Cleaning", description="清洗",
         default_mode="full_auto", default_priority=6, max_retries=2,
         timeout_seconds=600, downstream_service="cleaning-service",
         capabilities=["deduplication", "nsfw_filter", "quality_filter", "pii_redact"]),
    dict(slug="prelabel", cls_name="PrelabelAgent",
         name="Prelabel", description="预标注",
         default_mode="semi_auto", default_priority=5, max_retries=2,
         timeout_seconds=900, downstream_service="annotation-service",
         capabilities=["model_inference", "label_propagation", "active_learning"]),
    dict(slug="fine_annotation", cls_name="FineAnnotationAgent",
         name="Fine Annotation", description="精标注",
         default_mode="manual", default_priority=5, max_retries=1,
         timeout_seconds=7200, downstream_service="annotation-service",
         capabilities=["manual_annotation", "assisted_annotation", "consensus"]),
    dict(slug="review", cls_name="ReviewAgent",
         name="Review", description="审核",
         default_mode="manual", default_priority=4, max_retries=1,
         timeout_seconds=3600, downstream_service="annotation-service",
         capabilities=["review", "approval", "rejection_reasoning"]),
    dict(slug="scoring", cls_name="ScoringAgent",
         name="Scoring", description="评分",
         default_mode="full_auto", default_priority=4, max_retries=2,
         timeout_seconds=600, downstream_service="scoring-service",
         capabilities=["aesthetic", "quality_score", "rank"]),
    dict(slug="filtering", cls_name="FilteringAgent",
         name="Filtering", description="筛选",
         default_mode="full_auto", default_priority=3, max_retries=2,
         timeout_seconds=300, downstream_service="cleaning-service",
         capabilities=["threshold", "rule_engine", "tag_based"]),
    dict(slug="export", cls_name="ExportAgent",
         name="Export", description="导出",
         default_mode="full_auto", default_priority=2, max_retries=3,
         timeout_seconds=1200, downstream_service="dataset-service",
         capabilities=["jsonl", "parquet", "coco", "yolo"]),
    dict(slug="evaluation", cls_name="EvaluationAgent",
         name="Evaluation", description="评测",
         default_mode="full_auto", default_priority=3, max_retries=2,
         timeout_seconds=3600, downstream_service="evaluation-service",
         capabilities=["model_eval", "metric_aggregation", "report"]),
    dict(slug="badcase_analysis", cls_name="BadcaseAnalysisAgent",
         name="Badcase Analysis", description="BadCase 分析",
         default_mode="semi_auto", default_priority=4, max_retries=2,
         timeout_seconds=900, downstream_service="evaluation-service",
         capabilities=["clustering", "summarisation", "root_cause"]),
    dict(slug="feedback", cls_name="FeedbackAgent",
         name="Feedback", description="反馈",
         default_mode="full_auto", default_priority=3, max_retries=2,
         timeout_seconds=300, downstream_service="annotation-service",
         capabilities=["feedback_loop", "policy_update"]),
    dict(slug="memory", cls_name="MemoryAgent",
         name="Memory", description="记忆",
         default_mode="full_auto", default_priority=2, max_retries=2,
         timeout_seconds=60, downstream_service="agent-service",
         capabilities=["short_term", "long_term", "vector_recall"]),
    dict(slug="scheduling", cls_name="SchedulingAgent",
         name="Scheduling", description="调度",
         default_mode="full_auto", default_priority=6, max_retries=3,
         timeout_seconds=120, downstream_service="agent-service",
         capabilities=["queue", "priority", "retry", "backpressure"]),
    dict(slug="quality", cls_name="QualityAgent",
         name="Quality", description="质检",
         default_mode="full_auto", default_priority=4, max_retries=1,
         timeout_seconds=600, downstream_service="evaluation-service",
         capabilities=["sla_check", "accuracy_check", "consistency_check"]),
    dict(slug="generation_director", cls_name="GenerationDirectorAgent",
         name="Generation Director", description="生成-导演",
         default_mode="full_auto", default_priority=7, max_retries=1,
         timeout_seconds=60, downstream_service="asset-service",
         capabilities=["brief_parsing", "scheduling", "fan_out"]),
    dict(slug="generation_storyboard", cls_name="GenerationStoryboardAgent",
         name="Generation Storyboard", description="生成-分镜",
         default_mode="full_auto", default_priority=6, max_retries=1,
         timeout_seconds=60, downstream_service="asset-service",
         capabilities=["script_parse", "scene_split", "shot_alloc"]),
    dict(slug="generation_character", cls_name="GenerationCharacterAgent",
         name="Generation Character", description="生成-角色",
         default_mode="full_auto", default_priority=6, max_retries=1,
         timeout_seconds=60, downstream_service="asset-service",
         capabilities=["character_lookup", "consistency_lock", "embedding"]),
    dict(slug="generation_image", cls_name="GenerationImageAgent",
         name="Generation Image", description="生成-图像",
         default_mode="full_auto", default_priority=5, max_retries=2,
         timeout_seconds=600, downstream_service="asset-service",
         capabilities=["txt2img", "img2img", "controlnet"]),
    dict(slug="generation_video", cls_name="GenerationVideoAgent",
         name="Generation Video", description="生成-视频",
         default_mode="full_auto", default_priority=5, max_retries=2,
         timeout_seconds=1800, downstream_service="asset-service",
         capabilities=["img2vid", "interpolation", "camera_motion"]),
    dict(slug="generation_voice", cls_name="GenerationVoiceAgent",
         name="Generation Voice", description="生成-语音/音乐",
         default_mode="full_auto", default_priority=4, max_retries=2,
         timeout_seconds=300, downstream_service="asset-service",
         capabilities=["tts", "music_gen", "lip_sync"]),
    dict(slug="generation_qa", cls_name="GenerationQaAgent",
         name="Generation QA", description="生成-QA",
         default_mode="full_auto", default_priority=4, max_retries=1,
         timeout_seconds=120, downstream_service="asset-service",
         capabilities=["clip_score", "aesthetic", "nsfw", "consistency"]),
    dict(slug="skill_orchestrator", cls_name="SkillOrchestratorAgent",
         name="Skill Orchestrator", description="Skill 编排",
         default_mode="semi_auto", default_priority=6, max_retries=1,
         timeout_seconds=300, downstream_service="agent-service",
         capabilities=["skill_run", "skill_chain", "skill_auto_route",
                       "skill_marketplace", "obsidian_wiki", "llm_kb"]),
]


# ── Build the 23 classes & expose them at module scope ─────────────────────
def _build_module_globals() -> Dict[str, type]:
    """Materialise every concrete class and return a ``name -> class``
    map ready to be merged into ``globals()``."""
    out: Dict[str, type] = {}
    for meta in AGENT_META:
        cls = _make_agent_class(**meta)
        out[meta["cls_name"]] = cls
    return out


_module_globals = _build_module_globals()
globals().update(_module_globals)


# Exposed for the test suite so it can iterate without touching
# ``dir()``.
def get_builtin_classes() -> List[type]:
    """Return the list of all 23 built-in concrete classes."""
    return list(_module_globals.values())


def get_builtin_slugs() -> List[str]:
    """Return the canonical slug list (matches ``AgentType.values``)."""
    return [m["slug"] for m in AGENT_META]


__all__ = (
    list(_module_globals.keys())
    + ["AGENT_META", "get_builtin_classes", "get_builtin_slugs",
       "_make_step_list"]
)
