"""clean.image.blur — blur detection via Laplacian variance.

Higher variance = more high-frequency edges = sharper image.
Typical threshold: variance < 100 is blurry; < 50 is severely blurred.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._image_utils import _HAS_CV2, _HAS_NUMPY, _load_image, laplacian_variance, to_grayscale_array


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return per-item blur score; drop items whose variance < min_variance.

    params:
        min_variance: float = 80.0
        mode: str = "filter"  (filter | score | both)
    """
    min_var = float(params.get("min_variance", 80.0))
    mode = str(params.get("mode", "filter"))
    if not _HAS_NUMPY:
        return [{"item": x, "ok": True, "note": "numpy unavailable; passed through"} for x in items]

    scored: List[Dict[str, Any]] = []
    for x in items:
        try:
            img, meta = _load_image(x)
        except Exception as e:  # noqa: BLE001
            scored.append({"item": x, "ok": False, "error": str(e)})
            continue
        if img is None:
            scored.append({"item": x, "ok": False, **(meta or {})})
            continue
        try:
            gray = to_grayscale_array(img)
            var = laplacian_variance(gray)
        except Exception as e:  # noqa: BLE001
            scored.append({"item": x, "ok": False, "error": f"laplacian_failed: {e}"})
            continue
        rec = {"item": x, "variance": round(var, 2),
               "is_blurry": var < min_var,
               "engine": "cv2_Laplacian" if _HAS_CV2 else "numpy_Laplacian"}
        if mode == "filter":
            if var >= min_var:
                rec["passed"] = True
            else:
                rec["passed"] = False
        scored.append(rec)
    if mode == "filter":
        return [s for s in scored if s.get("passed", True)]
    return scored