/**
 * PageRegion.vue — semantic landmark wrapper used across all views.
 *
 * Asserts:
 *   - renders a <section role="region">
 *   - has aria-labelledby pointing at an sr-only h2
 *   - resolves i18n key OR uses raw string as label
 *   - exposes optional description as aria-describedby
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import PageRegion from '@/components/PageRegion.vue'

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      test: { hello: '你好' }
    },
    'en-US': {
      test: { hello: 'Hello' }
    }
  }
})

function factory(props: Record<string, unknown>) {
  return mount(PageRegion, {
    props,
    slots: { default: '<p>body</p>' },
    global: { plugins: [i18n] },
    attachTo: document.body
  })
}

describe('PageRegion', () => {
  it('renders a section with role="region"', () => {
    const w = factory({ label: 'test.hello' })
    const section = w.find('section')
    expect(section.exists()).toBe(true)
    expect(section.attributes('role')).toBe('region')
    w.unmount()
  })

  it('resolves i18n key for label', () => {
    const w = factory({ label: 'test.hello' })
    const h2 = w.find('h2')
    expect(h2.exists()).toBe(true)
    expect(h2.classes()).toContain('sr-only')
    expect(h2.text()).toBe('你好')
    w.unmount()
  })

  it('uses raw string when label has no dot (no i18n key)', () => {
    const w = factory({ label: 'static label' })
    expect(w.find('h2').text()).toBe('static label')
    w.unmount()
  })

  it('links h2 id with section aria-labelledby', () => {
    const w = factory({ label: 'test.hello' })
    const section = w.find('section')
    const h2 = w.find('h2')
    const labelledBy = section.attributes('aria-labelledby')
    expect(labelledBy).toBeTruthy()
    expect(h2.attributes('id')).toBe(labelledBy)
    w.unmount()
  })

  it('adds aria-describedby when description prop set', () => {
    const w = factory({ label: 'test.hello', description: 'test.hello' })
    const section = w.find('section')
    const describedBy = section.attributes('aria-describedby')
    expect(describedBy).toBeTruthy()
    const descEl = w.find(`#${describedBy}`)
    expect(descEl.exists()).toBe(true)
    expect(descEl.classes()).toContain('sr-only')
    w.unmount()
  })

  it('resolves i18n key for description (P0-1 regression)', () => {
    // P8-1 regression: previously the rendered text was the literal key
    // "test.hello" instead of the translated "你好".
    const w = factory({ label: 'test.hello', description: 'test.hello' })
    const section = w.find('section')
    const describedBy = section.attributes('aria-describedby')
    const descEl = w.find(`#${describedBy}`)
    expect(descEl.exists()).toBe(true)
    expect(descEl.text()).toBe('你好')
    expect(descEl.text()).not.toBe('test.hello')
    w.unmount()
  })

  it('does not add aria-describedby when description is empty', () => {
    const w = factory({ label: 'test.hello' })
    const section = w.find('section')
    expect(section.attributes('aria-describedby')).toBeUndefined()
    w.unmount()
  })

  it('renders slot content', () => {
    const w = factory({ label: 'test.hello' })
    expect(w.html()).toContain('<p>body</p>')
    w.unmount()
  })

  it('generates non-empty id for the heading', () => {
    const w = factory({ label: 'test.hello' })
    const id = w.find('h2').attributes('id')
    expect(id).toBeTruthy()
    expect(id.length).toBeGreaterThan(0)
    expect(id).toContain('page-region-heading')
    w.unmount()
  })
})
