"""label_pose_detect — human pose estimation (skeleton keypoints).

Detects human poses in an image and returns per-person keypoints (COCO 17
format by default).

Inputs:
    image:        str
    format:       str  — "coco_17"|"body_18"|"body_25"
    max_people:   int  — cap on detected people (default 10)

Outputs:
    poses:        list — each {"person_id", "keypoints": [{name, x, y, score}],
                            "score"}
    count:        int
"""
from __future__ import annotations

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


_VALID_FORMATS = {"coco_17", "body_18", "body_25"}

_KEYPOINTS_BY_FORMAT: Dict[str, List[str]] = {
    "coco_17": [
        "nose", "left_eye", "right_eye", "left_ear", "right_ear",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_hip", "right_hip",
        "left_knee", "right_knee", "left_ankle", "right_ankle",
    ],
    "body_18": [
        "nose", "neck", "right_shoulder", "right_elbow", "right_wrist",
        "left_shoulder", "left_elbow", "left_wrist", "right_hip",
        "right_knee", "right_ankle", "left_hip", "left_knee", "left_ankle",
        "right_eye", "left_eye", "right_ear", "left_ear",
    ],
    "body_25": [
        "nose", "neck", "right_shoulder", "right_elbow", "right_wrist",
        "left_shoulder", "left_elbow", "left_wrist", "mid_hip",
        "right_hip", "right_knee", "right_ankle", "left_hip", "left_knee",
        "left_ankle", "right_eye", "left_eye", "right_ear", "left_ear",
        "left_big_toe", "left_small_toe", "left_heel", "right_big_toe",
        "right_small_toe", "right_heel",
    ],
}


class PoseDetectInput(BaseModel):
    image: str = Field(...)
    format: str = Field(default="coco_17")
    max_people: int = Field(default=10, ge=1, le=64)
    model: str = Field(default="openpose")

    @field_validator("format")
    @classmethod
    def _fmt(cls, v: str) -> str:
        v = (v or "coco_17").lower().strip()
        if v not in _VALID_FORMATS:
            raise ValueError(f"format must be one of {sorted(_VALID_FORMATS)}")
        return v


async def label_pose_detect(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = PoseDetectInput.model_validate(input.params or {})
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    keypoint_names = _KEYPOINTS_BY_FORMAT[payload.format]
    live = None
    if NETWORK_OK and payload.image.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.pose.example/detect",
            payload.model_dump(), timeout=6.0,
        )

    if live and isinstance(live, dict) and live.get("poses"):
        poses: List[Dict[str, Any]] = []
        for i, p in enumerate(live["poses"][: payload.max_people]):
            kps = p.get("keypoints", [])
            poses.append({
                "person_id": str(p.get("person_id", f"person-{i}")),
                "score": clamp(float(p.get("score", 0.0))),
                "keypoints": [
                    {"name": kp.get("name", keypoint_names[j % len(keypoint_names)]),
                     "x": float(kp.get("x", 0.0)),
                     "y": float(kp.get("y", 0.0)),
                     "score": clamp(float(kp.get("score", 0.0)))}
                    for j, kp in enumerate(kps)
                ],
            })
        return build_output(
            success=True,
            result={"poses": poses, "count": len(poses), "format": payload.format,
                    "model": payload.model, "timestamp": now_iso()},
            source="live", confidence=0.9,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — generate 1-3 people with keypoints on a skeleton grid.
    seed = stable_seed(payload.image, payload.format)
    n_people = (seed % 3) + 1
    n_people = min(n_people, payload.max_people)
    poses = []
    for p_idx in range(n_people):
        p_seed = (seed >> (p_idx * 6)) & 0xFFFFFF
        cx = 100 + (p_seed % 300)
        cy = 80 + ((p_seed >> 4) % 200)
        score = clamp(0.6 + ((p_seed >> 8) % 350) / 1000.0)
        kps = []
        for k_idx, name in enumerate(keypoint_names):
            k_seed = (p_seed >> (k_idx % 6)) & 0xFF
            kx = cx + (k_seed - 128) % 40
            ky = cy + ((k_seed >> 2) - 64) % 60
            kps.append({
                "name": name, "x": float(kx), "y": float(ky),
                "score": round(clamp(0.5 + ((k_seed >> 4) % 450) / 1000.0), 4),
            })
        poses.append({"person_id": f"person-{p_idx}", "score": round(score, 4), "keypoints": kps})

    return build_output(
        success=True,
        result={"poses": poses, "count": len(poses), "format": payload.format,
                "model": payload.model, "timestamp": now_iso()},
        source="mock", confidence=0.75,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_pose_detect", "PoseDetectInput"]