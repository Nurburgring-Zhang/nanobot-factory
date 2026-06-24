"""audio_wav — 音频 WAV 导出器 (manifest + metadata, 无音频时不写 wav).

op_id: export.audio_wav
"""
from __future__ import annotations

import hashlib
import json
import os
import wave
from typing import Any, Dict

OP_ID = "export.audio_wav"
NAME = "音频 WAV 导出"
CATEGORY = "audio"
DESCRIPTION = "导出 audio dataset 到 WAV (单声道/立体声, 默认 16kHz) + JSON manifest"
PARAMS: list = [
    {"name": "dir", "type": "str", "default": "", "required": True,
     "description": "Output directory"},
    {"name": "sample_rate", "type": "int", "default": 16000, "required": False},
    {"name": "channels", "type": "int", "default": 1, "required": False},
    {"name": "audio_field", "type": "str", "default": "audio", "required": False},
    {"name": "samples_field", "type": "str", "default": "samples", "required": False,
     "description": "Field containing raw int16 samples (optional)"},
]


def _probe_with_wave(audio_path: str) -> Dict[str, Any]:
    try:
        with wave.open(audio_path, "rb") as w:
            return {
                "ok": True,
                "channels": w.getnchannels(),
                "sample_rate": w.getframerate(),
                "sample_width": w.getsampwidth(),
                "frame_count": w.getnframes(),
                "duration_sec": round(w.getnframes() / max(1, w.getframerate()), 3),
            }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _mock_probe(audio_path: str) -> Dict[str, Any]:
    h = int(hashlib.md5(audio_path.encode("utf-8", errors="ignore")).hexdigest()[:8], 16)
    duration = 1.0 + (h % 30) / 10.0  # 1.0 - 4.0 sec
    return {
        "ok": True,
        "mode": "mock",
        "channels": 1,
        "sample_rate": 16000,
        "sample_width": 2,
        "frame_count": int(16000 * duration),
        "duration_sec": round(duration, 3),
    }


def run(data: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    base = str(params.get("dir", "")).strip()
    if not base:
        return {"ok": False, "error": "missing_dir"}
    sr = int(params.get("sample_rate", 16000))
    ch = int(params.get("channels", 1))
    audio_field = str(params.get("audio_field", "audio"))
    samples_field = str(params.get("samples_field", "samples"))
    os.makedirs(base, exist_ok=True)
    items = list(data) if isinstance(data, list) else [data]
    manifest = []
    written = 0
    for idx, x in enumerate(items):
        if isinstance(x, dict):
            audio_path = str(x.get(audio_field, x.get("path", "")))
            samples = x.get(samples_field)
        else:
            audio_path = str(x)
            samples = None
        out_name = f"audio_{idx:05d}.wav"
        out_path = os.path.join(base, out_name)
        if samples is not None and isinstance(samples, (list, tuple)):
            # Write provided samples
            try:
                with wave.open(out_path, "wb") as w:
                    w.setnchannels(ch)
                    w.setsampwidth(2)
                    w.setframerate(sr)
                    frames = bytearray()
                    for s in samples:
                        v = int(max(-32768, min(32767, int(s)))) & 0xFFFF
                        frames += v.to_bytes(2, "little", signed=False)
                    w.writeframes(bytes(frames))
                info = {"ok": True, "channels": ch, "sample_rate": sr,
                        "frame_count": len(samples),
                        "duration_sec": round(len(samples) / sr, 3)}
                written += 1
            except Exception as e:  # noqa: BLE001
                info = {"ok": False, "error": str(e)}
        elif audio_path and os.path.exists(audio_path):
            info = _probe_with_wave(audio_path)
        else:
            info = _mock_probe(audio_path)
        manifest.append({
            "index": idx,
            "source_audio": audio_path,
            "written_path": out_path if samples is not None else None,
            "info": info,
        })
    manifest_path = os.path.join(base, "audio_manifest.jsonl")
    with open(manifest_path, "w", encoding="utf-8") as fp:
        for rec in manifest:
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return {
        "ok": True,
        "format": "audio_wav",
        "dir": os.path.abspath(base),
        "manifest_path": os.path.abspath(manifest_path),
        "audio_count": len(manifest),
        "wav_written": written,
    }
