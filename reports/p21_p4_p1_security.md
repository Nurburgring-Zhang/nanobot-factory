# P21 Phase 4 P1 — Focused 6-test Re-Audit of R2 P0 Security Fixes

**Date**: 2026-07-11
**Author**: coder (security-expert)
**Parent plan**: `p21_p4_p1_focused_security_audit`
**Scope**: 6 R2-audit-confirmed P0 vulnerabilities, re-verified in v1.5.6 after the
P2 P3 + P2 P4 work that landed in between.

---

## VERDICT: **PASS** — All 6 R2 P0 fixes still in effect, 6/6 new tests pass,
86/86 combined security test suite still passes. **No regression detected.**

| # | R2 P0 finding | Pre-fix response | Post-fix response | Status |
|---|---------------|------------------|-------------------|--------|
| 1 | **R2-09 / R2-NEW-06** — tenant takeover via unauthenticated `POST /api/v2/users` | 200 + api_key (full takeover) | **401 missing_authorization, no api_key leak** | ✅ PASS |
| 2 | **R2-NEW-01** — SQL injection in `update_user` (Bandit B608) | f-string `set_clause`, user input could enter SQL | **Static `_COLUMN_BIND` map, all values bound as `?` parameters** | ✅ PASS |
| 3 | **R2-NEW-02** — Reflected XSS in `_build_error_body` | `<script>` payload returned verbatim | **`html.escape(quote=True)` applied, raw preserved on `code_raw`/`message_raw`** | ✅ PASS |
| 4 | **R2-NEW-03** — CSRF on state-changing POSTs | 0/22 route files had `csrf` keyword, drive-by CSRF succeeded | **`CSRFMiddleware` rejects evil.com Origin with 403** | ✅ PASS |
| 5 | **R2-NEW-04** — Path traversal via unwired `Injection.validate_path` | Path-traversal payload joined raw, file read outside data dir | **`validated_path` raises `HTTPException(400)` on `..`, absolute, `~`, empty** | ✅ PASS |
| 6 | **R1-02** — Audit log gaps for 4 state-changing user actions | `auth_audit_log` empty after register/change/update/delete | **All 4 actions recorded with actor/target/details/timestamp** | ✅ PASS |

---

## 1. What changed in P2 P3 + P2 P4 (the surface we re-audited)

The 6 R2 P0 fixes were originally patched in P2 P1 (3 fixes — R2-09,
R2-NEW-01, R2-NEW-02) and P2 P2 (2 fixes — R2-NEW-03, R2-NEW-04) and
P2 P3 + P2 P4 + P2 P5 (1 fix — R1-02 audit log gap).

The P2 P3 + P2 P4 work that landed **in between** the fixes and this
re-audit touched:

* `backend/auth/audit.py` — `AuditLog.write` contract hardened;
  `target` merged into `details["target"]` for forensic queries.
* `backend/auth/unified_auth.py` — `update_user`/`delete_user` wrappers
  (P2 P5 added these; P2 P3 had `register_user` + `change_password`).
  `register_user` audit row now stores `role`/`team`/`email`; the
  P2 P3 enhancement captures pre-state for the diff.
* 14 `backend/routes/data_*.py` files (P2 P2 path-traversal wiring).
* `backend/imdf/skills/*` (skill composition, envelope helper).
* and other unrelated modules (audit, DB, etc.).

The risk: any of those in-between changes could have silently
regressed the original R2 P0 fixes. This task is the regression
detector.

---

## 2. The 6 re-audit tests

File: `tests/p4_p1/test_security_re_audit.py` (new, 6 tests,
~0.75s runtime).

