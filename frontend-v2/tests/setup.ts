/**
 * Vitest global setup.
 *
 *   - Mount @vue/test-utils helpers
 *   - Provide a deterministic i18n instance (zh-CN) for snapshot-free component tests
 *   - Mock window.matchMedia (Naive UI reads it during mount)
 *
 * Tests can override i18n by calling `useI18n()` inside the component and
 * mutating `i18n.global.locale.value` between renders.
 */
import { config } from '@vue/test-utils'
import { beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { i18n, setLocale } from '@/locales'

// Naive UI / Vue Flow both call matchMedia during mount. jsdom doesn't ship it.
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false
    })
  })
}

// jsdom has no ResizeObserver — provide a stub so Vue Flow / ECharts mounts don't blow up.
if (typeof window !== 'undefined' && !(window as any).ResizeObserver) {
  ;(window as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// Globally register i18n so any component calling useI18n() in <script setup>
// can resolve. Vue Test Utils' `global.providers` only injects into render
// context — for plugin-style install (which vue-i18n requires), use
// `global.plugins`.
;(config.global.plugins as any[]).push(i18n)

beforeEach(() => {
  setActivePinia(createPinia())
  // Reset locale to zh-CN baseline before each test for deterministic output.
  void setLocale('zh-CN')
})