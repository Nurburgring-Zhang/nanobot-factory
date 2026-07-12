from __future__ import annotations

"""Tests for ``clean_dedupe_hash``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_dedupe_hash")
clean_dedupe_hash = _mod.clean_dedupe_hash
compare = _mod.compare
match_threshold = _mod.match_threshold

import os
import pytest


def test_basic_phash():
    out = run_async(clean_dedupe_hash(build_skill_input({
        "image_url": "https://example.com/cat.jpg",
        "hash_size": 8,
        "method": "phash",
    })))
    assert out.success is True
    assert isinstance(out.result["hash"], str)
    assert len(out.result["hash"]) == 64
    assert "timestamp" in out.metadata

def test_dhash_branch_and_compare():
    out = run_async(clean_dedupe_hash(build_skill_input({
        "image_url": "https://example.com/cat.jpg",
        "method": "dhash",
    })))
    assert out.success is True
    h = out.result["hash"]
    d1 = compare(h, h)
    assert d1 == 0
    assert match_threshold("phash", 8) >= 4

def test_invalid_method():
    out = run_async(clean_dedupe_hash(build_skill_input({
        "image_url": "x", "method": "nope",
    })))
    assert out.success is False
    assert "unsupported" in out.error
