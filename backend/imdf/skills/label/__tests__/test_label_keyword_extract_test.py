"""Tests for label_keyword_extract."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_keyword_extract
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_english():
    text = ("Machine learning is a field of computer science that gives computers "
            "the ability to learn without being explicitly programmed. "
            "Machine learning focuses on the development of algorithms.")
    out = _run(label_keyword_extract(SkillInput(params={
        "text": text, "top_k": 5, "lang": "en",
    })))
    assert out.success is True
    res = out.result
    assert res["lang"] == "en"
    assert len(res["keywords"]) <= 5
    # Machine and learning should appear (high frequency)
    words = {kw["keyword"] for kw in res["keywords"]}
    assert "machine" in words or "learning" in words
    # Sum of scores ~= 1 (proportional to frequency)
    total = sum(kw["score"] for kw in res["keywords"])
    assert 0.0 < total <= 1.0


def test_happy_path_chinese():
    out = _run(label_keyword_extract(SkillInput(params={
        "text": "机器学习是计算机科学的一个领域,机器学习可以自动学习数据。深度学习是机器学习的子领域。",
        "lang": "zh",
    })))
    assert out.success is True
    res = out.result
    assert res["lang"] == "zh"
    assert len(res["keywords"]) > 0


def test_edge_case_top_k_caps():
    out = _run(label_keyword_extract(SkillInput(params={
        "text": "alpha beta gamma delta epsilon zeta eta theta",
        "top_k": 3, "lang": "en",
    })))
    assert out.success is True
    assert len(out.result["keywords"]) == 3
    assert len(out.result["keyphrases"]) <= 3


def test_edge_case_min_length_filter():
    out = _run(label_keyword_extract(SkillInput(params={
        "text": "I am a cat that is big and bold.",
        "min_length": 4, "lang": "en",
    })))
    assert out.success is True
    for kw in out.result["keywords"]:
        assert len(kw["keyword"]) >= 4


def test_edge_case_stopwords_filtered():
    out = _run(label_keyword_extract(SkillInput(params={
        "text": "the the the cat cat dog",
        "top_k": 5, "lang": "en",
    })))
    assert out.success is True
    words = {kw["keyword"] for kw in out.result["keywords"]}
    assert "the" not in words  # stopword removed


def test_error_handling_top_k_too_large():
    out = _run(label_keyword_extract(SkillInput(params={
        "text": "hello world", "top_k": 9999,
    })))
    # pydantic ge=1, le=50 â?9999 invalid
    assert out.success is False


def test_error_handling_empty_text():
    out = _run(label_keyword_extract(SkillInput(params={"text": ""})))
    assert out.success is False