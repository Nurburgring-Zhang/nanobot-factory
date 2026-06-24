"""clean.image.resolution — filter images by min/max width & height."""
from __future__ import annotations

from typing import Any, Dict, List

from .._image_utils import _load_image


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Keep images with width in [min_w, max_w] AND height in [min_h, max_h].

    params:
        min_w: int = 256
        max_w: int = 8192
        min_h: int = 256
        max_h: int = 8192
        drop_missing: bool = False (treat unreadable as failure vs. keep)
    """
    min_w = int(params.get("min_w", 256))
    max_w = int(params.get("max_w", 8192))
    min_h = int(params.get("min_h", 256))
    max_h = int(params.get("max_h", 8192))
    drop_missing = bool(params.get("drop_missing", False))

    kept = []
    for x in items:
        try:
            img, meta = _load_image(x)
        except Exception as e:  # noqa: BLE001
            if not drop_missing:
                kept.append(x)
            continue
        if img is None:
            if not drop_missing and not meta.get("missing"):
                kept.append(x)
            continue
        w, h = img.width, img.height
        if min_w <= w <= max_w and min_h <= h <= max_h:
            kept.append(x)
    return kept