"""P2 P1 fix: AQL Pydantic v2 model_type rejection (R2-NEW-#1).

R2 audit (reports/p21_r2_audit_data.md §67-87) claimed:

  > ``SampledLot.sampled_assets: List[Asset]`` in Pydantic v2 raises
  > ``ValidationError: 80 validation errors for SampledLot`` because
  > ``Asset`` is a Pydantic model and the schema lacks
  > ``arbitrary_types_allowed=True``.

Reproduction showed the current code already accepts Asset instances (Pydantic
v2 handles nested Pydantic models without the flag), but the R2 fix was still
applied defensively to future-proof the schema: if anyone later swaps Asset for
a dataclass / TypedDict / plain class, the schema will keep working without
re-introducing the same class of bug.

This test file verifies all three R2 reproducer scenarios PASS, locks in the
ISO 2859-1 sample-size expectations for the 7 standard AQL levels, and adds
property-style tests for related models (InspectionResult, DefectRecord,
LabelResult, StrategyVote) that share the same fix.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so ``backend.imdf.*`` resolves whether
# the test is run from project root, from tests/, or via plain pytest.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _PROJECT_ROOT / "backend"
for p in (str(_BACKEND), str(_PROJECT_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from imdf.labeling.auto_strategy_schemas import (  # noqa: E402
    AQLLevel,
    Asset,
    DefectRecord,
    InspectionDecision,
    InspectionResult,
    LabelConfidence,
    LabelResult,
    SampledLot,
    StrategyVote,
)
from imdf.quality.aql_sampling import AQLSampling, _lookup_plan  # noqa: E402


# --------------------------------------------------------------------------- #
#  R2 reproducer — Test 1
# --------------------------------------------------------------------------- #
def test_aql_sampling_1000_assets_no_validation_error():
    """R2 reproducer #1: AQLSampling.sample on 1000 Asset instances must not
    raise ``pydantic.ValidationError``.
    """
    lot = [Asset(asset_id=f"a_{i}", caption="x") for i in range(1000)]
    sampler = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=1000, seed=42)
    sampled = asyncio.run(sampler.sample(lot))
    assert isinstance(sampled, SampledLot)
    # ISO 2859-1 normal inspection, lot 501-1200 (letter J), AQL 1.0
    # → sample size 80, Ac 2, Re 3
    assert len(sampled.sampled_assets) == 80
    # all sampled items must be the same Asset instances from the input lot
    for a in sampled.sampled_assets:
        assert isinstance(a, Asset)
    assert sampled.accept_count == 2
    assert sampled.reject_count == 3
    assert sampled.lot_size == 1000
    assert sampled.aql_level == AQLLevel.AQL_1_0


# --------------------------------------------------------------------------- #
#  R2 reproducer — Test 2: ISO 2859-1 sample size across all 7 levels
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "level,expected_sample,expected_ac,expected_re",
    [
        # (lot_size 1000 → bucket 1200, letter J)
        (AQLLevel.AQL_0_1,  50,  0,  1),
        (AQLLevel.AQL_0_65, 80,  1,  2),
        (AQLLevel.AQL_1_0,  80,  2,  3),
        (AQLLevel.AQL_1_5,  80,  3,  4),
        (AQLLevel.AQL_2_5,  80,  5,  6),
        (AQLLevel.AQL_4_0,  80,  10, 11),
        (AQLLevel.AQL_6_5, 125, 14, 15),
    ],
)
def test_aql_sample_size_iso_2859_1_all_levels(
    level, expected_sample, expected_ac, expected_re
):
    """Cross-check ISO 2859-1 Table II-A values for lot_size=1000 (letter J)
    across all 7 AQL levels — the entire 70-entry lookup table must be
    reachable.
    """
    sampler = AQLSampling(level=level, lot_size=1000, seed=0)
    assert sampler.sample_size == expected_sample
    assert sampler.accept_count == expected_ac
    assert sampler.reject_count == expected_re

    plan = _lookup_plan(1000, level)
    assert plan == (expected_sample, expected_ac, expected_re)

    # End-to-end sample() also succeeds.
    lot = [Asset(asset_id=f"a_{i}", caption="x") for i in range(1000)]
    sampled = asyncio.run(sampler.sample(lot))
    assert len(sampled.sampled_assets) == expected_sample
    assert sampled.aql_level == level


# --------------------------------------------------------------------------- #
#  R2 reproducer — Test 3: Direct SampledLot construction with Asset list
# --------------------------------------------------------------------------- #
def test_sampledlot_direct_construction_with_asset_instances():
    """R2 reproducer #3: ``SampledLot(sampled_assets=[Asset(...)], ...)``
    must construct without raising.
    """
    sl = SampledLot(
        sampled_assets=[Asset(asset_id="a1", caption="x")],
        sample_size=1,
        accept_count=0,
        reject_count=1,
    )
    assert isinstance(sl, SampledLot)
    assert len(sl.sampled_assets) == 1
    assert sl.sampled_assets[0].asset_id == "a1"
    assert sl.sample_size == 1


# --------------------------------------------------------------------------- #
#  R2 reproducer — Test 4: lot size < sample size (under-sampling branch)
# --------------------------------------------------------------------------- #
def test_aql_sampling_undersampled_small_lot():
    """When actual lot size < planned sample size, the sampler uses the entire
    lot and marks ``under_sampled=True`` in metadata.

    To trigger this branch we need ``len(lot) < sampler.sample_size``.
    Sampler for ``lot_size=5`` clamps to bucket 50 (letter D), and
    ``(50, AQL_6_5) -> sample_size=20``. So 3 assets < 20 → entire lot used.
    """
    lot = [Asset(asset_id=f"a_{i}", caption="x") for i in range(3)]
    sampler = AQLSampling(level=AQLLevel.AQL_6_5, lot_size=5, seed=1)
    # bucket 50, AQL_6_5 → sample_size 20
    assert sampler.sample_size == 20
    sampled = asyncio.run(sampler.sample(lot))
    assert len(sampled.sampled_assets) == 3  # entire lot
    assert sampled.sample_size == 3  # SampledLot.sample_size reflects what was drawn
    assert sampled.metadata["under_sampled"] is True
    assert sampled.metadata["actual_lot_size"] == 3


def test_aql_sampling_full_sample_when_lot_exceeds_plan():
    """When actual lot size >= planned sample size, the sampler draws exactly
    ``sample_size`` items and ``under_sampled=False``.
    """
    lot = [Asset(asset_id=f"a_{i}", caption="x") for i in range(100)]
    # AQL_0_1 for bucket 50 (letter D) → sample_size 8
    sampler = AQLSampling(level=AQLLevel.AQL_0_1, lot_size=10, seed=1)
    assert sampler.sample_size == 8
    sampled = asyncio.run(sampler.sample(lot))
    assert len(sampled.sampled_assets) == 8
    assert sampled.metadata["under_sampled"] is False
    assert sampled.metadata["actual_lot_size"] == 100


# --------------------------------------------------------------------------- #
#  R2 reproducer — Test 5: empty + boundary lot sizes
# --------------------------------------------------------------------------- #
def test_aql_sampling_rejects_empty_lot():
    with pytest.raises(ValueError, match="lot is empty"):
        sampler = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=1000, seed=42)
        asyncio.run(sampler.sample([]))


def test_aql_sampling_rejects_zero_lot_size():
    with pytest.raises(ValueError, match="lot_size must be > 0"):
        AQLSampling(level=AQLLevel.AQL_1_0, lot_size=0, seed=42)


# --------------------------------------------------------------------------- #
#  R2 reproducer — Test 6: clamping outside the ISO bucket range
# --------------------------------------------------------------------------- #
def test_aql_sampling_clamps_outside_iso_range():
    # lot_size 5 → clamped to bucket 50 (letter D)
    sampler_small = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=5, seed=1)
    assert sampler_small.was_clamped is True
    assert sampler_small.bucket == 50
    assert sampler_small.sample_size == 13  # (50, AQL_1_0) → 13, 0, 1

    # lot_size 100_000 → clamped to bucket 50000
    sampler_big = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=100_000, seed=1)
    assert sampler_big.was_clamped is True
    assert sampler_big.bucket == 50000
    assert sampler_big.sample_size == 315  # (50000, AQL_1_0) → 315, 5, 6


# --------------------------------------------------------------------------- #
#  R2 reproducer — Test 7: inspect() with DefectRecord list
# --------------------------------------------------------------------------- #
def test_inspection_result_with_defect_records():
    """InspectionResult.defect_records: List[DefectRecord] — same Pydantic
    nesting pattern as SampledLot.sampled_assets. Verify the same fix applies.
    """
    defects = [
        DefectRecord(asset_id="a_0", defect_type="caption_missing", severity="minor"),
        DefectRecord(asset_id="a_1", defect_type="uri_broken", severity="major"),
    ]
    result = InspectionResult(
        lot_id="lot-test",
        aql_level=AQLLevel.AQL_1_0,
        sample_size=80,
        accept_count_threshold=2,
        reject_count_threshold=3,
        defects_found=2,
        defect_records=defects,
        decision=InspectionDecision.ACCEPT,
        rationale="defects 2 <= Ac 2 - lot accepted",
    )
    assert result.defect_rate == pytest.approx(2 / 80)
    assert len(result.defect_records) == 2
    assert result.defect_records[0].asset_id == "a_0"


# --------------------------------------------------------------------------- #
#  R2 reproducer — Test 8: nested Pydantic models in LabelResult / StrategyVote
# --------------------------------------------------------------------------- #
def test_label_result_with_strategy_votes():
    """LabelResult.strategy_votes: List[StrategyVote] (Pydantic) +
    LabelResult.top_k: List[LabelConfidence] (Pydantic) — same pattern, same
    fix should apply.
    """
    vote = StrategyVote(
        strategy="clip",
        asset_id="a_0",
        top_k=[LabelConfidence(category="animal", score=0.9)],
        confidence=0.9,
        uncertainty=0.1,
    )
    lr = LabelResult(
        asset_id="a_0",
        final_label=__import__(
            "imdf.labeling.auto_strategy_schemas", fromlist=["LabelCategory"]
        ).LabelCategory.ANIMAL,
        confidence=0.9,
        uncertainty=0.1,
        strategy_votes=[vote],
    )
    assert len(lr.strategy_votes) == 1
    assert lr.strategy_votes[0].strategy == "clip"
    assert lr.strategy_votes[0].top_k[0].score == 0.9


# --------------------------------------------------------------------------- #
#  R2 reproducer — Test 9: model_config audit
# --------------------------------------------------------------------------- #
def test_all_aql_related_models_have_arbitrary_types_allowed():
    """The R2 fix adds ``arbitrary_types_allowed=True`` to all schemas that
    carry ``List[BaseModel]`` fields. Lock the config in so a future refactor
    cannot silently drop the flag and re-introduce the bug.
    """
    expected = {
        SampledLot,
        InspectionResult,
        DefectRecord,
        StrategyVote,
        LabelResult,
    }
    for cls in expected:
        cfg = cls.model_config
        assert cfg.get("arbitrary_types_allowed") is True, (
            f"{cls.__name__} is missing arbitrary_types_allowed=True "
            f"(re-introduces R2-NEW-#1 risk)"
        )
        assert cfg.get("extra") == "allow", (
            f"{cls.__name__} lost extra='allow'"
        )
