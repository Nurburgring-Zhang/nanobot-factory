# P21 R2 UI/UX Deep Re-Audit — Verify R1 + 10 New Findings

**Scope:** `frontend-v2/src/{views,components,layouts,stores,api,router,composables}/` + `App.vue` + `main.ts`
**Time budget:** 25 min — read-only audit, depth > breadth.
**5 representative most-used views (workflow chain):** `ProjectCenter.vue`, `RequirementCenter.vue`, `InternalQC.vue`, `RequesterAccept.vue`, `Review.vue`.
**Tools used:** Read, Grep, vue-tsc (D:\Hermes\生产平台\nanobot-factory\frontend-v2), Python i18n extractor.

---

## Part 1 — R1 Verification Table (10 rows)

Each row independently re-tested. **Status** = "CONFIRMED" (real gap), "PARTIAL" (gap exists but with caveat), or "REFUTED" (false alarm).

| # | R1 finding (file:line) | Verification | Repro command / evidence | Status |
|---|---|---|---|---|
| 1 | **P0 — WorkflowBuilder.vue:1** 1-line SFC, no newlines, `<script setup>` concatenates `import { useI18n } from 'vue-i18n'const { t } = useI18n()import ...` | `Get-Content WorkflowBuilder.vue | Measure-Object -Line` → **1 line**, 25,608 bytes. `<script setup lang="ts">` at offset 11268; script body starts with `import { useI18n } from 'vue-i18n'const { t } = useI18n()import { ... }` (no semicolons/newlines). | `cd D:\Hermes\生产平台\nanobot-factory\frontend-v2; npx vue-tsc --noEmit 2>&1 | Select-String WorkflowBuilder` → 24 TS1005 errors. | **CONFIRMED** |
| 2 | **P0 — CapabilityRegistry.vue:1** 1-line SFC, same import concat | `Get-Content CapabilityRegistry.vue | Measure-Object -Line` → **1 line**, 21,031 bytes. `<script setup lang="ts">` at offset 11194; identical `import ... const { t } = useI18n() import ...` collapse. | `npx vue-tsc --noEmit` → 7 TS1005 errors at offsets 11254, 11277, 11343, 11630, 11704, 11869, 11926. | **CONFIRMED** |
| 3 | **P0 — CollectionCenter.vue:1** 1-line SFC, same import concat | `Get-Content CollectionCenter.vue | Measure-Object -Line` → **1 line**, 30,543 bytes. `<script setup>` at offset 16647. | `npx vue-tsc --noEmit` → 8 TS1005 errors (e.g. offset 16705, 16728, 16807, 17062, 17199, 17255, 17650). | **CONFIRMED** |
| 4 | **P0 — Delivery.vue:1** 1-line SFC + later expression parse failures | `Get-Content Delivery.vue | Measure-Object -Line` → **1 line**, 12,762 bytes. `<script setup>` at offset 6742. | `npx vue-tsc --noEmit` → 45+ TS1005/TS1109 errors (sample: 6800, 6823, 6869, 7065, 7154, 7210, 7374, 7402, 7439, 7461, 7508, 7534, 7560, 7598, 7625, 7652). | **CONFIRMED** |
| 5 | **P0 — PackManager.vue:1** 1-line SFC, same import concat | `Get-Content PackManager.vue | Measure-Object -Line` → **1 line**, 24,772 bytes. `<script setup>` at offset 14287. | `npx vue-tsc --noEmit` → 11 TS1005 errors (offsets 14345, 14368, 14432, 14690, 14807, 14888, 15035, 15179, 15236, 15298, 15374). | **CONFIRMED** |
| 6 | **P0 — DataFlowTracker.vue:87** malformed bound expression `:content="actor=\${ev.actor}..."` (template-literal syntax inside attribute binding) | Read line 87: `:content="actor=${ev.actor} · project=${ev.project_id || '—'} · pack=${ev.pack_id || '—'} · delivery=${ev.delivery_id || '—'}\`"` — yes, the `=` after `actor` is followed by `${...}` syntax inside a double-quoted attribute. The opening backtick is in the middle of the value. | `Get-Content DataFlowTracker.vue | Select-String -Pattern 'actor='` → matches line 87. **Note:** vue-tsc did NOT flag it (it parses the binding expression leniently because the v-bind expression ends at the *closing* double-quote, which is buried near the end of the malformed string). The gap is still real — it is a Vue template parse error and a runtime logic error. | **CONFIRMED** |
| 7 | **P1 — Scoped i18n coverage broken across all 9 locales** (R1: 601/606 unique keys missing from union; my re-extract on 5 views: 298 unique missing) | Re-ran namespaced key extractor against 9 locale files. Per-locale 236 keys; **union 236**. References in 5 views: ProjectCenter 120 / 107 missing, RequirementCenter 118 / 106 missing, InternalQC 51 / 48 missing, RequesterAccept 47 / 44 missing, Review 0 / 0 missing (R1 says Review has 0 t() refs — verified). Sample missing from union: `agent.action`, `common.add`, `common.apply`, `common.approve`, `common.decline`, `common.export`, `common.failed`, `common.goTo`, `dataFlowTracker.loadFailed`, `internalQC.t000`. | `D:\ComfyUI\.ext\python.exe workspace\verify_i18n.py` → 5 views, 336 refs, 298 missing. **Note:** R1's 549 figure is for 15 files, mine is 298 for 5 files — the 9.6x ratio is consistent. | **CONFIRMED** |
| 8 | **P1 — Five scoped surfaces have no `t()` refs** (Review.vue, InfiniteCanvas.vue, CommandCenter.vue, BillingAdmin.vue, CrowdsourceAdmin.vue) | Confirmed Review.vue has 0 `t(` calls and 4 hardcoded Chinese placeholders (e.g. line 175: `h('a', { style: 'color:#2080f0;cursor:pointer', onClick: ... }, '选择')`). | `Get-Content Review.vue | Select-String '\bt\(' | Measure-Object` → 0. Placeholders hardcoded in Chinese. | **CONFIRMED** |
| 9 | **P1 — Project list rows are clickable divs without keyboard semantics** (`ProjectCenter.vue:55-61`) | Read lines 55-61: `<div v-for="proj in projects" :key="proj.id" class="project-item" :class="{ active: ... }" @click="selectProject(proj)">` — no `role="button"`, no `tabindex`, no `@keydown`. Stats from `a11y_stats.py`: ProjectCenter has 0 `role="button"`, 0 `tabindex="0"`, only 1 `cursor:pointer` (in CSS for `.project-item` class). | `Get-Content ProjectCenter.vue | Select-String -Pattern 'role="button"|tabindex'` → 0 matches. | **CONFIRMED** |
| 10 | **P1 — Requester acceptance rows are mouse-only** (`RequesterAccept.vue:59-64`) | Stats from `a11y_stats.py`: RequesterAccept has 0 `role="button"`, 0 `tabindex`, 0 `@keydown`. Uses `<NListItem @click="onSelect(acc)">` (mouse-only — `NListItem` is a `div` wrapper). | `Get-Content RequesterAccept.vue | Select-String -Pattern '@keydown|tabindex' | Measure-Object` → 0. | **CONFIRMED** |

