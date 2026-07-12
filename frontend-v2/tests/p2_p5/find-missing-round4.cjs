// Analyze locale key counts and missing keys
const fs = require('fs');
const path = require('path');

const locales = ['en-US', 'zh-CN', 'ja-JP', 'ko-KR', 'fr-FR', 'de-DE', 'es-ES', 'ru-RU', 'ar-SA', 'pt-PT'];
const keys = {};

function flatten(obj, prefix='') {
  const out = [];
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? prefix + '.' + k : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      out.push(...flatten(v, full));
    } else if (typeof v === 'string') {
      out.push(full);
    }
  }
  return out;
}

for (const l of locales) {
  const filePath = path.join('src/locales', l + '.ts');
  const content = fs.readFileSync(filePath, 'utf8');
  let js = content.replace(/export default\s*/, '').replace(/as const\s*$/, '');
  const obj = (new Function('return (' + js + ')'))();
  keys[l] = new Set(flatten(obj));
  console.log(l + ': ' + keys[l].size + ' keys');
}

const enKeys = keys['en-US'];
const enKeysArr = [...enKeys];

console.log('\n=== Keys in en-US but missing in each other locale ===');
const missingPerLocale = {};
for (const l of locales) {
  if (l === 'en-US') continue;
  const missing = enKeysArr.filter(k => !keys[l].has(k));
  missingPerLocale[l] = missing;
  console.log(l + ': missing ' + missing.length + ' keys');
}

// Find the union of all missing keys (i.e. keys missing in AT LEAST one locale)
const allMissing = new Set();
for (const l of locales) {
  if (l === 'en-US') continue;
  for (const k of missingPerLocale[l]) allMissing.add(k);
}
console.log('\nUnion of all missing across 9 non-en locales: ' + allMissing.size + ' keys');

// Count how many locales are missing each key (most-missing = missing in 8 or 9 locales)
const missingCount = {};
for (const k of allMissing) {
  let n = 0;
  for (const l of locales) {
    if (l === 'en-US') continue;
    if (!keys[l].has(k)) n++;
  }
  missingCount[k] = n;
}

const sorted = [...allMissing].sort((a, b) => missingCount[b] - missingCount[a] || a.localeCompare(b));
console.log('\n=== Top 30 most-missing keys (count = # locales missing out of 9) ===');
for (let i = 0; i < Math.min(30, sorted.length); i++) {
  console.log((i+1) + '. ' + sorted[i] + ' (missing in ' + missingCount[sorted[i]] + '/9)');
}

// Output full list to file
const fullList = sorted.map((k, i) => ({
  rank: i + 1,
  key: k,
  missing_in: missingCount[k]
}));
fs.writeFileSync('all-missing-sorted.json', JSON.stringify(fullList, null, 2));
console.log('\nFull sorted missing list written to all-missing-sorted.json (' + fullList.length + ' keys)');
