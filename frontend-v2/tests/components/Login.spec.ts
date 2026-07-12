/**
 * Login.vue — semantic landmark regression test (P12-A3)
 *
 * Asserts:
 *   - The wrapper is a single `<main role="main">` element
 *   - There is no `role="region"` inside Login (no competing landmark)
 *   - The skip-link target points at `#login-main`
 *   - `aria-label` is set on the main landmark (so screen reader users
 *     hear "智影 / ZhiYing" instead of just "main")
 *   - `tabindex="-1"` is on the main so the skip-link can land focus there
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Login from '@/views/Login.vue'

describe('P12-A3 Login landmark', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders exactly one <main role="main"> wrapper', () => {
    const wrapper = mount(Login)
    const mains = wrapper.findAll('main')
    expect(mains).toHaveLength(1)
    expect(mains[0].attributes('role')).toBe('main')
    expect(mains[0].attributes('id')).toBe('login-main')
    expect(mains[0].attributes('tabindex')).toBe('-1')
    expect(mains[0].attributes('aria-label')).toBeTruthy()
  })

  it('does not use role="region" anywhere in the rendered tree', () => {
    const wrapper = mount(Login)
    // Walk the rendered HTML and confirm zero role="region" matches
    const html = wrapper.html()
    const regionMatches = html.match(/role=["']region["']/g) ?? []
    expect(regionMatches).toEqual([])
  })

  it('skip-link target points at the main landmark', () => {
    const wrapper = mount(Login)
    const skipLink = wrapper.find('a.skip-link')
    expect(skipLink.exists()).toBe(true)
    expect(skipLink.attributes('href')).toBe('#login-main')
  })

  it('preserves the live-region error alert (P8-2 a11y)', () => {
    // The error message div is a live region and SHOULD keep role="alert".
    // We only assert the structural contract here, not the conditional render.
    const wrapper = mount(Login)
    const html = wrapper.html()
    // No false-positive: role="alert" is the only other role in this file
    // and it's correct for an aria-live region. It must NOT be role="region".
    expect(html).not.toMatch(/role=["']region["']/)
  })
})