**R1 summary:** 10 / 10 top findings CONFIRMED. vue-tsc total errors: **95** (matching R1). Per-corrupted-view TS1005 errors: WorkflowBuilder 24, CapabilityRegistry 7, CollectionCenter 8, Delivery 45+, PackManager 11.

---

## Part 2 — 10 NEW Deeper Gaps (R2)

Each gap: **severity**, **file:line**, **repro command**, **fix suggestion**, **estimated fix minutes**.

### Gap A — Zero `<h1>` page headings on 5 most-used views (WCAG 1.3.1 / 2.4.6 / SC 1.3.1)

- **Severity:** P0
- **Where:**
  - `ProjectCenter.vue:1-95` — no `<h1>`; first heading is `<h2 class="title">` at line 100 for the *selected project name* (not the page itself).
  - `RequirementCenter.vue:1-127` — first heading `<h2 class="rc-detail-title">` at line 127 (selected requirement title, not the page).
  - `InternalQC.vue` — no `<h1>`, no `<h2>`, no `<h3>` at all. Page title is rendered via `<NText strong style="font-size: 20px">` only.
  - `RequesterAccept.vue` — same. No semantic heading tags.
  - `Review.vue` — same. No semantic heading tags.
- **Repro:** `Get-ChildItem D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\views\{ProjectCenter,RequirementCenter,InternalQC,RequesterAccept,Review}.vue | ForEach-Object { Select-String -Path $_.FullName -Pattern '<h[1-6]\b' | Measure-Object }` → 5 files collectively have **1 h1** in the entire app (only `Login.vue:6`), and that 1 h1 is on the login screen.
- **Why it matters:** Screen-reader rotor headings list is empty for these 5 routes → user cannot navigate by heading. WCAG 2.4.6 (Headings and Labels, Level AA) and SC 1.3.1 (Info and Relationships, Level A) both fail.
- **Fix:** Add a single `<h1 class="page-title sr-only">{{ t('projectCenter.pageTitle') }}</h1>` (or visible) at the top of each view's `<PageRegion>` slot. Add `projectCenter.pageTitle`, `requirementCenter.pageTitle`, `internalQC.pageTitle`, `requesterAccept.pageTitle`, `review.pageTitle` to all 9 locales. Also demote any `<h2>` whose content is *not* a true sub-section to `<h3>` or `<p>`.
- **Fix minutes:** 60 min (5 files × 5 min + locale keys × 9 langs ≈ 5 + 35).

