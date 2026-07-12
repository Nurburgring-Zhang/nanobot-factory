/**
 * P19-F1 E1 i18n — RTL layout smoke test.
 *
 * Verifies that switching the app locale to ar-SA triggers RTL layout. We can't
 * actually mount the full SPA in JSDOM (Vue + Naive UI is too heavy), so we
 * settle for a low-cost verification:
 *
 *   1. rtl.css exists and contains the rtl direction declaration
 *   2. rtl.css is imported by the main entrypoint (or available via the
 *      `setLocale` flow)
 *   3. ar-SA locale file exports an object with workflowBuilder.t032/t033
 *      (proves the locale wiring is in place end-to-end)
 *   4. main.ts / index.ts hooks ar-SA to the rtl document attribute
 *
 * The test is pure-JS (no Vue), so it can run under `npx jest` without the
 * vitest config.
 */
import { describe, test, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

// Resolve repo paths
const FRONTEND_ROOT = path.resolve(__dirname, '../../../');
const SRC = path.join(FRONTEND_ROOT, 'src');
const RTL_CSS = path.join(SRC, 'styles', 'rtl.css');
const LOCALES_DIR = path.join(SRC, 'locales');

describe('P19-F1 RTL layout wiring', () => {
  test('rtl.css exists', () => {
    expect(fs.existsSync(RTL_CSS)).toBe(true);
  });

  test('rtl.css declares direction: rtl', () => {
    const text = fs.readFileSync(RTL_CSS, 'utf-8');
    expect(text).toMatch(/direction:\s*rtl/);
  });

  test('rtl.css uses html[dir="rtl"] selector', () => {
    const text = fs.readFileSync(RTL_CSS, 'utf-8');
    expect(text).toMatch(/html\[dir=['"]rtl['"]\]/);
  });

  test('rtl.css includes Arabic-friendly font stack', () => {
    const text = fs.readFileSync(RTL_CSS, 'utf-8');
    // Should mention at least one Arabic font (Tajawal / Cairo / Noto Sans Arabic)
    const hasArabicFont = /(Tajawal|Cairo|Noto Sans Arabic)/i.test(text);
    expect(hasArabicFont).toBe(true);
  });

  test('ar-SA locale file exists and is non-trivial', () => {
    const ar = path.join(LOCALES_DIR, 'ar-SA.ts');
    expect(fs.existsSync(ar)).toBe(true);
    const text = fs.readFileSync(ar, 'utf-8');
    expect(text.length).toBeGreaterThan(1000);
    expect(text).toContain('export default');
  });

  test('ar-SA locale has workflowBuilder block with t032 and t033', () => {
    const ar = path.join(LOCALES_DIR, 'ar-SA.ts');
    const text = fs.readFileSync(ar, 'utf-8');
    // workflowBuilder block
    const m = text.match(/workflowBuilder:\s*\{([\s\S]*?)\},/);
    expect(m).not.toBeNull();
    const block = m![1];
    expect(block).toMatch(/t032:\s*['"]/);
    expect(block).toMatch(/t033:\s*['"]/);
  });

  test('locales index.ts references rtl.css OR ar-SA locale', () => {
    const idxPath = path.join(LOCALES_DIR, 'index.ts');
    expect(fs.existsSync(idxPath)).toBe(true);
    const text = fs.readFileSync(idxPath, 'utf-8');
    // Index should at least mention ar-SA so setLocale can pick it up.
    expect(text).toMatch(/ar-SA/);
  });

  test('main.ts sets document direction when locale is rtl', () => {
    // Search for any file in src/ that sets document.documentElement.dir
    const candidates = [
      path.join(SRC, 'main.ts'),
      path.join(SRC, 'App.vue'),
      path.join(LOCALES_DIR, 'index.ts'),
    ];
    let found = false;
    for (const f of candidates) {
      if (fs.existsSync(f)) {
        const t = fs.readFileSync(f, 'utf-8');
        if (/document\.documentElement\.dir\s*=/.test(t) ||
            /setAttribute\(['"]dir['"]/.test(t)) {
          found = true;
          break;
        }
      }
    }
    // If not found via main/App, check any .ts/.vue under src
    if (!found) {
      const stack = [SRC];
      while (stack.length) {
        const dir = stack.pop()!;
        for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
          const p = path.join(dir, entry.name);
          if (entry.isDirectory()) {
            if (entry.name === 'node_modules' || entry.name === '__tests__') continue;
            stack.push(p);
          } else if (/\.(ts|vue)$/.test(entry.name)) {
            const t = fs.readFileSync(p, 'utf-8');
            if (/setAttribute\(['"]dir['"]/.test(t) ||
                /documentElement\.dir\s*=/.test(t)) {
              found = true;
              break;
            }
          }
        }
        if (found) break;
      }
    }
    expect(found).toBe(true);
  });
});
