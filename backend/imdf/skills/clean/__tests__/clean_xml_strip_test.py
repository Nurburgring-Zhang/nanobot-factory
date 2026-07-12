from __future__ import annotations

"""Tests for ``clean_xml_strip``."""

import sys
from pathlib import Path

# Bootstrap loader — bypasses the broken ``backend.imdf.skills.__init__``.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _bootstrap import build_skill_input, import_skill_module, run_async  # noqa: E402

_mod = import_skill_module("clean_xml_strip")
clean_xml_strip = _mod.clean_xml_strip



def test_basic_xml_with_namespace():
    xml = '<root xmlns:ns="http://x" xmlns:y="http://y"><ns:item>1</ns:item></root>'
    out = run_async(clean_xml_strip(build_skill_input({"xml": xml})))
    assert out.success is True
    assert out.result["elements"] >= 2
    assert len(out.result["namespaces"]) == 2

def test_remove_namespaces_strips_prefix():
    xml = '<root xmlns:ns="http://x"><ns:item>1</ns:item></root>'
    out = run_async(clean_xml_strip(build_skill_input({
        "xml": xml, "remove_namespaces": True,
    })))
    assert "xmlns:ns" not in out.result["cleaned_xml"]

def test_empty_input():
    out = run_async(clean_xml_strip(build_skill_input({"xml": ""})))
    assert out.success is True
    assert out.result["cleaned_xml"] == ""
