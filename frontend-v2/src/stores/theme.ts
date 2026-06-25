import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

/**
 * Theme store — drives the Naive UI dark/light mode toggle.
 *
 * State machine:
 *   'light'  → always light
 *   'dark'   → always dark
 *   'auto'   → follows OS prefers-color-scheme
 *
 * The `resolved` getter is what UI components should bind against —
 * it collapses 'auto' into a concrete 'light' or 'dark'.
 *
 * Persists to localStorage under the key 'vdp-theme' so the choice
 * survives reloads. We also reflect the choice on <html> as a
 * `data-theme` attribute so global CSS can target it.
 */

const STORAGE_KEY = 'vdp-theme'

export type ThemeMode = 'light' | 'dark' | 'auto'

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>('light')
  const systemPrefersDark = ref<boolean>(false)
  const initialized = ref<boolean>(false)

  // Concrete value UI should bind against (auto → resolved via media query)
  const resolved = computed<'light' | 'dark'>(() => {
    if (mode.value === 'auto') {
      return systemPrefersDark.value ? 'dark' : 'light'
    }
    return mode.value
  })

  const isDark = computed<boolean>(() => resolved.value === 'dark')

  function readMediaQuery(): boolean {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  }

  function applyToDom(value: 'light' | 'dark'): void {
    if (typeof document === 'undefined') return
    const root = document.documentElement
    root.setAttribute('data-theme', value)
    // Also tweak the browser chrome color
    root.style.colorScheme = value
  }

  function persist(value: ThemeMode): void {
    if (typeof localStorage === 'undefined') return
    try {
      localStorage.setItem(STORAGE_KEY, value)
    } catch {
      // Quota exceeded / private mode — silent fallback; in-memory still works
    }
  }

  function restoreFromStorage(): void {
    if (typeof localStorage === 'undefined') {
      initialized.value = true
      return
    }
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw === 'light' || raw === 'dark' || raw === 'auto') {
        mode.value = raw
      }
    } catch {
      // corrupted — keep default 'light'
    }
    systemPrefersDark.value = readMediaQuery()
    applyToDom(resolved.value)
    initialized.value = true
  }

  function set(next: ThemeMode): void {
    mode.value = next
    persist(next)
  }

  /**
   * Cycle light → dark → auto → light. Bound to the header toggle button.
   */
  function cycle(): void {
    const order: ThemeMode[] = ['light', 'dark', 'auto']
    const idx = order.indexOf(mode.value)
    const next = order[(idx + 1) % order.length] ?? 'light'
    set(next)
  }

  /**
   * Convenience for a binary on/off toggle button.
   */
  function toggle(): void {
    set(isDark.value ? 'light' : 'dark')
  }

  // React to mode / system changes by writing data-theme to <html>
  watch(
    resolved,
    (v) => {
      applyToDom(v)
    },
    { immediate: false }
  )

  // Bind to OS preference changes (only matters in 'auto' mode)
  function bindSystemListener(): () => void {
    if (typeof window === 'undefined' || !window.matchMedia) {
      return () => undefined
    }
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => {
      systemPrefersDark.value = e.matches
    }
    // addEventListener is the modern API; addListener is the legacy one
    if (mq.addEventListener) {
      mq.addEventListener('change', handler)
      return () => mq.removeEventListener('change', handler)
    }
    mq.addListener(handler)
    return () => mq.removeListener(handler)
  }

  return {
    mode,
    resolved,
    isDark,
    systemPrefersDark,
    initialized,
    set,
    cycle,
    toggle,
    restoreFromStorage,
    bindSystemListener
  }
})
