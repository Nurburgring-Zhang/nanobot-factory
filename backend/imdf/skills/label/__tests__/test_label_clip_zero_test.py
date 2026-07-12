"""Tests for label_clip_zero."""
from __future__ import annotations

import os

import pytest

# Force offline mode before any imports
os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_clip_zero
from backend.skills import SkillInput


def _run(coro):
    """Drive an async coroutine in a sync test."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


def test_happy_path_basic():
    out = _run(label_clip_zero(SkillInput(params={
        "image": "https://example.com/cat.jpg",
        "candidates": ["cat", "dog", "car"],
    })))
    assert out.success is True
    assert out.metadata["source"] == "mock"
    res = out.result
    assert res["label"] in {"cat", "dog", "car"}
    assert 0.0 <= res["score"] <= 1.0
    assert set(res["scores"].keys()) == {"cat", "dog", "car"}
    assert len(res["top_k"]) <= 3
    assert "timestamp" in res


def test_edge_case_top_k_and_strip_blanks():
    out = _run(label_clip_zero(SkillInput(params={
        "image": "/tmp/img.png",
        "candidates": ["  alpha  ", "", "beta", "alpha", "gamma"],
        "top_k": 2,
    })))
    assert out.success is True
    # blanks + dupes removed �?3 unique labels
    assert len(out.result["scores"]) == 3
    assert len(out.result["top_k"]) == 2


def test_error_handling_too_few_candidates():
    out = _run(label_clip_zero(SkillInput(params={
        "image": "/tmp/x.png",
        "candidates": ["only-one"],
    })))
    assert out.success is False
    assert "invalid input" in out.error.lower()


def test_error_handling_missing_image():
    out = _run(label_clip_zero(SkillInput(params={
        "candidates": ["a", "b"],
    })))
    assert out.success is False
    assert "invalid input" in out.error.lower()


def test_deterministic_output():
    """Same input twice produces identical output (deterministic mock)."""
    p = {"image": "img-A", "candidates": ["x", "y", "z", "w"]}
    a = _run(label_clip_zero(SkillInput(params=p)))
    b = _run(label_clip_zero(SkillInput(params=p)))
    assert a.result["label"] == b.result["label"]
    assert a.result["scores"] == b.result["scores"]