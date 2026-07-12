/**
 * P21 P3 P2 focused — VisualEditor.vue (workflow editor scaffold) tests.
 *
 * Coverage:
 *   1. Mount renders canvas + palette + properties panel
 *   2. Palette exposes 7 node types (Start, End, Process, Decision, Loop, AI Skill, Provider)
 *   3. addNode() exposed method creates a node and selects it
 *   4. Drag-and-drop (palette → canvas) creates a node at the cursor position
 *   5. Properties panel edits the selected node label
 *   6. Save: onSaveClick populates the JSON textarea with a serialised document
 *   7. Load: importDoc restores nodes + edges
 *   8. Connect nodes creates a directed edge
 *   9. Delete node cascades removal of referencing edges
 *  10. clearAll empties nodes and edges
 *  11. Handle visibility per node type (start/end have only one handle)
 *
 * Run with (per task spec):
 *   cd frontend-v2 && npx vitest run tests/p3_p2_focused/visual_editor.test.ts
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import VisualEditor, {
  type VisualEditorDocument,
  type VisualEditorNode
} from '@/components/VisualEditor.vue'

/* Minimal DataTransfer mock for jsdom (jsdom 24+ lacks native DataTransfer). */
class MockDataTransfer {
  private store = new Map<string, string>()
  setData(type: string, value: string): void { this.store.set(type, value) }
  getData(type: string): string { return this.store.get(type) ?? '' }
  // Properties the events may inspect — keep them as no-op setters
  effectAllowed = 'copy'
  dropEffect = 'copy'
  files: unknown[] = []
  items: unknown[] = []
  types: string[] = []
}

function mountEditor(props: Record<string, unknown> = {}): VueWrapper {
  if (typeof localStorage !== 'undefined') {
    try { localStorage.clear() } catch { /* quota / private mode */ }
  }
  return mount(VisualEditor, {
    props,
    attachTo: document.body,
    global: { stubs: {} }
  })
}

function getExposed(vm: unknown): Record<string, unknown> {
  const v = vm as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const k of [
    'addNode', 'deleteNode', 'moveNode', 'selectNode', 'connectNodes',
    'clearAll', 'resetViewport', 'exportDoc', 'importDoc'
  ]) {
    out[k] = typeof v[k] === 'function' ? v[k] : undefined
  }
  for (const k of ['nodes', 'edges', 'selectedNodeId', 'viewport']) {
    const candidate = v[k] as { value?: unknown } | unknown
    if (candidate && typeof candidate === 'object' && 'value' in (candidate as Record<string, unknown>)) {
      out[k] = (candidate as { value: unknown }).value
    } else {
      out[k] = candidate
    }
  }
  return out
}

function buildDoc(): VisualEditorDocument {
  return {
    version: 1,
    nodes: [
      { id: 'start-1', type: 'start', label: 'Start', x: 100, y: 100, width: 140, height: 60, params: {} },
      { id: 'end-1', type: 'end', label: 'End', x: 400, y: 100, width: 140, height: 60, params: {} }
    ],
    edges: []
  }
}

