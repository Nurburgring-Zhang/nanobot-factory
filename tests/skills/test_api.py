"""P4-8-W1: HTTP endpoint tests — TestClient against agent_service."""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
if str(_BACKEND.parent) not in sys.path:
    sys.path.insert(0, str(_BACKEND.parent))

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def client():
    """Build a TestClient against the agent_service FastAPI app.

    Skills are mounted at startup via the lifespan context; this fixture
    yields once and reuses the client across all endpoint tests.
    """
    try:
        from fastapi.testclient import TestClient
        from services.agent_service.main import app
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"agent_service app not importable: {exc}")
    with TestClient(app) as c:
        yield c


def test_list_skills(client):
    r = client.get("/api/v1/skills")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 10
    names = {it["name"] for it in body["items"]}
    assert "guizang_ppt" in names
    assert "wewrite" in names


def test_get_skill_detail(client):
    r = client.get("/api/v1/skills/guizang_ppt")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "guizang_ppt"
    assert body["category"] == "content"


def test_get_skill_not_found(client):
    r = client.get("/api/v1/skills/__nope__")
    assert r.status_code == 404


def test_run_skill_endpoint(client):
    r = client.post(
        "/api/v1/skills/guizang_ppt/run",
        json={"inputs": {"topic": "AI Factory", "slides": 4}, "user_id": "tester"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["skill_name"] == "guizang_ppt"
    assert body["data"]["slide_count"] == 4


def test_run_chain_endpoint(client):
    r = client.post(
        "/api/v1/skills/orchestrator/run",
        json={
            "steps": [
                {"skill": "guizang_ppt", "inputs": {"topic": "AGI", "slides": 3}},
                {"skill": "humanizer_zh"},
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert len(body["steps"]) == 2


def test_run_auto_route(client):
    r = client.post(
        "/api/v1/skills/orchestrator/auto",
        json={"query": "我想做 PPT", "inputs": {"topic": "AI"}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # auto-route should at least not 500.
    assert "success" in body


def test_marketplace_install_and_rate(client):
    r = client.post("/api/v1/skills/guizang_ppt/install")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True

    r2 = client.post(
        "/api/v1/skills/guizang_ppt/rate",
        json={"stars": 5, "review": "nice", "user_id": "qa"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["success"] is True


def test_obsidian_wiki_roundtrip(client):
    r = client.post(
        "/api/v1/obsidian/wiki",
        json={"slug": "test-page", "title": "Test", "content": "Hello [[alpha]] #demo"},
    )
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["slug"] == "test-page"
    assert "alpha" in page["outgoing_links"]
    assert "demo" in page["tags"]

    g = client.get("/api/v1/obsidian/wiki/graph")
    assert g.status_code == 200
    graph = g.json()
    assert any(n["id"] == "test-page" for n in graph["nodes"])

    d = client.delete("/api/v1/obsidian/wiki/test-page")
    assert d.status_code == 200