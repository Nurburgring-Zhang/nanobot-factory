"""Tests for label_asr_transcribe."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_asr_transcribe
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_with_timestamps():
    out = _run(label_asr_transcribe(SkillInput(params={
        "audio": "https://example.com/clip.wav",
        "lang": "en",
        "timestamps": True,
    })))
    assert out.success is True
    res = out.result
    assert isinstance(res["text"], str) and len(res["text"]) > 0
    assert 2 <= len(res["segments"]) <= 3
    for s in res["segments"]:
        assert 0.0 <= s["start"] < s["end"]
        assert 0.0 <= s["confidence"] <= 1.0


def test_happy_path_chinese():
    out = _run(label_asr_transcribe(SkillInput(params={
        "audio": "/tmp/x.mp3",
        "lang": "zh",
    })))
    assert out.success is True
    assert out.result["lang"] == "zh"
    assert any("\u4e00" <= ch <= "\u9fff" for ch in out.result["text"])


def test_edge_case_timestamps_disabled():
    out = _run(label_asr_transcribe(SkillInput(params={
        "audio": "/tmp/x.mp3",
        "timestamps": False,
    })))
    assert out.success is True
    # segments list should be empty when timestamps=False
    assert out.result["segments"] == []


def test_error_handling_missing_audio():
    out = _run(label_asr_transcribe(SkillInput(params={})))
    assert out.success is False


def test_error_handling_empty_audio():
    out = _run(label_asr_transcribe(SkillInput(params={"audio": ""})))
    assert out.success is False


def test_segments_chronological():
    out = _run(label_asr_transcribe(SkillInput(params={
        "audio": "/tmp/x.mp3", "timestamps": True,
    })))
    segs = out.result["segments"]
    for i in range(len(segs) - 1):
        assert segs[i]["end"] <= segs[i + 1]["start"]