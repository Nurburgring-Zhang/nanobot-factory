"""Modifications content: router, layout, reports."""

ROUTER_ADDITION = """      // ===== P19 v5.6 - V5 Chapter 38 Infinite Canvas + Chapter 1.3 Command Center =====
      {
        path: 'canvas',
        name: 'infinite-canvas',
        component: () => import('@/components/InfiniteCanvas.vue'),
        meta: { title: 'Infinite Canvas', icon: 'canvas-outline', requiresAuth: true }
      },
      {
        path: 'command',
        name: 'command-center',
        component: () => import('@/components/CommandCenter.vue'),
        meta: { title: 'Command Center', icon: 'chatbubbles-outline', requiresAuth: true }
      },
"""

LAYOUT_ADDITION = """// === P19 v5.6 - V5 核心 UI ===
const v5CoreUiSubmenu: MenuOption = {
  type: 'group',
  label: () => h('span', null, { default: () => 'V5 Core UI' }),
  key: 'v5core',
  children: [
    { label: () => h(RouterLink, { to: '/canvas' }, () => 'Infinite Canvas'), key: 'infinite-canvas', icon: () => h('span', { class: 'menu-icon' }, 'C') },
    { label: () => h(RouterLink, { to: '/command' }, () => 'Command Center'), key: 'command-center', icon: () => h('span', { class: 'menu-icon' }, 'M') }
  ]
}
menuOptions.push(v5CoreUiSubmenu)
"""

REPORT_MD = """# P19 v5.6 — Infinite Canvas + Conversation Command Center

## Summary
Delivered V5 chapter 38 (Infinite Canvas) and V5 chapter 1.3 (Conversation
Command Center) as production-ready Vue 3 components on the existing
frontend-v2 stack, plus a Pinia store, 17 vitest tests, two new routes
(`/canvas`, `/command`) and a sidebar sub-menu. SVG-based infinite canvas
supports drag-to-move, 2-click connect, mouse wheel zoom (ctrl+wheel),
middle-click pan, debounced localStorage persistence (500 ms) and
keyboard shortcuts. Chat panel renders user / agent / system / plan
messages with auto-scroll, plan cards with per-task progress bars.

## Files created
- `frontend-v2/src/components/InfiniteCanvas.vue` (~300 LOC)
- `frontend-v2/src/components/CommandCenter.vue` (~190 LOC)
- `frontend-v2/src/stores/command.ts` (~210 LOC)
- `frontend-v2/src/stores/index.ts` (barrel, ~13 LOC)
- `frontend-v2/src/components/__tests__/InfiniteCanvas.spec.ts` (10 tests)
- `frontend-v2/src/components/__tests__/CommandCenter.spec.ts` (7 tests)

## Files modified
- `frontend-v2/src/router/index.ts` — 2 new routes (`canvas`, `command`)
- `frontend-v2/src/layouts/DefaultLayout.vue` — "V5 Core UI" sub-menu
  (NOTE: the task instructions said "modify App.vue", but the SPA's
  sidebar nav lives in `DefaultLayout.vue`; App.vue only configures
  global providers. The equivalent change is in DefaultLayout.vue so
  the new routes are reachable from the navigation chrome.)
- `frontend-v2/vite.config.ts` — vitest `include` widened to pick up
  `src/**/*.spec.ts` (so the task test command works)

## Test counts
- InfiniteCanvas.spec.ts — 10 tests (>=8 required):
  1. renders empty canvas with placeholder
  2. exposes palette button for each of 4 node types
  3. addNode adds + selects
  4. moveNode updates position
  5. connectNodes creates edge + idempotency
  6. connectNodes refuses self-loop
  7. deleteNode removes node + cascading edges
  8. zoom via ctrl+mousewheel updates label
  9. pan via middle-click drag changes viewport
  10. localStorage round-trip persistence
- CommandCenter.spec.ts — 7 tests (>=6 required):
  1. renders empty chat with placeholder
  2. submit creates user + plan + execution plan
  3. scroll-to-bottom on new message
  4. updatePlanProgress clamps to [0, 1]
  5. markTaskRunning / markTaskDone bookkeeping
  6. clear empties messages + plan
  7. empty / whitespace-only submit is ignored

## Example end-to-end scenario
User opens the app, navigates to `/canvas` from the new sidebar submenu,
drags 3 `asset` + 1 `capability` + 1 `agent` node from the palette.
After toggling the `C` connect button they click `asset-1` then
`capability`, then click `capability` again then `agent` — two
arrow-headed edges connect them visually. They reload the page; the
same 5 nodes + 2 edges restore verbatim from
`localStorage['vdp-canvas.state.v1']`. They then visit `/command`,
type "annotate 100 images, then score them", press Enter. A user
message, then a plan card with `asset-loader -> annotation-agent ->
scoring-agent -> aggregator` per-task progress bars (animating 0 -> 1
via `executePlan()` 80 ms per step), and a final "task completed"
system message all appear in the same `messages` array on
`useCommandStore`. The store itself persists `messages` to
`localStorage['vdp-command.messages.v1']` on every append.

## Verification
- Tests: `cd frontend-v2 && npx vitest run src/components/__tests__/InfiniteCanvas.spec.ts src/components/__tests__/CommandCenter.spec.ts --reporter=verbose`
- Type-check: `cd frontend-v2 && npx vue-tsc --noEmit`
- Build: `cd frontend-v2 && npx vite build`
"""

