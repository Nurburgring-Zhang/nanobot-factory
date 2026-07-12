"""Tests for label_blip2_vqa."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_blip2_vqa
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_what_question():
    out = _run(label_blip2_vqa(SkillInput(params={
        "image": "https://example.com/x.jpg",
        "question": "What is in this picture?",
    })))
    assert out.success is True
    assert out.result["answer"] in {
        "a person", "an animal", "a vehicle", "a building", "a landscape",
    }
    assert out.result["question"] == "What is in this picture?"
    assert 0.0 <= out.result["confidence"] <= 1.0


def test_edge_case_color_question():
    out = _run(label_blip2_vqa(SkillInput(params={
        "image": "/tmp/x.png",
        "question": "What color is dominant?",
    })))
    assert out.success is True
    assert out.result["answer"] in {
        "red", "blue", "green", "yellow", "black", "white", "purple",
    }


def test_edge_case_unknown_question_falls_back():
    out = _run(label_blip2_vqa(SkillInput(params={
        "image": "/tmp/x.png",
        "question": "Quantum entanglement of photons?",
    })))
    assert out.success is True
    assert out.result["answer"] == "uncertain"
    assert out.result["confidence"] == 0.5


def test_error_handling_empty_question():
    out = _run(label_blip2_vqa(SkillInput(params={
        "image": "/tmp/x.png",
        "question": "",
    })))
    assert out.success is False
    assert "invalid input" in out.error.lower() or "question" in out.error.lower()


def test_error_handling_missing_question():
    out = _run(label_blip2_vqa(SkillInput(params={"image": "x.png"})))
    assert out.success is False