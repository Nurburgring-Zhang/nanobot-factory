"""Tests for deep_research skill (P4-8-W1)."""
import pytest

from skills.builtin.deep_research import DeepResearchSkill


@pytest.mark.asyncio
async def test_deep_research_empty_topic_fails(make_ctx):
    """Empty topic must fail with a clear error."""
    skill = DeepResearchSkill()
    ctx = make_ctx(inputs={"topic": ""})
    result = await skill.execute(ctx)
    assert result.success is False
    assert "topic" in result.error.lower()


@pytest.mark.asyncio
async def test_deep_research_default_findings(make_ctx):
    """Default 5 findings when no findings count given."""
    skill = DeepResearchSkill()
    ctx = make_ctx(inputs={"topic": "AI 趋势"})
    result = await skill.execute(ctx)
    assert result.success is True
    data = result.data
    assert data["topic"] == "AI 趋势"
    assert len(data["findings"]) == skill.DEFAULT_FINDINGS == 5


@pytest.mark.asyncio
async def test_deep_research_custom_findings_count(make_ctx):
    """Custom findings count respected."""
    skill = DeepResearchSkill()
    ctx = make_ctx(inputs={"topic": "Web3", "findings": 3})
    result = await skill.execute(ctx)
    assert result.success is True
    assert len(result.data["findings"]) == 3


@pytest.mark.asyncio
async def test_deep_research_with_search_fn(make_ctx):
    """When search_fn is wired, findings come from search results."""
    skill = DeepResearchSkill()

    def fake_search(topic):
        return [
            {"title": f"src-{i}", "url": f"https://x/{i}", "snippet": f"snippet {i} about {topic}"}
            for i in range(8)
        ]

    skill.set_search_fn(fake_search)
    ctx = make_ctx(inputs={"topic": "blockchain", "findings": 3})
    result = await skill.execute(ctx)
    assert result.success is True
    assert result.data["source_count"] >= 3
    # Findings must reference search sources
    sources = {f["source"] for f in result.data["findings"]}
    assert "src-0" in sources


@pytest.mark.asyncio
async def test_deep_research_search_error_does_not_fail(make_ctx):
    """search_fn raising exception shouldn't fail the skill."""
    skill = DeepResearchSkill()

    def bad_search(_topic):
        raise RuntimeError("network down")

    skill.set_search_fn(bad_search)
    ctx = make_ctx(inputs={"topic": "X", "findings": 2})
    result = await skill.execute(ctx)
    # Should still succeed using outline-only fallback
    assert result.success is True
    assert ctx.pull("search_error") == "network down"