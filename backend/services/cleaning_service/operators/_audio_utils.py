"""Shared audio utility helpers."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:  # noqa: BLE001
    _HAS_NUMPY = False

try:
    import soundfile as sf
    _HAS_SF = True
except Exception:  # noqa: BLE001
    _HAS_SF = False

try:
    import librosa
    _HAS_LIBROSA = True
except Exception:  # noqa: BLE001
    _HAS_LIBROSA = False


def capabilities() -> Dict[str, bool]:
    return {"numpy": _HAS_NUMPY, "soundfile": _HAS_SF, "librosa": _HAS_LIBROSA}


def load_audio(path: str, sr: Optional[int] = None, mono: bool = True) -> Tuple[Any, int]:
    """Load an audio file with librosa (preferred) or soundfile (fallback).

    Returns (y, sr). Raises if neither available or file missing.
    """
    if not isinstance(path, str) or not os.path.exists(path):
        raise FileNotFoundError(path)
    if _HAS_LIBROSA:
        y, srr = librosa.load(path, sr=sr, mono=mono)
        return y, srr
    if _HAS_SF:
        y, srr = sf.read(path, dtype="float32", always_2d=not mono)
        if mono and y.ndim > 1:
            y = y.mean(axis=1)
        if sr is not None and srr != sr:
            # Lightweight resample fallback: just return original; caller can detect
            pass
        return y, srr
    raise RuntimeError("no audio library (librosa / soundfile) available")


def metadata(path: str) -> Dict[str, Any]:
    if _HAS_SF:
        try:
            info = sf.info(path)
            return {
                "path": path,
                "duration": float(info.duration),
                "sample_rate": int(info.samplerate),
                "channels": int(info.channels),
                "frames": int(info.frames),
            }
        except Exception as e:  # noqa: BLE001
            return {"path": path, "error": str(e)}
    if _HAS_LIBROSA:
        try:
            y, sr = librosa.load(path, sr=None, mono=False)
            dur = librosa.get_duration(y=y, sr=sr)
            ch = 1 if y.ndim == 1 else y.shape[0]
            return {"path": path, "duration": float(dur),
                    "sample_rate": int(sr), "channels": int(ch),
                    "frames": int(y.shape[-1])}
        except Exception as e:  # noqa: BLE001
            return {"path": path, "error": str(e)}
    return {"path": path, "error": "no audio library"}


def get_meta(item: Any) -> Dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    if isinstance(item, str):
        return metadata(item)
    return {}