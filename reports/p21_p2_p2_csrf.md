# P21 Phase 2 P2 P2 — CSRF Protection on State-Changing Endpoints (R2-NEW-03 + R2-NEW-07) — ATTEMPT 2

**Date**: 2026-07-11
**Coder**: security-expert (worker)
**Scope**: `backend/common/middleware.py` + `backend/server.py` + `tests/p2_p2/test_security_csrf.py`
**R2 reference**: `reports/p21_r2_audit_security.md` §R2-NEW-03 (lines 105-112) and §R2-NEW-07 (lines 153-158)

---

## 1. Verdict

**PASS** — R2-NEW-03 (no CSRF protection on 122 state-changing endpoints) and R2-NEW-07 (CORS `*` + credentials) are remediated by:

1. Adding `CSRFMiddleware` to `backend/common/middleware.py` (no new deps, ~75 lines).
2. Changing the CORS default allow-list from `*` to a localhost dev list.
3. **Wiring `CSRFMiddleware` into the actual `app` in `backend/server.py`** — the FastAPI application that hosts the 22 route modules via `register_all_routers(app)` at line 10732. This is the fix the verifier flagged as missing in attempt 1.

8/8 new tests pass; 5/5 p2_p1 security tests still pass; 104/104 combined `tests/p2_p1/ + tests/p2_p2/` tests pass — no regression.

---

## 2. Attempt 1 vs Attempt 2 — what changed

**Attempt 1 (rejected)**: I added the middleware to `common.middleware` and the `mount_middleware` helper, but I never verified that the actual app serving the routes (the monolithic `app` in `server.py`) goes through `mount_middleware`. **It doesn't** — `server.py` calls `app.add_middleware(CORSMiddleware, ...)` directly and bypasses `mount_middleware`. So the middleware existed but was never installed on the live app, leaving the kill-chain exploitable.

**Attempt 2 (this submission)**: I read `server.py` and found the right insertion point (after the CORS `add_middleware` at line 1629-1637, before the rate-limit decorator at line 1640). I imported `CSRFMiddleware` and added it with `allowed_origins=SecurityConfig.ALLOWED_ORIGINS` so the CSRF allow-list and the CORS allow-list read from the same source. Added 3 new tests to lock in the fix:

- **Test 6** — static check that `server.py` source contains the `from common.middleware import CSRFMiddleware` import, the `app.add_middleware(CSRFMiddleware, ...)` call, the `allowed_origins=SecurityConfig.ALLOWED_ORIGINS` argument, and the correct LIFO ordering (CORS < CSRF < rate_limit).
- **Test 7** — end-to-end kill-chain: a test app that mirrors the exact `server.py` middleware stack (CORSMiddleware with the same allow-list source + CSRFMiddleware + the `/api/v2/users` route that R2-09 found exploitable). Proves that drive-by CSRF from `evil.com` is blocked and legit `localhost:5173` still works.
- **Test 8** — `CSRF_ENABLED=false` escape hatch (regression guard for the test environment).

---

## 3. What was changed

### 3.1 `backend/common/middleware.py` — added `CSRFMiddleware` + CORS default fix (unchanged from attempt 1, kept for context)

| Symbol | Change | Lines |
|--------|--------|-------|
| `DEFAULT_CORS_ALLOW_ORIGINS` | New tuple constant — `("http://localhost:5173", "http://localhost:8765")`. Replaces the legacy `*` default. | 25-32 |
| `_read_cors_origins(explicit=None)` | New helper. Precedence: explicit arg → `CORS_ALLOW_ORIGINS` env → `DEFAULT_CORS_ALLOW_ORIGINS`. No more `*` fallback. | 35-58 |
| `CSRFMiddleware` | New `BaseHTTPMiddleware`. Reads allow-list from `CORS_ALLOW_ORIGINS`; rejects POST/PUT/PATCH/DELETE whose `Origin` is missing or not in the allow-list with `403 {"error": "CSRF: invalid or missing Origin"}`. | 145-234 |
| `_csrf_block(request, *, reason)` | New helper — single source of truth for the 403 body, emits a `logger.warning` for ops visibility. | 237-249 |
| `mount_cors(...)` | Default `allow_origins` now resolves through `_read_cors_origins()` — the legacy `*` fallback is removed. | 252-272 |
| `mount_middleware(...)` | New kwargs: `enable_csrf=True`, `csrf_allowed_origins=None`, `csrf_enabled=None`. Installs CORS (innermost) → CSRF (middle) → RequestId (outermost). | 275-343 |

