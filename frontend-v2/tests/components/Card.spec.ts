/**
 * NCard rendering smoke tests.
 *
 * NCard is the dominant surface primitive (every view wraps content in it).
 * Verify title + slot + bordered=false work as expected.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { NCard } from 'naive-ui'

describe('NCard', () => {
  beforeEach(() => {
    if (typeof document !== 'undefined') document.body.innerHTML = ''
  })

  it('renders title prop in header', () => {
    const wrapper = mount(NCard, {
      attachTo: document.body,
      props: { title: 'My Card' },
      slots: { default: '<p>body</p>' }
    })
    expect(wrapper.text()).toContain('My Card')
    expect(wrapper.html()).toContain('<p>body</p>')
    wrapper.unmount()
  })

  it('renders default slot without title', () => {
    const wrapper = mount(NCard, {
      attachTo: document.body,
      slots: { default: '<span class="probe">payload</span>' }
    })
    expect(wrapper.find('.probe').exists()).toBe(true)
    wrapper.unmount()
  })

  it('renders without crashing when bordered=false', () => {
    const wrapper = mount(NCard, {
      attachTo: document.body,
      props: { bordered: false },
      slots: { default: 'x' }
    })
    expect(wrapper.html()).toBeTruthy()
    wrapper.unmount()
  })
})