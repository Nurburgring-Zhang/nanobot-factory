"""Tests for label_clip_multi."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_clip_multi
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_default_threshold():
    out = _run(label_clip_multi(SkillInput(params={
        "image": "https://example.com/x.jpg",
        "candidates": ["sky", "sun", "cloud", "ground"],
    })))
    assert out.success is True
    res = out.result
    assert set(res["scores"].keys()) == {"sky", "sun", "cloud", "ground"}
    assert res["threshold"] == 0.5
    assert all(0.0 <= v <= 1.0 for v in res["scores"].values())
    # selected must be subset of candidates above threshold
    for s in res["selected"]:
        assert s in res["scores"]
        assert res["scores"][s] >= 0.5


def test_edge_case_low_threshold_selects_more():
    """Low threshold should select strictly >= selected at higher threshold."""
    base = {"image": "img-X", "candidates": ["a", "b", "c", "d"]}
    high = _run(label_clip_multi(SkillInput(params={**base, "threshold": 0.95})))
    low = _run(label_clip_multi(SkillInput(params={**base, "threshold": 0.05})))
    assert len(low.result["selected"]) >= len(high.result["selected"])


def test_error_handling_missing_candidates():
    out = _run(label_clip_multi(SkillInput(params={"image": "x.png"})))
    assert out.success is False
    assert "invalid input" in out.error.lower()


def test_error_handling_single_candidate():
    out = _run(label_clip_multi(SkillInput(params={
        "image": "x.png",
        "candidates": ["only"],
    })))
    assert out.success is False


def test_threshold_boundaries():
    out = _run(label_clip_multi(SkillInput(params={
        "image": "x.png",
        "candidates": ["x", "y"],
        "threshold": 0.0,
    })))
    assert out.success is True
    assert out.result["threshold"] == 0.0
    # With threshold=0, every label qualifies
    assert len(out.result["selected"]) == 2