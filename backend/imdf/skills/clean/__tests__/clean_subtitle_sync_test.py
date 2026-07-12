from __future__ import annotations

"""Tests for ``clean_subtitle_sync``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_subtitle_sync")
clean_subtitle_sync = _mod.clean_subtitle_sync



def test_basic_offset_applied():
    srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n\n"
    out = run_async(clean_subtitle_sync(build_skill_input({
        "srt": srt, "offset_ms": 1000,
    })))
    assert out.success is True
    assert out.result["cue_count"] == 1
    assert "00:00:02,000" in out.result["srt"]

def test_aligned_flag():
    srt = "1\n00:00:01,000 --> 00:00:04,000\nHello\n"
    out = run_async(clean_subtitle_sync(build_skill_input({
        "srt": srt, "audio_url": "https://example.com/audio.wav",
    })))
    assert out.result["aligned"] is True

def test_empty_srt():
    out = run_async(clean_subtitle_sync(build_skill_input({"srt": ""})))
    assert out.success is True
    assert out.result["cue_count"] == 0
