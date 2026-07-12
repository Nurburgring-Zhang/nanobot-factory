from __future__ import annotations

"""Tests for ``clean_csv_normalize``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_csv_normalize")
clean_csv_normalize = _mod.clean_csv_normalize



def test_basic_csv():
    csv = "Name,Age,City\nAlice,30,Beijing\nBob,25,Shanghai\n"
    out = run_async(clean_csv_normalize(build_skill_input({"csv": csv})))
    assert out.success is True
    assert out.result["headers"] == ["Name", "Age", "City"]
    assert out.result["rows"][0] == ["Alice", "30", "Beijing"]

def test_lowercase_headers_and_blank_drop():
    csv = "Name , Age , City\nAlice,30,Beijing\n\n, ,\nBob,25,Shanghai\n"
    out = run_async(clean_csv_normalize(build_skill_input({
        "csv": csv, "lowercase_headers": True,
    })))
    assert out.result["headers"] == ["name", "age", "city"]

def test_auto_delimiter():
    csv = "a\tb\tc\n1\t2\t3\n"
    out = run_async(clean_csv_normalize(build_skill_input({
        "csv": csv, "delimiter": "",
    })))
    assert out.result["detected_delimiter"] == "\t"