describe('VisualEditor', () => {
  beforeEach(() => {
    if (typeof document !== 'undefined') document.body.innerHTML = ''
  })

  it('mounts and renders canvas + palette + properties panel', async () => {
    const w = mountEditor()
    await nextTick()
    expect(w.find('[data-testid="visual-editor"]').exists()).toBe(true)
    expect(w.find('[data-testid="ve-canvas"]').exists()).toBe(true)
    expect(w.find('[data-testid="palette"]').exists()).toBe(true)
    expect(w.find('[data-testid="properties"]').exists()).toBe(true)
    expect(w.find('[data-testid="empty-state"]').exists()).toBe(true)
    w.unmount()
  })

  it('exposes 7 palette items for the documented node types', async () => {
    const w = mountEditor()
    await nextTick()
    const expected = ['start', 'end', 'process', 'decision', 'loop', 'ai_skill', 'provider']
    for (const t of expected) {
      const item = w.find(`[data-testid="palette-${t}"]`)
      expect(item.exists()).toBe(true)
      expect(item.attributes('draggable')).toBe('true')
      expect(item.attributes('data-node-type')).toBe(t)
    }
    w.unmount()
  })

  it('addNode creates a node of the requested type and selects it', async () => {
    const w = mountEditor()
    await nextTick()
    const api = getExposed(w.vm)
    const n = (api.addNode as Function)('process', 200, 200) as VisualEditorNode
    expect(n).toBeTruthy()
    expect(n.type).toBe('process')
    expect(typeof n.id).toBe('string')
    expect(n.id.length).toBeGreaterThan(5)
    expect(n.width).toBe(160) // palette default for process
    expect(n.height).toBe(70)
    await nextTick()
    expect(w.find(`[data-testid="canvas-node-${n.id}"]`).exists()).toBe(true)
    expect(w.html()).toContain('nodes: 1')
    expect(w.html()).toContain('selected: Process 1')
    // Re-read exposed state — selectedNodeId is a ref, the test snapshot was taken
    // before addNode fired.
    const fresh = getExposed(w.vm)
    expect(fresh.selectedNodeId as string).toBe(n.id)
    w.unmount()
  })

  it('drag-and-drop from palette to canvas creates a node', async () => {
    const w = mountEditor()
    await nextTick()
    const palette = w.find('[data-testid="palette-decision"]').element as HTMLElement
    const canvas = w.find('[data-testid="ve-canvas"]').element as HTMLElement
    canvas.getBoundingClientRect = () => ({
      left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600, x: 0, y: 0, toJSON: () => ({})
    } as DOMRect)

    const dt = new MockDataTransfer()
    // jsdom DragEvent has a getter-only dataTransfer — pass our mock via init.
    const dragStart = new Event('dragstart', { bubbles: true, cancelable: true }) as DragEvent
    Object.defineProperty(dragStart, 'dataTransfer', { value: dt, configurable: true })
    palette.dispatchEvent(dragStart)
    expect(dt.getData('application/x-vdp-node-type')).toBe('decision')

    const drop = new Event('drop', { bubbles: true, cancelable: true }) as DragEvent
    Object.defineProperty(drop, 'dataTransfer', { value: dt, configurable: true })
    Object.defineProperty(drop, 'clientX', { value: 320, configurable: true })
    Object.defineProperty(drop, 'clientY', { value: 220, configurable: true })
    Object.defineProperty(drop, 'preventDefault', { value: () => undefined, configurable: true })
    canvas.dispatchEvent(drop)
    await nextTick()

    const api = getExposed(w.vm)
    const all = api.nodes as VisualEditorNode[]
    const dropped = all.find(n => n.type === 'decision')
    expect(dropped).toBeTruthy()
    expect(w.find(`[data-testid="canvas-node-${dropped!.id}"]`).exists()).toBe(true)
    w.unmount()
  })

  it('properties panel edits the selected node label', async () => {
    const w = mountEditor()
    await nextTick()
    const api = getExposed(w.vm)
    const n = (api.addNode as Function)('process', 200, 200) as VisualEditorNode
    await nextTick()
    const labelInput = w.find('[data-testid="prop-label"]').element as HTMLInputElement
    expect(labelInput.value).toBe('Process 1')
    labelInput.value = 'My Process'
    labelInput.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    const all = (api.nodes as VisualEditorNode[])
    const found = all.find(x => x.id === n.id)
    expect(found?.label).toBe('My Process')
    w.unmount()
  })

  it('save click populates the JSON textarea with the document', async () => {
    const w = mountEditor()
    await nextTick()
    const api = getExposed(w.vm)
    const n = (api.addNode as Function)('process', 100, 100) as VisualEditorNode
    const m = (api.addNode as Function)('end', 300, 100) as VisualEditorNode
    ;(api.connectNodes as Function)(n.id, m.id)
    await nextTick()
    const saveBtn = w.find('[data-testid="save-btn"]').element as HTMLButtonElement
    saveBtn.click()
    await nextTick()
    const ta = w.find('[data-testid="json-input"]').element as HTMLTextAreaElement
    expect(ta.value.length).toBeGreaterThan(0)
    const parsed = JSON.parse(ta.value) as VisualEditorDocument
    expect(parsed.version).toBe(1)
    expect(parsed.nodes.length).toBe(2)
    expect(parsed.edges.length).toBe(1)
    expect(parsed.nodes[0].type).toBe('process')
    expect(parsed.edges[0].source).toBe(n.id)
    expect(parsed.edges[0].target).toBe(m.id)
    w.unmount()
  })

  it('load restores a document from JSON', async () => {
    const w = mountEditor()
    await nextTick()
    const ta = w.find('[data-testid="json-input"]').element as HTMLTextAreaElement
    const doc = buildDoc()
    ta.value = JSON.stringify(doc)
    ta.dispatchEvent(new Event('input', { bubbles: true }))
    await nextTick()
    const loadBtn = w.find('[data-testid="load-btn"]').element as HTMLButtonElement
    loadBtn.click()
    await nextTick()
    const api = getExposed(w.vm)
    const all = api.nodes as VisualEditorNode[]
    expect(all.length).toBe(2)
    expect(w.find(`[data-testid="canvas-node-start-1"]`).exists()).toBe(true)
    expect(w.find(`[data-testid="canvas-node-end-1"]`).exists()).toBe(true)
    w.unmount()
  })

  it('connectNodes creates a directed edge between two nodes', async () => {
    const w = mountEditor()
    await nextTick()
    const api = getExposed(w.vm)
    const a = (api.addNode as Function)('start', 100, 100) as VisualEditorNode
    const b = (api.addNode as Function)('process', 300, 100) as VisualEditorNode
    const edge = (api.connectNodes as Function)(a.id, b.id) as { id: string; source: string; target: string } | null
    expect(edge).not.toBeNull()
    expect(edge!.source).toBe(a.id)
    expect(edge!.target).toBe(b.id)
    await nextTick()
    expect(w.html()).toContain('edges: 1')
    // duplicate connection is rejected
    const dup = (api.connectNodes as Function)(a.id, b.id)
    expect(dup).toBeNull()
    w.unmount()
  })

  it('connectNodes refuses self-loops', async () => {
    const w = mountEditor()
    await nextTick()
    const api = getExposed(w.vm)
    const a = (api.addNode as Function)('process', 200, 200) as VisualEditorNode
    const edge = (api.connectNodes as Function)(a.id, a.id)
    expect(edge).toBeNull()
    expect((api.edges as unknown[]).length).toBe(0)
    w.unmount()
  })

  it('deleteNode removes node and cascades removal of referencing edges', async () => {
    const w = mountEditor()
    await nextTick()
    const api = getExposed(w.vm)
    const a = (api.addNode as Function)('start', 100, 100) as VisualEditorNode
    const b = (api.addNode as Function)('end', 300, 100) as VisualEditorNode
    ;(api.connectNodes as Function)(a.id, b.id)
    await nextTick()
    expect(w.html()).toContain('edges: 1')
    ;(api.deleteNode as Function)(a.id)
    await nextTick()
    expect(w.html()).toContain('nodes: 1')
    expect(w.html()).toContain('edges: 0')
    expect(w.find(`[data-testid="canvas-node-${a.id}"]`).exists()).toBe(false)
    w.unmount()
  })

  it('clearAll empties nodes and edges (re-read after mutation)', async () => {
    const w = mountEditor()
    await nextTick()
    const api = getExposed(w.vm)
    ;(api.addNode as Function)('start', 100, 100)
    ;(api.addNode as Function)('end', 300, 100)
    expect((api.nodes as unknown[]).length).toBe(2)
    ;(api.clearAll as Function)()
    await nextTick()
    // Re-read after clearAll (which replaces the nodes ref's array).
    const fresh = getExposed(w.vm)
    expect((fresh.nodes as unknown[]).length).toBe(0)
    expect((fresh.edges as unknown[]).length).toBe(0)
    expect(w.find('[data-testid="empty-state"]').exists()).toBe(true)
    w.unmount()
  })

  it('input handles are only on non-start nodes, output handles only on non-end nodes', async () => {
    const w = mountEditor()
    await nextTick()
    const api = getExposed(w.vm)
    const s = (api.addNode as Function)('start', 50, 50) as VisualEditorNode
    const e = (api.addNode as Function)('end', 200, 50) as VisualEditorNode
    await nextTick()
    // Start node: no input handle
    expect(w.find(`[data-testid="handle-in-${s.id}"]`).exists()).toBe(false)
    // Start node: has output handle
    expect(w.find(`[data-testid="handle-out-${s.id}"]`).exists()).toBe(true)
    // End node: has input handle
    expect(w.find(`[data-testid="handle-in-${e.id}"]`).exists()).toBe(true)
    // End node: no output handle
    expect(w.find(`[data-testid="handle-out-${e.id}"]`).exists()).toBe(false)
    w.unmount()
  })
})
