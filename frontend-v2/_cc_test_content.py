TEST_CONTENT = r'''
/**
 * CommandCenter tests (vitest, jsdom).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import CommandCenter from '@/components/CommandCenter.vue'

function clearLocalStorage(): void {
  if (typeof localStorage === 'undefined') return
  try { localStorage.clear() } catch { for (const k of Object.keys(localStorage)) localStorage.removeItem(k) }
}

function getExposed(vm: unknown): Record<string, unknown> {
  const v = vm as Record<string, unknown>
  const out: Record<string, unknown> = { store: v.store }
  out.submit = typeof v.submit === 'function' ? v.submit : (v.store && typeof (v.store as Record<string, unknown>).submitRequest === 'function' ? (v.store as Record<string, unknown>).submitRequest : undefined)
  return out
}

describe('CommandCenter', () => {
  beforeEach(() => {
    clearLocalStorage()
    if (typeof document !== 'undefined') document.body.innerHTML = ''
  })

  it('renders an empty chat with placeholder', async () => {
    const w = mount(CommandCenter, { attachTo: document.body })
    await nextTick()
    expect(w.find('[data-testid="empty-chat"]').exists()).toBe(true)
    expect(w.find('[data-testid="cc-input"]').exists()).toBe(true)
    expect(w.find('[data-testid="cc-submit"]').exists()).toBe(true)
    w.unmount()
  })

  it('submitting a request creates user + plan messages and an execution plan', async () => {
    const w = mount(CommandCenter, { attachTo: document.body })
    await nextTick()
    const api = getExposed(w.vm)
    const store = api.store as { messages: Array<{ role: string; plan?: { tasks: unknown[] } }>; submitRequest: (t: string) => unknown }
    store.submitRequest('annotate 100 images and then score them')
    await nextTick()
    const roles = store.messages.map(m => m.role)
    expect(roles).toContain('user')
    expect(roles).toContain('plan')
    const planMsg = store.messages.find(m => m.role === 'plan')
    expect(planMsg?.plan?.tasks.length).toBeGreaterThan(0)
    expect(w.find('[data-testid="plan-card"]').exists()).toBe(true)
    w.unmount()
  })

  it('scrolls the message list to the bottom when a new message is appended', async () => {
    const w = mount(CommandCenter, { attachTo: document.body })
    await nextTick()
    const list = w.find('[data-testid="message-list"]').element as HTMLElement
    let stub = 100
    Object.defineProperty(list, 'scrollHeight', { configurable: true, get: () => stub })
    Object.defineProperty(list, 'scrollTop', { configurable: true, get: () => 0, set: (v: number) => { (list as unknown as Record<string, number>)._lastTop = v } })
    const store = getExposed(w.vm).store as { submitRequest: (t: string) => unknown }
    store.submitRequest('collect assets then clean then annotate')
    stub = 500
    await nextTick()
    await nextTick()
    expect((list as unknown as Record<string, number>)._lastTop).toBe(500)
    w.unmount()
  })

  it('updatePlanProgress clamps to [0, 1]', async () => {
    const w = mount(CommandCenter, { attachTo: document.body })
    await nextTick()
    const store = getExposed(w.vm).store as {
      submitRequest: (t: string) => unknown
      currentPlan: { tasks: Array<{ id: string; progress: number }> } | null
      updatePlanProgress: (id: string, p: number) => void
    }
    store.submitRequest('score dataset')
    await nextTick()
    const tid = store.currentPlan!.tasks[0].id
    store.updatePlanProgress(tid, 0.5)
    expect(store.currentPlan!.tasks[0].progress).toBe(0.5)
    store.updatePlanProgress(tid, 5)
    expect(store.currentPlan!.tasks[0].progress).toBe(1)
    store.updatePlanProgress(tid, -5)
    expect(store.currentPlan!.tasks[0].progress).toBe(0)
    w.unmount()
  })

  it('markTaskRunning / markTaskDone bookkeeping', async () => {
    const w = mount(CommandCenter, { attachTo: document.body })
    await nextTick()
    const store = getExposed(w.vm).store as {
      submitRequest: (t: string) => unknown
      currentPlan: { tasks: Array<{ id: string; status: string }> } | null
      markTaskRunning: (id: string) => void
      markTaskDone: (id: string) => void
      executingTaskIds: string[]
    }
    store.submitRequest('workflow run')
    await nextTick()
    const tid = store.currentPlan!.tasks[0].id
    store.markTaskRunning(tid)
    expect(store.executingTaskIds).toContain(tid)
    expect(store.currentPlan!.tasks[0].status).toBe('running')
    store.markTaskDone(tid)
    expect(store.executingTaskIds).not.toContain(tid)
    expect(store.currentPlan!.tasks[0].status).toBe('done')
    w.unmount()
  })

  it('clear() empties messages and currentPlan', async () => {
    const w = mount(CommandCenter, { attachTo: document.body })
    await nextTick()
    const store = getExposed(w.vm).store as {
      submitRequest: (t: string) => unknown
      messages: unknown[]
      currentPlan: unknown
      clear: () => void
    }
    store.submitRequest('something')
    await nextTick()
    expect(store.messages.length).toBeGreaterThan(0)
    store.clear()
    expect(store.messages.length).toBe(0)
    expect(store.currentPlan).toBeNull()
    w.unmount()
  })

  it('empty / whitespace-only submit is ignored', async () => {
    const w = mount(CommandCenter, { attachTo: document.body })
    await nextTick()
    const store = getExposed(w.vm).store as {
      submitRequest: (t: string) => unknown | null
      messages: unknown[]
    }
    expect(store.submitRequest('')).toBeNull()
    expect(store.submitRequest('   ')).toBeNull()
    expect(store.messages.length).toBe(0)
    w.unmount()
  })
})
'''

CC_TEST = TEST_CONTENT.strip(chr(10))
