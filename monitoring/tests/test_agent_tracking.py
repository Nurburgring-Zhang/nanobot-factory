"""Layer 8 — Agent tracking tests."""

from __future__ import annotations

import asyncio
import pytest

from monitoring import agent_tracking as agent_mod


@pytest.fixture(autouse=True)
def _reset_tracker():
    agent_mod._TRACKER = None
    yield
    agent_mod._TRACKER = None


def test_record_creates_activity():
    tracker = agent_mod.AgentTracker()
    rec = tracker.record(
        agent_id="agent-1", task_id="t-1", user_id="alice",
        model="gpt-4o-mini", provider="openai", latency_ms=42.0,
        input_tokens=10, output_tokens=20, cost_usd=0.0001,
    )
    assert rec.agent_id == "agent-1"
    assert rec.model == "gpt-4o-mini"
    assert len(tracker.buffer) == 1


def test_recent_filter_by_user_and_status():
    tracker = agent_mod.AgentTracker()
    tracker.record(agent_id="a", user_id="alice", status="ok")
    tracker.record(agent_id="a", user_id="bob", status="error")
    tracker.record(agent_id="a", user_id="alice", status="error")
    alice_err = tracker.recent(limit=10, user_id="alice", status="error")
    assert len(alice_err) == 1
    assert alice_err[0]["user_id"] == "alice"


def test_stats_aggregate_by_model_and_status():
    tracker = agent_mod.AgentTracker()
    tracker.record(agent_id="a", user_id="alice", model="gpt-4o", status="ok", cost_usd=0.01)
    tracker.record(agent_id="b", user_id="bob", model="claude-3-5-sonnet", status="error", cost_usd=0.02)
    tracker.record(agent_id="a", user_id="alice", model="gpt-4o", status="ok", cost_usd=0.03)
    s = tracker.stats()
    assert s["by_status"]["ok"] == 2
    assert s["by_status"]["error"] == 1
    assert s["by_model"]["gpt-4o"] == 2
    assert s["total_cost_usd"] >= 0.05


@pytest.mark.asyncio
async def test_subscribe_receives_recorded_events():
    tracker = agent_mod.AgentTracker()
    q = await tracker.subscribe()
    tracker.record(agent_id="a", user_id="alice")
    ev = await asyncio.wait_for(q.get(), timeout=1.0)
    assert ev["agent_id"] == "a"
    await tracker.unsubscribe(q)


def test_buffer_respects_max_size():
    tracker = agent_mod.AgentTracker(buffer_size=5)
    for i in range(10):
        tracker.record(agent_id=f"a-{i}")
    assert len(tracker.buffer) == 5
