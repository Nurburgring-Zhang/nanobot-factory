"""Layer 11 — Compliance reports tests."""

from __future__ import annotations

import pytest

from monitoring import cost_tracking as cost_mod
from monitoring import agent_tracking as agent_mod
from monitoring import quality_tracking as quality_mod
from monitoring import compliance_reports as compliance


@pytest.fixture(autouse=True)
def _reset_singletons():
    cost_mod._TRACKER = None
    agent_mod._TRACKER = None
    quality_mod._TRACKER = None
    yield
    cost_mod._TRACKER = None
    agent_mod._TRACKER = None
    quality_mod._TRACKER = None


def test_gdpr_access_report_shape():
    cost_mod.get_tracker().record(user_id="u1", model="gpt-4o-mini", input_tokens=100, output_tokens=200)
    agent_mod.get_tracker().record(agent_id="a1", user_id="u1")
    quality_mod.get_tracker().record(annotator_id="u1", item_id="i1", label=1, score=0.9)

    report = compliance.generate_gdpr_access("u1")
    d = report.to_dict()
    assert d["report_type"] == "data_subject_access"
    assert d["user_id"] == "u1"
    # The fingerprint is nested inside the Subject section, not at top-level.
    subject_rows = d["sections"][0]["rows"]
    fingerprint_row = next(r for r in subject_rows if r["label"] == "data_fingerprint_sha256")
    assert fingerprint_row["value"] and len(fingerprint_row["value"]) == 64  # sha256 hex
    assert "GDPR Art. 15" in d["note"]


def test_gdpr_access_includes_record_counts():
    cost_mod.get_tracker().record(user_id="u1", model="gpt-4o", input_tokens=10, output_tokens=20)
    cost_mod.get_tracker().record(user_id="u1", model="gpt-4o", input_tokens=10, output_tokens=20)
    cost_mod.get_tracker().record(user_id="u2", model="gpt-4o", input_tokens=10, output_tokens=20)
    report = compliance.generate_gdpr_access("u1")
    d = report.to_dict()
    section = next(s for s in d["sections"] if s["title"] == "Categories of personal data")
    cost_count = next(r["value"] for r in section["rows"] if r["label"] == "Cost & billing records")
    assert cost_count == 2


def test_gdpr_erasure_report_shape():
    report = compliance.generate_gdpr_erasure("u1")
    d = report.to_dict()
    assert d["report_type"] == "right_to_erasure"
    assert d["user_id"] == "u1"
    assert d["note"].startswith("GDPR Art. 17")


def test_gdpr_access_markdown_contains_subject():
    report = compliance.generate_gdpr_access("u1")
    md = report.to_markdown()
    assert "# GDPR Report" in md
    assert "u1" in md


def test_eu_ai_act_report_has_six_sections():
    rep = compliance.generate_eu_ai_act_report()
    assert rep["report_type"] == "eu_ai_act_high_risk_system"
    assert len(rep["sections"]) == 6
    keys = {s["key"] for s in rep["sections"]}
    expected = {
        "data_governance", "technical_documentation", "record_keeping",
        "transparency", "human_oversight", "accuracy_robustness_cybersecurity",
    }
    assert keys == expected


def test_eu_ai_act_report_articles_match_regulation():
    rep = compliance.generate_eu_ai_act_report()
    by_key = {s["key"]: s["article"] for s in rep["sections"]}
    assert by_key["data_governance"] == "Art. 10"
    assert by_key["technical_documentation"] == "Art. 11"
    assert by_key["record_keeping"] == "Art. 12"
    assert by_key["transparency"] == "Art. 13"
    assert by_key["human_oversight"] == "Art. 14"
    assert by_key["accuracy_robustness_cybersecurity"] == "Art. 15"


def test_eu_ai_act_report_to_markdown():
    rep = compliance.generate_eu_ai_act_report()
    md = compliance.to_markdown(rep)
    assert "Art. 10" in md
    assert "Art. 15" in md
    assert "Implemented controls" in md
