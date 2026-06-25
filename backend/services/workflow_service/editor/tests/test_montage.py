"""Tests for montage engine — 5 montages + 4 time modes + BPM sync."""
import pytest

from services.workflow_service.editor.montage import (
    MontageEngine, MontagePlan,
    MONTAGE_TYPES, MONTAGE_TIME_MODES, LAYOUTS,
    list_montage_types, list_time_modes, bpm_to_cut_points,
)


# ---- catalog ----

def test_montage_types_count():
    assert len(MONTAGE_TYPES) == 5


def test_time_modes_count():
    assert len(MONTAGE_TIME_MODES) == 4


def test_layouts_count():
    assert len(LAYOUTS) == 3


def test_list_montage_types_meta():
    items = list_montage_types()
    assert len(items) == 5
    assert all("id" in m and "name" in m and "desc" in m for m in items)


def test_list_time_modes_meta():
    items = list_time_modes()
    assert len(items) == 4


# ---- BPM sync ----

def test_bpm_to_cut_points_basic():
    pts = bpm_to_cut_points(bpm=120, clip_count=5)
    # 60/120 = 0.5s per beat → 0, 0.5, 1.0, 1.5, 2.0
    assert pts == [0.0, 0.5, 1.0, 1.5, 2.0]


def test_bpm_to_cut_points_with_offset():
    pts = bpm_to_cut_points(bpm=60, clip_count=3, offset=10.0)
    # 60/60 = 1.0s per beat → 10, 11, 12
    assert pts == [10.0, 11.0, 12.0]


def test_bpm_invalid_raises():
    with pytest.raises(ValueError, match="bpm must be > 0"):
        bpm_to_cut_points(bpm=0, clip_count=3)
    with pytest.raises(ValueError, match="clip_count must be > 0"):
        bpm_to_cut_points(bpm=120, clip_count=0)


# ---- build_plan ----

def test_build_plan_sequential():
    engine = MontageEngine()
    plan = engine.build_plan(clips=["a", "b", "c"], type="sequential")
    assert plan.type == "sequential"
    assert len(plan.cut_points) == 3
    assert plan.clips == ["a", "b", "c"]


def test_build_plan_parallel_requires_two_clips():
    engine = MontageEngine()
    with pytest.raises(ValueError, match="requires >= 2 clips"):
        engine.build_plan(clips=["a"], type="parallel")


def test_build_plan_unknown_type():
    engine = MontageEngine()
    with pytest.raises(ValueError, match="unknown type"):
        engine.build_plan(clips=["a", "b"], type="unicorn")


def test_build_plan_with_bpm():
    engine = MontageEngine()
    plan = engine.build_plan(
        clips=["a", "b", "c", "d"],
        type="parallel", bpm=120,
    )
    assert plan.bpm == 120
    # BPM grid: 4 cut points spaced 0.5s apart
    assert plan.cut_points == [0.0, 0.5, 1.0, 1.5]


def test_build_plan_bpm_out_of_range():
    engine = MontageEngine()
    with pytest.raises(ValueError, match="bpm out of reasonable range"):
        engine.build_plan(clips=["a", "b"], type="sequential", bpm=300)


def test_build_plan_unknown_time_mode():
    engine = MontageEngine()
    # build_plan calls validate_plan internally — the ValueError surfaces here
    with pytest.raises(ValueError, match="unknown time mode"):
        engine.build_plan(
            clips=["a", "b"], type="sequential", time_mode="invalid_mode",
        )


# ---- apply ----

def test_apply_flashback_reverses_clips():
    engine = MontageEngine()
    timeline = {
        "clips": [
            {"id": "a", "start": 0.0, "duration": 1.0, "end": 1.0},
            {"id": "b", "start": 1.0, "duration": 1.0, "end": 2.0},
            {"id": "c", "start": 2.0, "duration": 1.0, "end": 3.0},
        ],
    }
    engine.apply(timeline, clips=["a", "b", "c"],
                 type="sequential", time_mode="flashback")
    ids = [c["id"] for c in timeline["clips"]]
    assert ids == ["c", "b", "a"]


def test_apply_flashforward_marks_clips():
    engine = MontageEngine()
    timeline = {
        "clips": [{"id": "a"}, {"id": "b"}],
    }
    engine.apply(timeline, clips=["a", "b"],
                 type="sequential", time_mode="flashforward")
    assert timeline["clips"][0].get("flashforward") is True
    assert "flashforward_previews" in timeline


def test_apply_parallel_timeline_marks_track():
    engine = MontageEngine()
    timeline = {
        "clips": [{"id": "a"}, {"id": "b"}],
    }
    engine.apply(timeline, clips=["a", "b"],
                 type="parallel", time_mode="parallel_timeline")
    for c in timeline["clips"]:
        assert "parallel_track" in c


def test_apply_appends_montages():
    engine = MontageEngine()
    timeline = {"clips": [], "cuts": []}
    result = engine.apply(timeline, clips=["a", "b"], type="sequential")
    assert result["type"] == "sequential"
    assert "montages" in timeline
    assert len(timeline["montages"]) == 1