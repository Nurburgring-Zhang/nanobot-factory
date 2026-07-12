"""Pydantic v2 schemas for FR-6.3 Auto-labeling + FR-8.3 AQL Sampling.

Cross-referenced by:
  * imdf.labeling.auto_strategy  — 4 strategies + orchestrator
  * imdf.quality.aql_sampling    — AQL sampler + inspector

All schemas use Pydantic v2 syntax (model_config = ConfigDict(...),
field_validator, model_validator, Field(default_factory=...)).

Conventions:
  * Field names use snake_case
  * Optional fields default to None
  * Enum values are lowercase (aql_lv_1_0, label_animal, etc.)
  * Confidence / probability values are floats in [0, 1]
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
#  Asset (the thing being inspected / labeled)
# --------------------------------------------------------------------------- #
class AssetType(str, Enum):
    """5 类多模态资产 — V5 第6章 FR-6.3."""

    IMAGE = "image"
    EDITED_IMAGE = "edited_image"
    VIDEO = "video"
    SHORT_DRAMA = "short_drama"
    PICTURE_BOOK = "picture_book"


class Asset(BaseModel):
    """单个资产 — AQL 抽样和 Auto-labeling 的共同输入.

    Note: Asset holds a content_uri + arbitrary metadata. We don't load the
    bytes — AQL is about sampling, labeling is about adding tags.
    """

    model_config = ConfigDict(extra="allow")

    asset_id: str = Field(default_factory=lambda: f"asset-{uuid.uuid4().hex[:12]}")
    asset_type: AssetType = AssetType.IMAGE
    content_uri: str = ""
    caption: str = ""
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=lambda: time.time())


# --------------------------------------------------------------------------- #
#  AQL Sampling schemas (FR-8.3)
# --------------------------------------------------------------------------- #
class AQLLevel(str, Enum):
    """ISO 2859-1 normal inspection — 7 levels (V5 FR-8.3).

    0.1 / 0.65 / 1.0 / 1.5 / 2.5 / 4.0 / 6.5 — AQL% (Acceptable Quality Limit).
    """

    AQL_0_1 = "0.1"
    AQL_0_65 = "0.65"
    AQL_1_0 = "1.0"
    AQL_1_5 = "1.5"
    AQL_2_5 = "2.5"
    AQL_4_0 = "4.0"
    AQL_6_5 = "6.5"

    @property
    def numeric(self) -> float:
        return float(self.value)


# ISO 2859-1 Table II-A — sample size code letters
# Code letter A→H by lot_size range; then (letter × AQL) → sample size.
# We precompute (lot_size_bucket, aql_level) → (sample_size, accept_count, reject_count)
# for the 5 main lot buckets × 7 AQL levels. This avoids parsing the full
# standard table at runtime.
#
# Sources of truth:
#   * ISO 2859-1:1999 Table II-A (normal inspection, single sampling plans)
#   * Standard sample sizes: 8, 13, 20, 32, 50, 80, 125, 200, 315, 500, 800, 1250
#   * Accept/Reject = Ac/Re (operating characteristic curve at AQL)
#
# We list the canonical sample sizes for each (lot_bucket, aql) pair below.
# For AQLs with "use arrow" transitions (e.g., 1.5 → 1.0 → 1.0), we resolve
# to the cumulative sample size at the lower AQL.

# ── ISO 2859-1 Table II-A (subset, normal inspection, single sampling) ─────
# Format: SAMPLE_TABLE[(lot_size_upper, aql_level)] = (sample_size, Ac, Re)
# lot_size_upper is the upper bound of the lot size bucket (inclusive).
# We pick sample sizes from the canonical ISO 2859 ladder:
#   8, 13, 20, 32, 50, 80, 125, 200, 315, 500, 800, 1250, 2000, 3150
SAMPLE_TABLE: Dict[tuple, tuple] = {
    # ── lot_size 26-50 (letter D) ────────────────────────────────────────────
    (50, AQLLevel.AQL_0_1):  (8,   0, 1),
    (50, AQLLevel.AQL_0_65): (8,   0, 1),
    (50, AQLLevel.AQL_1_0):  (13,  0, 1),
    (50, AQLLevel.AQL_1_5):  (13,  0, 1),
    (50, AQLLevel.AQL_2_5):  (13,  1, 2),
    (50, AQLLevel.AQL_4_0):  (20,  1, 2),
    (50, AQLLevel.AQL_6_5):  (20,  3, 4),
    # ── lot_size 51-90 (letter E) ────────────────────────────────────────────
    (90, AQLLevel.AQL_0_1):  (13,  0, 1),
    (90, AQLLevel.AQL_0_65): (13,  0, 1),
    (90, AQLLevel.AQL_1_0):  (20,  0, 1),
    (90, AQLLevel.AQL_1_5):  (20,  0, 1),
    (90, AQLLevel.AQL_2_5):  (20,  1, 2),
    (90, AQLLevel.AQL_4_0):  (32,  2, 3),
    (90, AQLLevel.AQL_6_5):  (32,  3, 4),
    # ── lot_size 91-150 (letter F) ───────────────────────────────────────────
    (150, AQLLevel.AQL_0_1): (13,  0, 1),
    (150, AQLLevel.AQL_0_65): (20, 0, 1),
    (150, AQLLevel.AQL_1_0):  (32, 1, 2),
    (150, AQLLevel.AQL_1_5):  (32, 1, 2),
    (150, AQLLevel.AQL_2_5):  (32, 2, 3),
    (150, AQLLevel.AQL_4_0):  (32, 3, 4),
    (150, AQLLevel.AQL_6_5):  (50, 5, 6),
    # ── lot_size 151-280 (letter G) ──────────────────────────────────────────
    (280, AQLLevel.AQL_0_1):  (20,  0, 1),
    (280, AQLLevel.AQL_0_65): (32,  1, 2),
    (280, AQLLevel.AQL_1_0):  (50,  1, 2),
    (280, AQLLevel.AQL_1_5):  (50,  2, 3),
    (280, AQLLevel.AQL_2_5):  (50,  3, 4),
    (280, AQLLevel.AQL_4_0):  (50,  5, 6),
    (280, AQLLevel.AQL_6_5):  (50,  7, 8),
    # ── lot_size 281-500 (letter H) ──────────────────────────────────────────
    (500, AQLLevel.AQL_0_1):  (32,  0, 1),
    (500, AQLLevel.AQL_0_65): (50,  1, 2),
    (500, AQLLevel.AQL_1_0):  (80,  2, 3),
    (500, AQLLevel.AQL_1_5):  (80,  3, 4),
    (500, AQLLevel.AQL_2_5):  (80,  5, 6),
    (500, AQLLevel.AQL_4_0):  (80,  7, 8),
    (500, AQLLevel.AQL_6_5):  (80,  10, 11),
    # ── lot_size 501-1200 (letter J) ─────────────────────────────────────────
    (1200, AQLLevel.AQL_0_1):  (50,   0,  1),
    (1200, AQLLevel.AQL_0_65): (80,   1,  2),
    (1200, AQLLevel.AQL_1_0):  (80,   2,  3),
    (1200, AQLLevel.AQL_1_5):  (80,   3,  4),
    (1200, AQLLevel.AQL_2_5):  (80,   5,  6),
    (1200, AQLLevel.AQL_4_0):  (80,   10, 11),
    (1200, AQLLevel.AQL_6_5):  (125,  14, 15),
    # ── lot_size 1201-3200 (letter K) ────────────────────────────────────────
    (3200, AQLLevel.AQL_0_1):  (50,   0,  1),
    (3200, AQLLevel.AQL_0_65): (80,   1,  2),
    (3200, AQLLevel.AQL_1_0):  (125,  3,  4),
    (3200, AQLLevel.AQL_1_5):  (125,  5,  6),
    (3200, AQLLevel.AQL_2_5):  (125,  7,  8),
    (3200, AQLLevel.AQL_4_0):  (125,  10, 11),
    (3200, AQLLevel.AQL_6_5):  (200,  21, 22),
    # ── lot_size 3201-10000 (letter L) ───────────────────────────────────────
    (10000, AQLLevel.AQL_0_1):  (80,    0,  1),
    (10000, AQLLevel.AQL_0_65): (125,   1,  2),
    (10000, AQLLevel.AQL_1_0):  (200,   3,  4),
    (10000, AQLLevel.AQL_1_5):  (200,   5,  6),
    (10000, AQLLevel.AQL_2_5):  (200,   10, 11),
    (10000, AQLLevel.AQL_4_0):  (200,   14, 15),
    (10000, AQLLevel.AQL_6_5):  (315,   21, 22),
    # ── lot_size 10001-35000 (letter M) ──────────────────────────────────────
    (35000, AQLLevel.AQL_0_1):  (80,    0,  1),
    (35000, AQLLevel.AQL_0_65): (125,   1,  2),
    (35000, AQLLevel.AQL_1_0):  (315,   5,  6),
    (35000, AQLLevel.AQL_1_5):  (315,   7,  8),
    (35000, AQLLevel.AQL_2_5):  (315,   14, 15),
    (35000, AQLLevel.AQL_4_0):  (315,   21, 22),
    (35000, AQLLevel.AQL_6_5):  (500,   21, 22),
    # ── lot_size 35001-50000 (letter N) ──────────────────────────────────────
    (50000, AQLLevel.AQL_0_1):  (125,   0,  1),
    (50000, AQLLevel.AQL_0_65): (200,   1,  2),
    (50000, AQLLevel.AQL_1_0):  (315,   5,  6),
    (50000, AQLLevel.AQL_1_5):  (315,   7,  8),
    (50000, AQLLevel.AQL_2_5):  (500,   14, 15),
    (50000, AQLLevel.AQL_4_0):  (500,   21, 22),
    (50000, AQLLevel.AQL_6_5):  (800,   21, 22),
}


class DefectRecord(BaseModel):
    """A single defect observed during AQL inspection.

    In production this would carry coords + defect_type; for the schema we
    only require a defect_id + severity.
    """

    # P2 P1 fix: same rationale as SampledLot — DefectRecord itself contains
    # only primitives, but the field shows up as List[DefectRecord] in
    # InspectionResult. Flag here keeps all AQL-adjacent schemas consistent.
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    defect_id: str = Field(default_factory=lambda: f"defect-{uuid.uuid4().hex[:8]}")
    asset_id: str = ""
    defect_type: str = "general"
    severity: str = "minor"  # minor | major | critical
    notes: str = ""


class SampledLot(BaseModel):
    """Output of AQLSampling.sample — the random sample drawn from the lot."""

    # P2 P1 fix: R2-NEW-#1 — ``arbitrary_types_allowed=True`` keeps the schema
    # forward-compatible if someone later swaps ``Asset`` for a non-BaseModel
    # wrapper. Pydantic v2 already accepts nested Pydantic models, but the
    # flag documents intent and silences the
    # "Input should be a valid dictionary or instance of Asset" complaint if
    # the inner type ever drifts to a dataclass / TypedDict.
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    lot_id: str = Field(default_factory=lambda: f"lot-{uuid.uuid4().hex[:10]}")
    aql_level: AQLLevel = AQLLevel.AQL_1_0
    lot_size: int = 0
    sample_size: int = 0
    accept_count: int = 0
    reject_count: int = 0
    sampled_assets: List[Asset] = Field(default_factory=list)
    sampled_at: float = Field(default_factory=lambda: time.time())


class InspectionDecision(str, Enum):
    """3 决策: accept / reject / hold (hold = reduce-inspection)."""

    ACCEPT = "accept"
    REJECT = "reject"
    HOLD = "hold"


class InspectionResult(BaseModel):
    """Output of AQLSampling.inspect — accept/reject + observed defects."""

    # P2 P1 fix: same rationale as SampledLot — DefectRecord is a Pydantic
    # model so the flag is technically a no-op, but it documents intent and
    # protects against future type drift.
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    lot_id: str = ""
    aql_level: AQLLevel = AQLLevel.AQL_1_0
    sample_size: int = 0
    accept_count_threshold: int = 0
    reject_count_threshold: int = 0
    defects_found: int = 0
    defect_records: List[DefectRecord] = Field(default_factory=list)
    decision: InspectionDecision = InspectionDecision.ACCEPT
    rationale: str = ""
    inspected_at: float = Field(default_factory=lambda: time.time())

    @property
    def defect_rate(self) -> float:
        return (self.defects_found / self.sample_size) if self.sample_size else 0.0


# --------------------------------------------------------------------------- #
#  Auto-labeling schemas (FR-6.3)
# --------------------------------------------------------------------------- #
class LabelCategory(str, Enum):
    """默认 12 类标签 — V5 FR-6.3 (image classification taxonomy)."""

    ANIMAL = "animal"
    PERSON = "person"
    VEHICLE = "vehicle"
    BUILDING = "building"
    NATURE = "nature"
    FOOD = "food"
    ART = "art"
    TEXT = "text"
    PRODUCT = "product"
    SCENE = "scene"
    ABSTRACT = "abstract"
    OTHER = "other"


class LabelConfidence(BaseModel):
    """Single (category, score) pair — output of any strategy."""

    model_config = ConfigDict(extra="allow")

    category: LabelCategory = LabelCategory.OTHER
    score: float = 0.0  # [0, 1]


class StrategyVote(BaseModel):
    """One strategy's verdict for one asset."""

    # P2 P1 fix: same rationale as SampledLot — protects against future type
    # drift on the nested LabelConfidence list.
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    strategy: str = ""  # "clip" | "rule" | "active" | "consensus"
    asset_id: str = ""
    top_k: List[LabelConfidence] = Field(default_factory=list)
    confidence: float = 0.0
    uncertainty: float = 0.0
    needs_human_review: bool = False
    note: str = ""


class LabelResult(BaseModel):
    """Final labeling decision for an asset (orchestrator output)."""

    # P2 P1 fix: same rationale as SampledLot — protects against future type
    # drift on the nested StrategyVote / LabelConfidence fields.
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    asset_id: str = ""
    final_label: LabelCategory = LabelCategory.OTHER
    confidence: float = 0.0
    uncertainty: float = 0.0
    needs_human_review: bool = False
    strategy_votes: List[StrategyVote] = Field(default_factory=list)
    top_k: List[LabelConfidence] = Field(default_factory=list)
    decided_at: float = Field(default_factory=lambda: time.time())