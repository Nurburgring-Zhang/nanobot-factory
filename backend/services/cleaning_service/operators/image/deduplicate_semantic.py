"""clean.image.deduplicate.semantic — semantic-style near-duplicate via color histogram.

Real CLIP embedding is ideal but expensive; we approximate with a compact
RGB histogram (64 dims) so this works without a GPU/ML stack installed.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._image_utils import _HAS_NUMPY, _load_image, color_histogram_features, cosine_distance


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Drop near-duplicates by histogram cosine distance < (1 - threshold).

    params:
        threshold: float = 0.92  (similarity ≥ 0.92 → drop)
    """
    threshold = float(params.get("threshold", 0.92))
    if not _HAS_NUMPY:
        return items

    feats: List[Any] = []
    out: List[Any] = []
    for x in items:
        try:
            img, _ = _load_image(x)
        except Exception:  # noqa: BLE001
            continue
        if img is None:
            continue
        try:
            f = color_histogram_features(img)
        except Exception:  # noqa: BLE001
            continue
        is_dup = False
        for prev in feats:
            if (1.0 - cosine_distance(f, prev)) >= threshold:
                is_dup = True
                break
        if not is_dup:
            feats.append(f)
            out.append(x)
    return out