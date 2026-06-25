"""Tests for cut engine — 6 ops + 3 detectors."""
import pytest

from services.workflow_service.editor.cut import (
    CutEngine,
    CUT_OPERATIONS,
    list_cut_operations,
    detect_cut_points,
    detect_silence_segments,
    extract_keyframes,
)


# ---- cut op ----

def test_cut_basic_split_at_offset():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "end": 10.0, "duration": 10.0}]}
    op = engine.cut(timeline, at=4.0)
    assert op.op == "cut"
    assert len(timeline["clips"]) == 2
    assert timeline["clips"][0]["id"] == "c1_a"
    assert timeline["clips"][1]["id"] == "c1_b"


def test_cut_negative_at_raises():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 5.0}]}
    with pytest.raises(ValueError, match="must be >= 0"):
        engine.cut(timeline, at=-1.0)


def test_cut_empty_clips_raises():
    engine = CutEngine()
    with pytest.raises(ValueError, match="no clips"):
        engine.cut({"clips": []}, at=1.0)


def test_cut_unknown_clip_id_raises():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 5.0}]}
    with pytest.raises(ValueError, match="clip_id not found"):
        engine.cut(timeline, at=1.0, clip_id="nope")


# ---- trim op ----

def test_trim_in_out_offsets():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "end": 10.0, "duration": 10.0}]}
    op = engine.trim(timeline, clip_id="c1", in_offset=1.0, out_offset=2.0)
    assert op.op == "trim"
    assert timeline["clips"][0]["start"] == 1.0
    assert timeline["clips"][0]["end"] == 8.0
    assert timeline["clips"][0]["duration"] == 7.0


def test_trim_out_larger_than_duration_raises():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 5.0}]}
    with pytest.raises(ValueError, match="out_offset larger"):
        engine.trim(timeline, clip_id="c1", in_offset=1.0, out_offset=10.0)


# ---- split op ----

def test_split_creates_two_clips():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "end": 10.0, "duration": 10.0}]}
    op = engine.split(timeline, offset=3.0, clip_id="c1")
    assert op.op == "split"
    assert len(timeline["clips"]) == 2
    assert timeline["cuts"][-1]["type"] == "split"


def test_split_invalid_offset_raises():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 5.0}]}
    with pytest.raises(ValueError, match="offset must be in"):
        engine.split(timeline, offset=0.0, clip_id="c1")
    with pytest.raises(ValueError, match="offset must be in"):
        engine.split(timeline, offset=5.0, clip_id="c1")


# ---- merge op ----

def test_merge_combines_consecutive_clips():
    engine = CutEngine()
    timeline = {
        "clips": [
            {"id": "c1", "start": 0.0, "duration": 3.0, "end": 3.0},
            {"id": "c2", "start": 3.0, "duration": 4.0, "end": 7.0},
        ]
    }
    op = engine.merge(timeline, clip_ids=["c1", "c2"])
    assert op.op == "merge"
    assert len(timeline["clips"]) == 1
    assert "merged-" in timeline["clips"][0]["id"]


def test_merge_requires_min_2():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 3.0}]}
    with pytest.raises(ValueError, match=">= 2"):
        engine.merge(timeline, clip_ids=["c1"])


# ---- reorder op ----

def test_reorder_changes_clip_order_and_re_stamps_starts():
    engine = CutEngine()
    timeline = {
        "clips": [
            {"id": "c1", "start": 0.0, "duration": 2.0, "end": 2.0},
            {"id": "c2", "start": 2.0, "duration": 3.0, "end": 5.0},
            {"id": "c3", "start": 5.0, "duration": 1.0, "end": 6.0},
        ]
    }
    op = engine.reorder(timeline, order=["c3", "c1", "c2"])
    assert op.op == "reorder"
    ids = [c["id"] for c in timeline["clips"]]
    assert ids == ["c3", "c1", "c2"]
    # starts re-stamped contiguously
    assert timeline["clips"][0]["start"] == 0.0
    assert timeline["clips"][1]["start"] == 1.0  # dur of c3
    assert timeline["clips"][2]["start"] == 3.0


def test_reorder_unknown_clip_raises():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 1.0}]}
    with pytest.raises(ValueError, match="unknown clip_ids"):
        engine.reorder(timeline, order=["nope"])


# ---- loop op ----

def test_loop_repeats_clip_n_times():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 2.0, "end": 2.0}]}
    op = engine.loop(timeline, clip_id="c1", count=3)
    assert op.op == "loop"
    assert len(timeline["clips"]) == 3
    for i, c in enumerate(timeline["clips"]):
        assert c["loop_index"] == i + 1


def test_loop_invalid_count_raises():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 2.0}]}
    with pytest.raises(ValueError, match=">= 1"):
        engine.loop(timeline, clip_id="c1", count=0)


# ---- batch ----

def test_batch_runs_multiple_ops():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 10.0, "end": 10.0}]}
    report = engine.batch(timeline, [
        {"op": "cut", "at": 3.0},
        {"op": "trim", "clip_id": "c1_a", "in_offset": 0.5, "out_offset": 0.0},
    ])
    assert len(report.operations) == 2


def test_batch_unknown_op_raises():
    engine = CutEngine()
    timeline = {"clips": [{"id": "c1", "start": 0.0, "duration": 5.0}]}
    with pytest.raises(ValueError, match="missing 'op'"):
        engine.batch(timeline, [{}])
    with pytest.raises(ValueError, match="unknown cut op"):
        engine.batch(timeline, [{"op": "teleport"}])


# ---- catalog ----

def test_list_cut_operations_has_six_ops():
    ops = list_cut_operations()
    assert len(ops) == 6
    ids = {o["id"] for o in ops}
    assert ids == set(CUT_OPERATIONS)


# ---- detectors ----

def test_detect_cut_points_thresholds_high_scores():
    frames = [0.1, 0.5, 0.7, 0.2, 0.9, 0.05]
    cuts = detect_cut_points(frames, threshold=0.4)
    assert len(cuts) == 3
    assert all(c["type"] == "scene_change" for c in cuts)


def test_detect_cut_points_invalid_threshold():
    with pytest.raises(ValueError):
        detect_cut_points([0.1, 0.5], threshold=0)
    with pytest.raises(ValueError):
        detect_cut_points([0.1, 0.5], threshold=1.5)


def test_detect_silence_segments_finds_quiet_runs():
    amps = [0.5, 0.5, 0.02, 0.01, 0.03, 0.5, 0.5, 0.01, 0.01, 0.5]
    segs = detect_silence_segments(amps, min_silence_sec=2, threshold=0.05)
    assert len(segs) >= 1
    assert all(s["duration"] >= 2 for s in segs)


def test_extract_keyframes_uniform_method():
    ts = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    kf = extract_keyframes(ts, method="uniform", interval_sec=1.0)
    assert len(kf) >= 2
    assert all(k["type"] == "uniform" for k in kf)


def test_extract_keyframes_i_frame_method():
    ts = list(range(20))
    kf = extract_keyframes(ts, method="i_frame")
    assert len(kf) == 5  # every 4th element
    assert all(k["type"] == "i_frame" for k in kf)


def test_extract_keyframes_unknown_method_raises():
    with pytest.raises(ValueError, match="unknown method"):
        extract_keyframes([0.0, 1.0], method="magic")