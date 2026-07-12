"""Layer 9 — Cost tracking tests."""

from __future__ import annotations

import pytest

from monitoring import cost_tracking as cost_mod


@pytest.fixture(autouse=True)
def _reset_tracker():
    cost_mod._TRACKER = None
    yield
    cost_mod._TRACKER = None


def test_compute_cost_known_model():
    cost = cost_mod.compute_cost_usd("gpt-4o-mini", 1000, 2000)
    expected = (1000 / 1000.0) * 0.00015 + (2000 / 1000.0) * 0.0006
    assert abs(cost - expected) < 1e-9


def test_compute_cost_unknown_model_uses_zero():
    cost = cost_mod.compute_cost_usd("totally-unknown-model-xyz", 1000, 1000)
    assert cost == 0.0


def test_record_persists_to_buffer():
    t = cost_mod.CostTracker()
    rec = t.record(user_id="alice", model="gpt-4o", input_tokens=100, output_tokens=200)
    assert rec.cost_usd > 0
    assert len(t.buffer) == 1


def test_per_user_aggregation():
    t = cost_mod.CostTracker()
    t.record(user_id="alice", model="gpt-4o", input_tokens=100, output_tokens=200)
    t.record(user_id="alice", model="gpt-4o-mini", input_tokens=50, output_tokens=50)
    t.record(user_id="bob", model="claude-3-haiku", input_tokens=500, output_tokens=500)
    rows = t.per_user()
    assert len(rows) == 2
    users = {r["user_id"] for r in rows}
    assert users == {"alice", "bob"}


def test_per_model_aggregation():
    t = cost_mod.CostTracker()
    t.record(user_id="alice", model="gpt-4o", input_tokens=100, output_tokens=200)
    t.record(user_id="bob", model="gpt-4o-mini", input_tokens=100, output_tokens=200)
    rows = t.per_model()
    assert len(rows) == 2


def test_per_task_aggregation():
    t = cost_mod.CostTracker()
    t.record(user_id="alice", task_id="t-A", model="gpt-4o", input_tokens=100, output_tokens=200)
    t.record(user_id="alice", task_id="t-A", model="gpt-4o", input_tokens=100, output_tokens=200)
    t.record(user_id="alice", task_id="t-B", model="gpt-4o-mini", input_tokens=50, output_tokens=50)
    rows = t.per_task()
    by_id = {r["task_id"]: r for r in rows}
    assert by_id["t-A"]["calls"] == 2
    assert by_id["t-B"]["calls"] == 1


def test_set_pricing_overrides_default():
    t = cost_mod.CostTracker()
    t.set_pricing("custom-model", input_per_1k=1.0, output_per_1k=2.0)
    cost = t.record(user_id="alice", model="custom-model", input_tokens=1000, output_tokens=1000).cost_usd
    assert cost == 3.0


def test_stats_reports_pricing_table():
    t = cost_mod.CostTracker()
    t.record(user_id="alice", model="gpt-4o-mini", input_tokens=100, output_tokens=200)
    s = t.stats()
    assert "pricing_table" in s
    assert "gpt-4o-mini" in s["pricing_table"]
    assert s["total_cost_usd"] > 0
