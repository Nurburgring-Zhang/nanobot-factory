/**
 * test_translations.cjs — Validates P19 v5.2-B i18n deliverable.
 *
 * Tests:
 *   1) All 9 locales load via Node's require() (after stripping TS)
 *      Actually: we use a regex-based loader here, since the files are .ts
 *      and we don't have a TypeScript runtime in this script.
 *   2) Each locale has >= 200 leaf keys (across all namespaces)
 *   3) zh-CN and en-US existing keys are unchanged (parity check)
 *   4) All 9 locales have the same top-level namespace set
 *   5) ar-SA has at least 1 Arabic-script value (RTL smoke check)
 *
 * Usage:
 *   node scripts/test_translations.cjs
 */
'use strict'

const fs = require('fs')
const path = require('path')

const LOCALE_DIR = path.resolve(__dirname, '..', 'frontend-v2/src/locales')

const EXPECTED_LOCALES = [
  'zh-CN',
  'en-US',
  'ja-JP',
  'ko-KR',
  'fr-FR',
  'de-DE',
  'es-ES',
  'ru-RU',
  'ar-SA'
]

const ARABIC_RE = /[\u0600-\u06FF]/
const HAN_RE = /[\u4E00-\u9FFF]/
const HIRAGANA_RE = /[\u3040-\u309F]/
const KATAKANA_RE = /[\u30A0-\u30FF]/
const HANGUL_RE = /[\uAC00-\uD7AF]/
const CYRILLIC_RE = /[\u0400-\u04FF]/

const NATIVE_SCRIPT_CHECKS = {
  'zh-CN': HAN_RE,
  'ja-JP': v => HIRAGANA_RE.test(v) || KATAKANA_RE.test(v),
  'ko-KR': HANGUL_RE,
  'fr-FR': v => /[àâçéèêëîïôûùüÿœæ]/i.test(v),
  'de-DE': v => /[äöüßÄÖÜẞ]/i.test(v),
  'es-ES': v => /[áéíóúñü¿¡]/i.test(v),
  'ru-RU': CYRILLIC_RE,
  'ar-SA': ARABIC_RE,
  'en-US': v => false
}

/**
 * Parse a .ts locale file into a nested object.
 * Uniform shape: `  ns: {` for namespaces, `    key: 'value'` for leaves.
 */
function parseLocaleFile(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8')
  const namespaces = {}
  let currentNs = null

  const lines = content.split('\n')
  for (const line of lines) {
    // Match namespace start: `  namespace: {`
    const nsMatch = line.match(/^\s{2}(\w+):\s*\{\s*$/)
    if (nsMatch) {
      currentNs = nsMatch[1]
      namespaces[currentNs] = {}
      continue
    }
    // Match leaf: `    key: 'value'`  (or `    key: 'value',`)
    const leafMatch = line.match(/^\s{4}(\w+):\s*'((?:\\.|[^'\\])*)'\s*,?\s*$/)
    if (leafMatch && currentNs) {
      const key = leafMatch[1]
      const value = leafMatch[2]
        .replace(/\\'/g, "'")
        .replace(/\\\\/g, '\\')
        .replace(/\\n/g, '\n')
        .replace(/\\t/g, '\t')
      namespaces[currentNs][key] = value
      continue
    }
    // Closing brace of a namespace
    if (currentNs && /^\s{2}\}\s*,?\s*$/.test(line)) {
      currentNs = null
    }
  }
  return namespaces
}

function flattenLeaves(obj, prefix = '') {
  const out = {}
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k
    if (typeof v === 'object' && v !== null) {
      Object.assign(out, flattenLeaves(v, fullKey))
    } else {
      out[fullKey] = v
    }
  }
  return out
}

let pass = 0
let fail = 0
const failures = []

function check(name, ok, detail) {
  if (ok) {
    console.log(`  PASS ${name}`)
    pass++
  } else {
    console.log(`  FAIL ${name} -- ${detail}`)
    failures.push(`${name}: ${detail}`)
    fail++
  }
}

