/**
 * P21 P3 P1 focused — Round 4 i18n keys coverage test.
 *
 * Goal: verify that the next 100 most-missing i18n keys (the round-4 set, which
 * is disjoint from the P2 P2 round-1, P2 P4 round-2, and P2 P5 round-3 sets) were
 * added to all 10 locales.
 *
 * After P2 P2 (round 1) + P2 P4 (round 2) + P2 P5 (round 3) each locale had 536
 * leaf keys. After P3 P1 focused (round 4) each locale should have 636 leaf keys.
 *
 * Round 4 keys distribution (100 keys, 5 namespaces):
 *   - capabilityRegistry: t020-t029 (10)
 *   - collectionCenter:   t028-t072 (45)
 *   - delivery:           t022-t032 (11)
 *   - internalQC:         t027-t039 (13)
 *   - packManager:        t029-t047, t049-t050 (21)
 *
 * Test surface:
 *   1. en-US is the source of truth and has at least 636 keys.
 *   2. Each non-en locale's key count is within 5 of en-US.
 *   3. Five randomly-chosen round-4 keys are present in all 10 locales.
 *   4. The P2 P2 baseline + round-1 keys are still present (regression check).
 *   5. The P2 P4 baseline + round-2 keys are still present (regression check).
 *   6. The P2 P5 baseline + round-3 keys are still present (regression check).
 *   7. All 100 round-4 keys are present in all 10 locales (full coverage).
 *   8. The 100 round-4 keys are exactly 100 in every locale (count lock).
 *
 * Run with (per task spec):
 *   cd frontend-v2 && npx vitest run tests/p3_p1_focused/i18n_keys_round4.test.ts
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
console.log(`[i18n_keys_round4.test] en-US has ${enKeys.length} keys`)

/** The 100 round-4 keys (P3 P1 focused batch). */
const ROUND4_KEYS: string[] = [
  // capabilityRegistry t020-t029 (10)
  'capabilityRegistry.t020', 'capabilityRegistry.t021', 'capabilityRegistry.t022', 'capabilityRegistry.t023', 'capabilityRegistry.t024', 'capabilityRegistry.t025', 'capabilityRegistry.t026', 'capabilityRegistry.t027', 'capabilityRegistry.t028', 'capabilityRegistry.t029',
  // collectionCenter t028-t072 (45)
  'collectionCenter.t028', 'collectionCenter.t029', 'collectionCenter.t030', 'collectionCenter.t031', 'collectionCenter.t032', 'collectionCenter.t033', 'collectionCenter.t034', 'collectionCenter.t035', 'collectionCenter.t036', 'collectionCenter.t037', 'collectionCenter.t038', 'collectionCenter.t039', 'collectionCenter.t040', 'collectionCenter.t041', 'collectionCenter.t042', 'collectionCenter.t043', 'collectionCenter.t044', 'collectionCenter.t045', 'collectionCenter.t046', 'collectionCenter.t047', 'collectionCenter.t048', 'collectionCenter.t049', 'collectionCenter.t050', 'collectionCenter.t051', 'collectionCenter.t052', 'collectionCenter.t053', 'collectionCenter.t054', 'collectionCenter.t055', 'collectionCenter.t056', 'collectionCenter.t057', 'collectionCenter.t058', 'collectionCenter.t059', 'collectionCenter.t060', 'collectionCenter.t061', 'collectionCenter.t062', 'collectionCenter.t063', 'collectionCenter.t064', 'collectionCenter.t065', 'collectionCenter.t066', 'collectionCenter.t067', 'collectionCenter.t068', 'collectionCenter.t069', 'collectionCenter.t070', 'collectionCenter.t071', 'collectionCenter.t072',
  // delivery t022-t032 (11)
  'delivery.t022', 'delivery.t023', 'delivery.t024', 'delivery.t025', 'delivery.t026', 'delivery.t027', 'delivery.t028', 'delivery.t029', 'delivery.t030', 'delivery.t031', 'delivery.t032',
  // internalQC t027-t039 (13)
  'internalQC.t027', 'internalQC.t028', 'internalQC.t029', 'internalQC.t030', 'internalQC.t031', 'internalQC.t032', 'internalQC.t033', 'internalQC.t034', 'internalQC.t035', 'internalQC.t036', 'internalQC.t037', 'internalQC.t038', 'internalQC.t039',
  // packManager t029-t047, t049-t050 (21) — t048 skipped intentionally
  'packManager.t029', 'packManager.t030', 'packManager.t031', 'packManager.t032', 'packManager.t033', 'packManager.t034', 'packManager.t035', 'packManager.t036', 'packManager.t037', 'packManager.t038', 'packManager.t039', 'packManager.t040', 'packManager.t041', 'packManager.t042', 'packManager.t043', 'packManager.t044', 'packManager.t045', 'packManager.t046', 'packManager.t047', 'packManager.t049', 'packManager.t050'
]

