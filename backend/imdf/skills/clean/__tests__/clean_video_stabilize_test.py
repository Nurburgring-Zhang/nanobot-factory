from __future__ import annotations

"""Tests for ``clean_video_stabilize``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_video_stabilize")
clean_video_stabilize = _mod.clean_video_stabilize



def test_basic_video_stabilize():
    out = run_async(clean_video_stabilize(build_skill_input({
        "video_url": "https://example.com/clip.mp4", "smoothing": 0.8,
    })))
    assert out.success is True
    assert out.result["frames_analyzed"] > 0

def test_crop_to_fit_flag():
    out = run_async(clean_video_stabilize(build_skill_input({
        "video_url": "https://example.com/clip.mp4", "crop_to_fit": True,
    })))
    assert out.result["fov_crop"] > 0

def test_no_crop_zero_fov():
    out = run_async(clean_video_stabilize(build_skill_input({
        "video_url": "https://example.com/clip.mp4", "crop_to_fit": False,
    })))
    assert out.result["fov_crop"] == 0.0
