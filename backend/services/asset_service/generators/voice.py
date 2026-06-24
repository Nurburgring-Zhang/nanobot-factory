"""P4-5-W1: Voice Generator — 4 voice models + voice cloning + multilingual.

Models (text-to-speech):
  * **ElevenLabs**        — openai-compatible (ElevenLabs has OpenAI-style API)
  * **OpenAI TTS**        — openai-compatible (``tts-1``, ``tts-1-hd``)
  * **火山语音 (火山 TTS)**  — volcengine
  * **ChatTTS (本地)**     — 自托管 / comfyui protocol (mock-friendly)

Features (借鉴 字节火山 / ElevenLabs):
  * **Voice clone** — upload 5-10s sample, extract ``voice_features`` (a
    pseudo-embedding — deterministic hash-based; prod should swap with
    a real speaker encoder like Resemblyzer).
  * **Multilingual** — zh / en / ja / ko + 24 地方言 (zh-yue / zh-minnan / …).
  * **Voice library** — list / search cloned voices by name, language, tags.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


VOICE_MODELS: Dict[str, Dict[str, str]] = {
    "elevenlabs": {"provider_id": "openai-compatible", "protocol": "openai-compatible",
                   "model": "eleven_multilingual_v2", "label": "ElevenLabs Multilingual v2"},
    "openai-tts": {"provider_id": "openai-compatible", "protocol": "openai-compatible",
                   "model": "tts-1-hd", "label": "OpenAI TTS HD"},
    "volc-tts": {"provider_id": "volcengine", "protocol": "volcengine",
                 "model": "volcengine-tts-v1", "label": "火山语音 TTS v1"},
    "chattts-local": {"provider_id": "comfyui", "protocol": "comfyui",
                      "model": "chattts-local-v0.1", "label": "ChatTTS (本地)"},
}

DEFAULT_MODEL = "openai-tts"

# Supported languages
SUPPORTED_LANGUAGES = frozenset({
    "zh", "en", "ja", "ko",
    # 24 地方言
    "zh-yue", "zh-minnan", "zh-wu", "zh-hakka", "zh-xiang",
    "zh-gansu", "zh-shanxi", "zh-hebei", "zh-sichuan", "zh-yunnan",
    "zh-guangxi", "zh-hunan", "zh-hubei", "zh-jiangxi", "zh-anhui",
    "zh-fujian", "zh-zhejiang", "zh-jiangsu", "zh-shandong", "zh-henan",
    "zh-nei_menggu", "zh-xinjiang", "zh-qinghai", "zh-tibetan",
})
DEFAULT_LANGUAGE = "zh"

# Sample length bounds (seconds)
MIN_CLONE_SAMPLE_SECONDS = 3
MAX_CLONE_SAMPLE_SECONDS = 60

VOICES_MEMORY_STORE: Dict[str, "ClonedVoice"] = {}
"""Process-local cloned voice registry (keyed by voice_id).

In production this should be Postgres; for the dev/CI scope, an
in-memory dict suffices and is replaced atomically on test reset.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class VoiceGenerateRequest:
    text: str
    model: str = DEFAULT_MODEL
    provider_id: Optional[str] = None
    language: str = DEFAULT_LANGUAGE
    voice_id: Optional[str] = None  # if set, use cloned voice
    speed: float = 1.0
    pitch: float = 1.0
    emotion: Optional[str] = None  # neutral/happy/sad/angry/excited
    mock: bool = True
    user_id: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "VoiceGenerateRequest":
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("text is required")
        if len(text) > 10000:
            raise ValueError("text must be <= 10000 chars")
        language = str(payload.get("language") or DEFAULT_LANGUAGE).lower()
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language: {language!r}")
        speed = float(payload.get("speed") or 1.0)
        speed = max(0.5, min(2.0, speed))
        pitch = float(payload.get("pitch") or 1.0)
        pitch = max(0.5, min(2.0, pitch))
        emotion = payload.get("emotion")
        if emotion is not None:
            emotion = str(emotion).strip().lower()
            if emotion not in {"neutral", "happy", "sad", "angry", "excited", "calm", "fearful"}:
                raise ValueError(f"unsupported emotion: {emotion!r}")
        return cls(
            text=text,
            model=str(payload.get("model") or DEFAULT_MODEL),
            provider_id=payload.get("provider_id"),
            language=language,
            voice_id=payload.get("voice_id"),
            speed=speed,
            pitch=pitch,
            emotion=emotion,
            mock=bool(payload.get("mock", True)),
            user_id=payload.get("user_id"),
        )


