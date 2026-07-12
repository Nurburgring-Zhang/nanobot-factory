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
import jaJP from './ja-JP'
import koKR from './ko-KR'
import frFR from './fr-FR'
import deDE from './de-DE'
import esES from './es-ES'
import ruRU from './ru-RU'
import arSA from './ar-SA'
import ptPT from './pt-PT'

export type LocaleCode = 'zh-CN' | 'en-US' | 'ja-JP' | 'ko-KR' | 'fr-FR' | 'de-DE' | 'es-ES' | 'ru-RU' | 'ar-SA' | 'pt-PT'

export const SUPPORTED_LOCALES: ReadonlyArray<LocaleCode> = [
  'zh-CN', 'en-US', 'ja-JP', 'ko-KR', 'fr-FR',
  'de-DE', 'es-ES', 'ru-RU', 'ar-SA', 'pt-PT'
]
export const LOCALE_STORAGE_KEY = 'imdf.locale'

/**
 * Per-locale metadata (display name + direction).
 * P21 P3 P2 focused: added to support App.vue / Topbar / LocaleToggle
 * which reference LOCALE_META but it was never exported.
 */
export const LOCALE_META: Record<LocaleCode, {
  name: string; nativeName: string; englishName: string; flag: string; dir: 'ltr' | 'rtl'
}> = {
  'zh-CN': { name: '简体中文', nativeName: '简体中文', englishName: 'Chinese (Simplified)', flag: '🇨🇳', dir: 'ltr' },
  'en-US': { name: 'English', nativeName: 'English', englishName: 'English', flag: '🇺🇸', dir: 'ltr' },
  'ja-JP': { name: '日本語', nativeName: '日本語', englishName: 'Japanese', flag: '🇯🇵', dir: 'ltr' },
  'ko-KR': { name: '한국어', nativeName: '한국어', englishName: 'Korean', flag: '🇰🇷', dir: 'ltr' },
  'fr-FR': { name: 'Français', nativeName: 'Français', englishName: 'French', flag: '🇫🇷', dir: 'ltr' },
  'de-DE': { name: 'Deutsch', nativeName: 'Deutsch', englishName: 'German', flag: '🇩🇪', dir: 'ltr' },
  'es-ES': { name: 'Español', nativeName: 'Español', englishName: 'Spanish', flag: '🇪🇸', dir: 'ltr' },
  'ru-RU': { name: 'Русский', nativeName: 'Русский', englishName: 'Russian', flag: '🇷🇺', dir: 'ltr' },
  'ar-SA': { name: 'العربية', nativeName: 'العربية', englishName: 'Arabic', flag: '🇸🇦', dir: 'rtl' },
  'pt-PT': { name: 'Português', nativeName: 'Português', englishName: 'Portuguese', flag: '🇵🇹', dir: 'ltr' }
}

export const RTL_LOCALES: ReadonlyArray<LocaleCode> = Object.entries(LOCALE_META)
  .filter(([, meta]) => meta.dir === 'rtl')
  .map(([code]) => code as LocaleCode)

/** Return true if the given locale is right-to-left. */
export function isRTL(locale: LocaleCode): boolean {
  return LOCALE_META[locale]?.dir === 'rtl'
}

/** Apply document direction (dir="rtl"/"ltr") to <html>. No-op on server. */
export function applyDocumentDirection(locale: LocaleCode): void {
  if (typeof document === 'undefined') return
  const dir = isRTL(locale) ? 'rtl' : 'ltr'
  document.documentElement.setAttribute('dir', dir)
}

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
    'en-US': enUS,
    'ja-JP': jaJP,
    'ko-KR': koKR,
    'fr-FR': frFR,
    'de-DE': deDE,
    'es-ES': esES,
    'ru-RU': ruRU,
    'ar-SA': arSA,
    'pt-PT': ptPT
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
    locale = 'en-US' as LocaleCode
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