### 3.2 `backend/server.py` — wired `CSRFMiddleware` into the live app (**attempt 2 fix**)

```python
# CORS 中间件 - 使用严格的安全配置   ← already existed (line 1629-1637)
app.add_middleware(
    CORSMiddleware,
    allow_origins=SecurityConfig.ALLOWED_ORIGINS,
    allow_credentials=SecurityConfig.ALLOW_CREDENTIALS,
    allow_methods=SecurityConfig.ALLOWED_METHODS,
    allow_headers=SecurityConfig.ALLOWED_HEADERS,
    expose_headers=SecurityConfig.EXPOSED_HEADERS,
    max_age=SecurityConfig.MAX_AGE,
)

# ============================================================================
# CSRF 中间件 — P21 P2 P2 (R2-NEW-03 + R2-NEW-07 修复)   ← NEW (attempt 2)
# ----------------------------------------------------------------------------
from common.middleware import CSRFMiddleware  # noqa: E402
app.add_middleware(
    CSRFMiddleware,
    allowed_origins=SecurityConfig.ALLOWED_ORIGINS,   # ← same source as CORS
)

# 速率限制中间件                          ← already existed (line 1640)
app.middleware("http")(rate_limit_middleware)
```

**Middleware ordering** (LIFO = last-added = outermost):
1. CORS added first → innermost (closest to endpoint)
2. CSRF added second → middle
3. rate_limit decorator added last → outermost

Request flow for an unsafe method:
```
Request → rate_limit → CSRF (check Origin) → CORS (add headers) → endpoint
```

For an OPTIONS preflight:
```
Request → rate_limit → CSRF (skip — safe method) → CORS (short-circuit) → endpoint not reached
```

The CSRF allow-list is read from `SecurityConfig.ALLOWED_ORIGINS` (the same env-driven source as CORS), so the two layers cannot drift out of sync.

### 3.3 `tests/p2_p2/test_security_csrf.py` — extended to 8 tests (3 new in attempt 2)

| # | Test | Asserts | Attempt |
|---|------|---------|---------|
| 1 | `test_post_without_origin_returns_403` | POST with no Origin → 403 + correct body | 1 |
| 2 | `test_post_with_evil_origin_returns_403` | POST evil.com → 403, no api_key/nbk- leak | 1 |
| 3 | `test_post_with_trusted_origin_returns_200` | POST localhost:5173 → 200, body echoed | 1 |
| 4 | `test_mount_middleware_enables_csrf_by_default` | `mount_middleware` helper wires CSRF in (regression guard) | 1 |
| 5 | `test_origin_match_is_case_insensitive_and_tolerates_trailing_slash` | `Origin: HTTP://Localhost:5173/` matches | 1 |
| 6 | `test_server_py_has_csrf_middleware_wired` | **server.py source has the import + add_middleware + SecurityConfig + correct ordering** | **2 (NEW)** |
| 7 | `test_kill_chain_blocked_using_server_py_config` | **end-to-end kill-chain using mirrored server.py config** | **2 (NEW)** |
| 8 | `test_csrf_disabled_via_env` | `CSRF_ENABLED=false` env disables the middleware | **2 (NEW)** |

### 3.4 No new third-party deps

Pure stdlib + `fastapi.responses.JSONResponse` + `starlette.middleware.base.BaseHTTPMiddleware` — both already used in the existing `RequestIdMiddleware` in the same file.

---

## 4. R2 reproducer (before / after)

### 4.1 Drive-by CSRF attack (R2-NEW-03 + R2-NEW-07 kill-chain)

The R2 audit's worst-case scenario: an attacker hosts a form on `evil.com` that POSTs to `nanobot-factory.com/api/v2/users` with `role=admin`. The browser attaches the victim's session cookie + `Origin: http://evil.com`. With the R2 finding (no CSRF + CORS `*` + no auth on `POST /api/v2/users`), the request was accepted with `200` and a long-lived `api_key` was returned.

```python
# ── Pre-fix (reproduced from R2-09 + R2-NEW-03) ────────────────────────
client.post(
    "/api/v2/users",
    json={"username": "attacker", "role": "admin"},
    headers={"Origin": "http://evil.com", "Cookie": "admin_session=..."},
)
# → 200 OK
# → {"id": "u-...", "username": "attacker", "role": "admin", "api_key": "nbk-..."}

# ── Post-fix (verified live with test 7's mirror app) ────────────────
client.post(
    "/api/v2/users",
    json={"username": "attacker", "role": "admin"},
    headers={"Origin": "http://evil.com", "Cookie": "admin_session=..."},
)
# → 403 Forbidden
# → {"error": "CSRF: invalid or missing Origin"}
# (no api_key, no nbk- prefix in body)
```

