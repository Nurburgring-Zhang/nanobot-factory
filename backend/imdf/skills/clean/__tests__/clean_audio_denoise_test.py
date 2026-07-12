from __future__ import annotations

"""Tests for ``clean_audio_denoise``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_audio_denoise")
clean_audio_denoise = _mod.clean_audio_denoise



def test_basic_audio_denoise():
    out = run_async(clean_audio_denoise(build_skill_input({
        "audio_url": "https://example.com/clip.wav",
        "strength": 0.7, "sample_rate": 16000,
    })))
    assert out.success is True
    assert out.result["output_url"]
    assert out.result["snr_out"] > out.result["snr_in"]

def test_default_sample_rate():
    out = run_async(clean_audio_denoise(build_skill_input({
        "audio_url": "https://example.com/clip.wav",
    })))
    assert out.success is True

def test_metadata_present():
    out = run_async(clean_audio_denoise(build_skill_input({
        "audio_url": "https://example.com/x.wav",
    })))
    assert "timestamp" in out.metadata
