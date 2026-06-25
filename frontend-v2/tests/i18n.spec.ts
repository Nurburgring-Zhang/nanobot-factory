/**
 * Locale switch integration test.
 *
 * Verifies that switching between zh-CN and en-US via setLocale() actually
 * updates vue-i18n's global locale value (which is what useI18n() reads).
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setLocale, getLocale, i18n, SUPPORTED_LOCALES } from '@/locales'

describe('locale switching', () => {
  beforeEach(() => {
    // Reset to baseline before each test so they are order-independent.
    return setLocale('zh-CN')
  })

  it('starts at zh-CN', () => {
    expect(getLocale()).toBe('zh-CN')
  })

  it('switches to en-US', async () => {
    await setLocale('en-US')
    expect(getLocale()).toBe('en-US')
    expect(i18n.global.locale.value).toBe('en-US')
  })

  it('switches back to zh-CN', async () => {
    await setLocale('en-US')
    await setLocale('zh-CN')
    expect(getLocale()).toBe('zh-CN')
  })

  it('falls back to en-US when given an unsupported locale', async () => {
    // setLocale() accepts only 'zh-CN' | 'en-US' but we cast through unknown
    // to assert the runtime guard.
    await setLocale('xx-XX' as any)
    expect(getLocale()).toBe('en-US')
  })

  it('exposes both supported locales', () => {
    expect(SUPPORTED_LOCALES).toEqual(['zh-CN', 'en-US'])
  })
})