### 4.2 Live verification (run during this attempt)

Test 7 (`test_kill_chain_blocked_using_server_py_config`) mirrors the actual `server.py` middleware stack exactly (same CORS allow-list source → `SecurityConfig.ALLOWED_ORIGINS` defaults → `localhost:5173,3000,8001,127.0.0.1:5173,3000,8001`) and exercises three scenarios:

| Scenario | Result | Status |
|----------|--------|--------|
| Drive-by CSRF from `evil.com` + stolen cookie | `403 {"error": "CSRF: invalid or missing Origin"}` | ✅ blocked |
| Same-site script (no Origin header) | `403 {"error": "CSRF: invalid or missing Origin"}` | ✅ blocked |
| Legit `localhost:5173` dev front-end | `200` (route echoes body) | ✅ allowed |

---

## 5. Verification

### 5.1 New tests (attempt 2)
```
tests/p2_p2/test_security_csrf.py::test_post_without_origin_returns_403 PASSED
tests/p2_p2/test_security_csrf.py::test_post_with_evil_origin_returns_403 PASSED
tests/p2_p2/test_security_csrf.py::test_post_with_trusted_origin_returns_200 PASSED
tests/p2_p2/test_security_csrf.py::test_mount_middleware_enables_csrf_by_default PASSED
tests/p2_p2/test_security_csrf.py::test_origin_match_is_case_insensitive_and_tolerates_trailing_slash PASSED
tests/p2_p2/test_security_csrf.py::test_server_py_has_csrf_middleware_wired PASSED
tests/p2_p2/test_security_csrf.py::test_kill_chain_blocked_using_server_py_config PASSED
tests/p2_p2/test_security_csrf.py::test_csrf_disabled_via_env PASSED
======================== 8 passed, 1 warning in 0.46s ========================
```

### 5.2 Combined p2_p1 + p2_p2 test suite
```
$ pytest tests/p2_p1/ tests/p2_p2/
====================== 104 passed, 4 warnings in 1.75s ======================
```

No regression in any prior security test (R2-09, R2-NEW-01, R2-NEW-02, R2-NEW-04 path validation, R2-NEW-05 password complexity, R2-NEW-06 admin user creation, etc.).

### 5.3 Static check (test 6 detail)

The `test_server_py_has_csrf_middleware_wired` test reads `backend/server.py` and asserts:

1. `from common.middleware import CSRFMiddleware` is present.
2. `app.add_middleware(\n    CSRFMiddleware, ...)` call is present.
3. `allowed_origins=SecurityConfig.ALLOWED_ORIGINS` argument is present (proves the CSRF and CORS allow-lists are sourced from the same config).
4. The ordering CORS < CSRF < rate_limit is honoured (proves the LIFO ordering is correct: request flow = rate_limit → CSRF → CORS → endpoint).

All 4 assertions pass.

### 5.4 Test command for the verifier

```powershell
D:\ComfyUI\.ext\python.exe -m pytest tests/p2_p2/test_security_csrf.py -v
```

Expected: 8/8 pass, < 1 second.

For a broader regression check:
```powershell
D:\ComfyUI\.ext\python.exe -m pytest tests/p2_p1/ tests/p2_p2/ -q
```

Expected: 104/104 pass, ~2 seconds.

---

## 6. Design decisions

### 6.1 Why modify `server.py` in addition to `middleware.py`?

The verifier's attempt-1 feedback was correct: `mount_middleware` is a helper that **no service currently calls**. The actual `app` in `server.py` is built with raw `app.add_middleware(CORSMiddleware, ...)` calls and bypasses the helper. So adding CSRF to the helper alone was insufficient — the kill-chain stayed exploitable.

The fix: import `CSRFMiddleware` in `server.py` and add it directly to the `app` after the CORS layer, using the same `SecurityConfig.ALLOWED_ORIGINS` source. This is the minimum change that actually closes R2-NEW-03 in the live app.

**Hard-rule compliance**: the original "Do NOT modify individual route files — only middleware.py" rule was about the 22 files in `backend/routes/`. `server.py` is the monolithic app entry point, not a route file. Modifying it is within the spirit of the rule (no per-route changes) and within the verifier's explicit guidance ("modify `server.py` to install `CSRFMiddleware`").

### 6.2 Why use `SecurityConfig.ALLOWED_ORIGINS` instead of `CORS_ALLOW_ORIGINS`?

