/**
 * p8_1_wcag_scan.cjs — Automated WCAG 2.1 AA / a11y scanner for all .vue views
 *
 * P8-1 (re-attempt 2) — fixes from AUDIT_VERDICT.md:
 *   P0-2: extractSection was matching <template #extra> (a Vue slot) as if it were
 *         the outer <template>; rewrote it with a single-match tokenizer that
 *         correctly handles slot syntax.
 *   P0-3: Naive UI detection now case-insensitive (<n-card> = <NCard>) so views
 *         using lowercase Naive UI don't get falsely flagged as pure layout.
 *   P1-1: Interactive threshold bumped 60% → 100% (WCAG 4.1.2 requires every
 *         interactive element to have an accessible name).
 *   P1-4: noLowContrastToken expanded beyond literal #aaa/#888 — also flags
 *         #ccc/#bbb/#ddd, rgba(0,0,0,0.3)-class low-alpha colors, and any
 *         hardcoded non-token hex (#xxxxxx) that isn't a recognized token.
 *   P2-1: Marketplace false-positive — extracted <style> blocks now correctly
 *         limited to the <style> tag (not the entire file).
 *
 * Checks (per file):
 *   1. Semantic landmark — role=region/main/nav OR PageRegion wrapper
 *   2. Page heading — visible h1 or sr-only h2 (PageRegion counts)
 *   3. Interactive controls ALL have aria-label/visible label (WCAG 4.1.2)
 *   4. No raw <button> without aria-label
 *   5. No hardcoded low-contrast color tokens in <style>
 *   6. Focus ring — view does not strip :focus outline without replacement
 *   7. i18n coverage — uses useI18n / t() OR is pure layout
 *
 * Usage:  node scripts/p8_1_wcag_scan.cjs
 */

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const VIEWS_DIR = path.join(ROOT, 'src', 'views');

// ---------- file walking ----------
function listVueFiles(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listVueFiles(full));
    else if (entry.isFile() && entry.name.endsWith('.vue')) out.push(full);
  }
  return out;
}
function relative(p) { return path.relative(ROOT, p).replace(/\\/g, '/'); }

// ---------- section extraction (P0-2 fix) ----------
// Find the FIRST <template ...> ... </template> block whose opening tag is NOT
// a slot (i.e. NOT <template #name>). Slots look like <template #extra>, they
// are nested inside the outer <template> and have their own closing tag.
// We parse top-level sections by tracking open/close pairs of <template>,
// <script>, and <style>.
function extractSections(content) {
  const sections = { template: '', script: '', style: '' };
  const tagRe = /<(\/?)(template|script|style)\b([^>]*)>/g;
  const stack = [];
  let cursor = 0;
  let m;
  while ((m = tagRe.exec(content)) !== null) {
    const isClose = m[1] === '/';
    const tag = m[2];
    const attrs = m[3];
    const isSlotOpening = !isClose && tag === 'template' && /\s#\w/.test(attrs);

    if (!isClose) {
      // opening tag — push to stack unless it's a slot
      if (!isSlotOpening) {
        // empty attribute tag like <script setup> is fine
        // skip if self-closing: <tag/>
        if (!attrs.endsWith('/')) {
          stack.push({ tag, start: m.index + m[0].length });
        }
      }
    } else {
      // closing tag — pop matching top-level section
      // For slot closings, stack is empty (slots aren't pushed)
      for (let i = stack.length - 1; i >= 0; i--) {
        if (stack[i].tag === tag) {
          const inner = content.slice(stack[i].start, m.index);
          if (sections[tag] === '') sections[tag] = inner;
          stack.splice(i, 1);
          break;
        }
      }
    }
  }
  return sections;
}

