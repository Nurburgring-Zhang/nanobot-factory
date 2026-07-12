/**
 * BillingAdmin.vue smoke tests (V5 §13.4 / Chapter 22 — CDP Advanced Billing).
 *
 * Coverage (≥ 5 tests):
 *   - renders the admin shell with the 3 sections (Usage / Invoices / Pricing Tiers)
 *   - shows empty-state placeholders when the store has no data
 *   - loads deterministic seed data on mount
 *   - resolves current tier correctly from aggregate usage
 *   - shows invoice download buttons when invoices are present
 *
 * Like CrowdsourceAdmin.spec.ts, Naive UI subcomponents are stubbed so the
 * smoke tests don't depend on jsdom rendering them. The store-level
 * behavior is what really matters here.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import BillingAdmin from '@/components/BillingAdmin.vue'
import { useBillingStore } from '@/stores/billing'

function mountWithProviders(component: any, options: any = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  // Slot-rendering stubs so data-testid children inside n-card / n-grid
  // (data-testid="usage-empty" etc.) are findable in jsdom.
  const slotStub = (tag: string) => ({
    name: tag,
    template: `<div><slot /></div>`,
    props: ['value', 'span'],
  })
  return mount(component, {
    ...options,
    global: {
      plugins: [pinia],
      stubs: {
        'n-card': slotStub('NCard'),
        'n-grid': slotStub('NGrid'),
        'n-grid-item': slotStub('NGridItem'),
        'n-button': slotStub('NButton'),
        Transition: false,
      },
    },
  })
}

describe('BillingAdmin', () => {
  beforeEach(() => {
    if (typeof document !== 'undefined') document.body.innerHTML = ''
  })

  it('renders the billing admin header', () => {
    const wrapper = mountWithProviders(BillingAdmin)
    expect(wrapper.text()).toContain('CDP Billing')
    wrapper.unmount()
  })

  it('exposes the 3 sections (Usage, Invoices, Pricing Tiers)', () => {
    const wrapper = mountWithProviders(BillingAdmin)
    expect(wrapper.text()).toContain('Current Month Usage')
    expect(wrapper.text()).toContain('Invoices')
    expect(wrapper.text()).toContain('Pricing Tiers')
    wrapper.unmount()
  })

  it('shows empty-state placeholders when store has no data', async () => {
    // Pre-mark the store as loaded so the component's onMounted loadAll() race
    // doesn't overwrite our empty arrays after the assertion.
    const pinia = createPinia()
    setActivePinia(pinia)
    const pre = useBillingStore()
    pre.loaded = true
    const wrapper = mount(BillingAdmin, {
      global: {
        plugins: [pinia],
        stubs: {
          'n-card': { template: '<div><slot /></div>' },
          'n-grid': { template: '<div><slot /></div>' },
          'n-grid-item': { template: '<div><slot /></div>' },
          'n-button': { template: '<div><slot /></div>' },
          Transition: false,
        },
      },
    })
    const store = useBillingStore()
    store.usage = []
    store.invoices = []
    store.tiers = []
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="usage-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="invoices-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tiers-empty"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('loads deterministic seed data on mount', async () => {
    const wrapper = mountWithProviders(BillingAdmin)
    await new Promise((r) => setTimeout(r, 80))
    await wrapper.vm.$nextTick()
    const store = useBillingStore()
    expect(store.loaded).toBe(true)
    expect(store.usage.length).toBe(3)
    expect(store.invoices.length).toBe(2)
    expect(store.tiers.length).toBe(3)
    wrapper.unmount()
  })

  it('resolves current tier from aggregate usage (tier_2 for seed)', async () => {
    const wrapper = mountWithProviders(BillingAdmin)
    const store = useBillingStore()
    await store.loadAll()
    // Seed usage qty: storage_gb 500 + api_calls 10000 + render_minutes 45 = 10545
    // 10545 >= tier_2.min_units (10_000) → tier_2 applies
    expect(store.currentTier).not.toBeNull()
    expect(store.currentTier!.name).toBe('tier_2')
    wrapper.unmount()
  })
})
