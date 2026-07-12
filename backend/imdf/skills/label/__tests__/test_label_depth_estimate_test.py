"""Tests for label_depth_estimate."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_depth_estimate
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_default():
    out = _run(label_depth_estimate(SkillInput(params={
        "image": "https://example.com/x.jpg",
    })))
    assert out.success is True
    res = out.result
    assert len(res["depth_map"]) == 64
    assert all(0.0 <= v <= 1.0 for v in res["depth_map"])  # normalized
    s = res["stats"]
    for k in ("mean", "median", "min", "max", "std"):
        assert k in s
    assert s["min"] <= s["mean"] <= s["max"]


def test_edge_case_unnormalized():
    out = _run(label_depth_estimate(SkillInput(params={
        "image": "/tmp/x.png",
        "max_depth": 5.0,
        "normalize": False,
        "sample_size": 32,
    })))
    assert out.success is True
    res = out.result
    assert res["normalized"] is False
    assert all(0.05 <= v <= 5.0 for v in res["depth_map"])
    assert res["stats"]["max"] <= 5.0


def test_edge_case_larger_sample_size():
    out = _run(label_depth_estimate(SkillInput(params={
        "image": "/tmp/x.png",
        "sample_size": 256,
    })))
    assert out.success is True
    assert len(out.result["depth_map"]) == 256


def test_error_handling_invalid_max_depth():
    out = _run(label_depth_estimate(SkillInput(params={
        "image": "x.png",
        "max_depth": -1.0,
    })))
    assert out.success is False


def test_error_handling_missing_image():
    out = _run(label_depth_estimate(SkillInput(params={})))
    assert out.success is False