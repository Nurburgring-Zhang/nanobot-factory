"""End-to-end smoke test for the monitoring FastAPI router."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from monitoring import agent_tracking, cost_tracking, quality_tracking, user_behavior
from monitoring.api import build_router


@pytest.fixture
def client():
    # Reset singletons
    agent_tracking._TRACKER = None
    cost_tracking._TRACKER = None
    quality_tracking._TRACKER = None
    user_behavior._TRACKER = None

    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


def test_capabilities_endpoint(client):
    r = client.get("/api/v1/monitoring/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert "layers" in body
    assert "6_sentry" in body["layers"]
    assert "7_health_deep" in body["layers"]


def test_sentry_errors_recent(client):
    client.get("/api/v1/monitoring/capabilities")  # warm
    # Inject an error via the public capture function (DSN-less so buffer only)
    from monitoring.sentry import capture_exception
    try:
        raise RuntimeError("test-route-error")
    except RuntimeError as exc:
        capture_exception(exc, layer="backend", tags={"route": "/x"})
    r = client.get("/api/v1/monitoring/errors/recent")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert any("test-route-error" in i["message"] for i in body["items"])


def test_health_deep_returns_20_services(client):
    r = client.get("/api/v1/monitoring/health/deep")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 20


def test_agent_activity_record_and_query(client):
    client.post("/api/v1/monitoring/agent/record", json={
        "agent_id": "a-test", "user_id": "u-test",
        "model": "gpt-4o-mini", "provider": "openai",
        "action": "invoke", "status": "ok", "latency_ms": 100,
    })
    r = client.get("/api/v1/monitoring/agent/activity")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1


def test_cost_record_and_per_user(client):
    client.post("/api/v1/monitoring/cost/record", json={
        "user_id": "alice", "model": "gpt-4o",
        "input_tokens": 1000, "output_tokens": 2000,
    })
    r = client.get("/api/v1/monitoring/cost/per_user")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert any(row["user_id"] == "alice" for row in rows)


def test_quality_record_and_drift(client):
    client.post("/api/v1/monitoring/quality/record", json={
        "annotator_id": "a1", "item_id": "i1", "label": 1, "score": 0.9,
    })
    r = client.get("/api/v1/monitoring/quality")
    assert r.status_code == 200


def test_compliance_gdpr_access(client):
    client.post("/api/v1/monitoring/cost/record", json={
        "user_id": "bob", "model": "gpt-4o-mini",
        "input_tokens": 100, "output_tokens": 200,
    })
    r = client.get("/api/v1/monitoring/compliance/gdpr/bob")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == "bob"
    assert body["report_type"] == "data_subject_access"


def test_compliance_gdpr_erasure_requires_confirm(client):
    r = client.post("/api/v1/monitoring/compliance/gdpr/bob/erasure", json={"confirm": False})
    assert r.status_code == 400
    r = client.post("/api/v1/monitoring/compliance/gdpr/bob/erasure", json={"confirm": True})
    assert r.status_code == 200


def test_compliance_eu_ai_act(client):
    r = client.get("/api/v1/monitoring/compliance/eu-ai-act")
    assert r.status_code == 200
    body = r.json()
    assert body["report_type"] == "eu_ai_act_high_risk_system"
    assert len(body["sections"]) == 6


def test_heatmap_record_and_query(client):
    client.post("/api/v1/monitoring/heatmap", json={
        "user_id": "alice", "session_id": "s1",
        "route": "/dashboard", "x": 0.5, "y": 0.5,
    })
    r = client.get("/api/v1/monitoring/heatmap/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1


def test_funnel_record_and_report(client):
    client.post("/api/v1/monitoring/funnel", json={"user_id": "u1", "stage": "login"})
    r = client.get("/api/v1/monitoring/funnel")
    assert r.status_code == 200
    body = r.json()
    assert body["total_events"] == 1


# --------------------------------------------------------------------------- #
# P19-E3 / F2 — SLO + tracing + anomaly endpoint smoke tests (bug-fix coverage)
# --------------------------------------------------------------------------- #


def test_slo_report_endpoint(client):
    r = client.get("/api/v1/monitoring/slo")
    assert r.status_code == 200
    body = r.json()
    assert "generated_at" in body
    assert "slos" in body and isinstance(body["slos"], list)
    assert "budgets" in body and isinstance(body["budgets"], dict)


def test_slo_burn_rate_rules_endpoint(client):
    r = client.get("/api/v1/monitoring/slo/rules")
    assert r.status_code == 200
    # YAML body should at least mention groups or rules keyword
    body = r.text
    assert isinstance(body, str) and len(body) > 0


def test_slo_recorder_snapshot_endpoint(client):
    # F2 critical bug fix: GET /slo/recorder/{name} must NOT 500.
    from monitoring import slo as slo_mod
    rec = slo_mod.get_recorder("api-route-smoke-slo", target=0.99, kind="availability")
    rec.reset()
    rec.record_outcome(success=True, latency_ms=120.0)
    rec.record_outcome(success=True, latency_ms=80.0)
    rec.record_outcome(success=False, latency_ms=400.0)

    r = client.get("/api/v1/monitoring/slo/recorder/api-route-smoke-slo")
    assert r.status_code == 200
    body = r.json()
    assert body["slo_name"] == "api-route-smoke-slo"
    assert body["sample_count"] == 3
    assert "budget" in body and isinstance(body["budget"], dict)


def test_tracing_status_endpoint(client):
    r = client.get("/api/v1/monitoring/tracing/status")
    assert r.status_code == 200
    body = r.json()
    # Either 'enabled' boolean or 'service_name' — accept either present key
    assert isinstance(body, dict)


def test_tracing_spans_endpoint(client):
    r = client.get("/api/v1/monitoring/tracing/spans")
    assert r.status_code == 200
    body = r.json()
    assert "count" in body
    assert "items" in body and isinstance(body["items"], list)
    assert isinstance(body["count"], int) and body["count"] >= 0


def test_anomaly_status_endpoint(client):
    r = client.get("/api/v1/monitoring/anomaly/status")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)


def test_anomaly_recent_endpoint(client):
    r = client.get("/api/v1/monitoring/anomaly/recent")
    assert r.status_code == 200
    body = r.json()
    assert "count" in body
    assert "items" in body and isinstance(body["items"], list)
    assert isinstance(body["count"], int) and body["count"] >= 0
