"""clean.audio.silence — drop/trim silent audio."""
from __future__ import annotations

from typing import Any, Dict, List

from .._audio_utils import _HAS_LIBROSA, _HAS_NUMPY, _HAS_SF, get_meta, load_audio


def _silence_ratio(y: "np.ndarray", thresh_db: float = -40.0) -> float:
    import numpy as np
    if len(y) == 0:
        return 1.0
    eps = 1e-12
    db = 20.0 * np.log10(np.maximum(np.abs(y), eps))
    return float((db < thresh_db).mean())


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return per-item silence_ratio; drop items above max_silence_ratio.

    params:
        max_silence_ratio: float = 0.6
        silence_db: float = -40.0
        mode: str = "score"
    """
    max_silence = float(params.get("max_silence_ratio", 0.6))
    silence_db = float(params.get("silence_db", -40.0))
    mode = str(params.get("mode", "score"))
    if not _HAS_NUMPY or (not _HAS_LIBROSA and not _HAS_SF):
        return [{"item": x, "silence_ratio": 0.0,
                 "note": "audio libs unavailable"} for x in items]
    out: List[Dict[str, Any]] = []
    for x in items:
        if not isinstance(x, str):
            out.append({"item": x, "silence_ratio": 0.0, "note": "not a file path"})
            continue
        try:
            y, _ = load_audio(x, sr=None, mono=True)
            ratio = _silence_ratio(y, thresh_db=silence_db)
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"silence_failed: {e}"})
            continue
        rec = {"item": x, "silence_ratio": round(ratio, 4),
               "is_silent": ratio >= max_silence,
               "silence_db": silence_db}
        if mode == "filter":
            rec["passed"] = ratio < max_silence
        out.append(rec)
    if mode == "filter":
        return [r for r in out if r.get("passed", True)]
    return out