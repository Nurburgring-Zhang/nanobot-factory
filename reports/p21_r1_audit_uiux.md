# P21 R1 UI/UX Audit — Critical Views Only

Scope audited read-only: 16 named Vue SFCs (the 15 reduced critical views/components plus `src/App.vue`). Skipped `__tests__/`, stores, API, locales (except key coverage), layouts, router, composables, public source changes.

## Commands / evidence

- Repo: `D:\Hermes\生产平台\nanobot-factory`
- Python used for scoped key/read checks: `D:\ComfyUI\.ext\python.exe`
- Type check command run from `frontend-v2`: `npx vue-tsc --noEmit 2>&1 | Select-Object -First 200`

### vue-tsc top errors by scoped file

`vue-tsc` is currently blocked before it can report semantic UI errors. The top output is parse-level syntax errors in six scoped one-line SFCs:

| File | Top errors captured | Representative top error |
|---|---:|---|
| `frontend-v2/src/views/CapabilityRegistry.vue:1` | 7 | `TS1005 ';' expected` at `(1,11254)` |
| `frontend-v2/src/views/CollectionCenter.vue:1` | 7 | `TS1005 ';' expected` at `(1,16705)` |
| `frontend-v2/src/views/Delivery.vue:1` | 45+ | `TS1005 ';' expected` at `(1,6800)`, later `TS1109 Expression expected` |
| `frontend-v2/src/views/PackManager.vue:1` | 11 | `TS1005 ';' expected` at `(1,14345)` |
| `frontend-v2/src/views/WorkflowBuilder.vue:1` | 24 | `TS1005 ';' expected` at `(1,11326)` |

Root pattern in these files: the whole SFC is one physical line and `<script setup>` starts as `import { useI18n } from 'vue-i18n'const { t } = useI18n()import ...`, so imports and statements are concatenated without semicolons/newlines.

### Locale key coverage for scoped `$t()`/`t()` refs

Literal `t()` references extracted from the scoped files and checked against all 9 locale files (`zh-CN`, `en-US`, `ja-JP`, `ko-KR`, `fr-FR`, `de-DE`, `es-ES`, `ru-RU`, `ar-SA`):

- Total scoped literal `t()` refs: **715**
- Unique scoped keys: **606**
- Missing refs: **601**
- Unique missing keys: **546**
- Most missing keys are absent in **all 9 locales**.

| File | `t()` refs | unique keys | missing refs | unique missing |
|---|---:|---:|---:|---:|
| `src/views/WorkflowBuilder.vue` | 55 | 49 | 13 | 9 |
| `src/views/CapabilityRegistry.vue` | 47 | 45 | 40 | 38 |
| `src/views/CollectionCenter.vue` | 98 | 93 | 86 | 85 |
| `src/views/DataFlowTracker.vue` | 12 | 12 | 12 | 12 |
| `src/views/Delivery.vue` | 42 | 41 | 38 | 37 |
| `src/views/InternalQC.vue` | 53 | 51 | 50 | 48 |
| `src/views/PackManager.vue` | 88 | 85 | 81 | 81 |
| `src/views/ProjectCenter.vue` | 135 | 121 | 119 | 108 |
| `src/views/RequesterAccept.vue` | 52 | 48 | 47 | 45 |
| `src/views/RequirementCenter.vue` | 133 | 118 | 115 | 106 |
| `src/views/Review.vue` | 0 | 0 | 0 | 0 |
| `src/components/InfiniteCanvas.vue` | 0 | 0 | 0 | 0 |
| `src/components/CommandCenter.vue` | 0 | 0 | 0 | 0 |
| `src/components/BillingAdmin.vue` | 0 | 0 | 0 | 0 |
| `src/components/CrowdsourceAdmin.vue` | 0 | 0 | 0 | 0 |
| `src/App.vue` | 0 | 0 | 0 | 0 |

## Top 20 gaps (P0/P1/P2)

