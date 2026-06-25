"""Tests for awesome_gpt_image skill (P4-8-W1)."""
import pytest

from skills.builtin.awesome_gpt_image import AwesomeGPTImageSkill, _CATALOGUE


@pytest.mark.asyncio
async def test_gpt_image_default_category_concept(make_ctx):
    skill = AwesomeGPTImageSkill()
    ctx = make_ctx(inputs={})  # empty → defaults to "concept"
    result = await skill.execute(ctx)
    assert result.success is True
    assert result.data["category"] == "concept"


@pytest.mark.asyncio
async def test_gpt_image_unknown_category_falls_back(make_ctx):
    skill = AwesomeGPTImageSkill()
    ctx = make_ctx(inputs={"category": "unicorn_land"})
    result = await skill.execute(ctx)
    assert result.success is True
    # Falls back to "concept" internally
    assert result.data["category"] == "unicorn_land"
    # But generated prompts come from catalogue concept
    assert all("prompt" in p for p in result.data["prompts"])


@pytest.mark.asyncio
async def test_gpt_image_custom_n(make_ctx):
    skill = AwesomeGPTImageSkill()
    ctx = make_ctx(inputs={"category": "portrait", "n": 6})
    result = await skill.execute(ctx)
    assert result.success is True
    assert len(result.data["prompts"]) == 6


@pytest.mark.asyncio
async def test_gpt_image_with_keywords(make_ctx):
    skill = AwesomeGPTImageSkill()
    ctx = make_ctx(inputs={"category": "landscape", "keywords": "sunset, beach"})
    result = await skill.execute(ctx)
    assert result.success is True
    # At least one prompt should contain the keyword
    prompts_text = " ".join(p["prompt"] for p in result.data["prompts"])
    assert "sunset" in prompts_text or "beach" in prompts_text


def test_catalogue_has_expected_categories():
    assert "portrait" in _CATALOGUE
    assert "landscape" in _CATALOGUE
    assert "product" in _CATALOGUE
    assert "concept" in _CATALOGUE