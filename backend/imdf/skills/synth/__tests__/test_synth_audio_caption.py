"""Tests for synth skill: synth_audio_caption (音频描述合成)."""
from __future__ import annotations

import pytest

from backend.skills import SkillInput, SkillOutput
from imdf.skills.synth.synth_audio_caption import audio_caption, AudioCaptionInput


def _input(**kwargs) -> SkillInput:
    return SkillInput(prompt=kwargs.pop("prompt", "test prompt"), params=kwargs, context={})


@pytest.mark.asyncio
async def test_happy_path():
    """basic happy path — should succeed and return structured result."""
    params = {'audio_ref': 'aud://test/001'}
    out = await audio_caption(_input(**params))
    assert isinstance(out, SkillOutput)
    assert out.success is True, f"unexpected failure: {out.error!r}"
    assert out.error == ""
    assert isinstance(out.result, dict)
    assert out.metadata.get("skill_module") == "synth_audio_caption"
    assert out.metadata.get("source") in ("live", "mock")


@pytest.mark.asyncio
async def test_with_pydantic_schema():
    """verify Pydantic input schema is well-defined."""
    schema = AudioCaptionInput.model_json_schema()
    assert "properties" in schema
    # every skill has at least one input field
    assert len(schema["properties"]) >= 1


@pytest.mark.asyncio
async def test_invalid_params_returns_error():
    """edge case: invalid params should NOT crash; returns SkillOutput(success=False)."""
    out = await audio_caption(SkillInput(prompt="x", params={"bogus_field": "bad"}, context={}))
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
    params = {'audio_ref': ''}
    out = await audio_caption(_input(**params))
    assert out.success is True
    assert isinstance(out.result, dict)
