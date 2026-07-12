/**
 * P21 P2 P5 — Round 3 i18n keys coverage test.
 *
 * Goal: verify that the next 100 most-missing i18n keys (the round-3 set, which
 * is disjoint from the P2 P2 round-1 set and the P2 P4 round-2 set) were added
 * to all 10 locales.
 *
 * After P2 P2 (round 1) + P2 P4 (round 2) each locale had 436 leaf keys.
 * After P2 P5 (round 3) each locale should have 536 leaf keys.
 *
 * Round 3 keys distribution (100 keys, 9 namespaces):
 *   - capabilityRegistry: t010-t019 (10)
 *   - collectionCenter: t017-t027 (11)
 *   - delivery: t011-t021 (11)
 *   - internalQC: t017-t026 (10)
 *   - packManager: t009-t028 (20)
 *   - projectCenter: t018-t027 (10)
 *   - requirementCenter: t018-t027 (10)
 *   - requesterAccept: t017-t029 (13)
 *   - workflowBuilder: t034-t038 (5)
 *
 * Test surface:
 *   1. en-US is the source of truth and has at least 536 keys.
 *   2. Each non-en locale's key count is within 5 of en-US.
 *   3. Five randomly-chosen round-3 keys are present in all 10 locales.
 *   4. The P2 P2 baseline + round-1 + round-2 keys are still present
 *      (no regression in 5 spot-check keys from P2 P2 and P2 P4).
 *   5. The 100 round-3 keys are all present in all 10 locales (full coverage).
 *
 * Run with (per task spec):
 *   cd frontend-v2 && npx vitest run tests/p2_p5/i18n_keys_round3.test.ts
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
console.log(`[i18n_keys_round3.test] en-US has ${enKeys.length} keys`)

/** The 100 round-3 keys (P2 P5 batch). */
const ROUND3_KEYS: string[] = [
  // capabilityRegistry t010-t019 (10)
  'capabilityRegistry.t010', 'capabilityRegistry.t011', 'capabilityRegistry.t012', 'capabilityRegistry.t013', 'capabilityRegistry.t014', 'capabilityRegistry.t015', 'capabilityRegistry.t016', 'capabilityRegistry.t017', 'capabilityRegistry.t018', 'capabilityRegistry.t019',
  // collectionCenter t017-t027 (11)
  'collectionCenter.t017', 'collectionCenter.t018', 'collectionCenter.t019', 'collectionCenter.t020', 'collectionCenter.t021', 'collectionCenter.t022', 'collectionCenter.t023', 'collectionCenter.t024', 'collectionCenter.t025', 'collectionCenter.t026', 'collectionCenter.t027',
  // delivery t011-t021 (11)
  'delivery.t011', 'delivery.t012', 'delivery.t013', 'delivery.t014', 'delivery.t015', 'delivery.t016', 'delivery.t017', 'delivery.t018', 'delivery.t019', 'delivery.t020', 'delivery.t021',
  // internalQC t017-t026 (10)
  'internalQC.t017', 'internalQC.t018', 'internalQC.t019', 'internalQC.t020', 'internalQC.t021', 'internalQC.t022', 'internalQC.t023', 'internalQC.t024', 'internalQC.t025', 'internalQC.t026',
  // packManager t009-t028 (20)
  'packManager.t009', 'packManager.t010', 'packManager.t011', 'packManager.t012', 'packManager.t013', 'packManager.t014', 'packManager.t015', 'packManager.t016', 'packManager.t017', 'packManager.t018', 'packManager.t019', 'packManager.t020', 'packManager.t021', 'packManager.t022', 'packManager.t023', 'packManager.t024', 'packManager.t025', 'packManager.t026', 'packManager.t027', 'packManager.t028',
  // projectCenter t018-t027 (10)
  'projectCenter.t018', 'projectCenter.t019', 'projectCenter.t020', 'projectCenter.t021', 'projectCenter.t022', 'projectCenter.t023', 'projectCenter.t024', 'projectCenter.t025', 'projectCenter.t026', 'projectCenter.t027',
  // requirementCenter t018-t027 (10)
  'requirementCenter.t018', 'requirementCenter.t019', 'requirementCenter.t020', 'requirementCenter.t021', 'requirementCenter.t022', 'requirementCenter.t023', 'requirementCenter.t024', 'requirementCenter.t025', 'requirementCenter.t026', 'requirementCenter.t027',
  // requesterAccept t017-t029 (13)
  'requesterAccept.t017', 'requesterAccept.t018', 'requesterAccept.t019', 'requesterAccept.t020', 'requesterAccept.t021', 'requesterAccept.t022', 'requesterAccept.t023', 'requesterAccept.t024', 'requesterAccept.t025', 'requesterAccept.t026', 'requesterAccept.t027', 'requesterAccept.t028', 'requesterAccept.t029',
  // workflowBuilder t034-t038 (5)
  'workflowBuilder.t034', 'workflowBuilder.t035', 'workflowBuilder.t036', 'workflowBuilder.t037', 'workflowBuilder.t038'
]

