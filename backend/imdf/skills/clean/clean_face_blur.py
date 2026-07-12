"""clean_face_blur — Auto face blurring.

Detects faces via an external service when reachable, falls back to a
mock result with deterministic bounding boxes for offline mode.  Emits
the list of regions to blur; downstream toolchain handles actual pixel
manipulation.

Skill function: ``clean_face_blur(input) -> SkillOutput``.
"""

import hashlib
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata, safe_httpx_call


SKILL_ID = "skill_clean_face_blur"


class FaceBlurInput(BaseModel):
    image_url: str = Field(..., description="Image URL or local path")
    blur_strength: int = Field(35, ge=1, le=99, description="Kernel percent (1-99)")
    min_face_size: int = Field(40, description="Minimum face dimension in px")
    max_faces: int = Field(20)


class FaceBlurOutput(BaseModel):
    faces: List[Dict[str, Any]] = Field(default_factory=list)
    blur_strength: int = 35
    offline: bool = False


def _fake_face_boxes(url: str, max_faces: int, min_size: int) -> List[Dict[str, Any]]:
    """Generate deterministic fake bounding boxes."""
    h = hashlib.md5(url.encode("utf-8")).digest()
    boxes = []
    for i in range(min(2, max_faces)):
        x = (h[i * 2] / 255.0) * 0.5
        y = (h[i * 2 + 1] / 255.0) * 0.5
        size = min_size + (h[(i * 4) % len(h)] % 80)
        boxes.append({"x": round(x, 3), "y": round(y, 3),
                      "w": size, "h": size,
                      "confidence": 0.9 - i * 0.05})
    return boxes


async def clean_face_blur(input: SkillInput) -> SkillOutput:
    payload = FaceBlurInput(**(input.params or {}))

    remote = await safe_httpx_call(
        "https://example.invalid/api/v1/clean/face/detect",
        payload=payload.model_dump(),
        mock={"faces": _fake_face_boxes(payload.image_url, payload.max_faces, payload.min_face_size)},
    )
    if remote["status"] == "ok" and remote["data"].get("faces"):
        faces = remote["data"]["faces"][: payload.max_faces]
        offline = False
    else:
        faces = _fake_face_boxes(payload.image_url, payload.max_faces, payload.min_face_size)
        offline = True

    out = FaceBlurOutput(
        faces=faces,
        blur_strength=payload.blur_strength,
        offline=offline,
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_face_blur", offline=offline),
    )


__all__ = ["FaceBlurInput", "FaceBlurOutput", "clean_face_blur"]
