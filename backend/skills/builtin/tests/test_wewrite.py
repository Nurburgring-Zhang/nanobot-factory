"""Tests for wewrite skill (P4-8-W1)."""
import pytest

from skills.builtin.wewrite import WeWriteSkill


@pytest.mark.asyncio
async def test_wewrite_empty_topic_fails(make_ctx):
    skill = WeWriteSkill()
    ctx = make_ctx(inputs={"topic": ""})
    result = await skill.execute(ctx)
    assert result.success is False
    assert "topic" in result.error.lower()


@pytest.mark.asyncio
async def test_wewrite_article_structure(make_ctx):
    skill = WeWriteSkill()
    ctx = make_ctx(inputs={"topic": "AI 内容生产", "length": 1000})
    result = await skill.execute(ctx)
    assert result.success is True
    data = result.data
    assert len(data["titles"]) == 3
    assert 3 <= len(data["outline"]) <= 5
    assert len(data["body"]) > 0
    assert "CTA" in data["cta"] or "关注" in data["cta"]
    assert data["length"] == 1000


@pytest.mark.asyncio
async def test_wewrite_custom_tone(make_ctx):
    skill = WeWriteSkill()
    ctx = make_ctx(inputs={"topic": "Web3", "tone": "幽默"})
    result = await skill.execute(ctx)
    assert result.success is True
    assert result.data["tone"] == "幽默"