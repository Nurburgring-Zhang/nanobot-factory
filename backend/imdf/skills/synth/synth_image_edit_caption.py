"""synth_image_edit_caption: Offline mock image-edit instruction generator.

**OFFLINE MOCK** — returns ``{mock: True, module: 'synth_image_edit_caption', echo: 'synth:synth_image_edit_caption:offline'}``.
Real image-edit instruction generation is NOT implemented. The "live API" branch in
this module POSTs to ``https://api.example.invalid/...`` which always fails DNS, so
in practice every call ends up in the deterministic offline mock that echoes the
input ``params`` back. To generate a real edit instruction, call a vision-capable
LLM provider directly via the providers module.

Args:
    base_caption: description of the source image (echoed back; not interpreted)
    edit_intent: 'enhance' / 'inpaint' / 'recolor' / etc. (echoed back; not used)

Returns:
    SkillOutput with ``result: {mock: True, echo: 'synth:synth_image_edit_caption:offline', params: {...}}``
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


class ImageEditCaptionInput(BaseModel):
    base_caption: str
    edit_intent: str = 'enhance'


class ImageEditCaptionOutput(BaseModel):
    pass


async def image_edit_caption(input: SkillInput) -> SkillOutput:
    """图像编辑指令生成 (image_edit_caption).

    Args:
        input.prompt:  free-form user text
        input.params:  parsed as ``ImageEditCaptionInput``; if invalid falls back to mock

    Returns:
        SkillOutput with structured ``result`` dict + metadata.
    """
    t0 = _now_ms()
    try:
        params = ImageEditCaptionInput.model_validate(input.params or {})
    except Exception as exc:
        return _build_output(
            success=False,
            result=None,
            error=f"invalid params: {exc}",
            metadata={"skill_module": "synth_image_edit_caption", "validation_error": True},
        )

    # Try live API first (best-effort); fall back to deterministic mock.
    live = None
    if NETWORK_OK:
        live = await _post_json(
            "https://api.example.invalid/synth/synth_image_edit_caption",
            params.model_dump(),
            timeout=2.0,
        )

    if live is not None and isinstance(live, dict):
        return _build_output(
            success=True,
            result=live,
            metadata={
                "skill_module": "synth_image_edit_caption",
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
            "skill_module": "synth_image_edit_caption",
            "source": "mock",
            "elapsed_ms": _now_ms() - t0,
        },
    )


def _mock(params: ImageEditCaptionInput) -> Dict[str, Any]:
    """Deterministic offline mock — replaces real LLM call when network unavailable."""
    base = params.model_dump()
    return {
        "mock": True,
        "module": "synth_image_edit_caption",
        "params": base,
        "echo": "synth:synth_image_edit_caption:offline",
    }


def _now_ms() -> float:
    import time
    return time.time() * 1000.0


__all__ = ["image_edit_caption", "ImageEditCaptionInput", "ImageEditCaptionOutput"]
