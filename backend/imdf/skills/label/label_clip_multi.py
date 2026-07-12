"""label_clip_multi — CLIP multi-label classification.

Returns multiple independently-scored labels for an image (independent
sigmoid probabilities, NOT softmax). Each candidate gets its own score in
[0, 1]. Labels above ``threshold`` are marked as ``selected``.

Inputs:
    image:     str
    candidates: list — must contain >=2 entries
    threshold: float — selection threshold (default 0.5)

Outputs:
    labels:      list — selected labels (above threshold)
    scores:      dict — per-candidate probability
    selected:    list — labels selected by threshold
    threshold:   float
"""

import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from backend.skills import SkillInput, SkillOutput

from ._base import (
    NETWORK_OK,
    build_output,
    clamp,
    now_iso,
    post_json,
    stable_seed,
)


class ClipMultiInput(BaseModel):
    image: str = Field(..., description="Image URL or local path")
    candidates: List[str] = Field(..., min_length=2)
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    model: str = Field(default="clip-vit-l14")

    @field_validator("candidates")
    @classmethod
    def _strip(cls, v: List[str]) -> List[str]:
        out = [c.strip() for c in v if c and c.strip()]
        if len(out) < 2:
            raise ValueError("candidates must have >=2 non-empty entries")
        return out


async def label_clip_multi(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = ClipMultiInput.model_validate(input.params or {})
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.clip-multi.example/classify",
            payload.model_dump(),
            timeout=4.0,
        )

    if live and isinstance(live, dict) and "scores" in live:
        scores = {k: clamp(float(v)) for k, v in live["scores"].items()}
        selected = [k for k, v in scores.items() if v >= payload.threshold]
        result = {
            "scores": scores,
            "selected": selected,
            "threshold": payload.threshold,
            "model": payload.model,
            "timestamp": now_iso(),
        }
        return build_output(
            success=True, result=result, source="live",
            confidence=max(scores.values()) if scores else 0.0,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — sigmoid-style independent scores.
    seed = stable_seed(payload.image, tuple(payload.candidates), "multi")
    scores: Dict[str, float] = {}
    for i, c in enumerate(payload.candidates):
        # 4-byte hash → [0, 1] mapped through sigmoid-shape scaling
        b = (seed >> (i * 4)) & 0xFFFFFFFF
        raw = (b % 1000) / 1000.0
        scores[c] = round(clamp(raw), 4)
    selected = [k for k, v in scores.items() if v >= payload.threshold]
    result = {
        "scores": scores,
        "selected": selected,
        "threshold": payload.threshold,
        "model": payload.model,
        "timestamp": now_iso(),
    }
    return build_output(
        success=True, result=result, source="mock",
        confidence=max(scores.values()) if scores else 0.0,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_clip_multi", "ClipMultiInput"]