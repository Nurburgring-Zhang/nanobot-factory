"""P21 Phase 4 P1 — Focused 6-test re-audit of R2 P0 security fixes.

Purpose
-------
Re-verify that the 6 R2-audit-confirmed P0 security fixes (which were
patched in P2 P1 + P2 P2 + P2 P5) are **STILL in effect** after the
P2 P3 + P2 P4 work that landed in between. The P2 P3 + P2 P4 changes
touched:

  * ``backend/auth/audit.py`` (audit log SQL hardening, helper methods)
  * ``backend/auth/unified_auth.py`` (``update_user`` / ``delete_user``
    wrappers, audit writes for 4 actions)
  * 14 ``backend/routes/data_*.py`` files (path-traversal guard
    wiring)
  * ``backend/imdf/skills/*`` (skill composition, envelope helper)
  * and other unrelated modules

We re-probe each of the 6 R2 P0 attack vectors to confirm the original
fixes are intact and no regression snuck in. If any test FAILS, the
underlying R2 P0 has regressed and must be reported as a CRITICAL
finding.

The 6 R2 P0 fixes (re-numbered in this file for clarity)::

  1. R2-09 / R2-NEW-06 — tenant takeover via unauthenticated
     ``POST /api/v2/users`` (P2 P1 fix in production.py)
  2. R2-NEW-01 — SQL injection in ``AuthDatabase.update_user``
     (P2 P1 fix in unified_auth.py)
  3. R2-NEW-02 — Reflected XSS in ``_build_error_body``
     (P2 P1 fix in error_handler.py)
  4. R2-NEW-03 — CSRF on state-changing POSTs
     (P2 P2 fix in middleware.py + server.py)
  5. R2-NEW-04 — Path traversal via unwired ``Injection.validate_path``
     (P2 P2 fix in path_dep.py + 14 route files)
  6. R1-02 / R2-NEW-? — Audit log gaps for the 4 state-changing user
     actions (P2 P1 + P2 P3 + P2 P4 + P2 P5 combined fix)

Pre-fix vs post-fix summary (for the verifier)::

  | # | Attack | Pre-fix response | Post-fix response |
  |---|--------|------------------|-------------------|
  | 1 | POST /api/v2/users (no auth) | 200 + api_key | 401, no leak |
  | 2 | update_user(sql-inject payload) | f-string SET clause | ?-bound params only |
  | 3 | _build_error_body(<script>) | verbatim in body | HTML-escaped |
  | 4 | POST (Origin: evil.com) | 200 | 403 CSRF |
  | 5 | validated_path(../../etc) | path joined raw | 400 + detail |
  | 6 | register/change/update/delete | no audit | 4 audit entries |

Run with::

    pytest tests/p4_p1/test_security_re_audit.py -v

The file is hermetic — each test builds its own minimal FastAPI app
and uses tempdir SQLite so no global state is mutated.
"""
from __future__ import annotations

import html
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Path setup (mirrors p2_p1..p2_p5 pattern) ────────────────────────────
_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Strong JWT secret so issue_access_token doesn't raise; CSRF disabled
# session-wide by conftest (CSRF_ENABLED=false). The CSRF test in this
# file force-enables CSRF on its own app, so the session default is
# irrelevant for that test.
os.environ.setdefault("JWT_SECRET", "x" * 64)
os.environ.setdefault("IMDF_TEST_MODE", "1")
os.environ.setdefault("CSRF_ENABLED", "false")


# ════════════════════════════════════════════════════════════════════════
# Test 1 — POST /api/v2/users without auth → 401
# ════════════════════════════════════════════════════════════════════════
# R2-09 / R2-NEW-06 — tenant takeover via unauthenticated admin creation.
# The P2 P1 fix added ``Depends(require_role_dep("admin"))`` to the route.
# Re-verifying: an attacker (no Authorization header) must NOT be able to
# create a user and must NOT receive an api_key.

