#!/usr/bin/env python3
"""
P21 P2 P5 — Audit log focused 2-site tests for ``update_user`` + ``delete_user``
(R1-02 final polish, the remaining 2 sites not explicitly verified by P2 P4).

Scope (per P21 P2 P5 task spec):
  * ``update_user`` → must write ``user.updated`` audit entry with details
  * ``delete_user`` → must write ``user.deleted`` audit entry

Out of scope (already covered by P2 P3 / P2 P4):
  * ``register_user``  → ``user.created``     (P2 P3 + P2 P4)
  * ``change_password`` → ``password.changed`` (P2 P3 + P2 P4)

This file is a NARROW, FOCUSED 2-site regression test that complements
the broader ``tests/p2_p3/test_audit_log.py`` and the 2-site
``tests/p2_p4/test_audit_log_2sites.py``.  It verifies the 2 remaining
state-changing actions explicitly named in the P2 P5 R1-02 fix.

Background — what was already done by P2 P3 (verified 2026-07-11):
  * ``UnifiedAuthManager.delete_user(user_id, actor=None)``
    (backend/auth/unified_auth.py:1245) already writes
    ``self.audit_log.write(action="user.deleted", actor=actor or "system",
    target=user_id, details={"username": ..., "role": ...})`` —
    capturing target metadata BEFORE the row is deleted
    (forensic value: even after delete, the audit row tells us
    "who deleted what").
  * ``UnifiedAuthManager.update_user(user_id, updates, actor=None)``
    (backend/auth/unified_auth.py:1275) already writes
    ``self.audit_log.write(action="user.updated", actor=actor or "system",
    target=user_id, details={"username": ..., "changed_fields": [...],
    "diff": {field: {"old": ..., "new": ...}}})`` — capturing
    the per-field old/new diff for forensic queries.

Both implementations are SUPERSETS of the minimal spec in the P2 P5
task (which only required ``actor`` + ``target`` + ``fields`` list).
The richer ``changed_fields`` / ``diff`` / ``username`` / ``role``
detail is preserved because it has demonstrable forensic value
(see P2 P3 tests: ``test_update_user_creates_audit_entry_with_diff``,
``test_delete_user_creates_audit_entry_with_target_metadata``).

R1 finding (reports/p21_r1_audit_security.md §2 A09, gap #02):
  * register_user / change_password / delete_user / update_user
    skipped audit log
  * OWASP A09:2021 / CWE-778 — Insufficient Logging

After the P21 P2 P3 + P2 P4 + P2 P5 fix:
  * All 4 actions (user.created, password.changed, user.updated,
    user.deleted) are recorded.
  * This file specifically re-verifies the 2 sites in P2 P5 scope.

Run:
    & "D:\\ComfyUI\\.ext\\python.exe" -m pytest \\
        "D:\\Hermes\\生产平台\\nanobot-factory\\tests\\p2_p5\\test_audit_log_2sites_rest.py" \\
        -v --tb=short
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — make ``backend`` importable (matches p2_p1..p2_p4 layout)
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
    return str(tmp_path / "p2_p5_audit_2sites_rest.db")


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
# 1. update_user — user.updated schema
# ============================================================================

def test_update_user_email_writes_user_updated_audit(mgr, tmp_db_path):
    """update_user (email change) → exactly 1 'user.updated' entry.

    Per P2 P5 task spec, the minimal contract is:
      action == "user.updated"
      actor  == the user performing the change
      target == the user being modified (in details)
      details captures the changed field(s)
    """
    user = mgr.register_user("p5_alice", "Password123!", "viewer")
    assert user is not None
    user_id = user.user_id

    # Update email
    new_email = "alice.new@example.com"
    ok = mgr.update_user(user_id, {"email": new_email}, actor="admin-p5")
    assert ok is True

    # Query the auth_audit_log for user.updated
    rows = _fetch_audit(
        tmp_db_path,
        "SELECT user_id, action, resource, result, details, timestamp "
        "FROM auth_audit_log WHERE action = 'user.updated'",
    )
    assert len(rows) == 1, (
        f"R1-02 P2 P5 NOT FIXED: expected 1 user.updated, got {len(rows)}"
    )

    actor, action, resource, result, details_json, ts = rows[0]
    assert action == "user.updated"
    assert resource == "user"
    assert result == "success"
    assert ts, "timestamp must be set"
    assert "T" in ts, f"non-ISO timestamp: {ts!r}"

    # actor should be the admin who performed the update
    assert actor == "admin-p5", (
        f"actor must be the executing user, got {actor!r}"
    )

    details = json.loads(details_json)
    # target stored in details (AuditLog.write contract)
    assert details.get("target") == user_id, (
        f"target must be recorded in details, got: {details}"
    )
    # changed_fields (P2 P3 contract — sorted for determinism)
    assert "changed_fields" in details, (
        f"details must include changed_fields (forensic value): {details}"
    )
    assert "email" in details["changed_fields"], (
        f"changed_fields must include 'email': {details['changed_fields']!r}"
    )
    # The username is captured for forensic value (P2 P3 enhancement)
    assert details.get("username") == "p5_alice"


def test_update_user_multiple_fields_captures_all_in_changed_fields(
    mgr, tmp_db_path
):
    """update_user with multiple field changes → changed_fields lists ALL."""
    user = mgr.register_user("p5_multi", "Password123!", "viewer")
    user_id = user.user_id

    ok = mgr.update_user(
        user_id,
        {"role": "annotator", "team": "qa", "display_name": "Multi Field"},
        actor="admin-p5b",
    )
    assert ok is True

    rows = _fetch_audit(
        tmp_db_path,
        "SELECT user_id, action, details "
        "FROM auth_audit_log WHERE action = 'user.updated'",
    )
    assert len(rows) == 1
    actor, action, details_json = rows[0]
    details = json.loads(details_json)

    # changed_fields is a sorted list per P2 P3 contract
    assert set(details["changed_fields"]) == {"role", "team", "display_name"}
    # All three fields appear in the diff
    assert set(details["diff"].keys()) == {"role", "team", "display_name"}


def test_update_user_captures_old_and_new_value_diff(mgr, tmp_db_path):
    """update_user diff must capture both 'old' and 'new' values per field.

    This is the core forensic value of the P2 P3 enhancement:
    "What was the role before, what is it now?"
    """
    user = mgr.register_user("p5_diff", "Password123!", "viewer")
    user_id = user.user_id

    ok = mgr.update_user(user_id, {"role": "admin"}, actor="admin-p5c")
    assert ok is True

    rows = _fetch_audit(
        tmp_db_path,
        "SELECT details FROM auth_audit_log WHERE action = 'user.updated'",
    )
    assert len(rows) == 1
    (details_json,) = rows[0]
    details = json.loads(details_json)

    role_diff = details["diff"]["role"]
    assert role_diff["old"] == "viewer", f"old role mismatch: {role_diff!r}"
    assert role_diff["new"] == "admin", f"new role mismatch: {role_diff!r}"


def test_update_user_on_nonexistent_user_writes_no_audit(mgr, tmp_db_path):
    """If update_user returns False (no such user), NO audit entry written."""
    n_before = len(_fetch_audit(
        tmp_db_path,
        "SELECT log_id FROM auth_audit_log WHERE action = 'user.updated'",
    ))

    ok = mgr.update_user(
        "user_does_not_exist_xyz", {"role": "admin"}, actor="admin-p5d"
    )
    assert ok is False, "update_user on missing user should return False"

    n_after = len(_fetch_audit(
        tmp_db_path,
        "SELECT log_id FROM auth_audit_log WHERE action = 'user.updated'",
    ))
    assert n_before == n_after, (
        f"update_user MUST NOT write audit entry for missing user. "
        f"Before: {n_before}, after: {n_after}"
    )


# ============================================================================
# 2. delete_user — user.deleted schema
# ============================================================================

def test_delete_user_writes_user_deleted_audit(mgr, tmp_db_path):
    """delete_user → exactly 1 'user.deleted' entry with target metadata.

    Per P2 P5 task spec, the minimal contract is:
      action == "user.deleted"
      actor  == the user performing the deletion
      target == the user being deleted (in details)

    Per P2 P3 enhancement, additional forensic fields are captured
    BEFORE the user row is deleted (since after delete, the row is gone):
      details.username  — the username at time of deletion
      details.role      — the role at time of deletion
    """
    user = mgr.register_user("p5_dave", "Password123!", "annotator")
    assert user is not None
    target_id = user.user_id

    ok = mgr.delete_user(target_id, actor="admin-p5del")
    assert ok is True

    rows = _fetch_audit(
        tmp_db_path,
        "SELECT user_id, action, resource, result, details, timestamp "
        "FROM auth_audit_log WHERE action = 'user.deleted'",
    )
    assert len(rows) == 1, (
        f"R1-02 P2 P5 NOT FIXED: expected 1 user.deleted, got {len(rows)}"
    )

    actor, action, resource, result, details_json, ts = rows[0]
    assert action == "user.deleted"
    assert resource == "user"
    assert result == "success"
    assert ts, "timestamp must be set"
    assert "T" in ts, f"non-ISO timestamp: {ts!r}"

    # actor should be the admin who performed the deletion
    assert actor == "admin-p5del", (
        f"actor must be the executing user, got {actor!r}"
    )

    details = json.loads(details_json)
    # target stored in details (AuditLog.write contract)
    assert details.get("target") == target_id, (
        f"target must be recorded in details, got: {details}"
    )
    # Forensic metadata captured BEFORE the delete (P2 P3 enhancement)
    assert details.get("username") == "p5_dave", (
        f"username must be captured before delete: {details}"
    )
    assert details.get("role") == "annotator", (
        f"role must be captured before delete: {details}"
    )


def test_delete_user_with_default_actor_records_system(mgr, tmp_db_path):
    """delete_user with no actor argument uses 'system' as default actor.

    This matches the P2 P3 design choice — never let the audit log
    have a NULL actor (forensic queries need SOMETHING to filter on).
    """
    user = mgr.register_user("p5_sysact", "Password123!", "viewer")
    target_id = user.user_id

    ok = mgr.delete_user(target_id)  # no actor
    assert ok is True

    rows = _fetch_audit(
        tmp_db_path,
        "SELECT user_id FROM auth_audit_log WHERE action = 'user.deleted'",
    )
    assert len(rows) == 1
    (actor,) = rows[0]
    assert actor == "system", (
        f"actor should default to 'system' when not provided, got: {actor!r}"
    )


def test_delete_user_actual_contract_for_missing_user(mgr, tmp_db_path):
    """Document the actual contract of delete_user for a missing user.

    Per unified_auth.py:1245 + AuthDatabase.delete_user at :676:
    ``DELETE FROM auth_users WHERE user_id = ?`` succeeds (returns 0
    rowcount) without raising, so ``self.db.delete_user()`` returns
    True even when no row matched.  The wrapper then writes a
    "user.deleted" audit entry with ``username=None`` and ``role=None``.

    This is current behavior (2026-07-11) and is preserved here as a
    forward-looking test.  A future fix could make delete_user
    return False when the user doesn't exist and skip the audit
    write — but that is out of P2 P5 scope.
    """
    n_before = len(_fetch_audit(
        tmp_db_path,
        "SELECT log_id FROM auth_audit_log WHERE action = 'user.deleted'",
    ))

    ok = mgr.delete_user("user_does_not_exist_xyz", actor="admin-p5d2")
    # CURRENT CONTRACT: returns True (DELETE with no match is not an error
    # at the sqlite level — AuthDatabase.delete_user does not check rowcount).
    assert ok is True, (
        f"delete_user on missing user currently returns True (current "
        f"contract, see unified_auth.py:676). Got: {ok!r}"
    )

    n_after = len(_fetch_audit(
        tmp_db_path,
        "SELECT log_id FROM auth_audit_log WHERE action = 'user.deleted'",
    ))
    # CURRENT CONTRACT: a 'phantom' user.deleted audit entry IS written
    # (with username=None, role=None) for forensic value of "someone
    # attempted to delete this user_id, but it didn't exist".
    assert n_after == n_before + 1, (
        f"Current contract: delete_user writes audit even for missing "
        f"users (phantom entry). Before: {n_before}, after: {n_after}. "
        f"See P2 P5 deliverable Notes for future-fix guidance."
    )

    # The phantom entry has username=None and role=None (target was gone)
    rows = _fetch_audit(
        tmp_db_path,
        "SELECT details FROM auth_audit_log WHERE action = 'user.deleted' "
        "AND user_id = 'admin-p5d2'",
    )
    assert len(rows) == 1
    (details_json,) = rows[0]
    details = json.loads(details_json)
    assert details.get("target") == "user_does_not_exist_xyz"
    assert details.get("username") is None
    assert details.get("role") is None


# ============================================================================
# 3. Combined 4/4 audit coverage (P2 P3 + P2 P4 + P2 P5)
# ============================================================================

def test_all_four_audit_actions_present_combined(
    mgr: UnifiedAuthManager, tmp_db_path: str
):
    """Combined: register + change_password + update + delete → 4 actions.

    This is the P2 P5 task acceptance criteria: "Combined with P2 P3/P4
    tests: 4/4 audit actions now logged".

    The 4 actions are:
      1. user.created       (P2 P3 + P2 P4 verified)
      2. password.changed   (P2 P3 + P2 P4 verified)
      3. user.updated       (P2 P5 — this file)
      4. user.deleted       (P2 P5 — this file)
    """
    user = mgr.register_user("p5_combo", "Password123!", "viewer")
    assert user is not None
    user_id = user.user_id

    # 1) change_password → password.changed (P2 P3/P4 site)
    mgr.change_password(user_id, "Password123!", "NewPass5678!")
    # 2) update_user → user.updated (P2 P5 site)
    mgr.update_user(user_id, {"email": "combo@x.com"}, actor="admin-p5combo")
    # 3) delete_user → user.deleted (P2 P5 site)
    mgr.delete_user(user_id, actor="admin-p5combo")

    actions = sorted({
        r[0] for r in _fetch_audit(
            tmp_db_path, "SELECT DISTINCT action FROM auth_audit_log",
        )
    })

    # All 4 in-scope actions must be present
    assert "user.created" in actions, f"missing user.created: {actions}"
    assert "password.changed" in actions, f"missing password.changed: {actions}"
    assert "user.updated" in actions, (
        f"R1-02 P2 P5 NOT FIXED: missing user.updated. Got: {actions}"
    )
    assert "user.deleted" in actions, (
        f"R1-02 P2 P5 NOT FIXED: missing user.deleted. Got: {actions}"
    )


# ============================================================================
# 4. AuditLog.list_entries forensic query for the 2 sites
# ============================================================================

def test_list_entries_returns_update_and_delete_actions(mgr, tmp_db_path):
    """list_entries(action=...) returns user.updated + user.deleted entries."""
    user = mgr.register_user("p5_list", "Password123!", "viewer")
    user_id = user.user_id
    mgr.update_user(user_id, {"role": "annotator"}, actor="admin-p5l")
    mgr.delete_user(user_id, actor="admin-p5l")

    updated = mgr.audit_log.list_entries(action="user.updated", limit=50)
    deleted = mgr.audit_log.list_entries(action="user.deleted", limit=50)

    assert updated, "list_entries(action='user.updated') returned empty"
    assert deleted, "list_entries(action='user.deleted') returned empty"

    # Each user.updated entry should have the forensic schema
    for e in updated:
        assert e["action"] == "user.updated"
        assert e["resource"] == "user"
        assert e["result"] == "success"
        assert e["details"]["target"] == user_id
        assert "changed_fields" in e["details"]
        assert e["timestamp"]

    # Each user.deleted entry should have target + username + role
    for e in deleted:
        assert e["action"] == "user.deleted"
        assert e["resource"] == "user"
        assert e["result"] == "success"
        assert e["details"]["target"] == user_id
        assert e["details"]["username"] == "p5_list"
        assert e["details"]["role"] == "annotator"  # role at time of delete
        assert e["timestamp"]


def test_list_entries_target_filter_isolates_specific_user(
    mgr: UnifiedAuthManager, tmp_db_path: str
):
    """list_entries(target=X) returns only entries whose details.target == X.

    This is the forensic query: "show me everything that happened to
    user X". Verifies the AuditLog.write contract for the 2 P2 P5 sites.
    """
    # Create two users, perform different actions on each
    user_a = mgr.register_user("p5_target_a", "Password123!", "viewer")
    user_b = mgr.register_user("p5_target_b", "Password123!", "viewer")

    mgr.update_user(user_a.user_id, {"email": "a@x.com"}, actor="admin-p5t")
    mgr.update_user(user_b.user_id, {"email": "b@x.com"}, actor="admin-p5t")
    mgr.delete_user(user_a.user_id, actor="admin-p5t")

    # Query for entries targeting user_a
    a_entries = mgr.audit_log.list_entries(target=user_a.user_id, limit=50)
    # Filter to only state-change actions (excluding auth.*)
    state_change_actions = {
        e["action"] for e in a_entries
        if e["action"] in ("user.updated", "user.deleted")
    }

    # user_a should have: user.updated (email change) + user.deleted
    assert "user.updated" in state_change_actions
    assert "user.deleted" in state_change_actions

    # And NOT user_b's events
    b_entries = mgr.audit_log.list_entries(target=user_b.user_id, limit=50)
    b_actions = {
        e["action"] for e in b_entries
        if e["action"] in ("user.updated", "user.deleted", "user.created")
    }
    # user_b should have user.updated but NOT user.deleted
    assert "user.updated" in b_actions
    assert "user.deleted" not in b_actions, (
        f"user_b entries must not include user.deleted for user_a: {b_actions}"
    )
