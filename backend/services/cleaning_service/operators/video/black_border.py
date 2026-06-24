"""clean.video.black_border — flag/filter videos with letterbox/pillarbox borders."""
from __future__ import annotations

from typing import Any, Dict, List

from .._video_utils import _HAS_CV2, _HAS_NUMPY, black_border_ratio_frame, iter_frames


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Sample up to 8 frames per video and flag if border ratio > threshold.

    params:
        threshold: float = 0.85
        max_frames: int = 8
        mode: str = "score"
    """
    threshold = float(params.get("threshold", 0.85))
    max_frames = int(params.get("max_frames", 8))
    mode = str(params.get("mode", "score"))
    if not _HAS_CV2 or not _HAS_NUMPY:
        return [{"item": x, "has_black_border": False,
                 "note": "cv2/numpy unavailable"} for x in items]
    out: List[Dict[str, Any]] = []
    for x in items:
        if not isinstance(x, str):
            out.append({"item": x, "has_black_border": False, "note": "not a file path"})
            continue
        frames = list(iter_frames(x, max_frames=max_frames))
        if not frames:
            out.append({"item": x, "has_black_border": False, "note": "no_frames"})
            continue
        try:
            ratios = [black_border_ratio_frame(f) for f in frames]
            avg = sum(ratios) / len(ratios)
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"border_check_failed: {e}"})
            continue
        rec = {"item": x, "avg_border_ratio": round(avg, 4),
               "has_black_border": avg >= threshold}
        if mode == "filter":
            rec["passed"] = avg < threshold
        out.append(rec)
    if mode == "filter":
        return [r for r in out if r.get("passed", True)]
    return out