/**
 * DefaultLayout smoke tests.
 *
 * The layout is the chrome shell: skip-link, sidebar, header, content slot.
 * Verifying its mount + a11y landmark presence is critical for the WCAG goal.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia } from 'pinia'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'dashboard', component: { template: '<div>dashboard</div>' } },
      { path: '/login', name: 'login', component: { template: '<div>login</div>' } }
    ]
  })
}

describe('DefaultLayout', () => {
  beforeEach(() => {
    if (typeof document !== 'undefined') document.body.innerHTML = ''
  })

  it('renders a skip-link targeting #main', () => {
    const wrapper = mount(DefaultLayout, {
      attachTo: document.body,
      global: {
        plugins: [createPinia(), makeRouter()],
        stubs: {
          'router-view': { template: '<div class="router-view-stub" />' },
          'router-link': { template: '<a><slot /></a>' }
        }
      }
    })
    const skip = wrapper.find('.skip-link')
    expect(skip.exists()).toBe(true)
    expect(skip.attributes('href')).toBe('#main')
    expect(skip.text()).toMatch(/skip|跳转/i)
    wrapper.unmount()
  })

  it('renders a <main id="main" tabindex="-1"> landmark for focus target', () => {
    const wrapper = mount(DefaultLayout, {
      attachTo: document.body,
      global: {
        plugins: [createPinia(), makeRouter()],
        stubs: { 'router-view': true, 'router-link': true }
      }
    })
    const main = document.querySelector('#main')
    expect(main).toBeTruthy()
    expect(main?.getAttribute('tabindex')).toBe('-1')
    wrapper.unmount()
  })

  it('exposes a sidebar brand with the app name', () => {
    const wrapper = mount(DefaultLayout, {
      attachTo: document.body,
      global: {
        plugins: [createPinia(), makeRouter()],
        stubs: { 'router-view': true, 'router-link': true }
      }
    })
    expect(document.body.innerHTML).toMatch(/智影|ZhiYing/)
    wrapper.unmount()
  })

  it('renders theme toggle button with an accessible label', () => {
    const wrapper = mount(DefaultLayout, {
      attachTo: document.body,
      global: {
        plugins: [createPinia(), makeRouter()],
        stubs: { 'router-view': true, 'router-link': true }
      }
    })
    const toggle = document.querySelector('.theme-toggle')
    expect(toggle).toBeTruthy()
    // theme-toggle has aria-label / title set via themeTooltip
    const label = toggle?.getAttribute('aria-label') || toggle?.getAttribute('title')
    expect(label).toBeTruthy()
    wrapper.unmount()
  })
})