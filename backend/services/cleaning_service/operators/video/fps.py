"""clean.video.fps — filter videos by framerate."""
from __future__ import annotations

from typing import Any, Dict, List

from .._video_utils import _HAS_CV2, get_metadata


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Keep videos whose fps is within [min_fps, max_fps].

    params:
        min_fps: float = 15.0
        max_fps: float = 120.0
    """
    lo = float(params.get("min_fps", 15.0))
    hi = float(params.get("max_fps", 120.0))
    if not _HAS_CV2:
        return items
    kept = []
    for x in items:
        meta = get_metadata(x)
        if not meta:
            continue
        fps = meta.get("fps", 0.0)
        if lo <= fps <= hi:
            kept.append(x)
    return kept