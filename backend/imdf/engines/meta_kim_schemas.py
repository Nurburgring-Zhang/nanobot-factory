"""P19 v5.3 — Meta_Kim Governance Loop Schemas (V5 Chapter 27).

Pydantic v2 typed contracts for the 7-step governance loop:

    clarify (intent) → search (capability) → select (owner)
    → split (task) → execute → verify → learn (write-back)

These schemas are the canonical wire format for the governance loop. They are
intentionally narrow (only fields the loop reads/writes) so they can be reused
across HTTP routes, CLI flags, test fixtures, and persisted JSON audit rows.

Why a separate file?
    The original P19-B4 skeleton (``meta_kim_engine.py``) used plain dataclasses
    for the 8-stage loop. V5 chapter 27 calls for a Pydantic v2 model so the
    contracts can be validated against ``response_format="json"`` LLM output,
    serialised to JSON Schema, and reused by downstream services.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class IntentType(str, Enum):
    """The canonical 12 IntentType categories referenced by V5 chapter 27."""

    DATA_ACQUISITION = "data_acquisition"
    DATA_CLEANING = "data_cleaning"
    ANNOTATION = "annotation"
    EXPORT = "export"
    SEARCH = "search"
    CLASSIFICATION = "classification"
    REVIEW = "review"
    QC = "qc"
    TRANSFORM = "transform"
    PUBLISH = "publish"
    ORCHESTRATION = "orchestration"
    UNKNOWN = "unknown"


class OwnerKind(str, Enum):
    """Who runs a task — bot / auto / human-required / hybrid."""

    BOT = "bot"
    AUTO = "auto"
    HUMAN_REQUIRED = "human_required"
    HYBRID = "hybrid"


class VerifyCriterionType(str, Enum):
    """The 4 supported verify criteria from V5 chapter 27.6."""

    AUTOMATED_TEST = "automated_test"
    QUALITY_THRESHOLD = "quality_threshold"
    COUNT_CHECK = "count_check"
    HUMAN_REVIEW = "human_review"


class LessonType(str, Enum):
    """What kind of lesson to record."""

    SUCCESS = "success"
    FAILURE = "failure"


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class Intent(BaseModel):
    """Structured user intent after Step 1 (Clarify).

    Output of the LLM ``complete(prompt, response_format="json")`` call.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    intent_id: str = Field(default_factory=lambda: _new_id("intent"))
    intent_type: IntentType = IntentType.UNKNOWN
    description: str = ""
    success_standard: Dict[str, Any] = Field(default_factory=dict)
    constraints: Dict[str, Any] = Field(default_factory=dict)
    clarifying_questions: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    raw_request: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utc_now_iso)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))

    @field_validator("success_standard", "constraints", mode="before")
    @classmethod
    def _ensure_dict(cls, v: Any) -> Dict[str, Any]:
        return dict(v) if isinstance(v, dict) else {}

    @field_validator("clarifying_questions", mode="before")
    @classmethod
    def _ensure_list(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)]


class Capability(BaseModel):
    """A capability candidate from the registry (Step 2 output).

    A thin wrapper around ``capabilities_v2.engine.Capability`` so that the
    governance loop can operate without taking a hard dependency on it.
    """

    model_config = ConfigDict(extra="allow")

    capability_id: str
    name: str = ""
    category: str = "general"
    description: str = ""
    relevance_score: float = 0.0
    automatable: bool = True
    tags: List[str] = Field(default_factory=list)
    owner: str = "platform"
    embedding: Optional[List[float]] = None


class Task(BaseModel):
    """One bounded subtask produced by Step 4 (Split)."""

    model_config = ConfigDict(extra="allow")

    task_id: str = Field(default_factory=lambda: _new_id("task"))
    name: str
    description: str = ""
    capability_id: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    estimated_duration_min: int = 5
    inputs: Dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"  # pending | running | success | failed
    output: Dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class VerifyCriterion(BaseModel):
    """One of the 4 supported verify criteria (Step 6 input)."""

    model_config = ConfigDict(extra="allow")

    type: VerifyCriterionType
    description: str = ""
    # For AUTOMATED_TEST:
    test_id: Optional[str] = None
    # For QUALITY_THRESHOLD:
    metric: Optional[str] = None
    threshold: Optional[float] = None
    # For COUNT_CHECK:
    min_count: Optional[int] = None


class VerifiedResult(BaseModel):
    """Outcome of Step 6 (Verify)."""

    model_config = ConfigDict(extra="allow")

    succeeded: bool = False
    requires_human_review: bool = False
    message: str = ""
    failures: List[str] = Field(default_factory=list)
    score: float = 0.0
    details: Dict[str, Any] = Field(default_factory=dict)


class Lesson(BaseModel):
    """A learned lesson produced by Step 7 (Learn)."""

    model_config = ConfigDict(extra="allow")

    lesson_id: str = Field(default_factory=lambda: _new_id("lesson"))
    type: LessonType
    description: str
    action: str = ""  # create_skill | needs_improvement | manual_review
    content: Dict[str, Any] = Field(default_factory=dict)
    run_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utc_now_iso)


class TaskExecution(BaseModel):
    """Combined execution result for one Task."""

    model_config = ConfigDict(extra="allow")

    task_id: str
    task_name: str
    status: str
    output: Dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0


class GovernedReport(BaseModel):
    """Aggregate governance report at the end of Step 7."""

    model_config = ConfigDict(extra="allow")

    run_id: str
    intent_type: str
    owner_kind: OwnerKind
    task_count: int = 0
    succeeded: bool = False
    requires_human_review: bool = False
    lessons_count: int = 0
    skill_created: Optional[str] = None
    failure_recorded: bool = False
    summary: str = ""
    created_at: str = Field(default_factory=_utc_now_iso)


class GovernedRun(BaseModel):
    """Top-level envelope returned by ``MetaKimEngine.govern_run``."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: _new_id("gov"))
    request: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    intent: Optional[Intent] = None
    capabilities: List[Capability] = Field(default_factory=list)
    owner: OwnerKind = OwnerKind.AUTO
    tasks: List[Task] = Field(default_factory=list)
    results: List[TaskExecution] = Field(default_factory=list)
    verified: Optional[VerifiedResult] = None
    lessons: List[Lesson] = Field(default_factory=list)
    report: Optional[GovernedReport] = None
    created_at: str = Field(default_factory=_utc_now_iso)


__all__ = [
    "IntentType",
    "OwnerKind",
    "VerifyCriterionType",
    "LessonType",
    "Intent",
    "Capability",
    "Task",
    "VerifyCriterion",
    "VerifiedResult",
    "Lesson",
    "TaskExecution",
    "GovernedReport",
    "GovernedRun",
]