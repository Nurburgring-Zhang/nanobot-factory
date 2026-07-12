"""label_blip_caption — BLIP image captioning.

Generates a natural-language description for an image. Length and style are
controlled by ``max_length`` and ``style``.

Inputs:
    image:      str
    max_length: int  — 8..128
    style:      str  — {"factual", "romantic", "humorous", "poetic"}

Outputs:
    caption:    str  — generated text
    style:      str
    model:      str
"""
from __future__ import annotations

import time
from typing import Any, Dict

from pydantic import BaseModel, Field

from backend.skills import SkillInput, SkillOutput

from ._base import (
    NETWORK_OK,
    build_output,
    clamp,
    now_iso,
    post_json,
    stable_seed,
)


class BlipCaptionInput(BaseModel):
    image: str = Field(..., description="Image URL or local path")
    max_length: int = Field(default=64, ge=8, le=256)
    style: str = Field(default="factual")
    model: str = Field(default="blip-base")

    @classmethod
    def normalize_style(cls, v: str) -> str:
        v = (v or "factual").lower().strip()
        if v not in {"factual", "romantic", "humorous", "poetic"}:
            return "factual"
        return v


async def label_blip_caption(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = BlipCaptionInput.model_validate(input.params or {})
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    payload_dict = payload.model_dump()
    payload_dict["style"] = BlipCaptionInput.normalize_style(payload_dict.get("style", "factual"))

    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.blip.example/caption",
            payload_dict, timeout=5.0,
        )

    if live and isinstance(live, dict) and live.get("caption"):
        caption = str(live["caption"])[: payload.max_length]
        return build_output(
            success=True,
            result={"caption": caption, "style": payload_dict["style"], "model": payload.model, "timestamp": now_iso()},
            source="live", confidence=0.9,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — deterministic caption from seed.
    seed = stable_seed(payload.image, payload_dict["style"])
    openings = {
        "factual": "An image showing",
        "romantic": "A dreamy scene of",
        "humorous": "A whimsical moment featuring",
        "poetic": "A poetic vision of",
    }
    subjects = [
        "sunlit mountains", "a quiet alley", "wildflowers in bloom",
        "a vintage car", "a curious cat", "an old library",
        "misty forests", "a bustling market", "autumn leaves",
    ]
    rng = open  # noqa: F841  placeholder
    open_seed = seed
    subj_seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
    open_choice = openings[payload_dict["style"]]
    subj = subjects[subj_seed % len(subjects)]
    tail = "with rich detail and balanced composition."
    caption = f"{open_choice} {subj}, {tail}"
    if len(caption) > payload.max_length:
        caption = caption[: payload.max_length - 1].rstrip() + "…"

    return build_output(
        success=True,
        result={"caption": caption, "style": payload_dict["style"], "model": payload.model, "timestamp": now_iso()},
        source="mock", confidence=0.75,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_blip_caption", "BlipCaptionInput"]