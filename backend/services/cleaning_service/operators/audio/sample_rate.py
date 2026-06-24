"""clean.audio.sample_rate — filter audio by sample rate; report mismatch."""
from __future__ import annotations

from typing import Any, Dict, List

from .._audio_utils import _HAS_LIBROSA, _HAS_SF, get_meta


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return per-item sample_rate; optionally filter to target_sr.

    params:
        target_sr: int = 16000
        tolerance_pct: float = 0.05
        mode: str = "score"
    """
    target = int(params.get("target_sr", 16000))
    tol = float(params.get("tolerance_pct", 0.05))
    mode = str(params.get("mode", "score"))
    if not (_HAS_LIBROSA or _HAS_SF):
        return [{"item": x, "sample_rate": 0,
                 "note": "audio libs unavailable"} for x in items]
    out: List[Dict[str, Any]] = []
    for x in items:
        meta = get_meta(x)
        sr = meta.get("sample_rate")
        if sr is None:
            out.append({"item": x, "error": "metadata_unavailable"})
            continue
        sr = int(sr)
        ratio = abs(sr - target) / max(1, target)
        rec = {"item": x, "sample_rate": sr, "target_sr": target,
               "delta_pct": round(ratio * 100.0, 2),
               "matches_target": ratio <= tol}
        if mode == "filter":
            rec["passed"] = ratio <= tol
        out.append(rec)
    if mode == "filter":
        return [r for r in out if r.get("passed", True)]
    return out