def _build_production_app_with_mocked_user_mgr() -> tuple[FastAPI, Any, Any]:
    """Build a hermetic FastAPI app with the production router and a
    mock UserManager so the test doesn't touch the real on-disk DB.
    Mirrors the helper in tests/p2_p1/test_security_p0_fixes.py.
    """
    from routes import production as prod_mod

    app = FastAPI()
    app.include_router(prod_mod.router)

    fake_user = MagicMock()
    fake_user.id = "u-fake-r2-09"
    fake_user.username = "legit_user"
    fake_user.role.value = "viewer"
    fake_user.api_key = "nbk-fake-r2-09-LEAKED-MARKER"

    fake_mgr = MagicMock()
    fake_mgr.create_user.return_value = fake_user
    fake_mgr.get_all_users.return_value = []
    fake_mgr.get_user.return_value = None
    fake_mgr.get_user_projects.return_value = []
    fake_mgr.create_project.return_value = None
    fake_mgr.create_version.return_value = None
    fake_mgr.export_dataset.return_value = None
    fake_mgr.cancel_task.return_value = True
    fake_mgr.get_task.return_value = None

    def _fake_get_user_mgr():
        return fake_mgr

    return app, _fake_get_user_mgr, fake_mgr


def test_r2_09_post_users_no_auth_returns_401():
    """R2-09 / R2-NEW-06 re-audit: ``POST /api/v2/users`` with no
    Authorization header must return **401** (not 200 with api_key).

    Pre-fix: the route had no auth at all, so ``POST /api/v2/users``
    with ``{"username":"attacker","role":"admin"}`` (no auth header)
    returned 200 with ``api_key=nbk-…`` — full tenant takeover.

    Post-fix (production.py:50-54): ``Depends(_admin_required)`` is
    applied, so the unauthenticated call hits ``require_role_dep``
    which returns 401 with no DB write and no api_key leak.
    """
    app, _, _ = _build_production_app_with_mocked_user_mgr()
    with TestClient(app) as client:
        r = client.post(
            "/api/v2/users",
            json={"username": "attacker", "role": "admin"},
        )
    # The 401 itself is the contract: no auth → 401.
    assert r.status_code == 401, (
        f"R2-09 REGRESSION: POST /api/v2/users without auth returned "
        f"{r.status_code} (expected 401). Body: {r.text}. "
        f"This is the original R2-09 tenant takeover path."
    )
    # The original exploit response leaked ``api_key=nbk-…``. The fix
    # must NOT leak any ``nbk-`` prefix in the 401 body.
    body_lower = r.text.lower()
    assert "nbk-" not in body_lower, (
        f"R2-09 REGRESSION: api_key leaked in 401 response: {r.text}"
    )
    # The body should mention missing_authorization (the canonical
    # require_role_dep error).
    assert (
        "missing_authorization" in body_lower
        or "unauthorized" in body_lower
        or "detail" in r.json()
    ), f"Unexpected 401 body shape: {r.text!r}"


# ════════════════════════════════════════════════════════════════════════
# Test 2 — AuthDatabase.update_user SQL is parameterized
# ════════════════════════════════════════════════════════════════════════
# R2-NEW-01 — SQL injection in update_user via f-string set_clause.
# The P2 P1 fix replaced the f-string with a static ``_COLUMN_BIND``
# map; column names come from the static allow-list, values are bound
# as ``?`` parameters.

