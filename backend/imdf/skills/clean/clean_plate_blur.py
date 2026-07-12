"""clean_plate_blur — Auto license-plate blurring.

Same shape as clean_face_blur but specialised for license plate
detection.  Region boxes are emitted; downstream toolchain applies the
actual blur.

Skill function: ``clean_plate_blur(input) -> SkillOutput``.
"""

import hashlib
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata, safe_httpx_call


SKILL_ID = "skill_clean_plate_blur"


class PlateBlurInput(BaseModel):
    image_url: str = Field(..., description="Image URL or local path")
    region_hint: str = Field("auto", description="auto|us|eu|cn — region-specific OCR boost")
    blur_strength: int = Field(50, ge=1, le=99)


class PlateBlurOutput(BaseModel):
    plates: List[Dict[str, Any]] = Field(default_factory=list)
    blur_strength: int = 50
    offline: bool = False
    region: str = "auto"


def _fake_plate_boxes(url: str) -> List[Dict[str, Any]]:
    h = hashlib.sha1(url.encode("utf-8")).digest()
    n = 1 + (h[0] % 2)
    boxes = []
    for i in range(n):
        x = (h[i + 1] / 255.0) * 0.7
        y = 0.5 + (h[i + 2] / 255.0) * 0.3
        w = 110 + (h[i + 3] % 40)
        h_box = 30 + (h[i + 4] % 12)
        boxes.append({"x": round(x, 3), "y": round(y, 3),
                      "w": w, "h": h_box,
                      "confidence": round(0.85 - i * 0.04, 3),
                      "region": "us"})
    return boxes


async def clean_plate_blur(input: SkillInput) -> SkillOutput:
    payload = PlateBlurInput(**(input.params or {}))

    remote = await safe_httpx_call(
        "https://example.invalid/api/v1/clean/plate/detect",
        payload=payload.model_dump(),
        mock={"plates": _fake_plate_boxes(payload.image_url)},
    )
    if remote["status"] == "ok" and remote["data"].get("plates"):
        plates = remote["data"]["plates"]
        offline = False
    else:
        plates = _fake_plate_boxes(payload.image_url)
        offline = True

    out = PlateBlurOutput(
        plates=plates,
        blur_strength=payload.blur_strength,
        offline=offline,
        region=payload.region_hint,
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_plate_blur", offline=offline),
    )


__all__ = ["PlateBlurInput", "PlateBlurOutput", "clean_plate_blur"]
