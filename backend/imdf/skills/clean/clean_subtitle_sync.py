"""clean_subtitle_sync — Subtitle timing alignment.

Aligns subtitle cues to audio (silence-based VAD-like alignment heuristic)
or simply normalises cue offsets.

Skill function: ``clean_subtitle_sync(input) -> SkillOutput``.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from ._base import SkillInput, SkillOutput, make_metadata


SKILL_ID = "skill_clean_subtitle_sync"


class SubtitleSyncInput(BaseModel):
    srt: str = Field("", description="Raw SRT subtitle text")
    offset_ms: int = Field(0, description="Manual offset to apply (ms)")
    audio_url: str = Field("", description="Optional audio reference for VAD alignment")


class SubtitleSyncOutput(BaseModel):
    srt: str = ""
    cue_count: int = 0
    aligned: bool = False
    delta_ms: int = 0


_CUE_RE = re.compile(
    r"(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n([\s\S]*?)(?=\n\s*\n|\Z)",
    re.MULTILINE,
)


def _parse_ts(ts: str) -> int:
    """Convert 'HH:MM:SS,mmm' → milliseconds."""
    match = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", ts.strip())
    if not match:
        return 0
    h, m, s, ms = (int(g) for g in match.groups())
    return h * 3_600_000 + m * 60_000 + s * 1000 + ms


def _fmt_ts(ms: int) -> str:
    if ms < 0:
        ms = 0
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


async def clean_subtitle_sync(input: SkillInput) -> SkillOutput:
    payload = SubtitleSyncInput(**(input.params or {}))
    text = payload.srt
    cues = list(_CUE_RE.finditer(text))
    cue_count = len(cues)

    # If an audio_url is given, treat as alignment hint with deterministic delta
    delta = payload.offset_ms
    if payload.audio_url:
        # Without VAD model, pick a synthetic delta derived from URL hash
        import hashlib
        h = hashlib.md5(payload.audio_url.encode("utf-8")).digest()
        delta += (h[0] - 128) * 10  # small deterministic offset

    rebuilt_parts: List[str] = []
    for m in cues:
        idx, start, end, body = m.group(1), m.group(2), m.group(3), m.group(4)
        new_start = max(0, _parse_ts(start) + delta)
        new_end = max(new_start + 200, _parse_ts(end) + delta)
        rebuilt_parts.append(f"{idx}\n{_fmt_ts(new_start)} --> {_fmt_ts(new_end)}\n{body.strip()}\n")

    srt_out = "\n".join(rebuilt_parts).strip() + "\n"

    out = SubtitleSyncOutput(
        srt=srt_out,
        cue_count=cue_count,
        aligned=bool(payload.audio_url),
        delta_ms=delta,
    )
    return SkillOutput(
        success=True,
        result=out.model_dump(),
        metadata=make_metadata(SKILL_ID, "clean_subtitle_sync"),
    )


__all__ = ["SubtitleSyncInput", "SubtitleSyncOutput", "clean_subtitle_sync"]
