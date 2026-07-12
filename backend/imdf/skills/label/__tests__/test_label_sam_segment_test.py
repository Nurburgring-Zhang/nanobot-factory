"""Tests for label_sam_segment."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_sam_segment
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_auto_mode():
    out = _run(label_sam_segment(SkillInput(params={
        "image": "https://example.com/scene.jpg",
    })))
    assert out.success is True
    res = out.result
    assert res["mode"] == "auto"
    assert 1 <= res["count"] <= 4
    for m in res["masks"]:
        assert m["mask_id"].startswith("mask-")
        assert m["area"] > 0
        assert len(m["bbox"]) == 4
        assert 0.0 <= m["score"] <= 1.0
        assert m["format"] == "rle"


def test_edge_case_box_mode():
    out = _run(label_sam_segment(SkillInput(params={
        "image": "/tmp/x.png",
        "mode": "box",
        "boxes": [[10, 10, 100, 100], [200, 50, 300, 200]],
    })))
    assert out.success is True
    assert out.result["mode"] == "box"
    assert out.result["count"] >= 1


def test_edge_case_point_mode():
    out = _run(label_sam_segment(SkillInput(params={
        "image": "/tmp/x.png",
        "mode": "point",
        "points": [[50, 50]],
    })))
    assert out.success is True
    assert out.result["mode"] == "point"


def test_error_handling_box_mode_without_boxes():
    out = _run(label_sam_segment(SkillInput(params={
        "image": "x.png", "mode": "box",
    })))
    assert out.success is False
    assert "box" in out.error.lower()


def test_error_handling_point_mode_without_points():
    out = _run(label_sam_segment(SkillInput(params={
        "image": "x.png", "mode": "point",
    })))
    assert out.success is False


def test_error_handling_invalid_mode():
    out = _run(label_sam_segment(SkillInput(params={
        "image": "x.png", "mode": "magic",
    })))
    assert out.success is False