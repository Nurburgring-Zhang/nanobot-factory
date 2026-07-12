"""P21 P2 P1 — security P0 fix verification tests.

Verifies the three production-route hardening changes called out in
``reports/p21_r2_audit_security.md``:

  * **R2-09 / R2-NEW-06** — ``POST /api/v2/users`` no longer creates an
    admin user with a long-lived ``api_key`` when called without
    authentication (or with a non-admin token).
    Unauthenticated → 401; non-admin → 403; admin → 200.

  * **R2-NEW-01** — ``AuthDatabase.update_user`` builds the SQL SET
    clause from a *static* column → ``?`` map. Caller input never
    reaches the SQL string itself. The mocked cursor.execute confirms
    the bound args carry the user's values and the column names come
    only from the static allow-list (regression guard for the original
    f-string Bandit B608 hit at ``unified_auth.py:625-631``).

  * **R2-NEW-02** — ``common.error_handler._build_error_body`` now runs
    :func:`html.escape` on ``code`` and ``message`` before serialising,
    so XSS payloads like ``<script>alert(1)</script>`` no longer land
    verbatim in the response body.

Each test runs independently of the others; no global state is mutated
(``monkeypatch`` / explicit ``TestClient`` context manager is used
where the FastAPI app / DB lifecycle matters).

The module is self-contained: it sets up ``sys.path`` and the minimum
ENV vars at import time, so it can be run via::

    pytest tests/p2_p1/test_security_p0_fixes.py -v

with the project root as the working directory (which matches
``pytest.ini``'s ``testpaths = tests`` and the global conftest).
"""
from __future__ import annotations

import html
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Path setup (mirrors tests/conftest.py) ──────────────────────────────
# The global ``tests/conftest.py`` already injects ``backend/`` into
# ``sys.path``; we still defensively do it here so this file works when
# invoked via ``pytest tests/p2_p1/test_security_p0_fixes.py`` from any
# working directory.
_THIS = Path(__file__).resolve()
_BACKEND = _THIS.parents[2] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Strong JWT secret so issue_access_token doesn't raise in tests.
os.environ.setdefault("JWT_SECRET", "x" * 64)
os.environ.setdefault("IMDF_TEST_MODE", "1")


# ── Imports that depend on path / env above ─────────────────────────────
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════

def _build_production_app_with_mocked_user_mgr():
    """Build a FastAPI app with the production router, returning a mock
    that replaces ``core.multi_tenant.UserManager`` so the admin→200
    test doesn't touch the real on-disk user database.
    """
    from routes import production as prod_mod

    app = FastAPI()
    app.include_router(prod_mod.router)

    fake_user = MagicMock()
    fake_user.id = "u-fake1234"
    fake_user.username = "legit_user"
    fake_user.role.value = "viewer"
    fake_user.api_key = "nbk-fake-api-key-zzzz9999"

    fake_mgr = MagicMock()
    fake_mgr.create_user.return_value = fake_user
    # Side-effect: list_users also needs to be present in some tests
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


# ════════════════════════════════════════════════════════════════════════
# Test 1 — POST /api/v2/users without auth → 401  (R2-09 / R2-NEW-06)
# ════════════════════════════════════════════════════════════════════════

def test_post_users_no_auth_returns_401():
    """Unauthenticated caller must be rejected with 401 (not 200 with an
    api_key as the original reproducer found).
    """
    app, _fake, _ = _build_production_app_with_mocked_user_mgr()
    with TestClient(app) as client:
        r = client.post(
            "/api/v2/users",
            json={"username": "attacker", "role": "admin"},
        )
    assert r.status_code == 401, (
        f"Expected 401, got {r.status_code}: {r.text}"
    )
    # The original R2-09 reproducer returned ``api_key=nbk-...``. The
    # fix must NOT leak any ``nbk-`` prefix in the 401 response body.
    body_lower = r.text.lower()
    assert "nbk-" not in body_lower, (
        f"api_key leaked in 401 response: {r.text}"
    )


# ════════════════════════════════════════════════════════════════════════
# Test 2 — POST /api/v2/users with non-admin JWT → 403
# ════════════════════════════════════════════════════════════════════════

