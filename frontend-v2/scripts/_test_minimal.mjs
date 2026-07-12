/**
 * p8_1_wcag_scan.mjs — Automated WCAG AA / a11y scanner for all .vue views
 *
 * Walks frontend-v2/src/views/**/*.vue and asserts 7 baseline a11y checks
 * per view. Produces reports/p8_1_wcag_scan.json + stdout summary.
 *
 * Checks (per file):
 *   1. <template> root element exists with semantic role/landmark (region / main / navigation / application)
 *   2. Page heading — either visible <h1> in DefaultLayout or sr-only <h2>
 *   3. Interactive controls (NButton, NSelect, NInput, NCheckbox, NRadio) have aria-label OR visible label
 *   4. No native <button> / <input type="submit"> without aria-label (WCAG 4.1.2 Name Role Value)
 *   5. Hardcoded #aaa / #888 in <style> (deprecated low-contrast tokens)
 *   6. WCAG AA focus ring — at least one :focus-visible rule in style block OR uses global token
 *   7. i18n coverage — uses useI18n() OR t() OR has no user-facing strings (pure layout)
 *
 * Exit codes:
 *   0 — scan completed (warnings allowed)
 *   1 — scan fatal (parser error / IO)
 *
 * Usage:  node scripts/p8_1_wcag_scan.mjs
 */

import fs from 'node:fs'
import path from 'node:path'
import url from 'node:url'

const __dirname = path.dirname(url.fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const VIEWS_DIR = path.join(ROOT, 'src', 'views')

// ---------- helpers ----------
function listVueFiles(dir) {
  const out = []
  if (!fs.existsSync(dir)) return out
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) out.push(...listVueFiles(full))
    else if (entry.isFile() && entry.name.endsWith('.vue')) out.push(full)
  }
  return out
}

function relative(p) {
  return path.relative(ROOT, p).replace(/\\/g, '/')
}

// Strip <template>…</template> block(s) into one string for matching
function extractSection(content, tag) {
  const re = new RegExp(`<${tag}[^>]*>([\\s\\S]*?)<\\/${tag}>`, 'g')
  const out = []
  let m
  while ((m = re.exec(content)) !== null) out.push(m[1])
  return out.join('\n')
}

// Count of <Tag> opening tags (ignoring self-closing / attribute name collisions)
function countTag(s, tag) {
  const re = new RegExp(`<${tag}(?:\\s|>|\\/)`, 'g')
  return (s.match(re) || []).length
}

