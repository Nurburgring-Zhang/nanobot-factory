"""P3-3-W1: 15 Agent types + default config catalogue.

Each agent type corresponds to a distinct bounded context inside the data
factory pipeline (采集→清洗→预标注→精标注→审核→评分→筛选→导出→评测...).
The Agent dispatch framework routes incoming ``agent_tasks`` to one of the
15 agent implementations registered in :data:`AGENT_REGISTRY`.

The 15 agent types — in pipeline order:
  1.  requirement_parser  — 需求解析
  2.  data_collection     — 采集
  3.  cleaning            — 清洗
  4.  prelabel            — 预标注
  5.  fine_annotation     — 精标注
  6.  review              — 审核
  7.  scoring             — 评分
  8.  filtering           — 筛选
  9.  export              — 导出
  10. evaluation          — 评测
  11. badcase_analysis    — BadCase 分析
  12. feedback            — 反馈
  13. memory              — 记忆
  14. scheduling          — 调度
  15. quality             — 质检

Each entry stores:
  - id (str, slug)
  - name (str, Chinese label)
  - description (str)
  - default_mode (ExecutionMode)
  - default_priority (int, 1-10, 1=lowest)
  - max_retries (int)
  - timeout_seconds (int)
  - downstream_service (str | None)  — service that hosts the actual logic
  - capabilities (list[str])          — capability tags
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List


class AgentType(str, Enum):
    """The 15 agent type identifiers.

    Values are stable slugs used in URLs, DB columns, and API payloads.
    """

    REQUIREMENT_PARSER = "requirement_parser"
    DATA_COLLECTION = "data_collection"
    CLEANING = "cleaning"
    PRELABEL = "prelabel"
    FINE_ANNOTATION = "fine_annotation"
    REVIEW = "review"
    SCORING = "scoring"
    FILTERING = "filtering"
    EXPORT = "export"
    EVALUATION = "evaluation"
    BADCASE_ANALYSIS = "badcase_analysis"
    FEEDBACK = "feedback"
    MEMORY = "memory"
    SCHEDULING = "scheduling"
    QUALITY = "quality"
    # P4-5-W2: multi-modal generation agents (asset_service / iteration/)
    GENERATION_DIRECTOR = "generation_director"
    GENERATION_STORYBOARD = "generation_storyboard"
    GENERATION_CHARACTER = "generation_character"
    GENERATION_IMAGE = "generation_image"
    GENERATION_VIDEO = "generation_video"
    GENERATION_VOICE = "generation_voice"
    GENERATION_QA = "generation_qa"
    # P4-8-W1: extended-skills orchestrator (routes into the 10 built-in skills)
    SKILL_ORCHESTRATOR = "skill_orchestrator"


# Aggregate iteration helper — keeps the rest of the package from caring
# about the literal list above.
ALL_AGENT_TYPES: List[AgentType] = list(AgentType)


class ExecutionMode(str, Enum):
    """How an agent actually runs.

    - FULL_AUTO   — runs end-to-end, no human checkpoints
    - SEMI_AUTO   — produces a plan + per-step approval gates
    - MANUAL      — returns a draft; human executes the actions
    """

    FULL_AUTO = "full_auto"
    SEMI_AUTO = "semi_auto"
    MANUAL = "manual"


# ── Default config per agent type ────────────────────────────────────────────
# Keep this as plain dicts so the FastAPI layer can serialise them straight
# away without custom encoders.
AGENT_REGISTRY: Dict[AgentType, Dict[str, Any]] = {
    AgentType.REQUIREMENT_PARSER: {
        "id": AgentType.REQUIREMENT_PARSER.value,
        "name": "需求解析",
        "description": "Parse natural-language production briefs into structured plans.",
        "default_mode": ExecutionMode.SEMI_AUTO,
        "default_priority": 8,
        "max_retries": 2,
        "timeout_seconds": 60,
        "downstream_service": "user-service",
        "capabilities": ["nlp", "intent_classification", "schema_extraction"],
    },
    AgentType.DATA_COLLECTION: {
        "id": AgentType.DATA_COLLECTION.value,
        "name": "采集",
        "description": "Crawl, scrape, or generate raw data sources from a target list.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 7,
        "max_retries": 3,
        "timeout_seconds": 1800,
        "downstream_service": "asset-service",
        "capabilities": ["crawler", "scraper", "synthetic_generation"],
    },
    AgentType.CLEANING: {
        "id": AgentType.CLEANING.value,
        "name": "清洗",
        "description": "Run 32 cleaning operators (dedup / NSFW / blur / ocr / ...).",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 6,
        "max_retries": 2,
        "timeout_seconds": 600,
        "downstream_service": "cleaning-service",
        "capabilities": ["deduplication", "nsfw_filter", "quality_filter", "pii_redact"],
    },
    AgentType.PRELABEL: {
        "id": AgentType.PRELABEL.value,
        "name": "预标注",
        "description": "Run model-assisted pre-annotation passes for human refinement.",
        "default_mode": ExecutionMode.SEMI_AUTO,
        "default_priority": 5,
        "max_retries": 2,
        "timeout_seconds": 900,
        "downstream_service": "annotation-service",
        "capabilities": ["model_inference", "label_propagation", "active_learning"],
    },
    AgentType.FINE_ANNOTATION: {
        "id": AgentType.FINE_ANNOTATION.value,
        "name": "精标注",
        "description": "Drive the manual + assisted fine-annotation workflow.",
        "default_mode": ExecutionMode.MANUAL,
        "default_priority": 5,
        "max_retries": 1,
        "timeout_seconds": 7200,
        "downstream_service": "annotation-service",
        "capabilities": ["manual_annotation", "assisted_annotation", "consensus"],
    },
    AgentType.REVIEW: {
        "id": AgentType.REVIEW.value,
        "name": "审核",
        "description": "Reviewer passes: accept / reject / request changes on annotations.",
        "default_mode": ExecutionMode.MANUAL,
        "default_priority": 4,
        "max_retries": 1,
        "timeout_seconds": 3600,
        "downstream_service": "annotation-service",
        "capabilities": ["review", "approval", "rejection_reasoning"],
    },
    AgentType.SCORING: {
        "id": AgentType.SCORING.value,
        "name": "评分",
        "description": "Run 15 aesthetic / quality scoring operators + composite ranking.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 4,
        "max_retries": 2,
        "timeout_seconds": 600,
        "downstream_service": "scoring-service",
        "capabilities": ["aesthetic", "quality_score", "rank"],
    },
    AgentType.FILTERING: {
        "id": AgentType.FILTERING.value,
        "name": "筛选",
        "description": "Apply threshold-based filters using scoring + tag rules.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 3,
        "max_retries": 2,
        "timeout_seconds": 300,
        "downstream_service": "cleaning-service",
        "capabilities": ["threshold", "rule_engine", "tag_based"],
    },
    AgentType.EXPORT: {
        "id": AgentType.EXPORT.value,
        "name": "导出",
        "description": "Materialise the dataset into the target format (jsonl / parquet / coco).",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 2,
        "max_retries": 3,
        "timeout_seconds": 1200,
        "downstream_service": "dataset-service",
        "capabilities": ["jsonl", "parquet", "coco", "yolo"],
    },
    AgentType.EVALUATION: {
        "id": AgentType.EVALUATION.value,
        "name": "评测",
        "description": "Run a model evaluation task + collect per-sample metrics.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 3,
        "max_retries": 2,
        "timeout_seconds": 3600,
        "downstream_service": "evaluation-service",
        "capabilities": ["model_eval", "metric_aggregation", "report"],
    },
    AgentType.BADCASE_ANALYSIS: {
        "id": AgentType.BADCASE_ANALYSIS.value,
        "name": "BadCase 分析",
        "description": "Cluster & summarise the bad cases surfaced by an evaluation run.",
        "default_mode": ExecutionMode.SEMI_AUTO,
        "default_priority": 4,
        "max_retries": 2,
        "timeout_seconds": 900,
        "downstream_service": "evaluation-service",
        "capabilities": ["clustering", "summarisation", "root_cause"],
    },
    AgentType.FEEDBACK: {
        "id": AgentType.FEEDBACK.value,
        "name": "反馈",
        "description": "Push review + bad-case feedback into the labelling pipeline.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 3,
        "max_retries": 2,
        "timeout_seconds": 300,
        "downstream_service": "annotation-service",
        "capabilities": ["feedback_loop", "policy_update"],
    },
    AgentType.MEMORY: {
        "id": AgentType.MEMORY.value,
        "name": "记忆",
        "description": "Read / write the long-term Agent memory store.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 2,
        "max_retries": 2,
        "timeout_seconds": 60,
        "downstream_service": "agent-service",
        "capabilities": ["short_term", "long_term", "vector_recall"],
    },
    AgentType.SCHEDULING: {
        "id": AgentType.SCHEDULING.value,
        "name": "调度",
        "description": "Fan-out / fan-in + priority queueing for downstream agent tasks.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 6,
        "max_retries": 3,
        "timeout_seconds": 120,
        "downstream_service": "agent-service",
        "capabilities": ["queue", "priority", "retry", "backpressure"],
    },
    AgentType.QUALITY: {
        "id": AgentType.QUALITY.value,
        "name": "质检",
        "description": "Run cross-cutting quality gates (SLA / accuracy / consistency).",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 4,
        "max_retries": 1,
        "timeout_seconds": 600,
        "downstream_service": "evaluation-service",
        "capabilities": ["sla_check", "accuracy_check", "consistency_check"],
    },
    # P4-5-W2: multi-modal generation agents wired through asset-service /iteration
    AgentType.GENERATION_DIRECTOR: {
        "id": AgentType.GENERATION_DIRECTOR.value,
        "name": "生成-导演",
        "description": "DirectorAgent — parses brief, schedules the 6 worker agents.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 7,
        "max_retries": 1,
        "timeout_seconds": 60,
        "downstream_service": "asset-service",
        "capabilities": ["brief_parsing", "scheduling", "fan_out"],
    },
    AgentType.GENERATION_STORYBOARD: {
        "id": AgentType.GENERATION_STORYBOARD.value,
        "name": "生成-分镜",
        "description": "StoryboardAgent — splits script into scenes/shots.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 6,
        "max_retries": 1,
        "timeout_seconds": 60,
        "downstream_service": "asset-service",
        "capabilities": ["script_parse", "scene_split", "shot_alloc"],
    },
    AgentType.GENERATION_CHARACTER: {
        "id": AgentType.GENERATION_CHARACTER.value,
        "name": "生成-角色",
        "description": "CharacterAgent — locks characters from the pool to each shot (consistency).",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 6,
        "max_retries": 1,
        "timeout_seconds": 60,
        "downstream_service": "asset-service",
        "capabilities": ["character_lookup", "consistency_lock", "embedding"],
    },
    AgentType.GENERATION_IMAGE: {
        "id": AgentType.GENERATION_IMAGE.value,
        "name": "生成-图像",
        "description": "ImageAgent — generates per-shot still frames (txt2img / img2img).",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 5,
        "max_retries": 2,
        "timeout_seconds": 600,
        "downstream_service": "asset-service",
        "capabilities": ["txt2img", "img2img", "controlnet"],
    },
    AgentType.GENERATION_VIDEO: {
        "id": AgentType.GENERATION_VIDEO.value,
        "name": "生成-视频",
        "description": "VideoAgent — animates frames into shots (img2vid).",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 5,
        "max_retries": 2,
        "timeout_seconds": 1800,
        "downstream_service": "asset-service",
        "capabilities": ["img2vid", "interpolation", "camera_motion"],
    },
    AgentType.GENERATION_VOICE: {
        "id": AgentType.GENERATION_VOICE.value,
        "name": "生成-语音/音乐",
        "description": "VoiceAgent — voice-over TTS + background music.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 4,
        "max_retries": 2,
        "timeout_seconds": 300,
        "downstream_service": "asset-service",
        "capabilities": ["tts", "music_gen", "lip_sync"],
    },
    AgentType.GENERATION_QA: {
        "id": AgentType.GENERATION_QA.value,
        "name": "生成-QA",
        "description": "QAAgent — runs CLIP / aesthetic / NSFW scoring + consistency gating.",
        "default_mode": ExecutionMode.FULL_AUTO,
        "default_priority": 4,
        "max_retries": 1,
        "timeout_seconds": 120,
        "downstream_service": "asset-service",
        "capabilities": ["clip_score", "aesthetic", "nsfw", "consistency"],
    },
    # P4-8-W1: extended-skills orchestrator — runs the 10 built-in skills
    # (guizang_ppt / wewrite / humanizer_zh / etc.) either as a single skill
    # or as a chain.  Backed by backend.skills.orchestrator.SkillOrchestrator.
    AgentType.SKILL_ORCHESTRATOR: {
        "id": AgentType.SKILL_ORCHESTRATOR.value,
        "name": "Skill 编排",
        "description": "Run the VDP-2026 skill framework — 10 built-in skills + SkillOrchestrator (chain / retry / fallback).",
        "default_mode": ExecutionMode.SEMI_AUTO,
        "default_priority": 6,
        "max_retries": 1,
        "timeout_seconds": 300,
        "downstream_service": "agent-service",
        "capabilities": [
            "skill_run", "skill_chain", "skill_auto_route",
            "skill_marketplace", "obsidian_wiki", "llm_kb",
        ],
    },
}


# ── Public helpers ────────────────────────────────────────────────────────────
def get_agent_config(agent_type: str | AgentType) -> Dict[str, Any]:
    """Look up the config for an agent type.

    Raises ``KeyError`` (via ``__getitem__``) when the agent type is
    unknown.  This is the canonical contract — callers should catch
    ``KeyError`` to detect unknown agents.  We do NOT use
    ``AgentType(agent_type)`` because that raises ``ValueError`` instead,
    which makes the caller's exception handling verbose.
    """
    if isinstance(agent_type, AgentType):
        return AGENT_REGISTRY[agent_type]
    # str look-up — match by value, do not coerce via the enum (ValueError path)
    for member in AgentType:
        if member.value == agent_type:
            return AGENT_REGISTRY[member]
    raise KeyError(agent_type)


def list_agent_summaries() -> List[Dict[str, Any]]:
    """Return the full agent catalogue (id, name, description, default_mode,
    default_priority, downstream_service, capabilities)."""
    return [
        {
            "id": cfg["id"],
            "name": cfg["name"],
            "description": cfg["description"],
            "default_mode": cfg["default_mode"].value
            if isinstance(cfg["default_mode"], ExecutionMode)
            else cfg["default_mode"],
            "default_priority": cfg["default_priority"],
            "downstream_service": cfg["downstream_service"],
            "capabilities": cfg["capabilities"],
        }
        for cfg in AGENT_REGISTRY.values()
    ]


__all__ = [
    "AgentType",
    "ExecutionMode",
    "AGENT_REGISTRY",
    "AGENT_CLASS_REGISTRY",
    "ALL_AGENT_TYPES",
    "get_agent_config",
    "get_agent_class",
    "list_agent_summaries",
    "register_builtin_agent_classes",
    "reset_agent_class_registry_for_test",
]


# ── P6-Fix-P0-5: bridge the 23 BaseAgent classes ──────────────────────────
# The new plugin contract (see ``backend/imdf/agents/``) lets us
# reference agent types by *class* as well as by metadata dict.
# We expose ``AGENT_CLASS_REGISTRY`` (a ``AgentType -> BaseAgent
# subclass`` map) plus a ``get_agent_class`` helper, and we
# auto-register the 23 built-in classes on first access so the
# executor / routes can stay oblivious to the plugin layer.
from typing import TYPE_CHECKING  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover — typing only
    from imdf.agents.base import BaseAgent  # noqa: F401

_AGENT_CLASS_REGISTRY: Dict[AgentType, "type[BaseAgent]"] = {}
_agent_class_registry_loaded: bool = False


def _ensure_agent_class_registry_loaded() -> None:
    """Lazy-load + cache the 23 built-in agent classes.

    Importing :mod:`imdf.agents` is non-trivial (it pulls in
    pydantic + a couple of other deps), so we delay the import
    until the caller actually asks for an agent class.  The
    ``register_builtin_agent_classes`` public function is the
    explicit way to pre-load.
    """
    global _agent_class_registry_loaded
    if _agent_class_registry_loaded:
        return
    try:
        from imdf.agents import register_builtin_agents  # type: ignore
        from imdf.agents.registry import PluginRegistry  # type: ignore
    except Exception as e:  # noqa: BLE001
        # Plugin layer unavailable — leave the registry empty; the
        # executor can still run via the metadata dict path.
        import logging
        logging.getLogger(__name__).debug(
            "imdf.agents plugin layer unavailable: %s", e,
        )
        _agent_class_registry_loaded = True
        return
    reg = PluginRegistry.get_registry()
    register_builtin_agents(registry=reg)
    # Mirror plugin-registry bindings into the local typed dict.
    for slug, cls in reg.items():
        try:
            at = AgentType(slug)
        except ValueError:
            continue
        _AGENT_CLASS_REGISTRY[at] = cls
    _agent_class_registry_loaded = True


def register_builtin_agent_classes() -> List[AgentType]:
    """Force-load + register the 23 built-in agent classes.

    Idempotent.  Returns the list of :class:`AgentType` entries that
    ended up in :data:`AGENT_CLASS_REGISTRY`.
    """
    _ensure_agent_class_registry_loaded()
    return list(_AGENT_CLASS_REGISTRY.keys())


def get_agent_class(agent_type: str | AgentType) -> "type[BaseAgent]":
    """Look up the concrete :class:`BaseAgent` subclass for an
    agent type.

    Raises ``KeyError`` when no class is registered (the caller
    should treat this the same as a missing metadata entry).
    """
    _ensure_agent_class_registry_loaded()
    if isinstance(agent_type, AgentType):
        at = agent_type
    else:
        try:
            at = AgentType(agent_type)
        except ValueError as e:
            raise KeyError(agent_type) from e
    try:
        return _AGENT_CLASS_REGISTRY[at]
    except KeyError as e:
        raise KeyError(agent_type) from e


def reset_agent_class_registry_for_test() -> None:
    """Test-only: drop the cached class registry and reset the
    plugin singleton so the next ``get_agent_class`` call
    re-imports from scratch."""
    global _agent_class_registry_loaded
    _AGENT_CLASS_REGISTRY.clear()
    _agent_class_registry_loaded = False
    try:
        from imdf.agents.registry import PluginRegistry  # type: ignore
        PluginRegistry.reset_singleton()
    except Exception:  # noqa: BLE001
        pass


# Public alias for the typed registry.
AGENT_CLASS_REGISTRY: Dict[AgentType, "type[BaseAgent]"] = _AGENT_CLASS_REGISTRY
