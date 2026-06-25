"""P4-8-W1: 10 built-in skill tests (one per skill)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pytest  # noqa: E402

import skills.builtin  # noqa: F401, E402  -- side-effect: register
from skills.context import SkillContext  # noqa: E402
from skills.orchestrator import SkillOrchestrator  # noqa: E402
from skills.registry import SKILL_REGISTRY  # noqa: E402


def _run(skill_name: str, inputs: dict) -> dict:
    orch = SkillOrchestrator()
    ctx = SkillContext.create(user_id="test", inputs=inputs)
    res = asyncio.run(orch.run_skill(skill_name, ctx, inputs=inputs))
    return res.to_dict()


def test_01_guizang_ppt():
    out = _run("guizang_ppt", {"topic": "AI 工厂"})
    assert out["success"] is True
    assert out["data"]["topic"] == "AI 工厂"
    assert len(out["data"]["deck"]["slides"]) >= 4


def test_02_guizang_social_card():
    out = _run("guizang_social_card", {"text": "AI 改变了数据工厂的产能"})
    assert out["success"] is True
    assert out["data"]["count"] >= 1
    assert all("hook" in c for c in out["data"]["cards"])


def test_03_awesome_gpt_image():
    out = _run("awesome_gpt_image", {"category": "portrait", "n": 3})
    assert out["success"] is True
    assert out["data"]["count"] == 3
    assert all("prompt" in p for p in out["data"]["prompts"])


def test_04_humanizer_zh():
    out = _run("humanizer_zh", {"text": "综上所述，AI 改变了世界。值得注意的是，在当今时代…"})
    assert out["success"] is True
    body = out["data"]
    assert body["humanized"] != body["original"]
    assert body["ai_tells_after"] <= body["ai_tells_before"]


def test_05_deep_research():
    out = _run("deep_research", {"topic": "AGI 风险", "findings": 3})
    assert out["success"] is True
    assert out["data"]["source_count"] == 0  # no search_fn wired
    assert len(out["data"]["findings"]) == 3
    assert all("claim" in f and "source" in f for f in out["data"]["findings"])


def test_06_anything_to_notebooklm():
    out = _run("anything_to_notebooklm", {
        "source": "Transformer 是一种注意力机制驱动的神经网络架构。它在 2017 年由 Vaswani 等人提出。"
    })
    assert out["success"] is True
    briefing = out["data"]["briefing"]
    assert briefing["tldr"]
    assert isinstance(briefing["topics"], list)
    assert isinstance(briefing["faq"], list) and len(briefing["faq"]) >= 1


def test_07_wewrite():
    out = _run("wewrite", {"topic": "AI 工厂的下一站", "length": 800})
    assert out["success"] is True
    assert len(out["data"]["titles"]) >= 3
    assert len(out["data"]["outline"]) >= 3
    assert out["data"]["cta"].startswith("👉")


def test_08_youtube_clipper():
    out = _run("youtube_clipper", {
        "transcript": "[00:00] 介绍 AI\n[02:30] 第一个关键点\n[05:00] 第二个关键点\n[07:30] 第三个关键点",
        "clips": 3,
    })
    assert out["success"] is True
    assert len(out["data"]["clips"]) == 3
    assert all("start" in c and "end" in c for c in out["data"]["clips"])


def test_09_oh_story_claudecode():
    out = _run("oh_story_claudecode", {"genre": "科幻", "keywords": "AI 觉醒", "count": 4})
    assert out["success"] is True
    ideas = out["data"]["ideas"]
    assert len(ideas) == 4
    # Sorted by heat_score desc.
    scores = [float(i["heat_score"]) for i in ideas]
    assert scores == sorted(scores, reverse=True)


def test_10_marketingskills():
    out = _run("marketingskills", {
        "tool": "landing_page",
        "product": "AI 工厂",
        "audience": "数据团队",
    })
    assert out["success"] is True
    body = out["data"]["output"]
    assert body["headline"]
    assert body["cta"]
    # Switch tools.
    out2 = _run("marketingskills", {"tool": "seo_brief", "product": "AI 工厂"})
    assert out2["success"] is True
    assert "keywords" in out2["data"]["output"]


# Bonus: registry must contain all 10.
def test_registry_has_all_10_builtins():
    expected = {
        "guizang_ppt", "guizang_social_card", "awesome_gpt_image",
        "humanizer_zh", "deep_research", "anything_to_notebooklm",
        "wewrite", "youtube_clipper", "oh_story_claudecode", "marketingskills",
    }
    assert expected.issubset(set(SKILL_REGISTRY.names())), \
        f"missing: {expected - set(SKILL_REGISTRY.names())}"