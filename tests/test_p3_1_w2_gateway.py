"""P3-1-W2: API Gateway integration tests (TestClient + httpx mock).

These tests run the gateway in-process via ``fastapi.testclient.TestClient`` —
no live uvicorn required, no canvas_web.py boot cost.  We mock the upstream
by pointing ``routes.yaml`` at an httpx ``MockTransport`` so we can assert
forwarding, JWT handling, rate-limit and circuit-breaker behaviour in a
hermetic, fast (<5s) suite.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — must come before any backend.* import.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ROOT))

# Use a deterministic JWT secret across gateway + tests so the gateway's
# ``_validate_jwt`` accepts tokens minted by the test helper.
os.environ.setdefault("JWT_SECRET", "test-gateway-secret-do-not-use-in-prod")
os.environ.setdefault("JWT_SECRET_KEY", os.environ["JWT_SECRET"])

from fastapi.testclient import TestClient  # noqa: E402

from jose import jwt as jose_jwt  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GATEWAY_ROUTES_YAML = _BACKEND / "gateway" / "routes.yaml"


def _import_app_for_tests():
    """Import the gateway app fresh and return (create_app, module).

    We patch the routes file to point at a non-existent local port so
    the upstream httpx call deterministically fails-fast unless we
    also patch ``ProxyClient._client`` with a MockTransport.
    """
    import importlib
    if "backend.gateway.main" in sys.modules:
        del sys.modules["backend.gateway.main"]
    if "backend.gateway.proxy" in sys.modules:
        del sys.modules["backend.gateway.proxy"]
    if "backend.gateway" in sys.modules:
        del sys.modules["backend.gateway"]
    main = importlib.import_module("backend.gateway.main")
    return main


def _make_token(sub: str = "user-1", **extra) -> str:
    payload = {
        "sub": sub,
        "iat": int(time.time()),
        "exp": int(time.time()) + 600,
    }
    payload.update(extra)
    return jose_jwt.encode(
        payload, os.environ["JWT_SECRET"], algorithm="HS256"
    )


def _make_test_client() -> Tuple[TestClient, Any]:
    """Build a TestClient with a fresh app + an httpx MockTransport that
    records every upstream call and returns canned responses."""
    from httpx import MockTransport, Response

    main = _import_app_for_tests()
    app = main.create_app(routes_path=GATEWAY_ROUTES_YAML)

    # The 12 services all share one upstream URL (http://127.0.0.1:8765/internal).
    # We replace the gateway's httpx.AsyncClient with a mock transport so we
    # can verify forwarding without booting the monolith.
    upstream_calls: List[Dict[str, Any]] = []

    def handler(request: httpx_Request) -> Response:
        # Record the *raw* URL the gateway sent — that lets the test
        # assert the /internal prefix is present.  We then strip /internal
        # from the path we put in the response body, emulating the
        # monolith's _StripInternalPrefixMiddleware behaviour.
        raw_url = str(request.url)
        url_for_log = raw_url
        url_for_body = raw_url
        if "/internal" in url_for_body:
            url_for_body = url_for_body.replace("/internal", "", 1)
        upstream_calls.append({
            "method": request.method,
            "url": url_for_log,  # raw — keeps /internal so the assertion can verify it
            "headers": dict(request.headers),
            "body": request.content,
        })
        # Mimic the monolith's path-strip behaviour and return a small JSON.
        return Response(
            200,
            json={
                "ok": True,
                "forwarded": {
                    "method": request.method,
                    "path": url_for_body.split("127.0.0.1:8765", 1)[-1]
                             if "127.0.0.1:8765" in url_for_body else url_for_body,
                },
                "actor": "stub-upstream",
            },
            headers={"X-Stub-Source": "gateway-test"},
        )

    # Import here so the type alias is available.
    import httpx as _httpx
    mock_client = _httpx.AsyncClient(transport=MockTransport(handler), timeout=5.0)
    app.state.proxy._client = mock_client

    return TestClient(app), upstream_calls


# httpx is imported above as _httpx but the type-hint alias keeps ruff happy.
httpx_Request = Any


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_module_imports():
    """Gateway package must import without errors."""
    main = _import_app_for_tests()
    assert main.app is not None
    assert main.create_app is not None


def test_routes_yaml_loaded_with_12_services():
    """routes.yaml must define exactly 12 microservice routes."""
    cfg = _load_routes(GATEWAY_ROUTES_YAML)
    services = cfg.get("services", [])
    assert len(services) == 12, f"expected 12 services, got {len(services)}"

    expected_prefixes = {
        "/api/v1/users", "/api/v1/auth", "/api/v1/assets",
        "/api/v1/datasets", "/api/v1/annotation", "/api/v1/crowd",
        "/api/v1/models", "/api/v1/billing", "/api/v1/export",
        "/api/v1/audit", "/api/v1/tenant", "/api/queue",
    }
    actual_prefixes = {s["prefix"] for s in services}
    assert actual_prefixes == expected_prefixes, (
        f"prefix mismatch:\n  expected={expected_prefixes}\n  actual={actual_prefixes}"
    )


def test_healthz_returns_200():
    """Gateway exposes a public health probe (no auth)."""
    client, _ = _make_test_client()
    r = client.get("/healthz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "gateway"


def test_gw_routes_endpoint_lists_all_12():
    """Management endpoint surfaces the compiled routes."""
    client, _ = _make_test_client()
    r = client.get("/_gw/routes")
    assert r.status_code == 200, r.text
    routes = r.json()["routes"]
    assert len(routes) == 12
    # require_auth attribute preserved
    auth_required = [x for x in routes if x["require_auth"]]
    no_auth = [x for x in routes if not x["require_auth"]]
    assert len(auth_required) == 10, f"10 routes should require auth, got {len(auth_required)}"
    assert len(no_auth) == 2, f"auth + queue should be public, got {len(no_auth)}"
    assert {x["name"] for x in no_auth} == {"auth-service", "queue-service"}


def test_missing_jwt_returns_401():
    """Protected routes must reject requests without a Bearer token."""
    client, calls = _make_test_client()
    r = client.get("/api/v1/users/me")
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "missing_bearer_token"
    assert calls == [], "upstream must NOT be called when auth fails"


def test_invalid_jwt_returns_401():
    """Bad signature must be rejected."""
    client, calls = _make_test_client()
    r = client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "invalid_or_expired_token"
    assert calls == [], "upstream must NOT be called when JWT is invalid"


def test_valid_jwt_proxies_to_upstream_with_internal_prefix():
    """A valid JWT must let the request through; gateway appends /internal."""
    client, calls = _make_test_client()
    token = _make_token(sub="user-42")
    r = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["actor"] == "stub-upstream"
    # The gateway MUST have appended /internal prefix when forwarding
    assert len(calls) == 1
    forwarded = calls[0]
    assert forwarded["method"] == "GET"
    assert forwarded["url"].endswith("/internal/api/v1/users/me"), (
        f"expected /internal prefix, got {forwarded['url']}"
    )
    # Response header from upstream should propagate
    assert r.headers.get("X-Stub-Source") == "gateway-test"
    # X-Upstream-Service + X-Request-ID injected
    assert r.headers.get("X-Upstream-Service") == "user-service"
    assert r.headers.get("X-Request-ID", "").startswith("req_")


def test_public_route_skips_auth():
    """auth-service has require_auth=False so login works without a token."""
    client, calls = _make_test_client()
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "demo", "password": "x"},
    )
    assert r.status_code == 200, r.text
    assert len(calls) == 1
    # Forwarded to /internal prefix
    assert calls[0]["url"].endswith("/internal/api/v1/auth/login")


def test_default_route_catches_unknown_paths():
    """Catch-all must forward unknown prefixes (with auth) to the monolith."""
    client, calls = _make_test_client()
    token = _make_token()
    r = client.get(
        "/api/v1/nonexistent/foo",
        headers={"Authorization": f"Bearer {token}"},
    )
    # default route returns 200 from stub
    assert r.status_code == 200, r.text
    assert len(calls) == 1
    assert calls[0]["url"].endswith("/internal/api/v1/nonexistent/foo")
    assert r.headers.get("X-Upstream-Service") == "default"


def test_x_request_id_is_propagated_when_supplied():
    """Client-supplied X-Request-ID must round-trip to upstream."""
    client, calls = _make_test_client()
    token = _make_token()
    rid = "req_smoke_1234"
    r = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}", "X-Request-ID": rid},
    )
    assert r.status_code == 200, r.text
    assert calls[0]["headers"]["x-request-id"] == rid
    assert r.headers["X-Request-ID"] == rid


def test_rate_limit_triggers_429_after_burst():
    """After exhausting the token bucket, the gateway must respond 429."""
    # Force a small bucket for this test
    main = _import_app_for_tests()
    cfg = main._load_routes(GATEWAY_ROUTES_YAML)
    cfg.setdefault("gateway", {}).setdefault("rate_limit", {})
    cfg["gateway"]["rate_limit"]["capacity"] = 5
    cfg["gateway"]["rate_limit"]["refill_per_second"] = 0.001  # ~0 tokens/s
    test_yaml = _ROOT / "tests" / "_tmp_routes_rl.yaml"
    test_yaml.write_text(_dump_yaml(cfg), encoding="utf-8")
    try:
        app = main.create_app(routes_path=test_yaml)
        client = TestClient(app)
        # 5 calls fit in the bucket — auth failures don't consume a token? Actually
        # the rate-limit middleware runs BEFORE the JWT check, so all requests
        # (including 401) consume a token.
        statuses: List[int] = []
        for _ in range(8):
            r = client.get("/api/v1/users/me")  # no JWT → 401 + consumes 1 token
            statuses.append(r.status_code)
        # We expect a mix of 401 (while tokens remain) and 429 (once exhausted).
        assert 429 in statuses, f"expected 429 in {statuses}"
        # The first few MUST be 401 (rate-limit allowed → JWT rejected)
        assert statuses[:5] == [401] * 5, f"first 5 should be 401, got {statuses[:5]}"
        # Later ones should be 429
        assert all(s == 429 for s in statuses[5:]), (
            f"after bucket empty, all should be 429, got {statuses[5:]}"
        )
    finally:
        if test_yaml.exists():
            test_yaml.unlink()


def test_circuit_breaker_opens_after_failures():
    """After N consecutive failures, the breaker must open (return 503)."""
    from httpx import MockTransport, Response
    main = _import_app_for_tests()

    # Use a 2-failure threshold for speed.
    cfg = main._load_routes(GATEWAY_ROUTES_YAML)
    cfg.setdefault("gateway", {}).setdefault("circuit_breaker", {})
    cfg["gateway"]["circuit_breaker"]["failure_threshold"] = 2
    cfg["gateway"]["circuit_breaker"]["reset_timeout_seconds"] = 60
    test_yaml = _ROOT / "tests" / "_tmp_routes_cb.yaml"
    test_yaml.write_text(_dump_yaml(cfg), encoding="utf-8")

    fail_calls: List[str] = []

    def failing_handler(request):
        fail_calls.append(str(request.url))
        return Response(500, json={"error": "boom"})

    try:
        app = main.create_app(routes_path=test_yaml)
        import httpx as _httpx
        app.state.proxy._client = _httpx.AsyncClient(
            transport=MockTransport(failing_handler), timeout=2.0
        )
        client = TestClient(app)
        token = _make_token()

        # Call 1 → 500 from upstream, breaker records failure (1/2)
        r1 = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r1.status_code == 500, r1.text

        # Call 2 → still 500, threshold reached → breaker OPEN
        r2 = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r2.status_code == 500, r2.text

        # Call 3 → breaker OPEN → fail-fast 503, upstream NOT called
        calls_before = len(fail_calls)
        r3 = client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r3.status_code == 503, r3.text
        assert r3.json()["detail"] == "circuit_open"
        assert r3.headers.get("X-Request-ID", "").startswith("req_")
        # No new upstream call after breaker opened
        assert len(fail_calls) == calls_before, (
            f"upstream should not be called after breaker opens: "
            f"before={calls_before} after={len(fail_calls)}"
        )

        # /_gw/breakers must reflect OPEN state
        br = client.get("/_gw/breakers").json()
        assert any(
            v == "open" for v in br["breakers"].values()
        ), f"expected an open breaker, got {br}"
    finally:
        if test_yaml.exists():
            test_yaml.unlink()


def test_request_id_generated_when_missing():
    """If the client does not supply X-Request-ID, the gateway mints one."""
    client, calls = _make_test_client()
    token = _make_token()
    r = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    rid = r.headers.get("X-Request-ID", "")
    assert rid.startswith("req_")
    # Forwarded upstream with the SAME id
    assert calls[0]["headers"]["x-request-id"] == rid


# ---------------------------------------------------------------------------
# Helpers (small yaml round-trip without PyYAML leak)
# ---------------------------------------------------------------------------

def _load_routes(path: Path) -> Dict[str, Any]:
    import yaml
    with path.open("r", encoding="utf-8") as fp:
        return yaml.safe_load(fp) or {}


def _dump_yaml(cfg: Dict[str, Any]) -> str:
    import yaml
    return yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
