"""label_clip_zero — CLIP zero-shot image classification.

Assigns the most likely category from a user-provided candidate list to an
image (URL or local path). Falls back to a deterministic offline mock when
the upstream CLIP service is unreachable.

Inputs:
    image:     str   — image URL or local path
    candidates: list — candidate category strings (>=2)

Outputs:
    label:    str   — best-matching candidate
    score:    float — softmax-style confidence in [0, 1]
    scores:   dict  — per-candidate scores
    timestamp/source/confidence/elapsed_ms — standard envelope
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


class ClipZeroInput(BaseModel):
    image: str = Field(..., description="Image URL or local path")
    candidates: List[str] = Field(..., min_length=2, description="Candidate labels (>=2)")
    model: str = Field(default="clip-vit-l14", description="CLIP backbone")
    top_k: int = Field(default=3, ge=1, le=20)

    @field_validator("candidates")
    @classmethod
    def _strip_blanks(cls, v: List[str]) -> List[str]:
        out = [c.strip() for c in v if c and c.strip()]
        if len(out) < 2:
            raise ValueError("candidates must contain at least 2 non-empty labels")
        return out


async def label_clip_zero(input: SkillInput) -> SkillOutput:
    """Async entry — validate → live-call → mock-fallback → SkillOutput."""
    t0 = time.perf_counter()
    try:
        payload = ClipZeroInput.model_validate(input.params or {})
    except Exception as exc:
        return build_output(
            success=False, result=None, error=f"invalid input: {exc}", source="label",
        )

    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.clip-zero.example/classify",
            payload.model_dump(),
            timeout=4.0,
        )

    if live and isinstance(live, dict) and "label" in live:
        result = {
            "label": str(live["label"]),
            "score": clamp(float(live.get("score", 0.9))),
            "scores": dict(live.get("scores", {})),
            "top_k": list(live.get("top_k", [])),
        }
        return build_output(
            success=True, result=result, source="live",
            confidence=result["score"],
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — deterministic score per candidate.
    seed = stable_seed(payload.image, tuple(payload.candidates))
    raw = [(seed >> i) & 0xFF for i in range(0, len(payload.candidates) * 8, 8)]
    scores_raw = [(raw[i] if i < len(raw) else 50) + 1 for i in range(len(payload.candidates))]
    total = sum(scores_raw)
    scores = {c: clamp(s / total) for c, s in zip(payload.candidates, scores_raw)}
    top_label = max(scores, key=lambda k: scores[k])
    top_k_sorted = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[: payload.top_k]

    result = {
        "label": top_label,
        "score": round(scores[top_label], 4),
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "top_k": [{"label": k, "score": round(v, 4)} for k, v in top_k_sorted],
        "model": payload.model,
        "timestamp": now_iso(),
    }
    return build_output(
        success=True, result=result, source="mock",
        confidence=round(scores[top_label], 4),
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_clip_zero", "ClipZeroInput"]