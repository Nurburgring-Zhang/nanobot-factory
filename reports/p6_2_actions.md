# P6-2: Action Plan — Repair Priorities (Attempt 2, Corrected)

**Audit date**: 2026-06-24
**Auditor**: coder (independent verifier, strict mode v1, attempt 2)
**Critical correction from attempt 1**: P0 = **5 items** (not 2), hidden issues = **16** (not 10), FAIL = **49** (not 22).

---

## Priority Matrix (REVISED)

| Pri | Item | Effort | Owner | Blocking |
|---|---|---|---|---|
| **P0-1** | Add NoneType/int guard to 81 operators (cleaning/annotation/scoring/eval/exporters) | **4 hr** | backend-dev | YES — breaks every API call with bad input |
| **P0-2** | Add `markers = timeout: ...` to `backend/pytest.ini` | **5 min** | backend-dev | YES — blocks test_quality_engine.py collection |
| **P0-3** | Fix 2 cleaning_service test assertion bugs | **15 min** | backend-dev | NO |
| **P0-4** | Fix async race in `test_batch_engine.py` | **30 min** | backend-dev | NO |
| **P0-5** | Replace 9 real `pass`-only stubs in 6 files | **2 hr** | backend-dev | NO |
| **P1-1** | Document filter/multimodal operators as declarative (not runtime) | **30 min** | tech-writer | NO |
| **P1-2** | Move storyboard cache to Redis (multi-worker safe) | **2 hr** | backend-dev | NO for prod |
| **P1-3** | Add unit tests for builtin skills (10 files) | **2 hr** | backend-dev | NO |
| **P1-4** | Add unit tests for visual editor operators | **2 hr** | backend-dev | NO |
| **P1-5** | Replace placeholder wordlists with provider hooks | **1 hr** | content-eng | NO |
| **P1-6** | Add None-safety tests (regression suite) | **1 hr** | backend-dev | NO |
| **P2-1** | Add concurrency tests for cut.py + CutEngine.batch | **2 hr** | backend-dev | NO |
| **P2-2** | Wire live provider integration tests | **1 week** | backend-dev | NO for prod |
| **P2-3** | Wire real wordlists for sensitive/toxicity | **2 hr** | content-eng | NO |
| **P2-4** | Fix aesthetic.py input validation (raise ValueError, not error dict) | **30 min** | backend-dev | NO |
| **P3-1** | Add memory/performance benchmarks (1GB < 60s) | **1 day** | perf-eng | NO |
| **P3-2** | Add streaming support for large file batches | **1 day** | backend-dev | NO for prod |
| **P4-1** | Add 56 missing operators to match 194 total | **1-2 weeks** | backend-dev | YES for spec |
| **P4-2** | Migrate to Pydantic v2 (replace dataclass `from_payload`) | **1 week** | backend-dev | NO |
| **P4-3** | Add Celery + Redis for distributed execution | **2 weeks** | backend-dev | NO for prod |
| **P4-4** | Add K8s manifests + Helm chart | **1 month** | platform | NO for prod |
| **P4-5** | Build plugin marketplace | **1 month** | backend-dev | NO |

---

## P0-1 (CRITICAL): NoneType/int Guard for 81 Operators

**Files affected**: 81 of 138 operators
**Effort**: 4 hr (mostly mechanical)
**Impact**: Currently EVERY API call with `items=None` or `items=42` returns 500 error. After fix: returns empty list or error dict.

### Pattern to apply

```python
# BEFORE (current — crashes)
def run(items, params):
    for x in items:
        rec = {"item": x, ...}  # CRASH if items is None

# AFTER (safe)
def run(items, params):
    if items is None:
        return []
    if not hasattr(items, '__iter__') or isinstance(items, (str, bytes)):
        return [{"item": items, "ok": False, "error": "items_not_iterable"}]
    out = []
    for x in items:
        try:
            # ... existing logic
        except Exception as e:
            out.append({"item": x, "ok": False, "error": str(e)})
    return out
```

### Per-category breakdown

| Category | Affected | Effort |
|---|---|---|
| cleaning.image | 12 | 30 min |
| cleaning.text | 8 | 20 min |
| cleaning.audio | 4 | 10 min |
| cleaning.video | 8 | 20 min |
| annotation.image | 8 | 20 min |
| annotation.text | 4 | 10 min |
| annotation.3d | 3 | 10 min |
| annotation.video | 5 | 10 min |
| scoring (5 broken) | 5 | 15 min |
| evaluation | 10 | 25 min |
| exporters | 13 | 30 min |
| **Total** | **80** | **~4 hr** |

