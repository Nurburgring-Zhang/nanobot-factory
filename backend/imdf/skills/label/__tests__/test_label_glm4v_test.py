"""Tests for label_glm4v."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_glm4v
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_caption_task():
    out = _run(label_glm4v(SkillInput(params={
        "image": "https://example.com/x.jpg",
        "task": "caption",
    })))
    assert out.success is True
    res = out.result
    assert res["task"] == "caption"
    assert isinstance(res["result"], str) and len(res["result"]) > 0
    assert res["lang"] == "zh"


def test_happy_path_classify_task():
    out = _run(label_glm4v(SkillInput(params={
        "image": "/tmp/x.png",
        "task": "classify",
        "options": ["cat", "dog", "car"],
        "lang": "en",
    })))
    assert out.success is True
    assert out.result["task"] == "classify"
    assert out.result["result"] in {"cat", "dog", "car"}
    assert out.result["lang"] == "en"


def test_happy_path_extract_task():
    out = _run(label_glm4v(SkillInput(params={
        "image": "/tmp/x.png",
        "task": "extract",
        "prompt": "Find any text in the image.",
    })))
    assert out.success is True
    assert out.result["task"] == "extract"
    assert isinstance(out.result["result"], dict)
    assert "text" in out.result["result"]


def test_error_handling_classify_without_options():
    out = _run(label_glm4v(SkillInput(params={
        "image": "x.png",
        "task": "classify",
    })))
    assert out.success is False


def test_error_handling_invalid_task():
    out = _run(label_glm4v(SkillInput(params={
        "image": "x.png",
        "task": "telekinesis",
    })))
    assert out.success is False


def test_error_handling_empty_prompt():
    out = _run(label_glm4v(SkillInput(params={
        "image": "x.png",
        "prompt": "",
    })))
    assert out.success is False