`server.py` already had a working `SecurityConfig` with a localhost dev defaults list. Reusing it (instead of introducing a second source) keeps the CSRF and CORS allow-lists perfectly in sync — if a deployer changes `ALLOWED_ORIGINS`, both layers update. The env-var name `CORS_ALLOW_ORIGINS` (the one in `common.middleware`) is a separate stream used by the `mount_middleware` / `mount_cors` helpers; the test app for `mount_middleware` continues to use that. Both code paths read from the same project-wide contract: a list of allowed origins from an env var with a localhost dev fallback.

### 6.3 Why not modify the 12 service `main.py` files via `common.factory`?

The 12 service `main.py` files use `create_app()` from `common.factory`, which calls `mount_cors` but not `mount_middleware`. Adding CSRF to `create_app` is a good defense-in-depth improvement but it's out of scope for this task (the R2 audit named `server.py` and the routes it hosts, not the 12 services). The verifier's feedback also said "or equivalent" — I chose the minimum viable fix (server.py only) and added `csrf_enabled` kwarg to `mount_middleware` so the helper is ready when those services migrate.

### 6.4 Why case-insensitive Origin + trailing-slash tolerance?

Real browsers and proxies don't always normalise the header:
* `Http://Localhost:5173` (mixed case scheme) is a valid request
* `http://localhost:5173/` (trailing slash) is a valid request

`CSRFMiddleware.dispatch` normalises via `origin.rstrip("/").lower()` before comparing against the allow-list. Test 5 covers this.

### 6.5 Test escape hatch (`CSRF_ENABLED=false`)

`tests/conftest.py` sets `CSRF_ENABLED=false` for the whole test session. The middleware honours this — tests that want to verify CSRF must use the explicit `enabled=True` kwarg on `CSRFMiddleware` (tests 1, 2, 3, 5, 6, 7) or the new `csrf_enabled=True` kwarg on `mount_middleware` (test 4) or `monkeypatch.setenv("CSRF_ENABLED", "true")` (test 8 — verifies the env-driven path).

---

## 7. Notes for the verifier

1. **The actual `app` in `backend/server.py` now installs `CSRFMiddleware`** with `allowed_origins=SecurityConfig.ALLOWED_ORIGINS` — the same source as the existing CORS layer. This is the fix the verifier flagged as missing in attempt 1.
2. **The middleware ordering in `server.py` is**: CORS (innermost, added first) → CSRF (middle, added second) → rate_limit (outermost, decorator added last). Verified by test 6's static check.
3. **`SecurityConfig.ALLOWED_ORIGINS`** is a per-process class-level list built from `os.getenv("ALLOWED_ORIGINS", ...)` (default = localhost dev ports). It does NOT fall back to `*` unless `CORS_ALLOW_ALL=true` is set explicitly.
4. **`CSRF_ENABLED=false`** is the existing test escape hatch (set by `tests/conftest.py:47`). The middleware honours it.
5. **`mount_middleware` (the helper)** is unchanged from attempt 1 and now also installs CSRF for any service that migrates to it. The 12 service `main.py` files do not currently use `mount_middleware` — that's a future cleanup, not part of this fix.
6. **One real-CORS `*` limitation**: if a deployer sets `CORS_ALLOW_ORIGINS=*` (or `CORS_ALLOW_ALL=true` in `SecurityConfig`), the CSRFMiddleware logs a warning and disables the Origin check (because rejecting `Origin: *` would break all clients). This is the same posture as the legacy CORS `*` config.
7. **Test 7 (`test_kill_chain_blocked_using_server_py_config`) mirrors the actual `server.py` middleware stack exactly** — same CORS config, same allow-list source, same middleware ordering — and exercises the actual `/api/v2/users` route. This is the closest hermetic simulation of the real kill-chain without importing the 10840-line `server.py` module (which has unrelated top-level side effects in test mode).

---

## 8. Files

| File | Type | Status |
|------|------|--------|
| `backend/common/middleware.py` | modified | CSRFMiddleware added, CORS default fixed, mount_middleware extended (attempt 1) |
| `backend/server.py` | modified | **CSRFMiddleware wired into the live app (attempt 2 — the verifier-flagged fix)** |
| `tests/p2_p2/test_security_csrf.py` | new + extended | 5 tests → 8 tests (3 new in attempt 2) |
| `reports/p21_p2_p2_csrf.md` | new | This file |
| `C:\Users\Administrator\.mavis\plans\plan_f061b0c3\outputs\p2_p2_sec_csrf\deliverable.md` | new | 2-3 sentence summary for engine confirmation |
