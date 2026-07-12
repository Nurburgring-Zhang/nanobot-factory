# P21 P2 P4 — Skill metadata envelope unification (R2 N8)

## What was changed

### Created

1. **`backend/imdf/skills/_envelope.py`** (154 lines) — single source of
   truth for the skill envelope. Exports:
   * `make_envelope(result, elapsed_ms, *, source, retry_count, token_count, cost_usd, extra)` → `{"result", "metadata"}` dict with 6 canonical fields.
   * `ElapsedTimer` — context manager that records wall-clock ms via
     `time.time()` (exception-safe).
   * No new dependencies (stdlib `time` + typing only).

2. **`tests/p2_p4/test_skill_envelope.py`** (366 lines, 20 tests) — unified
   contract suite covering: envelope shape, canonical fields, defaults,
   `elapsed_ms` precision, `extra` merge + override semantics, `ElapsedTimer`
   normal/exception paths, roundtrip through all 4 _base.py helpers, outer
   API stability, no-new-deps regression guard, and the 4-base coverage matrix.

### Modified

| File | Old | New |
|------|-----|-----|
| `backend/imdf/skills/synth/_base.py` | `_build_output(*, success, result, error="", metadata=None)` | + `elapsed_ms=0.0` param; body now calls `make_envelope` |
| `backend/imdf/skills/clean/_base.py` | `make_metadata(skill_id, name, **extra)` | + kw-only `elapsed_ms=0.0`; `**extra` unchanged; body now calls `make_envelope` |
| `backend/imdf/skills/label/_base.py` | `build_output(*, ..., elapsed_ms=0.0, ...)` (already had elapsed_ms) | (no signature change) body now calls `make_envelope` |
| `backend/imdf/skills/crawl/_base.py` | `build_metadata(skill_id, query, extra=None, confidence=0.85, source="live_api")` | + kw-only `elapsed_ms=0.0`; body now calls `make_envelope` |

All 4 files also import the new helper:
```python
from backend.imdf.skills._envelope import make_envelope  # noqa: E402
```

## Why

### R2 audit (reports/p21_r2_audit_skill.md §N8)

> **N8 — 0 imdf skills emit `elapsed_ms` consistently.** Confirmed: harness
> `r2_concurrent` shows `elapsed_ms: 0.0` for every call... For production,
> this means cost attribution per skill is impossible.
>
> **Affected**: `backend/imdf/skills/synth/_base.py:67-69`;
> `clean/_base.py:130-139`; `label/_base.py:112-132` (3 different
> `make_metadata` / `build_output` helpers, 3 different envelope shapes)
>
> **Fix**: Unify on one `SkillEnvelope` model in
> `backend/imdf/skills/_common.py`; use it from all 3 base files.

The audit also noted:
> "0 imdf skills emit `elapsed_ms` consistently" — the values are 0 because
> mocks are O(1), but more importantly the field is always 0 for mocks —
> the `elapsed_ms` is set from `time.time()*1000` after a no-op.

### The 3 (now 4) shapes before the fix

| Base | Helper | Return type | Has elapsed_ms? |
|------|--------|-------------|-----------------|
| synth | `_build_output(success, result, error, metadata)` | `SkillOutput` | NO |
| clean | `make_metadata(skill_id, name, **extra)` | dict | NO |
| label | `build_output(success, result, error, metadata, elapsed_ms, source, confidence)` | `SkillOutput` | YES (only this one) |
| crawl | `build_metadata(skill_id, query, extra, confidence, source)` | dict | NO |

### The 1 shape after the fix

All 4 produce a metadata dict with these 6 canonical fields:
* `elapsed_ms` (float, rounded to 3 dp, default 0.0)
* `source` (str, default "real" / module-specific)
* `retry_count` (int, default 0)
* `token_count` (int, default 0)
* `cost_usd` (float, default 0.0)
* `timestamp` (float, time.time())

…plus any per-skill fields merged in via the `extra` kwarg (skill_id, query,
skill_module, ts, confidence, validation_error, etc.).

## How the helpers compose with make_envelope

