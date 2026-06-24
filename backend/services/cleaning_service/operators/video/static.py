"""clean.video.static — flag videos with mostly static frames (low motion)."""
from __future__ import annotations

from typing import Any, Dict, List

from .._video_utils import _HAS_CV2, _HAS_NUMPY, iter_frames, static_frame_score


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Sample frames; compute mean pixel-diff; flag if < motion_threshold.

    params:
        motion_threshold: float = 0.02  (0..1; below = static)
        max_frames: int = 12
        mode: str = "score"
    """
    thr = float(params.get("motion_threshold", 0.02))
    max_frames = int(params.get("max_frames", 12))
    mode = str(params.get("mode", "score"))
    if not _HAS_CV2 or not _HAS_NUMPY:
        return [{"item": x, "motion_score": 0.0, "is_static": False,
                 "note": "cv2/numpy unavailable"} for x in items]
    out: List[Dict[str, Any]] = []
    for x in items:
        if not isinstance(x, str):
            out.append({"item": x, "motion_score": 0.0, "is_static": False})
            continue
        frames = list(iter_frames(x, max_frames=max_frames))
        if not frames:
            out.append({"item": x, "motion_score": 0.0, "is_static": False,
                        "note": "no_frames"})
            continue
        try:
            score = static_frame_score(frames)
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"static_score_failed: {e}"})
            continue
        rec = {"item": x, "motion_score": round(score, 4), "is_static": score < thr}
        if mode == "filter":
            rec["passed"] = score >= thr
        out.append(rec)
    if mode == "filter":
        return [r for r in out if r.get("passed", True)]
    return out