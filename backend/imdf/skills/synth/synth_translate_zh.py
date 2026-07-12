"""synth_translate_zh: Offline mock Chinese-to-English translator.

**OFFLINE MOCK** — returns ``{mock: True, module: 'synth_translate_zh', echo: 'synth:synth_translate_zh:offline'}``.
Real Chinese-to-English translation is NOT implemented. The "live API" branch in
this module POSTs to ``https://api.example.invalid/...`` which always fails DNS, so
in practice every call ends up in the deterministic offline mock that echoes the
input ``params`` back. To translate text for real, call an LLM provider (or a
dedicated translation API) directly via the providers module.

Args:
    text: Chinese text to translate (echoed back; not translated)
    formality: 'neutral' / 'formal' / 'casual' (echoed back; not used)

Returns:
    SkillOutput with ``result: {mock: True, echo: 'synth:synth_translate_zh:offline', params: {...}}``
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


class TranslateZhInput(BaseModel):
    text: str
    formality: str = 'neutral'


class TranslateZhOutput(BaseModel):
    pass


async def translate_zh(input: SkillInput) -> SkillOutput:
    """中译英 (translate_zh).

    Args:
        input.prompt:  free-form user text
        input.params:  parsed as ``TranslateZhInput``; if invalid falls back to mock

    Returns:
        SkillOutput with structured ``result`` dict + metadata.
    """
    t0 = _now_ms()
    try:
        params = TranslateZhInput.model_validate(input.params or {})
    except Exception as exc:
        return _build_output(
            success=False,
            result=None,
            error=f"invalid params: {exc}",
            metadata={"skill_module": "synth_translate_zh", "validation_error": True},
        )

    # Try live API first (best-effort); fall back to deterministic mock.
    live = None
    if NETWORK_OK:
        live = await _post_json(
            "https://api.example.invalid/synth/synth_translate_zh",
            params.model_dump(),
            timeout=2.0,
        )

    if live is not None and isinstance(live, dict):
        return _build_output(
            success=True,
            result=live,
            metadata={
                "skill_module": "synth_translate_zh",
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
            "skill_module": "synth_translate_zh",
            "source": "mock",
            "elapsed_ms": _now_ms() - t0,
        },
    )


def _mock(params: TranslateZhInput) -> Dict[str, Any]:
    """Deterministic offline mock — replaces real LLM call when network unavailable."""
    base = params.model_dump()
    return {
        "mock": True,
        "module": "synth_translate_zh",
        "params": base,
        "echo": "synth:synth_translate_zh:offline",
    }


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


__all__ = ["translate_zh", "TranslateZhInput", "TranslateZhOutput"]
