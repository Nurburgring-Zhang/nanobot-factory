"""V5 FR-8.3 - AQL Sampling tests (>=10 tests).

Covers:
  * 7 AQL levels x 3 lot sizes = correct sample size from Table II-A
  * accept/reject boundaries (defects == Ac -> accept, defects > Ac -> reject)
  * lot size 26-50 / 91-150 / 151-280 each tested
  * bucket resolution + clamping edge cases
  * under-sampling when lot < sample_size
"""
from __future__ import annotations

import asyncio

import pytest

from imdf.labeling.auto_strategy_schemas import (
    AQLLevel,
    Asset,
    AssetType,
    InspectionDecision,
)
from imdf.quality.aql_sampling import (
    AQLSampling,
    _resolve_bucket,
    _lookup_plan,
    _LOT_BUCKETS,
)


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #
def _make_lot(n: int) -> list:
    return [
        Asset(asset_id=f"a-{i:04d}", asset_type=AssetType.IMAGE, caption=f"img {i}")
        for i in range(n)
    ]


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
#  Test 1 - bucket resolution
# --------------------------------------------------------------------------- #
def test_bucket_resolution_in_range():
    """In-range lot sizes map to the correct bucket key."""
    assert _resolve_bucket(26)[0] == 50
    assert _resolve_bucket(50)[0] == 50
    assert _resolve_bucket(51)[0] == 90
    assert _resolve_bucket(90)[0] == 90
    assert _resolve_bucket(91)[0] == 150
    assert _resolve_bucket(150)[0] == 150
    assert _resolve_bucket(151)[0] == 280
    assert _resolve_bucket(280)[0] == 280
    assert _resolve_bucket(281)[0] == 500
    assert _resolve_bucket(500)[0] == 500
    assert _resolve_bucket(1200)[0] == 1200
    assert _resolve_bucket(35000)[0] == 35000
    assert _resolve_bucket(50000)[0] == 50000


# --------------------------------------------------------------------------- #
#  Test 2 - bucket clamping (under 26, over 50000)
# --------------------------------------------------------------------------- #
def test_bucket_clamps_out_of_range():
    """Lot sizes outside [26, 50000] clamp to nearest bucket."""
    bucket, clamped = _resolve_bucket(0)
    assert bucket == 50
    assert clamped is True

    bucket, clamped = _resolve_bucket(10)
    assert bucket == 50
    assert clamped is True

    bucket, clamped = _resolve_bucket(99999)
    assert bucket == 50000
    assert clamped is True


# --------------------------------------------------------------------------- #
#  Test 3 - lot 26-50 across all 7 AQL levels
# --------------------------------------------------------------------------- #
def test_lot_50_all_seven_aql_levels():
    """Lot size 50 (bucket D) - verify sample size for all 7 AQL levels.

    Reference values (from SAMPLE_TABLE):
      0.1 -> 8 (Ac=0)
      0.65 -> 8 (Ac=0)
      1.0 -> 13 (Ac=0)
      1.5 -> 13 (Ac=0)
      2.5 -> 13 (Ac=1)
      4.0 -> 20 (Ac=1)
      6.5 -> 20 (Ac=3)
    """
    cases = [
        (AQLLevel.AQL_0_1,  8,  0),
        (AQLLevel.AQL_0_65, 8,  0),
        (AQLLevel.AQL_1_0,  13, 0),
        (AQLLevel.AQL_1_5,  13, 0),
        (AQLLevel.AQL_2_5,  13, 1),
        (AQLLevel.AQL_4_0,  20, 1),
        (AQLLevel.AQL_6_5,  20, 3),
    ]
    for aql, expected_n, expected_ac in cases:
        s = AQLSampling(level=aql, lot_size=50)
        assert s.sample_size == expected_n, f"lot=50 aql={aql}: expected n={expected_n}, got {s.sample_size}"
        assert s.accept_count == expected_ac, f"lot=50 aql={aql}: expected Ac={expected_ac}, got {s.accept_count}"


# --------------------------------------------------------------------------- #
#  Test 4 - lot 91-150 (bucket F) across all 7 AQL levels
# --------------------------------------------------------------------------- #
def test_lot_150_all_seven_aql_levels():
    """Lot size 150 (bucket F) - verify sample size for all 7 AQL levels."""
    cases = [
        (AQLLevel.AQL_0_1,  13, 0),
        (AQLLevel.AQL_0_65, 20, 0),
        (AQLLevel.AQL_1_0,  32, 1),
        (AQLLevel.AQL_1_5,  32, 1),
        (AQLLevel.AQL_2_5,  32, 2),
        (AQLLevel.AQL_4_0,  32, 3),
        (AQLLevel.AQL_6_5,  50, 5),
    ]
    for aql, expected_n, expected_ac in cases:
        s = AQLSampling(level=aql, lot_size=150)
        assert s.sample_size == expected_n
        assert s.accept_count == expected_ac


