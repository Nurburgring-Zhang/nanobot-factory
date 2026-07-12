"""clean_audio_denoise — Audio denoising.

Uploads audio to a denoise service when reachable, otherwise emits a
deterministic mock + statistics.  Returns metadata: in/out file refs,
SNR estimate.

Skill function: ``clean_audio_denoise(input) -> SkillOutput``.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata, safe_httpx_call


SKILL_ID = "skill_clean_audio_denoise"


class AudioDenoiseInput(BaseModel):
    audio_url: str = Field(..., description="Audio URL or local path")
    strength: float = Field(0.6, ge=0.0, le=1.0)
    sample_rate: int = Field(16000, description="Target sample rate")


class AudioDenoiseOutput(BaseModel):
    output_url: str = ""
    snr_in: float = 0.0
    snr_out: float = 0.0
    duration_seconds: float = 0.0
    offline: bool = False


def _mock_stats(url: str) -> Dict[str, float]:
    h = hashlib.md5(url.encode("utf-8")).digest()
    snr_in = 8 + (h[0] / 255.0) * 6
    duration = (h[1] / 255.0) * 30
    return {"snr_in": round(snr_in, 2),
            "snr_out": round(snr_in + 6 + (h[2] / 255.0) * 3, 2),
            "duration": round(duration, 2)}


async def clean_audio_denoise(input: SkillInput) -> SkillOutput:
    payload = AudioDenoiseInput(**(input.params or {}))

    remote = await safe_httpx_call(
        "https://example.invalid/api/v1/clean/audio/denoise",
        payload=payload.model_dump(),
        mock={"output_url": "", **_mock_stats(payload.audio_url)},
    )
    if remote["status"] == "ok" and remote["data"].get("output_url"):
        data = remote["data"]
        offline = False
    else:
        data = {"output_url": "", **_mock_stats(payload.audio_url)}
        offline = True

    out = AudioDenoiseOutput(
        output_url=data.get("output_url", "") or f"mock://{payload.audio_url}.denoised.wav",
        snr_in=float(data.get("snr_in", 0.0)),
        snr_out=float(data.get("snr_out", 0.0)),
        duration_seconds=float(data.get("duration", 0.0)),
        offline=offline,
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_audio_denoise", offline=offline),
    )


__all__ = ["AudioDenoiseInput", "AudioDenoiseOutput", "clean_audio_denoise"]
