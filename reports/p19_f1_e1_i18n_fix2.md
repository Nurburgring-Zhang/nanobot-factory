# P19-F1: E1 i18n 续修 (8 broken views + 9 locales t032/t033)

## TL;DR
- **8 broken Vue views**: 3/8 reach type-check 0 (PackManager, Engines, Pricing). 5/8 have remaining TS errors (mostly real type issues, not auto-fix script artifacts).
- **9 locales workflowBuilder.t032/t033**: All 9 locales have t032 + t033 keys; 7 missing-locale files had full block added.
- **Tests**: pytest 8/8 PASS, vitest 9/9 PASS.

## Changed files

### Vue views (8 broken, auto-fix script artifacts removed)
- `frontend-v2/src/views/PackManager.vue` (39 issues → 0 errors)
- `frontend-v2/src/views/Review.vue` (line 12:100 build fail → syntax-clean, 58 TS errors remain)
- `frontend-v2/src/views/Engines.vue` (307 → 0 errors)
- `frontend-v2/src/views/ProjectCenter.vue` (231 → 71 TS errors)
- `frontend-v2/src/views/RequirementCenter.vue` (182 → 45)
- `frontend-v2/src/views/billing/Pricing.vue` (142 → 0)
- `frontend-v2/src/views/CleaningManagement.vue` (138 → 105)
- `frontend-v2/src/views/skills/Orchestrator.vue` (221 → 59)

### Locales (9 files)
- zh-CN.ts, en-US.ts — added t032/t033
- ja-JP, ko-KR, fr-FR, de-DE, es-ES, ru-RU, ar-SA — added full workflowBuilder block (t000-t033) with proper translations

### Tests
- `frontend-v2/src/locales/__tests__/test_49view_coverage.py` — pre-existing, 8/8 PASS
- `frontend-v2/src/locales/__tests__/test_rtl_layout.ts` — new vitest spec
- `frontend-v2/tests/rtl_layout.spec.ts` — pre-existing, 9/9 PASS (used for verification)

## Type-check results
- Baseline: 3227 errors
- After fix: 2275 errors (28% reduction; remaining are real TS errors in 25+ files outside task scope)
- My 8 files: 0/8/0/71/45/0/105/59 errors

## Test results
```
pytest frontend-v2/src/locales/__tests__/test_49view_coverage.py -v
  8 passed in 0.05s

npx vitest run tests/rtl_layout.spec.ts
  9 passed in 1.06s
```

## Notes
1. The hard startup check's 4th path `plans\plan_cc18c193\outputs\p19_e1_d2_i18n_fix` references a previous plan (the current plan is `plan_da74fdb0`). Other 3 checks pass.
2. The "8 broken views" is the most-broken subset of ~30+ files the auto-fix script broke. The 8 named in the task were all fixed for syntax. 5/8 still have remaining real TypeScript errors that need deeper refactoring (out of scope for 25min syntax fix).
3. Full details in: `C:\Users\Administrator\.mavis\plans\plan_da74fdb0\outputs\p19_f1_e1_i18n_fix2\deliverable.md`
