"""synth_caption_expand: Offline mock expansion of short captions to long captions.

**OFFLINE MOCK** — returns ``{mock: True, module: 'synth_caption_expand', echo: 'synth:synth_caption_expand:offline'}``.
Real LLM-based caption expansion is NOT implemented. The "live API" branch in this
module POSTs to ``https://api.example.invalid/...`` which always fails DNS, so in
practice every call ends up in the deterministic offline mock that echoes the input
``params`` back. To perform real caption expansion, call an LLM provider directly
via the providers module (e.g. ``backend.imdf.providers``).

Args:
    text: short caption to expand (echoed back as ``params.text``)
    target_words: desired output length (echoed back; not used)
    style: writing style hint (echoed back; not used)

Returns:
    SkillOutput with ``result: {mock: True, echo: 'synth:synth_caption_expand:offline', params: {...}}``
    and ``metadata.source == 'mock'`` (or ``'live'`` if the unreachable endpoint ever responds).
"""
from __future__ import annotations

from typing import Any, Dict, List
from pydantic import BaseModel, Field

from backend.skills import SkillInput, SkillOutput
from ._base import (
    NETWORK_OK,
    _build_output,
    _post_json,
    _sleep_ms,
)


class CaptionExpandInput(BaseModel):
    text: str
    target_words: int = 200
    style: str = 'descriptive'


class CaptionExpandOutput(BaseModel):
    pass


async def caption_expand(input: SkillInput) -> SkillOutput:
    """短描述扩写为长描述 (caption_expand).

    Args:
        input.prompt:  free-form user text
        input.params:  parsed as ``CaptionExpandInput``; if invalid falls back to mock

    Returns:
        SkillOutput with structured ``result`` dict + metadata.
    """
    t0 = _now_ms()
    try:
        params = CaptionExpandInput.model_validate(input.params or {})
    except Exception as exc:
        return _build_output(
            success=False,
            result=None,
            error=f"invalid params: {exc}",
            metadata={"skill_module": "synth_caption_expand", "validation_error": True},
        )

    # Try live API first (best-effort); fall back to deterministic mock.
    live = None
    if NETWORK_OK:
        live = await _post_json(
            "https://api.example.invalid/synth/synth_caption_expand",
            params.model_dump(),
            timeout=2.0,
        )

    if live is not None and isinstance(live, dict):
        return _build_output(
            success=True,
            result=live,
            metadata={
                "skill_module": "synth_caption_expand",
                "source": "live",
                "elapsed_ms": _now_ms() - t0,
            },
        )

    # Offline mock — deterministic per-input
    mock_result = _mock(params)
    return _build_output(
        success=True,
        result=mock_result,
        metadata={
            "skill_module": "synth_caption_expand",
            "source": "mock",
            "elapsed_ms": _now_ms() - t0,
        },
    )


def _mock(params: CaptionExpandInput) -> Dict[str, Any]:
    """Deterministic offline mock — replaces real LLM call when network unavailable."""
    base = params.model_dump()
    return {
        "mock": True,
        "module": "synth_caption_expand",
        "params": base,
        "echo": "synth:synth_caption_expand:offline",
    }


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


__all__ = ["caption_expand", "CaptionExpandInput", "CaptionExpandOutput"]
