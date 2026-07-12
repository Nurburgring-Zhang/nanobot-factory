from __future__ import annotations

"""Tests for ``clean_markdown_lint``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_markdown_lint")
clean_markdown_lint = _mod.clean_markdown_lint



def test_clean_markdown_zero_issues():
    text = "# Title\n\nSome text.\n\n- item 1\n- item 2\n"
    out = run_async(clean_markdown_lint(build_skill_input({"markdown": text})))
    assert out.success is True
    assert out.result["error_count"] == 0

def test_markdown_line_too_long():
    out = run_async(clean_markdown_lint(build_skill_input({
        "markdown": "# Title\n\n" + ("x" * 200),
        "max_line_length": 100,
    })))
    assert any(i["rule"] == "line-length" for i in out.result["issues"])

def test_markdown_unclosed_code_fence():
    out = run_async(clean_markdown_lint(build_skill_input({
        "markdown": "# Title\n\n```\nfoo",
    })))
    assert any(i["rule"] == "unclosed-code-fence" for i in out.result["issues"])
