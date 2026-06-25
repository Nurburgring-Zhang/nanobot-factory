"""P4-7-W2 tests — 12 service multimodal smoke.

Test count (>= 3 required, we ship 5):
1. test_list_capabilities      — 12 services registered
2. test_run_smoke_one          — user_service smoke returns face recognition
3. test_run_smoke_all          — all 12 smokes run without exception
4. test_services_endpoint      — /services returns 12 entries
5. test_service_smoke_endpoint — /services/{name}/smoke returns stub
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from imdf.multimodal.routes import build_router
from imdf.multimodal.service_integration import SERVICES, list_capabilities, run_smoke, run_all_smokes


EXPECTED_SERVICES = {
    "user_service",
    "asset_service",
    "annotation_service",
    "cleaning_service",
    "scoring_service",
    "dataset_service",
    "evaluation_service",
    "agent_service",
    "workflow_service",
    "notification_service",
    "search_service",
    "collection_service",
}


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


def test_list_capabilities():
    caps = list_capabilities()
    assert len(caps) == 12
    names = {c["service"] for c in caps}
    assert names == EXPECTED_SERVICES


def test_run_smoke_one():
    r = run_smoke("user_service", {"user_id": "u-1", "image_url": "stub://face/u-1.jpg"})
    assert r["service"] == "user_service"
    assert r["capability"] == "face_recognition_clip"
    assert r["score"] > 0


def test_run_smoke_all():
    results = run_all_smokes()
    assert len(results) == 12
    assert set(results.keys()) == EXPECTED_SERVICES
    # every smoke has the same shape
    for name, r in results.items():
        assert r["service"] == name
        assert r["capability"]
        assert r["_meta"]["elapsed_ms"] >= 0


def test_services_endpoint(client):
    r = client.get("/api/v1/multimodal/services")
    assert r.status_code == 200
    services = r.json()["services"]
    assert len(services) == 12
    names = {s["service"] for s in services}
    assert names == EXPECTED_SERVICES


def test_service_smoke_endpoint(client):
    r = client.post("/api/v1/multimodal/services/scoring_service/smoke", json={"payload": {"asset_id": "a-1"}})
    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "scoring_service"
    assert data["capability"] == "aesthetic_scoring"
    assert "aesthetic_score" in data

    # unknown service → 404
    r404 = client.post("/api/v1/multimodal/services/nope_service/smoke", json={"payload": {}})
    assert r404.status_code == 404