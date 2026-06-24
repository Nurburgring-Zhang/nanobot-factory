"""clean.image.compress_artifact — detect JPEG compression artifacts.

Heuristic: if image is JPEG with quality <= 60, and re-saved, edge energy
spreads across the 8x8 DCT blocks (high-freq noise ratio).
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._image_utils import _HAS_NUMPY, _HAS_PIL, _load_image


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return per-item blockiness score (0-1); drop items with score > threshold.

    params:
        threshold: float = 0.45  (blockiness score to flag as 'heavy artifacts')
        mode: str = "score"
    """
    threshold = float(params.get("threshold", 0.45))
    mode = str(params.get("mode", "score"))
    if not _HAS_NUMPY or not _HAS_PIL:
        return [{"item": x, "blockiness": 0.0, "note": "deps unavailable"} for x in items]
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
            gray = np.asarray(img.convert("L").resize((256, 256)), dtype=np.float32)
            # Measure blockiness: difference at 8-pixel boundaries vs interior
            h_diff = np.abs(gray[:, 8:] - gray[:, :-8])
            interior = np.abs(gray[:, 8:-8] - gray[:, 9:-7]) if gray.shape[1] > 17 else h_diff
            block_energy = float(h_diff[:, ::8].mean())
            interior_energy = float(interior.mean()) + 1e-6
            blockiness = min(1.0, block_energy / interior_energy / 5.0)
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"blockiness_failed: {e}"})
            continue
        rec = {"item": x, "blockiness": round(blockiness, 4),
               "is_artifacted": blockiness > threshold}
        if mode == "filter":
            rec["passed"] = blockiness <= threshold
        out.append(rec)
    if mode == "filter":
        return [r for r in out if r.get("passed", True)]
    return out