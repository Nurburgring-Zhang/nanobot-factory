"""eval.audio_quality — Audio quality assessment (heuristic).

Inputs: items are dicts with optional raw audio metrics (since we don't
ship a full audio decoder here):
    {sample_rate, channels, duration, samples?, rms?, peak?, snr_db?}

Or raw bytes (wav) — we parse the WAV header only.

Metrics:
  - sr_score: deviation from target_sr
  - snr_score: clip((snr_db - 10) / 30, 0, 1)
  - clipping: ratio of samples near max amplitude (>0.99)
  - silence_ratio: ratio of frames with rms < 0.01
  - dynamic_range: peak / max(rms, 1e-6) in dB
  - composite: weighted mean
"""
from __future__ import annotations

import io
import math
import struct
import wave
from typing import Any, Dict, List


def _parse_wav(data: bytes) -> Dict[str, Any]:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            return {
                "sample_rate": w.getframerate(),
                "channels": w.getnchannels(),
                "sample_width": w.getsampwidth(),
                "frames": w.getnframes(),
                "duration": w.getnframes() / max(1, w.getframerate()),
            }
    except Exception:  # noqa: BLE001
        return {}


def _score_one(item: Any) -> Dict[str, Any]:
    sr = ch = duration = snr_db = None
    rms = peak = clipping_ratio = silence_ratio = dyn_db = None
    if isinstance(item, (bytes, bytearray)):
        info = _parse_wav(item)
        sr = info.get("sample_rate")
        ch = info.get("channels")
        duration = info.get("duration")
    elif isinstance(item, dict):
        sr = item.get("sample_rate")
        ch = item.get("channels")
        duration = item.get("duration")
        snr_db = item.get("snr_db")
        rms = item.get("rms")
        peak = item.get("peak")
        clipping_ratio = item.get("clipping_ratio")
        silence_ratio = item.get("silence_ratio")
        dyn_db = item.get("dynamic_range_db")
    target_sr = 16000
    sr_score = 0.0
    if sr:
        dev = abs(sr - target_sr) / target_sr
        sr_score = max(0.0, 1.0 - dev)
    snr_score = 0.0
    if snr_db is not None:
        snr_score = max(0.0, min(1.0, (snr_db - 10) / 30.0))
    clip_pen = 1.0
    if clipping_ratio is not None:
        clip_pen = max(0.0, 1.0 - clipping_ratio * 5.0)
    sil_pen = 1.0
    if silence_ratio is not None:
        sil_pen = max(0.0, 1.0 - max(0.0, silence_ratio - 0.5) * 2.0)
    dyn_score = 0.5
    if dyn_db is not None:
        # ideal 20-40 dB
        if 20 <= dyn_db <= 40:
            dyn_score = 1.0
        else:
            dyn_score = max(0.0, 1.0 - abs(dyn_db - 30) / 50.0)
    present = [v for v in (sr_score, snr_score, clip_pen, sil_pen, dyn_score) if v is not None]
    composite = sum(present) / max(1, len(present)) if present else 0.0
    return {
        "sample_rate": sr,
        "channels": ch,
        "duration": duration,
        "snr_db": snr_db,
        "rms": rms,
        "peak": peak,
        "clipping_ratio": clipping_ratio,
        "silence_ratio": silence_ratio,
        "dynamic_range_db": dyn_db,
        "scores": {
            "sr": round(sr_score, 3),
            "snr": round(snr_score, 3),
            "clip_penalty": round(clip_pen, 3),
            "silence_penalty": round(sil_pen, 3),
            "dynamic_range": round(dyn_score, 3),
        },
        "composite": round(composite, 3),
    }


def run(items: List[Any], params: Dict[str, Any]) -> List[Dict[str, Any]]:
    mode = params.get("mode", "score")
    threshold = float(params.get("threshold", 0.5))
    out: List[Dict[str, Any]] = []
    composites: List[float] = []
    for i, it in enumerate(items):
        s = _score_one(it)
        composites.append(s["composite"])
        out.append({"sample_id": i, "audio_quality": s,
                    "above_threshold": s["composite"] >= threshold})
    if mode == "filter":
        out = [o for o in out if o.get("above_threshold")]
    elif mode == "aggregate":
        out = [{
            "count": len(composites),
            "composite_mean": round(sum(composites) / max(1, len(composites)), 3),
        }]
    return out


__all__ = ["run"]
