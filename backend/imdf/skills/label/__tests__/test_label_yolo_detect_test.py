"""Tests for label_yolo_detect."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_yolo_detect
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_default_classes():
    out = _run(label_yolo_detect(SkillInput(params={
        "image": "https://example.com/street.jpg",
    })))
    assert out.success is True
    res = out.result
    assert "boxes" in res and isinstance(res["boxes"], list)
    assert 2 <= res["count"] <= 5
    for b in res["boxes"]:
        assert {"label", "score", "bbox"} <= set(b.keys())
        assert 0.0 <= b["score"] <= 1.0
        assert len(b["bbox"]) == 4
        assert b["label"] in res["classes"]


def test_edge_case_custom_classes_filter():
    out = _run(label_yolo_detect(SkillInput(params={
        "image": "/tmp/x.png",
        "classes": ["person", "bicycle"],
        "conf_threshold": 0.0,
    })))
    assert out.success is True
    for b in out.result["boxes"]:
        assert b["label"] in {"person", "bicycle"}


def test_edge_case_high_threshold_filters_out():
    out_low = _run(label_yolo_detect(SkillInput(params={
        "image": "/tmp/y.png", "conf_threshold": 0.0,
    })))
    out_high = _run(label_yolo_detect(SkillInput(params={
        "image": "/tmp/y.png", "conf_threshold": 0.99,
    })))
    assert out_low.success and out_high.success
    assert out_high.result["count"] <= out_low.result["count"]


def test_error_handling_missing_image():
    out = _run(label_yolo_detect(SkillInput(params={})))
    assert out.success is False


def test_error_handling_invalid_conf_threshold():
    out = _run(label_yolo_detect(SkillInput(params={
        "image": "x.png",
        "conf_threshold": 1.5,
    })))
    assert out.success is False


def test_deterministic_output():
    p = {"image": "img-A", "conf_threshold": 0.0}
    a = _run(label_yolo_detect(SkillInput(params=p)))
    b = _run(label_yolo_detect(SkillInput(params=p)))
    assert a.result["boxes"] == b.result["boxes"]