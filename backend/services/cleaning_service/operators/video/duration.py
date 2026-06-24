"""clean.video.duration — filter videos by duration range."""
from __future__ import annotations

from typing import Any, Dict, List

from .._video_utils import _HAS_CV2, get_metadata


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Keep videos whose duration is within [min_s, max_s].

    params:
        min_seconds: float = 1.0
        max_seconds: float = 600.0
    """
    lo = float(params.get("min_seconds", 1.0))
    hi = float(params.get("max_seconds", 600.0))
    if not _HAS_CV2:
        return items
    kept = []
    for x in items:
        meta = get_metadata(x)
        if not meta:
            continue
        d = meta.get("duration", 0.0)
        if lo <= d <= hi:
            kept.append(x)
    return kept