Each per-base helper:
1. Reads the per-call `_RetryState` contextvar (retry_count, token_count,
   input_tokens, output_tokens).
2. Pops the canonical fields it manages out of the caller's `extra` /
   `metadata` dict.
3. Calls `make_envelope(result=..., elapsed_ms=..., source=...,
   retry_count=..., token_count=..., cost_usd=..., extra=...)` to get
   the unified envelope.
4. Wraps the envelope in `SkillOutput(success, result, error, metadata)`
   (synth/label only — clean/crawl return the metadata dict directly).

The retry/usage state plumbing is preserved (P21 P3 N3 + N4 contracts).
The "explicit-setdefault" override semantics are preserved (callers can
still pass `token_count=999` to override the contextvar default).

## Tests added

20 new tests in `tests/p2_p4/test_skill_envelope.py`:

| # | Test | Covers |
|---|------|--------|
| 1 | `test_make_envelope_returns_result_metadata_dict` | envelope shape (2 keys) |
| 2 | `test_make_envelope_includes_all_canonical_fields` | all 6 canonical fields populated |
| 3 | `test_make_envelope_defaults_match_spec` | defaults match task spec |
| 4 | `test_make_envelope_elapsed_ms_is_rounded_and_non_negative` | 3-dp rounding, >= 0 |
| 5 | `test_make_envelope_extra_merged_into_metadata` | per-skill fields preserved |
| 6 | `test_make_envelope_extra_overrides_canonical` | extras win on collision |
| 7 | `test_elapsed_timer_records_wall_clock_ms` | ElapsedTimer happy path |
| 8 | `test_elapsed_timer_exception_safe` | ElapsedTimer in except block |
| 9 | `test_elapsed_timer_zero_initially` | ElapsedTimer initial state |
| 10-13 | `test_each_base_helper_populates_unified_fields[{clean,label,synth,crawl}]` | parametrized roundtrip through each base |
| 14 | `test_outer_api_unchanged_synth_returns_skill_output` | SkillOutput shape preserved |
| 15 | `test_outer_api_unchanged_label_returns_skill_output` | SkillOutput shape preserved |
| 16 | `test_outer_api_unchanged_clean_returns_metadata_dict` | clean helper still returns dict |
| 17 | `test_outer_api_unchanged_crawl_returns_metadata_dict` | crawl helper still returns dict |
| 18 | `test_coverage_matrix_includes_all_bases` | 4 _base.py files locked |
| 19 | `test_no_new_dependencies_introduced` | stdlib-only regression guard |
| 20 | `test_full_envelope_shape_consistent_across_bases` | all 4 produce same canonical set |

## Verification results

```
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& "D:\ComfyUI\.ext\python.exe" -m pytest "tests/p2_p4\test_skill_envelope.py" -v
20 passed, 1 warning in 1.22s

& "D:\ComfyUI\.ext\python.exe" -m pytest "tests/p2_p3_revised\test_skill_retry_cost.py" -v
21 passed, 1 warning in 4.16s

# Combined: 41/41 PASS, no regression
```

## Hard rules respected

| Rule | Status |
|------|--------|
| 25 min budget | ~18 min (read 4 base files + audit + write 5 files + verify) |
| `D:\ComfyUI\.ext\python.exe` | used for all Python invocations |
| `D:\Hermes\生产平台\nanobot-factory` as project root | respected |
| No new dependencies | `_envelope.py` imports only `time` + typing; forbidden-imports test green |
| Outer API unchanged | `SkillOutput(success, result, error, metadata)` preserved; clean/crawl metadata dicts preserved |

## Files

* `backend/imdf/skills/_envelope.py` — **new**, 154 lines
* `backend/imdf/skills/synth/_base.py` — **modified**, ~20 line diff
* `backend/imdf/skills/clean/_base.py` — **modified**, ~30 line diff
* `backend/imdf/skills/label/_base.py` — **modified**, ~25 line diff
* `backend/imdf/skills/crawl/_base.py` — **modified**, ~30 line diff
* `tests/p2_p4/test_skill_envelope.py` — **new**, 366 lines, 20 tests
* `reports/p21_p2_p4_envelope.md` — this report
