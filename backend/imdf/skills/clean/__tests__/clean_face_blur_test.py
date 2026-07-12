from __future__ import annotations

"""Tests for ``clean_face_blur``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_face_blur")
clean_face_blur = _mod.clean_face_blur



def test_basic_face_blur():
    out = run_async(clean_face_blur(build_skill_input({
        "image_url": "https://example.com/group.jpg",
        "blur_strength": 50,
    })))
    assert out.success is True
    assert isinstance(out.result["faces"], list)

def test_blur_strength_echo():
    out = run_async(clean_face_blur(build_skill_input({
        "image_url": "https://example.com/face.jpg", "blur_strength": 80,
    })))
    assert out.result["blur_strength"] == 80

def test_max_faces_capping():
    out = run_async(clean_face_blur(build_skill_input({
        "image_url": "https://example.com/crowd.jpg", "max_faces": 1,
    })))
    assert len(out.result["faces"]) <= 1
