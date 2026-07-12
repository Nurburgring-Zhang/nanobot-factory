"""Tests for label_llava_chat."""
from __future__ import annotations

import os

os.environ["LABEL_OFFLINE"] = "1"

from imdf.skills.label import label_llava_chat
from backend.skills import SkillInput


def _run(c):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(c)


def test_happy_path_single_turn():
    out = _run(label_llava_chat(SkillInput(params={
        "turns": [
            {"role": "user", "content": "Describe this image.", "image": "https://example.com/a.jpg"},
        ],
    })))
    assert out.success is True
    res = out.result
    assert isinstance(res["reply"], str) and len(res["reply"]) > 0
    # turns = input (1) + assistant reply (1) = 2
    assert len(res["turns"]) == 2
    assert res["turns"][-1]["role"] == "assistant"
    assert res["turns"][-1]["content"] == res["reply"]


def test_edge_case_multi_turn():
    out = _run(label_llava_chat(SkillInput(params={
        "turns": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "Hello."},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "What is in the image?", "image": "x.png"},
        ],
    })))
    assert out.success is True
    assert len(out.result["turns"]) == 5


def test_edge_case_question_appends_extra():
    out = _run(label_llava_chat(SkillInput(params={
        "turns": [{"role": "user", "content": "Why is the sky blue?"}],
    })))
    assert out.success is True
    assert "centrally framed" in out.result["reply"]


def test_error_handling_invalid_role():
    out = _run(label_llava_chat(SkillInput(params={
        "turns": [{"role": "alien", "content": "hi"}],
    })))
    assert out.success is False
    assert "invalid input" in out.error.lower() or "role" in out.error.lower()


def test_error_handling_last_turn_not_user():
    out = _run(label_llava_chat(SkillInput(params={
        "turns": [{"role": "assistant", "content": "hi"}],
    })))
    assert out.success is False
    assert "last turn" in out.error.lower()


def test_error_handling_empty_turns():
    out = _run(label_llava_chat(SkillInput(params={"turns": []})))
    assert out.success is False