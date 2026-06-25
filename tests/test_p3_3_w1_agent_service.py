"""P3-3-W1 smoke test — agent-service boots + 15 agent types + tasks + memory.

Run from: D:\\Hermes\\生产平台\\nanobot-factory\\
    D:\\ComfyUI\\.ext\\python.exe -m pytest tests/test_p3_3_w1_agent_service.py -v --tb=short
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

# Ensure imdf.* / services.* are importable
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
_PROJECT_ROOT = _BACKEND.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

os.environ.setdefault("IMDF_DATA_DIR", str(_BACKEND / "imdf" / "data"))
os.environ.setdefault("JWT_SECRET", "test-secret-DO-NOT-USE-IN-PROD-abcdef123456")
os.environ.setdefault("IMDF_TEST_MODE", "1")

from fastapi.testclient import TestClient  # noqa: E402


# ── App boot ────────────────────────────────────────────────────────────────
def _client():
    mod = importlib.import_module("services.agent_service.main")
    # Reset module-level singletons between tests
    for mod_name in [
        "services.agent_service.store",
        "services.agent_service.memory",
        "services.agent_service.scheduler",
        "services.agent_service.executor",
    ]:
        m = importlib.import_module(mod_name)
        for fn_name in (
            "reset_store_singleton",
            "reset_memory_for_test",
            "reset_scheduler_for_test",
            "reset_executor_for_test",
        ):
            fn = getattr(m, fn_name, None)
            if fn is not None:
                fn()
    # Also reset imdf.engines.agent_router singleton
    try:
        eng = importlib.import_module("imdf.engines.agent_router")
        if hasattr(eng, "reset_agent_router_for_test"):
            eng.reset_agent_router_for_test()
    except Exception:  # noqa: BLE001
        pass
    return TestClient(mod.app)


# ── /healthz + root ────────────────────────────────────────────────────────
def test_agent_service_healthz():
    c = _client()
    r = c.get("/healthz")
    assert r.status_code == 200, r.text
    body = r.json()
    # P4-1-W1: common.create_app prefixes service with project name; allow either form
    assert "agent_service" in (body.get("service") or "") or body.get("service") == "agent-service"
    print(f"  agent-service /healthz: {body.get('status')}")


def test_agent_service_root():
    c = _client()
    r = c.get("/")
    assert r.status_code == 200
    body = r.json()
    assert "agent_service" in (body.get("service") or "") or body.get("service") == "agent-service"
    # P4-5-W2: 15 baseline + 7 generation agents = 22
    assert len(body["agent_types"]) >= 15
    assert "/api/v1/agents" in body["endpoints"]["agents"][0]


# ── /api/v1/agents ─────────────────────────────────────────────────────────
def test_list_agents_returns_15_plus_generation():
    c = _client()
    r = c.get("/api/v1/agents")
    assert r.status_code == 200
    body = r.json()
    # P4-5-W2: 15 baseline + 7 generation agents
    assert body["count"] >= 15
    types = {a["id"] for a in body["agents"]}
    expected = {
        "requirement_parser", "data_collection", "cleaning", "prelabel",
        "fine_annotation", "review", "scoring", "filtering", "export",
        "evaluation", "badcase_analysis", "feedback", "memory",
        "scheduling", "quality",
    }
    # original 15 still present
    assert expected.issubset(types), f"missing baseline={expected - types}"
    # P4-5-W2: 7 new generation agents present
    generation = {
        "generation_director", "generation_storyboard", "generation_character",
        "generation_image", "generation_video", "generation_voice", "generation_qa",
    }
    assert generation.issubset(types), f"missing generation={generation - types}"
    print(f"  agent-service: {body['count']} types OK (15 baseline + 7 generation)")


def test_list_agent_types():
    c = _client()
    r = c.get("/api/v1/agents/types")
    assert r.status_code == 200
    body = r.json()
    # P4-5-W2: 15 baseline + 7 generation agents
    assert body["count"] >= 15
    assert "cleaning" in body["types"]
    assert "generation_image" in body["types"]


def test_get_agent_detail():
    c = _client()
    r = c.get("/api/v1/agents/cleaning")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "cleaning"
    assert body["name"] == "清洗"
    assert body["default_mode"] in ("full_auto", "semi_auto", "manual")
    assert body["downstream_service"] == "cleaning-service"


def test_get_agent_unknown_404():
    c = _client()
    r = c.get("/api/v1/agents/nonexistent_agent")
    assert r.status_code == 404


# ── /api/v1/agent_tasks ───────────────────────────────────────────────────
def test_create_task_full_auto():
    c = _client()
    r = c.post(
        "/api/v1/agent_tasks",
        json={
            "agent_type": "cleaning",
            "payload": {"items": [1, 2, 3]},
            "run_inline": True,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task"]["agent_type"] == "cleaning"
    assert body["task"]["status"] in ("succeeded", "running")
    assert body["result"]["ok"] is True
    print(f"  cleaning task id={body['task']['task_id']} status={body['task']['status']}")


def test_create_task_unknown_404():
    c = _client()
    r = c.post(
        "/api/v1/agent_tasks",
        json={"agent_type": "totally_made_up_agent", "payload": {}},
    )
    assert r.status_code == 404


def test_get_task_by_id():
    c = _client()
    create = c.post(
        "/api/v1/agent_tasks",
        json={"agent_type": "scoring", "payload": {"x": 1}},
    )
    assert create.status_code == 200
    tid = create.json()["task"]["task_id"]
    g = c.get(f"/api/v1/agent_tasks/{tid}")
    assert g.status_code == 200
    assert g.json()["task_id"] == tid


def test_task_list_and_stats():
    c = _client()
    # create a couple of tasks
    c.post("/api/v1/agent_tasks", json={"agent_type": "evaluation", "payload": {}})
    c.post("/api/v1/agent_tasks", json={"agent_type": "export", "payload": {}})
    lst = c.get("/api/v1/agent_tasks?limit=10")
    assert lst.status_code == 200
    assert lst.json()["count"] >= 2
    stats = c.get("/api/v1/agent_tasks/stats")
    assert stats.status_code == 200
    assert "pending" in stats.json()
    assert "total" in stats.json()


def test_task_cancel():
    c = _client()
    create = c.post(
        "/api/v1/agent_tasks",
        json={"agent_type": "review", "payload": {}},
    )
    tid = create.json()["task"]["task_id"]
    cancel = c.post(f"/api/v1/agent_tasks/{tid}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"


def test_task_retry_after_failure():
    c = _client()
    create = c.post(
        "/api/v1/agent_tasks",
        json={"agent_type": "filtering", "payload": {}},
    )
    tid = create.json()["task"]["task_id"]
    # Manually mark as failed first
    from services.agent_service.store import get_store, TaskStatus
    get_store().transition(tid, TaskStatus.FAILED.value, error="manual_fail")
    retry = c.post(f"/api/v1/agent_tasks/{tid}/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "pending"
    assert retry.json()["error"] is None


def test_run_agent_inline_semi_auto():
    """A semi_auto task should return ``awaiting_human=True``."""
    c = _client()
    r = c.post(
        "/api/v1/agents/prelabel/run",
        json={"payload": {"samples": 5}, "mode": "semi_auto"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["ok"] is True
    assert body["result"]["mode"] == "semi_auto"
    assert body["result"].get("awaiting_human") is True


def test_run_agent_inline_manual():
    """A manual task should return ``draft_only=True``."""
    c = _client()
    r = c.post(
        "/api/v1/agents/fine_annotation/run",
        json={"payload": {"samples": 3}, "mode": "manual"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["ok"] is True
    assert body["result"]["mode"] == "manual"
    assert body["result"].get("draft_only") is True


# ── /api/v1/agent_memory ──────────────────────────────────────────────────
def test_memory_upsert_and_get():
    c = _client()
    put = c.put(
        "/api/v1/agent_memory/test_scope/sample_key",
        json={"value": {"note": "hello"}},
    )
    assert put.status_code == 200
    g = c.get("/api/v1/agent_memory/test_scope/sample_key")
    assert g.status_code == 200
    assert g.json()["value"]["note"] == "hello"


def test_memory_list():
    c = _client()
    c.put("/api/v1/agent_memory/scope_x/key_a", json={"value": 1})
    c.put("/api/v1/agent_memory/scope_x/key_b", json={"value": 2})
    lst = c.get("/api/v1/agent_memory/scope_x")
    assert lst.status_code == 200
    body = lst.json()
    assert body["scope"] == "scope_x"
    assert body["count"] >= 2


# ── /api/v1/scheduler/state ───────────────────────────────────────────────
def test_scheduler_state():
    c = _client()
    r = c.get("/api/v1/scheduler/state")
    assert r.status_code == 200
    body = r.json()
    assert "buckets" in body
    # After running a task, we should see the bucket for its downstream service.
    c.post(
        "/api/v1/agent_tasks",
        json={"agent_type": "cleaning", "payload": {}, "run_inline": True},
    )
    r2 = c.get("/api/v1/scheduler/state")
    assert r2.status_code == 200
    # cleaning-service bucket should exist
    assert "cleaning-service" in r2.json()["buckets"]


# ── imdf/engines/agent_router ────────────────────────────────────────────
def test_engines_agent_router():
    eng = importlib.import_module("imdf.engines.agent_router")
    eng.reset_agent_router_for_test()
    router = eng.get_agent_router()
    decision = router.route("cleaning", {"x": 1})
    assert decision.eligible is True
    assert decision.downstream_service == "cleaning-service"
    bad = router.route("totally_made_up_agent", {})
    assert bad.eligible is False
    assert "unknown_agent_type" in bad.reason
    routes = router.list_routes()
    assert len(routes) == 15
    print(f"  imdf.engines.agent_router: 15 routes OK")
