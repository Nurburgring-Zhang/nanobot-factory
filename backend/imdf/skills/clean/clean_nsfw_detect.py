"""clean_nsfw_detect — NSFW content detection.

Reports an NSFW probability score in [0, 1] along with a categorical
label and a list of bounding boxes (offline mode emits empty list).

Skill function: ``clean_nsfw_detect(input) -> SkillOutput``.
"""

import hashlib
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata, safe_httpx_call


SKILL_ID = "skill_clean_nsfw_detect"


class NsfwDetectInput(BaseModel):
    image_url: str = Field(..., description="Image URL or local path")
    threshold: float = Field(0.7, ge=0.0, le=1.0)


class NsfwDetectOutput(BaseModel):
    nsfw_score: float = 0.0
    label: str = "safe"
    boxes: List[Dict[str, Any]] = Field(default_factory=list)
    flagged: bool = False
    offline: bool = False


def _mock_score(url: str) -> float:
    h = hashlib.md5(url.encode("utf-8")).digest()
    return round(0.05 + (h[0] / 255.0) * 0.45, 4)


def _mock_label(score: float) -> str:
    if score >= 0.85:
        return "explicit"
    if score >= 0.65:
        return "suggestive"
    if score >= 0.4:
        return "borderline"
    return "safe"


async def clean_nsfw_detect(input: SkillInput) -> SkillOutput:
    payload = NsfwDetectInput(**(input.params or {}))

    remote = await safe_httpx_call(
        "https://example.invalid/api/v1/clean/nsfw/detect",
        payload=payload.model_dump(),
        mock={"nsfw_score": _mock_score(payload.image_url), "boxes": []},
    )
    if remote["status"] == "ok" and "nsfw_score" in remote["data"]:
        score = float(remote["data"]["nsfw_score"])
        boxes = list(remote["data"].get("boxes", []))
        offline = False
    else:
        score = _mock_score(payload.image_url)
        boxes = []
        offline = True

    label = _mock_label(score)
    out = NsfwDetectOutput(
        nsfw_score=score,
        label=label,
        boxes=boxes,
        flagged=score >= payload.threshold,
        offline=offline,
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_nsfw_detect", offline=offline,
                               confidence=0.95 if not offline else 0.55),
    )


__all__ = ["NsfwDetectInput", "NsfwDetectOutput", "clean_nsfw_detect"]