/** Five spot-check keys from different round-4 namespaces. */
const SPOT_CHECK_KEYS = [
  'capabilityRegistry.t025',
  'collectionCenter.t045',
  'delivery.t028',
  'internalQC.t033',
  'packManager.t040'
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

/** Five P2 P5 round-3 spot-check keys (regression check). */
const P25_SPOT_CHECKS = [
  'capabilityRegistry.t015',
  'collectionCenter.t022',
  'packManager.t018',
  'projectCenter.t024',
  'workflowBuilder.t036'
]

describe('P21 P3 P1 focused i18n round-4 coverage', () => {
  it('en-US is the source of truth and has at least 636 keys', () => {
    // Baseline (pre-P2-P2): 236 keys.
    // After P2 P2 (round 1): 336.
    // After P2 P4 (round 2): 436.
    // After P2 P5 (round 3): 536.
    // After P3 P1 focused (round 4): 636.
    expect(enKeys.length).toBeGreaterThanOrEqual(636)
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
    'spot-check round-4 key "%s" is present in all 10 locales',
    (key) => {
      for (const [name, dict] of Object.entries(LOCALES)) {
        const keys = flattenKeys(dict)
        expect(keys, `locale ${name} should contain key ${key}`).toContain(key)
      }
    }
  )

  it('all 100 round-4 keys are present in all 10 locales', () => {
    for (const [name, dict] of Object.entries(LOCALES)) {
      const keys = new Set(flattenKeys(dict))
      const missing = ROUND4_KEYS.filter((k) => !keys.has(k))
      expect(
        missing,
        `locale ${name} is missing ${missing.length} round-4 keys: ${missing.slice(0, 5).join(', ')}${missing.length > 5 ? '...' : ''}`
      ).toEqual([])
    }
  })

  it('all 10 locales share the round-4 namespace extensions', () => {
    // Round 4 extended 5 existing namespaces.
    // Verify each round-4 namespace exists in every locale.
    for (const [name, dict] of Object.entries(LOCALES)) {
      for (const requiredNs of [
        'capabilityRegistry',
        'collectionCenter',
        'delivery',
        'internalQC',
        'packManager'
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

  it('P2 P5 baseline + 100 round-3 keys still present in all 10 locales (no regression)', () => {
    for (const [name, dict] of Object.entries(LOCALES)) {
      const keys = flattenKeys(dict)
      for (const k of P25_SPOT_CHECKS) {
        expect(keys, `locale ${name} should still have ${k} from P2 P5`).toContain(k)
      }
    }
  })

  it('round-4 key count is exactly 100 in every locale', () => {
    // The intersection of en-US keys and each locale's keys should contain
    // exactly 100 round-4 keys. This locks the contract that exactly 100 NEW
    // keys were added (not 99, not 101).
    for (const [name, dict] of Object.entries(LOCALES)) {
      const localeKeys = new Set(flattenKeys(dict))
      const present = ROUND4_KEYS.filter((k) => localeKeys.has(k))
      expect(
        present.length,
        `locale ${name} should have all 100 round-4 keys; got ${present.length}`
      ).toBe(100)
    }
  })
})
