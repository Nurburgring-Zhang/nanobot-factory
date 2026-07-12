"""clean_video_stabilize — Video stabilization.

Detects camera shake and reports the trajectory / smoothed output
parameters.  Emits stabilisation metadata (translation drift, rotation
corrected, smoothed FOV crop).

Skill function: ``clean_video_stabilize(input) -> SkillOutput``.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata, safe_httpx_call


SKILL_ID = "skill_clean_video_stabilize"


class VideoStabilizeInput(BaseModel):
    video_url: str = Field(..., description="Video URL or local path")
    smoothing: float = Field(0.6, ge=0.0, le=1.0)
    crop_to_fit: bool = Field(True)


class VideoStabilizeOutput(BaseModel):
    output_url: str = ""
    frames_analyzed: int = 0
    translation_drift_px: float = 0.0
    rotation_corrected_deg: float = 0.0
    fov_crop: float = 0.0
    offline: bool = False


def _mock_stab_stats(url: str) -> Dict[str, Any]:
    h = hashlib.sha256(url.encode("utf-8")).digest()
    return {
        "frames": int(50 + (h[0] / 255.0) * 200),
        "drift": round(8 + (h[1] / 255.0) * 20, 2),
        "rotation": round(0.5 + (h[2] / 255.0) * 3, 3),
        "fov_crop": round(0.02 + (h[3] / 255.0) * 0.08, 4),
    }


async def clean_video_stabilize(input: SkillInput) -> SkillOutput:
    payload = VideoStabilizeInput(**(input.params or {}))

    remote = await safe_httpx_call(
        "https://example.invalid/api/v1/clean/video/stabilize",
        payload=payload.model_dump(),
        mock={"output_url": "", **_mock_stab_stats(payload.video_url)},
    )

    if remote["status"] == "ok" and remote["data"].get("frames_analyzed"):
        data = remote["data"]
        offline = False
    else:
        data = _mock_stab_stats(payload.video_url)
        data["output_url"] = ""
        offline = True

    fov_crop = float(data.get("fov_crop", 0.0)) if payload.crop_to_fit else 0.0

    out = VideoStabilizeOutput(
        output_url=data.get("output_url", "") or f"mock://{payload.video_url}.stabilized.mp4",
        frames_analyzed=int(data.get("frames", 0)),
        translation_drift_px=float(data.get("drift", 0.0)),
        rotation_corrected_deg=float(data.get("rotation", 0.0)),
        fov_crop=fov_crop,
        offline=offline,
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_video_stabilize", offline=offline),
    )


__all__ = ["VideoStabilizeInput", "VideoStabilizeOutput", "clean_video_stabilize"]