def test_r2_new_01_update_user_uses_parameterized_sql():
    """R2-NEW-01 re-audit: ``AuthDatabase.update_user`` must build its
    SET clause from a *static* column → ``?`` map. Caller input must
    NEVER appear in the SQL string itself.

    Pre-fix (unified_auth.py:625-631): the SET clause was built as
    ``", ".join(k + " = ?" for k in filtered)`` then embedded via
    ``f"UPDATE auth_users SET {set_clause} WHERE ..."``. While the
    keys were gated by an ``allowed`` set, Bandit B608 (and the R2
    pentest) flagged the f-string as risky. After P2 P1 the SET
    clause is built from a static ``_COLUMN_BIND`` map and all values
    are bound as parameters.

    This test inserts a baseline user, captures the SQL emitted by
    ``update_user``, and asserts:
      * the SQL has the expected ``UPDATE auth_users SET … = ? … WHERE
        user_id = ?`` shape;
      * no caller-influenced substring (quotes, comments, statement
        separators) appears in the SQL string;
      * the values are bound as parameters (not inlined).
    """
    from auth.unified_auth import AuthDatabase, AuthUser

    tmp_dir = tempfile.mkdtemp(prefix="p4_p1_r2_new_01_")
    db_path = os.path.join(tmp_dir, "unified_auth_r2_new_01.db")
    try:
        db = AuthDatabase(db_path)
        baseline = AuthUser(
            user_id="u-r2-new-01-victim",
            username="victim_r2_new_01",
            email="victim@x",
            role="viewer",
            password_hash="x",
            password_salt="y",
            hash_method="argon2",
            is_active=True,
            is_verified=True,
            display_name="Victim",
            team="",
            metadata={},
            created_at="2026-01-01T00:00:00",
            last_login=None,
            login_count=0,
        )
        assert db.insert_user(baseline), "baseline insert failed"

        # ── Spy on the connection ─────────────────────────────────────
        captured: list = []

        class _SpyConn:
            def __init__(self, real):
                self._real = real

            def execute(self, sql, params=()):
                captured.append((sql, params))
                return self._real.execute(sql, params)

            def commit(self):
                return self._real.commit()

            def close(self):
                return self._real.close()

            def __getattr__(self, name):
                return getattr(self._real, name)

        original_get_conn = db._get_conn

        def _spy_get_conn():
            return _SpyConn(original_get_conn())

        db._get_conn = _spy_get_conn

        # ── Attempt a typical role/email change ────────────────────────
        ok = db.update_user(
            "u-r2-new-01-victim",
            {"role": "admin", "email": "newmail@x"},
        )
        assert ok, "update_user returned False"
        db._get_conn = original_get_conn

        # ── Assertions on the captured SQL ─────────────────────────────
        update_calls = [
            (s, p) for s, p in captured if "UPDATE auth_users" in s
        ]
        assert update_calls, (
            f"update_user did not issue UPDATE; captured={captured!r}"
        )
        sql, params = update_calls[-1]

        # 1. Static structure
        assert "UPDATE auth_users SET" in sql, sql
        assert "WHERE user_id = ?" in sql, sql
        # 2. The column names must come from the static allow-list
        #    (here: role, email). No caller-influenced substring.
        sql_no_placeholders = sql.replace("?", "")
        for forbidden in (
            "'", "--", "/*", "*/",
            "; DROP", ";SELECT", ";UPDATE", ";DELETE",
        ):
            assert forbidden not in sql_no_placeholders, (
                f"R2-NEW-01 REGRESSION: user input leaked into SQL "
                f"string! forbidden={forbidden!r} sql={sql!r}"
            )
        # 3. Bound params: new values + user_id
        for expected in ("admin", "newmail@x", "u-r2-new-01-victim"):
            assert expected in params, (
                f"expected {expected!r} in params={params!r}"
            )
        # 4. No bound param may itself be raw SQL fragment.
        for p in params:
            assert not (
                isinstance(p, str)
                and p.strip().upper().startswith("SELECT ")
            ), f"params contains raw SQL fragment: {p!r}"
    finally:
        try:
            os.unlink(db_path)
        except OSError:
            pass


# ════════════════════════════════════════════════════════════════════════
# Test 3 — _build_error_body escapes XSS payload
# ════════════════════════════════════════════════════════════════════════
# R2-NEW-02 — reflected XSS in _build_error_body. The P2 P1 fix added
# ``html.escape(..., quote=True)`` on ``code`` and ``message``; raw
# values preserved on ``code_raw`` / ``message_raw`` for log/audit use.

