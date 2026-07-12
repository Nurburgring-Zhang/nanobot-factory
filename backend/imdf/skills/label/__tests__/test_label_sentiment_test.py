"""Tests for label_sentiment."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_sentiment
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_positive_english():
    out = _run(label_sentiment(SkillInput(params={
        "text": "I love this product. It is amazing and wonderful!",
        "granularity": "sentence",
        "lang": "en",
    })))
    assert out.success is True
    res = out.result
    assert res["label"] in {"positive", "neutral", "negative"}
    assert res["lang"] == "en"
    assert len(res["sentences"]) >= 2
    assert all(s["score"] >= 0 for s in res["sentences"])  # positive


def test_happy_path_negative_english():
    out = _run(label_sentiment(SkillInput(params={
        "text": "This is terrible. Awful. I hate it.",
        "lang": "en",
    })))
    assert out.success is True
    assert out.result["label"] == "negative"


def test_happy_path_positive_chinese():
    out = _run(label_sentiment(SkillInput(params={
        "text": "这个东西很好,我很喜欢,完美!",
    })))
    assert out.success is True
    assert out.result["label"] == "positive"
    assert out.result["lang"] == "zh"


def test_edge_case_document_granularity():
    out = _run(label_sentiment(SkillInput(params={
        "text": "Great product!",
        "granularity": "document",
    })))
    assert out.success is True
    assert len(out.result["sentences"]) == 1


def test_edge_case_neutral_text():
    out = _run(label_sentiment(SkillInput(params={
        "text": "Today is Wednesday.",
        "lang": "en",
    })))
    assert out.success is True
    assert out.result["label"] == "neutral"


def test_error_handling_invalid_granularity():
    out = _run(label_sentiment(SkillInput(params={
        "text": "hi",
        "granularity": "phoneme",
    })))
    assert out.success is False


def test_error_handling_empty_text():
    out = _run(label_sentiment(SkillInput(params={"text": ""})))
    assert out.success is False