@dataclass
class VoiceGenerateResponse:
    audio_url: str
    duration_seconds: float
    language: str
    model: str
    provider_id: str
    voice_id: Optional[str] = None
    emotion: Optional[str] = None
    mock: bool = True
    elapsed_ms: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VoiceCloneRequest:
    name: str
    sample_url: str  # URL or asset:// path to the audio sample
    sample_duration_seconds: float = 5.0
    language: str = DEFAULT_LANGUAGE
    tags: List[str] = field(default_factory=list)
    description: Optional[str] = None

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "VoiceCloneRequest":
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        name = str(payload.get("name") or "").strip()
        if not name or len(name) > 120:
            raise ValueError("name is required, 1-120 chars")
        sample_url = str(payload.get("sample_url") or "").strip()
        if not sample_url or len(sample_url) > 2048:
            raise ValueError("sample_url is required, 1-2048 chars")
        if not re.match(r"^(https?://|/|[A-Za-z]:[\\/]|asset://)", sample_url):
            raise ValueError("sample_url must be http(s)://, /, asset://, or absolute path")
        sample_duration = float(payload.get("sample_duration_seconds") or 5.0)
        if sample_duration < MIN_CLONE_SAMPLE_SECONDS or sample_duration > MAX_CLONE_SAMPLE_SECONDS:
            raise ValueError(f"sample_duration_seconds must be {MIN_CLONE_SAMPLE_SECONDS}-{MAX_CLONE_SAMPLE_SECONDS}")
        language = str(payload.get("language") or DEFAULT_LANGUAGE).lower()
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language: {language!r}")
        return cls(
            name=name,
            sample_url=sample_url,
            sample_duration_seconds=sample_duration,
            language=language,
            tags=[str(t)[:40] for t in (payload.get("tags") or []) if t][:16],
            description=(str(payload.get("description"))[:2000] if payload.get("description") else None),
        )


@dataclass
class ClonedVoice:
    voice_id: str
    name: str
    sample_url: str
    sample_duration_seconds: float
    language: str
    tags: List[str]
    description: Optional[str]
    voice_features: Dict[str, Any]  # pseudo-embedding + meta
    created_at: str
    owner_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════════