def test_r2_new_02_build_error_body_escapes_xss():
    """R2-NEW-02 re-audit: ``_build_error_body`` must html-escape
    user-controlled ``code`` and ``message`` before serialising.

    Pre-fix (error_handler.py:77-96): a payload like
    ``<script>alert(1)</script>`` was returned verbatim in
    ``error.code`` and ``error.message`` — a reflected XSS sink for any
    browser-side JSON renderer.

    Post-fix: ``html.escape(..., quote=True)`` is applied; raw values
    are still available on ``code_raw`` / ``message_raw`` for
    server-side logs and machine clients.
    """
    from common.error_handler import _build_error_body

    payload_code = "<script>alert(1)</script>"
    payload_message = "<img src=x onerror=alert(2)>"
    body = _build_error_body(payload_code, payload_message, None)

    # The escaped forms MUST be present.
    assert html.escape(payload_code, quote=True) in body["error"]["code"], (
        f"R2-NEW-02 REGRESSION: code not escaped: {body['error']['code']!r}"
    )
    assert html.escape(payload_message, quote=True) in body["error"]["message"], (
        f"R2-NEW-02 REGRESSION: message not escaped: "
        f"{body['error']['message']!r}"
    )
    # The raw payload must NOT appear verbatim in code / message.
    assert payload_code not in body["error"]["code"], (
        f"R2-NEW-02 REGRESSION: raw <script> leaked in code: "
        f"{body['error']['code']!r}"
    )
    assert payload_message not in body["error"]["message"], (
        f"R2-NEW-02 REGRESSION: raw <img...> leaked in message: "
        f"{body['error']['message']!r}"
    )
    # Spot-check the specific encoding.
    assert "<script>" not in body["error"]["code"], (
        f"R2-NEW-02 REGRESSION: raw <script> tag present in code"
    )
    assert "&lt;script&gt;" in body["error"]["code"], (
        f"R2-NEW-02 REGRESSION: escaped &lt;script&gt; not found in code"
    )
    # The fix also preserves the raw value for log correlation.
    assert body["error"].get("code_raw") == payload_code, (
        f"R2-NEW-02 REGRESSION: raw code lost: "
        f"{body['error'].get('code_raw')!r}"
    )
    assert body["error"].get("message_raw") == payload_message, (
        f"R2-NEW-02 REGRESSION: raw message lost: "
        f"{body['error'].get('message_raw')!r}"
    )


# ════════════════════════════════════════════════════════════════════════
# Test 4 — CSRF: POST with evil.com Origin → 403
# ════════════════════════════════════════════════════════════════════════
# R2-NEW-03 — no CSRF protection on state-changing POSTs. The P2 P2
# fix added ``CSRFMiddleware`` (middleware.py:145-227) and wired it
# into ``server.py`` (the live app). Re-verifying here with a
# hermetic app that uses the same middleware.

