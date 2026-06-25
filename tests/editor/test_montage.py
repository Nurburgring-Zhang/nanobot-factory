"""P4-6-W1 tests for montage engine.

3 tests covering: 5 montages + 4 time modes + BPM sync.
"""
from __future__ import annotations

import pytest

from services.workflow_service.editor.montage import (
    MONTAGE_TIME_MODES, MONTAGE_TYPES, MontageEngine, MontagePlan,
    bpm_to_cut_points, list_montage_types, list_time_modes,
)


def test_montage_types_and_time_modes():
    assert len(MONTAGE_TYPES) == 5
    assert set(MONTAGE_TYPES) == {
        "parallel", "cross", "sequential", "thematic", "contrast",
    }
    assert len(MONTAGE_TIME_MODES) == 4
    assert set(MONTAGE_TIME_MODES) == {
        "linear", "flashback", "flashforward", "parallel_timeline",
    }
    assert len(list_montage_types()) == 5
    assert len(list_time_modes()) == 4


def test_bpm_sync_basic_and_invalid():
    """BPM sync returns the right number of evenly spaced cut points."""
    cps = bpm_to_cut_points(bpm=120, clip_count=4, offset=0.0)
    assert len(cps) == 4
    # 60/120 = 0.5
    assert cps[0] == 0.0
    assert cps[1] == pytest.approx(0.5)
    assert cps[2] == pytest.approx(1.0)
    assert cps[3] == pytest.approx(1.5)
    # with offset
    cps2 = bpm_to_cut_points(bpm=60, clip_count=3, offset=2.0)
    assert cps2[0] == pytest.approx(2.0)
    assert cps2[1] == pytest.approx(3.0)     # 1 sec/beat
    assert cps2[2] == pytest.approx(4.0)
    # invalid
    with pytest.raises(ValueError):
        bpm_to_cut_points(bpm=0, clip_count=4)
    with pytest.raises(ValueError):
        bpm_to_cut_points(bpm=120, clip_count=0)


def test_montage_plan_all_5_types(sample_timeline):
    """Each of the 5 montage types builds a valid plan + mutates timeline."""
    eng = MontageEngine()
    clips = ["c1", "c2", "c3"]
    for mtype in MONTAGE_TYPES:
        plan = eng.build_plan(
            clips=clips, type=mtype, time_mode="linear",
            layout="split_screen", bpm=120)
        assert plan.type == mtype
        assert len(plan.clips) == 3
        assert plan.cut_points, f"no cut_points for {mtype}"
        # Apply mutates timeline
        plan2 = eng.apply(
            sample_timeline, clips=clips, type=mtype,
            time_mode="linear", layout="split_screen", bpm=120,
            params={"per_clip_sec": 1.0})
        assert plan2["type"] == mtype
    # Validate invalid type
    with pytest.raises(ValueError):
        eng.build_plan(clips=clips, type="bogus")
    # Validate parallel requires >= 2 clips
    with pytest.raises(ValueError):
        eng.build_plan(clips=["c1"], type="parallel")
    # Apply attaches montages[] to the timeline
    assert "montages" in sample_timeline
    assert len(sample_timeline["montages"]) >= 5
