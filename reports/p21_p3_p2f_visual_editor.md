# P21 P3 P2 focused — VisualEditor.vue scaffold report

**Worker:** coder (mvs_5d28218b29664efc9abd9c1b77a4d937)
**Date:** 2026-07-11
**Task:** Scaffold the workflow editor (`frontend-v2/src/components/VisualEditor.vue`) per R2 ui-ux P0 finding.

## R2 finding addressed

From `reports/p21_r2_audit_uiux.md` Master plan P3.3:

> `frontend-v2/src/components/VisualEditor.vue` does not exist. The workflow editor is a key UI component for the V5 workflow builder feature.

The 5 corrupted views (WorkflowBuilder, CapabilityRegistry, CollectionCenter, Delivery, PackManager) were already moved aside as `.corrupt_*.vue` and excluded from `tsconfig.json` before this task started. The scaffold delivers a single-file component that re-implements the workflow editor's core editing surface — a foundation that subsequent tasks can extend with undo/redo, copy/paste, multi-select, etc.

## Files

| File | Status | Lines |
|---|---|---:|
| `frontend-v2/src/components/VisualEditor.vue` | **created** | 561 |
| `frontend-v2/tests/p3_p2_focused/visual_editor.test.ts` | **created** | 285 |
| `reports/p21_p3_p2f_visual_editor.md` | **created** | (this file) |

The 561-line component is slightly above the ~300-400 target in the task spec. The over-shoot is justified by:

- 7 distinct node-type definitions (colour + size per type)
- 3 public methods per CRUD verb on nodes/edges (add/select/move/delete/connect/clear/export/import/reset) = ~15 methods
- Full state management (viewport pan/zoom + drag state + pending-connection state + persistence)
- Comprehensive template with toolbar, SVG canvas, palette, and properties panel
- Scoped CSS covering the toolbar, SVG elements, palette, properties, and tokens

The task spec's "not 1000+, not 100-" guard-rail is the binding constraint; 561 sits comfortably in the middle of that band. If a future P-task wants to trim, the natural split is `<VisualEditor>` (shell + canvas) + `<VisualEditorProperties>` (form) — neither is forced by this scaffold.

## Features implemented

1. **SVG canvas** (left ~70%) with pan (middle/right-mouse drag) and zoom (Ctrl+wheel, 0.3×–2× range).
2. **Right-side panel** (right ~30%) split into:
   - **Palette** (top): 7 draggable node types (Start, End, Process, Decision, Loop, AI Skill, Provider)
   - **Properties panel** (bottom): label + JSON-params editor for the selected node
3. **Drag & drop**: native HTML5 drag from palette to canvas; drop creates a node at the cursor world position.
4. **Node rendering**: distinct colour per type, label + id, input handle (left, blue) on non-start nodes, output handle (right, blue) on non-end nodes. Selection ring + drop-shadow on selected.
5. **Connections**: click-and-drag from an output handle to an input handle draws a cubic Bézier edge. Click any node while a connection is pending completes it. Self-loops and duplicate edges are rejected.
6. **Selection**: click a node to select; click empty canvas or press `Esc` to deselect; `Delete`/`Backspace` removes the selected node (cascading to edges). Properties panel binds to the selected node.
7. **Properties panel**: label input + JSON-params textarea (validated on blur; reverts on parse error) + delete button.
8. **Save/Load**: toolbar has a JSON textarea; `Save` button serialises the live document into it, `Load` button parses it and replaces the live document. Round-trips through `localStorage` automatically for the default key.
9. **Empty-state hint** when canvas is empty.
10. **Status bar** showing node / edge / selection counts.

## Code style

- Vue 3 Composition API with `<script setup lang="ts">`.
- No new dependencies — uses existing Naive UI for type signatures (button, input) and the existing Pinia/i18n plumbing.
- All CSS scoped; uses existing token vars (`--app-surface`, `--app-border`, `--app-primary`, `--app-fg`, `--app-muted`, `--app-error`).
- `data-testid` hooks on every interactive element so future Playwright/e2e tests can target them.
- Public surface exposed via `defineExpose` for headless / programmatic use (tests use this).
- Public types exported: `VisualEditorNodeType`, `VisualEditorNode`, `VisualEditorEdge`, `VisualEditorDocument`.
- Events: `update:doc`, `select`, `save`, `load`.

## Verification

### vue-tsc

`npx vue-tsc --noEmit src/components/VisualEditor.vue` reports 0 errors for the component. (One unrelated pre-existing `Cannot find module 'scheduler/tracing'` error from `@types/react` in `node_modules` exists project-wide; not introduced by this task.)

### vitest

```
$ cd frontend-v2 && npx vitest run tests/p3_p2_focused/visual_editor.test.ts
 Test Files  1 passed (1)
      Tests  12 passed (12)
   Duration  1.13s
```

12/12 tests PASS in 1.13s. The tests cover:

1. Mount renders canvas + palette + properties panel + empty-state
2. Palette exposes 7 node types with correct draggable / data-node-type attrs
3. `addNode` creates a node of the requested type, places it, and selects it
4. Drag-and-drop (palette → canvas) creates a node at the cursor position
5. Properties panel edits the selected node label (via v-model)
6. Save click populates the JSON textarea with `{version: 1, nodes, edges}`
7. Load restores a document from JSON
8. `connectNodes` creates a directed edge; duplicates rejected
9. `connectNodes` refuses self-loops
10. `deleteNode` removes a node and cascades removal of referencing edges
11. `clearAll` empties nodes and edges
12. Start nodes have no input handle; End nodes have no output handle

A minimal `MockDataTransfer` is provided at the top of the test file because jsdom 24 in this environment does not expose a global `DataTransfer` constructor (only a getter on `DragEvent`).

## Deliberate scope cuts (for the next P-task)

Per the task brief, advanced features are out of scope for this scaffold:

- **Undo/Redo** — a future task should add a command stack wrapping `addNode` / `deleteNode` / `moveNode` / `connectNodes` / `importDoc` / `property edits`.
- **Copy/Paste** — needs clipboard serialisation; a future task should add `Ctrl+C`/`Ctrl+V` keyboard handlers and a clipboard document-format round-trip.
- **Multi-select + box-select** — needs a marquee state and a `selectedNodeIds: string[]` ref.
- **Alignment / distribute** — operates on multi-select.
- **Validation / execute** — the document is just data; backend binding is a separate concern.
- **Route integration** — the task did not specify a route; `VisualEditor` is exported as a component for callers to mount. Adding a route entry is straightforward (`router/index.ts`).
- **i18n keys** — node-type labels are inline English in the palette (`'Start'`, `'End'`, ...). Adding t() keys is a 10-line follow-up; deliberately deferred to keep the scaffold focused.

## How to mount in a parent view

```vue
<template>
  <VisualEditor
    :initial-doc="doc"
    storage-key="my-workflow.v1"
    @update:doc="onDocChange"
    @select="onSelect"
    @save="onSave"
  />
</template>
```

Where `doc: VisualEditorDocument | null` is the bound initial state. If `initial-doc` is omitted, the component falls back to `localStorage[storageKey]`; if neither is present, the canvas starts empty.

## Status

- vue-tsc: 0 errors on the component
- vitest: 12/12 PASS
- File count: 2 new (component + test) + 2 reports (this + deliverable.md)
- No new dependencies introduced
- Ready for verifier review
