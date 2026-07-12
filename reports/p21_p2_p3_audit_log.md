# P21 Phase 2 P3 — Audit Log Gap Fix on State-Changing Actions (R1-02)

**Author**: coder (P21 P2 P3 security fix)
**Date**: 2026-07-11
**R1 reference**: `reports/p21_r1_audit_security.md` §2 A09 + §3 gap #02
**R2 reference**: `reports/p21_r2_audit_security.md` (re-verified)
**Audit severity**: P0 / OWASP A09:2021 — Security Logging & Monitoring
**CWE**: CWE-778 Insufficient Logging

---

## 1. Problem statement

R1 finding (p21_r1_audit_security.md, gap #02):

> State-changing actions (`register_user`, `change_password`, `delete_user`)
> in `backend/auth/unified_auth.py` skip the audit log.  Only `auth.success`,
> `auth.failed`, `auth.locked` are recorded.

R2 reproducer (p21_r2_audit_security.md):

> After `mgr.register_user() → change_password() → delete_user()`, querying
> `auth_audit_log` returns `[]`.  R1 finding is **100% re-validated**.

### R2 reproducer (before fix)

```python
import os, sys, tempfile, sqlite3
os.environ['IMDF_TEST_MODE'] = '1'
sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory\backend')
from auth.unified_auth import UnifiedAuthManager

td = tempfile.mkdtemp()
db = os.path.join(td, 'a09.db')
mgr = UnifiedAuthManager(jwt_secret='x'*40, db_path=db)

mgr.register_user('victim', 'Password123!', 'viewer')
u = mgr.get_user(username='victim')
mgr.change_password(u.user_id, 'Password123!', 'NewPass5678!')
mgr.delete_user(u.user_id)

conn = sqlite3.connect(db)
print([r[0] for r in
       conn.execute('SELECT DISTINCT action FROM auth_audit_log').fetchall()])
conn.close()
```

**BEFORE**: `[]`  ← forensic GAP

### R2 reproducer (after fix)

Same code, with one additional line `mgr.update_user(u.user_id, {'role': 'annotator'}, actor='admin-1')` for completeness:

**AFTER**:
```
['password.changed', 'user.created', 'user.deleted', 'user.updated']
```

All 4 state-changing actions now recorded.

---

## 2. Root cause

The `UnifiedAuthManager` had a private `_audit()` method that records
`auth.success / auth.failed / auth.locked` events into the `auth_audit_log`
table (which is created by `AuthDatabase._init_db()`).  However, the
4 state-changing methods never called it:

| Method | Line | State change audited? |
|--------|------|----------------------|
| `_create_user` / `register_user` | `unified_auth.py:850-880` | NO |
| `change_password` | `unified_auth.py:1237-1269` | NO |
| `delete_user` (public) | `unified_auth.py:1215-1217` | NO |
| `update_user` (db helper) | `unified_auth.py:618-671` | NO (no public wrapper) |

The OWASP A09:2021 — Security Logging & Monitoring category requires that
"security-relevant events are logged in a way that enables forensic analysis."
With the gap, an attacker who gained DB access could call
`delete_user('admin')` and the audit trail would not show who did it
or when.

---

## 3. Fix design

### 3.1 New helper: `backend/auth/audit.py` → `AuditLog`

Created a small, focused helper that wraps the existing
`auth_audit_log` table (no schema change):

```python
class AuditLog:
    def __init__(self, db, resource: str = "user"):
        self._db = db                       # AuthDatabase instance
        self._lock = db._lock               # reuse DB write lock
        self._resource = resource

    def write(
        self,
        action: str,                        # "user.created", etc.
        actor: str,                         # user_id of the actor
        target: str,                        # user_id being acted upon
        details: Optional[Dict] = None,
        ip_address: Optional[str] = None,
        result: str = "success",
    ) -> None:
        # Writes to the SAME auth_audit_log table that _audit() uses.
        # If actor == target, the 'target' field is omitted from
        # details to avoid duplication (password.changed case).
        # Audit failure is logged but NEVER raised (must not block
        # business operations).
        ...
```

Key design choices:

* **No schema change** — uses the existing `auth_audit_log` table.
* **No new dependency** — pure stdlib (`json`, `secrets`, `sqlite3`,
  `threading`, `datetime`).
* **Resource tag** — `resource="user"` (vs. `_audit()`'s default
  `"auth"`) so forensic queries can split user-management events
  from auth events.
* **Failure-tolerant** — `try/except` around the DB write; logs
  via `logging.error()` and returns.  An audit failure must never
  raise, or a flaky DB could block business operations.
* **Helper completeness** — also provides a `list_entries(...)` query
  helper for future admin endpoints (filtered by action / actor / target).

### 3.2 Wiring into `UnifiedAuthManager`

```python
# in __init__ (after self.revocation = ...)
self.audit_log = AuditLog(self.db, resource="user")
```

### 3.3 Four audit calls

| Method | New audit call |
|--------|----------------|
| `_create_user` (covers `register_user`) | `self.audit_log.write("user.created", actor=actor or username, target=user.user_id, details={"role": user.role, "team": user.team, "email": user.email})` |
| `change_password` | `self.audit_log.write("password.changed", actor=user_id, target=user_id, details={"tokens_revoked": deleted})` |
| `delete_user` (public) | `self.audit_log.write("user.deleted", actor=actor or "system", target=user_id, details={"username": target.username, "role": target.role})` |
| `update_user` (new public wrapper) | `self.audit_log.write("user.updated", actor=actor or "system", target=user_id, details={"username": before.username, "changed_fields": [...], "diff": {"role": {"old": "viewer", "new": "annotator"}, ...}})` |

Notes:

* `register_user` is a thin delegate to `_create_user`, so auditing
  inside `_create_user` covers both the public `register_user` and
  the bootstrap `_ensure_admin_exists` paths.
* For the bootstrap path, we now pass `actor="system"` (instead of
  letting it default to the new username) so forensic queries can
  distinguish platform-bootstrap events from user-initiated ones.
* `delete_user` captures `username` and `role` into `details` BEFORE
  the row is deleted (the row is gone after `db.delete_user`, and
  the audit log is the only forensic record).
* `update_user` is a NEW public method on `UnifiedAuthManager` that
  wraps the existing `db.update_user` and adds a snapshot-based
  diff so the audit log shows *what* changed, not just *that*
  something changed.  Internal callers (`authenticate()` password
  upgrade, `authenticate()` last_login update) still call
  `db.update_user` directly — those are not user-initiated state
  changes in the R1-02 sense.

---

## 4. Test coverage — `tests/p2_p3/test_audit_log.py`

12 tests, all passing in 1.17s:

| # | Test | What it verifies |
|---|------|------------------|
| 1 | `test_r1_reproducer_state_changes_now_audited` | R1/R2 reproducer; all 4 action types present |
| 2 | `test_register_user_creates_audit_entry` | `user.created` has actor=username, role in details |
| 3 | `test_change_password_creates_audit_entry` | `password.changed` has actor=target, tokens_revoked |
| 4 | `test_update_user_creates_audit_entry_with_diff` | `user.updated` has old→new diff per field |
| 5 | `test_delete_user_creates_audit_entry_with_target_metadata` | `user.deleted` captured BEFORE row is gone (forensic value) |
| 6 | `test_audit_log_helper_direct_write` | `AuditLog.write` callable standalone |
| 7 | `test_audit_log_helper_list_filters_by_target` | `list_entries(target=...)` filter works |
| 8 | `test_audit_log_helper_actor_equals_target_omits_target_field` | when actor==target, details stays clean |
| 9 | `test_audit_log_write_does_not_raise_on_bad_payload` | failure tolerance (e.g. `db=None`) |
| 10 | `test_auth_events_still_recorded_alongside_state_changes` | existing `auth.success` / `auth.failed` still captured |
| 11 | `test_bootstrap_admin_creates_audit_entry_with_system_actor` | bootstrap path uses `actor="system"` |
| 12 | `test_timestamps_are_monotonic_within_test` | all entries have non-empty ISO-8601 timestamps |

### Run command

```powershell
& "D:\ComfyUI\.ext\python.exe" -m pytest `
  "D:\Hermes\生产平台\nanobot-factory\tests\p2_p3\test_audit_log.py" -v --tb=short
# Expected: 12 passed in ~1.2s
```

### Regression check — existing auth tests

```powershell
& "D:\ComfyUI\.ext\python.exe" -m pytest `
  "D:\Hermes\生产平台\nanobot-factory\backend\auth\tests" -v --tb=short
# Expected: 99 passed in ~14s (regression-clean)
```

---

## 5. Sample audit log output (after fix)

```sql
sqlite> SELECT action, user_id, details FROM auth_audit_log;
```

| action | user_id (actor) | details (JSON) |
|--------|-----------------|----------------|
| `user.created` | `system` | `{"role": "admin", "team": "system", "email": "admin@nanobot.local", "target": "u-c4d0235016586c2d"}` |
| `user.created` | `victim` | `{"role": "viewer", "team": "", "email": "victim@nanobot.local", "target": "u-0ddf6980d7a42240"}` |
| `password.changed` | `u-0ddf6980d7a42240` | `{"tokens_revoked": 0}` |
| `user.updated` | `admin-1` | `{"username": "victim", "changed_fields": ["role"], "diff": {"role": {"old": "viewer", "new": "annotator"}}, "target": "u-0ddf6980d7a42240"}` |
| `user.deleted` | `admin-1` | `{"username": "victim", "role": "annotator", "target": "u-0ddf6980d7a42240"}` |

Forensic answers now possible:

* "Who created user X?" → `SELECT user_id FROM auth_audit_log WHERE action='user.created' AND details LIKE '%X%'`
* "Who deleted user X?" → `SELECT user_id FROM auth_audit_log WHERE action='user.deleted' AND details LIKE '%X%'`
* "When was user X's password changed?" → `SELECT timestamp FROM auth_audit_log WHERE action='password.changed' AND user_id='X'`
* "What role changes did admin-1 do?" → `SELECT details FROM auth_audit_log WHERE action='user.updated' AND user_id='admin-1'`

---

## 6. Files changed

| File | Change | Lines (delta) |
|------|--------|---------------|
| `backend/auth/audit.py` | **NEW** — `AuditLog` class with `write()` + `list_entries()` | +191 |
| `backend/auth/unified_auth.py` | Added `from .audit import AuditLog`, `self.audit_log = AuditLog(...)` in `__init__`, audit calls in `_create_user` / `change_password` / `delete_user` / new public `update_user`, `actor="system"` for bootstrap | +90 / -8 |
| `tests/p2_p3/test_audit_log.py` | **NEW** — 12 tests covering R1-02 reproducer + invariants + helper | +341 |
| `reports/p21_p2_p3_audit_log.md` | **NEW** — this report | — |

**Total**: 3 files changed, 1 report, ~620 LoC added (1 helper + 12 tests + 1 report).

---

## 7. R1-02 → R2 re-verification → P21 P2 P3 fix → FORENSIC GAP CLOSED

```
R1 audit (2026-07-09):   audit_log = []  after state changes  ← GAP
R2 re-audit (2026-07-10): audit_log = []  after state changes  ← GAP re-confirmed
P21 P2 P3 fix (2026-07-11):
   user.created     → 1 entry (actor=system, target=admin user_id, details={role,team,email})
   user.created     → 1 entry (actor=username, target=new user_id, details={role,team,email})
   password.changed → 1 entry (actor=user_id, target=user_id, details={tokens_revoked})
   user.updated     → 1 entry (actor=admin, target=user_id, details={changed_fields, diff})
   user.deleted     → 1 entry (actor=admin, target=user_id, details={username,role})
                                          ← FORENSIC GAP CLOSED
```

12/12 tests PASS, 99/99 regression tests PASS.

---

## 8. Out-of-scope (intentionally not changed)

* **No schema change** to `auth_audit_log` table (kept R1-compatible).
* **No new dependency** added.
* **`_audit()` (legacy auth.* events) is kept unchanged** — it still
  records `auth.success` / `auth.failed` / `auth.locked`.  The new
  `AuditLog` helper complements it (different resource tag, different
  use case).
* **Internal callers of `db.update_user` (e.g. `authenticate()`)** are
  NOT audited — those are programmatic (not user-initiated) state
  writes in the R1-02 sense.  Only the new public `update_user`
  wrapper audits.
* **No changes to FastAPI routes / `auth_routes.py`** — the audit
  log is read internally (via `AuditLog.list_entries()`); exposing
  it via HTTP is a separate task.

---

**Report end.** R1-02 (P0 / OWASP A09 / CWE-778) — CLOSED.
