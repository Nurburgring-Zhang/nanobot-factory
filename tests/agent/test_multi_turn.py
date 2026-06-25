"""P4-3-W1: Multi-turn session manager tests.

Run from project root:
    D:\\ComfyUI\\.ext\\python.exe -m pytest tests/agent/test_multi_turn.py -v --tb=short
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

# Path setup (mirror tests/test_p3_3_w1_agent_service.py)
_BACKEND = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_PROJECT_ROOT = _BACKEND.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("IMDF_DATA_DIR", str(_BACKEND / "imdf" / "data"))
os.environ.setdefault("JWT_SECRET", "test-secret-DO-NOT-USE-IN-PROD-abcdef123456")
os.environ.setdefault("IMDF_TEST_MODE", "1")

from fastapi.testclient import TestClient  # noqa: E402

from services.agent_service.memory.multi_turn import (  # noqa: E402
    MultiTurnSessionManager,
    SessionContext,
    TokenUsage,
    TokenUsageTracker,
    get_session_manager,
    reset_session_manager_for_test,
)


# ── helpers ────────────────────────────────────────────────────────────────
def _client() -> TestClient:
    """Reset every W1 singleton before constructing the TestClient."""
    for mod_name in (
        "services.agent_service.memory.multi_turn",
        "services.agent_service.instructions",
        "services.agent_service.variables",
        "services.agent_service.tools.registry",
        "services.agent_service.loader",
        "services.agent_service.memory",
        "services.agent_service.store",
        "services.agent_service.scheduler",
        "services.agent_service.executor",
    ):
        m = importlib.import_module(mod_name)
        for fn_name in (
            "reset_session_manager_for_test",
            "reset_instructions_for_test",
            "reset_variable_store_for_test",
            "reset_tool_registry_for_test",
            "reset_loader_for_test",
            "reset_memory_for_test",
            "reset_store_singleton",
            "reset_scheduler_for_test",
            "reset_executor_for_test",
        ):
            fn = getattr(m, fn_name, None)
            if fn is not None:
                fn()
    try:
        eng = importlib.import_module("imdf.engines.agent_router")
        if hasattr(eng, "reset_agent_router_for_test"):
            eng.reset_agent_router_for_test()
    except Exception:  # noqa: BLE001
        pass
    return TestClient(importlib.import_module("services.agent_service.main").app)


# ── Tests ──────────────────────────────────────────────────────────────────
def test_session_create_and_get():
    """POST /api/v1/agent/sessions creates a session; GET retrieves it."""
    c = _client()
    create = c.post("/api/v1/agent/sessions", json={"user_id": "alice"})
    assert create.status_code == 200, create.text
    body = create.json()
    sid = body["session_id"]
    assert sid.startswith("ses-")
    assert body["user_id"] == "alice"
    assert body["messages"] == []
    assert body["summary"] == ""

    g = c.get(f"/api/v1/agent/sessions/{sid}")
    assert g.status_code == 200
    assert g.json()["session_id"] == sid
    print(f"  session create+get sid={sid}")


def test_session_add_messages_and_window():
    """Adding more than the cap drops the oldest non-system message."""
    c = _client()
    create = c.post("/api/v1/agent/sessions", json={"user_id": "bob"})
    sid = create.json()["session_id"]

    # Cap to 5 to make the test fast
    c.post(
        f"/api/v1/agent/sessions/{sid}/messages",
        json={"role": "system", "content": "you are helpful"},
    )
    # Set a small cap via metadata
    mgr = get_session_manager()
    ctx = mgr.get(sid)
    assert ctx is not None
    ctx.metadata["max_messages"] = 5

    for i in range(8):
        c.post(
            f"/api/v1/agent/sessions/{sid}/messages",
            json={"role": "user", "content": f"msg-{i}"},
        )

    listing = c.get(f"/api/v1/agent/sessions/{sid}/messages")
    assert listing.status_code == 200
    msgs = listing.json()["messages"]
    # System message is preserved; the oldest non-system got dropped
    assert len(msgs) <= 5
    assert msgs[0]["role"] == "system"
    # The most recent user message survives
    assert any("msg-7" in m["content"] for m in msgs)
    # The very first user message is gone
    assert not any("msg-0" in m["content"] for m in msgs)
    print(f"  session window capped to {len(msgs)} messages (cap=5)")


def test_session_summary_offline():
    """Default summariser returns a deterministic offline summary."""
    c = _client()
    sid = c.post("/api/v1/agent/sessions", json={"user_id": "carol"}).json()["session_id"]
    c.post(
        f"/api/v1/agent/sessions/{sid}/messages",
        json={"role": "user", "content": "What's the weather in Paris?"},
    )
    c.post(
        f"/api/v1/agent/sessions/{sid}/messages",
        json={"role": "assistant", "content": "Sunny, 22°C, light breeze."},
    )
    r = c.post(f"/api/v1/agent/sessions/{sid}/summary")
    assert r.status_code == 200, r.text
    summary = r.json()["summary"]
    assert summary
    assert "Paris" in summary or "weather" in summary
    # And the summary is now persisted on the session
    g = c.get(f"/api/v1/agent/sessions/{sid}")
    assert "Paris" in g.json()["summary"] or "weather" in g.json()["summary"]
    print(f"  session summary length={len(summary)} chars")


def test_session_token_usage():
    """record_usage accumulates per session + per user + global."""
    c = _client()
    sid = c.post("/api/v1/agent/sessions", json={"user_id": "dave"}).json()["session_id"]
    mgr = get_session_manager()
    mgr.record_usage(sid, prompt=100, completion=50, model="gpt-4o-mini")
    mgr.record_usage(sid, prompt=200, completion=100, model="gpt-4o-mini")
    u = c.get(f"/api/v1/agent/sessions/{sid}/usage")
    assert u.status_code == 200
    usage = u.json()["usage"]
    assert usage["prompt_tokens"] == 300
    assert usage["completion_tokens"] == 150
    assert usage["total_tokens"] == 450
    assert usage["last_model"] == "gpt-4o-mini"

    snap = c.get("/api/v1/agent/usage").json()["snapshot"]
    assert "global" in snap
    assert "user:dave" in snap
    assert snap["global"]["total_tokens"] >= 450
    print(f"  session usage: prompt={usage['prompt_tokens']} completion={usage['completion_tokens']}")


def test_session_delete_and_listing():
    """DELETE removes the session; LIST skips it."""
    c = _client()
    sid_a = c.post("/api/v1/agent/sessions", json={"user_id": "eve"}).json()["session_id"]
    sid_b = c.post("/api/v1/agent/sessions", json={"user_id": "eve"}).json()["session_id"]
    listing = c.get("/api/v1/agent/sessions?user_id=eve")
    assert listing.status_code == 200
    sids = [s["session_id"] for s in listing.json()["sessions"]]
    assert sid_a in sids and sid_b in sids

    d = c.delete(f"/api/v1/agent/sessions/{sid_a}")
    assert d.status_code == 200
    assert d.json()["deleted"] is True

    # GET should 404
    g = c.get(f"/api/v1/agent/sessions/{sid_a}")
    assert g.status_code == 404
    # LIST excludes the deleted one
    sids_after = [
        s["session_id"] for s in c.get("/api/v1/agent/sessions?user_id=eve").json()["sessions"]
    ]
    assert sid_a not in sids_after
    assert sid_b in sids_after
    print(f"  session delete: {sid_a} removed, {sid_b} remains")
