from __future__ import annotations

"""Tests for ``clean_dedupe_embed``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_dedupe_embed")
clean_dedupe_embed = _mod.clean_dedupe_embed

import pytest


def test_basic_no_duplicates():
    out = run_async(clean_dedupe_embed(build_skill_input({
        "items": ["apple", "banana", "cherry"],
        "threshold": 0.99,
    })))
    assert out.success is True
    assert out.result["offline"] is True
    assert out.result["duplicates"] == []

def test_offline_grouping_for_identical_url_pair():
    items = ["https://example.com/x.jpg", "https://example.com/x.jpg"]
    out = run_async(clean_dedupe_embed(build_skill_input({
        "items": items, "threshold": 0.5, "dim": 32,
    })))
    assert out.success is True
    assert out.result["duplicates"]

def test_metadata_present():
    out = run_async(clean_dedupe_embed(build_skill_input({
        "items": ["a", "b"], "threshold": 0.5,
    })))
    assert "timestamp" in out.metadata
