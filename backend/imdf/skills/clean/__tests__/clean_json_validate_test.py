from __future__ import annotations

"""Tests for ``clean_json_validate``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_json_validate")
clean_json_validate = _mod.clean_json_validate



def test_valid_document():
    out = run_async(clean_json_validate(build_skill_input({
        "document": {"name": "alice", "age": 30},
        "schema": {
            "type": "object", "required": ["name"],
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        },
    })))
    assert out.success is True
    assert out.result["valid"] is True

def test_missing_required_field():
    out = run_async(clean_json_validate(build_skill_input({
        "document": {"age": 30},
        "schema": {"type": "object", "required": ["name"]},
    })))
    assert out.result["valid"] is False

def test_enum_violation():
    out = run_async(clean_json_validate(build_skill_input({
        "document": {"role": "owner"},
        "schema": {"type": "string", "enum": ["viewer", "editor"]},
    })))
    assert out.result["valid"] is False
