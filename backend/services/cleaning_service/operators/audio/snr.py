"""clean.audio.snr — Signal-to-Noise ratio estimate.

Uses the lower 10th-percentile energy window as noise floor; median energy
window as signal. Returns SNR in dB.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .._audio_utils import _HAS_LIBROSA, _HAS_NUMPY, _HAS_SF, get_meta, load_audio


def _snr_db(y: "np.ndarray", frame_len: int = 2048) -> float:
    import numpy as np
    if len(y) < frame_len:
        return 0.0
    n_frames = len(y) // frame_len
    if n_frames < 2:
        return 0.0
    energies = np.array([
        float(np.mean(y[i * frame_len:(i + 1) * frame_len] ** 2))
        for i in range(n_frames)
    ])
    energies = np.maximum(energies, 1e-12)
    db = 10.0 * np.log10(energies)
    noise_floor = float(np.percentile(db, 10))
    signal = float(np.median(db))
    return round(signal - noise_floor, 2)


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return per-item SNR (dB); drop items below min_snr_db.

    params:
        min_snr_db: float = 10.0
        mode: str = "score"
    """
    threshold = float(params.get("min_snr_db", 10.0))
    mode = str(params.get("mode", "score"))
    if not _HAS_NUMPY or (not _HAS_LIBROSA and not _HAS_SF):
        return [{"item": x, "snr_db": 0.0,
                 "note": "audio libs unavailable"} for x in items]
    out: List[Dict[str, Any]] = []
    for x in items:
        if not isinstance(x, str):
            out.append({"item": x, "snr_db": 0.0, "note": "not a file path"})
            continue
        try:
            y, _ = load_audio(x, sr=None, mono=True)
            snr = _snr_db(y)
        except Exception as e:  # noqa: BLE001
            out.append({"item": x, "error": f"snr_failed: {e}"})
            continue
        rec = {"item": x, "snr_db": snr, "is_noisy": snr < threshold}
        if mode == "filter":
            rec["passed"] = snr >= threshold
        out.append(rec)
    if mode == "filter":
        return [r for r in out if r.get("passed", True)]
    return out