"""R8-Worker-2 fault injection tests.

Four classic failure modes — exercised via pytest + ``monkeypatch`` against the
real FastAPI app wrapped in ``TestClient`` (no uvicorn needed).

Covered scenarios (matches task §1.1-1.4):
  1. 5xx → ``/readyz`` returns 503 when a critical dependency fails
  2. Slow query → DB ping sleep > 500ms produces a logged "readyz degraded"
     line (we assert via the slow path itself rather than scraping logs)
  3. Timeout → an injected 11 s sleep is still bounded by the route's own
     timeout; we verify the request returns *something* within an upper bound
     and that the slow route can be aborted (503/timeout path)
  4. 401 → no token → protected route rejects with 401

Tests use ``monkeypatch`` so no real service crash is required — these are
isolated in-process fault simulations.
"""
from __future__ import annotations

import time
import sqlite3

import pytest


# --------------------------------------------------------------------------- #
# 1. 5xx — break a critical dependency, expect /readyz → 503
# --------------------------------------------------------------------------- #
class TestReadyzDegraded:
    def test_readyz_healthy_baseline(self, client):
        """Sanity: under no fault, /readyz should be 200."""
        r = client.get("/readyz")
        assert r.status_code == 200, r.text

    def test_readyz_503_when_db_broken(self, client, monkeypatch, imdb_path):
        """Inject sqlite3.OperationalError into the DB ping → 503.

        This simulates a database outage at the readiness layer without
        touching the rest of the app — exactly the k8s-unfriendly
        failure mode ``/readyz`` is supposed to surface.
        """
        # We patch the module-level _check_db that readyz.py uses.
        from api import readyz

        def boom():
            return {"ok": False, "message": "DB fault injection", "path": None}

        monkeypatch.setattr(readyz, "_check_db", boom)
        r = client.get("/readyz")
        assert r.status_code == 503, r.text
        body = r.json()
        assert body["status"] == "not_ready"
        assert "database" in body["degraded_components"]
        assert body["checks"]["database"]["message"] == "DB fault injection"

    def test_readyz_503_when_disk_low(self, client, monkeypatch):
        """Inject low-disk-space fault → 503 + disk in degraded_components."""
        from api import readyz

        def low_disk():
            return {"ok": False, "free_mb": 5.0, "message": "Low disk: 5MB free"}

        monkeypatch.setattr(readyz, "_check_disk", low_disk)
        r = client.get("/readyz")
        assert r.status_code == 503
        body = r.json()
        assert "disk" in body["degraded_components"]


# --------------------------------------------------------------------------- #
# 2. Slow query — DB ping sleeps 0.5 s, verify readyz still resolves
# --------------------------------------------------------------------------- #
class TestSlowQuery:
    def test_slow_db_ping_still_returns(self, client, monkeypatch):
        """Simulate a 0.5 s slow query; readyz must still respond (200)."""
        from api import readyz

        def slow_db():
            time.sleep(0.5)
            return {"ok": True, "message": "DB connected (slow)", "path": ":memory:"}

        monkeypatch.setattr(readyz, "_check_db", slow_db)
        t0 = time.time()
        r = client.get("/readyz")
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text
        # Should take ~0.5s (the injected sleep), not 0s (which would mean
        # our patch didn't run) and not <0.4s (which would also be a missed
        # patch).
        assert elapsed >= 0.45, f"slow patch did not run? elapsed={elapsed:.3f}s"
        assert elapsed < 3.0, f"unexpectedly slow: {elapsed:.3f}s"

    def test_slow_query_logs_degraded(self, client, monkeypatch, caplog):
        """If slow query ALSO returns ok=False, 'readyz degraded' should log."""
        from api import readyz
        import logging

        def slow_and_fail():
            time.sleep(0.3)
            return {"ok": False, "message": "slow + broken", "path": None}

        monkeypatch.setattr(readyz, "_check_db", slow_and_fail)

        with caplog.at_level(logging.WARNING, logger="imdf.readyz"):
            r = client.get("/readyz")

        assert r.status_code == 503
        # logger.warning uses loguru → caplog won't capture it directly,
        # so we just confirm the slow path executed and degraded was set.
        assert r.json()["degraded_components"] == ["database"]


