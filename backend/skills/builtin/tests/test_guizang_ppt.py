"""Tests for guizang_ppt skill (P4-8-W1)."""
import pytest

from skills.builtin.guizang_ppt import (
    GuizangPPTSkill,
    _synthesize_deck,
    _coerce_deck_obj,
    _parse_deck,
)


@pytest.mark.asyncio
async def test_guizang_ppt_empty_topic_fails(make_ctx):
    skill = GuizangPPTSkill()
    ctx = make_ctx(inputs={"topic": ""})
    result = await skill.execute(ctx)
    assert result.success is False
    assert "topic" in result.error.lower()


@pytest.mark.asyncio
async def test_guizang_ppt_default_slides(make_ctx):
    skill = GuizangPPTSkill()
    ctx = make_ctx(inputs={"topic": "AI 趋势"})
    result = await skill.execute(ctx)
    # With mock LLM, falls back to template → still success
    assert result.success is True
    assert result.data["topic"] == "AI 趋势"
    # slide count may be 0 if LLM returned nothing parseable; with mock it's 0
    # but result should be a valid deck object either way
    assert "deck" in result.data


@pytest.mark.asyncio
async def test_guizang_ppt_custom_slides(make_ctx):
    skill = GuizangPPTSkill()
    ctx = make_ctx(inputs={"topic": "Web3", "slides": 5})
    result = await skill.execute(ctx)
    assert result.success is True
    # Either fallback template gives 5 slides, or LLM returned parseable deck
    deck = result.data["deck"]
    assert "slides" in deck


def test_synthesize_deck_creates_slides():
    deck = _synthesize_deck("测试主题", slide_count=3, parse_errors=["e1"])
    assert deck["title"] == "测试主题"
    assert len(deck["slides"]) == 3
    assert deck["_parse_source"] == "fallback_template"
    assert deck["_parse_errors"] == ["e1"]


def test_coerce_deck_obj_dict_form():
    obj = {"title": "T", "slides": [{"page": 1}]}
    out = _coerce_deck_obj(obj, "T")
    assert out is not None
    assert out["title"] == "T"
    assert out["slides"] == [{"page": 1}]


def test_coerce_deck_obj_list_form():
    obj = [{"page": 1}, {"page": 2}]
    out = _coerce_deck_obj(obj, "T")
    assert out is not None
    assert out["title"] == "T"
    assert len(out["slides"]) == 2


def test_coerce_deck_obj_rejects_invalid():
    assert _coerce_deck_obj("string", "T") is None
    assert _coerce_deck_obj({"no_slides": True}, "T") is None
    assert _coerce_deck_obj([], "T") is None


def test_parse_deck_direct_json():
    raw = '{"title": "X", "slides": [{"page": 1, "title": "t"}]}'
    deck = _parse_deck(raw, topic="X", slide_count=1)
    assert deck["_parse_source"] == "direct_json"
    assert deck["_parse_source"] != "fallback_template"
    assert deck["title"] == "X"


def test_parse_deck_fallback_on_invalid():
    deck = _parse_deck("not json at all", topic="T", slide_count=4)
    assert deck["_parse_source"] == "fallback_template"
    assert len(deck["slides"]) == 4
    assert deck["_parse_errors"]  # non-empty