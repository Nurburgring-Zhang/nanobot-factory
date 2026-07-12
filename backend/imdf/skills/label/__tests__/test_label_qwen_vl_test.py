"""Tests for label_qwen_vl."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_qwen_vl
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_chinese_default():
    out = _run(label_qwen_vl(SkillInput(params={
        "image": "https://example.com/x.jpg",
    })))
    assert out.success is True
    res = out.result
    assert res["lang"] == "zh"
    assert any("\u4e00" <= ch <= "\u9fff" for ch in res["caption"])
    assert isinstance(res["tags"], list)
    assert all(isinstance(t, str) for t in res["tags"])


def test_happy_path_english():
    out = _run(label_qwen_vl(SkillInput(params={
        "image": "/tmp/x.png",
        "lang": "en",
        "prompt": "Describe this scene.",
    })))
    assert out.success is True
    assert out.result["lang"] == "en"
    assert isinstance(out.result["caption"], str)
    assert len(out.result["tags"]) == 3


def test_edge_case_invalid_lang_falls_back_to_zh():
    out = _run(label_qwen_vl(SkillInput(params={
        "image": "/tmp/x.png",
        "lang": "klingon",
    })))
    assert out.success is True
    assert out.result["lang"] == "zh"


def test_error_handling_empty_prompt():
    out = _run(label_qwen_vl(SkillInput(params={
        "image": "x.png",
        "prompt": "",
    })))
    assert out.success is False


def test_error_handling_missing_image():
    out = _run(label_qwen_vl(SkillInput(params={})))
    assert out.success is False