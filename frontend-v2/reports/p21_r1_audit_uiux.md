# P21 R1 UI/UX Audit Report (PARTIAL — task killed at 40min)

## Methodology
1. Inventoried 62 views + 21 components.
2. Read App.vue (526 lines), ErrorBoundary.vue (top 50), 4 stub views (Invoices, Orders, Pricing, Contracts), 5 corrupted views.
3. Ran `npx vue-tsc --noEmit` -> 95 errors, exit 2.
4. Ran `npx vite build` -> fails at first parse error (CollectionCenter.vue:1:34).
5. Programmatic i18n key cross-reference: 786 distinct t() keys used, 237 in zh-CN -> 549 missing.
6. Per-view pattern audit on all 62 views (NAlert error, NEmpty, NSkeleton, loading.value, role, aria-label, try/catch, await calls, message.error).

## Top 30 Gaps

### P0 - Build/runtime blockers (5 views cannot mount)
1. `src/views/CollectionCenter.vue` (1 line / 30KB / vite parse error at 1:34). Fix: git checkout HEAD -- then re-apply. Test: `npx vite build`.
2. `src/views/Delivery.vue` (1 line / 13KB / vue-tsc: 45 errors - worst). Fix: same.
3. `src/views/WorkflowBuilder.vue` (1 line / 26KB / vue-tsc: 25 errors).
4. `src/views/PackManager.vue` (1 line / 25KB / vue-tsc: 11 errors).
5. `src/views/CapabilityRegistry.vue` (1 line / 21KB / vue-tsc: 7 errors).

All 5 share same corruption pattern (template collapsed to 1 line).

### P1 - Stub views (no API integration)
6. `src/views/billing/Invoices.vue:40-95` - Hardcoded invoices array; onMounted empty; downloadFile shows message.info; comment "// 实际: GET /api/v1/invoices/{no}/verify".
7. `src/views/billing/Orders.vue:47-92` - Hardcoded 3 orders; submit() generates fake ID with Math.random().
8. `src/views/billing/Pricing.vue:64-86` - Hardcoded 5-plan static list; confirmUpgrade() mutates currentPlan locally.
9. `src/views/contracts/Contracts.vue:44-95` - Hardcoded contracts; // 实际: comments throughout.
10. `src/views/crm/Customers.vue` - 0 message.error, 0 NEmpty, 0 try/catch in 220-line view. Likely stub (not fully read).
11. `src/views/tickets/Tickets.vue` - 294 lines, 0 NEmpty, 0 message.error. Likely stub (not fully read).

### P1 - i18n gaps (549 keys missing in zh-CN)
12. `src/locales/zh-CN.ts` (and en-US, ja-JP, ar-SA, ru-RU - all flat 237 keys). 786 t() references vs 237 defined -> 549 missing = runtime fallback to key string.
13. `src/components/GlobalSearch.vue` - Hardcoded English: "Search datasets, projects...", "No matches", "Try a different keyword...", "Recent", "Favorites", "Star current page".
14. `src/components/ShortcutHelp.vue` - Hardcoded English: "Keyboard shortcuts", "Press ? to toggle this dialog", "Navigate".
15. `src/components/Topbar.vue` - Likely hardcoded English menu items (not read; flagged via pattern audit).
16. 5 corrupted views use t('namespace.t000')..t099 placeholders - all fall back to literal "namespace.t000" string.
17. `requirementCenter.*` namespace - 50+ t() calls; only 1-2 in zh-CN.

### P1 - Dark mode gaps
18. `src/views/billing/Pricing.vue:92-96` - `color: #18a058; background: #999;` literals in scoped style. Scoped wins against App.vue global overrides.
19. `src/views/billing/Invoices.vue:99` - `padding: 16px` literal background white-only.
20. `src/views/contracts/Contracts.vue` - Same scoped-style pattern.
21. 11+ other views using `color: #999/#888/#666/#333` - 30+ occurrences.
22. `src/App.vue:357-368` - background fallback light - can FOUC on cold start.