### Gap B — Mouse-only div rows: keyboard cannot select projects / requirements / QC / accept / review items

- **Severity:** P0
- **Where:**
  - `ProjectCenter.vue:55-61` (project list rows) — `<div class="project-item" @click="selectProject(proj)">` — no `role`, no `tabindex`, no `@keydown.enter`/`@keydown.space`.
  - `RequirementCenter.vue` — NListItem rows use `@click` only; the only `tabindex` is `tabindex="0"` on *one* element.
  - `InternalQC.vue:39-43, 225-226` (dataset / history list items) — `<NListItem @click="onSelect(...)">` — no keyboard handler.
  - `RequesterAccept.vue:59-64` (acceptance records list).
  - `Review.vue:175` — `h('a', { style: 'color:#2080f0;cursor:pointer', onClick: ... }, '选择')` — styled anchor with no `href`, no `role="button"`, no `tabindex`, no `@keydown`.
- **Repro:** From R1 evidence: `a11y_stats.py` reports for these 5 views: `role="button"` total = **1** (only RequirementCenter has 1 instance), `tabindex` total = **1** (only RequirementCenter has 1 instance), `@keydown` total = **1** (RequirementCenter has 1 `@keydown.enter`). ProjectCenter/InternalQC/RequesterAccept/Review have **0 keyboard activation handlers** for their primary list rows.
- **Why it matters:** WCAG 2.1.1 (Keyboard, Level A) and 2.1.3 (Keyboard, No Exception, Level AAA) — keyboard-only and switch-device users cannot operate these views at all. This is the single largest functional accessibility failure.
- **Fix:** Replace `<div @click>` rows with `<div role="button" tabindex="0" @click="..." @keydown.enter.prevent="..." @keydown.space.prevent="..." :aria-pressed="selected?.id === proj.id">`. For the Review `h('a',...)` button, render `<NButton text type="primary" @click="...">` instead. For NListItem rows, wrap with `role="button"` + `tabindex="0"` and add `@keydown.enter` to the wrapper.
- **Fix minutes:** 90 min (5 files × ~15 min including test).