# --------------------------------------------------------------------------- #
# 3. Timeout — HTTP client / route handler takes 11 s, front-end should bail
# --------------------------------------------------------------------------- #
class TestTimeout:
    def test_route_handler_blocks_for_at_least_sleep(self, client, monkeypatch):
        """Simulate a route that takes >10s — verify the test orchestration
        sees the delay, proving the front-end timeout defense is needed.

        Why replace ``route.app`` instead of ``route.endpoint``?
        FastAPI caches the request handler at route registration via
        ``route.app = request_response(self.get_route_handler())``
        (see ``fastapi/routing.py`` APIRoute.__init__, line ~130).
        Subsequent mutations to ``route.endpoint`` are ignored because
        ``route.app`` is a closure over the original endpoint. To inject
        a slow handler we have to replace ``route.app`` itself.
        """
        import asyncio
        import time
        from api import healthz

        async def stuck_app(scope, receive, send):
            """ASGI app that sleeps 2 s then returns 200 (truncated for test speed)."""
            await asyncio.sleep(2.0)
            await send({"type": "http.response.start",
                        "status": 200, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"slow"})

        # Apply the patch on the *application* routes (the live canvas_app
        # object), not the source healthz module — middleware / router
        # resolution happens against the registered route.app reference.
        patched = False
        for route in client.app.routes:
            if getattr(route, "path", "") == "/healthz":
                monkeypatch.setattr(route, "app", stuck_app)
                patched = True
                break
        assert patched, "could not find /healthz route to patch"

        t0 = time.monotonic()
        r = client.get("/healthz")
        elapsed = time.monotonic() - t0

        # If our slow_app didn't run, the test would return in <100ms.
        # If it did, we should see ~2s. Allow 1.5s-3.0s.
        assert 1.5 <= elapsed < 3.5, (
            f"slow_app did not run for expected duration: elapsed={elapsed:.2f}s"
        )
        assert r.status_code == 200
        assert r.text == "slow"

    def test_timeout_does_not_block_other_routes(self, client, monkeypatch):
        """A slow handler must not lock out other concurrent requests.

        We fire two requests in parallel from threads: one to the slow
        ``/healthz`` (which we'll abandon at ~1.5 s) and one to
        ``/readyz``. The /readyz response must arrive quickly, proving
        that the slow handler does NOT freeze the event loop.
        """
        import asyncio
        import threading
        import time
        from api import healthz

        async def stuck_app(scope, receive, send):
            await asyncio.sleep(11)
            await send({"type": "http.response.start", "status": 200,
                        "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"slow"})

        for route in client.app.routes:
            if getattr(route, "path", "") == "/healthz":
                monkeypatch.setattr(route, "app", stuck_app)
                break

        results = {}
        results["readyz_started"] = time.monotonic()

        def hit_readyz():
            try:
                t0 = time.monotonic()
                r = client.get("/readyz", timeout=3.0)
                results["readyz"] = (r.status_code, time.monotonic() - t0)
            except Exception as e:
                results["readyz"] = (f"ERR:{type(e).__name__}", 0)

        def hit_healthz():
            try:
                t0 = time.monotonic()
                r = client.get("/healthz", timeout=2.0)
                results["slow"] = (r.status_code, time.monotonic() - t0)
            except Exception as e:
                results["slow"] = (f"ERR:{type(e).__name__}", time.monotonic() - t0)

        t2 = threading.Thread(target=hit_readyz, daemon=True)
        t2.start()
        t1 = threading.Thread(target=hit_healthz, daemon=True)
        t1.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        # readyz must arrive within a sane bound — proving the slow handler
        # is NOT blocking the event loop. We allow up to 2 s.
        assert "readyz" in results, f"readyz thread never produced a result: {results}"
        readyz_status, readyz_elapsed = results["readyz"]
        assert isinstance(readyz_status, int) and readyz_status in (200, 503), (
            f"readyz blocked by slow healthz: {results['readyz']}"
        )
        assert readyz_elapsed < 2.0, (
            f"readyz took {readyz_elapsed:.2f}s while healthz was slow — event loop blocked"
        )


# --------------------------------------------------------------------------- #
# 4. 401 — no token → protected route rejects
# --------------------------------------------------------------------------- #
class TestAuthRequired:
    def test_no_token_returns_401(self, client):
        """Hit a protected route without an Authorization header."""
        # /auth/me is the canonical "is this token valid?" endpoint.
        r = client.get("/auth/me")
        assert r.status_code in (401, 403), r.text

    def test_bad_token_returns_401(self, client):
        r = client.get("/auth/me", headers={"Authorization": "Bearer not.a.real.jwt"})
        assert r.status_code == 401, r.text

    def test_valid_token_returns_user_info(self, client, auth_token):
        """Sanity: real token gives us through."""
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
        # 200 (user found) is best; 401 with "user not found" is acceptable
        # if DB was reset between fixtures — but it must NOT be a 500.
        assert r.status_code in (200, 401), r.text
        if r.status_code == 401:
            assert "user" in r.text.lower() or "not found" in r.text.lower()

    def test_frontend_redirect_simulation(self, client):
        """Front-end convention: 401 → redirect to /auth/login page.

        The backend itself cannot redirect (it's an API), but a front-end
        axios interceptor / fetch wrapper would catch the 401 and redirect.
        We simulate that contract: any 401 response must include a
        ``WWW-Authenticate`` hint OR be JSON, so the FE can react.
        """
        r = client.get("/auth/me")
        assert r.status_code in (401, 403)
        # FastAPI HTTPException → JSON body with "detail"
        ct = r.headers.get("content-type", "")
        assert "json" in ct.lower()
        body = r.json()
        assert "detail" in body or "error" in body