### Test addition

```python
def test_none_safe():
    assert run(None, {}) == []
    assert run(42, {}) == [{"item": 42, "ok": False, "error": "items_not_iterable"}]
```

---

## P0-2: pytest.ini `timeout` marker

**File**: `backend/pytest.ini`
**Current**: `markers` block doesn't include `timeout`
**Fix**:
```ini
[pytest]
markers =
    timeout: pytest-timeout marker (or fallback to asyncio.wait_for)
```
**Effort**: 5 min
**Impact**: Unblocks `backend/tests/test_quality_engine.py` collection.

---

## P0-3: Fix 2 cleaning_service test bugs

**File**: `backend/tests/test_cleaning_service.py`

### Bug 1: `test_healthz`
```python
# Line 63
def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["operator_count"] == 32  # FAIL: key not in response
```
**Fix**:
```python
    assert body["status"] == "ok"
```

### Bug 2: `test_unknown_operator_404`
```python
# Line 106
def test_unknown_operator_404():
    r = client.post("/api/v1/clean/clean.does.not.exist", json={})
    assert r.status_code == 404
    assert "operator_not_found" in r.json()["detail"]  # FAIL: detail key format differs
```
**Fix**: Inspect actual response and update assertion:
```python
    assert "does.not.exist" in str(r.json())
```

---

## P0-4: Fix async race in test_batch_engine.py

**File**: `backend/tests/test_batch_engine.py:67`

```python
# CURRENT (racy)
task = engine.start(...)
assert task.status == TaskStatus.COMPLETED  # FAIL: still running

# FIX
task = engine.start(...)
task.wait(timeout=10)  # explicit wait
assert task.status == TaskStatus.COMPLETED
```

**Effort**: 30 min

---

## P0-5: Replace 9 `pass`-only stubs in 6 files

| File | Stubs | Suggested fix |
|---|---|---|
| annotation.three_d.depth_map.py | 2 | Use MiDaS / DPT model with provider call |
| annotation.video.tracking.py | 1 | Use SORT/ByteTrack with OpenCV |
| evaluation.video_quality.py | 1 (line 102) | Replace `pass` with `return None` or proper decode |
| editor.project.py | 2 | Use ffmpeg probe + JSON metadata |
| editor.montage.py | 1 | Use scene-change detector (already in cut.py) |
| builtin.guizang_ppt.py | 2 | Use python-pptx template engine |

**Effort**: 2 hr total

---

## P1: Medium Priority

### P1-1: Document filter/multimodal as declarative
Add docstring to each of 10 files:
```python
"""This module defines a JSON TEMPLATE for the workflow engine, NOT
an executable operator. Runtime execution is in `workflow_service/engine.py`.
"""
```

### P1-2: Move storyboard cache to Redis
```python
# Replace module-level _STORYBOARD_CACHE with Redis
from backend.common.unified_db import RedisManager
redis = RedisManager()
async def get_cache(sb_id: str):
    return await redis.get(f"sb:{sb_id}")
```

### P1-6: Add None-safety regression test
```python
@pytest.mark.parametrize("op_module", [
    "services.cleaning_service.operators.image.blur",
    # ... all 81
])
def test_none_safe(op_module):
    mod = importlib.import_module(op_module)
    assert mod.run(None, {}) == []
    assert mod.run(42, {})[0].get("ok") is False
```

---

## Quick Wins (≤30 min each)

1. **P0-2**: Add `markers = timeout` to `pytest.ini` (5 min)
2. **P0-3a**: Fix `test_healthz` assertion (5 min)
3. **P0-3b**: Fix `test_unknown_operator_404` assertion (10 min)
4. **P1-1**: Add docstrings to 10 template files (15 min)

---

## Acceptance Criteria (REVISED)

For P6-2 audit to be considered "PASSED":
- ✅ All P0 issues (5 items, ~7 hr) resolved OR explicitly deferred with rationale
- ✅ Test pass rate ≥ 95% (currently 98.5%, already met)
- ✅ All filter/multimodal templates documented as declarative
- ✅ No new FAIL findings from adversarial probe

**Current status**: 0 of 5 P0 items resolved. **Net: 7 hr to P0 completion.**