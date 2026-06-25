/**
 * NButton / ActionButton smoke tests.
 *
 * Verifies the wrapper component renders, accepts props, and emits click.
 * Does not exhaustively test Naive UI's internal behaviour — that's the
 * library's responsibility.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ActionButton from '@/components/ActionButton.vue'

describe('ActionButton', () => {
  beforeEach(() => {
    if (typeof document !== 'undefined') document.body.innerHTML = ''
  })

  it('renders default slot content', () => {
    const wrapper = mount(ActionButton, {
      attachTo: document.body,
      slots: { default: 'Click me' }
    })
    expect(wrapper.text()).toContain('Click me')
    wrapper.unmount()
  })

  it('emits click when not disabled', async () => {
    const wrapper = mount(ActionButton, {
      attachTo: document.body,
      props: { type: 'primary' },
      slots: { default: 'Go' }
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeTruthy()
    expect(wrapper.emitted('click')!.length).toBe(1)
    wrapper.unmount()
  })

  it('does not emit click when disabled', async () => {
    const wrapper = mount(ActionButton, {
      attachTo: document.body,
      props: { disabled: true },
      slots: { default: 'No' }
    })
    await wrapper.trigger('click')
    expect(wrapper.emitted('click')).toBeFalsy()
    wrapper.unmount()
  })

  it('exposes disabled state via the disabled prop', () => {
    const wrapper = mount(ActionButton, {
      attachTo: document.body,
      props: { disabled: true },
      slots: { default: 'X' }
    })
    // Naive UI emits a `disabled=""` attribute and adds the
    // `n-button--disabled` class; either signal is sufficient for AT.
    const html = wrapper.html()
    expect(html).toMatch(/n-button--disabled/)
    expect(html).toMatch(/disabled=""|disabled=/)
    wrapper.unmount()
  })
})