# P21 Phase 2 P4 — Audit log 2-site focused verification (R1-02 split)

**Author**: coder (P21 P2 P4 security-expert)
**Date**: 2026-07-11
**Sprint**: P21 / Phase 2 / P4 / P1 fix
**R1 reference**: `reports/p21_r1_audit_security.md` §2 A09 + §3 gap #02
**R2 reference**: `reports/p21_r2_audit_security.md` (re-verified)
**Audit severity**: P0 / OWASP A09:2021 — Security Logging & Monitoring
**CWE**: CWE-778 Insufficient Logging
**Scope**: `register_user` + `change_password` only (2 sites)

---

## 1. Scope split (P2 P4 vs P2 P5)

The R1-02 finding lists 3 functions that skip audit log:
`register_user`, `change_password`, `delete_user`. P21 Phase 2 split this
into 2 sub-tasks for smaller blast radius:

| Sub-task | Functions in scope | Test file | Status |
|----------|-------------------|-----------|--------|
| **P2 P4** (this task) | `register_user`, `change_password` | `tests/p2_p4/test_audit_log_2sites.py` | **DONE** (8/8 PASS) |
| **P2 P5** (separate task) | `delete_user`, `update_user` | `tests/p2_p5/test_audit_log_2sites_p2p5.py` (TBD) | TODO |

Both tasks are independent; either can be merged first without affecting
the other (different functions, different test files, no shared state).

---

## 2. Audit-claim-drift (verification finding)

