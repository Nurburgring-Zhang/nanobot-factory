"""synth_neg_prompt: Offline mock negative-prompt (anti-prompt) generator.

**OFFLINE MOCK** — returns ``{mock: True, module: 'synth_neg_prompt', echo: 'synth:synth_neg_prompt:offline'}``.
Real negative-prompt generation is NOT implemented. The "live API" branch in this
module POSTs to ``https://api.example.invalid/...`` which always fails DNS, so in
practice every call ends up in the deterministic offline mock that echoes the input
``params`` back. To generate a real negative prompt, call an LLM provider directly
via the providers module.

Args:
    base_prompt: the positive prompt to negate (echoed back; not interpreted)
    strength: 'low' / 'medium' / 'high' (echoed back; not used)

Returns:
    SkillOutput with ``result: {mock: True, echo: 'synth:synth_neg_prompt:offline', params: {...}}``
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


class NegPromptInput(BaseModel):
    base_prompt: str
    strength: str = 'medium'


class NegPromptOutput(BaseModel):
    pass


async def neg_prompt(input: SkillInput) -> SkillOutput:
    """负向 prompt 生成 (neg_prompt).

    Args:
        input.prompt:  free-form user text
        input.params:  parsed as ``NegPromptInput``; if invalid falls back to mock

    Returns:
        SkillOutput with structured ``result`` dict + metadata.
    """
    t0 = _now_ms()
    try:
        params = NegPromptInput.model_validate(input.params or {})
    except Exception as exc:
        return _build_output(
            success=False,
            result=None,
            error=f"invalid params: {exc}",
            metadata={"skill_module": "synth_neg_prompt", "validation_error": True},
        )

    # Try live API first (best-effort); fall back to deterministic mock.
    live = None
    if NETWORK_OK:
        live = await _post_json(
            "https://api.example.invalid/synth/synth_neg_prompt",
            params.model_dump(),
            timeout=2.0,
        )

    if live is not None and isinstance(live, dict):
        return _build_output(
            success=True,
            result=live,
            metadata={
                "skill_module": "synth_neg_prompt",
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
            "skill_module": "synth_neg_prompt",
            "source": "mock",
            "elapsed_ms": _now_ms() - t0,
        },
    )


def _mock(params: NegPromptInput) -> Dict[str, Any]:
    """Deterministic offline mock — replaces real LLM call when network unavailable."""
    base = params.model_dump()
    return {
        "mock": True,
        "module": "synth_neg_prompt",
        "params": base,
        "echo": "synth:synth_neg_prompt:offline",
    }


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


__all__ = ["neg_prompt", "NegPromptInput", "NegPromptOutput"]