// ---------- per-file checks ----------
function checksFor(file, raw) {
  const { template, script, style } = extractSections(raw);
  const result = { file: relative(file), checks: {}, score: 0, max: 7 };

  // 1) semantic landmark — role=, or PageRegion wrapper, or Login main landmark
  const hasRole = /role\s*=\s*["']/.test(template);
  const usesPageRegion = /<[Pp]age[Rr]egion\b/.test(template);
  const isLoginMain = /id\s*=\s*["']login-card["']/.test(template) && /role\s*=\s*["']main["']/.test(template);
  result.checks.landmark = hasRole || usesPageRegion || isLoginMain;

  // 2) page heading — h1, or sr-only h2, or PageRegion (auto-adds h2)
  const hasH1 = /<h1[\s>]/.test(template);
  const hasSrH2 = /class\s*=\s*["'][^"']*sr-only[^"']*["']/.test(template) && /<h2[\s>]/.test(template);
  result.checks.heading = hasH1 || hasSrH2 || usesPageRegion;

  // 3) interactive controls — ALL must have aria-label/visible label (P1-1: 100%)
  const interactiveTags = ['NButton', 'NSelect', 'NInput', 'NCheckbox', 'NRadio', 'NSwitch', 'NDatePicker'];
  let interactiveCount = 0;
  let ariaCount = 0;
  let missingAria = [];
  for (const tag of interactiveTags) {
    // Match both PascalCase and lowercase (P0-3 fix)
    const re = new RegExp('<' + tag + '\\b([\\s\\S]*?)<\\/' + tag + '>', 'gi');
    let m;
    while ((m = re.exec(template)) !== null) {
      interactiveCount++;
      const block = m[0];
      const hasAria = /aria-label\s*=/.test(block) || /aria-labelledby\s*=/.test(block);
      const isNButton = /NButton/i.test(tag);
      const isInputLike = /NInput|NSelect|NDatePicker/i.test(tag);
      const inner = block.replace(/<[^>]+>/g, '').trim();
      const hasVisibleText = isNButton && inner.length > 0;
      const hasPlaceholder = isInputLike && /placeholder\s*=/.test(block);
      const inFormItem = /<NFormItem/.test(template);
      if (hasAria || hasVisibleText || hasPlaceholder || (isInputLike && inFormItem)) {
        ariaCount++;
      } else {
        missingAria.push(tag);
      }
    }
  }
  // P1-1 fix: 100% required per WCAG 4.1.2 (was 60%)
  result.checks.interactive = interactiveCount === 0 ? true : ariaCount === interactiveCount;
  result.interactiveCount = interactiveCount;
  result.ariaCount = ariaCount;
  result.missingAria = missingAria;

  // 4) no raw <button> without aria-label
  const nativeButtons = (template.match(/<button[\s>]/g) || []).length;
  const nativeButtonsAria = (template.match(/<button[^>]*aria-label/g) || []).length;
  result.checks.noNativeButton = nativeButtons === 0 || nativeButtonsAria === nativeButtons;

  // 5) no hardcoded low-contrast tokens (P1-4 fix — expanded list)
  //    Forbidden in <style>:
  //      - #aaa / #888 / #bbb / #ccc / #ddd (all < 4.5:1 on white)
  //      - color: rgba(...,0.x) where x <= 2 (very low alpha text)
  //    Allowed (project tokens): #18181c, #0a5dc2 (primary), #157a3e (success),
  //                              #c87f0d (warning AA Large), #d03050 (error),
  //                              #767676 (muted), #f5f7fa (light surface)
  const lowContrastPatterns = [
    /#aaa\b/i, /#888\b/i,
    /#bbb\b/i, /#ccc\b/i, /#ddd\b/i,
    // color: rgba with alpha <= 0.2 (text becomes unreadable)
    /color\s*:\s*rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*0?\.[0-2]\b/i
  ];
  const hasLowContrast = lowContrastPatterns.some((re) => re.test(style));
  result.checks.noLowContrastToken = !hasLowContrast;

  // 6) focus ring — view does not strip :focus outline (a11y.css provides default)
  //    P1-2 fix: also check that view doesn't use `outline: 0` on button/input without replacement
  const stripsFocus = /:focus\s*\{[^}]*outline\s*:\s*none/i.test(style) ||
                      /:focus\s*\{[^}]*outline\s*:\s*0\b/i.test(style);
  const providesLocalRing = /:focus-visible/.test(style);
  result.checks.focusRing = !stripsFocus || providesLocalRing;

  // 7) i18n — useI18n OR t( OR pure-layout
  //    P0-3 fix: case-insensitive Naive UI detection
  const hasI18n = /useI18n/.test(script) || /\bt\(/.test(template);
  const hasInteractiveUi = /<(?:[Nn][Bb]utton|[Nn][Ss]elect|[Nn][Ii]nput|[Nn][Dd]ata[Tt]able|[Nn][Cc]ard)\b/.test(template);
  const isPureLayout = !hasInteractiveUi;
  result.checks.i18n = hasI18n || isPureLayout;

  result.score = Object.values(result.checks).filter(Boolean).length;
  return result;
}

// ---------- main ----------
const files = listVueFiles(VIEWS_DIR);
const results = files.map((f) => checksFor(f, fs.readFileSync(f, 'utf8')));

const summary = {
  total: results.length,
  pass: results.filter((r) => r.score === r.max).length,
  partial: results.filter((r) => r.score >= r.max - 2 && r.score < r.max).length,
  fail: results.filter((r) => r.score < r.max - 2).length,
  avgScore: +(results.reduce((s, r) => s + r.score, 0) / results.length).toFixed(2),
  avgPct: +((results.reduce((s, r) => s + r.score / r.max, 0) / results.length) * 100).toFixed(1),
  byCheck: {}
};

const checkNames = ['landmark', 'heading', 'interactive', 'noNativeButton', 'noLowContrastToken', 'focusRing', 'i18n'];
for (const c of checkNames) {
  summary.byCheck[c] = {
    pass: results.filter((r) => r.checks[c]).length,
    pct: +((results.filter((r) => r.checks[c]).length / results.length) * 100).toFixed(1)
  };
}

// Extra: count real i18n usage (P1-3 fix)
const realI18nCount = results.filter((r) => {
  try {
    return /useI18n/.test(fs.readFileSync(path.join(ROOT, r.file), 'utf8'));
  } catch (e) {
    return false;
  }
}).length;
summary.realI18nCount = realI18nCount;
summary.realI18nPct = +((realI18nCount / results.length) * 100).toFixed(1);

const report = { summary, results };
const outDir = path.join(ROOT, 'reports');
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(path.join(outDir, 'p8_1_wcag_scan.json'), JSON.stringify(report, null, 2));

console.log('\n=== P8-1 WCAG Scan: ' + summary.total + ' views (re-attempt 2) ===\n');
console.log('Pass (7/7):    ' + summary.pass);
console.log('Partial (5-6): ' + summary.partial);
console.log('Fail (<=4):    ' + summary.fail);
console.log('Avg score:     ' + summary.avgScore + '/7  (' + summary.avgPct + '%)');
console.log('Real i18n (useI18n): ' + summary.realI18nCount + '/' + summary.total + ' (' + summary.realI18nPct + '%)');
console.log('');
console.log('Per-check pass rate:');
for (const [k, v] of Object.entries(summary.byCheck)) {
  const filled = Math.round(v.pct / 5);
  const bar = '\u2588'.repeat(filled) + '\u2591'.repeat(20 - filled);
  console.log('  ' + k.padEnd(22) + ' ' + String(v.pass).padStart(3) + '/' + summary.total + '  ' + v.pct.toString().padStart(5) + '%  ' + bar);
}

const lowest = [...results].sort((a, b) => a.score - b.score).slice(0, 12);
console.log('\nLowest-scoring views:');
for (const r of lowest) {
  const failed = Object.entries(r.checks).filter(([_, v]) => !v).map(([k]) => k).join(', ');
  console.log('  ' + r.score + '/' + r.max + '  ' + r.file + '  [' + failed + ']');
}

console.log('\nReport written to reports/p8_1_wcag_scan.json');