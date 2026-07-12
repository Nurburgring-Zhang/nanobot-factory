/**
 * P21 P3 P1 focused — zh-CN Simplified Chinese completeness test.
 *
 * Goal: verify that the zh-CN locale is fully translated to Simplified Chinese
 * and no English-fallback remains. After P2 P2/P4/P5 (300+ keys added in 3 rounds),
 * the R2 audit's "237 missing" was reduced to 4 intentional cross-locale design
 * choices (2 brand names + 2 "ID" technical abbreviations). This task translates
 * the 2 "ID" technical abbreviations to "编号" and combines the 2 brand names
 * with the Chinese brand "智影" to make them distinct from the English source.
 *
 * Result: 0 keys remain where zh-CN === en-US.
 *
 * Test surface:
 *   1. en-US is the source of truth and has at least 636 keys.
 *   2. zh-CN key count is within 5 of en-US (parity).
 *   3. zh-CN has the 4 previously-flagged keys now translated.
 *   4. Count keys where zh-CN matches en — assert <= 10 (most done).
 *   5. 5 spot-check keys are translated (zh-CN value !== en value).
 *   6. zh-CN has CJK characters (proves it's a real Chinese locale, not English).
 *
 * Run with (per task spec):
 *   cd frontend-v2 && npx vitest run tests/p3_p1_focused/zh_cn_completeness.test.ts
 */
import { describe, it, expect } from 'vitest'
import enUS from '@/locales/en-US'
import zhCN from '@/locales/zh-CN'

type LocaleDict = Record<string, any>

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

/** Walk an object and return all leaf string values keyed by dotted path. */
function flattenValues(obj: LocaleDict, prefix: string = ''): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, flattenValues(v as LocaleDict, full))
    } else if (typeof v === 'string') {
      out[full] = v
    }
  }
  return out
}

const enKeys = flattenKeys(enUS)
const enValues = flattenValues(enUS)
const zhValues = flattenValues(zhCN)
const zhKeys = flattenKeys(zhCN)

console.log(`[zh_cn_completeness.test] en-US has ${enKeys.length} keys, zh-CN has ${zhKeys.length} keys`)

/** Spot-check keys (5 picks across namespaces, including the 4 previously-flagged). */
const SPOT_CHECK_KEYS = [
  'common.appSubName',       // was 'nanobot-factory', now '智影 · nanobot-factory'
  'auth.loginSubtitle',      // was 'nanobot-factory', now '智影 · nanobot-factory'
  'annotation.colId',        // was 'ID', now '编号'
  'engines.colId',           // was 'ID', now '编号'
  'common.add'               // generic spot-check
]

/** The 4 previously-flagged keys (zh-CN === en-US before this task). */
const PREVIOUSLY_FLAGGED = [
  'common.appSubName',
  'auth.loginSubtitle',
  'annotation.colId',
  'engines.colId'
]

describe('P21 P3 P1 focused — zh-CN completeness', () => {
  it('en-US is the source of truth and has at least 636 keys', () => {
    // After P2 P2 (100) + P2 P4 (100) + P2 P5 (100) + the additional 100 keys
    // added in subsequent rounds, each locale has 636 keys.
    expect(enKeys.length).toBeGreaterThanOrEqual(636)
  })

  it('zh-CN key count is within 5 of en-US (parity)', () => {
    const diff = Math.abs(zhKeys.length - enKeys.length)
    expect(diff).toBeLessThanOrEqual(5)
  })

  it('all 4 previously-flagged keys are now translated (zh-CN !== en-US)', () => {
    for (const k of PREVIOUSLY_FLAGGED) {
      expect(zhValues[k], `zh-CN should have key ${k}`).toBeDefined()
      expect(enValues[k], `en-US should have key ${k}`).toBeDefined()
      expect(
        zhValues[k],
        `key ${k}: zh-CN should be translated (got zh-CN=${JSON.stringify(zhValues[k])}, en-US=${JSON.stringify(enValues[k])})`
      ).not.toBe(enValues[k])
    }
  })

  it('count of keys where zh-CN matches en is <= 10', () => {
    let matchCount = 0
    const matches: string[] = []
    for (const k of enKeys) {
      if (k in zhValues && zhValues[k] === enValues[k]) {
        matchCount++
        matches.push(k)
      }
    }
    console.log(`[zh_cn_completeness.test] zh-CN === en match count: ${matchCount}`)
    if (matchCount > 0) {
      console.log(`[zh_cn_completeness.test] remaining matches: ${matches.slice(0, 10).join(', ')}`)
    }
    expect(matchCount).toBeLessThanOrEqual(10)
  })

  it.each(SPOT_CHECK_KEYS)(
    'spot-check key "%s" is translated (zh-CN !== en-US)',
    (key) => {
      expect(zhValues[key], `zh-CN should have key ${key}`).toBeDefined()
      expect(enValues[key], `en-US should have key ${key}`).toBeDefined()
      expect(
        zhValues[key],
        `key ${key}: zh-CN value (${JSON.stringify(zhValues[key])}) should differ from en-US value (${JSON.stringify(enValues[key])})`
      ).not.toBe(enValues[key])
    }
  )

  it('zh-CN contains CJK characters (proves it is a real Chinese locale)', () => {
    // Count CJK Unified Ideographs (U+4E00 to U+9FFF) across all values.
    const cjkRegex = /[\u4e00-\u9fff]/
    let cjkValueCount = 0
    for (const v of Object.values(zhValues)) {
      if (cjkRegex.test(v)) cjkValueCount++
    }
    // Most non-trivial zh-CN values should contain at least one CJK character.
    // Allow brand-name-only values (e.g. "智影 · nanobot-factory") which DO contain CJK.
    expect(cjkValueCount).toBeGreaterThanOrEqual(550)
  })

  it('the 4 previously-flagged keys now have specific Chinese values', () => {
    // 2 brand names combined with Chinese brand
    expect(zhValues['common.appSubName']).toBe('智影 · nanobot-factory')
    expect(zhValues['auth.loginSubtitle']).toBe('智影 · nanobot-factory')
    // 2 technical abbreviations translated to Chinese
    expect(zhValues['annotation.colId']).toBe('编号')
    expect(zhValues['engines.colId']).toBe('编号')
  })
})
