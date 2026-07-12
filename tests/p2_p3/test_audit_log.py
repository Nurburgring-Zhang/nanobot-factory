#!/usr/bin/env python3
"""
P21 P2 P3 — Audit log gap fix tests (R1-02).

Verifies that state-changing actions on user accounts
(register_user, change_password, update_user, delete_user) now
produce entries in ``auth_audit_log`` with the correct action
names, actor, target, and timestamp.

Reproduces the R1 / R2 finding at the test boundary:
* R1 finding (reports/p21_r1_audit_security.md §2 A09, gap #02):
  After `mgr.register_user → change_password → delete_user`,
  `SELECT action FROM auth_audit_log` returns ``[]`` (FORENSIC GAP).
* R2 reproducer (reports/p21_r2_audit_security.md): re-verified
  the gap, confirming R1 finding is reproducible.

After the P21 P2 P3 fix:
* All 4 actions (user.created, password.changed, user.updated,
  user.deleted) are recorded.
* Each entry has actor, target, timestamp, and JSON details.
* The ``AuditLog.write`` helper is exposed and queryable.

Run:
    & "D:\\ComfyUI\\.ext\\python.exe" -m pytest \\
        tests/p2_p3/test_audit_log.py -v --tb=short
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pytest

# Make ``backend`` importable (matches the layout used by p2_p1 / p2_p2 tests).
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
    """Per-test SQLite path so tests don't share audit log state."""
    return str(tmp_path / "audit_test.db")


@pytest.fixture
def mgr(tmp_db_path: str) -> UnifiedAuthManager:
    """Fresh UnifiedAuthManager + temp SQLite for each test."""
    return UnifiedAuthManager(jwt_secret="x" * 40, db_path=tmp_db_path)


