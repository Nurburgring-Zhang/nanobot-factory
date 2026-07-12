// Find 100 most-missing keys in 9 locales
const fs = require('fs');
const path = require('path');

// Use a TS-friendly loader
function loadLocale(file) {
  // Read the file and eval the export
  const code = fs.readFileSync(file, 'utf-8');
  // Replace `export default` with `module.exports = `
  // Also strip `as const` (Node won't parse that)
  let transformed = code.replace(/export\s+default\s+/, 'module.exports = ');
  transformed = transformed.replace(/\s+as\s+const\b/g, '');
  // Use Function constructor to evaluate
  const mod = { exports: {} };
  try {
    const fn = new Function('module', 'exports', transformed);
    fn(mod, mod.exports);
  } catch (e) {
    console.error('Eval error for', file, ':', e.message);
    return null;
  }
  return mod.exports;
}

function flattenKeys(obj, prefix = '') {
  const out = [];
  for (const [k, v] of Object.entries(obj || {})) {
    const full = prefix ? prefix + '.' + k : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      out.push(...flattenKeys(v, full));
    } else if (typeof v === 'string') {
      out.push(full);
    }
  }
  return out;
}

const localesDir = path.join(process.cwd(), 'src', 'locales');
const localeFiles = ['en-US.ts', 'zh-CN.ts', 'ja-JP.ts', 'ko-KR.ts', 'fr-FR.ts', 'de-DE.ts', 'es-ES.ts', 'ru-RU.ts', 'ar-SA.ts', 'pt-PT.ts'];

const locales = {};
for (const f of localeFiles) {
  const name = f.replace('.ts', '');
  locales[name] = loadLocale(path.join(localesDir, f));
  if (!locales[name]) {
    console.error('Failed to load', f);
    process.exit(1);
  }
}

const enKeys = new Set(flattenKeys(locales['en-US']));
console.log('en-US has', enKeys.size, 'keys');

// For each non-en locale, find missing keys
const missingByLocale = {};
for (const name of Object.keys(locales)) {
  if (name === 'en-US') continue;
  const lk = new Set(flattenKeys(locales[name]));
  missingByLocale[name] = [...enKeys].filter(k => !lk.has(k));
}

// Count how many locales each en key is missing from
const missingFrom = {};
for (const k of enKeys) {
  missingFrom[k] = 0;
  for (const name of Object.keys(missingByLocale)) {
    if (missingByLocale[name].includes(k)) missingFrom[k]++;
  }
}

// Sort by "most missing" (highest count first)
const sortedKeys = Object.entries(missingFrom)
  .filter(([k, c]) => c > 0)
  .sort((a, b) => b[1] - a[1]);

console.log('Total en keys missing from at least 1 locale:', sortedKeys.length);
console.log('\nTop 30 most-missing keys:');
sortedKeys.slice(0, 30).forEach(([k, c]) => {
  console.log(`  ${k} (missing from ${c}/9 locales)`);
});

console.log('\nBottom 10 (least missing but still missing in some):');
sortedKeys.slice(-10).forEach(([k, c]) => {
  console.log(`  ${k} (missing from ${c}/9 locales)`);
});

// Save the full list to disk
const outPath = path.join(process.cwd(), 'tests', 'p2_p5', 'most-missing-keys.json');
fs.writeFileSync(outPath, JSON.stringify(sortedKeys, null, 2));
console.log('\nFull list saved to tests/p2_p5/most-missing-keys.json');
