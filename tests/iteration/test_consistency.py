"""P4-5-W2: Consistency workflow tests (>=4)."""
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


# ── 1. 5-round auto-refinement converges to target ──────────────────────
def test_5_round_refinement_converges():
    from services.asset_service.iteration.consistency import (
        ConsistencyConfig,
        get_workflow,
    )

    # Custom scorer that gradually improves with each regen call.
    state = {"calls": 0}

    def improving_scorer(_asset):
        state["calls"] += 1
        # Cap at 0.95 so the workflow always converges in ≤5 rounds.
        return min(0.95, 0.5 + state["calls"] * 0.05)

    wf = get_workflow()
    report = wf.run(
        project_id="proj-converge",
        brief={"script": "single scene"},
        config=ConsistencyConfig(target_score=0.85, max_rounds=5, nsfw_threshold=0.40),
        scorer=improving_scorer,
    )
    assert report.passed is True
    assert report.final_avg_score >= 0.85
    assert report.final_avg_score >= report.initial_avg_score
    assert len(report.rounds) <= 5
    assert report.asset_count >= 1


# ── 2. NSFW fallback path triggers when many assets score low ─────────
def test_nsfw_fallback_used_count():
    from services.asset_service.iteration.consistency import (
        ConsistencyConfig,
        get_workflow,
    )

    def very_low_scorer(_a):
        return 0.05

    wf = get_workflow()
    report = wf.run(
        project_id="proj-nsfw2",
        brief={"script": "single scene"},
        config=ConsistencyConfig(target_score=0.99, max_rounds=3, nsfw_threshold=0.5),
        scorer=very_low_scorer,
    )
    assert report.fallback_used_count >= 1
    assert report.final_avg_score > report.initial_avg_score
    # At least one round used the fallback model
    assert any(r.fallback_used for r in report.rounds)


# ── 3. Incremental: only re-generates changed shots ─────────────────────
def test_incremental_only_changed_shots():
    from services.asset_service.iteration.consistency import (
        ConsistencyConfig,
        get_workflow,
    )

    # First scorer pass: high scores for shot s1, low for s2.
    def biased(asset):
        shot = asset.get("shot_id", "")
        return 0.9 if "s1" in shot else 0.1

    wf = get_workflow()
    report = wf.run(
        project_id="proj-incr",
        brief={"script": "s1.\n\ns2."},
        config=ConsistencyConfig(target_score=0.85, max_rounds=3, nsfw_threshold=0.5, increment_only=True),
        scorer=biased,
    )
    assert report.rounds, "expected ≥1 round"
    # Each round should regenerate only the bad shots (those containing 's2' in the shot_id).
    for r in report.rounds:
        assert all("s2" in s for s in r.regenerated_shots), r.regenerated_shots


# ── 4. History persists + report can be re-fetched ────────────────────
def test_history_and_get_report():
    from services.asset_service.iteration.consistency import (
        ConsistencyConfig,
        get_workflow,
    )

    wf = get_workflow()
    r1 = wf.run(
        project_id="proj-A",
        brief={"script": "scene A"},
        config=ConsistencyConfig(target_score=0.5, max_rounds=1),
    )
    r2 = wf.run(
        project_id="proj-B",
        brief={"script": "scene B"},
        config=ConsistencyConfig(target_score=0.5, max_rounds=1),
    )
    hist_all = wf.history(limit=10)
    assert len(hist_all) == 2
    hist_a = wf.history(project_id="proj-A", limit=10)
    assert len(hist_a) == 1
    assert hist_a[0]["project_id"] == "proj-A"
    fetched = wf.get("proj-A", r1.started_at)
    assert fetched is not None
    assert fetched["project_id"] == "proj-A"
    assert fetched["final_avg_score"] == r1.final_avg_score