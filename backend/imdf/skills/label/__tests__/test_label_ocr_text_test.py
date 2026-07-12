"""Tests for label_ocr_text."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_ocr_text
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_english():
    out = _run(label_ocr_text(SkillInput(params={
        "image": "https://example.com/sign.jpg",
        "lang": "en",
    })))
    assert out.success is True
    res = out.result
    assert isinstance(res["text"], str) and len(res["text"]) > 0
    assert res["lang"] == "en"
    assert 2 <= len(res["regions"]) <= 4
    for r in res["regions"]:
        assert {"text", "bbox", "confidence"} <= set(r.keys())
        assert 0.0 <= r["confidence"] <= 1.0


def test_happy_path_chinese():
    out = _run(label_ocr_text(SkillInput(params={
        "image": "/tmp/x.png",
        "lang": "zh",
    })))
    assert out.success is True
    res = out.result
    assert res["lang"] == "zh"
    assert any("\u4e00" <= ch <= "\u9fff" for ch in res["text"])


def test_edge_case_unknown_lang_uses_english_bank():
    out = _run(label_ocr_text(SkillInput(params={
        "image": "/tmp/x.png",
        "lang": "klingon",
    })))
    assert out.success is True
    # Falls back to English bank
    assert out.result["lang"] == "klingon"  # echoed back
    assert len(out.result["regions"]) >= 2


def test_error_handling_missing_image():
    out = _run(label_ocr_text(SkillInput(params={})))
    assert out.success is False


def test_error_handling_invalid_params():
    """Wrong type for image (list instead of str) must be rejected."""
    out = _run(label_ocr_text(SkillInput(params={
        "image": ["x.png"],  # should be a string
    })))
    assert out.success is False