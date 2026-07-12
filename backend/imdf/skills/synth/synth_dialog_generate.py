"""Synth skill — 多轮对话生成.

Module: ``synth_dialog_generate``
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


class DialogGenerateInput(BaseModel):
    topic: str
    num_turns: int = Field(default=3)
    participants: list = ['A', 'B']


class DialogGenerateOutput(BaseModel):
    pass


async def dialog_generate(input: SkillInput) -> SkillOutput:
    """多轮对话生成 (dialog_generate).

    Args:
        input.prompt:  free-form user text
        input.params:  parsed as ``DialogGenerateInput``; if invalid falls back to mock

    Returns:
        SkillOutput with structured ``result`` dict + metadata.
    """
    t0 = _now_ms()
    try:
        params = DialogGenerateInput.model_validate(input.params or {})
    except Exception as exc:
        return _build_output(
            success=False,
            result=None,
            error=f"invalid params: {exc}",
            metadata={"skill_module": "synth_dialog_generate", "validation_error": True},
        )

    # Try live API first (best-effort); fall back to deterministic mock.
    live = None
    if NETWORK_OK:
        live = await _post_json(
            "https://api.example.invalid/synth/synth_dialog_generate",
            params.model_dump(),
            timeout=2.0,
        )

    if live is not None and isinstance(live, dict):
        return _build_output(
            success=True,
            result=live,
            metadata={
                "skill_module": "synth_dialog_generate",
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
            "skill_module": "synth_dialog_generate",
            "source": "mock",
            "elapsed_ms": _now_ms() - t0,
        },
    )


def _mock(params: DialogGenerateInput) -> Dict[str, Any]:
    """Deterministic offline mock — replaces real LLM call when network unavailable."""
    base = params.model_dump()
    return {
        "mock": True,
        "module": "synth_dialog_generate",
        "params": base,
        "echo": "synth:synth_dialog_generate:offline",
    }


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


__all__ = ["dialog_generate", "DialogGenerateInput", "DialogGenerateOutput"]
