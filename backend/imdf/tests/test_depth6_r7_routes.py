"""VDP-2026 Depth-6 — R7 Deployment Readiness HTTP route tests.

These tests exercise the ``/api/v1/deploy_r7/*`` endpoints that were
added in depth-6. The original ``readiness.py`` only emitted an
info-log on canvas_web boot, leaving the catalog invisible to external
processes. The new routes mount the catalog so Prometheus / Grafana
/ status pages can poll it.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("JWT_SECRET", "depth6-test-secret-key")


@pytest.fixture(scope="module")
def client():
    """Build a TestClient against the real canvas_web app, ensuring
    ``imdf/`` is at sys.path[0] (the shared backend/tests/conftest
    strips it for back-compat).
    """
    imdf_root = _BACKEND.resolve()
    while imdf_root in sys.path:
        sys.path.remove(imdf_root)
    sys.path.insert(0, str(imdf_root))

    from perf_r9.primitives import reset_for_test
    reset_for_test()

    from fastapi.testclient import TestClient
    import imdf.api.canvas_web as cw
    return TestClient(cw.app)


def test_r7_health_returns_ok(client):
    r = client.get("/api/v1/deploy_r7/health")
    assert r.status_code == 200, r
    body = r.json()
    assert body["status"] == "ok", body
    assert body["total_endpoints"] >= 30, body
    assert "R1" in body["modules"]
    assert "R6" in body["modules"]


def test_r7_readiness_reports_total_endpoints(client):
    r = client.get("/api/v1/deploy_r7/readiness")
    assert r.status_code == 200, r
    body = r.json()
    assert body["total_endpoints"] >= 30, body
    assert "R1" in body["modules"]
    assert body["mounted_via_http"] is True, body


def test_r7_endpoints_returns_catalog(client):
    r = client.get("/api/v1/deploy_r7/endpoints")
    assert r.status_code == 200, r
    body = r.json()
    assert body["count"] == len(body["endpoints"])
    assert body["count"] >= 30
    # Every entry has the canonical shape.
    for e in body["endpoints"]:
        assert set(e.keys()) >= {"module", "method", "path"}


def test_r7_endpoints_by_module_groups_correctly(client):
    r = client.get("/api/v1/deploy_r7/endpoints_by_module")
    assert r.status_code == 200, r
    body = r.json()
    assert "R1" in body
    assert "R6" in body
    assert isinstance(body["R1"], list)
    assert len(body["R1"]) >= 1


def test_r7_audit_detects_missing_endpoints(client):
    # Send a partial mounted-paths list. The audit should report
    # catalog endpoints whose prefix is missing.
    r = client.post(
        "/api/v1/deploy_r7/audit",
        json={"mounted_paths": ["/api/v1/capabilities_v2", "/api/v1/dataflow"]},
    )
    assert r.status_code == 200, r
    body = r.json()
    assert body["catalogued"] >= 30
    # Both prefixes are present in the catalog, so matched >= 2.
    assert body["matched"] >= 2
    # The audit also reports the missing endpoints.
    assert isinstance(body["missing"], list)


def test_r7_audit_with_full_catalog_matches_all(client):
    """If we send every catalogued prefix, ``missing`` should be empty."""
    from deploy_r7.readiness import ENDPOINT_CATALOGUE
    # Use just the unique top-level prefixes (longest-prefix match).
    prefixes = sorted({"/" + e["path"].split("/")[1] for e in ENDPOINT_CATALOGUE if "/" in e["path"]})
    r = client.post(
        "/api/v1/deploy_r7/audit",
        json={"mounted_paths": prefixes},
    )
    assert r.status_code == 200, r
    body = r.json()
    assert body["missing"] == [], body


def test_r7_helm_summary_renders(client):
    r = client.get("/api/v1/deploy_r7/helm_summary")
    assert r.status_code == 200, r
    body = r.json()
    assert "summary_md" in body, body
    assert "VDP-2026" in body["summary_md"], body["summary_md"]
    assert "endpoints" in body["summary_md"].lower(), body["summary_md"]