1. **P0 — Workflow Builder route cannot type-check/compile.** `frontend-v2/src/views/WorkflowBuilder.vue:1` has a one-line SFC where `<script setup>` imports and `const { t } = useI18n()` are concatenated; repro: run `npx vue-tsc --noEmit` and see `TS1005` at `(1,11326)` and following offsets.
2. **P0 — Capability Registry route cannot type-check/compile.** `frontend-v2/src/views/CapabilityRegistry.vue:1` has the same one-line `<script setup>` concatenation; repro: `vue-tsc` reports `TS1005` at `(1,11254)`.
3. **P0 — Collection Center route cannot type-check/compile.** `frontend-v2/src/views/CollectionCenter.vue:1` has the same one-line `<script setup>` concatenation; repro: `vue-tsc` reports `TS1005` at `(1,16705)`.
4. **P0 — Delivery route cannot type-check/compile.** `frontend-v2/src/views/Delivery.vue:1` has the same one-line `<script setup>` concatenation plus later expression parse failures; repro: `vue-tsc` reports `TS1005` at `(1,6800)` and `TS1109` later in the same line.
5. **P0 — Pack Manager route cannot type-check/compile.** `frontend-v2/src/views/PackManager.vue:1` has the same one-line `<script setup>` concatenation; repro: `vue-tsc` reports `TS1005` at `(1,14345)`.
6. **P0 — Data Flow Tracker contains a malformed bound expression.** `frontend-v2/src/views/DataFlowTracker.vue:87` uses `:content="actor=${ev.actor} ... \`"` instead of a quoted string/template literal; repro: open the timeline path after fixing earlier parse blockers or run Vue template compilation and this expression is invalid/unsafe.
7. **P1 — Scoped i18n coverage is broken across all 9 locales.** Representative refs: `frontend-v2/src/views/ProjectCenter.vue:38` (`projectCenter.t003`), `frontend-v2/src/views/RequirementCenter.vue:15` (`requirementCenter.t001`), `frontend-v2/src/views/DataFlowTracker.vue:6` (`dataFlowTracker.pageTitle`) are missing from every locale; repro: switch locale or run the extraction above and these keys render/fallback as raw keys.
8. **P1 — Five scoped surfaces have no `t()` refs and are hardcoded English/Chinese.** `frontend-v2/src/views/Review.vue:6`, `frontend-v2/src/components/InfiniteCanvas.vue:45`, `frontend-v2/src/components/CommandCenter.vue:10`, `frontend-v2/src/components/BillingAdmin.vue:4`, `frontend-v2/src/components/CrowdsourceAdmin.vue:4`; repro: switch to `ar-SA`/`ja-JP` and labels remain source-language text.
9. **P1 — Project list rows are clickable divs without keyboard semantics.** `frontend-v2/src/views/ProjectCenter.vue:55`-`61` uses `<div class="project-item" @click="selectProject(proj)">` with no `role="button"`, `tabindex`, or key handlers; repro: tab through the page and project rows are not operable by keyboard.
10. **P1 — Requester acceptance rows are mouse-only.** `frontend-v2/src/views/RequesterAccept.vue:59`-`64` uses `NListItem @click="onSelect(acc)"` without explicit keyboard activation or selected-state aria; repro: keyboard-only user cannot reliably select pending acceptance records.
11. **P1 — Internal QC dataset/history selection is mouse-only.** `frontend-v2/src/views/InternalQC.vue:39`-`43` and `frontend-v2/src/views/InternalQC.vue:225`-`226` use click handlers on list items/thing content without keyboard semantics; repro: tab to the lists and try selecting a dataset/history row without a mouse.
12. **P1 — Infinite Canvas is not accessible as an application surface.** `frontend-v2/src/components/InfiniteCanvas.vue:13`-`19` has single-letter icon buttons (`C`, `R`, `DEL`) without `aria-label`, and `role="application"` SVG without a label; repro: inspect with a screen reader/accessibility tree and controls are announced as ambiguous letters or unlabeled application.
13. **P1 — Infinite Canvas nodes are mouse-only SVG groups.** `frontend-v2/src/components/InfiniteCanvas.vue:37` binds `@mousedown`/`@click` to `<g>` nodes with no focusability/role/keyboard move/select model; repro: keyboard-only user cannot select, drag, connect, or delete nodes except after mouse selection.
14. **P1 — Review table action uses a styled anchor as a button.** `frontend-v2/src/views/Review.vue:175` renders `h('a', { style: 'color:#2080f0;cursor:pointer', onClick: ... }, '选择')` with no `href`, role, or keydown; repro: screen reader/keyboard users do not get a proper button control.
15. **P1 — Critical layouts are fixed LTR grids and do not mirror in RTL.** `frontend-v2/src/views/ProjectCenter.vue:852`-`856` hardcodes `grid-template-columns: 280px 1fr 320px` and semantic `col-left/col-right`; repro: switch to `ar-SA`, the left navigation/details/actions order remains LTR instead of mirroring.
16. **P1 — More critical views use fixed desktop-only columns.** `frontend-v2/src/views/RequirementCenter.vue:753`-`757`, `frontend-v2/src/views/InternalQC.vue:499`-`502`, and `frontend-v2/src/views/RequesterAccept.vue:425`-`428` hardcode 280/320/360px side panes with no media query; repro: at 375px/768px widths the layout overflows horizontally.
17. **P1 — Data Flow pipeline has LTR-only visual direction.** `frontend-v2/src/views/DataFlowTracker.vue:52` and `frontend-v2/src/views/DataFlowTracker.vue:183`-`187` use literal `→` and `right: -14px`; repro: in `ar-SA` pipeline direction/arrow remains left-to-right.
18. **P1 — Dark theme is bypassed by SVG/direct hex colors.** `frontend-v2/src/components/InfiniteCanvas.vue:22`, `frontend-v2/src/components/InfiniteCanvas.vue:28`, `frontend-v2/src/components/InfiniteCanvas.vue:33`, and `frontend-v2/src/components/InfiniteCanvas.vue:38`-`41` hardcode light grid/fill/text/stroke values in SVG attributes; repro: switch to dark theme and canvas nodes/text retain light-theme contrast assumptions.
19. **P1 — Several audited surfaces hardcode light-theme CSS colors outside tokens.** Examples: `frontend-v2/src/components/BillingAdmin.vue:130`, `frontend-v2/src/components/BillingAdmin.vue:141`, `frontend-v2/src/components/BillingAdmin.vue:168`, `frontend-v2/src/components/CrowdsourceAdmin.vue:220`, `frontend-v2/src/components/CrowdsourceAdmin.vue:226`, `frontend-v2/src/components/CrowdsourceAdmin.vue:239`, `frontend-v2/src/components/CrowdsourceAdmin.vue:251`, `frontend-v2/src/views/Review.vue:300`, `frontend-v2/src/views/InternalQC.vue:515`, `frontend-v2/src/views/InternalQC.vue:525`, and `frontend-v2/src/views/RequesterAccept.vue:435`; repro: switch to dark theme and these blocks remain pale backgrounds/borders or low-contrast text.
20. **P2 — Persistent loading/error/empty states are incomplete on critical data screens.** `frontend-v2/src/views/ProjectCenter.vue:489`-`492` and `frontend-v2/src/views/RequirementCenter.vue:570`-`573` collapse failures to toast + empty data, while `frontend-v2/src/components/BillingAdmin.vue:116`-`122` and `frontend-v2/src/components/CrowdsourceAdmin.vue:105`-`107` call store loaders without local error UI; repro: force API/store failure and the page has no durable retryable error panel.

