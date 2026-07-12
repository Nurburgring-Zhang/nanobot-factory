"""synth_translate_en: Offline mock English-to-Chinese translator.

**OFFLINE MOCK** — returns ``{mock: True, module: 'synth_translate_en', echo: 'synth:synth_translate_en:offline'}``.
Real English-to-Chinese translation is NOT implemented. The "live API" branch in
this module POSTs to ``https://api.example.invalid/...`` which always fails DNS, so
in practice every call ends up in the deterministic offline mock that echoes the
input ``params`` back. To translate text for real, call an LLM provider (or a
dedicated translation API) directly via the providers module.

Args:
    text: English text to translate (echoed back; not translated)
    formality: 'neutral' / 'formal' / 'casual' (echoed back; not used)

Returns:
    SkillOutput with ``result: {mock: True, echo: 'synth:synth_translate_en:offline', params: {...}}``
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


class TranslateEnInput(BaseModel):
    text: str
    formality: str = 'neutral'


class TranslateEnOutput(BaseModel):
    pass


async def translate_en(input: SkillInput) -> SkillOutput:
    """英译中 (translate_en).

    Args:
        input.prompt:  free-form user text
        input.params:  parsed as ``TranslateEnInput``; if invalid falls back to mock

    Returns:
        SkillOutput with structured ``result`` dict + metadata.
    """
    t0 = _now_ms()
    try:
        params = TranslateEnInput.model_validate(input.params or {})
    except Exception as exc:
        return _build_output(
            success=False,
            result=None,
            error=f"invalid params: {exc}",
            metadata={"skill_module": "synth_translate_en", "validation_error": True},
        )

    # Try live API first (best-effort); fall back to deterministic mock.
    live = None
    if NETWORK_OK:
        live = await _post_json(
            "https://api.example.invalid/synth/synth_translate_en",
            params.model_dump(),
            timeout=2.0,
        )

    if live is not None and isinstance(live, dict):
        return _build_output(
            success=True,
            result=live,
            metadata={
                "skill_module": "synth_translate_en",
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
            "skill_module": "synth_translate_en",
            "source": "mock",
            "elapsed_ms": _now_ms() - t0,
        },
    )


def _mock(params: TranslateEnInput) -> Dict[str, Any]:
    """Deterministic offline mock — replaces real LLM call when network unavailable."""
    base = params.model_dump()
    return {
        "mock": True,
        "module": "synth_translate_en",
        "params": base,
        "echo": "synth:synth_translate_en:offline",
    }


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


__all__ = ["translate_en", "TranslateEnInput", "TranslateEnOutput"]
