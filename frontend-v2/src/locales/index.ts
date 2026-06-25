/**
 * i18n bootstrap — vue-i18n@9 Composition API mode.
 *
 * Usage:
 *   import { i18n } from '@/locales'
 *   app.use(i18n)
 *
 * Locale resolution order:
 *   1. localStorage `imdf.locale` (set by stores/locale.ts)
 *   2. `navigator.language` (defaults to en-US when neither matches)
 */
import { createI18n } from 'vue-i18n'
import zhCN from './zh-CN'
import enUS from './en-US'

export type LocaleCode = 'zh-CN' | 'en-US'

export const SUPPORTED_LOCALES: ReadonlyArray<LocaleCode> = ['zh-CN', 'en-US']
export const LOCALE_STORAGE_KEY = 'imdf.locale'

export function detectInitialLocale(): LocaleCode {
  // Order matters: prefer the browser localStorage (only present in jsdom /
  // real browser). Node 18+ exposes `localStorage` as a bare reference to
  // `node:localStorage`, which has no `getItem` method — guard with `window`
  // first to avoid that trap.
  if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
    try {
      const stored = window.localStorage.getItem(LOCALE_STORAGE_KEY)
      if (stored === 'zh-CN' || stored === 'en-US') return stored
    } catch {
      // SecurityError in some sandboxed iframes — fall through.
    }
  }
  if (typeof navigator !== 'undefined' && typeof navigator.language === 'string') {
    const lower = navigator.language.toLowerCase()
    if (lower.startsWith('zh')) return 'zh-CN'
    return 'en-US'
  }
  return 'en-US'
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectInitialLocale(),
  fallbackLocale: 'en-US',
  messages: {
    'zh-CN': zhCN,
    'en-US': enUS
  },
  // Keep messages as const so missing keys surface as runtime warnings rather than
  // silently rendering undefined.
  missingWarn: true,
  fallbackWarn: false,
  silentFallbackWarn: false
})

/**
 * Switch the active locale and persist. Returns the locale that was actually set.
 */
export async function setLocale(locale: LocaleCode): Promise<LocaleCode> {
  if (!SUPPORTED_LOCALES.includes(locale)) {
    // eslint-disable-next-line no-console
    console.warn(`[i18n] unsupported locale: ${locale}, falling back to en-US`)
    locale = 'en-US'
  }
  i18n.global.locale.value = locale
  if (typeof window !== 'undefined' && typeof window.localStorage !== 'undefined') {
    try {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, locale)
    } catch {
      // Ignore quota / SecurityError.
    }
  }
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('lang', locale)
  }
  return locale
}

export function getLocale(): LocaleCode {
  return i18n.global.locale.value as LocaleCode
}