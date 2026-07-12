"""Tests for label_entity_ner."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_entity_ner
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_dates_and_money():
    text = "On 2026-01-15 the deal closed at $1,250,000 USD."
    out = _run(label_entity_ner(SkillInput(params={
        "text": text,
        "types": ["DATE", "MONEY"],
        "lang": "en",
    })))
    assert out.success is True
    res = out.result
    assert res["count"] >= 2
    types_found = {e["type"] for e in res["entities"]}
    assert "DATE" in types_found
    assert "MONEY" in types_found
    # Every entity has the required fields
    for e in res["entities"]:
        assert 0 <= e["start"] < e["end"] <= len(text)
        assert 0.0 <= e["confidence"] <= 1.0


def test_happy_path_person_detection():
    out = _run(label_entity_ner(SkillInput(params={
        "text": "John Smith and Jane Doe met in Berlin.",
        "types": ["PERSON", "LOC"],
        "lang": "en",
    })))
    assert out.success is True
    persons = [e for e in out.result["entities"] if e["type"] == "PERSON"]
    assert len(persons) >= 1
    for p in persons:
        assert "Smith" in p["text"] or "Doe" in p["text"]


def test_edge_case_empty_types_falls_back():
    out = _run(label_entity_ner(SkillInput(params={
        "text": "Today is 2026-07-09 and the price is 50%.",
        "types": [],
    })))
    assert out.success is True
    assert out.result["types"] == ["PERSON", "ORG", "LOC"]


def test_edge_case_auto_lang_detection():
    out = _run(label_entity_ner(SkillInput(params={
        "text": "2026-01-15 happened.",
        "lang": "auto",
        "types": ["DATE"],
    })))
    assert out.success is True
    # Should detect as English (no CJK chars)
    assert out.result["lang"] == "en"


def test_error_handling_empty_text():
    out = _run(label_entity_ner(SkillInput(params={"text": ""})))
    assert out.success is False


def test_error_handling_missing_text():
    out = _run(label_entity_ner(SkillInput(params={})))
    assert out.success is False