DELIVERABLE_MD = """# Deliverable — P19 v5.6 Infinite Canvas + Command Center

## Summary
Shipped V5 chapter 38 (Infinite Canvas / tldraw-style) and V5 chapter
1.3 (Conversation Command Center) as Vue 3 components on the existing
frontend-v2 stack, plus a Pinia store, 17 vitest unit tests, two new
routes (`/canvas`, `/command`), a sidebar submenu, and vitest include
update. SVG drag/connect/zoom/pan with debounced localStorage
persistence. Chat panel with intent parsing, structured plan cards
with per-task progress bars, and Pinia-backed message history that
persists to localStorage.

## Changed files
### Created
- `frontend-v2/src/components/InfiniteCanvas.vue` — SVG infinite canvas
- `frontend-v2/src/components/CommandCenter.vue` — chat panel
- `frontend-v2/src/stores/command.ts` — Pinia store (`useCommandStore`)
- `frontend-v2/src/stores/index.ts` — barrel export (was missing — created)
- `frontend-v2/src/components/__tests__/InfiniteCanvas.spec.ts` — 10 tests
- `frontend-v2/src/components/__tests__/CommandCenter.spec.ts` — 7 tests
- `reports/p19_v56_canvas_command.md` — design + LOC + e2e example

### Modified
- `frontend-v2/src/router/index.ts` — 2 routes under DefaultLayout
- `frontend-v2/src/layouts/DefaultLayout.vue` — "V5 Core UI" submenu
  (NOTE: task instructions say "App.vue" but the SPA's sidebar lives
  in DefaultLayout.vue; App.vue only configures global providers. The
  equivalent reachable nav is in DefaultLayout.)
- `frontend-v2/vite.config.ts` — vitest `include` widened to
  `['tests/**/*.spec.ts', 'src/**/*.spec.ts']` (existing
  `tests/components/*.spec.ts` continue to work)

## Notes
- All Vue components use `<script setup lang="ts">`.
- No new npm dependencies — uses only Vue 3, Pinia, Naive UI CSS
  variables (`--app-primary`, `--app-border`, etc.).
- `InfiniteCanvas` exposes its mutators (`addNode`, `moveNode`,
  `connectNodes`, `deleteNode`, `toggleConnectMode`, etc.) via
  `defineExpose` so vitest specs can drive the component
  deterministically without simulating complex mouse coordinates.
- `useCommandStore.submitRequest()` calls a local keyword-based
  intent parser; the real backend route (`/api/v1/agent/parse_intent`)
  is not yet implemented end-to-end, so the surface stays identical
  for a one-line swap later.
- localStorage debounce = 500 ms (per spec); uses a configurable
  `storageKey` prop so multiple canvases can co-exist.
- `__tests__` directory at `src/components/__tests__/` is new; vitest
  `include` widened to pick it up. Existing tests continue to work.
- Pre-existing `frontend-v2/src/stores/command.ts` + `index.ts` from
  prior partial attempt were preserved (no work duplicated).
- Verify command: `cd frontend-v2 && npx vitest run
  src/components/__tests__/InfiniteCanvas.spec.ts
  src/components/__tests__/CommandCenter.spec.ts --reporter=verbose`
"""