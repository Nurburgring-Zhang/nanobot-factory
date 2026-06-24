"""clean.video.resolution — filter videos by min/max width & height."""
from __future__ import annotations

from typing import Any, Dict, List

from .._video_utils import _HAS_CV2, get_metadata


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Keep videos with width/height in [min_w..max_w, min_h..max_h].

    params:
        min_w: int = 320
        max_w: int = 7680
        min_h: int = 240
        max_h: int = 4320
    """
    min_w = int(params.get("min_w", 320))
    max_w = int(params.get("max_w", 7680))
    min_h = int(params.get("min_h", 240))
    max_h = int(params.get("max_h", 4320))
    if not _HAS_CV2:
        return items
    kept = []
    for x in items:
        meta = get_metadata(x)
        if not meta:
            continue
        w, h = meta.get("width", 0), meta.get("height", 0)
        if min_w <= w <= max_w and min_h <= h <= max_h:
            kept.append(x)
    return kept