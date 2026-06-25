"""Tests for marketingskills skill (P4-8-W1)."""
import pytest

from skills.builtin.marketingskills import MarketingSkills, _TOOLS, _synth


@pytest.mark.asyncio
async def test_marketingskills_unsupported_tool_fails(make_ctx):
    skill = MarketingSkills()
    ctx = make_ctx(inputs={"tool": "nonexistent_tool", "product": "X"})
    result = await skill.execute(ctx)
    assert result.success is False
    assert "unsupported" in result.error.lower() or "tool" in result.error.lower()


@pytest.mark.asyncio
async def test_marketingskills_default_tool(make_ctx):
    skill = MarketingSkills()
    ctx = make_ctx(inputs={"product": "AI 助手"})
    result = await skill.execute(ctx)
    # Default = landing_page
    assert result.success is True
    assert result.data["tool"] == "landing_page"


@pytest.mark.asyncio
async def test_marketingskills_each_supported_tool(make_ctx):
    for tool_name in _TOOLS.keys():
        skill = MarketingSkills()
        ctx = make_ctx(inputs={"tool": tool_name, "product": "Test Product"})
        result = await skill.execute(ctx)
        assert result.success is True, f"tool={tool_name} failed"
        assert result.data["tool"] == tool_name
        assert result.data["output"]  # non-empty


def test_synth_returns_correct_fields_for_landing_page():
    out = _synth(tool="landing_page", product="X", audience="dev")
    assert "headline" in out
    assert "subhead" in out
    assert "bullets" in out
    assert "cta" in out


def test_synth_returns_correct_fields_for_seo():
    out = _synth(tool="seo_brief", product="Y", audience="dev")
    assert "title" in out
    assert "outline" in out
    assert "keywords" in out


def test_synth_unknown_tool_returns_empty():
    assert _synth(tool="unknown", product="X", audience="dev") == {}