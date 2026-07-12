from __future__ import annotations

"""Tests for ``clean_nsfw_detect``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_nsfw_detect")
clean_nsfw_detect = _mod.clean_nsfw_detect



def test_basic_nsfw_score():
    out = run_async(clean_nsfw_detect(build_skill_input({
        "image_url": "https://example.com/test.jpg",
    })))
    assert out.success is True
    assert 0.0 <= out.result["nsfw_score"] <= 1.0

def test_threshold_high_no_flag():
    out = run_async(clean_nsfw_detect(build_skill_input({
        "image_url": "https://example.com/x.jpg", "threshold": 0.99,
    })))
    assert out.result["flagged"] is False

def test_threshold_zero_flagged():
    out = run_async(clean_nsfw_detect(build_skill_input({
        "image_url": "https://example.com/x.jpg", "threshold": 0.0,
    })))
    assert out.result["flagged"] is True
