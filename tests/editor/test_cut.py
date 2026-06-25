"""P4-6-W1 tests for cut engine.

4 tests covering: 6 cut operations + cut-point detection + silence + keyframes.
"""
from __future__ import annotations

import pytest

from services.workflow_service.editor.cut import (
    CUT_OPERATIONS, CutEngine, detect_cut_points,
    detect_silence_segments, extract_keyframes, list_cut_operations,
)


def test_cut_operations_catalog():
    """All 6 cut operations registered."""
    assert len(CUT_OPERATIONS) == 6
    assert set(CUT_OPERATIONS) == {
        "cut", "trim", "split", "merge", "reorder", "loop",
    }
    items = list_cut_operations()
    assert len(items) == 6
    assert {x["id"] for x in items} == set(CUT_OPERATIONS)


def test_cut_engine_six_operations(sample_timeline):
    """All 6 operations execute and produce non-empty results."""
    eng = CutEngine()
    # 1) split
    op1 = eng.split(sample_timeline, offset=1.5, clip_id="c2")
    assert op1.op == "split"
    assert len(op1.result_clips) == 2
    # 2) trim (still on c1, untouched by split)
    op2 = eng.trim(sample_timeline, clip_id="c1",
                   in_offset=0.5, out_offset=0.5)
    assert op2.op == "trim"
    assert op2.result_clips[0]["duration"] == pytest.approx(2.0)
    # 3) reorder (c2 was split into c2_a + c2_b — use those)
    op3 = eng.reorder(sample_timeline,
                      order=["c3", "c1", "c2_a", "c2_b"])
    assert op3.op == "reorder"
    assert [c["id"] for c in sample_timeline["clips"][:4]] == [
        "c3", "c1", "c2_a", "c2_b"]
    # 4) merge consecutive clips (c3 + c1)
    op4 = eng.merge(sample_timeline, clip_ids=["c3", "c1"])
    assert op4.op == "merge"
    merged_id = op4.result_clips[0]["id"]
    assert merged_id.startswith("merged-")
    # 5) loop
    op5 = eng.loop(sample_timeline, clip_id=merged_id, count=2)
    assert op5.op == "loop"
    assert len(op5.result_clips) == 2
    # 6) cut (at 0.5)
    op6 = eng.cut(sample_timeline, at=0.5)
    assert op6.op == "cut"
    assert len(op6.result_clips) == 2


def test_detect_cut_points_and_silence_and_keyframes():
    """Detector helpers return sane structures."""
    # Scene change detector
    cuts = detect_cut_points([0.1, 0.2, 0.55, 0.6, 0.9], threshold=0.4)
    assert len(cuts) == 3
    assert all("score" in c and c["score"] >= 0.4 for c in cuts)
    # Silence detector: one long silence segment, no second short one
    amps = [0.05, 0.02, 0.0, 0.0, 0.0, 0.0, 0.3, 0.5, 0.4, 0.6]
    sil = detect_silence_segments(amps, min_silence_sec=3.0,
                                  threshold=0.1)
    assert len(sil) == 1
    assert sil[0]["duration"] >= 3.0
    assert sil[0]["start"] == 0
    # Keyframe extractor
    kf_uniform = extract_keyframes(
        [0.0, 0.5, 1.0, 1.5, 2.0], method="uniform", interval_sec=1.0)
    assert len(kf_uniform) == 3
    kf_scene = extract_keyframes(
        [0.0, 0.4, 0.9, 1.0, 2.5], method="scene_change")
    assert all(k["type"] == "scene_change" for k in kf_scene)
    kf_iframe = extract_keyframes(
        [0.0, 0.5, 1.0, 1.5, 2.0], method="i_frame")
    assert all(k["type"] == "i_frame" for k in kf_iframe)


def test_cut_engine_validates_invalid_inputs(sample_timeline):
    """Invalid inputs surface as ValueError."""
    eng = CutEngine()
    # split.offset = 0
    try:
        eng.split(sample_timeline, offset=0, clip_id="c1")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for offset=0")
    # merge requires >= 2
    try:
        eng.merge(sample_timeline, clip_ids=["c1"])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for merge < 2")
    # trim too aggressive
    try:
        eng.trim(sample_timeline, clip_id="c1",
                 in_offset=10.0, out_offset=10.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for over-trim")
    # loop with count = 0
    try:
        eng.loop(sample_timeline, clip_id="c1", count=0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for count=0")
    # unknown op in batch
    try:
        eng.batch(sample_timeline, [{"op": "unknown_op"}])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown op")
