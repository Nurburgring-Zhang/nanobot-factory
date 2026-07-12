/**
 * P19-E1 D2 i18n — RTL layout validator.
 *
 * Verifies that:
 *   1. ar-SA locale is in the RTL_LOCALES set
 *   2. setLocale('ar-SA') sets dir="rtl" on <html>
 *   3. setLocale('zh-CN') resets dir="ltr" (no leakage)
 *   4. rtl.css file exists and contains the required direction declaration
 *   5. The 9 supported locales all switch cleanly without leaving stale state
 *      (i.e. document.documentElement.dir flips to ltr after a non-RTL set).
 *
 * This test runs under Vitest (frontend-v2 already wires up the
 * tests/**.spec.ts glob in vite.config.ts). jsdom provides the
 * document / window stubs.
 *
 * Run: cd frontend-v2 && npx vitest run tests/rtl_layout.spec.ts
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import {
  setLocale,
  getLocale,
  isRTL,
  RTL_LOCALES,
  SUPPORTED_LOCALES,
  applyDocumentDirection,
  i18n,
} from '@/locales'

const RTL_CSS_PATH = 'src/styles/rtl.css'

describe('RTL layout — locale switcher', () => {
  beforeEach(async () => {
    // Reset to a known baseline before every test.
    await setLocale('zh-CN')
    // jsdom starts with no <html dir=...>; simulate the bootstrap state.
    document.documentElement.removeAttribute('dir')
  })

  afterEach(() => {
    document.documentElement.removeAttribute('dir')
  })

  it('exposes ar-SA as the only RTL locale', () => {
    expect(RTL_LOCALES).toEqual(['ar-SA'])
    expect(isRTL('ar-SA')).toBe(true)
    expect(isRTL('en-US')).toBe(false)
    expect(isRTL('zh-CN')).toBe(false)
    expect(isRTL('ja-JP')).toBe(false)
  })

  it('switches <html dir="rtl"> when locale becomes ar-SA', async () => {
    await setLocale('ar-SA')
    expect(getLocale()).toBe('ar-SA')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
    expect(document.documentElement.getAttribute('lang')).toBe('ar-SA')
  })

  it('switches <html dir="ltr"> when locale returns to zh-CN', async () => {
    await setLocale('ar-SA')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
    await setLocale('zh-CN')
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
    expect(document.documentElement.getAttribute('lang')).toBe('zh-CN')
  })

  it('keeps <html dir="ltr"> for every non-RTL locale in SUPPORTED_LOCALES', async () => {
    const ltrLocales = SUPPORTED_LOCALES.filter((l) => !RTL_LOCALES.includes(l))
    expect(ltrLocales.length).toBeGreaterThan(0)
    for (const code of ltrLocales) {
      await setLocale(code)
      expect(document.documentElement.getAttribute('dir')).toBe('ltr')
      expect(document.documentElement.getAttribute('lang')).toBe(code)
    }
  })

  it('applyDocumentDirection() is idempotent (calling twice is a no-op)', () => {
    applyDocumentDirection('ar-SA')
    applyDocumentDirection('ar-SA')
    expect(document.documentElement.getAttribute('dir')).toBe('rtl')
    applyDocumentDirection('zh-CN')
    applyDocumentDirection('zh-CN')
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
  })

  it('9 locales round-trip cleanly without stale state', async () => {
    // Cross-product: switch to every locale in turn, then back to baseline.
    // No locale should leave <html dir> pointing the wrong way.
    for (const code of SUPPORTED_LOCALES) {
      await setLocale(code)
      const expectedDir = isRTL(code) ? 'rtl' : 'ltr'
      expect(document.documentElement.getAttribute('dir')).toBe(expectedDir)
    }
    await setLocale('zh-CN')
    expect(document.documentElement.getAttribute('dir')).toBe('ltr')
  })

  it('vue-i18n internal state stays in sync with setLocale()', async () => {
    await setLocale('ar-SA')
    expect(i18n.global.locale.value).toBe('ar-SA')
    await setLocale('en-US')
    expect(i18n.global.locale.value).toBe('en-US')
    await setLocale('ja-JP')
    expect(i18n.global.locale.value).toBe('ja-JP')
  })
})

describe('RTL layout — CSS asset', () => {
  it('rtl.css exists at frontend-v2/src/styles/rtl.css', async () => {
    // Vitest root is frontend-v2, so relative path resolves correctly.
    const fs = await import('node:fs/promises')
    const stat = await fs.stat(RTL_CSS_PATH)
    expect(stat.isFile()).toBe(true)
    expect(stat.size).toBeGreaterThan(100)
  })

  it('rtl.css declares direction: rtl for html[dir=rtl]', async () => {
    const fs = await import('node:fs/promises')
    const text = await fs.readFile(RTL_CSS_PATH, 'utf-8')
    // Both the global `html[dir='rtl']` selector and the literal property
    // are required for RTL to actually render.
    expect(text).toMatch(/html\[dir=['"]rtl['"]\]/)
    expect(text).toMatch(/direction:\s*rtl/)
    // And the mirrored font-family fallback for Arabic script
    expect(text).toMatch(/font-family/)
  })
})