## Per-surface coverage notes

| Surface | WCAG 2.1 AA | Dark theme | RTL `ar-SA` | Responsive | Notes |
|---|---|---|---|---|---|
| `WorkflowBuilder.vue` | blocked | blocked | blocked | blocked | P0 compile blocker at line 1; 13 missing i18n refs. |
| `CapabilityRegistry.vue` | blocked | blocked | blocked | blocked | P0 compile blocker at line 1; 40 missing i18n refs. |
| `CollectionCenter.vue` | blocked | blocked | blocked | blocked | P0 compile blocker at line 1; 86 missing i18n refs. |
| `DataFlowTracker.vue` | fail | partial | fail | partial | Malformed timeline content at line 87; missing 12/12 i18n keys; LTR arrow/right positioning. |
| `Delivery.vue` | blocked | blocked | blocked | blocked | P0 compile blocker at line 1; 38 missing i18n refs. |
| `InternalQC.vue` | fail | fail | fail | fail | Mouse-only list selection, fixed 3-col grid, hardcoded colors, 50 missing refs. |
| `PackManager.vue` | blocked | blocked | blocked | blocked | P0 compile blocker at line 1; 81 missing i18n refs. |
| `ProjectCenter.vue` | fail | partial | fail | fail | Mouse-only project rows, fixed LTR tri-column layout, 119 missing refs. |
| `RequesterAccept.vue` | fail | fail | fail | fail | Mouse-only rows, fixed tri-column layout, hardcoded active color, 47 missing refs. |
| `RequirementCenter.vue` | partial | partial | fail | fail | Has role/tabindex for requirement rows, but fixed LTR tri-column layout and 115 missing refs. |
| `Review.vue` | fail | fail | fail | partial | Hardcoded Chinese, styled anchor button, no i18n refs. |
| `InfiniteCanvas.vue` | fail | fail | fail | partial | Mouse-only SVG nodes, unlabeled controls/application, hardcoded SVG colors. |
| `CommandCenter.vue` | partial | partial | fail | partial | Hardcoded English copy, plan/status text not localized; dark role backgrounds use fixed colors. |
| `BillingAdmin.vue` | partial | fail | partial | partial | English-only copy, light CSS colors; grid is responsive but tables need mobile treatment. |
| `CrowdsourceAdmin.vue` | partial | fail | partial | partial | English-only copy, light CSS colors; tables/charts need RTL/mobile treatment. |
| `App.vue` | pass-ish | partial | partial | responsive shell | Has providers/ErrorBoundary/Suspense and RTL locale mapping, but shortcut descriptions/icons are hardcoded and child views still break RTL/dark. |

## Recommended fix order

1. Fix P0 compile blockers first (`WorkflowBuilder`, `CapabilityRegistry`, `CollectionCenter`, `Delivery`, `PackManager`, then `DataFlowTracker.vue:87`).
2. Add missing locale namespaces/keys in all 9 locale files, or remove/replace placeholder `tNNN` references with existing semantic keys.
3. Normalize the critical view layout primitives: keyboard-selectable rows, tokenized colors, RTL-aware logical properties, and responsive breakpoints for 3-column views.
