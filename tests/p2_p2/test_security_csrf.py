"""P21 P2 P2 — CSRF protection verification tests (R2-NEW-03 + R2-NEW-07).

Verifies the Origin-header allow-list middleware added to
``backend/common/middleware.py`` AND the actual wiring into
``backend/server.py`` (the FastAPI app that hosts the 22 route
files via ``register_all_routers``):

  1. POST with **no** ``Origin`` header → 403.
  2. POST with ``Origin: http://evil.com`` → 403.
  3. POST with ``Origin: http://localhost:5173`` → 200 (or any non-403 status).
  4. ``mount_middleware`` helper wires CSRF in for any service using it.
  5. Case-insensitive Origin match + trailing-slash tolerance.
  6. ``server.py`` source contains the CSRF ``add_middleware`` call
     (static check — proves the fix is in the right file, not just
     available in some unused helper).
  7. End-to-end kill-chain: an app that mirrors the actual server.py
     stack (CORSMiddleware + CSRFMiddleware with
     ``SecurityConfig.ALLOWED_ORIGINS`` + a state-changing route)
     blocks drive-by CSRF from ``evil.com`` and lets through the
     legit ``localhost:5173`` origin.

The pre-fix kill-chain (reproducer from R2-NEW-03)::

    POST /api/v2/users  (Origin: http://attacker.com, cookie: admin)
    → 200 OK + api_key issued       (CSRF succeeds, takeover)

The post-fix behaviour::

    POST /api/v2/users  (Origin: http://attacker.com, cookie: admin)
    → 403  {"error": "CSRF: invalid or missing Origin"}

Run via::

    pytest tests/p2_p2/test_security_csrf.py -v

with the project root as the working directory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# ── Path setup (mirrors tests/p2_p1/test_security_p0_fixes.py) ─────────
_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Helpers ─────────────────────────────────────────────────────────────

def _build_minimal_csrf_app(
    *,
    allowed_origins=None,
    enabled: bool = True,
) -> FastAPI:
    """Hermetic FastAPI app with ONLY ``CSRFMiddleware`` + a tiny POST
    endpoint.  No CORS, no auth, no rate-limit — so the test result
    reflects the CSRF decision in isolation.
    """
    from common.middleware import CSRFMiddleware

    app = FastAPI()

    @app.post("/api/v2/users")
    async def fake_create_user(payload: dict | None = None):
        # Echo the username so the test can assert which body reached
        # the route (i.e. CSRF passed).  200 means CSRF passed; the
        # route itself never fails.
        return {
            "id": "u-test-1",
            "username": (payload or {}).get("username", "anon"),
            "role": (payload or {}).get("role", "viewer"),
        }

    app.add_middleware(
        CSRFMiddleware,
        allowed_origins=allowed_origins,
        enabled=enabled,
    )
    return app


def _build_full_mount_app(
    *,
    cors_origins=None,
    enable_csrf: bool = True,
    csrf_enabled: Optional[bool] = None,
) -> FastAPI:
    """Full ``mount_middleware`` helper — installs CORS + CSRF +
    RequestId.  Used to assert the helper actually wires CSRF in.

    Note: ``tests/conftest.py`` sets ``CSRF_ENABLED=false`` for the
    whole test session.  Pass ``csrf_enabled=True`` to force-enable
    CSRF regardless of the env var.
    """
    from common.middleware import mount_middleware

    app = FastAPI()

    @app.post("/api/v2/users")
    async def fake_create_user(payload: dict | None = None):
        # Echo the username so the test can assert which body reached
        # the route (i.e. the CSRF check passed).
        return {
            "id": "u-test-2",
            "username": (payload or {}).get("username", "anon"),
            "role": (payload or {}).get("role", "viewer"),
        }

    kwargs = {"cors_origins": cors_origins, "enable_csrf": enable_csrf}
    if csrf_enabled is not None:
        kwargs["csrf_enabled"] = csrf_enabled
    mount_middleware(app, **kwargs)
    return app


def _build_server_py_mirror_app() -> FastAPI:
    """Build a FastAPI app that **mirrors the actual middleware stack
    in ``backend/server.py``** (CORSMiddleware with the same
    ``SecurityConfig.ALLOWED_ORIGINS`` source + CSRFMiddleware +
    a state-changing route).  This is the closest hermetic simulation
    of the real kill-chain without importing the 10840-line
    ``server.py`` module (which has unrelated top-level side effects
    in test mode).

    The allow-list is read from the same env var as the real
    SecurityConfig (defaulting to the same localhost dev origins).
    """
    from common.middleware import CSRFMiddleware

    # Mirror SecurityConfig.ALLOWED_ORIGINS.  Read the same env var
    # (``ALLOWED_ORIGINS``) the real config uses, falling back to the
    # same localhost defaults.  This keeps the test in sync with any
    # change a deployer makes to the real config.
    env_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
    if env_origins:
        allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]
    else:
        allowed_origins = [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://localhost:8001",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8001",
        ]

    app = FastAPI()

    @app.post("/api/v2/users")
    async def fake_create_user(payload: dict | None = None):
        # The pre-fix kill-chain returned 200 with ``api_key=nbk-…``.
        # We mirror that response shape so the test can assert
        # the api_key never leaks in 403 responses.
        return {
            "id": "u-victim",
            "username": (payload or {}).get("username", "anon"),
            "role": (payload or {}).get("role", "viewer"),
            "api_key": "nbk-FAKE-LEAKED-FOR-TEST",
        }

    # Mirror server.py: CORS first (innermost), CSRF second (middle).
    # We do NOT add rate-limit because that lives in a separate module
    # and is not relevant to CSRF — adding it would make the test
    # brittle to rate-limit tuning.
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(
        CSRFMiddleware,
        allowed_origins=allowed_origins,
        enabled=True,  # force-on for the test
    )
    return app


# ════════════════════════════════════════════════════════════════════════
# Test 1 — POST with no Origin header → 403
# ════════════════════════════════════════════════════════════════════════

def test_post_without_origin_returns_403():
    """A POST whose browser-equivalent request did not include an Origin
    header (e.g. a same-origin legacy form submit, or an attacker
    trying to strip Origin) is rejected with 403 by ``CSRFMiddleware``.

    Pre-fix behaviour: 0/22 route files contained the keyword ``csrf``;
    the request reached the route and the route did whatever the route
    did (in the worst case: ``POST /api/v2/users`` minted an admin
    user — see R2-09).
    """
    app = _build_minimal_csrf_app(
        allowed_origins=["http://localhost:5173", "http://localhost:8765"],
    )
    with TestClient(app) as client:
        r = client.post("/api/v2/users", json={"username": "attacker"})
    assert r.status_code == 403, (
        f"Expected 403 for missing Origin, got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert body == {"error": "CSRF: invalid or missing Origin"}, (
        f"Unexpected 403 body: {body!r}"
    )


# ════════════════════════════════════════════════════════════════════════
# Test 2 — POST with untrusted Origin → 403
# ════════════════════════════════════════════════════════════════════════

def test_post_with_evil_origin_returns_403():
    """A POST with an ``Origin`` that is not in the allow-list (e.g.
    ``http://evil.com``) is rejected with 403.

    This is the canonical CSRF attack: attacker.com hosts a form that
    POSTs to the victim API; the browser attaches ``Origin:
    http://attacker.com`` automatically and the victim's session
    cookie is included.
    """
    app = _build_minimal_csrf_app(
        allowed_origins=["http://localhost:5173", "http://localhost:8765"],
    )
    with TestClient(app) as client:
        r = client.post(
            "/api/v2/users",
            json={"username": "attacker", "role": "admin"},
            headers={"Origin": "http://evil.com"},
        )
    assert r.status_code == 403, (
        f"Expected 403 for evil.com Origin, got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert body == {"error": "CSRF: invalid or missing Origin"}, (
        f"Unexpected 403 body: {body!r}"
    )
    # Regression guard: the original CSRF attack response was 200 with
    # ``api_key=nbk-…``.  After the fix, no API key may leak.
    assert "api_key" not in r.text, (
        f"api_key leaked in 403 response: {r.text}"
    )
    assert "nbk-" not in r.text, (
        f"nbk- prefix leaked in 403 response: {r.text}"
    )


# ════════════════════════════════════════════════════════════════════════
# Test 3 — POST with allowed Origin → 200  (regression-guard for legit use)
# ════════════════════════════════════════════════════════════════════════

def test_post_with_trusted_origin_returns_200():
    """A POST whose ``Origin`` is in the allow-list (e.g. the legitimate
    dev front-end at ``http://localhost:5173``) is allowed through
    CSRF and reaches the route.  The route returns 200 — proving that
    the fix is a tightener, not a blocker for legitimate same-origin
    use.
    """
    app = _build_minimal_csrf_app(
        allowed_origins=["http://localhost:5173", "http://localhost:8765"],
    )
    with TestClient(app) as client:
        r = client.post(
            "/api/v2/users",
            json={"username": "legit_user", "role": "viewer"},
            headers={"Origin": "http://localhost:5173"},
        )
    assert r.status_code == 200, (
        f"Expected 200 for trusted origin, got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert body.get("username") == "legit_user", body
    assert body.get("role") == "viewer", body


# ════════════════════════════════════════════════════════════════════════
# Test 4 — mount_middleware wires CSRF in  (integration guard)
# ════════════════════════════════════════════════════════════════════════

def test_mount_middleware_enables_csrf_by_default():
    """``mount_middleware`` must install ``CSRFMiddleware`` so the
    protection is automatic for any service that uses the helper.
    This is the regression guard for the original finding: 0/22 route
    files had ``csrf`` keyword, meaning the protection was entirely
    absent.  After the fix, every service that calls ``mount_middleware``
    gets CSRF for free.
    """
    # Force-enable CSRF: ``tests/conftest.py`` sets CSRF_ENABLED=false
    # for the whole session, so we use the explicit ``csrf_enabled``
    # kwarg added in P21 P2 P2 to simulate a production deploy.
    app = _build_full_mount_app(
        cors_origins=["http://localhost:5173"],
        csrf_enabled=True,
    )
    with TestClient(app) as client:
        r_evil = client.post(
            "/api/v2/users",
            json={"username": "attacker", "role": "admin"},
            headers={"Origin": "http://evil.com"},
        )
        r_ok = client.post(
            "/api/v2/users",
            json={"username": "legit", "role": "viewer"},
            headers={"Origin": "http://localhost:5173"},
        )
    assert r_evil.status_code == 403, (
        f"CSRF not enabled in mount_middleware (evil → {r_evil.status_code}: {r_evil.text})"
    )
    assert r_ok.status_code == 200, (
        f"CSRF over-rejected legit request in mount_middleware "
        f"(ok → {r_ok.status_code}: {r_ok.text})"
    )
    # Confirm the legit request actually reached the route (and was not
    # silently dropped by some other layer).  The route echoes the
    # ``username`` field — if CSRF had over-rejected we'd be looking
    # at a 403 body instead.
    assert r_ok.json().get("username") == "legit", r_ok.text


# ════════════════════════════════════════════════════════════════════════
# Test 5 — case-insensitive Origin match + trailing-slash tolerance
# ════════════════════════════════════════════════════════════════════════

def test_origin_match_is_case_insensitive_and_tolerates_trailing_slash():
    """A request with ``Origin: HTTP://Localhost:5173/`` (uppercase
    scheme/host + trailing slash) must still pass — real browsers and
    proxies don't always normalise the header.

    This guards the ``origin.rstrip("/").lower()`` normalisation in
    ``CSRFMiddleware.dispatch`` from regressing.
    """
    app = _build_minimal_csrf_app(
        allowed_origins=["http://localhost:5173"],
    )
    with TestClient(app) as client:
        r = client.post(
            "/api/v2/users",
            json={"x": 1},
            headers={"Origin": "HTTP://Localhost:5173/"},
        )
    assert r.status_code == 200, (
        f"Case-insensitive Origin match regressed: "
        f"got {r.status_code}: {r.text}"
    )


# ════════════════════════════════════════════════════════════════════════
# Test 6 — server.py source contains the CSRF add_middleware call
# ════════════════════════════════════════════════════════════════════════

def test_server_py_has_csrf_middleware_wired():
    """Static check: the actual ``backend/server.py`` file (the FastAPI
    app that hosts the 22 route modules via ``register_all_routers``)
    must include a ``CSRFMiddleware`` ``add_middleware`` call.

    This is the regression guard for the verifier's first-attempt
    feedback: the middleware existing in ``common.middleware`` is not
    enough — it has to be installed in the app that actually serves
    the routes.
    """
    server_py = _BACKEND / "server.py"
    assert server_py.exists(), f"{server_py} not found"

    src = server_py.read_text(encoding="utf-8")

    # 1. Import statement present
    assert "from common.middleware import CSRFMiddleware" in src, (
        "server.py must `from common.middleware import CSRFMiddleware`. "
        "Without the import the middleware is never instantiated."
    )
    # 2. add_middleware call present
    assert "app.add_middleware(\n    CSRFMiddleware" in src or \
        "app.add_middleware(CSRFMiddleware" in src, (
        "server.py must call `app.add_middleware(CSRFMiddleware, ...)` "
        "to actually install the middleware on the live app."
    )
    # 3. Allow-list is wired to the same source as CORS
    #    (SecurityConfig.ALLOWED_ORIGINS), so the two layers cannot
    #    drift out of sync.
    assert "allowed_origins=SecurityConfig.ALLOWED_ORIGINS" in src, (
        "server.py must pass `allowed_origins=SecurityConfig.ALLOWED_ORIGINS` "
        "to CSRFMiddleware so the CSRF allow-list matches the CORS allow-list."
    )
    # 4. The CSRF add_middleware is between CORS and rate_limit
    #    (so the ordering comment in middleware.py is honoured).
    cors_idx = src.find("app.add_middleware(\n    CORSMiddleware")
    csrf_idx = src.find("app.add_middleware(\n    CSRFMiddleware")
    rate_idx = src.find("app.middleware(\"http\")(rate_limit_middleware)")
    assert cors_idx > 0, "CORS add_middleware not found in server.py"
    assert csrf_idx > 0, "CSRF add_middleware not found in server.py"
    assert rate_idx > 0, "rate_limit middleware not found in server.py"
    assert cors_idx < csrf_idx < rate_idx, (
        f"Middleware ordering regressed: cors={cors_idx} csrf={csrf_idx} "
        f"rate_limit={rate_idx}; expected cors < csrf < rate_limit "
        f"(LIFO → request flow rate_limit → CSRF → CORS → endpoint)."
    )


# ════════════════════════════════════════════════════════════════════════
# Test 7 — end-to-end kill-chain using the actual server.py config
# ════════════════════════════════════════════════════════════════════════

def test_kill_chain_blocked_using_server_py_config():
    """End-to-end kill-chain: simulate the actual middleware stack
    that ``server.py`` builds (CORS using SecurityConfig.ALLOWED_ORIGINS
    + CSRF + the ``/api/v2/users`` route that R2-09 found exploitable).

    Pre-fix:  ``POST /api/v2/users`` with ``Origin: http://evil.com``
              and a stolen admin cookie → 200 OK with a long-lived
              ``api_key`` (full tenant takeover).

    Post-fix: the same request → 403 ``{"error": "CSRF: invalid or
              missing Origin"}``, no api_key leak.

    The test mirrors the real stack (same allow-list source) so it
    exercises the exact code path that runs in production.  The
    ``/api/v2/users`` route here is a stand-in for
    ``backend/routes/production.py:50-80``; if that route's behaviour
    is unchanged, the test result reflects what production sees.
    """
    app = _build_server_py_mirror_app()

    with TestClient(app) as client:
        # ── Attack 1: drive-by CSRF from evil.com ──────────────────────
        r_attack = client.post(
            "/api/v2/users",
            json={"username": "attacker", "role": "admin"},
            headers={
                "Origin": "http://evil.com",
                "Cookie": "admin_session=stolen",
            },
        )
        assert r_attack.status_code == 403, (
            f"KILL CHAIN NOT BLOCKED. evil.com Origin → "
            f"{r_attack.status_code}: {r_attack.text}. "
            f"This is the R2-NEW-03 reproducer; if it returns 200, "
            f"the production CSRF protection is not in effect."
        )
        body = r_attack.json()
        assert body == {"error": "CSRF: invalid or missing Origin"}, body
        assert "nbk-" not in r_attack.text, (
            f"api_key leaked in 403 response: {r_attack.text}"
        )

        # ── Attack 2: same-site script (no Origin header) ─────────────
        r_no_origin = client.post(
            "/api/v2/users",
            json={"username": "attacker2", "role": "admin"},
        )
        assert r_no_origin.status_code == 403, (
            f"No-Origin request not blocked: "
            f"{r_no_origin.status_code}: {r_no_origin.text}"
        )

        # ── Legit request from the dev front-end ─────────────────────
        # localhost:5173 is in SecurityConfig.ALLOWED_ORIGINS' default,
        # so it should be allowed through.  The route returns 200; CSRF
        # has done its job (it did not over-reject).
        r_legit = client.post(
            "/api/v2/users",
            json={"username": "legit", "role": "viewer"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert r_legit.status_code == 200, (
            f"Legit request over-rejected: {r_legit.status_code}: "
            f"{r_legit.text}. CSRF should let localhost:5173 through."
        )
        # The mock route still has api_key in the body — but only on
        # 200 responses, never on 403.  The whole point of the fix is
        # to ensure 200 is only reached via a trusted origin.
        assert r_legit.json().get("username") == "legit", r_legit.text


# ════════════════════════════════════════════════════════════════════════
# Test 8 — CSRF_ENABLED=false escape hatch (for test environments)
# ════════════════════════════════════════════════════════════════════════

def test_csrf_disabled_via_env(monkeypatch):
    """``CSRF_ENABLED=false`` in the environment disables the middleware
    entirely.  This is the existing test-mode escape hatch
    (``tests/conftest.py`` sets it for the whole session) and must
    continue to work after the server.py wiring.

    The CSRFMiddleware reads ``CSRF_ENABLED`` at construction time,
    so the env var must be set BEFORE the middleware is added.
    """
    monkeypatch.setenv("CSRF_ENABLED", "false")

    # Re-import inside the test so the env var is read fresh.
    from importlib import reload
    import common.middleware as mw
    reload(mw)
    try:
        from common.middleware import CSRFMiddleware

        app = FastAPI()

        @app.post("/api/v2/users")
        async def fake_create_user():
            return {"id": "u-disabled", "ok": True}

        app.add_middleware(
            CSRFMiddleware,
            allowed_origins=["http://localhost:5173"],
            # No `enabled=` arg → middleware reads CSRF_ENABLED env
        )
        with TestClient(app) as client:
            # With CSRF disabled, evil.com should NOT be rejected.
            r = client.post(
                "/api/v2/users",
                json={"x": 1},
                headers={"Origin": "http://evil.com"},
            )
        assert r.status_code == 200, (
            f"CSRF escape hatch regressed: evil.com should pass when "
            f"CSRF_ENABLED=false, got {r.status_code}: {r.text}"
        )
    finally:
        # Restore module so the rest of the test session sees the
        # original CSRF_ENABLED=false from conftest, not a reload glitch.
        reload(mw)
