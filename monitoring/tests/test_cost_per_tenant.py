"""P19-D1 — cost-per-tenant tests.

Covers:
* CostRecord.tenant_id field accepts arbitrary tenant strings.
* CostTracker.per_tenant() aggregates correctly by tenant_id.
* 10 tenants × 100 cost events → top-10 tenant ranking is exact.
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from monitoring import cost_tracking as cost_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_tracker(monkeypatch):
    monkeypatch.setattr(cost_mod, "_TRACKER", cost_mod.CostTracker(), raising=False)
    yield


def test_cost_record_accepts_tenant_id():
    t = cost_mod.get_tracker()
    rec = t.record(user_id="u", tenant_id="acme-corp",
                   model="gpt-4o-mini", input_tokens=100, output_tokens=50)
    assert rec.tenant_id == "acme-corp"
    # Default tenant_id is "default".
    rec2 = t.record(user_id="u", model="gpt-4o-mini", input_tokens=1, output_tokens=1)
    assert rec2.tenant_id == "default"


def test_per_tenant_aggregates_correctly():
    t = cost_mod.get_tracker()
    # tenant A: 3 records totalling $0.003
    for _ in range(3):
        t.record(user_id="u", tenant_id="A", model="gpt-4o-mini",
                 input_tokens=1000, output_tokens=500)
    # tenant B: 2 records totalling $0.030
    for _ in range(2):
        t.record(user_id="u", tenant_id="B", model="gpt-4o",
                 input_tokens=1000, output_tokens=500)
    # tenant C: 1 record $0.000015
    t.record(user_id="u", tenant_id="C", model="gpt-4o-mini",
             input_tokens=100, output_tokens=0)
    rows = t.per_tenant()
    assert len(rows) == 3
    # Sorted descending by cost_usd.
    assert rows[0]["tenant_id"] == "B"
    assert rows[1]["tenant_id"] == "A"
    assert rows[2]["tenant_id"] == "C"
    assert rows[0]["cost_usd"] > rows[1]["cost_usd"] > rows[2]["cost_usd"]
    # counts
    assert rows[0]["calls"] == 2
    assert rows[1]["calls"] == 3
    assert rows[2]["calls"] == 1
    # unique_users
    assert rows[0]["unique_users"] == 1


def test_per_tenant_10_tenants_100_events_each():
    """Stress: 10 tenants × 100 cost events → top-10 ranking is exact."""
    t = cost_mod.get_tracker()
    tenant_ids = [f"tenant-{i:02d}" for i in range(10)]
    # Pre-set deterministic per-tenant cost: tenant i costs $0.001 * (i+1) per call.
    expected_costs = {tid: 0.0 for tid in tenant_ids}
    for tid in tenant_ids:
        multiplier = int(tid.split("-")[1]) + 1
        for _ in range(100):
            rec = t.record(user_id=f"user-{tid}", tenant_id=tid,
                           model="gpt-4o-mini", input_tokens=0, output_tokens=0,
                           cost_usd=0.001 * multiplier)
            expected_costs[tid] += rec.cost_usd
    rows = t.per_tenant(limit=10)
    assert len(rows) == 10
    # Order must be descending by cost_usd.
    costs = [r["cost_usd"] for r in rows]
    assert costs == sorted(costs, reverse=True)
    # Top tenant is the highest-multiplier one.
    assert rows[0]["tenant_id"] == "tenant-09"
    # Each row's calls is exactly 100.
    for r in rows:
        assert r["calls"] == 100
    # Round-tripped totals match expected within rounding (8-decimal precision).
    for r in rows:
        expected = round(expected_costs[r["tenant_id"]], 6)
        actual = round(r["cost_usd"], 6)
        assert abs(expected - actual) < 1e-5


def test_per_tenant_respects_limit():
    t = cost_mod.get_tracker()
    for i in range(5):
        t.record(user_id="u", tenant_id=f"t-{i}", cost_usd=float(i + 1))
    rows = t.per_tenant(limit=3)
    assert len(rows) == 3


def test_per_tenant_empty_buffer():
    t = cost_mod.get_tracker()
    assert t.per_tenant() == []


def test_per_tenant_unique_users_counted():
    t = cost_mod.get_tracker()
    for u in ("alice", "bob", "carol"):
        t.record(user_id=u, tenant_id="X", cost_usd=0.01)
    t.record(user_id="alice", tenant_id="Y", cost_usd=0.02)
    rows = t.per_tenant()
    by_id = {r["tenant_id"]: r for r in rows}
    assert by_id["X"]["unique_users"] == 3
    assert by_id["Y"]["unique_users"] == 1