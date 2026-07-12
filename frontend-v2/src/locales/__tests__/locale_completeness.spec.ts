/**
 * P20-N locale-completeness vitest spec.
 *
 * Companion to test_locale_completeness.py. Mirrors the same assertions
 * in vitest (jest-style) syntax so vitest's *.spec.ts include pattern
 * picks it up.
 *
 * Run with: npx vitest run src/locales/__tests__/locale_completeness.spec.ts
 */
import { describe, test, expect } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

const FRONTEND_ROOT = path.resolve(__dirname, '../../../');
const LOCALES_DIR = path.join(FRONTEND_ROOT, 'src', 'locales');

const LOCALES = [
  'zh-CN', 'en-US', 'ja-JP', 'ko-KR',
  'fr-FR', 'de-DE', 'es-ES', 'ru-RU', 'ar-SA',
];

const EXPECTED_KEYS = Array.from({ length: 34 }, (_, i) => `t${String(i).padStart(3, '0')}`);

function readLocale(name: string): string {
  return fs.readFileSync(path.join(LOCALES_DIR, `${name}.ts`), 'utf-8');
}

function extractWorkflowBuilder(text: string): string | null {
  const m = text.match(/workflowBuilder:\s*\{([\s\S]*?)\n\s*\},/);
  return m ? m[1] : null;
}

describe('P20-N workflowBuilder coverage', () => {
  test.each(LOCALES)('%s has workflowBuilder block', (loc) => {
    const text = readLocale(loc);
    expect(extractWorkflowBuilder(text)).not.toBeNull();
  });

  test.each(LOCALES)('%s has all 34 workflowBuilder.tNNN keys', (loc) => {
    const text = readLocale(loc);
    const block = extractWorkflowBuilder(text);
    expect(block).not.toBeNull();
    const keys = Array.from(block!.matchAll(/\b(t\d{3}):/g)).map((m) => m[1]);
    expect(keys).toHaveLength(34);
    for (const expected of EXPECTED_KEYS) {
      expect(keys).toContain(expected);
    }
  });

  test.each(LOCALES)('%s workflowBuilder values are non-empty', (loc) => {
    const text = readLocale(loc);
    const block = extractWorkflowBuilder(text);
    expect(block).not.toBeNull();
    const pairs = [...block!.matchAll(/(t\d{3}):\s*'([^']*)'/g)];
    expect(pairs.length).toBeGreaterThan(0);
    for (const m of pairs) {
      expect(m[2].trim().length).toBeGreaterThan(0);
    }
  });

  test('zh-CN vs en-US translations differ (proves they were translated)', () => {
    const zh = extractWorkflowBuilder(readLocale('zh-CN')) || '';
    const en = extractWorkflowBuilder(readLocale('en-US')) || '';
    const zhPairs = Object.fromEntries(
      [...zh.matchAll(/(t\d{3}):\s*'([^']*)'/g)].map((m) => [m[1], m[2]])
    );
    const enPairs = Object.fromEntries(
      [...en.matchAll(/(t\d{3}):\s*'([^']*)'/g)].map((m) => [m[1], m[2]])
    );
    let diffCount = 0;
    for (const k of Object.keys(zhPairs)) {
      if (k in enPairs && zhPairs[k] !== enPairs[k]) diffCount++;
    }
    expect(diffCount).toBeGreaterThanOrEqual(10);
  });
});

describe('P20-N locale file structure', () => {
  test.each(LOCALES)('%s file exists', (loc) => {
    expect(fs.existsSync(path.join(LOCALES_DIR, `${loc}.ts`))).toBe(true);
  });

  test.each(LOCALES)('%s has export default', (loc) => {
    expect(readLocale(loc)).toContain('export default');
  });

  test.each(LOCALES)('%s ends with `} as const`', (loc) => {
    const text = readLocale(loc).trim();
    expect(/\}\s*as\s+const\s*$/.test(text)).toBe(true);
  });

  test.each(LOCALES)('%s has balanced braces (string-aware)', (loc) => {
    const text = readLocale(loc);
    let depth = 0;
    let i = 0;
    while (i < text.length) {
      const ch = text[i];
      if (ch === '"' || ch === "'" || ch === '`') {
        const quote = ch;
        i++;
        while (i < text.length && text[i] !== quote) {
          if (text[i] === '\\') i += 2;
          else i++;
        }
        i++;
        continue;
      }
      if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        expect(depth).toBeGreaterThanOrEqual(0);
      }
      i++;
    }
    expect(depth).toBe(0);
  });
});

describe('P20-N ar-SA RTL', () => {
  test('ar-SA contains Arabic-script characters', () => {
    const text = readLocale('ar-SA');
    const arabic = text.match(/[\u0600-\u06FF]/g) || [];
    expect(arabic.length).toBeGreaterThanOrEqual(10);
  });

  test('ar-SA workflowBuilder is in Arabic', () => {
    const block = extractWorkflowBuilder(readLocale('ar-SA')) || '';
    const pairs = Object.fromEntries(
      [...block.matchAll(/(t\d{3}):\s*'([^']*)'/g)].map((m) => [m[1], m[2]])
    );
    expect(Object.keys(pairs).length).toBeGreaterThanOrEqual(30);
    let arabicCount = 0;
    for (const v of Object.values(pairs)) {
      if (/[\u0600-\u06FF]/.test(v as string)) arabicCount++;
    }
    expect(arabicCount).toBeGreaterThanOrEqual(20);
  });
});