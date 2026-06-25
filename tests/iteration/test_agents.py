"""P4-5-W2: MultiAgent orchestrator tests (>=5)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


_REPO = Path(__file__).resolve().parents[2]
_BACKEND = _REPO / "backend"
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ITERATION_DATA_DIR", str(tmp_path / "iter"))
    import services.asset_service.iteration.session as sess_mod
    import services.asset_service.iteration.agents as agents_mod
    import services.asset_service.iteration.consistency as cons_mod

    sess_mod._STORE = None
    agents_mod._ORCHESTRATOR = None
    cons_mod._WORKFLOW = None
    yield


# ── 1. List agents (registry has 7 entries) ─────────────────────────────
def test_list_agents_seven_entries():
    from services.asset_service.iteration.agents import AgentRole, list_agents

    agents = list_agents()
    assert len(agents) == 7
    roles = {a["role"] for a in agents}
    expected = {
        AgentRole.DIRECTOR.value,
        AgentRole.STORYBOARD.value,
        AgentRole.CHARACTER.value,
        AgentRole.IMAGE.value,
        AgentRole.VIDEO.value,
        AgentRole.VOICE.value,
        AgentRole.QA.value,
    }
    assert roles == expected


# ── 2. Orchestrator builds a complete pipeline ──────────────────────────
def test_orchestrator_runs_all_agents():
    from services.asset_service.iteration.agents import (
        AgentRole,
        AgentStatus,
        get_orchestrator,
    )

    orch = get_orchestrator()
    brief = {
        "script": "Scene 1: a hero walks into a tavern.\n\nScene 2: the hero meets a wizard.",
        "characters": ["hero", "wizard"],
        "shots_per_scene": 2,
    }
    character_pool = {
        "hero": {"character_id": "hero", "reference_url": "/characters/hero.png"},
        "wizard": {"character_id": "wizard", "reference_url": "/characters/wizard.png"},
    }
    report = orch.run_sync(brief, character_pool=character_pool)
    assert report.ok
    roles_done = {r["role"]: r["status"] for r in report.agent_results}
    for role in AgentRole:
        assert roles_done[role.value] == AgentStatus.DONE.value, f"{role} not done: {roles_done}"

    # storyboard built
    assert len(report.storyboard["scenes"]) >= 1
    # assets produced for image + video
    image_assets = [a for a in report.asset_pool if a["modality"] == "image"]
    video_assets = [a for a in report.asset_pool if a["modality"] == "video"]
    assert len(image_assets) >= 1
    assert len(video_assets) == len(image_assets)
    # characters bound
    assert "hero" in report.character_state
    assert "wizard" in report.character_state
    # QA scored
    assert len(report.qa_scores) >= 1


# ── 3. Blackboard publishes messages ──────────────────────────────────
def test_blackboard_event_log_and_assets():
    from services.asset_service.iteration.agents import (
        AgentRole,
        Blackboard,
        DirectorAgent,
        ImageAgent,
        QAAgent,
        StoryboardAgent,
    )

    bb = Blackboard(run_id="r1", brief={"script": "single scene"})
    DirectorAgent(bb).run()
    StoryboardAgent(bb).run()
    ImageAgent(bb).run()
    QAAgent(bb).run()
    assert any(e.kind == "info" for e in bb.events)
    assert any(e.kind == "asset" for e in bb.events)
    assert any(e.kind == "score" for e in bb.events)
    # asset_pool mirrors published assets
    asset_msgs = [e for e in bb.events if e.kind == "asset"]
    assert {a["asset_id"] for a in bb.asset_pool} == {m.payload["asset_id"] for m in asset_msgs}


# ── 4. History persists across instances ───────────────────────────────
def test_history_persists_via_store():
    from services.asset_service.iteration.agents import get_orchestrator

    orch = get_orchestrator()
    orch.run_sync(brief={"script": "x"})
    orch.run_sync(brief={"script": "y"})
    hist = orch.history(limit=10)
    assert len(hist) == 2
    # newest first
    assert hist[0]["started_at"] >= hist[1]["started_at"]


# ── 5. Custom scorer flags NSFW + falls back to other model ────────────
def test_custom_scorer_and_fallback_path_via_consistency():
    from services.asset_service.iteration.consistency import (
        ConsistencyConfig,
        get_workflow,
    )

    def low_scorer(_asset: dict) -> float:
        # Every asset below the nsfw threshold → fallback path triggered.
        return 0.1

    wf = get_workflow()
    report = wf.run(
        project_id="proj-nsfw",
        brief={"script": "single scene"},
        config=ConsistencyConfig(target_score=0.95, max_rounds=3, nsfw_threshold=0.85),
        scorer=low_scorer,
    )
    assert report.fallback_used_count >= 1
    # final avg must be lifted by the +0.05 fallback bump
    assert report.final_avg_score > report.initial_avg_score
    assert report.asset_count >= 1
    assert isinstance(report.rounds, list)