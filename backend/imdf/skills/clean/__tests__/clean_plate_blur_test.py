from __future__ import annotations

"""Tests for ``clean_plate_blur``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_plate_blur")
clean_plate_blur = _mod.clean_plate_blur



def test_basic_plate_blur():
    out = run_async(clean_plate_blur(build_skill_input({
        "image_url": "https://example.com/car.jpg",
        "blur_strength": 60, "region_hint": "us",
    })))
    assert out.success is True
    assert out.result["region"] == "us"

def test_region_hint_default():
    out = run_async(clean_plate_blur(build_skill_input({
        "image_url": "https://example.com/car.jpg",
    })))
    assert out.result["region"] == "auto"

def test_plates_have_geometry():
    out = run_async(clean_plate_blur(build_skill_input({
        "image_url": "https://example.com/car.jpg",
    })))
    for plate in out.result["plates"]:
        assert {"x", "y", "w", "h"}.issubset(plate.keys())
