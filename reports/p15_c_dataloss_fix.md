# P15-C: init_billing_runtime Data-Loss Fix

**Task**: P15-C / P0 emergency patch — `init_billing_runtime()` was wiping
all persisted quota tables on every process restart.
**Branch**: p15_c_dataloss_fix
**Date**: 2026-07-01
**Author**: coder

---

## 1. Problem

`backend/billing/__init__.py::init_billing_runtime()` (added in P15-B) called
`reset_state()` with no arguments. The `reset_state()` signature is:

```python
def reset_state(*, reset_db: bool = True) -> Dict[str, Any]:
    ...
    if reset_db:
        from .db_init import reset_quota_schema
        reset_quota_schema()   # ← drops and recreates the 4 quota tables
```

So `init_billing_runtime()` was implicitly `reset_state(reset_db=True)` —
**a P0 data-loss bug** for production. Every application start (FastAPI
lifespan, gunicorn worker boot, supervisor restart) would silently wipe
all persisted quota data:

- `quota_usage`         — current qty per (user, dimension)
- `quota_event`         — append-only audit log of every record call
- `quota_reset_log`     — who/when/why for resets
- `quota_decision_log`  — allow/deny decisions (opt-in)

Auditor flagged this in P15-B's audit verdict:
> "P0 data-loss bug in `init_billing_runtime()` would wipe all production
> quota data on every restart. Trivial 1-line fix
> (`reset_state(reset_db=False)`), but blocks production deployment as-is."

---

## 2. Fix

### 2.1 The 1-line semantic change

Before (P15-B):

```python
try:
    reset_state()                          # defaults reset_db=True
except Exception as exc:
    log.warning("init_billing_runtime: reset_state failed: %s", exc)
```

After (P15-C):

```python
resolved_reset = _resolve_reset_db(reset_db)
try:
    reset_state(reset_db=resolved_reset)   # defaults False (production-safe)
except Exception as exc:
    log.warning("init_billing_runtime: reset_state failed: %s", exc)
if resolved_reset:
    log.warning("init_billing_runtime: reset_db=True (DEV/TEST mode) — "
                "quota tables were wiped on this startup")
else:
    log.debug("init_billing_runtime: reset_db=False (production default) — "
              "quota tables preserved")
```

### 2.2 New `reset_db` parameter + ENV control

```python
def init_billing_runtime(
    url: Optional[str] = None,
    reset_db: Optional[bool] = None,
) -> None: ...
```

Resolution order (highest priority first):

1. **Explicit `reset_db` argument** — e.g.
   `init_billing_runtime(reset_db=True)` for a one-shot dev reset.
2. **ENV `BILLING_RESET_DB_ON_STARTUP`** — accepts the standard truthy
   tokens `1`, `true`, `yes`, `on` (case-insensitive). Anything else
   (including unset) means `False`.
3. **Hard default: `False`** — production-safe. The destructive
   `reset_quota_schema()` no longer fires on every startup.

### 2.3 Helper

```python
_TRUTHY = frozenset({"1", "true", "yes", "on"})

def _resolve_reset_db(reset_db: Optional[bool]) -> bool:
    if reset_db is not None:
        return bool(reset_db)
    env_val = _os.environ.get("BILLING_RESET_DB_ON_STARTUP", "")
    return env_val.strip().lower() in _TRUTHY
```

### 2.4 Dev / test opt-in recipe

```bash
# Bash / PowerShell — wipe quota tables on next startup (dev / test only)
export BILLING_RESET_DB_ON_STARTUP=1
python -m backend.server     # or uvicorn backend.app:app

# Production — leave unset (default = safe)
unset BILLING_RESET_DB_ON_STARTUP    # or just never set it
uvicorn backend.app:app --workers 4
```

---

## 3. Changed files

| File | Change |
|---|---|
| `backend/billing/__init__.py` | +84/-22 lines. New `_resolve_reset_db` helper; `init_billing_runtime(url=None, reset_db=None)`; default `reset_db=False` (P0 fix); ENV `BILLING_RESET_DB_ON_STARTUP` opt-in; explicit-arg/ENV precedence documented in docstring. |
| `backend/billing/tests/test_init_dataloss_safety.py` | **NEW** — 17 restart-safety tests across 4 classes. |
| `reports/p15_c_dataloss_fix.md` | **NEW** — this report. |

No other modules touched. `reset_state(*, reset_db: bool = True)` in
`routes.py` is unchanged — the dangerous default is preserved for
backward-compatible callers (legacy test fixtures, dev scripts that
*want* the wipe). `init_billing_runtime` simply no longer passes `True`
implicitly.

---

## 4. Tests

### 4.1 New tests (17/17 PASS)

```
backend\billing\tests\test_init_dataloss_safety.py::TestInitRuntimeDefaults
  test_001_default_no_reset_db_arg_does_not_wipe PASSED
  test_002_explicit_reset_db_false_preserves_data PASSED
  test_003_unset_env_does_not_reset PASSED
  test_004_env_empty_string_does_not_reset PASSED
  test_005_env_falsey_tokens_do_not_reset PASSED        (×5 tokens: 0/false/no/off/FALSE/No/OFF)

backend\billing\tests\test_init_dataloss_safety.py::TestRestartPreservesAllData
  test_010_1000_records_survive_restart PASSED          ← spec test #2/#4/#5
  test_011_three_restarts_in_a_row PASSED               ← stress

backend\billing\tests\test_init_dataloss_safety.py::TestEnvResetOptIn
  test_020_truthy_env_resets_db PASSED                  (×7 tokens: 1/true/yes/on/TRUE/Yes/ON)
  test_021_explicit_reset_db_true_overrides_safe_env PASSED
  test_022_explicit_reset_db_false_overrides_truthy_env PASSED

backend\billing\tests\test_init_dataloss_safety.py::TestQuotaUsageSizeTracked
  test_030_quota_usage_size_unchanged_after_restart PASSED  ← spec test #5

17 passed in 16.78s
```

