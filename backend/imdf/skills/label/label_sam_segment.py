"""label_sam_segment — SAM (Segment Anything) segmentation.

Returns one or more segmentation masks for an image. Supports box-prompted,
point-prompted, or auto-everything mode.

Inputs:
    image:       str
    boxes:       list[list[int]]?  — prompt boxes [x1,y1,x2,y2]
    points:      list[list[int]]?  — prompt points (pixel coords)
    mode:        str  — "auto"|"box"|"point"

Outputs:
    masks:       list — each {mask_id, area, bbox, score, format}
    count:       int
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


_VALID_MODES = {"auto", "box", "point"}


class SamSegmentInput(BaseModel):
    image: str = Field(...)
    boxes: List[List[int]] = Field(default_factory=list)
    points: List[List[int]] = Field(default_factory=list)
    mode: str = Field(default="auto")
    model: str = Field(default="sam-vit-h")

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        v = (v or "auto").lower().strip()
        if v not in _VALID_MODES:
            raise ValueError(f"mode must be one of {sorted(_VALID_MODES)}")
        return v


async def label_sam_segment(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = SamSegmentInput.model_validate(input.params or {})
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    if payload.mode == "box" and not payload.boxes:
        return build_output(success=False, error="mode='box' requires at least one box", source="label")
    if payload.mode == "point" and not payload.points:
        return build_output(success=False, error="mode='point' requires at least one point", source="label")

    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.sam.example/segment",
            payload.model_dump(), timeout=8.0,
        )

    if live and isinstance(live, dict) and live.get("masks"):
        masks = [
            {
                "mask_id": str(m.get("mask_id", f"mask-{i}")),
                "area": int(m.get("area", 0)),
                "bbox": list(m.get("bbox", [0, 0, 0, 0])),
                "score": clamp(float(m.get("score", 0.0))),
                "format": m.get("format", "rle"),
            }
            for i, m in enumerate(live["masks"])
        ]
        return build_output(
            success=True,
            result={"masks": masks, "count": len(masks), "mode": payload.mode,
                    "model": payload.model, "timestamp": now_iso()},
            source="live", confidence=0.9,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — derive masks from prompt boxes/points or auto.
    seed = stable_seed(payload.image, payload.mode, len(payload.boxes), len(payload.points))
    n_seeds = max(2, (seed % 4) + 1)
    masks: List[Dict[str, Any]] = []
    for i in range(n_seeds):
        s = (seed >> (i * 3)) & 0xFFFFFF
        area = 2000 + (s % 50000)
        bbox = [s % 400, (s >> 4) % 300, ((s >> 8) % 400) + 100, ((s >> 12) % 300) + 100]
        masks.append({
            "mask_id": f"mask-{i}",
            "area": area,
            "bbox": bbox,
            "score": round(clamp(0.6 + (s % 350) / 1000.0), 4),
            "format": "rle",
        })

    return build_output(
        success=True,
        result={"masks": masks, "count": len(masks), "mode": payload.mode,
                "model": payload.model, "timestamp": now_iso()},
        source="mock", confidence=0.8,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_sam_segment", "SamSegmentInput"]