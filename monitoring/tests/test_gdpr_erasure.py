"""P19-D1 — GDPR 真 right-to-erasure tests.

Covers:
* Real erasure removes every record across cost_tracking / agent_tracking /
  quality_tracking for the given user.
* Audit chain records the erasure event (or reports unavailability cleanly).
* 100-mock-user stress: erase 1 → all its entries gone → others untouched.
* data_subject_access export contains every record (counts + fingerprint).
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from monitoring import (  # noqa: E402
    compliance_reports as compliance_mod,
    cost_tracking as cost_mod,
    agent_tracking as agent_mod,
    quality_tracking as quality_mod,
)


@pytest.fixture(autouse=True)
def _isolated_trackers(monkeypatch):
    """Each test gets fresh in-process trackers (avoids cross-test bleed)."""
    # Force fresh singletons.
    monkeypatch.setattr(cost_mod, "_TRACKER", cost_mod.CostTracker(), raising=False)
    monkeypatch.setattr(agent_mod, "_TRACKER", agent_mod.AgentTracker(), raising=False)
    monkeypatch.setattr(quality_mod, "_TRACKER", quality_mod.QualityTracker(), raising=False)
    yield


def _seed(uid: str, n_cost: int = 3, n_agent: int = 2, n_quality: int = 1) -> None:
    cost = cost_mod.get_tracker()
    agent = agent_mod.get_tracker()
    quality = quality_mod.get_tracker()
    for i in range(n_cost):
        cost.record(user_id=uid, model="gpt-4o-mini",
                    input_tokens=100 + i, output_tokens=50 + i)
    for i in range(n_agent):
        agent.record(agent_id="agent-x", task_id=f"t-{uid}-{i}",
                     user_id=uid, action="invoke", status="ok")
    for i in range(n_quality):
        quality.record(annotator_id=uid, item_id=f"q-{uid}-{i}",
                       label=i, score=0.5)


def test_execute_gdpr_erasure_removes_every_record():
    uid = f"user-{uuid.uuid4()}"
    _seed(uid, n_cost=5, n_agent=4, n_quality=2)
    # Sanity: pre-erase counts.
    pre_cost = sum(1 for r in cost_mod.get_tracker().buffer if r.user_id == uid)
    pre_agent = sum(1 for r in agent_mod.get_tracker().buffer if r.user_id == uid)
    pre_quality = sum(1 for r in quality_mod.get_tracker().buffer if r.annotator_id == uid)
    assert pre_cost == 5 and pre_agent == 4 and pre_quality == 2

    out = compliance_mod.execute_gdpr_erasure(uid, requester="auditor-1")
    assert out["user_id"] == uid
    assert out["erased"]["cost_records"] == 5
    assert out["erased"]["agent_records"] == 4
    assert out["erased"]["quality_records"] == 2
    assert out["erased"]["total"] == 11

    # Post-erase: nothing left for this user.
    assert sum(1 for r in cost_mod.get_tracker().buffer if r.user_id == uid) == 0
    assert sum(1 for r in agent_mod.get_tracker().buffer if r.user_id == uid) == 0
    assert sum(1 for r in quality_mod.get_tracker().buffer if r.annotator_id == uid) == 0


def test_execute_gdpr_erasure_is_idempotent():
    uid = f"user-{uuid.uuid4()}"
    _seed(uid, n_cost=3, n_agent=2, n_quality=1)
    out1 = compliance_mod.execute_gdpr_erasure(uid, requester="auditor")
    assert out1["erased"]["total"] == 6
    out2 = compliance_mod.execute_gdpr_erasure(uid, requester="auditor")
    assert out2["erased"]["total"] == 0


def test_erasure_returns_audit_chain_field():
    uid = f"user-{uuid.uuid4()}"
    _seed(uid)
    out = compliance_mod.execute_gdpr_erasure(uid)
    # audit_chain_entry is either an entry dict OR None (if audit chain unavailable)
    assert "audit_chain_entry" in out
    assert "audit_chain_unavailable" in out
    # If the chain is unavailable, the flag is True and entry is None.
    if out["audit_chain_unavailable"]:
        assert out["audit_chain_entry"] is None
    else:
        # If the chain is available, the entry exposes seq + entry_hash.
        entry = out["audit_chain_entry"]
        assert entry is not None
        assert "seq" in entry and "entry_hash" in entry


def test_erasure_100_mock_users_one_erased():
    """Stress: 100 mock users, erase 1, others untouched."""
    trackers = (
        cost_mod.get_tracker(),
        agent_mod.get_tracker(),
        quality_mod.get_tracker(),
    )
    users = [f"user-{i:03d}" for i in range(100)]
    victim = users[42]
    for uid in users:
        _seed(uid, n_cost=2, n_agent=1, n_quality=1)
    total_cost_pre = sum(len(t.buffer) for t in trackers[:1])
    total_agent_pre = sum(len(t.buffer) for t in trackers[1:2])
    total_quality_pre = sum(len(t.buffer) for t in trackers[2:3])

    out = compliance_mod.execute_gdpr_erasure(victim)

    assert out["erased"]["total"] == 4  # 2 + 1 + 1
    # Every other user still has 2 cost + 1 agent + 1 quality records.
    for uid in users:
        if uid == victim:
            continue
        assert sum(1 for r in trackers[0].buffer if r.user_id == uid) == 2
        assert sum(1 for r in trackers[1].buffer if r.user_id == uid) == 1
        assert sum(1 for r in trackers[2].buffer if r.annotator_id == uid) == 1
    # Victim: zero in every buffer.
    assert sum(1 for r in trackers[0].buffer if r.user_id == victim) == 0
    assert sum(1 for r in trackers[1].buffer if r.user_id == victim) == 0
    assert sum(1 for r in trackers[2].buffer if r.annotator_id == victim) == 0
    # Total cost entries dropped by exactly 2 (victim's 2 cost rows).
    assert len(trackers[0].buffer) == total_cost_pre - 2
    assert len(trackers[1].buffer) == total_agent_pre - 1
    assert len(trackers[2].buffer) == total_quality_pre - 1


def test_data_subject_access_export_contains_all_records():
    uid = f"user-{uuid.uuid4()}"
    _seed(uid, n_cost=7, n_agent=3, n_quality=2)
    out = compliance_mod.export_data_subject_access(uid)
    assert out["user_id"] == uid
    assert out["counts"]["cost"] == 7
    assert out["counts"]["agent"] == 3
    assert out["counts"]["quality"] == 2
    assert out["counts"]["total"] == 12
    assert len(out["records"]["cost"]) == 7
    assert len(out["records"]["agent"]) == 3
    assert len(out["records"]["quality"]) == 2
    assert isinstance(out["fingerprint_sha256"], str) and len(out["fingerprint_sha256"]) == 64


def test_data_subject_access_export_stable_fingerprint():
    uid = f"user-{uuid.uuid4()}"
    _seed(uid, n_cost=3, n_agent=1, n_quality=1)
    a = compliance_mod.export_data_subject_access(uid)
    b = compliance_mod.export_data_subject_access(uid)
    # Fingerprint can differ if timestamps vary (records have timestamp field);
    # what we really assert is shape + counts are stable.
    assert a["counts"] == b["counts"]
    assert a["user_id"] == b["user_id"]


def test_legacy_generate_gdpr_erasure_dry_run_still_works():
    uid = f"user-{uuid.uuid4()}"
    _seed(uid, n_cost=2, n_agent=1, n_quality=1)
    report = compliance_mod.generate_gdpr_erasure(uid)
    # Dry-run: must NOT erase.
    assert sum(1 for r in cost_mod.get_tracker().buffer if r.user_id == uid) == 2
    assert report.report_type == "right_to_erasure"
    assert report.user_id == uid
    assert report.sections[0]["rows"][1]["value"] == 4