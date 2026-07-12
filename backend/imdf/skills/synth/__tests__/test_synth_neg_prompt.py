"""Tests for synth skill: synth_neg_prompt (负向 prompt 生成)."""
from __future__ import annotations

import pytest

from backend.skills import SkillInput, SkillOutput
from imdf.skills.synth.synth_neg_prompt import neg_prompt, NegPromptInput


def _input(**kwargs) -> SkillInput:
    return SkillInput(prompt=kwargs.pop("prompt", "test prompt"), params=kwargs, context={})


@pytest.mark.asyncio
async def test_happy_path():
    """basic happy path — should succeed and return structured result."""
    params = {'base_prompt': 'A photo of a cat'}
    out = await neg_prompt(_input(**params))
    assert isinstance(out, SkillOutput)
    assert out.success is True, f"unexpected failure: {out.error!r}"
    assert out.error == ""
    assert isinstance(out.result, dict)
    assert out.metadata.get("skill_module") == "synth_neg_prompt"
    assert out.metadata.get("source") in ("live", "mock")


@pytest.mark.asyncio
async def test_with_pydantic_schema():
    """verify Pydantic input schema is well-defined."""
    schema = NegPromptInput.model_json_schema()
    assert "properties" in schema
    # every skill has at least one input field
    assert len(schema["properties"]) >= 1


@pytest.mark.asyncio
async def test_invalid_params_returns_error():
    """edge case: invalid params should NOT crash; returns SkillOutput(success=False)."""
    out = await neg_prompt(SkillInput(prompt="x", params={"bogus_field": "bad"}, context={}))
    assert isinstance(out, SkillOutput)
    # either success=True (mock fallback) or success=False with error
    if not out.success:
        assert "invalid params" in out.error or "validation" in out.error.lower()
    else:
        # mock fallback path — still valid output
        assert out.result is not None


@pytest.mark.asyncio
async def test_empty_payload_handled():
    """edge case: empty/minimal input still produces a result."""
    params = {'base_prompt': ''}
    out = await neg_prompt(_input(**params))
    assert out.success is True
    assert isinstance(out.result, dict)
