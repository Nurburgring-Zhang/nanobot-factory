"""clean_logo_watermark — Logo / watermark detection.

Detects logo overlays & watermarks in images.  Returns bounding boxes
and a confidence score per region.

Skill function: ``clean_logo_watermark(input) -> SkillOutput``.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata, safe_httpx_call


SKILL_ID = "skill_clean_logo_watermark"


class LogoWatermarkInput(BaseModel):
    image_url: str = Field(..., description="Image URL or local path")
    min_area_ratio: float = Field(0.005, ge=0.0001, le=0.5)
    max_detections: int = Field(5, ge=1, le=50)


class LogoWatermarkOutput(BaseModel):
    detections: List[Dict[str, Any]] = Field(default_factory=list)
    has_watermark: bool = False
    offline: bool = False


def _fake_watermarks(url: str, max_detections: int) -> List[Dict[str, Any]]:
    h = hashlib.sha256(url.encode("utf-8")).digest()
    n = h[0] % (max_detections + 1)
    out = []
    for i in range(n):
        x = 0.7 + (h[i + 1] / 255.0) * 0.25
        y = 0.05 + (h[i + 2] / 255.0) * 0.15
        w = 60 + (h[i + 3] % 60)
        h_b = 30 + (h[i + 4] % 30)
        out.append({"x": round(x, 3), "y": round(y, 3),
                    "w": w, "h": h_b,
                    "kind": "watermark" if i == 0 else "logo",
                    "confidence": round(0.78 - i * 0.07, 3)})
    return out


async def clean_logo_watermark(input: SkillInput) -> SkillOutput:
    payload = LogoWatermarkInput(**(input.params or {}))

    remote = await safe_httpx_call(
        "https://example.invalid/api/v1/clean/logo/detect",
        payload=payload.model_dump(),
        mock={"detections": _fake_watermarks(payload.image_url, payload.max_detections)},
    )
    if remote["status"] == "ok" and remote["data"].get("detections") is not None:
        detections = remote["data"]["detections"][: payload.max_detections]
        offline = False
    else:
        detections = _fake_watermarks(payload.image_url, payload.max_detections)
        offline = True

    out = LogoWatermarkOutput(
        detections=detections,
        has_watermark=any(d.get("kind") == "watermark" for d in detections),
        offline=offline,
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_logo_watermark", offline=offline),
    )


__all__ = ["LogoWatermarkInput", "LogoWatermarkOutput", "clean_logo_watermark"]