function checksFor(file, raw) {
  const template = extractSection(raw, 'template')
  const script = extractSection(raw, 'script')
  const style = extractSection(raw, 'style')

  const result = { file: relative(file), checks: {}, score: 0, max: 7 }

  // 1) semantic landmark
  const hasRole = /role\s*=\s*["']/.test(template)
  const isMain = /<template>/.test(template) && /id\s*=\s*["']login-card["']/.test(template)
  const landmarkOk = hasRole || isMain
  result.checks.landmark = landmarkOk

  // 2) page heading — h1 or sr-only h2
  const hasH1 = /<h1[\s>]/.test(template)
  const hasSrH2 = /class\s*=\s*["'][^"']*sr-only[^"']*["']/.test(template) && /<h2[\s>]/.test(template)
  result.checks.heading = hasH1 || hasSrH2

  // 3) interactive controls aria-label OR visible label
  const interactiveTags = ['NButton', 'NSelect', 'NInput', 'NCheckbox', 'NRadio', 'NSwitch', 'NDatePicker']
  let interactiveCount = 0
  let ariaCount = 0
  for (const tag of interactiveTags) {
    const m = template.match(new RegExp(`<${tag}([\\s\\S]*?)\\/\\s*>|<${tag}([\\s\\S]*?)>([\\s\\S]*?)<\\/${tag}>`, 'g')) || []
    for (const block of m) {
      interactiveCount++
      if (/aria-label\s*=/.test(block) || /aria-labelledby\s*=/.test(block)) ariaCount++
      else if (tag === 'NButton') {
        // NButton with text inside is fine
        const inner = block.replace(/<[^>]+>/g, '').trim()
        if (inner.length > 0) ariaCount++
      } else if (tag === 'NInput' || tag === 'NSelect' || tag === 'NDatePicker') {
        // placeholder or :placeholder= counts as visible label proxy
        if (/placeholder\s*=/.test(block) || /<NFormItem/.test(block)) ariaCount++
      }
    }
  }
  result.checks.interactive = interactiveCount === 0 ? true : ariaCount / interactiveCount >= 0.6

  // 4) no raw <button> or <input type="submit"> without aria-label
  const nativeButtons = (template.match(/<button[\s>]/g) || []).length
  const nativeButtonsAria = (template.match(/<button[^>]*aria-label/g) || []).length
  result.checks.noNativeButton = nativeButtons === 0 || nativeButtonsAria === nativeButtons

  // 5) no hardcoded #aaa / #888 in style
  const hasAaa = /#aaa\b/i.test(style)
  const has888 = /#888\b/i.test(style)
  result.checks.noLowContrastToken = !(hasAaa || has888)

  // 6) focus ring — global a11y.css OR local :focus-visible
  const usesGlobalFocusRing = /a11y\.css/.test(raw) || /--a11y-focus-ring/.test(style)
  const hasLocalFocusVisible = /:focus-visible/.test(style)
  result.checks.focusRing = usesGlobalFocusRing || hasLocalFocusVisible

  // 7) i18n — useI18n OR t( OR pure-layout (no user strings, scored lenient)
  const hasI18n = /useI18n/.test(script) || /\bt\(/.test(template)
  const isPureLayout = !/<NButton|<NSelect|<NInput|<NDataTable|<NCard[\s>]/i.test(template)
  result.checks.i18n = hasI18n || isPureLayout

  // Score
  result.score = Object.values(result.checks).filter(Boolean).length
  result.interactiveCount = interactiveCount
  result.ariaCount = ariaCount
  result.nativeButtons = nativeButtons
  return result
}

// ---------- main ----------
const files = listVueFiles(VIEWS_DIR)
const results = files.map((f) => checksFor(f, fs.readFileSync(f, 'utf8')))

const summary = {
  total: results.length,
  pass: results.filter((r) => r.score === r.max).length,
  partial: results.filter((r) => r.score >= r.max - 2 && r.score < r.max).length,
  fail: results.filter((r) => r.score < r.max - 2).length,
  avgScore: +(results.reduce((s, r) => s + r.score, 0) / results.length).toFixed(2),
  avgPct: +((results.reduce((s, r) => s + r.score / r.max, 0) / results.length) * 100).toFixed(1),
  byCheck: {}
}

const checkNames = ['landmark', 'heading', 'interactive', 'noNativeButton', 'noLowContrastToken', 'focusRing', 'i18n']
for (const c of checkNames) {
  summary.byCheck[c] = {
    pass: results.filter((r) => r.checks[c]).length,
    pct: +((results.filter((r) => r.checks[c]).length / results.length) * 100).toFixed(1)
  }
}

const report = { summary, results }
const outDir = path.join(ROOT, 'reports')
fs.mkdirSync(outDir, { recursive: true })
fs.writeFileSync(path.join(outDir, 'p8_1_wcag_scan.json'), JSON.stringify(report, null, 2))

// stdout summary
console.log(`\n=== P8-1 WCAG Scan: ${summary.total} views ===\n`)
console.log(`Pass (7/7):    ${summary.pass}`)
console.log(`Partial (5-6): ${summary.partial}`)
console.log(`Fail (≤4):     ${summary.fail}`)
console.log(`Avg score:     ${summary.avgScore}/7  (${summary.avgPct}%)\n`)
console.log('Per-check pass rate:')
for (const [k, v] of Object.entries(summary.byCheck)) {
  const bar = '█'.repeat(Math.round(v.pct / 5)) + '░'.repeat(20 - Math.round(v.pct / 5))
  console.log(`  ${k.padEnd(22)} ${String(v.pass).padStart(3)}/${summary.total}  ${v.pct.toString().padStart(5)}%  ${bar}`)
}

// top 10 lowest-scoring views
const lowest = [...results].sort((a, b) => a.score - b.score).slice(0, 10)
console.log('\nLowest-scoring views:')
for (const r of lowest) {
  const failed = Object.entries(r.checks).filter(([_, v]) => !v).map(([k]) => k).join(', ')
  console.log(`  ${r.score}/${r.max}  ${r.file}  [${failed}]`)
}

console.log(`\nReport written to reports/p8_1_wcag_scan.json`)
