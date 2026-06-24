"""clean.audio.duration — filter audio by duration."""
from __future__ import annotations

from typing import Any, Dict, List

from .._audio_utils import _HAS_LIBROSA, _HAS_SF, get_meta


def run(items: List[Any], params: Dict[str, Any]) -> List[Any]:
    """Keep items whose duration is within [min_s, max_s].

    params:
        min_seconds: float = 0.5
        max_seconds: float = 3600.0
    """
    if not (_HAS_LIBROSA or _HAS_SF):
        return items
    lo = float(params.get("min_seconds", 0.5))
    hi = float(params.get("max_seconds", 3600.0))
    out = []
    for x in items:
        meta = get_meta(x)
        d = meta.get("duration")
        if d is None:
            continue
        if lo <= float(d) <= hi:
            out.append(x)
    return out