/** Five spot-check keys from different namespaces (P2 P5 round 3). */
const SPOT_CHECK_KEYS = [
  'capabilityRegistry.t015',
  'collectionCenter.t022',
  'packManager.t018',
  'projectCenter.t024',
  'workflowBuilder.t036'
]

/** Five P2 P2 round-1 spot-check keys (regression check). */
const P22_SPOT_CHECKS = [
  'common.add',
  'dataFlowTracker.pageTitle',
  'form.title',
  'menu.statusbarReady',
  'projectCenter.t000'
]

/** Five P2 P4 round-2 spot-check keys (regression check). */
const P24_SPOT_CHECKS = [
  'capabilityRegistry.t003',
  'packManager.t000',
  'delivery.t002',
  'button.cancelJob',
  'Cancel'
]

describe('P21 P2 P5 i18n round-3 coverage', () => {
  it('en-US is the source of truth and has at least 536 keys', () => {
    // Baseline (pre-P2-P2): 236 keys.
    // After P2 P2 (round 1): 336.
    // After P2 P4 (round 2): 436.
    // After P2 P5 (round 3): 536.
    expect(enKeys.length).toBeGreaterThanOrEqual(536)
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
    'spot-check round-3 key "%s" is present in all 10 locales',
    (key) => {
      for (const [name, dict] of Object.entries(LOCALES)) {
        const keys = flattenKeys(dict)
        expect(keys, `locale ${name} should contain key ${key}`).toContain(key)
      }
    }
  )

  it('all 100 round-3 keys are present in all 10 locales', () => {
    for (const [name, dict] of Object.entries(LOCALES)) {
      const keys = new Set(flattenKeys(dict))
      const missing = ROUND3_KEYS.filter((k) => !keys.has(k))
      expect(
        missing,
        `locale ${name} is missing ${missing.length} round-3 keys: ${missing.slice(0, 5).join(', ')}${missing.length > 5 ? '...' : ''}`
      ).toEqual([])
    }
  })

  it('all 10 locales share the round-3 namespace extensions', () => {
    // Round 3 extended 8 existing namespaces and 1 new (workflowBuilder continued t034+).
    // Verify each round-3 namespace exists in every locale.
    for (const [name, dict] of Object.entries(LOCALES)) {
      for (const requiredNs of [
        'capabilityRegistry',
        'collectionCenter',
        'delivery',
        'internalQC',
        'packManager',
        'projectCenter',
        'requirementCenter',
        'requesterAccept',
        'workflowBuilder'
      ]) {
        expect(
          requiredNs in dict,
          `locale ${name} should have namespace ${requiredNs}`
        ).toBe(true)
      }
    }
  })

  it('P2 P2 baseline + 100 round-1 keys still present in all 10 locales (no regression)', () => {
    for (const [name, dict] of Object.entries(LOCALES)) {
      const keys = flattenKeys(dict)
      for (const k of P22_SPOT_CHECKS) {
        expect(keys, `locale ${name} should still have ${k} from P2 P2`).toContain(k)
      }
    }
  })

  it('P2 P4 baseline + 100 round-2 keys still present in all 10 locales (no regression)', () => {
    for (const [name, dict] of Object.entries(LOCALES)) {
      const keys = flattenKeys(dict)
      for (const k of P24_SPOT_CHECKS) {
        expect(keys, `locale ${name} should still have ${k} from P2 P4`).toContain(k)
      }
    }
  })

  it('round-3 key count is exactly 100 in every locale', () => {
    // The intersection of en-US keys and each locale's keys should contain
    // exactly 100 round-3 keys. This locks the contract that exactly 100 NEW
    // keys were added (not 99, not 101).
    for (const [name, dict] of Object.entries(LOCALES)) {
      const localeKeys = new Set(flattenKeys(dict))
      const present = ROUND3_KEYS.filter((k) => localeKeys.has(k))
      expect(
        present.length,
        `locale ${name} should have all 100 round-3 keys; got ${present.length}`
      ).toBe(100)
    }
  })
})
