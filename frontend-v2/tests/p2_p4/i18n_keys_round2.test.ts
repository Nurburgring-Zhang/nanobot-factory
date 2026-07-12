/**
 * P21 P2 P4 — Round 2 i18n keys coverage test.
 *
 * Goal: verify that the next 100 most-missing i18n keys (the round-2 set, which
 * is disjoint from the P2 P2 round-1 set) were added to all 10 locales.
 *
 * Round 1 (P2 P2) added 100 keys; round 2 (P2 P4) adds the next 100. After both
 * rounds each locale should have 436 leaf keys (was 236 baseline + 100 P2 P2 +
 * 100 P2 P4 = 436).
 *
 * Test surface:
 *   1. en-US is the source of truth and has at least 436 keys.
 *   2. Each non-en locale's key count is within 5 of en-US.
 *   3. Five randomly-chosen keys from the round-2 set are present in all 10
 *      locales. The keys are picked from different namespaces to span the
 *      distribution (capabilityRegistry.*, packManager.*, delivery.*,
 *      button.*, top-level).
 *   4. The 6 NEW top-level namespaces introduced by round 2 are present in
 *      all 10 locales.
 *   5. The P2 P2 baseline + 100 round-1 keys are still present (no regression).
 *
 * Run with (per task spec):
 *   cd frontend-v2 && npx vitest run tests/p2_p4/i18n_keys_round2.test.ts
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
 * Top-level string values (no dot) are emitted as-is.
 * e.g. { a: { b: 'x', c: 'y' }, d: 'z' } => ['a.b', 'a.c', 'd']
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
console.log(`[i18n_keys_round2.test] en-US has ${enKeys.length} keys`)

/**
 * Spot-check keys: P2 P4 round 2 picks 5 keys from different namespaces.
 * - `capabilityRegistry.t003` (high-freq, custom translation)
 * - `packManager.t000` (new namespace, t000 in new ns)
 * - `delivery.t002` (extended existing namespace)
 * - `button.cancelJob` (new namespace)
 * - `Cancel` (top-level, no-namespace)
 */
const SPOT_CHECK_KEYS = [
  'capabilityRegistry.t003',
  'packManager.t000',
  'delivery.t002',
  'button.cancelJob',
  'Cancel'
]

describe('P21 P2 P4 i18n round-2 coverage', () => {
  it('en-US is the source of truth and has at least 436 keys', () => {
    // Baseline (pre-update): 236.
    // After P2 P2 (round 1): 336.
    // After P2 P4 (round 2): 436.
    expect(enKeys.length).toBeGreaterThanOrEqual(436)
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

  it('all 10 locales share the new round-2 namespaces', () => {
    // Round 2 introduced 3 new top-level namespaces and extended 3 existing ones.
    // The 6 new top-level namespaces that P2 P4 round-2 added or extended are:
    //   - agent (new)
    //   - agentManagement (new)
    //   - canvasDesigner (new)
    //   - button (new)
    //   - capabilityRegistry (extended with t000-t009)
    //   - packManager (new)
    for (const [name, dict] of Object.entries(LOCALES)) {
      for (const requiredNs of [
        'agent',
        'agentManagement',
        'canvasDesigner',
        'button',
        'capabilityRegistry',
        'packManager'
      ]) {
        expect(
          name in dict || requiredNs in dict,
          `locale ${name} should have namespace ${requiredNs}`
        ).toBe(true)
      }
    }
  })

  it('all 10 locales include the P2 P2 baseline + 100 round-1 keys (no regression)', () => {
    // The 5 spot-check keys from P2 P2 (round 1) must still resolve.
    const P22_SPOT_CHECKS = [
      'common.add',
      'dataFlowTracker.pageTitle',
      'form.title',
      'menu.statusbarReady',
      'projectCenter.t000'
    ]
    for (const [name, dict] of Object.entries(LOCALES)) {
      const keys = flattenKeys(dict)
      for (const k of P22_SPOT_CHECKS) {
        expect(keys, `locale ${name} should still have ${k} from P2 P2`).toContain(k)
      }
    }
  })

  it('all 10 locales have the round-2 unnamespaced keys at the TOP level (not under common)', () => {
    // vue-i18n resolves t('Cancel') by looking up the first segment at the top
    // level of the messages object. If we put the unnamespaced keys under
    // common, t('Cancel') would not find them.
    for (const k of ['Cancel', 'Close', 'Clear', 'Open', 'Retry']) {
      for (const [name, dict] of Object.entries(LOCALES)) {
        expect(
          k in dict,
          `locale ${name} should have top-level key ${k}`
        ).toBe(true)
      }
    }
  })
})
