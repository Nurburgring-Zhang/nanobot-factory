"""Tests for guizang_social_card skill (P4-8-W1)."""
import pytest

from skills.builtin.guizang_social_card import GuizangSocialCardSkill, _parse_cards


@pytest.mark.asyncio
async def test_social_card_empty_text_fails(make_ctx):
    skill = GuizangSocialCardSkill()
    ctx = make_ctx(inputs={"text": ""})
    result = await skill.execute(ctx)
    assert result.success is False
    assert "text" in result.error.lower()


@pytest.mark.asyncio
async def test_social_card_default_count(make_ctx):
    skill = GuizangSocialCardSkill()
    ctx = make_ctx(inputs={"text": "这是一段关于 AI 的长文内容。" * 5})
    result = await skill.execute(ctx)
    assert result.success is True
    assert len(result.data["cards"]) == skill.DEFAULT_COUNT


@pytest.mark.asyncio
async def test_social_card_custom_platform_and_count(make_ctx):
    skill = GuizangSocialCardSkill()
    ctx = make_ctx(inputs={
        "text": "Web3 内容测试 " * 5,
        "platform": "小红书",
        "count": 3,
    })
    result = await skill.execute(ctx)
    assert result.success is True
    assert result.data["platform"] == "小红书"
    assert len(result.data["cards"]) == 3


def test_parse_cards_synthesizes_n_cards():
    cards = _parse_cards(raw="ignored", count=4, topic="AI")
    assert len(cards) == 4
    for i, c in enumerate(cards):
        assert c["page"] == i + 1
        assert "hook" in c
        assert len(c["body"]) == 2
        assert "cta" in c
    # Last card has special CTA
    assert "收藏" in cards[-1]["cta"] or "转发" in cards[-1]["cta"]