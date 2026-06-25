/**
 * NInput via SearchBar smoke tests.
 *
 * SearchBar is the most-used input wrapper, so we exercise v-model + clearable
 * here. Naive UI's NInput is tested upstream.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import SearchBar from '@/components/SearchBar.vue'

describe('SearchBar', () => {
  beforeEach(() => {
    if (typeof document !== 'undefined') document.body.innerHTML = ''
  })

  it('renders the placeholder prop', () => {
    const wrapper = mount(SearchBar, {
      attachTo: document.body,
      props: { placeholder: 'Find me' }
    })
    expect(wrapper.find('input').attributes('placeholder')).toBe('Find me')
    wrapper.unmount()
  })

  it('emits update:modelValue + search on Enter / button click', async () => {
    const wrapper = mount(SearchBar, {
      attachTo: document.body,
      props: { modelValue: '' }
    })
    const input = wrapper.find('input')
    await input.setValue('hello world')
    await input.trigger('keyup.enter')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('search')).toBeTruthy()
    wrapper.unmount()
  })

  it('emits reset when the reset button is clicked', async () => {
    const wrapper = mount(SearchBar, {
      attachTo: document.body,
      props: { modelValue: 'foo' }
    })
    const buttons = wrapper.findAll('button')
    // 2nd button is the reset button (after the search button).
    await buttons[1].trigger('click')
    expect(wrapper.emitted('reset')).toBeTruthy()
    wrapper.unmount()
  })

  it('exposes accessible label via placeholder for screen readers', () => {
    const wrapper = mount(SearchBar, {
      attachTo: document.body,
      props: { placeholder: 'Search datasets' }
    })
    // <input placeholder="Search datasets"> is announced by screen readers as
    // an accessible name; the attribute must round-trip cleanly.
    expect(wrapper.find('input').attributes('placeholder')).toBe('Search datasets')
    wrapper.unmount()
  })
})