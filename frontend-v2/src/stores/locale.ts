/**
 * Locale Pinia store — wraps vue-i18n with persistence + reactive getter.
 *
 * Components that need to *observe* locale changes should subscribe to
 * `useLocaleStore().current` instead of `i18n.global.locale.value` directly,
 * so the Pinia devtools and `localStorage` stay in sync.
 */
import { defineStore } from 'pinia'
import { computed } from 'vue'
import { i18n, setLocale, getLocale, LOCALE_STORAGE_KEY, SUPPORTED_LOCALES, type LocaleCode } from '@/locales'

export const useLocaleStore = defineStore('locale', () => {
  const current = computed<LocaleCode>(() => getLocale())

  const supported = computed(() => SUPPORTED_LOCALES)

  function restoreFromStorage(): void {
    if (typeof window === 'undefined' || typeof window.localStorage === 'undefined') return
    try {
      const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY)
      if (stored === 'zh-CN' || stored === 'en-US') {
        void setLocale(stored)
      }
    } catch {
      // Ignore SecurityError / quota issues.
    }
  }

  async function changeTo(next: LocaleCode): Promise<void> {
    await setLocale(next)
  }

  async function toggle(): Promise<void> {
    await setLocale(current.value === 'zh-CN' ? 'en-US' : 'zh-CN')
  }

  return {
    current,
    supported,
    i18n, // exposed for components that need the global t() outside of useI18n
    restoreFromStorage,
    changeTo,
    toggle
  }
})