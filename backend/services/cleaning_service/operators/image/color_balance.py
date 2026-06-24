"""clean.image.color_balance — flag images with skewed color cast.

Uses Gray-World assumption: avg of R/G/B channels should be ~equal.
Deviation > 0.15 (relative) = strong color cast.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._image_utils import _HAS_NUMPY, _load_image


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return per-item mean RGB + deviation flag.

    params:
        deviation_threshold: float = 0.15
        mode: str = "score"
    """
    thr = float(params.get("deviation_threshold", 0.15))
    mode = str(params.get("mode", "score"))
    if not _HAS_NUMPY:
        return [{"item": x, "balanced": True, "note": "numpy unavailable"} for x in items]
    import numpy as np
    out: List[Dict[str, Any]] = []
    for x in items:
        try:
            img, _ = _load_image(x)
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": str(e)})
            continue
        if img is None:
            out.append({"item": x, "error": "load_failed"})
            continue
        try:
            arr = np.asarray(img.convert("RGB").resize((128, 128)), dtype=np.float32) / 255.0
            mean = arr.reshape(-1, 3).mean(axis=0)
            gray_world = mean.mean()
            deviation = float(np.abs(mean - gray_world).max())
            balanced = deviation < thr
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": str(e)})
            continue
        rec = {
            "item": x,
            "mean_rgb": [round(float(c), 4) for c in mean],
            "deviation": round(deviation, 4),
            "balanced": balanced,
        }
        if mode == "filter":
            rec["passed"] = balanced
        out.append(rec)
    if mode == "filter":
        return [r for r in out if r.get("passed", True)]
    return out