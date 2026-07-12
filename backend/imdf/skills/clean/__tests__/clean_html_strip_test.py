from __future__ import annotations

"""Tests for ``clean_html_strip``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_html_strip")
clean_html_strip = _mod.clean_html_strip



def test_basic_html_to_text():
    out = run_async(clean_html_strip(build_skill_input({
        "html": '<p>Hello <b>world</b></p><a href="x">link</a>',
    })))
    assert out.success is True
    assert "Hello" in out.result["text"]
    assert "world" in out.result["text"]
    assert "<" not in out.result["text"]

def test_entity_decode():
    out = run_async(clean_html_strip(build_skill_input({
        "html": "<p>Tom &amp; Jerry &lt;3</p>",
    })))
    assert "Tom & Jerry <3" == out.result["text"]

def test_br_kept_as_linebreak():
    out = run_async(clean_html_strip(build_skill_input({
        "html": "line1<br/>line2<br>line3",
    })))
    assert out.result["line_count"] >= 2
