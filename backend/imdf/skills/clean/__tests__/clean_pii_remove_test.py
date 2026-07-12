from __future__ import annotations

"""Tests for ``clean_pii_remove``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_pii_remove")
clean_pii_remove = _mod.clean_pii_remove



def test_basic_email_redaction():
    text = "Reach me at alice@example.com for details."
    out = run_async(clean_pii_remove(build_skill_input({"text": text})))
    assert out.success is True
    assert "alice@example.com" not in out.result["redacted"]
    assert out.result["redaction_count"] == 1

def test_multi_pii_redaction():
    text = "Email: a@b.com Phone: 415-555-1234 IP: 192.168.1.1"
    out = run_async(clean_pii_remove(build_skill_input({"text": text})))
    assert out.result["redaction_count"] >= 3

def test_custom_replacement_token():
    text = "bob@example.com"
    out = run_async(clean_pii_remove(build_skill_input({
        "text": text, "replacement": "<<EMAIL>>",
    })))
    assert "<<EMAIL>>" in out.result["redacted"]
