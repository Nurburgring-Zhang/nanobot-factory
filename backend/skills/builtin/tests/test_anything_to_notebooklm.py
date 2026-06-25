"""Tests for anything_to_notebooklm skill (P4-8-W1)."""
import pytest

from skills.builtin.anything_to_notebooklm import (
    AnythingToNotebookLMSkill,
    _extract_keywords,
    _build_faq,
)


@pytest.mark.asyncio
async def test_notebooklm_empty_source_fails(make_ctx):
    skill = AnythingToNotebookLMSkill()
    ctx = make_ctx(inputs={"source": ""})
    result = await skill.execute(ctx)
    assert result.success is False
    assert "source" in result.error.lower()


@pytest.mark.asyncio
async def test_notebooklm_briefing_structure(make_ctx):
    skill = AnythingToNotebookLMSkill()
    ctx = make_ctx(inputs={
        "source": "人工智能正在改变世界。机器学习模型变得越来越强大。"
                  "深度学习在图像识别和自然语言处理方面取得了突破。"
                  "我们每天都在使用AI技术。"
    })
    result = await skill.execute(ctx)
    assert result.success is True
    b = result.data["briefing"]
    assert "tldr" in b
    assert "topics" in b
    assert "faq" in b
    assert "quotes" in b
    assert len(b["topics"]) <= 5
    assert len(b["faq"]) == skill.DEFAULT_FAQ
    assert len(b["quotes"]) == skill.DEFAULT_QUOTES


def test_extract_keywords_filters_short_words():
    text = "AI AI AI 深度 深度 学习 学习 学习 短 x a bb"
    out = _extract_keywords(text, top_k=3)
    assert "AI" in out or "学习" in out or "深度" in out
    # 'x', 'a' should be filtered (too short)
    assert all(2 <= len(w) <= 12 for w in out)


def test_extract_keywords_empty_returns_empty():
    assert _extract_keywords("", top_k=5) == []


def test_build_faq_returns_n_items():
    faq = _build_faq(
        source="A. B. C.",
        sentences=["Sentence A", "Sentence B", "Sentence C"],
        n=3,
    )
    assert len(faq) == 3
    for f in faq:
        assert "q" in f and "a" in f


def test_build_faq_empty_returns_empty():
    assert _build_faq(source="", sentences=[], n=3) == []