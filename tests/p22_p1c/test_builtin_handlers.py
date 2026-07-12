"""P22-P1c: tests for the 50 builtin skill handlers.

Covers:
- registration count (50 handlers loaded from BUILTIN_SKILLS)
- SkillManager registers all 50 in self.skills
- execute_skill dispatches to a real handler for each spec.id
- 5 sample handlers (one per category group) actually do something useful
- no NotImplementedError / no 'no implementation' error on any spec

Run with: pytest tests/p22_p1c/test_builtin_handlers.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

# Add repo root to sys.path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.skills.legacy import SkillManager, SkillInput
from backend.skills_builtin import BUILTIN_SKILLS
from backend.skills_builtin_handlers import (
    HANDLERS,
    IMPLEMENTATIONS,
    _BuiltinHandler,
    all_handlers,
    get_handler,
)


# -------- registration --------

def test_50_implementations_registered():
    assert len(IMPLEMENTATIONS) == 50, f"expected 50, got {len(IMPLEMENTATIONS)}"


def test_50_handlers_built():
    assert len(HANDLERS) == 50, f"expected 50, got {len(HANDLERS)}"
    for h in HANDLERS.values():
        assert isinstance(h, _BuiltinHandler)
        assert h.spec_id == h.name


def test_handlers_match_specs():
    spec_ids = {s.id for s in BUILTIN_SKILLS}
    handler_ids = set(HANDLERS.keys())
    # every spec has a handler
    missing = spec_ids - handler_ids
    assert not missing, f"specs without handlers: {missing}"


def test_get_handler_returns_builtin_handler():
    h = get_handler("skill_crawl_web")
    assert h is not None
    assert h.spec_id == "skill_crawl_web"
    assert get_handler("nonexistent_skill") is None


def test_all_handlers_returns_copy():
    a = all_handlers()
    b = all_handlers()
    assert a is not b
    a["foo"] = "bar"
    assert "foo" not in all_handlers()


# -------- SkillManager integration --------

def test_skill_manager_registers_50_builtin():
    sm = SkillManager()
    # 5 core + 50 builtin
    assert len(sm.skills) == 55, f"expected 55, got {len(sm.skills)}"


def test_skill_manager_can_lookup_builtin():
    sm = SkillManager()
    for spec in BUILTIN_SKILLS:
        assert spec.id in sm.skills, f"spec {spec.id} not registered in SkillManager"
        h = sm.skills[spec.id]
        assert isinstance(h, _BuiltinHandler), f"expected _BuiltinHandler for {spec.id}"


def test_get_all_skills_marks_50_as_real():
    sm = SkillManager()
    real = sm.get_real_skills()
    # All 55 should now be 'real' (5 core + 50 builtin)
    real_ids = {s["id"] for s in real}
    assert len(real) == 55
    for spec in BUILTIN_SKILLS:
        assert spec.id in real_ids


# -------- sample real executions --------

@pytest.mark.asyncio
async def test_dedupe_real():
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_dedupe",
        SkillInput(prompt="", params={"items": ["a", "b", "a", "c", "b", "c"]}),
    )
    assert out.success
    assert out.result["input_count"] == 6
    assert out.result["unique_count"] == 3
    assert out.result["removed"] == 3
    assert sorted(out.result["unique"]) == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_dedupe_handles_dicts():
    sm = SkillManager()
    items = [{"k": 1}, {"k": 2}, {"k": 1}, {"k": 3}]
    out = await sm.execute_skill("skill_dedupe", SkillInput(params={"items": items}))
    assert out.success
    assert out.result["unique_count"] == 3


@pytest.mark.asyncio
async def test_auto_label_real():
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_auto_label",
        SkillInput(prompt="This is an AI model trained on data for image generation"),
    )
    assert out.success
    assert "primary" in out.result
    assert out.result["primary"] in {"tech", "media", "business", "ops", "research", "uncategorized"}


@pytest.mark.asyncio
async def test_score_quality_real():
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_score_quality",
        SkillInput(prompt="This is a test. It has multiple sentences. With words."),
    )
    assert out.success
    assert 0 <= out.result["overall"] <= 1
    assert "components" in out.result


@pytest.mark.asyncio
async def test_format_normalize_json_to_dict():
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_format_normalize",
        SkillInput(params={"payload": '{"a": 1, "b": [2, 3]}', "target": "json"}),
    )
    assert out.success
    assert out.result["normalized"] == {"a": 1, "b": [2, 3]}


@pytest.mark.asyncio
async def test_format_normalize_csv_to_list():
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_format_normalize",
        SkillInput(params={"payload": "name,age\nalice,30\nbob,25", "target": "csv"}),
    )
    assert out.success
    assert out.result["format"] == "csv"
    assert out.result["normalized"] == [
        {"name": "alice", "age": "30"},
        {"name": "bob", "age": "25"},
    ]


@pytest.mark.asyncio
async def test_seed_extract_real():
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_seed_extract",
        SkillInput(params={"text": "Visit https://example.com or email foo@bar.com for info."}),
    )
    assert out.success
    assert "https://example.com" in out.result["urls"]
    assert "foo@bar.com" in out.result["emails"]


@pytest.mark.asyncio
async def test_meta_intent_real():
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_meta_intent",
        SkillInput(prompt="Can you summarize this document?"),
    )
    assert out.success
    assert out.result["primary"] in {"query", "command", "create", "delete", "analyze", "summarize", "translate"}


@pytest.mark.asyncio
async def test_meta_review_grading():
    sm = SkillManager()
    full = {"name": "x", "description": "y", "tags": ["a"], "owner": "me"}
    out = await sm.execute_skill("skill_meta_review", SkillInput(params={"target": full}))
    assert out.success
    assert out.result["score"] == 100
    assert out.result["grade"] == "A"

    empty = {}
    out = await sm.execute_skill("skill_meta_review", SkillInput(params={"target": empty}))
    assert out.success
    assert out.result["score"] == 0
    assert out.result["grade"] == "D"


@pytest.mark.asyncio
async def test_octo_bot_create():
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_octo_bot_create",
        SkillInput(params={"spec": {"name": "test-bot"}}),
    )
    assert out.success
    assert out.result["bot_id"].startswith("bot_")
    assert out.result["spec"]["name"] == "test-bot"


@pytest.mark.asyncio
async def test_comfy_workflow_persistence(tmp_path, monkeypatch):
    # Use tmp dir for persistence
    monkeypatch.chdir(tmp_path)
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_comfy_workflow",
        SkillInput(params={"action": "save", "workflow": {"name": "wf1", "nodes": ["a", "b"]}}),
    )
    assert out.success
    out = await sm.execute_skill("skill_comfy_workflow", SkillInput(params={"action": "list"}))
    assert out.success
    assert "wf1" in out.result["workflows"]


@pytest.mark.asyncio
async def test_comfy_run_offline_fallback(tmp_path, monkeypatch):
    """skill_comfy_run: when COMFYUI_URL is unreachable, return
    queued_offline payload with would_post_to metadata. Validates the
    P22-P2-real real-HTTP integration path is wired (not silent drop)."""
    monkeypatch.chdir(tmp_path)
    # Point at a guaranteed-unreachable URL with short timeout via env
    monkeypatch.setenv("COMFYUI_URL", "http://127.0.0.1:1")  # port 1 always closed
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_comfy_run",
        SkillInput(params={"workflow": {"3": {"inputs": {"seed": 42}, "class_type": "KSampler"}}}),
    )
    assert out.success, f"comfy_run should always return success=True, got: {out.error}"
    # Either real success (if some local ComfyUI happens to run) or offline queue
    if out.result.get("status") == "queued_offline":
        assert "would_post_to" in out.result
        assert "payload_size" in out.result
        assert out.metadata.get("engine") == "comfy"
    else:
        # Real success path
        assert "prompt_id" in out.result
        assert out.metadata.get("engine") == "comfy"


@pytest.mark.asyncio
async def test_agency_crud(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_agency_expert",
        SkillInput(params={"action": "save", "item": {"id": "exp1", "skills": ["python"]}}),
    )
    assert out.success
    out = await sm.execute_skill("skill_agency_expert", SkillInput(params={"action": "get", "id": "exp1"}))
    assert out.success
    assert out.result["item"]["skills"] == ["python"]


@pytest.mark.asyncio
async def test_translate_passthrough():
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_translate",
        SkillInput(params={"text": "hello", "target": "zh"}),
    )
    assert out.success
    # Without API configured, source='passthrough' and text returned unchanged
    assert out.result["source"] == "passthrough"
    assert out.result["translated"] == "hello"


@pytest.mark.asyncio
async def test_meta_lesson_round_trip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sm = SkillManager()
    out = await sm.execute_skill(
        "skill_meta_lesson",
        SkillInput(params={"action": "add", "lesson": {"title": "test", "body": "always validate inputs"}}),
    )
    assert out.success
    lid = out.result["lesson_id"]
    out = await sm.execute_skill("skill_meta_lesson", SkillInput(params={"action": "list"}))
    assert out.success
    assert out.result["count"] >= 1
    assert any(ls["id"] == lid for ls in out.result["lessons"])


# -------- dispatch coverage --------

@pytest.mark.asyncio
@pytest.mark.parametrize("spec_id", [s.id for s in BUILTIN_SKILLS])
async def test_every_spec_dispatches_to_real_handler(spec_id):
    """For every builtin spec, execute_skill must NOT raise NotImplementedError
    or return 'no implementation registered'. Real handlers may legitimately
    return success=False (e.g. missing required params) but the dispatch
    path itself must be wired."""
    sm = SkillManager()
    out = await sm.execute_skill(spec_id, SkillInput(prompt="", params={}))
    # Must be a SkillOutput (not an exception)
    assert out is not None
    # Must NOT be the 'no implementation' error from _BuiltinHandler
    assert "no implementation registered" not in (out.error or ""), (
        f"{spec_id} has no implementation"
    )
    # Most handlers will return success=False with a real validation error
    # like 'url required' or 'query required' — that's fine, just must not
    # be the dispatcher-level 'no implementation' error.