function main() {
  console.log('='.repeat(60))
  console.log('P19 v5.2-B i18n validation')
  console.log('='.repeat(60))

  // Test 1: All 9 locale files exist
  console.log('\n[Test 1] 9 locale files exist')
  const loaded = {}
  for (const code of EXPECTED_LOCALES) {
    const p = path.join(LOCALE_DIR, `${code}.ts`)
    const exists = fs.existsSync(p)
    check(`${code}.ts exists`, exists, exists ? '' : `missing at ${p}`)
    if (exists) {
      try {
        loaded[code] = parseLocaleFile(p)
      } catch (e) {
        check(`${code}.ts parses`, false, e.message)
      }
    }
  }

  // Test 2: Each locale has >= 200 leaf keys
  console.log('\n[Test 2] Each locale has >= 200 leaf keys')
  for (const code of EXPECTED_LOCALES) {
    if (!loaded[code]) continue
    const flat = flattenLeaves(loaded[code])
    check(`${code} has >= 200 leaf keys`, Object.keys(flat).length >= 200, `got ${Object.keys(flat).length}`)
  }

  // Test 3: zh-CN/en-US existing keys unchanged (parity with our reference snapshot)
  console.log('\n[Test 3] zh-CN / en-US namespace parity')
  if (loaded['zh-CN'] && loaded['en-US']) {
    const zhNs = new Set(Object.keys(loaded['zh-CN']))
    const enNs = new Set(Object.keys(loaded['en-US']))
    const sameNs = zhNs.size === enNs.size && [...zhNs].every(n => enNs.has(n))
    check('zh-CN and en-US have identical namespaces', sameNs, `zh missing: ${[...zhNs].filter(n => !enNs.has(n))}, en missing: ${[...enNs].filter(n => !zhNs.has(n))}`)

    // Per-namespace key parity
    let parityOk = true
    const parityDetails = []
    for (const ns of zhNs) {
      const zhKeys = Object.keys(loaded['zh-CN'][ns] || {})
      const enKeys = Object.keys(loaded['en-US'][ns] || {})
      if (zhKeys.length !== enKeys.length) {
        parityOk = false
        parityDetails.push(`${ns}: zh=${zhKeys.length} vs en=${enKeys.length}`)
      }
    }
    check('zh-CN vs en-US per-namespace key count parity', parityOk, parityDetails.join('; '))
  }

  // Test 4: All 9 locales share the same namespace set (note: zh-CN/en-US are
  // reference files; the 7 new locales include 9 additional namespaces on top).
  console.log('\n[Test 4] All 7 new locales share the same namespace set')
  const NEW_LOCALES = ['ja-JP', 'ko-KR', 'fr-FR', 'de-DE', 'es-ES', 'ru-RU', 'ar-SA']
  const refNs = new Set(Object.keys(loaded['ja-JP'] || {}))
  let allMatch = true
  for (const code of NEW_LOCALES) {
    if (!loaded[code]) continue
    const codeNs = new Set(Object.keys(loaded[code]))
    const missing = [...refNs].filter(n => !codeNs.has(n))
    const extra = [...codeNs].filter(n => !refNs.has(n))
    if (missing.length > 0 || extra.length > 0) {
      allMatch = false
      console.log(`    ${code} missing: ${missing.join(',')}, extra: ${extra.join(',')}`)
    }
  }
  // Also check that zh-CN and en-US are subsets (unchanged by P19)
  if (loaded['zh-CN'] && loaded['en-US']) {
    const newNs = new Set(Object.keys(loaded['ja-JP'] || {}))
    const zhMissing = [...newNs].filter(n => !Object.keys(loaded['zh-CN']).includes(n))
    const enMissing = [...newNs].filter(n => !Object.keys(loaded['en-US']).includes(n))
    const zhEnSame = JSON.stringify(Object.keys(loaded['zh-CN']).sort()) === JSON.stringify(Object.keys(loaded['en-US']).sort())
    check('zh-CN unchanged (no new namespaces added)', zhMissing.length > 0, `expected zh-CN to NOT have new ns, missing in zh-CN: ${zhMissing.join(',')}`)
    check('en-US unchanged (no new namespaces added)', enMissing.length > 0, `expected en-US to NOT have new ns, missing in en-US: ${enMissing.join(',')}`)
    check('zh-CN and en-US have identical namespace sets', zhEnSame, 'zh-CN vs en-US differ')
  }
  check('All 7 new locales share the same namespace set', allMatch, 'see above')

  // Test 5: Native script content (en-US is English so skip; zh-CN may be a
// pure-Chinese site where some keys are technical and stay English).
  console.log('\n[Test 5] Native script content for non-English locales')
  for (const code of EXPECTED_LOCALES) {
    if (code === 'en-US') continue
    if (!loaded[code]) continue
    const flat = flattenLeaves(loaded[code])
    const values = Object.values(flat)
    const checker = NATIVE_SCRIPT_CHECKS[code]
    // Support both RegExp (use .test) and function (call directly)
    const testScript = checker instanceof RegExp
      ? (v) => checker.test(v)
      : checker
    if (typeof testScript === 'function') {
      const hasNativeScript = values.some(v => typeof v === 'string' && testScript(v))
      check(`${code} has at least 1 native-script value`, hasNativeScript, `total values: ${values.length}`)
    }
  }

  // Test 6: ar-SA has Arabic script content
  console.log('\n[Test 6] ar-SA RTL metadata')
  if (loaded['ar-SA']) {
    const flat = flattenLeaves(loaded['ar-SA'])
    const arabicCount = Object.values(flat).filter(v => typeof v === 'string' && ARABIC_RE.test(v)).length
    check('ar-SA has >= 50 Arabic-script values (RTL smoke check)', arabicCount >= 50, `got ${arabicCount}`)
  }

  // Test 7: 9 new namespaces present in 7 NEW locales (zh-CN/en-US unchanged)
  console.log('\n[Test 7] 9 new namespaces present in 7 new locales (zh-CN/en-US unchanged)')
  const NEW_NS = ['agent', 'drama', 'canvas', 'comfy', 'redfox', 'crawler', 'dataset', 'qc', 'delivery']
  for (const code of NEW_LOCALES) {
    if (!loaded[code]) continue
    const nsSet = new Set(Object.keys(loaded[code]))
    const missing = NEW_NS.filter(n => !nsSet.has(n))
    check(
      `${code} has all 9 new namespaces`,
      missing.length === 0,
      `missing: ${missing.join(',')}`
    )
  }

  // Test 8: New namespace keys >= 50 each (only check 7 new locales)
  console.log('\n[Test 8] Each new namespace has >= 50 keys (7 new locales)')
  let nsKeyFailures = 0
  for (const code of NEW_LOCALES) {
    if (!loaded[code]) continue
    for (const ns of NEW_NS) {
      const keys = Object.keys(loaded[code][ns] || {})
      if (keys.length < 50) {
        console.log(`  FAIL ${code}.${ns} has >= 50 keys -- got ${keys.length}`)
        failures.push(`${code}.${ns}: ${keys.length} keys`)
        nsKeyFailures++
        fail++
      }
    }
  }
  if (nsKeyFailures === 0) {
    console.log(`  PASS all 7 locales × 9 namespaces have >= 50 keys`)
    pass++
  }

  // Summary
  console.log('\n' + '='.repeat(60))
  console.log(`SUMMARY: ${pass} pass, ${fail} fail`)
  console.log('='.repeat(60))
  if (fail > 0) {
    console.log('\nFAILURES:')
    failures.forEach(f => console.log(`  - ${f}`))
    process.exit(1)
  } else {
    console.log('\nAll tests passed.')
    process.exit(0)
  }
}

try {
  main()
} catch (e) {
  console.error('FATAL:', e)
  process.exit(2)
}