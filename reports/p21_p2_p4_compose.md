# P21 Phase 2 P4 — Skill composition helper (R2 audit N5)

**Author**: coder (P21 P2 P4 skill-expert)
**Date**: 2026-07-11
**Sprint**: P21 / Phase 2 / P4 / P1 fix
**R2 reference**: `reports/p21_r2_audit_skill.md` §2 N5 (P0)
**Audit claim**: "No skill composition is possible. The Pydantic v2 blocker (N1) prevents `clean_pii_remove → synth_translate_en` and other chains. ... There is no `SkillPipeline` / `SkillChain` API."
**Scope**: Add `chain()` + `PipelineStep` composition helper to `backend.imdf.skills.compose`. Export from package `__init__.py`. Add focused test suite.

---

## 1. What was changed

| File | Change | Lines |
|------|--------|-------|
| `backend/imdf/skills/compose.py` | **NEW** — `PipelineStep` dataclass + `chain()` async function + default extract/inject helpers | 158 |
| `backend/imdf/skills/__init__.py` | **MODIFIED** — added `from .compose import PipelineStep, chain` + 2 entries in `__all__` | +6 |
| `tests/p2_p4/test_skill_compose.py` | **NEW** — 17-test focused suite (2-step / 3-step / error / custom extract-inject / dataclass surface) | 343 |

**Existing skill files (clean_pii_remove, synth_translate_en, all 8 clean + 8 label + 17 synth)**: **untouched** per spec hard rule.

---

## 2. Design choices

### 2.1 Why `chain()` (not `SkillPipeline` class)

The task spec's reference implementation was `chain(skills: List[PipelineStep], initial: SkillInput) -> List[SkillOutput]`. I followed that exactly because:
- The audit framing is "no `SkillPipeline` / `SkillChain` API" — both names appear, but a free function is smaller, easier to test, and the right level of abstraction for sequential composition. Async helpers typically live as functions.
- The dataclass `PipelineStep` IS the user's "what skill + what hooks" container. `chain()` IS the executor. The two-piece split matches Python's `graph + apply()` pattern.

### 2.2 Default extract / inject semantics

| Default | What it does | Why |
|---------|-------------|-----|
| `extract(out) → out.result` | Read `SkillOutput.result` if present, else return the whole output | The most common inter-skill contract is "what the previous skill produced" flows forward. `SkillOutput.result` is the documented "data" field of the envelope. |
| `inject(value, _prev) → SkillInput(params={"input": value})` | Wrap value as `{"input": value}` | Matches the convention of imdf skills that read a single canonical key (e.g. several `*Input` models take `text` as the primary field). The default is intentionally generic — typed skills (e.g. `PiiRemoveInput(text=...)` or `TranslateEnInput(text=...)`) get custom inject lambdas. |

A custom extract/inject example for the R2 headline chain:

```python
chain([
    PipelineStep(
        name="redact",
        func=clean_pii_remove,
        extract=lambda out: out.result["redacted"],
        inject=lambda x, _: SkillInput(params={"text": x}),
    ),
    PipelineStep(
        name="translate",
        func=translate_en,
        inject=lambda x, _: SkillInput(params={"text": x}),
    ),
], initial=SkillInput(params={"text": "email bob@x.com"}))
```

This is the exact "clean_pii_remove → synth_translate_en" pattern from the R2 §N5 finding — now compositionable.

### 2.3 Why no new dependencies

The spec hard rule says "Do NOT introduce new dependencies". The helper is stdlib-only:
- `dataclasses` (stdlib since 3.7)
- `typing` (stdlib)
- `backend.skills.SkillInput, SkillOutput` (already-imported project symbols)

No `tenacity`, no `pydantic`, no `asyncio` machinery beyond what the existing skills already use.

### 2.4 Error handling: loud-fail with caller-side recovery

The chain does **not** swallow errors and does **not** buffer partial results silently. Reasoning:
- The R2 audit's headline finding was that "chained real work is impossible" — silent partial-result accumulation would hide which step is broken and make production debugging much harder than the synchronous `Python traceback → file → line`.
- Skills are pure relative to their `SkillInput` — callers who need partial results can re-run the earlier steps independently (this is exactly what the new test `test_earlier_results_not_lost_on_error` exercises).
- The chain's pre-conditions (non-empty list, all `PipelineStep`) raise `TypeError` early — easier to debug than runtime `AttributeError` deep in a chained call.

