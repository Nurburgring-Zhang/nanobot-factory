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

/**
 * P12-A1: Brand colour tokens — single source of truth for primary / success /
 * warning / error / info hex values used by Naive UI theme overrides AND by
 * any view that needs a hex literal (e.g. inline SVG, chart palettes).
 *
 * The actual runtime swap between light and dark happens via CSS variables
 * (`--app-primary` etc. in App.vue); these tokens exist so:
 *   1. The hex values live in one file and not scattered across App.vue.
 *   2. Contrast claims documented in reports/p8_2_a11y_wcag_v3.md stay in
 *      lock-step with the live code (grep `--app-primary` / `themeOverrides`
 *      and you'll find all callers).
 *
 * Light-mode contrasts (on #ffffff):
 *   primary #0a5dc2 → 6.25:1 (AA Normal Text — bumped from #2080f0 at 3.88:1)
 *   success #157a3e → 5.41:1 (AA Normal Text — bumped from #18a058 at 3.38:1)
 *   warning #c87f0d → 3.23:1 (AA Large only — paired with icon+text)
 *   error   #d03050 → 4.98:1 (AA Normal Text)
 *
 * Dark-mode contrasts (on #18181c):
 *   primary #5aa9ff → 7.21:1 (AAA)
 *   success #4cc07c → 7.70:1 (AAA)
 *   warning #ffb340 → 9.93:1 (AAA)
 *   error   #ff5a72 → 5.87:1 (AA)
 *
 * Update these constants AND the matching dark block + CSS var block in
 * App.vue together — they must stay in sync.
 */
export const PRIMARY_COLOR_OVERRIDES = {
  light: {
    primaryColor: '#0a5dc2',
    primaryColorHover: '#3a82d6',
    primaryColorPressed: '#085096',
    primaryColorSuppl: '#3a82d6'
  },
  dark: {
    primaryColor: '#5aa9ff',
    primaryColorHover: '#7cbbff',
    primaryColorPressed: '#3d92ee',
    primaryColorSuppl: '#7cbbff'
  }
} as const

export const SUCCESS_COLOR_OVERRIDES = {
  light: {
    successColor: '#157a3e',
    successColorHover: '#3a9a5b',
    successColorPressed: '#0e5c2d',
    successColorSuppl: '#3a9a5b'
  },
  dark: {
    successColor: '#4cc07c',
    successColorHover: '#6fd49b',
    successColorPressed: '#2fa362',
    successColorSuppl: '#6fd49b'
  }
} as const

export const WARNING_COLOR_OVERRIDES = {
  light: {
    warningColor: '#c87f0d',
    warningColorHover: '#e09a22',
    warningColorPressed: '#9a640a',
    warningColorSuppl: '#e09a22'
  },
  dark: {
    warningColor: '#ffb340',
    warningColorHover: '#ffc66b',
    warningColorPressed: '#e09a22',
    warningColorSuppl: '#ffc66b'
  }
} as const

export const ERROR_COLOR_OVERRIDES = {
  light: {
    errorColor: '#d03050',
    errorColorHover: '#e0415e',
    errorColorPressed: '#a0203e',
    errorColorSuppl: '#e0415e'
  },
  dark: {
    errorColor: '#ff5a72',
    errorColorHover: '#ff8294',
    errorColorPressed: '#e0415e',
    errorColorSuppl: '#ff8294'
  }
} as const

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
