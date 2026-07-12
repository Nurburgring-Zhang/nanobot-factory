"""Tests for label_blip_caption."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_blip_caption
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_factual():
    out = _run(label_blip_caption(SkillInput(params={
        "image": "https://example.com/scene.jpg",
        "style": "factual",
        "max_length": 80,
    })))
    assert out.success is True
    res = out.result
    assert isinstance(res["caption"], str) and len(res["caption"]) > 0
    assert res["caption"].startswith("An image showing")
    assert res["style"] == "factual"
    assert len(res["caption"]) <= 80


def test_edge_case_style_normalization():
    """Unknown style â?falls back to 'factual'."""
    out = _run(label_blip_caption(SkillInput(params={
        "image": "/tmp/x.png",
        "style": "TECHNICAL",
        "max_length": 100,
    })))
    assert out.success is True
    assert out.result["style"] == "factual"


def test_edge_case_max_length_truncates():
    out = _run(label_blip_caption(SkillInput(params={
        "image": "/tmp/y.png",
        "max_length": 30,
    })))
    assert out.success is True
    # 29 chars + ellipsis
    assert len(out.result["caption"]) <= 30


def test_error_handling_invalid_max_length():
    out = _run(label_blip_caption(SkillInput(params={
        "image": "/tmp/y.png",
        "max_length": 0,  # below min 8
    })))
    assert out.success is False
    assert "invalid input" in out.error.lower()


def test_error_handling_missing_image():
    out = _run(label_blip_caption(SkillInput(params={"max_length": 64})))
    assert out.success is False