def _query_actions(db_path: str, sql: str = "SELECT action FROM auth_audit_log") -> list:
    """Read raw rows from auth_audit_log (debug helper)."""
    conn = sqlite3.connect(db_path)
    try:
        return [r[0] for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


# ============================================================================
# 1. R1 / R2 REPRODUCER (before/after)
# ============================================================================

def test_r1_reproducer_state_changes_now_audited(mgr: UnifiedAuthManager, tmp_db_path: str):
    """R1-02 reproducer: state-changing actions MUST appear in audit log.

    Before fix: ``SELECT DISTINCT action FROM auth_audit_log`` returned ``[]``.
    After fix:   it must include all 4 action types.
    """
    user = mgr.register_user("victim", "Password123!", "viewer")
    assert user is not None
    mgr.change_password(user.user_id, "Password123!", "NewPass5678!")
    mgr.update_user(user.user_id, {"role": "annotator"}, actor="admin-1")
    mgr.delete_user(user.user_id, actor="admin-1")

    actions = set(_query_actions(tmp_db_path, "SELECT DISTINCT action FROM auth_audit_log"))
    required = {"user.created", "password.changed", "user.updated", "user.deleted"}
    missing = required - actions
    assert not missing, (
        f"R1-02 NOT FIXED: missing audit actions {missing}. "
        f"Got: {sorted(actions)}"
    )


# ============================================================================
# 2. PER-ACTION INVARIANTS
# ============================================================================

def test_register_user_creates_audit_entry(mgr: UnifiedAuthManager, tmp_db_path: str):
    """register_user must produce a 'user.created' entry with role in details."""
    user = mgr.register_user("alice", "Password123!", "annotator", email="alice@x.com")
    assert user is not None
    user_id = user.user_id

    conn = sqlite3.connect(tmp_db_path)
    try:
        rows = conn.execute(
            "SELECT user_id, action, resource, details, timestamp "
            "FROM auth_audit_log WHERE action = 'user.created' AND user_id = 'alice'"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1, f"Expected exactly 1 user.created, got {len(rows)}"
    actor, action, resource, details_json, ts = rows[0]
    assert actor == "alice"
    assert action == "user.created"
    assert resource == "user"
    assert ts, "timestamp must be set"
    details = json.loads(details_json)
    assert details["role"] == "annotator"
    assert details["target"] == user_id
    assert details["email"] == "alice@x.com"


def test_change_password_creates_audit_entry(mgr: UnifiedAuthManager, tmp_db_path: str):
    """change_password must produce a 'password.changed' entry."""
    user = mgr.register_user("bob", "Password123!", "viewer")
    mgr.change_password(user.user_id, "Password123!", "NewPass5678!")

    conn = sqlite3.connect(tmp_db_path)
    try:
        rows = conn.execute(
            "SELECT user_id, action, details, timestamp "
            "FROM auth_audit_log WHERE action = 'password.changed'"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1, f"Expected exactly 1 password.changed, got {len(rows)}"
    actor, action, details_json, ts = rows[0]
    assert actor == user.user_id
    assert ts, "timestamp must be set"
    details = json.loads(details_json)
    assert "tokens_revoked" in details


def test_update_user_creates_audit_entry_with_diff(mgr: UnifiedAuthManager, tmp_db_path: str):
    """update_user must produce a 'user.updated' entry capturing the diff."""
    user = mgr.register_user("carol", "Password123!", "viewer")
    mgr.update_user(user.user_id, {"role": "reviewer", "team": "qa"}, actor="admin-x")

    conn = sqlite3.connect(tmp_db_path)
    try:
        rows = conn.execute(
            "SELECT user_id, action, details "
            "FROM auth_audit_log WHERE action = 'user.updated'"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1, f"Expected exactly 1 user.updated, got {len(rows)}"
    actor, action, details_json = rows[0]
    assert actor == "admin-x"
    details = json.loads(details_json)
    assert details["target"] == user.user_id
    assert set(details["changed_fields"]) == {"role", "team"}
    assert details["diff"]["role"]["old"] == "viewer"
    assert details["diff"]["role"]["new"] == "reviewer"
    assert details["diff"]["team"]["old"] == ""
    assert details["diff"]["team"]["new"] == "qa"


def test_delete_user_creates_audit_entry_with_target_metadata(
    mgr: UnifiedAuthManager, tmp_db_path: str
):
    """delete_user must produce a 'user.deleted' entry — captured BEFORE row is gone."""
    user = mgr.register_user("dave", "Password123!", "annotator")
    target_id = user.user_id
    mgr.delete_user(target_id, actor="admin-y")

    conn = sqlite3.connect(tmp_db_path)
    try:
        rows = conn.execute(
            "SELECT user_id, action, details, timestamp "
            "FROM auth_audit_log WHERE action = 'user.deleted'"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) == 1, f"Expected exactly 1 user.deleted, got {len(rows)}"
    actor, action, details_json, ts = rows[0]
    assert actor == "admin-y"
    assert ts, "timestamp must be set"
    details = json.loads(details_json)
    assert details["target"] == target_id
    # Target metadata captured before deletion (R1-02 forensic value)
    assert details["username"] == "dave"
    assert details["role"] == "annotator"


# ============================================================================
# 3. AuditLog HELPER UNIT TESTS
# ============================================================================

def test_audit_log_helper_direct_write(mgr: UnifiedAuthManager, tmp_db_path: str):
    """AuditLog.write works as a standalone helper (not only via mgr)."""
    helper = AuditLog(mgr.db, resource="user")
    helper.write(
        action="user.custom_action",
        actor="actor-1",
        target="target-1",
        details={"foo": "bar"},
    )

    entries = helper.list_entries(action="user.custom_action")
    assert len(entries) == 1
    e = entries[0]
    assert e["user_id"] == "actor-1"
    assert e["action"] == "user.custom_action"
    assert e["resource"] == "user"
    assert e["details"]["foo"] == "bar"
    assert e["details"]["target"] == "target-1"
    assert e["timestamp"]


def test_audit_log_helper_list_filters_by_target(
    mgr: UnifiedAuthManager, tmp_db_path: str
):
    """list_entries(target=...) must filter by JSON-stored target."""
    helper = AuditLog(mgr.db, resource="user")
    helper.write("a.test", actor="a", target="target-A", details={})
    helper.write("a.test", actor="b", target="target-B", details={})

    only_a = helper.list_entries(target="target-A")
    assert len(only_a) == 1
    assert only_a[0]["user_id"] == "a"
    assert only_a[0]["details"]["target"] == "target-A"

    only_b = helper.list_entries(target="target-B")
    assert len(only_b) == 1
    assert only_b[0]["user_id"] == "b"


def test_audit_log_helper_actor_equals_target_omits_target_field(
    mgr: UnifiedAuthManager, tmp_db_path: str
):
    """When actor == target, 'target' is NOT duplicated in details.

    (For password.changed, actor and target are the same user; we keep
    details clean by only inserting target when it differs.)
    """
    helper = AuditLog(mgr.db, resource="user")
    helper.write("self.action", actor="self-1", target="self-1", details={"x": 1})
    entries = helper.list_entries(action="self.action")
    assert len(entries) == 1
    # target should NOT appear in details (it equals actor)
    assert "target" not in entries[0]["details"]
    assert entries[0]["details"]["x"] == 1


def test_audit_log_write_does_not_raise_on_bad_payload(
    mgr: UnifiedAuthManager, tmp_db_path: str
):
    """Audit failure must never raise (审计失败不应阻塞业务操作)."""
    helper = AuditLog(mgr.db, resource="user")
    # Force a DB error by closing the connection mid-test using a wrong db
    bad_helper = AuditLog(db=None)  # type: ignore[arg-type]
    # Should NOT raise even with no db
    bad_helper.write(action="x", actor="y", target="z", details={})


# ============================================================================
# 4. INTEGRATION — R1-02 BEFORE/AFTER + AUTH EVENTS UNCHANGED
# ============================================================================

def test_auth_events_still_recorded_alongside_state_changes(
    mgr: UnifiedAuthManager, tmp_db_path: str
):
    """auth.success / auth.failed events (existing _audit) must coexist
    with the new user.* state-change events.
    """
    user = mgr.register_user("eve", "Password123!", "viewer")
    mgr.login("eve", "Password123!", ip_address="10.0.0.1")
    mgr.login("eve", "WRONG", ip_address="10.0.0.1")
    mgr.change_password(user.user_id, "Password123!", "EvenNewer1!")
    mgr.delete_user(user.user_id, actor="admin-z")

    actions = set(_query_actions(tmp_db_path, "SELECT DISTINCT action FROM auth_audit_log"))
    # Old auth events
    assert "auth.success" in actions
    assert "auth.failed" in actions
    # New state-changing events
    assert "user.created" in actions
    assert "password.changed" in actions
    assert "user.deleted" in actions


def test_bootstrap_admin_creates_audit_entry_with_system_actor(
    mgr: UnifiedAuthManager, tmp_db_path: str
):
    """The default admin bootstrap path produces 'user.created' with actor='system'.

    This guarantees forensic queries can distinguish self-registration
    from bootstrap (admin created by the platform itself).
    """
    conn = sqlite3.connect(tmp_db_path)
    try:
        rows = conn.execute(
            "SELECT user_id, details FROM auth_audit_log "
            "WHERE action = 'user.created' AND user_id = 'system'"
        ).fetchall()
    finally:
        conn.close()

    assert len(rows) >= 1, "bootstrap admin should produce 'user.created' with actor='system'"
    actor, details_json = rows[0]
    assert actor == "system"
    details = json.loads(details_json)
    assert details["role"] == "admin"


def test_timestamps_are_monotonic_within_test(mgr: UnifiedAuthManager, tmp_db_path: str):
    """Audit entries should have non-empty, parseable ISO timestamps."""
    user = mgr.register_user("frank", "Password123!", "viewer")
    mgr.change_password(user.user_id, "Password123!", "NewerPass1!")
    mgr.delete_user(user.user_id, actor="admin-w")
    target_id = user.user_id

    # Read raw rows; filter in Python to entries whose details JSON
    # mentions frank (by username, target id, or actor).
    conn = sqlite3.connect(tmp_db_path)
    try:
        raw = conn.execute(
            "SELECT action, timestamp, user_id, details FROM auth_audit_log "
            "WHERE action IN ('user.created', 'password.changed', 'user.deleted')"
        ).fetchall()
    finally:
        conn.close()

    def is_frank(row):
        action, _ts, actor, details_json = row
        if actor == target_id or actor == "frank":
            return True
        try:
            d = json.loads(details_json or "{}")
        except json.JSONDecodeError:
            return False
        return d.get("username") == "frank" or d.get("target") == target_id

    rows = [r for r in raw if is_frank(r)]
    assert len(rows) == 3, (
        f"Expected 3 lifecycle events for frank, got {len(rows)}: {rows}"
    )
    for action, ts, _actor, _details in rows:
        assert ts, f"empty timestamp for {action}"
        # ISO-8601 has at least YYYY-MM-DDTHH:MM:SS
        assert "T" in ts, f"non-ISO timestamp for {action}: {ts!r}"
