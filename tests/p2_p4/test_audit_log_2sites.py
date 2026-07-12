#!/usr/bin/env python3
"""
P21 P2 P4 — Audit log 2-site focused tests (R1-02).

Scope (per P21 P2 P4 task spec, NOT a redo of P21 P2 P3):
  * ``register_user``   → must write ``user.created``   audit entry
  * ``change_password`` → must write ``password.changed`` audit entry

Out of scope (deferred to P2 P5):
  * ``delete_user``     → ``user.deleted``     (P2 P5)
  * ``update_user``     → ``user.updated``     (P2 P5)

This file is a NARROW, FOCUSED 2-site regression test that complements
the broader 4-site ``tests/p2_p3/test_audit_log.py``.  It verifies
the 2 functions explicitly named in the P2 P4 R1-02 fix and asserts:

  1. R1 reproducer at 2-site boundary (R1-02 partial re-verification)
  2. ``user.created`` payload schema (actor / target / details / timestamp)
  3. ``password.changed`` payload schema (actor == target, tokens_revoked)
  4. Failure paths do NOT leak audit entries
  5. ``list_entries`` forensic query works for these 2 actions
  6. Multiple sequential password changes produce N audit entries (no dedup)

The AuditLog helper class is in ``backend/auth/audit.py`` and is
initialized in ``UnifiedAuthManager.__init__`` via
``self.audit_log = AuditLog(self.db, resource="user")``.

R1 finding (reports/p21_r1_audit_security.md §2 A09, gap #02):
  * register_user / change_password / delete_user skipped audit log
  * OWASP A09:2021 / CWE-778 — Insufficient Logging

Run:
    & "D:\\ComfyUI\\.ext\\python.exe" -m pytest \\
        "D:\\Hermes\\生产平台\\nanobot-factory\\tests\\p2_p4\\test_audit_log_2sites.py" \\
        -v --tb=short
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — make ``backend`` importable (matches p2_p1 / p2_p2 / p2_p3 layout)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Test mode so the bootstrap admin gets an ephemeral random password
# instead of raising AdminConfigError.
os.environ.setdefault("IMDF_TEST_MODE", "1")

from auth.unified_auth import UnifiedAuthManager  # noqa: E402
from auth.audit import AuditLog  # noqa: E402


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def tmp_db_path(tmp_path: Path) -> str:
    """Per-test SQLite path so audit log state never leaks across tests."""
    return str(tmp_path / "p2_p4_audit_2sites.db")


@pytest.fixture
def mgr(tmp_db_path: str) -> UnifiedAuthManager:
    """Fresh UnifiedAuthManager with ephemeral temp SQLite."""
    return UnifiedAuthManager(jwt_secret="x" * 40, db_path=tmp_db_path)


def _fetch_audit(db_path: str, sql: str, params: tuple = ()) -> list:
    """Read raw rows from auth_audit_log (raw fetchall wrapper)."""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


# ============================================================================
# 1. R1-02 REPRODUCER (2-site re-validation)
# ============================================================================

def test_r1_reproducer_2sites_now_audited(mgr, tmp_db_path):
    """R1-02 partial re-verification: register_user + change_password now
    produce audit entries. (delete_user + update_user are P2 P5 scope.)

    Before the P21 P2 P3 fix (and the P2 P4 verification pass), the
    R1 reproducer returned ``[]`` from auth_audit_log.  After the fix
    the 2 in-scope actions must be present.
    """
    user = mgr.register_user("r1_victim", "Password123!", "viewer")
    assert user is not None
    mgr.change_password(user.user_id, "Password123!", "NewPass5678!")

    actions = sorted({
        r[0] for r in _fetch_audit(
            tmp_db_path,
            "SELECT DISTINCT action FROM auth_audit_log",
        )
    })

    # Must contain BOTH in-scope actions
    assert "user.created" in actions, (
        f"R1-02 NOT FIXED for register_user: missing 'user.created'. "
        f"Got: {actions}"
    )
    assert "password.changed" in actions, (
        f"R1-02 NOT FIXED for change_password: missing 'password.changed'. "
        f"Got: {actions}"
    )


# ============================================================================
# 2. register_user — user.created schema
# ============================================================================

def test_register_user_writes_user_created_with_full_schema(mgr, tmp_db_path):
    """register_user → exactly 1 'user.created' with all forensic fields."""
    user = mgr.register_user(
        "alice_2sites", "Password123!", "annotator",
        email="alice@x.com", team="production",
    )
    assert user is not None
    user_id = user.user_id

    rows = _fetch_audit(
        tmp_db_path,
        "SELECT user_id, action, resource, result, ip_address, "
        "details, timestamp "
        "FROM auth_audit_log WHERE action = 'user.created'",
    )

    # Filter to alice's record (in case bootstrap admin also wrote one)
    rows = [r for r in rows if r[0] == "alice_2sites"]
    assert len(rows) == 1, (
        f"Expected exactly 1 user.created for alice, got {len(rows)}"
    )

    (actor, action, resource, result, ip, details_json, ts) = rows[0]
    assert actor == "alice_2sites", f"actor mismatch: {actor!r}"
    assert action == "user.created"
    assert resource == "user", f"resource should be 'user' (not 'auth'): {resource!r}"
    assert result == "success"
    assert ip is None  # register_user is internal; no IP at this layer
    assert ts, "timestamp must be populated"
    # ISO-8601 check (loose)
    assert "T" in ts and len(ts) >= 19, f"non-ISO timestamp: {ts!r}"

    details = json.loads(details_json)
    # Required keys for forensic query
    for k in ("role", "team", "email", "target"):
        assert k in details, f"missing key {k!r} in details: {details}"
    assert details["role"] == "annotator"
    assert details["team"] == "production"
    assert details["email"] == "alice@x.com"
    assert details["target"] == user_id


def test_register_user_duplicate_does_not_write_audit(mgr, tmp_db_path):
    """If register_user returns None (duplicate username), NO audit entry."""
    first = mgr.register_user("dup_user", "Password123!", "viewer")
    assert first is not None

    # Snapshot the count after first registration
    n_before = len(_fetch_audit(
        tmp_db_path, "SELECT log_id FROM auth_audit_log WHERE action = 'user.created'",
    ))

    second = mgr.register_user("dup_user", "Another123!", "admin")
    assert second is None, "duplicate register_user should return None"

    n_after = len(_fetch_audit(
        tmp_db_path, "SELECT log_id FROM auth_audit_log WHERE action = 'user.created'",
    ))
    assert n_before == n_after, (
        f"register_user MUST NOT write audit entry on duplicate. "
        f"Before: {n_before}, after: {n_after}"
    )


# ============================================================================
# 3. change_password — password.changed schema
# ============================================================================

def test_change_password_writes_password_changed_with_actor_eq_target(mgr, tmp_db_path):
    """change_password → exactly 1 'password.changed' with actor == target.

    For password.changed, the actor is the user themselves (self-service
    password change).  The actor and target are intentionally the same
    so forensic queries don't need a JOIN to find out whose password
    was changed.
    """
    user = mgr.register_user("bob_2sites", "Password123!", "viewer")
    mgr.change_password(user.user_id, "Password123!", "NewPass5678!")

    rows = _fetch_audit(
        tmp_db_path,
        "SELECT user_id, action, resource, result, details, timestamp "
        "FROM auth_audit_log WHERE action = 'password.changed'",
    )
    assert len(rows) == 1, (
        f"Expected exactly 1 password.changed, got {len(rows)}"
    )

    actor, action, resource, result, details_json, ts = rows[0]
    assert action == "password.changed"
    assert actor == user.user_id, f"actor must be the user_id, got {actor!r}"
    assert resource == "user"
    assert result == "success"
    assert ts, "timestamp must be set"
    assert "T" in ts, f"non-ISO timestamp: {ts!r}"

    details = json.loads(details_json)
    # tokens_revoked key is recorded (P10R4-1 auto-revoke on change)
    assert "tokens_revoked" in details, (
        f"details must record tokens_revoked (P10R4-1 invariant): {details}"
    )
    assert isinstance(details["tokens_revoked"], int)
    # Actor==target ⇒ 'target' should be omitted from details to avoid duplication
    # (AuditLog.write's contract: only set target if it differs from actor)
    assert "target" not in details or details.get("target") == user.user_id


def test_change_password_wrong_old_password_does_not_write_audit(mgr, tmp_db_path):
    """If change_password returns False (wrong old password), NO audit entry."""
    user = mgr.register_user("charlie_2sites", "Password123!", "viewer")

    n_before = len(_fetch_audit(
        tmp_db_path,
        "SELECT log_id FROM auth_audit_log WHERE action = 'password.changed'",
    ))

    ok = mgr.change_password(user.user_id, "WRONG_OLD", "NewPass5678!")
    assert ok is False, "wrong old password should return False"

    n_after = len(_fetch_audit(
        tmp_db_path,
        "SELECT log_id FROM auth_audit_log WHERE action = 'password.changed'",
    ))
    assert n_before == n_after, (
        f"change_password MUST NOT write audit entry on auth failure. "
        f"Before: {n_before}, after: {n_after}"
    )


def test_change_password_multiple_changes_each_write_audit(mgr, tmp_db_path):
    """Each successful change_password → exactly 1 entry (no dedup)."""
    user = mgr.register_user("dora_2sites", "Password123!", "viewer")
    mgr.change_password(user.user_id, "Password123!", "NewPass1!")
    mgr.change_password(user.user_id, "NewPass1!", "NewPass2!")
    mgr.change_password(user.user_id, "NewPass2!", "NewPass3!")

    rows = _fetch_audit(
        tmp_db_path,
        "SELECT user_id, details FROM auth_audit_log "
        "WHERE action = 'password.changed' AND user_id = ?",
        (user.user_id,),
    )
    assert len(rows) == 3, (
        f"Expected 3 password.changed entries (one per change), got {len(rows)}"
    )
    # All entries point to the same user
    for actor, _details_json in rows:
        assert actor == user.user_id


# ============================================================================
# 4. list_entries forensic query
# ============================================================================

def test_list_entries_returns_register_and_password_actions(mgr, tmp_db_path):
    """AuditLog.list_entries returns BOTH in-scope actions for the user.

    Note on actor semantics (intentional design from P2 P3):
      * ``user.created``     → actor=username (no user_id yet at write time)
      * ``password.changed`` → actor=user_id (the user themselves)
    So we filter with two separate ``action=`` queries (action filter is
    exact, no ambiguity).
    """
    user = mgr.register_user("eve_2sites", "Password123!", "viewer")
    mgr.change_password(user.user_id, "Password123!", "NewPass1!")

    created = mgr.audit_log.list_entries(action="user.created", limit=50)
    pw_changed = mgr.audit_log.list_entries(action="password.changed", limit=50)

    # Both actions present in the audit log
    assert created, "list_entries(action='user.created') returned empty"
    assert pw_changed, "list_entries(action='password.changed') returned empty"

    # user.created: actor=username, target=user_id, role in details
    alice_created = [e for e in created if e["user_id"] == "eve_2sites"]
    assert len(alice_created) == 1, (
        f"Expected 1 user.created for eve_2sites, got {len(alice_created)}"
    )
    e = alice_created[0]
    assert e["details"]["target"] == user.user_id
    assert e["details"]["role"] == "viewer"

    # password.changed: actor=user_id, tokens_revoked populated
    bob_pw = [e for e in pw_changed if e["user_id"] == user.user_id]
    assert len(bob_pw) == 1, (
        f"Expected 1 password.changed for {user.user_id}, got {len(bob_pw)}"
    )
    e = bob_pw[0]
    assert e["details"]["tokens_revoked"] >= 0

    # Each entry must have the forensic fields populated
    for e in created + pw_changed:
        assert e["user_id"], f"actor/user_id empty: {e}"
        assert e["action"], f"action empty: {e}"
        assert e["resource"] == "user", (
            f"resource should be 'user' for state-change events: {e}"
        )
        assert e["result"] == "success"
        assert e["timestamp"], f"timestamp empty: {e}"
        assert e["details"], f"details empty: {e}"


def test_filter_by_action_returns_only_password_changed(mgr, tmp_db_path):
    """``list_entries(action='password.changed')`` returns only that action."""
    user = mgr.register_user("frank_2sites", "Password123!", "viewer")
    mgr.change_password(user.user_id, "Password123!", "NewPass1!")

    entries = mgr.audit_log.list_entries(action="password.changed", limit=50)
    assert len(entries) >= 1
    for e in entries:
        assert e["action"] == "password.changed"
        assert e["resource"] == "user"