def test_r2_new_03_post_with_evil_origin_returns_403():
    """R2-NEW-03 re-audit: ``POST`` with ``Origin: http://evil.com``
    must be rejected with 403 by ``CSRFMiddleware``.

    Pre-fix: 0/22 route files contained the keyword ``csrf``; combined
    with CORS ``allow_origins="*"`` and ``allow_credentials=True``, an
    attacker's form at ``evil.com`` could POST to
    ``/api/v2/users`` with the victim's session cookie and a hostile
    ``role=admin`` body — full tenant takeover.

    Post-fix (middleware.py:145-227 + server.py:1629-1640): the
    ``CSRFMiddleware`` reads an allow-list (``CORS_ALLOW_ORIGINS`` /
    explicit ``allowed_origins``) and rejects any unsafe-method
    request whose ``Origin`` is not in the list. Test 7 of p2_p2
    verified the full kill-chain using a server.py-mirror app; we
    re-probe the same kill-chain here.
    """
    from common.middleware import CSRFMiddleware

    app = FastAPI()

    @app.post("/api/v2/users")
    async def fake_create_user(payload: Optional[dict] = None):
        # Mirror production.py:50-70 shape so the test reflects
        # what an attacker actually gets on a 200.
        return {
            "id": "u-r2-new-03-victim",
            "username": (payload or {}).get("username", "anon"),
            "role": (payload or {}).get("role", "viewer"),
            "api_key": "nbk-R2-NEW-03-LEAKED-MARKER",
        }

    # Force-enable CSRF (conftest sets CSRF_ENABLED=false session-wide).
    app.add_middleware(
        CSRFMiddleware,
        allowed_origins=[
            "http://localhost:5173",
            "http://localhost:8765",
        ],
        enabled=True,
    )

    with TestClient(app) as client:
        # ── Attack 1: drive-by CSRF from evil.com ─────────────────────
        r_evil = client.post(
            "/api/v2/users",
            json={"username": "attacker", "role": "admin"},
            headers={
                "Origin": "http://evil.com",
                "Cookie": "admin_session=stolen",
            },
        )
        assert r_evil.status_code == 403, (
            f"R2-NEW-03 REGRESSION: CSRF not blocking evil.com. "
            f"Got {r_evil.status_code}: {r_evil.text}. "
            f"This is the original drive-by CSRF attack."
        )
        body = r_evil.json()
        assert body == {"error": "CSRF: invalid or missing Origin"}, (
            f"R2-NEW-03 REGRESSION: unexpected 403 body: {body!r}"
        )
        # No api_key leak in the 403 response (regression guard for
        # the original exploit that returned 200 + api_key).
        assert "nbk-" not in r_evil.text, (
            f"R2-NEW-03 REGRESSION: nbk- prefix leaked in 403 body: "
            f"{r_evil.text}"
        )

        # ── Attack 2: missing Origin header ───────────────────────────
        r_no_origin = client.post(
            "/api/v2/users",
            json={"username": "attacker2", "role": "admin"},
        )
        assert r_no_origin.status_code == 403, (
            f"R2-NEW-03 REGRESSION: missing-Origin request not blocked. "
            f"Got {r_no_origin.status_code}: {r_no_origin.text}"
        )

        # ── Legit request from the dev front-end ─────────────────────
        # Regression guard: the fix must NOT over-reject trusted origins.
        r_legit = client.post(
            "/api/v2/users",
            json={"username": "legit", "role": "viewer"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert r_legit.status_code == 200, (
            f"R2-NEW-03 REGRESSION: legit request over-rejected. "
            f"Got {r_legit.status_code}: {r_legit.text}"
        )
        assert r_legit.json().get("username") == "legit", r_legit.text


# ════════════════════════════════════════════════════════════════════════
# Test 5 — validated_path rejects parent traversal
# ════════════════════════════════════════════════════════════════════════
# R2-NEW-04 — path traversal. The P2 P2 fix added ``validated_path``
# (common/path_dep.py) wrapping ``Injection.validate_path``. Re-verify
# the most basic traversal vector: ``../../etc/passwd`` is rejected
# with HTTPException(400).

def test_r2_new_04_validated_path_rejects_parent_traversal():
    """R2-NEW-04 re-audit: ``validated_path`` must raise HTTPException
    with status_code=400 on path-traversal inputs.

    Pre-fix: ``Injection.validate_path`` existed in
    ``backend/imdf/security/owasp_protection.py:264`` but was not
    wired into any of the 122 routes. ``os.path.join`` and
    ``f"data/{user_input}"`` patterns in data_video.py, data_dataset.py
    etc. let ``?path=../../etc/passwd`` reach the filesystem.

    Post-fix: ``backend/common/path_dep.py::validated_path`` wraps the
    upstream check and raises ``HTTPException(400)`` on any rejected
    path. 32 routes in 14 data_* files were wired in P2 P2.

    This test exercises the helper directly (not via a route) — the
    helper itself is the single source of truth, so a regression here
    means 32 routes lose their guard simultaneously.
    """
    from fastapi import HTTPException
    from backend.common.path_dep import validated_path

    # ── 1. Parent traversal: ../../etc/passwd → 400 ──────────────────
    with pytest.raises(HTTPException) as excinfo:
        validated_path("../../etc/passwd")
    assert excinfo.value.status_code == 400, (
        f"R2-NEW-04 REGRESSION: parent traversal not blocked with 400. "
        f"Got status_code={excinfo.value.status_code}: {excinfo.value.detail!r}"
    )
    # The detail should mention "path traversal" (the canonical prefix
    # used by validated_path; verified at path_dep.py:118).
    detail = str(excinfo.value.detail)
    assert "traversal" in detail.lower(), (
        f"Unexpected detail for parent traversal: {detail!r}"
    )

    # ── 2. Absolute path: /etc/passwd → 400 ──────────────────────────
    with pytest.raises(HTTPException) as excinfo:
        validated_path("/etc/passwd")
    assert excinfo.value.status_code == 400
    assert "absolute" in str(excinfo.value.detail).lower(), (
        f"Unexpected detail for absolute path: {excinfo.value.detail!r}"
    )

    # ── 3. Tilde: ~/secrets → 400 ───────────────────────────────────
    with pytest.raises(HTTPException) as excinfo:
        validated_path("~/secrets")
    assert excinfo.value.status_code == 400

    # ── 4. Windows absolute: C:\\Windows\\System32 → 400 ────────────
    with pytest.raises(HTTPException) as excinfo:
        validated_path("C:\\Windows\\System32")
    assert excinfo.value.status_code == 400

    # ── 5. Empty path → 400 ──────────────────────────────────────────
    with pytest.raises(HTTPException) as excinfo:
        validated_path("")
    assert excinfo.value.status_code == 400

    # ── 6. Legit relative path: ./data/x.jpg → returns the path ─────
    # This is the regression guard: a real path must NOT be rejected.
    returned = validated_path("./data/x.jpg")
    assert returned == "./data/x.jpg", (
        f"Legit path was rejected (over-restrictive): {returned!r}"
    )


# ════════════════════════════════════════════════════════════════════════
# Test 6 — All 4 audit actions logged (R1-02 + P2 P5)
# ════════════════════════════════════════════════════════════════════════
# R1-02 / R2 NEW — audit log gaps. Fixed across P2 P1 (no, that was
# tenant takeover — the audit fix landed in P2 P3 + P2 P4 + P2 P5).
# Re-verifying here as a single combined-coverage test that exercises
# all 4 state-changing actions and asserts the audit log has all 4
# expected entries.

def _fetch_audit(db_path: str, sql: str, params: tuple = ()) -> list:
    """Read raw rows from auth_audit_log (raw fetchall wrapper)."""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def test_r1_02_all_four_audit_actions_logged(tmp_path: Path):
    """R1-02 re-audit: all 4 state-changing user actions must be
    recorded in ``auth_audit_log``.

    The 4 actions are::

      1. user.created       (P2 P3 + P2 P4 fix)
      2. password.changed   (P2 P3 + P2 P4 fix)
      3. user.updated       (P2 P5 fix)
      4. user.deleted       (P2 P5 fix)

    Pre-fix: the R1 reproducer (``unified_auth.py:816/1203/1181``)
    returned ``[]`` from ``auth_audit_log`` after register /
    change_password / delete_user. The R2 audit re-confirmed
    R1-02 in the 4/5 P0 verification table.

    Post-fix: P2 P3 added the audit writes; P2 P4 verified the
    2-site subset (register + change_password); P2 P5 verified
    the remaining 2 (update + delete). This re-audit exercises
    all 4 in one flow to confirm none of the fixes regressed.
    """
    from auth.unified_auth import UnifiedAuthManager

    db_path = str(tmp_path / "p4_p1_r1_02_audit.db")
    mgr = UnifiedAuthManager(jwt_secret="x" * 40, db_path=db_path)

    # ── Exercise the 4 actions in sequence ───────────────────────────
    user = mgr.register_user("p4_p1_alice", "Password123!", "viewer")
    assert user is not None
    user_id = user.user_id

    ok_pw = mgr.change_password(
        user_id, "Password123!", "NewPass5678!"
    )
    assert ok_pw, "change_password returned False"

    ok_upd = mgr.update_user(
        user_id, {"email": "alice.new@x.com"}, actor="admin-p4p1"
    )
    assert ok_upd, "update_user returned False"

    ok_del = mgr.delete_user(user_id, actor="admin-p4p1")
    assert ok_del, "delete_user returned False"

    # ── Verify all 4 actions are present in the audit log ────────────
    actions = sorted({
        r[0] for r in _fetch_audit(
            db_path, "SELECT DISTINCT action FROM auth_audit_log"
        )
    })

    expected = {
        "user.created",
        "password.changed",
        "user.updated",
        "user.deleted",
    }
    missing = expected - set(actions)
    assert not missing, (
        f"R1-02 REGRESSION: audit log missing actions {missing!r}. "
        f"Got: {actions}. "
        f"This is the original R1-02 finding (P2 P3 + P2 P4 + P2 P5 "
        f"combined fix should cover all 4)."
    )

    # ── Verify each action has the expected minimal payload shape ────
    # (regression guard for the P2 P3 / P2 P5 enhancements: actor,
    # target, details, timestamp, resource, result).

    # 1. user.created
    # Note: ``UnifiedAuthManager.__init__`` creates a bootstrap admin
    # in IMDF_TEST_MODE, so the audit log already has a user.created
    # row for the bootstrap admin. Filter by details.target == user_id
    # so the assertions below unambiguously check our test user.
    created_rows = _fetch_audit(
        db_path,
        "SELECT user_id, action, resource, result, details, timestamp "
        "FROM auth_audit_log WHERE action = 'user.created' "
        "AND json_extract(details, '$.target') = ?",
        (user_id,),
    )
    assert len(created_rows) == 1, (
        f"user.created audit row for our test user not found "
        f"(expected 1, got {len(created_rows)}). "
        f"This may indicate the audit write in register_user regressed."
    )
    actor, action, resource, result, details_json, ts = created_rows[0]
    assert resource == "user"
    assert result == "success"
    assert ts and "T" in ts, f"non-ISO timestamp: {ts!r}"
    details = json.loads(details_json)
    assert details.get("target") == user_id
    # register_user captures role/team/email (per unified_auth.py:899-908);
    # the actor is the user themselves.
    assert actor == "p4_p1_alice" or actor == user_id
    # role / team / email are recorded for forensic value
    assert details.get("role") == "viewer", f"missing role: {details}"

    # 2. password.changed
    # Note: for password.changed, actor == target == user_id, so the
    # ``AuditLog.write`` contract (audit.py:93) deliberately omits the
    # ``target`` field from details when actor==target — they're
    # logically the same entity. We filter to our user via ``user_id``.
    pw_rows = _fetch_audit(
        db_path,
        "SELECT user_id, details FROM auth_audit_log "
        "WHERE action = 'password.changed' AND user_id = ?",
        (user_id,),
    )
    assert len(pw_rows) == 1, (
        f"password.changed audit row for our test user not found "
        f"(expected 1, got {len(pw_rows)})"
    )
    actor, details_json = pw_rows[0]
    assert actor == user_id  # actor is the user themselves
    details = json.loads(details_json)
    # The P2 P3 enhancement captures tokens_revoked (forensic value).
    assert "tokens_revoked" in details, (
        f"password.changed missing tokens_revoked: {details}"
    )

    # 3. user.updated
    # Filter by target == user_id (actor is admin-p4p1, different from target)
    upd_rows = _fetch_audit(
        db_path,
        "SELECT user_id, details FROM auth_audit_log "
        "WHERE action = 'user.updated' "
        "AND json_extract(details, '$.target') = ?",
        (user_id,),
    )
    assert len(upd_rows) == 1, (
        f"user.updated audit row for our test user not found "
        f"(expected 1, got {len(upd_rows)})"
    )
    actor, details_json = upd_rows[0]
    assert actor == "admin-p4p1", f"actor mismatch: {actor!r}"
    details = json.loads(details_json)
    assert details.get("target") == user_id
    # The P2 P3 enhancement captures changed_fields + diff.
    assert "changed_fields" in details, (
        f"user.updated missing changed_fields: {details}"
    )
    assert "email" in details["changed_fields"]
    assert "diff" in details
    assert details["diff"]["email"]["old"] == "alice@x.com" or \
        details["diff"]["email"]["new"] == "alice.new@x.com"

    # 4. user.deleted
    del_rows = _fetch_audit(
        db_path,
        "SELECT user_id, details FROM auth_audit_log "
        "WHERE action = 'user.deleted' "
        "AND json_extract(details, '$.target') = ?",
        (user_id,),
    )
    assert len(del_rows) == 1, (
        f"user.deleted audit row for our test user not found "
        f"(expected 1, got {len(del_rows)})"
    )
    actor, details_json = del_rows[0]
    assert actor == "admin-p4p1", f"actor mismatch: {actor!r}"
    details = json.loads(details_json)
    assert details.get("target") == user_id
    # The P2 P3 enhancement captures target metadata BEFORE delete.
    assert details.get("username") == "p4_p1_alice", (
        f"user.deleted missing pre-delete username: {details}"
    )
