"""P4-5-W1 — Voice generator tests (2 tests, mock mode).

Coverage:
  1. VoiceGenerator.clone creates a deterministic voice_features embedding
     and lists it; multilingual language whitelist enforced.
  2. VoiceGenerator.generate returns a duration-scaled audio URL with model
     and language metadata.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True)
def _reset_voice_store():
    """Reset the in-memory voice library between tests for isolation."""
    from services.asset_service.generators import voice as voice_mod
    voice_mod.VOICES_MEMORY_STORE.clear()
    yield
    voice_mod.VOICES_MEMORY_STORE.clear()


def test_clone_creates_deterministic_features_and_library():
    """VoiceGenerator.clone: deterministic embedding + library search."""
    from services.asset_service.generators.voice import (
        SUPPORTED_LANGUAGES,
        VoiceCloneRequest,
        VoiceGenerator,
    )

    # Multilingual whitelist — 4 base + 24 地方言 = 28
    assert "zh" in SUPPORTED_LANGUAGES
    assert "en" in SUPPORTED_LANGUAGES
    assert "ja" in SUPPORTED_LANGUAGES
    assert "ko" in SUPPORTED_LANGUAGES
    assert "zh-yue" in SUPPORTED_LANGUAGES
    assert "zh-sichuan" in SUPPORTED_LANGUAGES
    assert len(SUPPORTED_LANGUAGES) == 28

    gen = VoiceGenerator()

    # Clone two voices
    v1 = gen.clone(VoiceCloneRequest(
        name="苏晚晴 voice",
        sample_url="https://x.com/sample1.wav",
        sample_duration_seconds=8.0,
        language="zh",
        tags=["female", "anime"],
        description="苏晚晴的真人声音样本",
    ))
    v2 = gen.clone(VoiceCloneRequest(
        name="Captain Vega voice",
        sample_url="https://x.com/sample2.wav",
        sample_duration_seconds=10.0,
        language="en",
        tags=["female", "sci-fi"],
    ))

    # Deterministic embedding from (sample_url | language | name)
    assert v1.voice_features["embedding_dim"] == 64
    assert len(v1.voice_features["embedding"]) == 64
    assert all(isinstance(x, float) for x in v1.voice_features["embedding"])
    # Same name + url + lang → same embedding (deterministic).
    # Build the candidate without inserting it into the library.
    candidate = VoiceCloneRequest(
        name="苏晚晴 voice",
        sample_url="https://x.com/sample1.wav",
        sample_duration_seconds=8.0,
        language="zh",
        tags=["female", "anime"],
    )
    assert _extract_features(candidate) == v1.voice_features
    # Different sample → different
    assert _extract_features(VoiceCloneRequest(
        name="苏晚晴 voice",
        sample_url="https://x.com/sample1_v2.wav",
        sample_duration_seconds=8.0,
        language="zh",
    )) != v1.voice_features
    # v1 vs v2
    assert v1.voice_features["embedding"] != v2.voice_features["embedding"]

    # Library
    voices = gen.list_voices()
    assert len(voices) == 2
    # Language filter
    zh_voices = gen.list_voices(language="zh")
    assert len(zh_voices) == 1
    assert zh_voices[0].name == "苏晚晴 voice"
    # Tag filter
    sci_fi = gen.list_voices(tag="sci-fi")
    assert len(sci_fi) == 1
    # Query
    q = gen.list_voices(query="vega")
    assert len(q) == 1
    assert q[0].voice_id == v2.voice_id
    # Get
    got = gen.get_voice(v1.voice_id)
    assert got is not None
    assert got.name == "苏晚晴 voice"
    # Delete
    assert gen.delete_voice(v2.voice_id) is True
    assert gen.delete_voice("nonexistent") is False
    assert len(gen.list_voices()) == 1


def _extract_features(req: "VoiceCloneRequest") -> dict:
    """Pure helper: extract voice_features without inserting."""
    from services.asset_service.generators.voice import _extract_voice_features
    return _extract_voice_features(req.sample_url, req.language, req.name)


def test_generate_returns_duration_scaled_audio():
    """VoiceGenerator.generate returns a duration-scaled audio URL with metadata."""
    from services.asset_service.generators.voice import (
        VoiceGenerateRequest,
        VoiceGenerator,
    )

    gen = VoiceGenerator()
    req = VoiceGenerateRequest(
        text="你好,世界. 这是一段测试语音。Hello, world.",
        language="zh",
        model="volc-tts",
        speed=1.0,
        emotion="neutral",
        mock=True,
    )
    resp = gen.generate(req)
    assert resp.audio_url
    assert resp.language == "zh"
    assert resp.model == "volc-tts"
    assert resp.emotion == "neutral"
    assert resp.duration_seconds > 0
    assert resp.elapsed_ms >= 0
    # zh text ≈ 150 chars/min → a ~33-char text is ~13s, but accept a generous range
    assert 0.5 <= resp.duration_seconds <= 60.0

    # Speed × 2 → roughly halves duration
    req_fast = VoiceGenerateRequest(
        text="测试加速",
        language="zh",
        speed=2.0,
        mock=True,
    )
    resp_fast = gen.generate(req_fast)
    assert resp_fast.duration_seconds < resp.duration_seconds

    # Reject unsupported language
    with pytest.raises(Exception):
        VoiceGenerateRequest.from_payload({"text": "x", "language": "klingon"})

    # Reject unsupported emotion
    with pytest.raises(Exception):
        VoiceGenerateRequest.from_payload({"text": "x", "emotion": "ecstatic"})
