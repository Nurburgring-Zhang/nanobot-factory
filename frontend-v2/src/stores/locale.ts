/**
 * Locale Pinia store — wraps vue-i18n with persistence + reactive getter.
 *
 * Components that need to *observe* locale changes should subscribe to
 * `useLocaleStore().current` instead of `i18n.global.locale.value` directly,
 * so the Pinia devtools and `localStorage` stay in sync.
 */
import { defineStore } from 'pinia'
import { computed } from 'vue'
import {
  i18n,
  setLocale,
  getLocale,
  LOCALE_STORAGE_KEY,
  SUPPORTED_LOCALES,
  LOCALE_META,
  RTL_LOCALES,
  isRTL,
  applyDocumentDirection,
  type LocaleCode
} from '@/locales'

export const useLocaleStore = defineStore('locale', () => {
  const current = computed<LocaleCode>(() => getLocale())

  const supported = computed(() => SUPPORTED_LOCALES)

  const meta = computed(() => LOCALE_META)

  const isCurrentRTL = computed(() => isRTL(current.value))

  function restoreFromStorage(): void {
    if (typeof window === 'undefined' || typeof window.localStorage === 'undefined') return
    try {
      const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY)
      if (stored && (SUPPORTED_LOCALES as readonly string[]).includes(stored)) {
        void setLocale(stored as LocaleCode)
      }
    } catch {
      // Ignore SecurityError / quota issues.
    }
  }

  async function changeTo(next: LocaleCode): Promise<void> {
    await setLocale(next)
  }

  /**
   * Cycle to the next locale in `SUPPORTED_LOCALES` order.
   * Used by the floating LocaleToggle button.
   */
  async function cycleNext(): Promise<void> {
    const idx = SUPPORTED_LOCALES.indexOf(current.value)
    const nextIdx = (idx + 1) % SUPPORTED_LOCALES.length
    await setLocale(SUPPORTED_LOCALES[nextIdx])
  }

  // Back-compat alias for the previous zh-CN / en-US toggle behaviour.
  async function toggle(): Promise<void> {
    await cycleNext()
  }

  return {
    current,
    supported,
    meta,
    isCurrentRTL,
    rtlLocales: RTL_LOCALES,
    i18n, // exposed for components that need the global t() outside of useI18n
    restoreFromStorage,
    changeTo,
    cycleNext,
    toggle,
    applyDocumentDirection
  }
})