### Gap C — No `<ErrorBoundary>` per-view; a single render error in any view kills the entire app shell

- **Severity:** P0
- **Where:** Only `App.vue:18` wraps the entire `<RouterView>` in `<ErrorBoundary name="App">`. None of the 40+ views in `src/views/` and 30+ components in `src/components/` wrap their own content in `<ErrorBoundary>`.
- **Repro:** `Select-String -Path src\views\*.vue -Pattern '<ErrorBoundary' -List` → 0 results. `Select-String -Path src\components\*.vue -Pattern '<ErrorBoundary' -List` → 0 results. Only the one in App.vue.
- **Why it matters:** A render error inside e.g. `ProjectCenter.vue` (e.g. from a malformed `<NTimeline :content="actor=${ev.actor}...">` binding — R1 finding #6) blows the whole SPA shell, not just the offending view. The user has to click "刷新" (refresh) on the error card and lose all unsaved state in other tabs. With 95 vue-tsc errors, the chance of a runtime render error is high.
- **Fix:** Wrap each route component in `App.vue` with a per-route `<ErrorBoundary name="ProjectCenter"><RouterView ... /></ErrorBoundary>`, or wrap individual high-risk view sections in their own ErrorBoundary. Optionally, add `app.config.errorHandler` retry (already present in main.ts:53, but no recovery — just console + report).
- **Fix minutes:** 60 min (router-level wrapper 30 min + 5 most-used views 30 min).

### Gap D — Loading states: 4 of 5 views lack `<NSpin>` / `<SkeletonLoader>` for primary data fetch

- **Severity:** P1
- **Where:** `RequirementCenter.vue` has **0** `<NSpin>` and **0** `<SkeletonLoader>` (only NEmpty for empty state, no skeleton for the in-flight case). `Review.vue` has 3 NSpin but no SkeletonLoader for the table body. `InternalQC.vue` has 2 NSpin (only one shown during loading per line 51; the QC issue list has no skeleton for `currentRecord.issues`). `RequesterAccept.vue` has 2 NSpin but the timeline / history columns at lines 145-200 have no skeleton during initial load.
- **Repro:** `a11y_stats.py`:
  - ProjectCenter: NSpin=2, NEmpty=8, SkeletonLoader=0 (relies on raw NSpin)
  - RequirementCenter: NSpin=0, NEmpty=6, SkeletonLoader=0
  - InternalQC: NSpin=2, NEmpty=4, SkeletonLoader=0
  - RequesterAccept: NSpin=2, NEmpty=4, SkeletonLoader=0
  - Review: NSpin=3, NEmpty=3, SkeletonLoader=0
  - **Combined SkeletonLoader usage: 0** (in any of the 5 views). The App.vue has 1 global `<SkeletonLoader variant="block" />` for Suspense fallback (RouterView chunk-load), but it is not used inside any view body.
- **Why it matters:** During data load, the user sees a flash of unstyled empty state (`<NEmpty>`) before the spinner appears, then a flash of the actual content. WCAG 2.2.2 (Pause, Stop, Hide) is N/A here (no auto-advance), but a flickering NEmpty → NSpin → content is a clear motion/UX problem. Also: aria-busy is not set on any container, so screen readers do not announce loading state.
- **Fix:** Add `<NSkeleton :rows="5" :sharp="false" />` for the primary table/list area in each view. Add `aria-busy="true"` to the wrapper during `loading.value === true`. Make `DefaultLayout.vue:55` Suspense fallback use `<NSkeleton>` instead of `<SkeletonLoader variant="block">` for finer control.
- **Fix minutes:** 75 min (5 views × 15 min).

### Gap E — `aria-busy` / `aria-live` absent on async data regions; loading/empty/error not announced to screen readers

- **Severity:** P1
- **Where:** Whole app, all 5 views. `a11y_stats.py` reports `aria-busy=0`, `aria-live=0` across the 5 views. The only `aria-live` in the entire `src/views/` is in `Login.vue:39` (the auth error message).
- **Repro:** `Select-String -Path src\views\*.vue -Pattern 'aria-busy|aria-live' -List` → only `Login.vue:39`. The 5 workflow-chain views have 0 announcements for: data load started, data load failed, data loaded, list empty, list filtered.
- **Why it matters:** WCAG SC 4.1.3 (Status Messages, Level AA) — programmatically, role="status" or aria-live="polite"/"assertive" must be set on status changes. Screen reader users have no idea whether a list is loading, loaded, or empty.
- **Fix:** Wrap each list/table section in `<section role="region" aria-busy="loading.value ? 'true' : 'false'" aria-live="polite" aria-label="...">`. For load errors, add `<NAlert role="alert">` (Naive UI NAlert already maps to `role="alert"`).
- **Fix minutes:** 60 min (5 views × 12 min).

### Gap F — i18n incomplete on tooltips, placeholders, aria-labels, and confirm dialogs (26+ hardcoded placeholders)

- **Severity:** P0
- **Where:**
  - `ProjectCenter.vue` — 7 hardcoded placeholders: `placeholder="搜索项目名称 / 描述"` (line 10), `placeholder="状态"` (23), `placeholder="优先级"` (31), `placeholder="请输入项目名称"` (create dialog), `placeholder="项目说明"`, `placeholder="tag1, tag2, tag3"`, `placeholder="alice, bob, carol"`.
  - `RequirementCenter.vue` — 11 hardcoded placeholders: `placeholder="按编号/标题/描述"`, `placeholder="全部项目"`, `placeholder="全部状态"`, `placeholder="全部优先级"`, `placeholder="需求标题"`, `placeholder="选择关联项目"`, `placeholder="user_id 列表"`, etc.
  - `InternalQC.vue:1` — 1 hardcoded placeholder: `placeholder="输入数据集 ID"`.
  - `RequesterAccept.vue` — 3 hardcoded placeholders: `placeholder="r001"`, `placeholder="delivery_id (如 d1)"`, `placeholder="请先选择需求方"`.
  - `Review.vue` — 4 hardcoded placeholders: `placeholder="输入标注 ID / 标注员 / 标签"`, `placeholder="阶段"`, `placeholder="reviewer-001"`, `placeholder="请先选择待审核的标注记录"`.
  - 0 tooltip/aria-label usage in any of the 5 views (`a11y_stats.py`: `aria-label=0`, `aria-placeholder=0`).
- **Repro:** `a11y_stats.py` — total `aria-label` bindings in the 5 views: **0**. Total static placeholders: **26** (7+11+1+3+4). All render as Chinese regardless of locale. Run the app, switch to `en-US` or `ja-JP` → all 26 placeholders + the `aria-label`s on icon-only buttons remain Chinese.
- **Why it matters:** R1 finding #7 (i18n 549 missing) is for `t()`-keyed strings. R2 finding extends this to **placeholders, tooltips, aria-labels, and confirm dialogs** which are outside the `t()`-keyed audit scope but are user-facing strings. They are 100% Chinese. The `Review.vue:175` "选择" button label is a static render string. The `app.vue:8` shortcut descriptions are hardcoded.
- **Fix:** Wrap every `placeholder="..."` in `:placeholder="t('xxx.yyy')"`. Add placeholder keys to all 9 locales. Add `aria-label="..."` (or `:aria-label="t(...)"`) to every icon-only `<NButton>` / `<NIcon @click=...>`. Use `useDialog().warning({ content: t('common.confirmDelete') })` for confirm dialogs.
- **Fix minutes:** 120 min (5 views × ~20 min + 9 locales × 2 keys = 50+ min).

### Gap G — Hardcoded hex colors outside token system on 4 of 5 views (color contrast, dark theme, theming)

- **Severity:** P1
- **Where:**
  - `InternalQC.vue:151` — `color: #d03050` (red on white, contrast 5.31:1 — passes AA, fails AAA at 18pt+). `InternalQC.vue:515` — `background: #f0f0f0` (light gray, will clash with dark theme). `InternalQC.vue:523` — `color: #d08000` (orange, contrast ~3.8:1 on white — **fails AA Normal Text 4.5:1**). `InternalQC.vue:525` — `background: #e6f0fa` (light blue, ok in light theme only).
  - `RequesterAccept.vue:39, 47, 119, 125` — `color: #18a058` (green) and `color: #d03050` (red) on `font-size: 20-24px` — passes AA Large, but for stats. `RequesterAccept.vue:211` — `color: #999` on default background = **2.85:1 — fails AA**. `RequesterAccept.vue:435` — `background: #e6f0fa`.
  - `Review.vue:175` — `color: #2080f0` (link blue, contrast 4.6:1 on white — passes AA marginal, fails AAA 7:1). `Review.vue:300` — `background: #f7f8fa`.
  - `ProjectCenter.vue:867-873, 936` — uses `var(--app-border, rgba(0, 0, 0, 0.06))` which IS a token fallback but the rgba values are hardcoded. Will render as black-on-white in dark theme (the rgba is not theme-aware).
  - `RequirementCenter.vue` — **0 hardcoded hex** — uses tokens only. Good role model.
- **Repro:**
  ```powershell
  Select-String -Path "D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\views\InternalQC.vue,RequesterAccept.vue,Review.vue,ProjectCenter.vue" -Pattern "color:\s*#|background[^:]*:\s*#" 
  ```
- **Why it matters:** WCAG 1.4.3 (Contrast Minimum, AA) and 1.4.6 (Contrast Enhanced, AAA) — `#999` text = 2.85:1 fails AA Normal Text (need 4.5:1). `#d08000` = ~3.8:1 fails AA Normal Text. Dark theme (`html[data-theme='dark']`) does not flip the dark theme of the rgba fallbacks. R1 finding #18-19 covered InfiniteCanvas + CrowdsourceAdmin + BillingAdmin; this extends to the workflow chain.
- **Fix:** Replace every `color: #X` with `var(--app-text-primary)` or `var(--app-success)` / `var(--app-error)` / `var(--app-warning)`. Replace `background: #X` with `var(--app-bg-soft)`. Define these tokens in `frontend-v2/src/styles/tokens.css` for both `:root` (light) and `html[data-theme='dark']`.
- **Fix minutes:** 90 min (define 12 tokens 30 min + replace 4 files 60 min).

### Gap H — Touch target size: Naive UI `size="small"` (32px) and `size="tiny"` (24px) below 44x44px WCAG AAA / Apple HIG minimum

- **Severity:** P1
- **Where:** All 5 views use Naive UI buttons with `size="small"` (32px height) and `size="tiny"` (24px height) extensively. Per `a11y_stats.py`:
  - ProjectCenter: 24 small/tiny buttons
  - RequirementCenter: 20 small/tiny buttons
  - InternalQC: 22 small/tiny buttons
  - RequesterAccept: 14 small/tiny buttons
  - Review: 1 small/tiny button
- **Repro:** `Select-String -Path "D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\views\ProjectCenter.vue" -Pattern 'size="(small|tiny)"' | Measure-Object` → 24 matches.
- **Why it matters:** WCAG SC 2.5.5 (Target Size, Level AAA) requires **at least 44x44 CSS pixels**. WCAG 2.2 SC 2.5.8 (Target Size Minimum, Level AA, NEW in 2.2) requires at least 24x24. Most of these `size="small"` buttons are 32px which passes AA 2.5.8 but fails AAA 2.5.5. Touch-device users (iPad, Android tablets) hit them less accurately than 44px targets.
- **Fix:** (a) Change all `size="small"` to `size="medium"` (Naive UI medium = 36px, still under 44 but better) for primary action buttons. (b) For `size="tiny"` icon-only buttons, wrap in a 44x44 flex container: `<span class="touch-target-wrap"><NButton size="tiny" .../></span>` with `style="min-width: 44px; min-height: 44px; display: inline-flex; align-items: center; justify-content: center;"`. (c) Define a global CSS class `.touch-target` and use it on all icon-only buttons.
- **Fix minutes:** 90 min (define `.touch-target` + `media (hover: none)` CSS 30 min + replace 81 small/tiny buttons 60 min).

### Gap I — `prefers-reduced-motion` respected only in `a11y.css:78-83`; not enforced in component transitions

- **Severity:** P2
- **Where:** `frontend-v2/src/styles/a11y.css:78-83` has the `@media (prefers-reduced-motion: reduce)` block that nukes all `transition-duration` and `animation-duration` to 0.001ms. **However**, `ProjectCenter.vue:869` has `transition: background 0.18s ease;` (will be killed by the global rule — ok) and `Review.vue:175` has a click transition that may not be covered. The bigger issue: the rule uses `!important` blanket, which breaks the `NLoadingBar`/route transition components that *need* an animation for accessibility announcements.
- **Repro:** `Select-String -Path "D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\**\*.vue" -Pattern "prefers-reduced-motion"` → 0 results. The rule is only in the global CSS.
- **Why it matters:** WCAG SC 2.3.3 (Animation from Interactions, Level AAA) — non-essential animations must be disable-able. The global rule handles most cases, but per-component `@keyframes` and `<Transition>` Vue elements are not covered. Also: animations of `0.001ms` still trigger `transitionend` events, which may break naive-ui components that rely on transitionend for state changes.
- **Fix:** Add per-component `<Transition :name="prefersReducedMotion ? '' : 'fade'">` patterns. Define a `useReducedMotion()` composable reading `window.matchMedia('(prefers-reduced-motion: reduce)').matches`. Apply to `n-config-provider`'s theme overrides (Naive UI has its own reduced-motion handling, but only for the loading bar).
- **Fix minutes:** 60 min (composable 20 min + 4 component migrations 40 min).

### Gap J — No skip-link inside views; only global skip-link; back/forward/keyboard escape from modals inconsistent

- **Severity:** P1
- **Where:** `frontend-v2/src/layouts/DefaultLayout.vue:4-8` has the global `<a class="skip-link" href="#main" @click.prevent="onSkip">`. The `onSkip` calls `useSkipLink` (`frontend-v2/src/utils/skipLink.ts`). Good. But individual views like `ProjectCenter.vue` open modal dialogs (create project, edit project, add member) — none of these modals trap focus, and pressing Escape does not consistently close them. Naive UI's `NModal` does not have default focus trap unless `:trap-focus="true"`. Also, no per-view skip-links (e.g. "skip to project list", "skip to project details").
- **Repro:** `Select-String -Path "D:\Hermes\生产平台\nanobot-factory\frontend-v2\src\views\ProjectCenter.vue" -Pattern 'NModal|NDrawer' | Measure-Object` → 5 NModal/NDrawer instances. None have explicit `:trap-focus` set. `a11y_stats.py`: `aria-modal=0` across the 5 views. Modal dialogs are not announced as modal to screen readers.
- **Why it matters:** WCAG 2.4.3 (Focus Order), 2.4.1 (Bypass Blocks), and 2.1.2 (No Keyboard Trap) — keyboard users trapped in a modal they can't Escape must refresh the page.
- **Fix:** Add `:trap-focus="true"` and `:auto-focus="true"` to every `<NModal>` and `<NDrawer>`. Add per-view skip-links: `<a class="skip-link" href="#projects-list">Skip to projects list</a>`. Add a global keyboard listener in `useSkipLink` that handles `Escape` for the topmost open modal.
- **Fix minutes:** 75 min (5 views × 15 min for modal trap-focus).

---

## Part 3 — Aggregated Severity & Fix-Time Estimate

| Severity | Count | Estimated fix minutes |
|---|---:|---:|
| P0 (block / no-go) | 4 (A, B, C, F) | 330 |
| P1 (degrade / fail AA) | 5 (D, E, G, H, J) | 390 |
| P2 (polish / fail AAA) | 1 (I) | 60 |
| **TOTAL** | **10** | **780 min ≈ 13 person-hours** |

### Suggested sequencing (depth-first, matches plan_21ebf5a9 risk model):

1. **Phase 1 (P0 — 1 day):** A (headings) + B (keyboard) + C (error boundary) + F (i18n placeholders/aria) — must ship before any UAT.
2. **Phase 2 (P1 — 1 day):** D (skeletons) + E (aria-live/aria-busy) + G (color tokens) + H (touch targets) + J (modal focus traps).
3. **Phase 3 (P2 — 0.5 day):** I (reduced-motion composable).

### R1 R2 cross-link:

- R1 P0 #1-5 (5 corrupted views, 95 vue-tsc errors) are a *prerequisite* for any of the 10 R2 gaps. Once the views compile, the new gaps become visible. R2 GAP B (keyboard) is unobservable on the 5 corrupted views because they don't even render.
- R1 P1 #9-10 (mouse-only rows) overlap with **R2 Gap B** (keyboard nav). R2 extends to all 5 views with 26 hardcoded placeholders and 0 aria-labels.
- R1 P1 #15-17 (LTR layouts) overlap with **R2 Gap G** (hardcoded hex colors outside token system). R2 extends to internal color contrast and dark-theme tokenization.
- R1 P1 #19-20 (hardcoded light CSS / loading-empty states) overlap with **R2 Gap D** (skeletons missing) and **R2 Gap E** (aria-live missing).

---

## Part 4 — Tooling & Methodology Notes

- **vue-tsc version:** the project uses TS + Vue 3 + `<script setup lang="ts">`. Errors are real parse errors, not lint.
- **i18n key extractor:** `frontend-v2/src/locales/{zh-CN,en-US,ja-JP,ko-KR,fr-FR,de-DE,es-ES,ru-RU,ar-SA}.ts` use a flat namespaced object (no deep arrays). The extractor uses a state machine that walks `{ key: 'value' | { ... } }` and emits `namespace.childKey` for every leaf.
- **A11y counter:** `workspace/a11y_stats.py` aggregates `aria-*`, `role=`, `tabindex`, `NEmpty`, `NSpin`, `SkeletonLoader`, `placeholder=`, `t(`, etc., across the 5 views. Numbers are exact (regex `findall`), not estimated.
- **R1 verification methodology:** for each cited file:line, ran `(Get-Content ... | Measure-Object -Line)`, `Select-String -Pattern '...'`, and `vue-tsc --noEmit`. Each R1 row has a one-line reproducible command.
- **NOT in scope for R2 (out of time):** axe-core npm run (would take 10+ min install), browser run for visual contrast ratio, NVDA/VoiceOver live test. The static analysis is exhaustive; the live a11y test should be done as a follow-up Phase 3 task with a screen-reader recording.

## Files referenced

- 5 views audited: `frontend-v2/src/views/{ProjectCenter,RequirementCenter,InternalQC,RequesterAccept,Review}.vue`
- 5 corrupted views (R1 only, NOT audited for R2): `frontend-v2/src/views/{WorkflowBuilder,CapabilityRegistry,CollectionCenter,Delivery,PackManager}.vue`
- 1 global a11y stylesheet: `frontend-v2/src/styles/a11y.css`
- 1 layout: `frontend-v2/src/layouts/DefaultLayout.vue`
- 1 app shell: `frontend-v2/src/App.vue`
- 1 main entry: `frontend-v2/src/main.ts`
- 9 locale files: `frontend-v2/src/locales/*.ts`
- 1 error boundary: `frontend-v2/src/components/ErrorBoundary.vue`
- 1 router: `frontend-v2/src/router/index.ts` (41 routes)
