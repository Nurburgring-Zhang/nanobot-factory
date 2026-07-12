"""label_asr_transcribe — ASR (speech-to-text) transcription.

Transcribes an audio file (URL or local path) into text. Returns segments
with start/end timestamps when timestamps=True.

Inputs:
    audio:      str  — URL or local path
    lang:       str  — language hint, default "en"
    timestamps: bool — include per-segment timing

Outputs:
    text:       str
    segments:   list — {text, start, end, confidence}
    lang:       str
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from backend.skills import SkillInput, SkillOutput

from ._base import (
    NETWORK_OK,
    build_output,
    clamp,
    now_iso,
    post_json,
    require_non_empty,
    stable_seed,
)


class AsrTranscribeInput(BaseModel):
    audio: str = Field(...)
    lang: str = Field(default="en")
    timestamps: bool = Field(default=True)
    model: str = Field(default="whisper-large-v3")


_MOCK_SCRIPT = {
    "en": [
        "Hello and welcome to the show.",
        "Today we will talk about machine learning.",
        "Please subscribe to our channel for more.",
    ],
    "zh": [
        "欢迎收听本期节目。",
        "今天我们来聊一聊机器学习。",
        "请订阅我们的频道以获取更多内容。",
    ],
    "ja": [
        "番組へようこそ。",
        "今日は機械学習について話します。",
        "詳しくはチャンネル登録してください。",
    ],
}


async def label_asr_transcribe(input: SkillInput) -> SkillOutput:
    t0 = time.perf_counter()
    try:
        payload = AsrTranscribeInput.model_validate(input.params or {})
        require_non_empty(payload.audio, "audio")
    except Exception as exc:
        return build_output(success=False, error=f"invalid input: {exc}", source="label")

    live = None
    if NETWORK_OK and payload.audio.startswith(("http://", "https://")):
        live = await post_json(
            "https://api.asr.example/transcribe",
            payload.model_dump(), timeout=10.0,
        )

    if live and isinstance(live, dict) and live.get("segments"):
        segments = [
            {
                "text": str(s.get("text", "")),
                "start": float(s.get("start", 0.0)),
                "end": float(s.get("end", 0.0)),
                "confidence": clamp(float(s.get("confidence", 0.0))),
            }
            for s in live["segments"]
        ]
        text = " ".join(s["text"] for s in segments).strip()
        return build_output(
            success=True,
            result={"text": text, "segments": segments, "lang": payload.lang,
                    "model": payload.model, "timestamp": now_iso()},
            source="live", confidence=0.9,
            elapsed_ms=(time.perf_counter() - t0) * 1000,
        )

    # Offline mock — fixed script timed at ~2s/segment with 0.2s gaps.
    seed = stable_seed(payload.audio, payload.lang)
    script = _MOCK_SCRIPT.get(payload.lang, _MOCK_SCRIPT["en"])
    n = (seed % 2) + 2  # 2..3 segments
    segments: List[Dict[str, Any]] = []
    for i in range(n):
        s = (seed >> (i * 4)) & 0xFFFF
        text = script[s % len(script)]
        start = float(i * 2.0)
        end = start + 1.7  # < 2.0s so next segment's start is strictly greater
        segments.append({
            "text": text, "start": round(start, 2), "end": round(end, 2),
            "confidence": round(clamp(0.85 + ((s >> 4) % 150) / 1000.0), 4),
        })
    full = " ".join(seg["text"] for seg in segments)
    out_segments = segments if payload.timestamps else []
    return build_output(
        success=True,
        result={"text": full, "segments": out_segments, "lang": payload.lang,
                "model": payload.model, "timestamp": now_iso()},
        source="mock", confidence=0.8,
        elapsed_ms=(time.perf_counter() - t0) * 1000,
    )


__all__ = ["label_asr_transcribe", "AsrTranscribeInput"]