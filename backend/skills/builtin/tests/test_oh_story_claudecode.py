"""Tests for oh_story_claudecode skill (P4-8-W1)."""
import pytest

from skills.builtin.oh_story_claudecode import OhStoryClaudeCodeSkill, _CORPUS


@pytest.mark.asyncio
async def test_story_default_genre(make_ctx):
    skill = OhStoryClaudeCodeSkill()
    ctx = make_ctx(inputs={})  # empty → defaults to "都市"
    result = await skill.execute(ctx)
    assert result.success is True
    assert result.data["genre"] == "都市"


@pytest.mark.asyncio
async def test_story_custom_genre(make_ctx):
    skill = OhStoryClaudeCodeSkill()
    ctx = make_ctx(inputs={"genre": "玄幻", "count": 3})
    result = await skill.execute(ctx)
    assert result.success is True
    assert result.data["genre"] == "玄幻"
    assert len(result.data["ideas"]) == 3


@pytest.mark.asyncio
async def test_story_unknown_genre_falls_back_to_dushi(make_ctx):
    skill = OhStoryClaudeCodeSkill()
    ctx = make_ctx(inputs={"genre": "不存在流派"})
    result = await skill.execute(ctx)
    assert result.success is True
    # Falls back to default genre internally but echo user input
    assert result.data["genre"] == "不存在流派"


@pytest.mark.asyncio
async def test_story_ideas_have_required_fields(make_ctx):
    skill = OhStoryClaudeCodeSkill()
    ctx = make_ctx(inputs={"genre": "科幻", "count": 3})
    result = await skill.execute(ctx)
    assert result.success is True
    for idea in result.data["ideas"]:
        assert "title" in idea
        assert "logline" in idea
        assert "target_audience" in idea
        assert "hook" in idea
        assert "risk" in idea
        assert "heat_score" in idea
        assert 0 <= float(idea["heat_score"]) <= 1


@pytest.mark.asyncio
async def test_story_ideas_sorted_by_heat_desc(make_ctx):
    skill = OhStoryClaudeCodeSkill()
    ctx = make_ctx(inputs={"genre": "言情", "count": 4})
    result = await skill.execute(ctx)
    ideas = result.data["ideas"]
    scores = [float(i["heat_score"]) for i in ideas]
    assert scores == sorted(scores, reverse=True)


def test_corpus_has_expected_genres():
    assert "都市" in _CORPUS
    assert "玄幻" in _CORPUS
    assert "科幻" in _CORPUS
    assert "言情" in _CORPUS
    for genre, items in _CORPUS.items():
        for item in items:
            assert 0 <= item["heat"] <= 1, f"{genre}/{item} heat out of range"