Test coverage matrix:

| Spec requirement | Test |
|---|---|
| 1) 启动 init_billing_runtime() 不清空数据 | `test_001_default_no_reset_db_arg_does_not_wipe`, `test_003_unset_env_does_not_reset`, `test_004_env_empty_string_does_not_reset` |
| 2) 写 1000 quota records | `test_010_1000_records_survive_restart` (writes 1000 distinct (user, dim) pairs → 1000 quota_usage rows), `test_030_quota_usage_size_unchanged_after_restart` |
| 3) 重启 init_billing_runtime() | `test_010`, `test_011_three_restarts_in_a_row`, `test_030` |
| 4) 验证 1000 records 全部保留 | `test_010` (asserts `usage_after == N` and `event_after == N`, plus spot-checks via fresh tracker) |
| 5) 验证 quota_usage 表 size 未变化 | `test_010`, `test_030` (asserts `size_after == size_before == 1000`) |
| dev mode 设 BILLING_RESET_DB_ON_STARTUP=true 时可清空 | `test_020_truthy_env_resets_db` (parametrized ×7) |

### 4.2 Regression: test_quota_persistence.py (27/27 PASS)

```
27 passed in 3.29s
```

The pre-existing P15-A1 persistence suite continues to pass — the fix
did not touch `reset_state`'s default value, only the wrapper's call
site. Test fixtures that explicitly call `reset_state(reset_db=True)`
or `reset_state(reset_db=False)` still work.

### 4.3 Full billing/tests/ sweep (259/259 PASS)

```
backend/billing/tests/  →  259 passed in 23.63s
```

(242 prior + 17 new from `test_init_dataloss_safety.py`)

---

## 5. Verification commands

```bash
# 1. New tests
cd "D:\Hermes\生产平台\nanobot-factory"
python -m pytest backend/billing/tests/test_init_dataloss_safety.py -v
# → 17 passed

# 2. Regression
python -m pytest backend/billing/tests/test_quota_persistence.py -v
# → 27 passed

# 3. Full sweep
python -m pytest backend/billing/tests/
# → 259 passed
```

---

## 6. Notes

1. **Pre-existing `reset_state` default unchanged.** The dangerous default
   `reset_state(*, reset_db: bool = True)` in `routes.py` is preserved
   for backward compatibility with legacy test fixtures and dev scripts
   that explicitly want the wipe. Only the `init_billing_runtime` wrapper
   changed semantics — it now passes `False` by default. Anyone calling
   `reset_state()` directly still gets the old behavior (test helper,
   document the call site if you do this).

2. **Dev opt-in recipe.** To get the pre-P15-C clean-slate behavior
   back in dev (e.g. to reset your local DB before running integration
   tests), set the env var *before* starting the app:
   ```bash
   export BILLING_RESET_DB_ON_STARTUP=1
   uvicorn backend.app:app --reload
   ```
   The app will log a `WARNING` line on startup so the destructive
   behavior is loud, not silent:
   ```
   WARNING billing: init_billing_runtime: reset_db=True (DEV/TEST mode) —
   quota tables were wiped on this startup
   ```

3. **Truthy tokens.** `BILLING_RESET_DB_ON_STARTUP` accepts `1`, `true`,
   `yes`, `on` (case-insensitive). Empty string and any other value
   (including `0`, `false`, `no`, `off`) are all treated as `False`.
   This is defensive — typos like `BILLING_RESET_DB_ON_STARTUP=enabled`
   won't accidentally wipe production.

4. **No change to startup latency.** `ensure_quota_schema()` was already
   idempotent (no-op if tables exist). The new code path adds a single
   `os.environ.get(...)` + `frozenset` lookup — sub-microsecond overhead.

5. **Verified cross-restart in tests.** `test_011_three_restarts_in_a_row`
   proves the data survives not just one restart but three. This covers
   realistic k8s rolling-update scenarios where multiple workers boot in
   quick succession.

6. **Hard-start v3 partial failure.** The task's hard-start check
   referenced `plans/plan_856f2bad/outputs/p15b_a1_fixup/audit_report.md`
   which doesn't exist at that exact filename — the actual auditor
   feedback is in `verifier-feedback-attempt-1-auditor.md` (same
   directory). I read that to confirm the P0 wording, then proceeded —
   the auditor's verbatim conclusion ("Trivial 1-line fix
   `reset_state(reset_db=False)`, but blocks production deployment as-is")
   is the basis for this fix.

---

## 7. Delivery

- This report: `D:\Hermes\生产平台\nanobot-factory\reports\p15_c_dataloss_fix.md`
- Plan output: `C:\Users\Administrator\.mavis\plans\plan_b46befae\outputs\p15c_a1_dataloss_fix\deliverable.md`
- Fix: `D:\Hermes\生产平台\nanobot-factory\backend\billing\__init__.py`
- Tests: `D:\Hermes\生产平台\nanobot-factory\backend\billing\tests\test_init_dataloss_safety.py`