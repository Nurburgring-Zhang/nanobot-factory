"""Synth skill — 时序动作描述.

Module: ``synth_video_temporal``
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


class VideoTemporalInput(BaseModel):
    video_ref: str
    num_segments: int = Field(default=4)


class VideoTemporalOutput(BaseModel):
    pass


async def video_temporal(input: SkillInput) -> SkillOutput:
    """时序动作描述 (video_temporal).

    Args:
        input.prompt:  free-form user text
        input.params:  parsed as ``VideoTemporalInput``; if invalid falls back to mock

    Returns:
        SkillOutput with structured ``result`` dict + metadata.
    """
    t0 = _now_ms()
    try:
        params = VideoTemporalInput.model_validate(input.params or {})
    except Exception as exc:
        return _build_output(
            success=False,
            result=None,
            error=f"invalid params: {exc}",
            metadata={"skill_module": "synth_video_temporal", "validation_error": True},
        )

    # Try live API first (best-effort); fall back to deterministic mock.
    live = None
    if NETWORK_OK:
        live = await _post_json(
            "https://api.example.invalid/synth/synth_video_temporal",
            params.model_dump(),
            timeout=2.0,
        )

    if live is not None and isinstance(live, dict):
        return _build_output(
            success=True,
            result=live,
            metadata={
                "skill_module": "synth_video_temporal",
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
            "skill_module": "synth_video_temporal",
            "source": "mock",
            "elapsed_ms": _now_ms() - t0,
        },
    )


def _mock(params: VideoTemporalInput) -> Dict[str, Any]:
    """Deterministic offline mock — replaces real LLM call when network unavailable."""
    base = params.model_dump()
    return {
        "mock": True,
        "module": "synth_video_temporal",
        "params": base,
        "echo": "synth:synth_video_temporal:offline",
    }


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


__all__ = ["video_temporal", "VideoTemporalInput", "VideoTemporalOutput"]