---

## 3. Test coverage (17 tests, all PASS in 0.33s)

| Class | Test | Asserts |
|-------|------|---------|
| `TestTwoStepChain` | `test_a_then_b_yields_hello_bang` | The headline R2 N5 acceptance criterion: `a("hello") -> b` yields `result == "hello!"` |
| `TestTwoStepChain` | `test_chain_preserves_metadata_per_step` | Each step's `SkillOutput.metadata` is preserved end-to-end |
| `TestTwoStepChain` | `test_step_names_preserved` | `PipelineStep.name` is set and readable |
| `TestThreeStepChain` | `test_a_b_c_yields_hello_bang_uppercased` | 3-step chain `a → b → c` (c uppercases) yields `"HELLO!"` |
| `TestThreeStepChain` | `test_three_step_chain_returns_all_outputs_in_order` | The list-of-outputs contract holds for 3 steps |
| `TestErrorHandling` | `test_middle_skill_raises_chain_raises` | Middle step `ValueError` propagates out of `chain()` |
| `TestErrorHandling` | `test_earlier_results_not_lost_on_error` | Caller can recover earlier results via re-running the pure skill (the recommended recovery pattern) |
| `TestErrorHandling` | `test_empty_chain_raises_type_error` | `chain([], ...)` raises `TypeError("non-empty list")` |
| `TestErrorHandling` | `test_non_list_raises_type_error` | `chain((step,), ...)` (tuple, not list) raises `TypeError` |
| `TestErrorHandling` | `test_non_pipeline_step_raises_type_error` | `chain([step, "not-a-step"], ...)` raises `TypeError` |
| `TestCustomExtractInject` | `test_extract_nested_result_field` | Nested-dict extract (`out.result["translation"]`) flows into next step's `params["text"]` |
| `TestCustomExtractInject` | `test_pii_then_translate_simulation` | Closer-to-real `clean_pii_remove → synth_translate_en` simulation — redacted text flows into translate_skill, returns `"[EN] email me at bob[AT]x.com"` |
| `TestDataclassSurface` | `test_pipeline_step_is_dataclass` | `PipelineStep` is a `@dataclass` (per task spec) |
| `TestDataclassSurface` | `test_chain_exported_from_compose_module` | `from backend.imdf.skills.compose import chain, PipelineStep` works directly (bypasses pre-existing `imdf.creative` blocker — see §4) |
| `TestDataclassSurface` | `test_default_extract_reads_result` | `_default_extract(out).result` returns the dict |
| `TestDataclassSurface` | `test_default_inject_wraps_input_key` | `_default_inject("VAL", prev)` returns `SkillInput(params={"input": "VAL"})`, and `prev` is **not** mutated |
| `TestDataclassSurface` | `test_default_extract_handles_missing_result_attr` | Defensive: if a step returns a non-`SkillOutput` object, default extract returns the object itself (no crash) |

### Combined p2_p4 run

```
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& D:\ComfyUI\.ext\python.exe -m pytest tests/p2_p4/ -v
======================== 41 passed, 1 warning in 2.35s ========================
```

17 new (compose) + 16 (video_metadata) + 8 (audit_log_2sites) = 41 PASS. No regressions.

---

## 4. Known limitation: pre-existing `imdf.creative` import blocker

`backend/imdf/skills/__init__.py` line 13 does `from .registry import (...)`, which transitively imports `imdf.creative.redfox.skills`, and `imdf` is **not** on the import path:

```
$ python -c "from backend.imdf.skills import list_redfox_skills"
ModuleNotFoundError: No module named 'imdf.creative'
```

This is a **pre-existing** P0 / R2 N6 finding (the "crawl base import blocker" / the registry import shadowing by `imdf.creative`). It is **out of scope** for this P4 task per the hard rule "Do NOT modify existing skill files — only ADD `compose.py` + `__init__.py` export".

What this means for the new export:
- `from backend.imdf.skills.compose import chain, PipelineStep` ✅ — works (direct module import, bypasses `__init__.py` blocker)
- `from backend.imdf.skills import chain, PipelineStep` ❌ — currently fails because the package `__init__.py` can't load due to the registry import blocker

