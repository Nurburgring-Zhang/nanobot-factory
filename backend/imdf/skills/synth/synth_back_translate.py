"""Synth skill — 回译增强.

Module: ``synth_back_translate``
Category: synth
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


class BackTranslateInput(BaseModel):
    text: str
    pivot_lang: str = 'en'
    rounds: int = Field(default=2)


class BackTranslateOutput(BaseModel):
    pass


async def back_translate(input: SkillInput) -> SkillOutput:
    """回译增强 (back_translate).

    Args:
        input.prompt:  free-form user text
        input.params:  parsed as ``BackTranslateInput``; if invalid falls back to mock

    Returns:
        SkillOutput with structured ``result`` dict + metadata.
    """
    t0 = _now_ms()
    try:
        params = BackTranslateInput.model_validate(input.params or {})
    except Exception as exc:
        return _build_output(
            success=False,
            result=None,
            error=f"invalid params: {exc}",
            metadata={"skill_module": "synth_back_translate", "validation_error": True},
        )

    # Try live API first (best-effort); fall back to deterministic mock.
    live = None
    if NETWORK_OK:
        live = await _post_json(
            "https://api.example.invalid/synth/synth_back_translate",
            params.model_dump(),
            timeout=2.0,
        )

    if live is not None and isinstance(live, dict):
        return _build_output(
            success=True,
            result=live,
            metadata={
                "skill_module": "synth_back_translate",
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
            "skill_module": "synth_back_translate",
            "source": "mock",
            "elapsed_ms": _now_ms() - t0,
        },
    )


def _mock(params: BackTranslateInput) -> Dict[str, Any]:
    """Deterministic offline mock — replaces real LLM call when network unavailable."""
    base = params.model_dump()
    return {
        "mock": True,
        "module": "synth_back_translate",
        "params": base,
        "echo": "synth:synth_back_translate:offline",
    }


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


__all__ = ["back_translate", "BackTranslateInput", "BackTranslateOutput"]
