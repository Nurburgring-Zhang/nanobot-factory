"""clean.image.aspect_ratio — filter images by aspect-ratio range."""
from __future__ import annotations

from typing import Any, Dict, List

from .._image_utils import _load_image


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Keep images whose W/H aspect ratio is within [min_ratio, max_ratio].

    params:
        min_ratio: float = 0.5   # 1:2 portrait
        max_ratio: float = 2.0   # 2:1 landscape
    """
    lo = float(params.get("min_ratio", 0.5))
    hi = float(params.get("max_ratio", 2.0))

    kept = []
    for x in items:
        try:
            img, _ = _load_image(x)
        except Exception:  # noqa: BLE001
            continue
        if img is None or img.height == 0:
            continue
        r = img.width / img.height
        if lo <= r <= hi:
            kept.append(x)
    return kept