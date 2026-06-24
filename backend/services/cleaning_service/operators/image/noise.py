"""clean.image.noise — image-level noise estimation via Laplacian high-pass.

Returns noise sigma estimate per item; high sigma = noisy / grainy.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from .._image_utils import _HAS_CV2, _HAS_NUMPY, _load_image, to_grayscale_array


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return per-item noise sigma (Median Absolute Deviation on Laplacian).

    params:
        max_sigma: float = 25.0  (drop items with sigma above this; only in filter mode)
        mode: str = "score"      (score | filter)
    """
    max_sigma = float(params.get("max_sigma", 25.0))
    mode = str(params.get("mode", "score"))
    if not _HAS_NUMPY:
        return [{"item": x, "ok": True, "note": "numpy unavailable"} for x in items]
    if not _HAS_CV2:
        # Pure-numpy Laplacian + MAD fallback (slightly less precise)
        from scipy.ndimage import median_filter, laplace

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
            import numpy as np
            gray = to_grayscale_array(img)
            if _HAS_CV2:
                import cv2
                lap = cv2.Laplacian(gray, cv2.CV_64F)
            else:
                from scipy.ndimage import laplace
                lap = laplace(gray.astype(np.float64))
            mad = float(np.median(np.abs(lap - np.median(lap))))
            sigma = mad / 0.6745  # robust Gaussian noise estimate
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"noise_estimation_failed: {e}"})
            continue
        rec = {"item": x, "sigma": round(sigma, 2), "is_noisy": sigma > max_sigma}
        if mode == "filter" and sigma > max_sigma:
            rec["passed"] = False
        elif mode == "filter":
            rec["passed"] = True
        out.append(rec)
    if mode == "filter":
        return [r for r in out if r.get("passed", True)]
    return out