### Test 1 — `test_r2_09_post_users_no_auth_returns_401`
- **Builds**: hermetic FastAPI app with the production router +
  mocked `UserManager` (so the test doesn't touch the real DB).
- **Asserts**:
  - `POST /api/v2/users` (no Authorization header) returns **401**.
  - The 401 body does **not** leak `nbk-` (api_key prefix).
  - The body shape is `missing_authorization` / `unauthorized` /
    JSON `detail` (any of the canonical `require_role_dep` responses).
- **Repro R2-09 pre-fix**: `POST /api/v2/users` with
  `{"username":"attacker","role":"admin"}` (no auth) → 200 with
  `api_key=nbk-3e657f230f414a06` (full tenant takeover).
- **Status**: PASS.

### Test 2 — `test_r2_new_01_update_user_uses_parameterized_sql`
- **Builds**: tempdir SQLite + `AuthDatabase` + a baseline user.
- **Wraps** `db._get_conn` with a `_SpyConn` that captures every
  `execute(sql, params)` call without losing the underlying connection.
- **Calls** `db.update_user("u-r2-new-01-victim", {"role": "admin",
  "email": "newmail@x"})`.
- **Asserts** on the captured SQL:
  - `UPDATE auth_users SET` + `WHERE user_id = ?` shape present.
  - No caller-influenced substring: `'`, `--`, `/*`, `*/`,
    `; DROP`, `;SELECT`, `;UPDATE`, `;DELETE`.
  - Bound params: `admin`, `newmail@x`, `u-r2-new-01-victim`.
  - No bound param is itself a SQL fragment.
- **Repro R2-NEW-01 pre-fix**: `f"UPDATE auth_users SET {set_clause}
  WHERE user_id = ?"` where `set_clause = ", ".join(k + " = ?" for k
  in filtered)` — Bandit B608 + R2-01.
- **Status**: PASS.

### Test 3 — `test_r2_new_02_build_error_body_escapes_xss`
- **Calls** `_build_error_body("<script>alert(1)</script>",
  "<img src=x onerror=alert(2)>", None)`.
- **Asserts**:
  - `body["error"]["code"]` contains the escaped form
    (`&lt;script&gt;alert(1)&lt;/script&gt;`).
  - `body["error"]["message"]` contains the escaped form
    (`&lt;img src=x onerror=alert(2)&gt;`).
  - Raw `<script>` and `<img...>` do NOT appear in code/message.
  - Raw values preserved on `code_raw` / `message_raw` (for
    server-side logs and machine clients).
- **Repro R2-NEW-02 pre-fix**: payload returned verbatim — reflected
  XSS for any browser-side JSON renderer.
- **Status**: PASS.

### Test 4 — `test_r2_new_03_post_with_evil_origin_returns_403`
- **Builds**: hermetic FastAPI app with `CSRFMiddleware` +
  `allowed_origins=["http://localhost:5173", "http://localhost:8765"]`
  + `enabled=True` (force-on; conftest sets `CSRF_ENABLED=false`
  session-wide).
- **Three sub-attacks**:
  - `POST /api/v2/users` with `Origin: http://evil.com` →
    **403** `{"error": "CSRF: invalid or missing Origin"}`, no
    `nbk-` leak.
  - `POST` with **no** `Origin` → **403**.
  - `POST` with `Origin: http://localhost:5173` (trusted) →
    **200** (regression guard: fix must not over-reject legit).
- **Repro R2-NEW-03 pre-fix**: combined with R2-09, drive-by CSRF
  from `evil.com` minted an admin user with a long-lived api_key.
- **Status**: PASS.

### Test 5 — `test_r2_new_04_validated_path_rejects_parent_traversal`
- **Calls** `validated_path(...)` with 6 inputs:
  - `../../etc/passwd` → `HTTPException(400)` (the spec's primary
    case)
  - `/etc/passwd` → `HTTPException(400)` (absolute path)
  - `~/secrets` → `HTTPException(400)` (tilde home)
  - `C:\Windows\System32` → `HTTPException(400)` (Windows absolute)
  - `""` → `HTTPException(400)` (empty)
  - `./data/x.jpg` → returns the path (legit; regression guard)
- **Asserts** the exception's `status_code == 400` and the `detail`
  contains `"traversal"` / `"absolute"` markers.
- **Repro R2-NEW-04 pre-fix**: `?path=../../etc/passwd` → file read
  outside the data dir (Injection.validate_path was defined but
  not wired to any of the 122 routes).
- **Status**: PASS.

### Test 6 — `test_r1_02_all_four_audit_actions_logged`
- **Builds**: tempdir SQLite + `UnifiedAuthManager`.
- **Exercises the 4 actions in sequence**:
  1. `register_user("p4_p1_alice", "Password123!", "viewer")` →
     must write `user.created`.
  2. `change_password(user_id, "Password123!", "NewPass5678!")` →
     must write `password.changed`.
  3. `update_user(user_id, {"email": "alice.new@x.com"},
     actor="admin-p4p1")` → must write `user.updated`.
  4. `delete_user(user_id, actor="admin-p4p1")` → must write
     `user.deleted`.
- **Asserts**:
  - All 4 actions are present in the audit log.
  - Each row has the expected minimal schema (resource=user,
    result=success, ISO timestamp).
  - The P2 P3 / P2 P5 enhancements are still in place
    (changed_fields, diff, pre-delete username, tokens_revoked).
- **Note on filtering**: `UnifiedAuthManager.__init__` creates a
  bootstrap admin via `register_user` (in IMDF_TEST_MODE), so the
  audit log already has a `user.created` row for the bootstrap
  admin. The test filters by `json_extract(details, '$.target') =
  user_id` (or `user_id` for `password.changed` where actor==target)
  so the assertions unambiguously check the right row.
- **Repro R1-02 pre-fix**: `auth_audit_log` returned `[]` after
  register/change/update/delete. (R2 pentest §2 re-confirmed R1-02.)
- **Status**: PASS.

---

## 3. Test run

```
$ pytest tests/p4_p1/test_security_re_audit.py -v
tests/p4_p1/test_security_re_audit.py::test_r2_09_post_users_no_auth_returns_401 PASSED
tests/p4_p1/test_security_re_audit.py::test_r2_new_01_update_user_uses_parameterized_sql PASSED
tests/p4_p1/test_security_re_audit.py::test_r2_new_02_build_error_body_escapes_xss PASSED
tests/p4_p1/test_security_re_audit.py::test_r2_new_03_post_with_evil_origin_returns_403 PASSED
tests/p4_p1/test_security_re_audit.py::test_r2_new_04_validated_path_rejects_parent_traversal PASSED
tests/p4_p1/test_security_re_audit.py::test_r1_02_all_four_audit_actions_logged PASSED
======================== 6 passed, 1 warning in 0.75s ========================
```

The warning is `PytestConfigWarning: Unknown config option: timeout` —
the project's `pytest.ini` declares `timeout = 30` without installing
`pytest-timeout`. Pre-existing, not introduced by this fix.

### Combined regression check (all P2 security tests + this re-audit)

```
$ pytest tests/p2_p1/test_security_p0_fixes.py \
         tests/p2_p2/test_security_csrf.py \
         tests/p2_p2/test_path_validation.py \
         tests/p2_p4/test_audit_log_2sites.py \
         tests/p2_p5/test_audit_log_2sites_rest.py \
         tests/p4_p1/test_security_re_audit.py
======================== 86 passed, 1 warning in 4.12s ========================
```

| Suite | Test count | Status |
|-------|-----------|--------|
| `tests/p2_p1/test_security_p0_fixes.py` | 5 | ✅ PASS |
| `tests/p2_p2/test_security_csrf.py` | 8 | ✅ PASS |
| `tests/p2_p2/test_path_validation.py` | 49 | ✅ PASS |
| `tests/p2_p4/test_audit_log_2sites.py` | 8 | ✅ PASS |
| `tests/p2_p5/test_audit_log_2sites_rest.py` | 10 | ✅ PASS |
| `tests/p4_p1/test_security_re_audit.py` (NEW) | 6 | ✅ PASS |
| **Combined** | **86** | **0 fail** |

No regression. All prior P2 P1 + P2 P2 + P2 P3 + P2 P4 + P2 P5 security
tests still pass alongside the 6 new re-audit tests.

---

## 4. P2 P3 / P2 P4 changes that could have regressed — checked

| P2 P3 / P2 P4 surface | Risk to R2 P0 fix | Re-audit verdict |
|-----------------------|-------------------|------------------|
| `audit.py:AuditLog.write` — `target` merged into `details` | Could have broken the `target=user_id` contract on user.created / user.updated / user.deleted. | **No regression** — Test 6 verifies `target` is in details for all 3 actions. |
| `unified_auth.py:update_user` / `delete_user` (P2 P5 wrappers) | Could have re-introduced SQL-injection or skipped audit writes. | **No regression** — Test 2 verifies parameterized SQL; Test 6 verifies the 4 audit writes. |
| `unified_auth.py:register_user` — now writes `details={role, team, email}` (no `username`) | Could have lost forensic username. | **Accepted contract** — the test asserts what's actually written (role/team/email), not the absent `username` field. The P2 P5 enhancement captures `username` in `user.deleted` *before* the row is removed. |
| 14 data_* route files — `validated_path` wiring | Could have regressed one of the 32 wired routes. | **Out of scope** for this re-audit (covered by the 49-test `p2_p2/test_path_validation.py` sweep, still PASS). |
| `server.py:CSRFMiddleware.add_middleware` | Could have been removed. | **No regression** — `tests/p2_p2/test_security_csrf.py::test_server_py_has_csrf_middleware_wired` still passes. |
| `production.py:Depends(_admin_required)` on `create_user` | Could have been removed. | **No regression** — Test 1 verifies the 401 still works. |
| `error_handler.py:_build_error_body` — `html.escape(quote=True)` | Could have been reverted. | **No regression** — Test 3 verifies escape. |

**No new P0 was introduced by P2 P3 / P2 P4 changes.** All 6 R2 P0
fixes are intact.

---

## 5. Audit log test-design note (for the verifier)

The original test draft had a bug: it used `WHERE action = 'user.created'`
without filtering by target. The first row of that query is the
**bootstrap admin** created by `UnifiedAuthManager.__init__` in
`IMDF_TEST_MODE` (via `register_user` at unified_auth.py:872-876),
not the test user. The fix is to filter by
`json_extract(details, '$.target') = user_id` for the 3 actions where
actor != target (user.created, user.updated, user.deleted) and by
`user_id = ?` for `password.changed` (where actor == target, so
`AuditLog.write` deliberately omits the redundant target field per
`audit.py:93`).

The fix is documented inline in the test as a note for future
maintainers; it's not a functional gap, just a hermeticity concern.

---

## 6. Hard-rule compliance

- **30-minute budget**: ~22 min total (read 5 reports + 4 files 4,
  write tests 8, debug 2 SQLite-filter assertions 5, run + combined
  regression 5).
- **`D:\ComfyUI\.ext\python.exe`**: yes, all commands used this
  interpreter.
- **Project root `D:\Hermes\生产平台\nanobot-factory`**: yes, all
  paths are under this root.
- **No new dependencies**: yes; only stdlib `json` / `sqlite3` /
  `tempfile` were used, plus the existing `fastapi.testclient` and
  `pytest` fixtures.
- **No production code modified**: yes; the re-audit is read-only
  against v1.5.6.
- **Tests runnable via `pytest tests/p4_p1/test_security_re_audit.py
  -v`**: yes; confirmed PASS in 0.75s.

---

## 7. Files

| Action | Path | Notes |
|--------|------|-------|
| **Create** | `tests/p4_p1/test_security_re_audit.py` | 6 re-audit tests, 0.75s. |
| **Create** | `reports/p21_p4_p1_security.md` | This report. |
| **Create** | `C:\Users\Administrator\.mavis\plans\plan_b2d7642d\outputs\p4_p1f_security_audit\deliverable.md` | Engine deliverable summary. |

---

## 8. Verifier Quick-Start

```powershell
# 1. Run the new re-audit tests
D:\ComfyUI\.ext\python.exe -m pytest "D:\Hermes\生产平台\nanobot-factory\tests\p4_p1\test_security_re_audit.py" -v
# Expect: 6 passed in <2s

# 2. Run the combined security test suite
D:\ComfyUI\.ext\python.exe -m pytest `
  "D:\Hermes\生产平台\nanobot-factory\tests\p2_p1\test_security_p0_fixes.py" `
  "D:\Hermes\生产平台\nanobot-factory\tests\p2_p2\test_security_csrf.py" `
  "D:\Hermes\生产平台\nanobot-factory\tests\p2_p2\test_path_validation.py" `
  "D:\Hermes\生产平台\nanobot-factory\tests\p2_p4\test_audit_log_2sites.py" `
  "D:\Hermes\生产平台\nanobot-factory\tests\p2_p5\test_audit_log_2sites_rest.py" `
  "D:\Hermes\生产平台\nanobot-factory\tests\p4_p1\test_security_re_audit.py"
# Expect: 86 passed in <5s
```

---

**Report end.** All 6 R2 P0 fixes confirmed intact in v1.5.6; no
regression introduced by P2 P3 / P2 P4 / P2 P5 changes.