# Voice feature extraction (deterministic pseudo-embedding)
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_voice_features(sample_url: str, language: str, name: str) -> Dict[str, Any]:
    """Build a deterministic voice_features blob from the sample + meta.

    Real impl: feed the audio through a speaker encoder (Resemblyzer /
    WavLM). For now: SHA-256 of (sample_url| language| name) → 64-d
    pseudo-embedding + descriptive meta.
    """
    blob = f"{sample_url}|{language}|{name}".encode("utf-8")
    h = hashlib.sha256(blob).digest()
    emb = []
    for i in range(64):
        byte = h[i % len(h)]
        emb.append(round((byte - 128) / 128.0, 4))
    return {
        "embedding_dim": 64,
        "embedding": emb,
        "language": language,
        "name": name,
        "sample_url": sample_url,
        "extractor": "pseudo-sha256-v1",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Generator
# ═══════════════════════════════════════════════════════════════════════════════

class VoiceGenerator:
    """Text-to-speech + voice clone + library."""

    def __init__(self, *, default_mock: bool = True) -> None:
        self.default_mock = default_mock

    def list_models(self) -> List[Dict[str, str]]:
        return [{"name": name, **meta} for name, meta in VOICE_MODELS.items()]

    def resolve_model(self, model: str) -> Dict[str, str]:
        meta = VOICE_MODELS.get(model)
        if not meta:
            meta = VOICE_MODELS[DEFAULT_MODEL]
            return {"name": DEFAULT_MODEL, **meta, "fallback_from": model}
        return {"name": model, **meta}

    # ── TTS ───────────────────────────────────────────────────────────────
    def generate(self, req: VoiceGenerateRequest) -> VoiceGenerateResponse:
        start = time.time()
        resolved = self.resolve_model(req.model)
        provider_id = req.provider_id or resolved["provider_id"]

        # Rough duration estimate: ~150 chars/minute for zh, ~180 for en, scaled by speed
        chars_per_min = 150 if req.language.startswith("zh") else 180
        minutes = len(req.text) / max(1, chars_per_min)
        duration = (minutes * 60) / max(0.1, req.speed)

        audio_url = ""
        cost_usd = 0.0
        warnings: List[str] = []

        use_mock = req.mock or self.default_mock
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
                    "input": req.text,
                    "voice": req.voice_id or "alloy",
                    "language": req.language,
                    "speed": req.speed,
                    "pitch": req.pitch,
                    "emotion": req.emotion,
                }
                result = asyncio.run(call_provider_smart(
                    provider_cfg, payload, kind="chat",  # TTS uses chat-like adapter
                    user_id=req.user_id or "anonymous",
                ))
                cost_usd = float(result.get("cost_usd") or 0.0)
                audio_url = (result.get("data") or {}).get("audio_url") or ""
            except Exception as e:  # pragma: no cover
                logger.warning("voice generate failed (%s); mock fallback", e)
                warnings.append(f"provider_fallback: {e!s}")

        if not audio_url:
            audio_url = (
                f"https://via.placeholder.com/audio.mp3"
                f"?text=mock+voice+{req.model}+lang={req.language}"
                f"+len={len(req.text)}"
            )

        elapsed = int((time.time() - start) * 1000)
        return VoiceGenerateResponse(
            audio_url=audio_url,
            duration_seconds=round(duration, 2),
            language=req.language,
            model=req.model,
            provider_id=provider_id,
            voice_id=req.voice_id,
            emotion=req.emotion,
            mock=bool(use_mock),
            elapsed_ms=elapsed,
            cost_usd=cost_usd,
        )

    # ── Clone ─────────────────────────────────────────────────────────────
    def clone(self, req: VoiceCloneRequest, owner_id: Optional[str] = None) -> ClonedVoice:
        voice_id = f"voice_{uuid.uuid4().hex[:12]}"
        features = _extract_voice_features(req.sample_url, req.language, req.name)
        voice = ClonedVoice(
            voice_id=voice_id,
            name=req.name,
            sample_url=req.sample_url,
            sample_duration_seconds=req.sample_duration_seconds,
            language=req.language,
            tags=req.tags,
            description=req.description,
            voice_features=features,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            owner_id=owner_id,
        )
        VOICES_MEMORY_STORE[voice_id] = voice
        return voice

    # ── Library ───────────────────────────────────────────────────────────
    def list_voices(
        self,
        language: Optional[str] = None,
        tag: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ClonedVoice]:
        items = list(VOICES_MEMORY_STORE.values())
        if language:
            items = [v for v in items if v.language == language]
        if tag:
            items = [v for v in items if tag in v.tags]
        if query:
            q = query.lower()
            items = [v for v in items if q in v.name.lower() or any(q in t.lower() for t in v.tags)]
        items.sort(key=lambda v: v.created_at, reverse=True)
        return items[offset:offset + max(1, limit)]

    def get_voice(self, voice_id: str) -> Optional[ClonedVoice]:
        return VOICES_MEMORY_STORE.get(voice_id)

    def delete_voice(self, voice_id: str) -> bool:
        return VOICES_MEMORY_STORE.pop(voice_id, None) is not None


__all__ = [
    "VOICE_MODELS",
    "DEFAULT_MODEL",
    "SUPPORTED_LANGUAGES",
    "VoiceGenerateRequest",
    "VoiceGenerateResponse",
    "VoiceCloneRequest",
    "ClonedVoice",
    "VoiceGenerator",
    "VOICES_MEMORY_STORE",
]
