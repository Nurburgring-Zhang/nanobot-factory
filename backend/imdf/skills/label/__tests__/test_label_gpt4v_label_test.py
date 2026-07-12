"""Tests for label_gpt4v_label."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_gpt4v_label
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_default_prompt():
    out = _run(label_gpt4v_label(SkillInput(params={
        "image": "https://example.com/x.jpg",
    })))
    assert out.success is True
    res = out.result
    assert isinstance(res["caption"], str) and len(res["caption"]) > 0
    assert isinstance(res["tags"], list) and len(res["tags"]) >= 3
    assert isinstance(res["structured"], dict)
    assert "timestamp" in res


def test_edge_case_custom_schema_kept_in_metadata():
    """Custom schema isn't validated in mock path, but result.structured still present."""
    schema = {"type": "object", "properties": {"caption": {"type": "string"}}}
    out = _run(label_gpt4v_label(SkillInput(params={
        "image": "/tmp/x.png",
        "prompt": "Caption this.",
        "schema": schema,
        "max_tokens": 64,
    })))
    assert out.success is True
    assert out.result["model"] == "gpt-4-vision-preview"
    assert "caption" in out.result["structured"]


def test_error_handling_missing_image():
    out = _run(label_gpt4v_label(SkillInput(params={"prompt": "hi"})))
    assert out.success is False
    assert "invalid input" in out.error.lower()


def test_error_handling_empty_prompt():
    out = _run(label_gpt4v_label(SkillInput(params={
        "image": "x.png",
        "prompt": "",
    })))
    assert out.success is False


def test_max_tokens_too_large():
    out = _run(label_gpt4v_label(SkillInput(params={
        "image": "x.png",
        "max_tokens": 9999,
    })))
    assert out.success is False