"""label_depth_estimate — monocular depth estimation.

Estimates a per-pixel depth map for an image and returns summary statistics
(mean/median/min/max) plus a flat-sampled point list for downstream use.

Inputs:
    image:      str
    max_depth:  float — clamp upper bound (meters)
    normalize:  bool  — whether to normalize to [0, 1]

Outputs:
    depth_map:   list — sampled values (length = sample_size)
    stats:       dict — {mean, median, min, max, std}
    shape:       list — [H, W]
    normalized:  bool
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List

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


class DepthEstimateInput(BaseModel):
    image: str = Field(...)
    max_depth: float = Field(default=10.0, gt=0.0, le=1000.0)
    normalize: bool = Field(default=True)
    sample_size: int = Field(default=64, ge=16, le=4096)
    model: str = Field(default="midas-v21")


async def label_depth_estimate(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = DepthEstimateInput.model_validate(input.params or {})
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.depth.example/estimate",
            payload.model_dump(), timeout=6.0,
        )

    if live and isinstance(live, dict) and live.get("depth_map"):
        depth_map = [float(x) for x in live["depth_map"][: payload.sample_size]]
        stats = _stats(depth_map)
        if payload.normalize:
            depth_map = [clamp(d / payload.max_depth) for d in depth_map]
        return build_output(
            success=True,
            result={
                "depth_map": depth_map, "stats": stats,
                "shape": list(live.get("shape", [0, 0])),
                "normalized": payload.normalize, "model": payload.model,
                "timestamp": now_iso(),
            },
            source="live", confidence=0.9,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — synthesize a depth ramp with noise.
    seed = stable_seed(payload.image, payload.model)
    depth_map: List[float] = []
    for i in range(payload.sample_size):
        t = i / max(payload.sample_size - 1, 1)
        noise = ((seed >> (i % 16)) & 0xFF) / 255.0 - 0.5
        depth_map.append(0.2 + t * (payload.max_depth - 0.2) + noise * 0.3)
    depth_map = [clamp(d, 0.05, payload.max_depth) for d in depth_map]
    raw_stats = _stats(depth_map)
    out_map = depth_map
    if payload.normalize:
        out_map = [round(clamp(d / payload.max_depth), 4) for d in depth_map]
    return build_output(
        success=True,
        result={
            "depth_map": out_map, "stats": raw_stats, "shape": [16, payload.sample_size // 16],
            "normalized": payload.normalize, "model": payload.model,
            "timestamp": now_iso(),
        },
        source="mock", confidence=0.7,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


def _stats(values: List[float]) -> Dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "std": 0.0}
    n = len(values)
    sorted_v = sorted(values)
    mean = sum(values) / n
    median = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    var = sum((v - mean) ** 2 for v in values) / n
    return {
        "mean": round(mean, 4),
        "median": round(median, 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "std": round(math.sqrt(var), 4),
    }


__all__ = ["label_depth_estimate", "DepthEstimateInput"]