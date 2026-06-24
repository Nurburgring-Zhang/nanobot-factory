"""clean.video.nsfw — sample frames and run skin-tone NSFW heuristic on each."""
from __future__ import annotations

from typing import Any, Dict, List

from .._video_utils import _HAS_CV2, _HAS_NUMPY, iter_frames


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aggregate max skin-ratio across N frames; flag if max >= threshold.

    params:
        threshold: float = 0.35
        max_frames: int = 10
    """
    threshold = float(params.get("threshold", 0.35))
    max_frames = int(params.get("max_frames", 10))
    if not _HAS_CV2 or not _HAS_NUMPY:
        return [{"item": x, "is_nsfw": False, "note": "cv2/numpy unavailable"} for x in items]
    import cv2
    import numpy as np
    out: List[Dict[str, Any]] = []
    for x in items:
        if not isinstance(x, str):
            out.append({"item": x, "is_nsfw": False})
            continue
        frames = list(iter_frames(x, max_frames=max_frames))
        if not frames:
            out.append({"item": x, "is_nsfw": False, "note": "no_frames"})
            continue
        ratios: List[float] = []
        try:
            for f in frames:
                ycc = cv2.cvtColor(f, cv2.COLOR_BGR2YCrCb)
                Y = ycc[..., 0].astype(np.float32)
                Cr = ycc[..., 1].astype(np.float32)
                Cb = ycc[..., 2].astype(np.float32)
                mask = (Y > 80) & (Cr > 133) & (Cr < 180) & (Cb > 77) & (Cb < 135) & (Cr > Cb)
                # downsample to 128x128 for speed
                h, w = mask.shape
                step_h = max(1, h // 64)
                step_w = max(1, w // 64)
                mask = mask[::step_h, ::step_w]
                ratios.append(float(mask.mean()))
            max_r = max(ratios)
            avg_r = float(np.mean(ratios))
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"video_nsfw_failed: {e}"})
            continue
        out.append({
            "item": x,
            "max_skin_ratio": round(max_r, 4),
            "avg_skin_ratio": round(avg_r, 4),
            "is_nsfw": max_r >= threshold,
            "frames_sampled": len(ratios),
        })
    return out