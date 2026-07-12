from __future__ import annotations

"""Tests for ``clean_text_normalize``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_text_normalize")
clean_text_normalize = _mod.clean_text_normalize



def test_normalize_lowercase_and_strip_punct():
    out = run_async(clean_text_normalize(build_skill_input({
        "text": "Hello, WORLD!",
        "lowercase": True, "strip_punct": True,
    })))
    assert out.success is True
    assert out.result["normalized"] == "hello world"
    assert "lowercase" in out.result["changes"]

def test_collapse_whitespace():
    out = run_async(clean_text_normalize(build_skill_input({
        "text": "foo   bar\tbaz", "collapse_whitespace": True,
    })))
    assert out.result["normalized"] == "foo bar baz"

def test_metadata_present():
    out = run_async(clean_text_normalize(build_skill_input({"text": "x"})))
    assert "timestamp" in out.metadata
    assert "skill_id" in out.metadata