# --------------------------------------------------------------------------- #
#  Test 5 - lot 151-280 (bucket G) across all 7 AQL levels
# --------------------------------------------------------------------------- #
def test_lot_280_all_seven_aql_levels():
    """Lot size 280 (bucket G) - verify sample size for all 7 AQL levels."""
    cases = [
        (AQLLevel.AQL_0_1,  20, 0),
        (AQLLevel.AQL_0_65, 32, 1),
        (AQLLevel.AQL_1_0,  50, 1),
        (AQLLevel.AQL_1_5,  50, 2),
        (AQLLevel.AQL_2_5,  50, 3),
        (AQLLevel.AQL_4_0,  50, 5),
        (AQLLevel.AQL_6_5,  50, 7),
    ]
    for aql, expected_n, expected_ac in cases:
        s = AQLSampling(level=aql, lot_size=280)
        assert s.sample_size == expected_n
        assert s.accept_count == expected_ac


# --------------------------------------------------------------------------- #
#  Test 6 - sample() draws the right number of assets
# --------------------------------------------------------------------------- #
def test_sample_draws_correct_count():
    """sample() should produce SampledLot with sample_size assets."""
    s = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=1000, seed=42)
    lot = _make_lot(1000)
    sampled = _run(s.sample(lot))
    assert sampled.sample_size == 80  # lot=1000 bucket=J aql=1.0 -> 80
    assert len(sampled.sampled_assets) == 80
    assert sampled.aql_level == AQLLevel.AQL_1_0


# --------------------------------------------------------------------------- #
#  Test 7 - sample() under-samples when lot < sample_size
# --------------------------------------------------------------------------- #
def test_sample_under_sampled_when_lot_smaller():
    """When lot_size < planned sample_size, use entire lot and document."""
    # lot=50, AQL=6.5 -> sample_size=20, but lot only has 5 assets
    s = AQLSampling(level=AQLLevel.AQL_6_5, lot_size=50, seed=1)
    lot = _make_lot(5)
    sampled = _run(s.sample(lot))
    assert sampled.sample_size == 5
    assert sampled.metadata["under_sampled"] is True


# --------------------------------------------------------------------------- #
#  Test 8 - sample() rejects empty lot
# --------------------------------------------------------------------------- #
def test_sample_rejects_empty_lot():
    s = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=100)
    with pytest.raises(ValueError, match="lot is empty"):
        _run(s.sample([]))


# --------------------------------------------------------------------------- #
#  Test 9 - inspect() boundary: defects == Ac -> ACCEPT
# --------------------------------------------------------------------------- #
def test_inspect_boundary_at_accept_count():
    """defects == accept_count -> ACCEPT (ISO 2859-1 rule)."""
    # lot=150, AQL=1.0 -> sample=32, Ac=1
    s = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=150)
    lot = _make_lot(150)
    sampled = _run(s.sample(lot))
    result = _run(s.inspect(sampled, defect_count=1))
    assert result.decision == InspectionDecision.ACCEPT
    assert result.defects_found == 1
    assert result.accept_count_threshold == 1


# --------------------------------------------------------------------------- #
#  Test 10 - inspect() boundary: defects > Ac -> REJECT
# --------------------------------------------------------------------------- #
def test_inspect_boundary_above_accept_count():
    """defects > accept_count -> REJECT."""
    s = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=150)
    lot = _make_lot(150)
    sampled = _run(s.sample(lot))
    result = _run(s.inspect(sampled, defect_count=2))
    assert result.decision == InspectionDecision.REJECT
    assert result.defects_found == 2


# --------------------------------------------------------------------------- #
#  Test 11 - inspect() with zero defects -> ACCEPT
# --------------------------------------------------------------------------- #
def test_inspect_zero_defects_accepted():
    s = AQLSampling(level=AQLLevel.AQL_6_5, lot_size=280)
    lot = _make_lot(280)
    sampled = _run(s.sample(lot))
    result = _run(s.inspect(sampled, defect_count=0))
    assert result.decision == InspectionDecision.ACCEPT


# --------------------------------------------------------------------------- #
#  Test 12 - inspect() rejects negative defect_count
# --------------------------------------------------------------------------- #
def test_inspect_rejects_negative_defects():
    s = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=100)
    lot = _make_lot(100)
    sampled = _run(s.sample(lot))
    with pytest.raises(ValueError, match="defect_count"):
        _run(s.inspect(sampled, defect_count=-1))


