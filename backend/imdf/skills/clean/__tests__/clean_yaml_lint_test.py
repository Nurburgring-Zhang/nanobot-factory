from __future__ import annotations

"""Tests for ``clean_yaml_lint``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_yaml_lint")
clean_yaml_lint = _mod.clean_yaml_lint



def test_clean_yaml_parses():
    out = run_async(clean_yaml_lint(build_skill_input({
        "yaml": "name: alice\nage: 30\ncity: shenzhen\n",
    })))
    assert out.success is True
    assert out.result["valid"] is True
    assert "name" in out.result["keys"]

def test_tab_indent_error():
    out = run_async(clean_yaml_lint(build_skill_input({"yaml": "name:\tvalue\n"})))
    assert out.result["valid"] is False

def test_nested_keys():
    out = run_async(clean_yaml_lint(build_skill_input({
        "yaml": "section:\n  key1: v1\n  key2: v2\n",
    })))
    assert out.result["parsed"] is True
