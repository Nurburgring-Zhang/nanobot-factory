"""clean.image.nsfw — skin-tone heuristic NSFW detector.

Loose but cheap (no ML model). Returns flag + skin ratio; production should
replace with a dedicated NSFW classifier (e.g. CLIP-based or in-house CNN).
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._image_utils import _HAS_NUMPY, _load_image, skin_tone_ratio


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flag items where skin_ratio >= threshold.

    params:
        threshold: float = 0.35  (skin pixel ratio to flag as suspicious)
    """
    threshold = float(params.get("threshold", 0.35))
    if not _HAS_NUMPY:
        return [{"item": x, "is_nsfw": False, "note": "numpy unavailable"} for x in items]

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
            ratio = skin_tone_ratio(img)
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"skin_ratio_failed: {e}"})
            continue
        out.append({
            "item": x,
            "skin_ratio": round(ratio, 4),
            "is_nsfw": ratio >= threshold,
            "model": "YCbCr-heuristic",
        })
    return out