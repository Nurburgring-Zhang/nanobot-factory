from __future__ import annotations

"""Tests for ``clean_logo_watermark``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_logo_watermark")
clean_logo_watermark = _mod.clean_logo_watermark



def test_basic_watermark_detection():
    out = run_async(clean_logo_watermark(build_skill_input({
        "image_url": "https://example.com/wm.jpg",
    })))
    assert out.success is True
    assert isinstance(out.result["detections"], list)

def test_max_detections_capped():
    out = run_async(clean_logo_watermark(build_skill_input({
        "image_url": "https://example.com/x.jpg", "max_detections": 2,
    })))
    assert len(out.result["detections"]) <= 2

def test_metadata_present():
    out = run_async(clean_logo_watermark(build_skill_input({
        "image_url": "https://example.com/z.jpg",
    })))
    assert "confidence" in out.metadata
