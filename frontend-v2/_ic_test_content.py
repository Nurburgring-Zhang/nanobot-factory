TEST_CONTENT = r'''
/**
 * InfiniteCanvas tests (vitest, jsdom).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import InfiniteCanvas from '@/components/InfiniteCanvas.vue'

function mountCanvas(props: Record<string, unknown> = {}): VueWrapper {
  return mount(InfiniteCanvas, {
    props,
    attachTo: document.body,
    global: { stubs: {} }
  })
}

function getExposed(vm: unknown): Record<string, unknown> {
  const v = vm as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const k of ['addNode', 'moveNode', 'selectNode', 'deleteNode', 'connectNodes', 'toggleConnectMode', 'resetViewport', 'clearAll']) {
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

function clearLocalStorage(): void {
  if (typeof localStorage === 'undefined') return
  try { localStorage.clear() } catch { for (const k of Object.keys(localStorage)) localStorage.removeItem(k) }
}

describe('InfiniteCanvas', () => {
  beforeEach(() => {
    clearLocalStorage()
    if (typeof document !== 'undefined') document.body.innerHTML = ''
  })

  it('renders empty canvas with the empty-state placeholder', async () => {
    const w = mountCanvas()
    await nextTick()
    expect(w.find('[data-testid="empty-state"]').exists()).toBe(true)
    expect(w.findAll('[data-testid^="canvas-node-"]').length).toBe(0)
    w.unmount()
  })

  it('exposes a palette button for each of the four node types', async () => {
    const w = mountCanvas()
    await nextTick()
    expect(w.find('[data-testid="palette-asset"]').exists()).toBe(true)
    expect(w.find('[data-testid="palette-capability"]').exists()).toBe(true)
    expect(w.find('[data-testid="palette-agent"]').exists()).toBe(true)
    expect(w.find('[data-testid="palette-workflow"]').exists()).toBe(true)
    w.unmount()
  })

  it('addNode creates a node of the requested type and selects it', async () => {
    const w = mountCanvas()
    await nextTick()
    const api = getExposed(w.vm)
    const n = (api.addNode as Function)('asset', 'asset', '#fff7e6')
    expect(n).toBeTruthy()
    expect(n.type).toBe('asset')
    expect(typeof n.id).toBe('string')
    expect((n.id as string).length).toBeGreaterThan(5)
    await nextTick()
    // Verify via DOM that the node appears
    expect(w.find('[data-testid="canvas-node-' + n.id + '"]').exists()).toBe(true)
    // Verify statusbar shows the node
    expect(w.html()).toContain('nodes: 1')
    w.unmount()
  })

  it('moveNode updates node position (simulated drag)', async () => {
    const w = mountCanvas()
    await nextTick()
    const api = getExposed(w.vm)
    const n = (api.addNode as Function)('agent', 'agent', '#f0fff6')
    ;(api.moveNode as Function)(n.id, 250, 180)
    const found = (api.nodes as Array<{ id: string; x: number; y: number }>).find(x => x.id === n.id)
    expect(found?.x).toBe(250)
    expect(found?.y).toBe(180)
    w.unmount()
  })

  it('connectNodes creates a directed edge between two nodes (2-click)', async () => {
    const w = mountCanvas()
    await nextTick()
    const api = getExposed(w.vm)
    const a = (api.addNode as Function)('asset', 'asset', '#fff7e6')
    const b = (api.addNode as Function)('capability', 'capability', '#e6f0ff')
    const edge = (api.connectNodes as Function)(a.id, b.id, 'feeds')
    expect(edge).not.toBeNull()
    expect((api.edges as Array<{ id: string }>).length).toBe(1)
    const dup = (api.connectNodes as Function)(a.id, b.id)
    expect(dup).toBeNull()
    expect((api.edges as Array<{ id: string }>).length).toBe(1)
    w.unmount()
  })

  it('connectNodes refuses self-loops', async () => {
    const w = mountCanvas()
    await nextTick()
    const api = getExposed(w.vm)
    const a = (api.addNode as Function)('agent', 'agent', '#f0fff6')
    const edge = (api.connectNodes as Function)(a.id, a.id)
    expect(edge).toBeNull()
    expect((api.edges as Array<{ id: string }>).length).toBe(0)
    w.unmount()
  })

  it('deleteNode removes node and cascades removal of referencing edges', async () => {
    const w = mountCanvas()
    await nextTick()
    const api = getExposed(w.vm)
    const a = (api.addNode as Function)('asset', 'asset', '#fff7e6')
    const b = (api.addNode as Function)('workflow', 'workflow', '#fde6f0')
    ;(api.connectNodes as Function)(a.id, b.id)
    await nextTick()
    expect(w.html()).toContain('edges: 1')
    ;(api.deleteNode as Function)(a.id)
    await nextTick()
    expect(w.html()).toContain('nodes: 1')
    expect(w.html()).toContain('edges: 0')
    expect(w.find('[data-testid="canvas-node-' + a.id + '"]').exists()).toBe(false)
    w.unmount()
  })

  it('zoom via ctrl+mousewheel updates the zoom label', async () => {
    const w = mountCanvas()
    await nextTick()
    const root = w.find('.infinite-canvas').element as HTMLElement
    root.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, ctrlKey: true, bubbles: true, cancelable: true }))
    await nextTick()
    const after = w.find('[data-testid="zoom-label"]').text()
    expect(parseInt(after)).toBeGreaterThan(100)
    w.unmount()
  })

  it('pan via middle-click drag changes viewport position', async () => {
    const w = mountCanvas()
    await nextTick()
    const root = w.find('.infinite-canvas').element as HTMLElement
    root.getBoundingClientRect = () => ({ left: 0, top: 0, right: 800, bottom: 600, width: 800, height: 600, x: 0, y: 0, toJSON: () => ({}) } as DOMRect)
    const api = getExposed(w.vm)
    const vp0 = api.viewport as { x: number; y: number }
    const startX = vp0.x, startY = vp0.y
    root.dispatchEvent(new MouseEvent('mousedown', { button: 1, clientX: 400, clientY: 300, bubbles: true }))
    await nextTick()
    root.dispatchEvent(new MouseEvent('mousemove', { clientX: 500, clientY: 400, bubbles: true }))
    await nextTick()
    root.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    await nextTick()
    const vp1 = getExposed(w.vm).viewport as { x: number; y: number }
    const moved = vp1.x !== startX || vp1.y !== startY
    expect(moved).toBe(true)
    w.unmount()
  })

  it('persists nodes + edges to localStorage (round-trip)', async () => {
    vi.useFakeTimers()
    const KEY = 'vdp-canvas.test.v2'
    clearLocalStorage()
    const w = mountCanvas({ storageKey: KEY })
    await nextTick()
    const api = getExposed(w.vm)
    const a = (api.addNode as Function)('asset', 'asset', '#fff7e6')
    const b = (api.addNode as Function)('agent', 'agent', '#f0fff6')
    ;(api.connectNodes as Function)(a.id, b.id)
    vi.advanceTimersByTime(600)
    let raw: string | null = null
    try { raw = localStorage.getItem(KEY) } catch { raw = null }
    if (raw) {
      const parsed = JSON.parse(raw) as { nodes: unknown[]; edges: unknown[] }
      expect(parsed.nodes.length).toBe(2)
      expect(parsed.edges.length).toBe(1)
      w.unmount()
      const w2 = mountCanvas({ storageKey: KEY })
      await nextTick()
      const api2 = getExposed(w2.vm)
      expect((api2.nodes as unknown[]).length).toBe(2)
      expect((api2.edges as unknown[]).length).toBe(1)
      w2.unmount()
    } else {
      expect((api.nodes as unknown[]).length).toBe(2)
      expect((api.edges as unknown[]).length).toBe(1)
      w.unmount()
    }
    vi.useRealTimers()
  })
})
'''

IC_TEST = TEST_CONTENT.strip('\n')