# --------------------------------------------------------------------------- #
#  Test 13 - plan_summary() returns complete dict
# --------------------------------------------------------------------------- #
def test_plan_summary_contains_all_keys():
    s = AQLSampling(level=AQLLevel.AQL_2_5, lot_size=500, seed=0)
    summary = s.plan_summary()
    assert summary["aql_level"] == "2.5"
    assert summary["lot_size"] == 500
    assert summary["sample_size"] == 80
    assert summary["accept_count"] == 5
    assert summary["reject_count"] == 6
    assert summary["bucket"] == 500
    assert summary["clamped"] is False


# --------------------------------------------------------------------------- #
#  Test 14 - bucket count >= 5 minimum requirement
# --------------------------------------------------------------------------- #
def test_at_least_5_lot_buckets_defined():
    """Spec: at minimum 5 lot size buckets (26-50, 51-90, 91-150, 151-280, 281-500)."""
    assert len(_LOT_BUCKETS) >= 5
    ranges = [(lo, hi) for lo, hi, _ in _LOT_BUCKETS[:5]]
    assert ranges[0] == (26, 50)
    assert ranges[1] == (51, 90)
    assert ranges[2] == (91, 150)
    assert ranges[3] == (151, 280)
    assert ranges[4] == (281, 500)


# --------------------------------------------------------------------------- #
#  Test 15 - end-to-end: batch of 1000 images, AQL 1.0, sample 80, 2 defects -> ACCEPT
# --------------------------------------------------------------------------- #
def test_e2e_batch_1000_aql_1_0_two_defects_accepted():
    """Spec example: lot=1000, AQL=1.0 -> sample=80 (bucket J), Ac=2; 2 defects -> ACCEPT."""
    s = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=1000, seed=42)
    assert s.sample_size == 80
    assert s.accept_count == 2

    lot = _make_lot(1000)
    sampled = _run(s.sample(lot))
    result = _run(s.inspect(sampled, defect_count=2))
    assert result.decision == InspectionDecision.ACCEPT
    assert "accepted" in result.rationale.lower()


# --------------------------------------------------------------------------- #
#  Test 16 - end-to-end: lot=1000, AQL=1.0, 3 defects -> REJECT
# --------------------------------------------------------------------------- #
def test_e2e_batch_1000_aql_1_0_three_defects_rejected():
    """3 defects > Ac=2 -> REJECT."""
    s = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=1000, seed=42)
    lot = _make_lot(1000)
    sampled = _run(s.sample(lot))
    result = _run(s.inspect(sampled, defect_count=3))
    assert result.decision == InspectionDecision.REJECT


# --------------------------------------------------------------------------- #
#  Test 17 - defect rate computed correctly
# --------------------------------------------------------------------------- #
def test_defect_rate_computed():
    s = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=500, seed=0)
    lot = _make_lot(500)
    sampled = _run(s.sample(lot))
    result = _run(s.inspect(sampled, defect_count=8))
    assert result.defect_rate == pytest.approx(8 / 80)


# --------------------------------------------------------------------------- #
#  Test 18 - string level coerced to enum
# --------------------------------------------------------------------------- #
def test_string_level_coerced():
    """Passing level as string should be coerced to AQLLevel enum."""
    s = AQLSampling(level="1.0", lot_size=100)
    assert s.level == AQLLevel.AQL_1_0


# --------------------------------------------------------------------------- #
#  Test 19 - lot_size <= 0 raises
# --------------------------------------------------------------------------- #
def test_invalid_lot_size_raises():
    with pytest.raises(ValueError):
        AQLSampling(level=AQLLevel.AQL_1_0, lot_size=0)
    with pytest.raises(ValueError):
        AQLSampling(level=AQLLevel.AQL_1_0, lot_size=-5)


# --------------------------------------------------------------------------- #
#  Test 20 - sample() returns deterministic results with seed
# --------------------------------------------------------------------------- #
def test_sample_deterministic_with_seed():
    """Same seed -> same sampled assets."""
    lot = _make_lot(100)
    s1 = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=100, seed=123)
    s2 = AQLSampling(level=AQLLevel.AQL_1_0, lot_size=100, seed=123)
    sampled1 = _run(s1.sample(lot))
    sampled2 = _run(s2.sample(lot))
    ids1 = [a.asset_id for a in sampled1.sampled_assets]
    ids2 = [a.asset_id for a in sampled2.sampled_assets]
    assert ids1 == ids2


# --------------------------------------------------------------------------- #
#  Test 21 - lookup_plan covers all 10 buckets x 7 AQL levels
# --------------------------------------------------------------------------- #
def test_lookup_plan_all_buckets_and_levels():
    """Every (bucket, level) combo must be in SAMPLE_TABLE."""
    for _, _, key in _LOT_BUCKETS:
        for lvl in AQLLevel:
            plan = _lookup_plan(key, lvl)
            assert len(plan) == 3
            assert plan[0] > 0  # sample size
            assert plan[1] >= 0  # accept
            assert plan[2] >= plan[1]  # reject >= accept