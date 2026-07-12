/**
 * P21 P2 P2 — Top-100 i18n keys coverage test.
 *
 * Goal: verify that the 100 most-missing i18n keys were added to all 10 locales
 * (en-US, zh-CN, ja-JP, ko-KR, fr-FR, de-DE, es-ES, ru-RU, ar-SA, pt-PT).
 *
 * Test surface:
 *   1. en-US is the source of truth and has at least 336 keys.
 *   2. Each non-en locale's key count is within 5 of en-US.
 *   3. Five randomly-chosen keys from the top-100 are present in all 10 locales.
 *   4. All 10 locales share the same 12 top-level namespaces.
 *
 * Run with (per task spec):
 *   cd frontend-v2 && npx vitest run tests/p2_p2/i18n_keys.test.ts
 */
import { describe, it, expect } from 'vitest'
import enUS from '@/locales/en-US'
import zhCN from '@/locales/zh-CN'
import jaJP from '@/locales/ja-JP'
import koKR from '@/locales/ko-KR'
import frFR from '@/locales/fr-FR'
import deDE from '@/locales/de-DE'
import esES from '@/locales/es-ES'
import ruRU from '@/locales/ru-RU'
import arSA from '@/locales/ar-SA'
import ptPT from '@/locales/pt-PT'

// Type for a locale messages object: a recursive record of strings.
type LocaleDict = Record<string, any>

const LOCALES: Record<string, LocaleDict> = {
  'en-US': enUS,
  'zh-CN': zhCN,
  'ja-JP': jaJP,
  'ko-KR': koKR,
  'fr-FR': frFR,
  'de-DE': deDE,
  'es-ES': esES,
  'ru-RU': ruRU,
  'ar-SA': arSA,
  'pt-PT': ptPT
}

/**
 * Walk a nested object and emit all leaf keys as dotted paths.
 * e.g. { a: { b: 'x', c: 'y' } } => ['a.b', 'a.c']
 */
function flattenKeys(obj: LocaleDict, prefix: string = ''): string[] {
  const out: string[] = []
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      out.push(...flattenKeys(v as LocaleDict, full))
    } else if (typeof v === 'string') {
      out.push(full)
    }
  }
  return out
}

const enKeys = flattenKeys(enUS)
console.log(`[i18n_keys.test] en-US has ${enKeys.length} keys`)

// The 5 spot-check keys. Picked from different namespaces to span the top-100
// distribution (common.*, dataFlowTracker.*, form.*, menu.*, view.t***).
const SPOT_CHECK_KEYS = [
  'common.add',
  'dataFlowTracker.pageTitle',
  'form.title',
  'menu.statusbarReady',
  'projectCenter.t000'
]

describe('P21 P2 P2 i18n top-100 coverage', () => {
  it('en-US is the source of truth and has at least 336 keys', () => {
    // Original baseline (pre-update): 236 keys.
    // After adding 100 new keys: 336 keys.
    expect(enKeys.length).toBeGreaterThanOrEqual(336)
  })

  it.each(
    Object.entries(LOCALES).filter(([name]) => name !== 'en-US')
  )('%s key count is within 5 of en-US', (_name, dict) => {
    const keys = flattenKeys(dict)
    const diff = Math.abs(keys.length - enKeys.length)
    // Allow a small drift for the "tolerated near-miss" range. Task spec: "within 5".
    expect(diff).toBeLessThanOrEqual(5)
  })

  it.each(SPOT_CHECK_KEYS)(
    'spot-check key "%s" is present in all 10 locales',
    (key) => {
      for (const [name, dict] of Object.entries(LOCALES)) {
        const keys = flattenKeys(dict)
        expect(keys, `locale ${name} should contain key ${key}`).toContain(key)
      }
    }
  )

  it('all 10 locales share the same set of top-level namespaces', () => {
    const namespaces = Object.keys(enUS).sort()
    for (const [name, dict] of Object.entries(LOCALES)) {
      const ns = Object.keys(dict).sort()
      // The 12 new namespaces we added must be present in every locale.
      for (const requiredNs of [
        'common',
        'dataFlowTracker',
        'form',
        'menu',
        'multimodalAgentChat',
        'userManagement',
        'projectCenter',
        'requirementCenter',
        'internalQC',
        'requesterAccept',
        'collectionCenter',
        'delivery'
      ]) {
        expect(ns, `locale ${name} should have namespace ${requiredNs}`).toContain(
          requiredNs
        )
      }
      // Also verify no extra namespaces (compared to en-US) — we did not add any.
      const extras = ns.filter((n) => !namespaces.includes(n))
      expect(extras, `locale ${name} has extra namespaces: ${extras}`).toEqual([])
    }
  })

  it('pt-PT (Portuguese) is registered as the 10th locale', () => {
    // Sanity: pt-PT was the explicit task spec requirement.
    const ptKeys = flattenKeys(ptPT)
    expect(ptKeys.length).toBeGreaterThanOrEqual(336)
    // Spot-check: "Adicionar" is the Portuguese translation of "common.add"
    expect(ptPT.common.add).toBe('Adicionar')
  })
})
