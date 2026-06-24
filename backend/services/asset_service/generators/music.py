"""P4-5-W1: Music Generator — 3 music models.

Models:
  * **Suno v4**          → openai-compatible (suno-api)
  * **Udio v1.5**        → openai-compatible
  * **阿里通义音乐**       → volcengine / openai-compatible

Input features:
  * **Style** (genre tags: cinematic, lo-fi, epic, electronic, …)
  * **Mood** (mood tags: melancholic, joyful, tense, calm, …)
  * **Tempo** (BPM, optional)
  * **Duration** (seconds, optional)
  * **Reference snippet** (existing audio to riff on — Suno extend, Udio remix)
  * **Lyrics** (optional)

Output:
  * music_url + metadata (bpm, key, mood, lyric line counts)
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


MUSIC_MODELS: Dict[str, Dict[str, str]] = {
    "suno": {"provider_id": "openai-compatible", "protocol": "openai-compatible",
             "model": "suno-v4", "label": "Suno v4"},
    "udio": {"provider_id": "openai-compatible", "protocol": "openai-compatible",
             "model": "udio-v1.5", "label": "Udio v1.5"},
    "tongyi-music": {"provider_id": "volcengine", "protocol": "volcengine",
                     "model": "tongyi-music-v1", "label": "阿里通义音乐 v1"},
}

DEFAULT_MODEL = "suno"

# Tempo / duration bounds
MIN_BPM, MAX_BPM = 30, 240
MIN_DURATION, MAX_DURATION = 5, 600
DEFAULT_DURATION = 60

# Genre whitelist (curated to avoid prompt-injection / sensitive words)
_ALLOWED_GENRES = frozenset({
    "cinematic", "lo-fi", "epic", "electronic", "ambient", "classical",
    "rock", "pop", "jazz", "blues", "folk", "country", "hip-hop", "r&b",
    "orchestral", "chinese-traditional", "guzheng", "erhu", "pipa",
    "synthwave", "house", "techno", "drum-and-bass", "trap",
    "documentary", "children", "comedy", "romance", "thriller", "horror",
    "anime", "game-ost", "corporate", "advertising", "wedding",
})

_ALLOWED_MOODS = frozenset({
    "melancholic", "joyful", "tense", "calm", "epic", "romantic",
    "mysterious", "uplifting", "dark", "playful", "triumphant",
    "nostalgic", "dreamy", "aggressive", "peaceful", "energetic",
})


@dataclass
class MusicGenerateRequest:
    style: str = "cinematic"
    mood: str = "calm"
    tempo_bpm: Optional[int] = None
    duration_seconds: int = DEFAULT_DURATION
    reference_audio_url: Optional[str] = None
    lyrics: Optional[str] = None
    instrumental: bool = True
    title: Optional[str] = None
    model: str = DEFAULT_MODEL
    provider_id: Optional[str] = None
    mock: bool = True
    user_id: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "MusicGenerateRequest":
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        style = str(payload.get("style") or "cinematic").strip().lower()
        if style not in _ALLOWED_GENRES:
            raise ValueError(f"unsupported style: {style!r}; allowed={sorted(_ALLOWED_GENRES)}")
        mood = str(payload.get("mood") or "calm").strip().lower()
        if mood not in _ALLOWED_MOODS:
            raise ValueError(f"unsupported mood: {mood!r}; allowed={sorted(_ALLOWED_MOODS)}")
        bpm = payload.get("tempo_bpm")
        if bpm is not None:
            bpm = int(bpm)
            if bpm < MIN_BPM or bpm > MAX_BPM:
                raise ValueError(f"tempo_bpm must be {MIN_BPM}-{MAX_BPM}")
        duration = int(payload.get("duration_seconds") or DEFAULT_DURATION)
        duration = max(MIN_DURATION, min(MAX_DURATION, duration))
        lyrics = payload.get("lyrics")
        if lyrics is not None:
            lyrics = str(lyrics)
            if len(lyrics) > 8000:
                raise ValueError("lyrics must be <= 8000 chars")
        return cls(
            style=style,
            mood=mood,
            tempo_bpm=bpm,
            duration_seconds=duration,
            reference_audio_url=payload.get("reference_audio_url"),
            lyrics=lyrics,
            instrumental=bool(payload.get("instrumental", not bool(lyrics))),
            title=(str(payload.get("title"))[:200] if payload.get("title") else None),
            model=str(payload.get("model") or DEFAULT_MODEL),
            provider_id=payload.get("provider_id"),
            mock=bool(payload.get("mock", True)),
            user_id=payload.get("user_id"),
        )


@dataclass
class MusicMetadata:
    bpm: Optional[int]
    key: Optional[str]
    duration_seconds: int
    mood: str
    style: str
    lyric_lines: int = 0
    instrumental: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MusicGenerateResponse:
    music_id: str
    music_url: str
    metadata: MusicMetadata
    model: str
    provider_id: str
    mock: bool
    elapsed_ms: int
    cost_usd: float
    title: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════════
# Music theory helpers — derive key + bpm hints from style/mood
# ═══════════════════════════════════════════════════════════════════════════════

_MUSIC_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_BPM_BY_STYLE = {
    "lo-fi": (70, 90), "ambient": (60, 80), "classical": (60, 120),
    "jazz": (80, 160), "blues": (60, 120), "hip-hop": (70, 100),
    "trap": (130, 160), "house": (118, 130), "techno": (120, 140),
    "drum-and-bass": (160, 180), "rock": (100, 140), "pop": (100, 130),
    "electronic": (120, 140), "cinematic": (60, 100), "epic": (80, 120),
    "orchestral": (60, 120), "synthwave": (90, 120), "folk": (80, 130),
    "country": (80, 130), "r&b": (60, 100),
}


def _derive_bpm(style: str, explicit: Optional[int]) -> int:
    if explicit is not None:
        return explicit
    lo, hi = _BPM_BY_STYLE.get(style, (90, 120))
    return (lo + hi) // 2


def _derive_key(mood: str) -> str:
    """Naive mood→key heuristic. Real impl would query music21 / librosa."""
    minor_moods = {"melancholic", "tense", "dark", "mysterious", "peaceful"}
    major_moods = {"joyful", "uplifting", "triumphant", "playful", "energetic"}
    quality = "minor" if mood in minor_moods else "major"
    idx = (sum(ord(c) for c in mood) % len(_MUSIC_KEYS))
    return f"{_MUSIC_KEYS[idx]} {quality}"


# ═══════════════════════════════════════════════════════════════════════════════
# Generator
# ═══════════════════════════════════════════════════════════════════════════════

class MusicGenerator:
    """Multi-model music generator."""

    def __init__(self, *, default_mock: bool = True) -> None:
        self.default_mock = default_mock

    def list_models(self) -> List[Dict[str, str]]:
        return [{"name": name, **meta} for name, meta in MUSIC_MODELS.items()]

    def resolve_model(self, model: str) -> Dict[str, str]:
        meta = MUSIC_MODELS.get(model)
        if not meta:
            meta = MUSIC_MODELS[DEFAULT_MODEL]
            return {"name": DEFAULT_MODEL, **meta, "fallback_from": model}
        return {"name": model, **meta}

    def generate(self, req: MusicGenerateRequest) -> MusicGenerateResponse:
        start = time.time()
        resolved = self.resolve_model(req.model)
        provider_id = req.provider_id or resolved["provider_id"]

        bpm = _derive_bpm(req.style, req.tempo_bpm)
        key = _derive_key(req.mood)
        lyric_lines = len([ln for ln in (req.lyrics or "").splitlines() if ln.strip()])

        meta = MusicMetadata(
            bpm=bpm,
            key=key,
            duration_seconds=req.duration_seconds,
            mood=req.mood,
            style=req.style,
            lyric_lines=lyric_lines,
            instrumental=req.instrumental,
        )

        cost_usd = 0.0
        use_mock = req.mock or self.default_mock
        music_url = ""
        if not use_mock:
            try:
                import asyncio
                from imdf.engines.provider_registry import call_provider_smart, _get_provider_config
                try:
                    provider_cfg = _get_provider_config(provider_id)
                except Exception:
                    provider_cfg = {
                        "id": provider_id, "protocol": resolved["protocol"],
                        "apiKey": "", "chatModels": [resolved["model"]],
                    }
                payload = {
                    "model": resolved["model"],
                    "style": req.style,
                    "mood": req.mood,
                    "bpm": bpm,
                    "duration": req.duration_seconds,
                    "instrumental": req.instrumental,
                    "lyrics": req.lyrics,
                    "reference_audio_url": req.reference_audio_url,
                    "title": req.title,
                }
                result = asyncio.run(call_provider_smart(
                    provider_cfg, payload, kind="chat",
                    user_id=req.user_id or "anonymous",
                ))
                cost_usd = float(result.get("cost_usd") or 0.0)
                music_url = (result.get("data") or {}).get("music_url") or ""
            except Exception as e:  # pragma: no cover
                logger.warning("music generate failed (%s); mock fallback", e)

        music_id = uuid.uuid4().hex[:12]
        if not music_url:
            music_url = (
                f"https://via.placeholder.com/audio.mp3"
                f"?text=mock+music+{req.model}+style={req.style}+mood={req.mood}"
                f"+id={music_id}"
            )

        elapsed = int((time.time() - start) * 1000)
        return MusicGenerateResponse(
            music_id=music_id,
            music_url=music_url,
            metadata=meta,
            model=req.model,
            provider_id=provider_id,
            mock=bool(use_mock),
            elapsed_ms=elapsed,
            cost_usd=cost_usd,
            title=req.title,
        )


__all__ = [
    "MUSIC_MODELS",
    "DEFAULT_MODEL",
    "MusicGenerateRequest",
    "MusicGenerateResponse",
    "MusicMetadata",
    "MusicGenerator",
]