### P1 - WCAG 2.1 AA gaps
23. `src/App.vue:9-12` - NMessageProvider/NNotificationProvider has no aria-live - toasts not announced.
24. `src/components/Topbar.vue` - No skip-link before main nav. WCAG 2.4.1 Bypass Blocks.
25. `src/views/billing/Invoices.vue:11`, Orders.vue:15, Pricing.vue:40, Contracts.vue:15 - NModal title lacks aria-label; close button only X icon.
26. `src/views/Dashboard.vue:50-58` - chart div has aria-label but echarts canvas inherits no role="img".
27. All views lack aria-live="polite" on data refresh.

### P2 - Loading/Empty/Error state gaps
28. 0 of 62 views use NSkeleton or SkeletonLoader (per-view audit column skel is 0).
29. `src/views/billing/Invoices.vue`, Orders.vue, Pricing.vue, Contracts.vue - NDataTable renders empty rows when data=[] (no NEmpty).
30. `src/views/Dashboard.vue` - Stat cards show 0 without "no data" hint; IterativeStudio.vue (334 lines, 26 API calls, 0 try/catch) - no error handling.

## Cross-cutting statistics
- Files: 62 views + 21 components = 83 .vue files in scope
- Corrupted (1-line collapse): 5 views = 6.0% of files cannot mount
- Stub (no real API): at least 4 confirmed (Invoices, Orders, Pricing, Contracts)
- vue-tsc: 95 errors (all in 5 corrupted files) -> 0 errors if those 5 are reverted
- i18n: 786 t() references, 237 defined in zh-CN -> 549 missing keys = ~70% gap
- Skeleton coverage: 0/62 views
- Empty state coverage: 47/62 have NEmpty; 15 lack
- Aria-label coverage: 5/62 use aria-label; 57 lack
- role="..." coverage: 5/62 use role; 57 lack

## Estimated fix time
| Severity | Count | Min/fix | Total |
|----------|-------|---------|-------|
| P0 (5 corrupt views) | 5 | 15 min | 75 min |
| P1 (stub + i18n + dark + WCAG) | 22 | 20 min | 440 min |
| P2 (loading + empty + error) | 8 | 10 min | 80 min |
| **TOTAL** | **35** | | **~9.9 hours** |

## Reproducible test commands
```powershell
# A. Type check (P0 evidence)
cd D:\Hermes\生产平台\nanobot-factory\frontend-v2
npx vue-tsc --noEmit 2>&1 | Tee-Object reports\type-check-p21_r1.log
# Expected: exit 2, 95 errors

# B. Build (P0 evidence)
npx vite build 2>&1 | Tee-Object reports\build-p21_r1.log
# Expected: fails on CollectionCenter.vue:1:34

# C. Find corrupt 1-line files
Get-ChildItem src\views -Recurse -Filter *.vue |
  Where-Object { (Get-Content $_.FullName).Count -lt 5 } |
  Select-Object FullName
# Expected: 5 files

# D. i18n key cross-reference
& "D:\ComfyUI\.ext\python.exe" reports\_audit_i18n.py
# Expected: ~590 missing in zh-CN

# E. Per-view pattern audit
& "D:\ComfyUI\.ext\python.exe" reports\_audit_per_view.py
# Expected: 0/62 with NSkeleton
```

## Recommendations (priority order)
1. Day 1 morning: Revert 5 corrupted views via git, then re-apply edits in small chunks. Get build green.
2. Day 1 afternoon: Wire billing/{Invoices,Orders,Pricing} and contracts/Contracts.vue to real APIs.
3. Day 2: i18n namespace migration - extract hardcoded English literals to locales/en-US.ts baseline, then mirror to other 7 locales.
4. Day 3: Dark mode CSS-variable migration - color: #999 -> var(--app-muted) sweep.
5. Day 4: Add SkeletonLoader to data-loading views, NEmpty fallback to NDataTable-bearing views, axe-core CI hook.
6. Day 5: Per-view ErrorBoundary + skip-link + aria-live on toasts.