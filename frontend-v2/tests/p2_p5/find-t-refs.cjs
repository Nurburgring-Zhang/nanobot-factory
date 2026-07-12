// Find t() references in views/components that are missing from en-US
const fs = require('fs');
const path = require('path');

function loadLocale(file) {
  const code = fs.readFileSync(file, 'utf-8');
  let transformed = code.replace(/export\s+default\s+/, 'module.exports = ');
  transformed = transformed.replace(/\s+as\s+const\b/g, '');
  const mod = { exports: {} };
  try {
    const fn = new Function('module', 'exports', transformed);
    fn(mod, mod.exports);
  } catch (e) {
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

const en = loadLocale(path.join(process.cwd(), 'src', 'locales', 'en-US.ts'));
const enKeys = new Set(flattenKeys(en));
console.log('en-US has', enKeys.size, 'keys');

// Walk src/ and find all t('...') calls in .vue and .ts files
const refs = new Set();
const srcDir = path.join(process.cwd(), 'src');

function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walk(p);
    } else if (entry.name.endsWith('.vue') || entry.name.endsWith('.ts') || entry.name.endsWith('.tsx')) {
      const content = fs.readFileSync(p, 'utf-8');
      // Match t('key'), t("key"), t(`key`)
      const re = /t\(\s*['"`]([A-Za-z][A-Za-z0-9_.]*)['"`]/g;
      let m;
      while ((m = re.exec(content)) !== null) {
        refs.add(m[1]);
      }
    }
  }
}

walk(srcDir);
console.log('Total unique t() refs:', refs.size);

// Skip top-level short names that may be false positives (single-word lowercase)
const filteredRefs = [...refs].filter(k => k.includes('.') || /^[A-Z]/.test(k));
console.log('Filtered unique t() refs:', filteredRefs.length);

const missing = filteredRefs.filter(k => !enKeys.has(k)).sort();
console.log('\nMissing from en-US:', missing.length);

// Group by namespace
const byNamespace = {};
for (const k of missing) {
  const ns = k.split('.')[0];
  byNamespace[ns] = (byNamespace[ns] || 0) + 1;
}
console.log('\nMissing by namespace:');
Object.entries(byNamespace).sort((a, b) => b[1] - a[1]).forEach(([ns, n]) => {
  console.log(`  ${ns}: ${n}`);
});

const outPath = path.join(process.cwd(), 'tests', 'p2_p5', 'all-missing-from-en.json');
fs.writeFileSync(outPath, JSON.stringify(missing, null, 2));
console.log('\nFull missing list saved to', outPath);
