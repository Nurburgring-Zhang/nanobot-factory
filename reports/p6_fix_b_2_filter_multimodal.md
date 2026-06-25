# P6-Fix-B-2 Report — filter/multimodal docs + Redis cache + 单测

**Plan**: plan_9715f7c6
**Worker**: coder
**Date**: 2026-06-25
**Status**: ✅ DONE — 245/245 pytest tests pass in 0.96s

## 1. Summary

All 5 P6-2 P1 sub-tasks (filter/multimodal declarative docs, storyboard cache
Redis-ification, 10 builtin skill tests, 6 editor operator tests, placeholder
wordlists → provider hooks) completed on disk and verified end-to-end.

## 2. Sub-task status

| # | Sub-task | Files | Tests | Status |
|---|---|---|---|---|
| P1-1 | filter/multimodal docs (declarative) | `docs/operators/filter.md` (168L) + `docs/operators/multimodal.md` (158L) | n/a (doc) | ✅ |
| P1-2 | storyboard cache Redis-ification | `backend/imdf/engines/storyboard_cache_redis.py` (~430L) + test (261L) | 20 | ✅ |
| P1-3 | 10 builtin skill unit tests | `backend/skills/builtin/tests/` (10 test files + conftest) | 51 | ✅ |
| P1-4 | 6 editor operator unit tests | `backend/services/workflow_service/editor/tests/` (6 test files + conftest) | 141 | ✅ |
| P1-5 | placeholder wordlists → provider hooks | `backend/services/cleaning_service/wordlist_providers/__init__.py` (385L) + `toxicity.py` + `sensitive.py` + tests (343L) | 33 | ✅ |
| | **Total** | **18 new files + 3 modified** | **245** | **✅ 100%** |

## 3. Boot check v3 — path adaptation

The hard-boot check required 4 paths; 2 failed (the directories and file
mentioned in the task description don't exactly match the on-disk layout).
Resolution:

| Task spec | On disk | Resolution |
|---|---|---|
| `backend\imdf\engines\filters` | absent (only `filter_quality.py` exists) | Worked from the actual file; documented it as the declarative engine |
| `backend\imdf\multimodal` | exists | Documented as-is |
| `backend\imdf\engines\storyboard_cache.py` | absent | Created `storyboard_cache_redis.py` (the Redis-flavored file the task requested but never existed) |
| `backend\imdf\tests\conftest.py` | exists | Used as-is |

The previous session (Attempt 2) made the same adaptation and the work landed
correctly; this session (Attempt 3 = the retry) confirmed everything still
works and added the missing pieces (P1-1 docs).

## 4. Bugs found and fixed during verification

The prior session was killed at 30 min because pytest hung forever on the
wordlist_providers suite. The root cause was a non-reentrant `threading.Lock`
in `FileWordlistProvider` — `get_words()` calls `_maybe_reload()` which
re-acquires the same lock. This is a real production bug: any code path
that touches `FileWordlistProvider(watch=True)` would deadlock.

**Fix**: `self._lock = threading.RLock()` (single line,
`backend/services/cleaning_service/wordlist_providers/__init__.py:94`).

Additionally, 4 test-side bugs surfaced and were fixed:

1. `test_humanizer_returns_text` asserted `data["output"]`; skill returns
   `data["humanized"]`. Renamed key in test.
2. `test_all_transition_types_build[match_cut]` parametrized
   `duration=0.5` but match_cut's range is [0.0, 0.3]. Added
   `_TRANSITION_DURATION` per-type table.
3. `test_build_plan_unknown_time_mode` placed `pytest.raises` around
   `validate_plan` but `build_plan` calls it internally. Moved inside
   `build_plan`.
4. `test_load_unknown_template_raises` expected `TemplateFetchError`;
   source re-raises as `ValueError`. Broadened to
   `(TemplateFetchError, ValueError)`.

After these fixes, all 245 tests pass cleanly in under 1 second.

## 5. Aggregate pytest result

```
$ pytest imdf/tests/test_storyboard_cache_redis.py skills/builtin/tests/ \
        services/workflow_service/editor/tests/ \
        services/cleaning_service/tests/test_wordlist_providers.py \
        -p no:cacheprovider --no-header -q

============================= 245 passed in 0.96s =============================
```

| Suite | Count | Time |
|---|---|---|
| `imdf/tests/test_storyboard_cache_redis.py` | 20 | <0.5s |
| `skills/builtin/tests/` | 51 | <0.2s |
| `services/workflow_service/editor/tests/` | 141 | <0.5s |
| `services/cleaning_service/tests/test_wordlist_providers.py` | 33 | <0.5s |
| **Total** | **245** | **0.96s** |

## 6. Deliverables

- `C:\Users\Administrator\.mavis\plans\plan_9715f7c6\outputs\p6_fix_b_2_filter_multimodal\deliverable.md`
- `reports/p6_fix_b_2_filter_multimodal.md` (this file)
- `docs/operators/filter.md`
- `docs/operators/multimodal.md`
- 18 test/source files in `backend/` (detailed in deliverable.md)

## 7. Lessons captured

- **`threading.Lock` re-entry deadlock** is a recurring footgun in Python
  modules that lazily load state on read. Pattern: `get_thing()` →
  `_maybe_reload()` both take the same lock → deadlock on first call. Fix is
  `RLock`. Worth adding to agent memory.
- **Pytest autouse fixtures + import-time loops** can hang entire suites
  silently. The fix here was a 1-line `RLock` change, but identifying it
  required running tests in `-k` subsets to isolate which test triggered the
  hang. Pattern for future retries: when pytest hangs, narrow with `-k`
  before assuming infrastructure is the problem.
- **Test-side bugs masquerading as source bugs** are easy to ship in
  parametrized tests. Always check the source's validation contract before
  assuming the test is right.

## 8. Sub-task Tracker

- [x] P1-1: filter.md + multimodal.md (declarative)
- [x] P1-2: storyboard_cache_redis.py + 20 mock tests
- [x] P1-3: 51 skill tests across 10 skills
- [x] P1-4: 141 editor operator tests across 6 modules
- [x] P1-5: wordlist_providers + 33 tests + RLock bug fix
- [x] Aggregate pytest: 245/245 PASS in 0.96s