**Action taken**: I added the export to `__init__.py` as a forward-looking change — when N6 (or whoever owns the `imdf.creative` import path) is fixed, the package-level re-export will be live without further code changes.

**Action NOT taken (intentionally)**: I did **not** wrap the `from .registry import` in `try/except` because:
- The hard rule says "only ADD `compose.py` + `__init__.py` export" — adding a `try/except` around the existing registry import is a defensive change to existing behaviour, not strictly an "add export".
- A future fix for N6 should be in `registry.py` (or by adding `imdf` to the path), not by making `imdf.skills` silently import-less. Silent fallback would hide the bug.
- The `compose` module is fully usable today via direct import, which the test suite verifies.

The test file deliberately uses direct import (`from backend.imdf.skills.compose import ...`) so the suite passes in the current (broken-`__init__`) state and will continue to pass when the blocker is fixed.

---

## 5. Verifier checklist (re-runnable)

```powershell
# 1. Run the new test suite
$env:PYTHONPATH = "D:\Hermes\生产平台\nanobot-factory"
& D:\ComfyUI\.ext\python.exe -m pytest tests/p2_p4/test_skill_compose.py -v
# Expected: 17 passed in <1s

# 2. Full p2_p4 regression
& D:\ComfyUI\.ext\python.exe -m pytest tests/p2_p4/ -v
# Expected: 41 passed in <5s

# 3. Headline R2 N5 acceptance: a("hello") -> b yields "hello!"
& D:\ComfyUI\.ext\python.exe -c "import asyncio, sys; sys.path.insert(0, r'D:\Hermes\生产平台\nanobot-factory'); from backend.imdf.skills.compose import PipelineStep, chain; from backend.skills import SkillInput, SkillOutput

async def a(i): return SkillOutput(success=True, result=(i.params['input']).upper())
async def b(i): return SkillOutput(success=True, result=(i.params['input']).lower() + '!')

async def main():
    r = await chain([PipelineStep('a',a), PipelineStep('b',b)], SkillInput(params={'input':'hello'}))
    print('FINAL:', r[-1].result)
asyncio.run(main())"
# Expected: FINAL: hello!

# 4. Verify __init__.py export is in place (static check, doesn't require import to succeed)
& D:\ComfyUI\.ext\python.exe -c "import pathlib; src = pathlib.Path(r'D:\Hermes\生产平台\nanobot-factory\backend\imdf\skills\__init__.py').read_text(encoding='utf-8'); assert 'from .compose' in src; assert '\"PipelineStep\"' in src; assert '\"chain\"' in src; print('EXPORT OK')"
# Expected: EXPORT OK
```

---

## 6. Open items / future work

1. **N6 unblock** — fixing `imdf.creative` import path will make the package-level `from backend.imdf.skills import chain, PipelineStep` work. Out of scope for P4.
2. **N1 + N2** — even with the composition helper, individual imdf skills still throw on default params (R2 N1 Pydantic v2 + R2 N2 missing defaults). Until N1 + N2 are also fixed end-to-end, production chains like `clean_pii_remove → synth_translate_en` will still raise on the second link. The composition helper is the **scaffolding** for those chains — the underlying skills still need their own fixes.
3. **Parallel / branching chains** — the current `chain()` is strictly sequential. A future `chain_parallel(steps, initial)` (using `asyncio.gather`) would be a 1-file addition if / when needed. Not in scope today.
4. **Retry per-step** — `chain()` does not retry individual steps. A future `PipelineStep(retries=N)` field with `tenacity` integration would address R2 N3 (retry/backoff). Out of scope here.

---

## 7. Files referenced

- `backend/imdf/skills/compose.py` (new, 158 lines)
- `backend/imdf/skills/__init__.py` (+6 lines, 2 imports + 2 `__all__` entries)
- `tests/p2_p4/test_skill_compose.py` (new, 343 lines, 17 tests)
- `backend/skills/legacy.py` (read-only, defines `SkillInput` / `SkillOutput` dataclasses)
- `backend/imdf/skills/clean/clean_pii_remove.py` (read-only, source of `clean_pii_remove` for future chain demos)
- `backend/imdf/skills/synth/synth_translate_en.py` (read-only, source of `translate_en` for future chain demos)
- `reports/p21_r2_audit_skill.md` (R2 audit, §2 N5 the spec maps to)

— end of report —
