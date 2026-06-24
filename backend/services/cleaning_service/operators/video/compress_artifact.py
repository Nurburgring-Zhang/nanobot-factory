"""clean.video.compress_artifact — blockiness / MPEG-style artifact score.

Heuristic on sampled frames: ratio of edge energy at 8-pixel boundaries vs
interior energy.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._video_utils import _HAS_CV2, _HAS_NUMPY, cv2_to_gray, iter_frames


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Average blockiness over sampled frames.

    params:
        threshold: float = 0.4
        max_frames: int = 8
        mode: str = "score"
    """
    threshold = float(params.get("threshold", 0.4))
    max_frames = int(params.get("max_frames", 8))
    mode = str(params.get("mode", "score"))
    if not _HAS_CV2 or not _HAS_NUMPY:
        return [{"item": x, "blockiness": 0.0,
                 "note": "cv2/numpy unavailable"} for x in items]
    import numpy as np
    out: List[Dict[str, Any]] = []
    for x in items:
        if not isinstance(x, str):
            out.append({"item": x, "blockiness": 0.0, "is_artifacted": False})
            continue
        frames = list(iter_frames(x, max_frames=max_frames))
        if not frames:
            out.append({"item": x, "blockiness": 0.0, "is_artifacted": False,
                        "note": "no_frames"})
            continue
        scores = []
        try:
            for f in frames:
                g = cv2_to_gray(f).astype(np.float32)
                if g.shape[0] < 16 or g.shape[1] < 16:
                    continue
                h_diff = np.abs(g[:, 8:] - g[:, :-8])
                block_energy = float(h_diff[:, ::8].mean())
                interior = np.abs(g[:, 8:-8] - g[:, 9:-7]).mean() + 1e-6
                scores.append(min(1.0, block_energy / interior / 5.0))
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"blockiness_failed: {e}"})
            continue
        if not scores:
            out.append({"item": x, "blockiness": 0.0, "is_artifacted": False})
            continue
        avg = float(np.mean(scores))
        rec = {"item": x, "blockiness": round(avg, 4),
               "is_artifacted": avg > threshold,
               "frames_sampled": len(scores)}
        if mode == "filter":
            rec["passed"] = avg <= threshold
        out.append(rec)
    if mode == "filter":
        return [r for r in out if r.get("passed", True)]
    return out