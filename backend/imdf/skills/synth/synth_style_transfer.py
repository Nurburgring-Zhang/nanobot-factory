"""synth_style_transfer: Offline mock style-transfer paraphraser.

**OFFLINE MOCK** — returns ``{mock: True, module: 'synth_style_transfer', echo: 'synth:synth_style_transfer:offline'}``.
Real style transfer (rewriting text in a different register/tone) is NOT implemented.
The "live API" branch in this module POSTs to ``https://api.example.invalid/...``
which always fails DNS, so in practice every call ends up in the deterministic
offline mock that echoes the input ``params`` back. To perform real style transfer,
call an LLM provider directly via the providers module.

Args:
    text: text to rewrite (echoed back; not transformed)
    source_style: 'formal' / 'casual' / 'technical' / etc. (echoed back; not used)
    target_style: 'formal' / 'casual' / 'technical' / etc. (echoed back; not used)

Returns:
    SkillOutput with ``result: {mock: True, echo: 'synth:synth_style_transfer:offline', params: {...}}``
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


class StyleTransferInput(BaseModel):
    text: str
    source_style: str = 'formal'
    target_style: str = 'casual'


class StyleTransferOutput(BaseModel):
    pass


async def style_transfer(input: SkillInput) -> SkillOutput:
    """风格迁移 (style_transfer).

    Args:
        input.prompt:  free-form user text
        input.params:  parsed as ``StyleTransferInput``; if invalid falls back to mock

    Returns:
        SkillOutput with structured ``result`` dict + metadata.
    """
    t0 = _now_ms()
    try:
        params = StyleTransferInput.model_validate(input.params or {})
    except Exception as exc:
        return _build_output(
            success=False,
            result=None,
            error=f"invalid params: {exc}",
            metadata={"skill_module": "synth_style_transfer", "validation_error": True},
        )

    # Try live API first (best-effort); fall back to deterministic mock.
    live = None
    if NETWORK_OK:
        live = await _post_json(
            "https://api.example.invalid/synth/synth_style_transfer",
            params.model_dump(),
            timeout=2.0,
        )

    if live is not None and isinstance(live, dict):
        return _build_output(
            success=True,
            result=live,
            metadata={
                "skill_module": "synth_style_transfer",
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
            "skill_module": "synth_style_transfer",
            "source": "mock",
            "elapsed_ms": _now_ms() - t0,
        },
    )


def _mock(params: StyleTransferInput) -> Dict[str, Any]:
    """Deterministic offline mock — replaces real LLM call when network unavailable."""
    base = params.model_dump()
    return {
        "mock": True,
        "module": "synth_style_transfer",
        "params": base,
        "echo": "synth:synth_style_transfer:offline",
    }


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


__all__ = ["style_transfer", "StyleTransferInput", "StyleTransferOutput"]
