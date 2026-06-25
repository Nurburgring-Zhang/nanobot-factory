"""P4-8-W1: framework tests — decorator, registry, context, result, orchestrator."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure backend is importable.
_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest  # noqa: E402

from skills.base import Skill, SkillCategory, skill  # noqa: E402
from skills.context import Blackboard, SkillContext  # noqa: E402
from skills.orchestrator import ChainStep, SkillOrchestrator  # noqa: E402
from skills.registry import SKILL_REGISTRY  # noqa: E402
from skills.result import SkillResult  # noqa: E402


# ── 1. Decorator + auto-registration ────────────────────────────────────────
def test_skill_decorator_registers_in_global_registry():
    @skill(
        name="_test_decorator_skill",
        description="Decorator test skill",
        category=SkillCategory.PRODUCTIVITY,
        version="1.0.0",
        tags=["test"],
    )
    class _T(Skill):
        async def execute(self, ctx: SkillContext) -> SkillResult:
            return SkillResult.ok(data={"echo": ctx.inputs.get("x")}, skill_name=self.meta.name)

    assert SKILL_REGISTRY.has("_test_decorator_skill")
    meta = SKILL_REGISTRY.meta("_test_decorator_skill")
    assert meta.category == SkillCategory.PRODUCTIVITY
    assert "test" in meta.tags
    assert meta.builtin is True


# ── 2. SkillContext + Blackboard sharing ────────────────────────────────────
def test_context_blackboard_is_shared_across_derives():
    ctx = SkillContext.create(user_id="u1", project_id="p1", inputs={"a": 1})
    child = ctx.derive(skill_name="child")
    child.put("k", 42)
    assert ctx.pull("k") == 42  # shared
    assert len(child.trace) == 1
    child.finish_last(True, note="done")
    assert child.trace[-1].success is True


# ── 3. SkillResult pick() modes ──────────────────────────────────────────────
def test_skill_result_pick_modes():
    r1 = SkillResult.ok(data={"output": "x"})
    assert r1.pick() == {"output": "x"}
    assert r1.pick("output") == "x"
    assert r1.pick("json").startswith("{")
    r2 = SkillResult.fail("bad", skill_name="x")
    assert r2.success is False
    assert r2.error == "bad"


# ── 4. SkillOrchestrator routing + chain ─────────────────────────────────────
def test_orchestrator_routes_and_chains():
    # Ensure built-ins are loaded.
    import skills.builtin  # noqa: F401

    orch = SkillOrchestrator()
    # Register explicit route keywords.
    orch.register_route("guizang_ppt", ["ppt", "演示", "幻灯片"])
    orch.register_route("humanizer_zh", ["改写", "人话", "humanizer"])
    chosen = orch.route("帮我做一个 PPT 讲 AI")
    assert chosen == "guizang_ppt"
    chosen2 = orch.route("帮我改写成更自然的人话")
    assert chosen2 == "humanizer_zh"

    async def _chain():
        ctx = SkillContext.create(user_id="u1", inputs={"topic": "AI"})
        chain = await orch.run_chain(
            [
                ChainStep(skill="guizang_ppt", inputs={"topic": "AI 工厂"}),
                ChainStep(skill="humanizer_zh", pick_mode="data"),
            ],
            ctx,
        )
        return chain

    res = asyncio.run(_chain())
    assert res.success is True
    assert len(res.steps) == 2
    assert res.steps[0]["success"] is True
    assert res.steps[1]["success"] is True


# ── 5. Registry search + list + categories ──────────────────────────────────
def test_registry_search_and_categories():
    import skills.builtin  # noqa: F401
    items = SKILL_REGISTRY.search("ppt")
    assert any(i["name"] == "guizang_ppt" for i in items)
    summary = SKILL_REGISTRY.categories_summary()
    # Built-in skills cover at least content + image + research + video + marketing.
    assert summary.get("content", 0) >= 3
    assert summary.get("research", 0) >= 1
    assert summary.get("marketing", 0) >= 1
    assert len(SKILL_REGISTRY) >= 10