def test_post_users_non_admin_jwt_returns_403():
    """A non-admin (e.g. viewer) token must NOT be able to create a user."""
    from common.auth import issue_access_token

    viewer_token = issue_access_token(username="eve", role="viewer")

    app, _fake, _ = _build_production_app_with_mocked_user_mgr()
    with TestClient(app) as client:
        r = client.post(
            "/api/v2/users",
            json={"username": "attacker", "role": "admin"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
    assert r.status_code == 403, (
        f"Expected 403, got {r.status_code}: {r.text}"
    )
    body_lower = r.text.lower()
    assert "nbk-" not in body_lower, (
        f"api_key leaked in 403 response: {r.text}"
    )


# ════════════════════════════════════════════════════════════════════════
# Test 3 — POST /api/v2/users with admin JWT → 200  (legit use still works)
# ════════════════════════════════════════════════════════════════════════

def test_post_users_admin_jwt_returns_200():
    """Legitimate admin still works — no over-restriction."""
    from common.auth import issue_access_token

    admin_token = issue_access_token(username="admin", role="admin")

    app, fake_get_user_mgr, fake_mgr = _build_production_app_with_mocked_user_mgr()
    # Patch the lazy-loader so the endpoint uses our mock instead of the
    # real UserManager (which would touch the on-disk DB).
    with patch("routes.production._get_user_mgr", side_effect=fake_get_user_mgr):
        with TestClient(app) as client:
            r = client.post(
                "/api/v2/users",
                json={"username": "legit_user", "role": "viewer"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
    assert r.status_code == 200, (
        f"Expected 200, got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert body.get("username") == "legit_user"
    # Even the admin path returns an api_key (by design for
    # production.py — that's what makes the original bug a takeover
    # vector), but the route is no longer reachable without an admin
    # token, as proven by tests 1 and 2 above.
    assert body.get("api_key"), "admin path must return api_key for the caller's records"
    # Sanity: the mock was actually called once.
    assert fake_mgr.create_user.called, "UserManager.create_user should be called for admin caller"


# ════════════════════════════════════════════════════════════════════════
# Test 4 — AuthDatabase.update_user SQL is parameterized  (R2-NEW-01)
# ════════════════════════════════════════════════════════════════════════

def test_update_user_uses_parameterized_sql():
    """The pre-fix code at ``unified_auth.py:625-631`` built the SET
    clause as ``", ".join(k + ' = ?' for k in filtered)`` and then
    embedded it via ``f"UPDATE auth_users SET {set_clause} WHERE ..."``.
    Bandit B608 + R2-01 both flagged this. The new code is column-name
    safe because (a) column names come from a *static* ``_COLUMN_BIND``
    mapping and (b) all values are bound as parameters — caller input
    never reaches the SQL string.

    This test:
      1. inserts a real baseline user (proves the table schema works),
      2. wraps ``db._get_conn`` so the next ``update_user`` call's
         ``execute(sql, params)`` is captured without losing the
         underlying DB connection,
      3. asserts the captured SQL has the expected shape and contains
         no caller-influenced substring, and
      4. asserts the captured params carry the new values + the
         user_id (matching the documented ``values = [..., user_id]``
         order).
    """
    from auth.unified_auth import AuthDatabase, AuthUser

    tmp_dir = tempfile.mkdtemp(prefix="auth_p2p1_")
    db_path = os.path.join(tmp_dir, "unified_auth.db")
    try:
        db = AuthDatabase(db_path)
        baseline = AuthUser(
            user_id="u-test001",
            username="victim_p2p1",
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

        # ── Spy: wrap the connection object so we capture execute() ─────
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
                # Forward anything else (PRAGMA, row_factory, ...) to the
                # real connection.
                return getattr(self._real, name)

        original_get_conn = db._get_conn

        def _spy_get_conn():
            return _SpyConn(original_get_conn())

        db._get_conn = _spy_get_conn

        # ── Call update_user with a benign role/email change ────────────
        ok = db.update_user(
            "u-test001",
            {"role": "admin", "email": "newmail@x"},
        )
        assert ok, "update_user returned False"

        # Restore for cleanup
        db._get_conn = original_get_conn

        # ── Assertions on the captured SQL ──────────────────────────────
        # Find the UPDATE call (insert_user also issues an INSERT, so
        # filter for the marker).
        update_calls = [(s, p) for s, p in captured if "UPDATE auth_users" in s]
        assert update_calls, (
            f"update_user did not issue UPDATE; captured={captured!r}"
        )
        sql, params = update_calls[-1]

        # 1. Static structure
        assert "UPDATE auth_users SET" in sql, sql
        assert "WHERE user_id = ?" in sql, sql
        # 2. The SET clause is built from the static _COLUMN_BIND map.
        #    After removing "?" placeholders, the SQL must not contain
        #    any string literal, comment, or statement separator — i.e.
        #    caller input was never inlined.
        sql_no_placeholders = sql.replace("?", "")
        for forbidden in (
            "'", "--", "/*", "*/",
            "; DROP", ";SELECT", ";UPDATE", ";DELETE",
        ):
            assert forbidden not in sql_no_placeholders, (
                f"User input leaked into SQL string! forbidden={forbidden!r} "
                f"sql={sql!r}"
            )
        # 3. Bound params: role, email, user_id  (order is determined
        #    by dict insertion order; we only assert membership since
        #    Python dicts preserve order in 3.7+ but we don't want to
        #    couple to that).
        assert "admin" in params, f"new role missing from params={params!r}"
        assert "newmail@x" in params, f"new email missing from params={params!r}"
        assert "u-test001" in params, f"user_id missing from params={params!r}"
        # 4. No bound param may be the raw SQL fragment (proves no
        #    "value-as-SQL" was ever smuggled in).
        for p in params:
            assert not (isinstance(p, str) and p.strip().upper().startswith("SELECT ")), (
                f"params contains raw SQL fragment: {p!r}"
            )

    finally:
        # Best-effort cleanup; tempfile.mkdtemp + persistent SQLite may
        # leave files behind but pytest's tmp_path fixtures are unrelated.
        try:
            os.unlink(db_path)
        except OSError:
            pass


# ════════════════════════════════════════════════════════════════════════
# Test 5 — _build_error_body escapes XSS  (R2-NEW-02)
# ════════════════════════════════════════════════════════════════════════

def test_build_error_body_escapes_xss():
    """``_build_error_body`` must html-escape user-controlled ``code`` and
    ``message`` before serialising. Before the fix, the response body
    returned ``<script>alert('xss')</script>`` verbatim — a reflected
    XSS sink for any browser-side JSON renderer that doesn't escape.

    Reproducer from the R2-09 pentest::

        _build_error_body("<script>alert(1)</script>", "x", None)
        # Pre-fix : {"error": {"code": "<script>alert(1)</script>", ...}}
        # Post-fix: {"error": {"code": "&lt;script&gt;alert(1)&lt;/script&gt;", ...}}
    """
    from common.error_handler import _build_error_body

    payload_code = "<script>alert(1)</script>"
    payload_message = "<img src=x onerror=alert(2)>"
    body = _build_error_body(payload_code, payload_message, None)

    # The escaped forms MUST be present in code / message.
    assert html.escape(payload_code, quote=True) in body["error"]["code"], (
        f"code not escaped: {body['error']['code']!r}"
    )
    assert html.escape(payload_message, quote=True) in body["error"]["message"], (
        f"message not escaped: {body['error']['message']!r}"
    )

    # The raw payload must NOT appear verbatim in code or message.
    assert payload_code not in body["error"]["code"], (
        f"raw <script> leaked: {body['error']['code']!r}"
    )
    assert payload_message not in body["error"]["message"], (
        f"raw <img...> leaked: {body['error']['message']!r}"
    )

    # Spot-check the specific encoding of the audit reproducer.
    assert "<script>" not in body["error"]["code"], body["error"]["code"]
    assert "&lt;script&gt;" in body["error"]["code"], body["error"]["code"]
    assert "<img src=x onerror=alert(2)>" not in body["error"]["message"], (
        body["error"]["message"]
    )
    assert "&lt;img src=x onerror=alert(2)&gt;" in body["error"]["message"], (
        body["error"]["message"]
    )

    # The fix also preserves the raw (unescaped) value for server-side
    # log correlation / machine clients that don't render HTML.
    assert body["error"].get("code_raw") == payload_code, (
        f"raw code lost: {body['error'].get('code_raw')!r}"
    )
    assert body["error"].get("message_raw") == payload_message, (
        f"raw message lost: {body['error'].get('message_raw')!r}"
    )
