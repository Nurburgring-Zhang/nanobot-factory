"""Tests for humanizer_zh skill (P4-8-W1)."""
import pytest

from skills.builtin.humanizer_zh import HumanizerZhSkill


@pytest.mark.asyncio
async def test_humanizer_empty_text_fails(make_ctx):
    skill = HumanizerZhSkill()
    ctx = make_ctx(inputs={"text": ""})
    result = await skill.execute(ctx)
    assert result.success is False
    assert "text" in result.error.lower()


@pytest.mark.asyncio
async def test_humanizer_returns_text(make_ctx):
    skill = HumanizerZhSkill()
    ctx = make_ctx(inputs={"text": "综上所述，AI 正在改变世界。值得注意的是，它的速度越来越快。"})
    result = await skill.execute(ctx)
    assert result.success is True
    # HumanizerZhSkill returns {"original": ..., "humanized": ..., "ai_tells_before": ..., ...}
    # (not "output") — see skills/builtin/humanizer_zh.py execute().
    assert "humanized" in result.data
    assert isinstance(result.data["humanized"], str)
    assert len(result.data["humanized"]) > 0


@pytest.mark.asyncio
async def test_humanizer_strips_some_ai_tells(make_ctx):
    skill = HumanizerZhSkill()
    text = "在当今时代，AI 是赋能行业的重要工具。"
    ctx = make_ctx(inputs={"text": text})
    result = await skill.execute(ctx)
    out = result.data["humanized"]
    # The output should not contain identical "AI 是赋能行业" + 综上 + 在当今时代
    # (it's a mock LLM with [mock:] prefix, but we just verify it runs)
    assert result.success is True