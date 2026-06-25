"""P4-5-W2: IterativeSession unit tests (>=4)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest


# ── Path bootstrap so ``backend.services.asset_service.*`` resolves ────────
_REPO = Path(__file__).resolve().parents[2]
_BACKEND = _REPO / "backend"
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """Redirect the iteration JSON store to a tmp dir for test isolation."""
    monkeypatch.setenv("ITERATION_DATA_DIR", str(tmp_path / "iter"))
    # Reset the module-level singletons so they pick up the new env.
    import services.asset_service.iteration.session as sess_mod
    import services.asset_service.iteration.agents as agents_mod
    import services.asset_service.iteration.consistency as cons_mod
    import services.asset_service.iteration.store as store_mod

    sess_mod._STORE = None
    agents_mod._ORCHESTRATOR = None
    cons_mod._WORKFLOW = None
    store_mod._LOCK.__init__()  # type: ignore[attr-defined]
    yield


# ── 1. Session CRUD + multi-turn dialogue ────────────────────────────────
def test_session_crud_and_multi_turn():
    from services.asset_service.iteration.session import (
        SessionState,
        get_session_store,
    )

    store = get_session_store()
    row = store.create_session(
        owner_id="u1",
        project_id="p1",
        modality="image",
        initial_prompt="a red dragon",
        params={"steps": 30},
        title="dragons",
    )
    sid = row["session_id"]
    assert row["state"] == SessionState.DRAFT.value
    assert len(row["prompt_versions"]) == 1
    assert row["prompt_versions"][0]["text"] == "a red dragon"

    # ── Multi-turn dialogue ─────────────────────────────────────────
    pv2 = store.iterate_prompt(sid, "a red dragon breathing fire", note="add FX")
    assert pv2 is not None
    pv3 = store.iterate_prompt(sid, "a red dragon breathing fire in a snowy mountain")
    assert pv3 is not None
    assert pv2.parent_version_id == row["prompt_versions"][0]["version_id"]

    sess = store.get_session(sid)
    assert sess is not None
    assert sess["state"] == SessionState.REVIEW.value
    assert len(sess["prompt_versions"]) == 3


# ── 2. Asset + feedback + state machine ─────────────────────────────────
def test_session_assets_and_feedback_and_finalize():
    from services.asset_service.iteration.session import (
        SessionState,
        get_session_store,
    )

    store = get_session_store()
    row = store.create_session(owner_id="u2", project_id="p1", modality="image", initial_prompt="x")
    sid = row["session_id"]
    pv_id = row["prompt_versions"][0]["version_id"]

    asset = store.add_asset(sid, pv_id, modality="image", url="/tmp/a.png", seed=42)
    assert asset and asset["session_id"] == sid

    fb = store.add_feedback(sid, rating=5, text="great", asset_id=asset["asset_id"])
    assert fb and fb["rating"] == 5

    # second feedback should not regress state
    store.add_feedback(sid, rating=2, text="actually meh")
    sess = store.get_session(sid)
    assert sess["state"] == SessionState.REVIEW.value

    # finalize
    store.finalize(sid)
    sess2 = store.get_session(sid)
    assert sess2["state"] == SessionState.FINAL.value
    assert len(store.list_assets(sid)) == 1
    assert len(store.list_feedback(sid)) == 2


# ── 3. A/B testing + best pick ──────────────────────────────────────────
def test_ab_testing_and_pick_best():
    from services.asset_service.iteration.session import (
        SessionState,
        get_session_store,
    )

    store = get_session_store()
    row = store.create_session(owner_id="u3", project_id="p1", modality="image", initial_prompt="hero")
    sid = row["session_id"]
    pv_id = row["prompt_versions"][0]["version_id"]

    ab = store.start_ab(
        sid,
        parent_prompt_version_id=pv_id,
        variants=[
            {"text": "v1", "params": {}, "note": "A"},
            {"text": "v2", "params": {}, "note": "B"},
            {"text": "v3", "params": {}, "note": "C"},
        ],
    )
    assert ab is not None
    assert ab["status"] == "running"
    assert len(ab["variants"]) == 3

    variants = ab["variants"]
    scores = {variants[0]["version_id"]: 0.7, variants[1]["version_id"]: 0.92, variants[2]["version_id"]: 0.85}
    store.score_ab(ab["ab_id"], scores)
    picked = store.pick_best(ab["ab_id"])
    assert picked["winner_variant_id"] == variants[1]["version_id"]
    assert picked["status"] == "decided"

    sess = store.get_session(sid)
    assert sess["best_variant_id"] == variants[1]["version_id"]
    assert sess["state"] == SessionState.FINAL.value
    # winner was promoted into the session prompt history
    assert any(pv["version_id"] == variants[1]["version_id"] for pv in sess["prompt_versions"])


# ── 4. Discard + cascade delete ─────────────────────────────────────────
def test_discard_and_cascade_delete():
    from services.asset_service.iteration.session import (
        SessionState,
        get_session_store,
    )

    store = get_session_store()
    row = store.create_session(owner_id="u4", project_id="p2", modality="video", initial_prompt="ocean")
    sid = row["session_id"]
    pv_id = row["prompt_versions"][0]["version_id"]
    store.add_asset(sid, pv_id, modality="video", url="/tmp/o.mp4")
    store.add_feedback(sid, rating=1, text="no")
    store.iterate_prompt(sid, "ocean at night")

    # Discard
    store.discard(sid)
    sess = store.get_session(sid)
    assert sess["state"] == SessionState.DISCARDED.value

    # Cannot iterate a discarded session
    pv_after = store.iterate_prompt(sid, "ocean in storm")
    assert pv_after is None

    # Cascade delete
    assert store.delete_session(sid) is True
    assert store.get_session(sid) is None
    assert store.list_assets(sid) == []
    assert store.list_feedback(sid) == []
    assert store.list_ab(sid) == []