The P2 P4 task prompt assumed a fresh state ("If `self.audit_log` doesn't
exist as a class attribute, find an existing audit log helper. If nothing
exists, create a minimal `AuditLog` class"). The actual current state of
the code (verified 2026-07-11):

| Spec expectation | Actual state (verified) | Drift |
|------------------|--------------------------|-------|
| `self.audit_log` doesn't exist | Exists at `unified_auth.py:784` | prior P2 P3 wired it |
| `AuditLog` class doesn't exist | Exists at `backend/auth/audit.py` (192 lines) | prior P2 P3 created it |
| `register_user` missing audit call | Present at `_create_user:899-908` (covers register_user delegate) | prior P2 P3 added it |
| `change_password` missing audit call | Present at `change_password:1379-1386` | prior P2 P3 added it |

**No source code change was required.** P2 P4 is a **focused-verification**
+ **2-site test deliverable** rather than a code-fix task.

---

## 3. Source verification (read-only confirmation)

The 2 in-scope audit calls (verified by reading `unified_auth.py:780-1386`):

### 3.1 `register_user` → `user.created`

```python
# backend/auth/unified_auth.py:899-908 (inside _create_user,
# which register_user delegates to)
self.audit_log.write(
    action="user.created",
    actor=actor or username,        # "system" for bootstrap, else username
    target=user.user_id,
    details={
        "role": user.role,
        "team": user.team,
        "email": user.email,
    },
)
```

Wiring: `register_user(username, password, role, ...)` → `self._create_user(...)`
(line 930) → `self.db.insert_user(user)` → `self.audit_log.write(...)` at line 899.

### 3.2 `change_password` → `password.changed`

```python
# backend/auth/unified_auth.py:1379-1386 (inside change_password)
self.audit_log.write(
    action="password.changed",
    actor=user_id,                  # user is the actor (self-service)
    target=user_id,                 # same user is the target
    details={
        "tokens_revoked": deleted,  # P10R4-1 auto-revoke count
    },
)
```

Both calls match the spec from `reports/p21_r2_audit_security.md` (lines
that originally said "After `mgr.register_user → change_password →
delete_user`, querying `auth_audit_log` returns `[]`").

---

## 4. Test coverage — `tests/p2_p4/test_audit_log_2sites.py`

8 tests, all passing in 1.16s. Focused ONLY on the 2 in-scope functions
(per hard rule "Leave `delete_user` and `update_user` for a separate task"):

| # | Test | Function under test | What it verifies |
|---|------|---------------------|------------------|
| 1 | `test_r1_reproducer_2sites_now_audited` | register + change_password | R1-02 partial reproducer: both `user.created` AND `password.changed` present in `auth_audit_log` (the 2 in-scope actions) |
| 2 | `test_register_user_writes_user_created_with_full_schema` | register_user | `user.created` row has `actor`, `target`, `resource="user"`, `result="success"`, ISO timestamp, and full details (role, team, email, target) |
| 3 | `test_register_user_duplicate_does_not_write_audit` | register_user (failure path) | If `register_user` returns `None` (duplicate username), NO audit row is written — failure must not pollute the audit log |
| 4 | `test_change_password_writes_password_changed_with_actor_eq_target` | change_password | `password.changed` row has `actor == target == user_id`, `resource="user"`, ISO timestamp, `tokens_revoked` populated |
| 5 | `test_change_password_wrong_old_password_does_not_write_audit` | change_password (failure path) | If `change_password` returns `False` (wrong old password), NO audit row is written — auth failure must not log "password.changed" |
| 6 | `test_change_password_multiple_changes_each_write_audit` | change_password (sequence) | 3 sequential successful changes → exactly 3 `password.changed` rows (no dedup, no dropping) |
| 7 | `test_list_entries_returns_register_and_password_actions` | forensic query | `AuditLog.list_entries(action=...)` returns both in-scope action types with all forensic fields populated (actor / target / resource / result / timestamp / details) |
| 8 | `test_filter_by_action_returns_only_password_changed` | forensic filter | `list_entries(action="password.changed")` returns ONLY `password.changed` rows |

### Run command

```powershell
& "D:\ComfyUI\.ext\python.exe" -m pytest `
  "D:\Hermes\生产平台\nanobot-factory\tests\p2_p4\test_audit_log_2sites.py" `
  -v --tb=short
```

**Expected**: 8 passed in ~1.2s.

### Regression check — combined P2 P3 + P2 P4

```powershell
& "D:\ComfyUI\.ext\python.exe" -m pytest `
  "D:\Hermes\生产平台\nanobot-factory\tests\p2_p3\test_audit_log.py" `
  "D:\Hermes\生产平台\nanobot-factory\tests\p2_p4\test_audit_log_2sites.py" `
  -v --tb=short
```

**Expected**: 20 passed in ~5s (12 P2 P3 + 8 P2 P4).

### Edge-case coverage (intentionally added beyond P2 P3)

| Test | Why it matters |
|------|----------------|
| `test_register_user_duplicate_does_not_write_audit` (P2 P4 #3) | P2 P3 didn't cover this — duplicate register returns `None` early (line 873-874) and must not reach the audit write. Guards against a future bug where a partial-write code path leaks a phantom audit row. |
| `test_change_password_wrong_old_password_does_not_write_audit` (P2 P4 #5) | P2 P3 didn't cover this — wrong old password returns `False` early (line 1362-1363) and must not reach the audit write. Guards against a future bug where a failed password change falsely claims success in the audit log. |
| `test_change_password_multiple_changes_each_write_audit` (P2 P4 #6) | P2 P3 didn't cover this — 3 changes must produce 3 entries (not 1 or 0). Guards against a future bug where a dedup cache incorrectly collapses multiple changes. |
| `test_filter_by_action_returns_only_password_changed` (P2 P4 #8) | P2 P3 had `list_entries(target=...)` test but not `list_entries(action=...)`. The action filter is the primary forensic query — guards against schema drift in the `action` column. |

---

## 5. Sample audit log output (P2 P4 2-site slice)

After running the 2 in-scope operations:

```sql
sqlite> SELECT user_id, action, details FROM auth_audit_log
        WHERE action IN ('user.created', 'password.changed');
```

| user_id (actor) | action | details (JSON) |
|-----------------|--------|----------------|
| `system` | `user.created` | `{"role": "admin", "team": "system", "email": "admin@nanobot.local", "target": "u-..."}` |
| `r1_victim` | `user.created` | `{"role": "viewer", "team": "", "email": "r1_victim@nanobot.local", "target": "u-..."}` |
| `u-0ddf...` | `password.changed` | `{"tokens_revoked": 0}` |

Forensic answers now possible for the 2 in-scope actions:
- "Who created user X?" → `SELECT user_id FROM auth_audit_log WHERE action='user.created' AND details LIKE '%X%'`
- "When was user X's password changed?" → `SELECT timestamp FROM auth_audit_log WHERE action='password.changed' AND user_id='X'`

---

## 6. Hard rules compliance

| Rule | Met? | Evidence |
|------|------|----------|
| 25-minute timebox | ✓ | ~12 min actual (file inventory 3 + reads 4 + write 3 + verify 2) |
| `D:\ComfyUI\.ext\python.exe` | ✓ | Used in all 3 test invocations |
| `D:\Hermes\生产平台\nanobot-factory` as project root | ✓ | All paths absolute |
| No new dependencies | ✓ | No `pip install` or `requirements.txt` changes |
| Only modify 2 functions (register + change_password) | ✓ | NO source modification (calls already in place from P2 P3) |
| Leave `delete_user` and `update_user` for P2 P5 | ✓ | P2 P4 test file does NOT call `delete_user` or `update_user` |

---

## 7. Files changed

| File | Change | Lines (delta) |
|------|--------|---------------|
| `tests/p2_p4/test_audit_log_2sites.py` | **NEW** — 8 focused tests for register_user + change_password | +297 |
| `reports/p21_p2_p4_audit_log.md` | **NEW** — this report | — |
| `backend/auth/unified_auth.py` | **NOT MODIFIED** | 0 |
| `backend/auth/audit.py` | **NOT MODIFIED** | 0 |

**Total**: 1 new test file, 1 new report, 0 source changes. The P2 P4
deliverable is verification (via the new test suite) of code that P2 P3
already wrote.

---

## 8. R1-02 → R2 → P2 P3 → P2 P4 status

```
R1 audit (2026-07-09):  audit_log = []  after state changes         ← GAP
R2 re-audit (2026-07-10): audit_log = []  after state changes       ← GAP re-confirmed
P21 P2 P3 fix (2026-07-11):
   user.created     → 1 entry (actor=system/username, target=user_id, details={role,team,email})
   password.changed → 1 entry (actor=user_id, target=user_id, details={tokens_revoked})
   user.updated     → 1 entry (actor=admin, target=user_id, details={changed_fields, diff})
   user.deleted     → 1 entry (actor=admin, target=user_id, details={username,role})
                                       ← FORENSIC GAP CLOSED
P21 P2 P4 (this task, 2026-07-11):
   Focused 2-site regression test (register_user + change_password only)
   8/8 tests pass in 1.16s
   20/20 tests pass in 5.11s when combined with P2 P3
                                       ← P2 P4 SPLIT VERIFIED
```

P2 P5 will own the symmetric 2-site test for `delete_user` and `update_user`.

---

## 9. Out-of-scope (intentionally not changed)

* **`delete_user`** (line 1245-1273) — out of P2 P4 scope; will be verified by P2 P5.
* **`update_user`** (line 1275-1329) — out of P2 P4 scope; will be verified by P2 P5.
* **`backend/auth/audit.py`** — already complete from P2 P3; no P2 P4 change needed.
* **No FastAPI route changes** — the audit log is read internally via `AuditLog.list_entries()`; HTTP exposure is a separate task.
* **No schema change** — `auth_audit_log` table is unchanged from P2 P3.

---

**Report end.** P2 P4 R1-02 split (register_user + change_password) — VERIFIED, 8/8 tests pass, no source change required.
