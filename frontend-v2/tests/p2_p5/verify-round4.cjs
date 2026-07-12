// Verify round 4 keys present in all 10 locales
const fs = require('fs');

const locales = ['en-US', 'zh-CN', 'ja-JP', 'ko-KR', 'fr-FR', 'de-DE', 'es-ES', 'ru-RU', 'ar-SA', 'pt-PT'];

function flatten(obj, prefix='') {
  const out = [];
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? prefix + '.' + k : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) out.push(...flatten(v, full));
    else if (typeof v === 'string') out.push(full);
  }
  return out;
}

const localeData = {};
const localeKeys = {};
for (const l of locales) {
  const content = fs.readFileSync('src/locales/' + l + '.ts', 'utf8');
  let js = content.replace(/export default\s*/, '').replace(/as const\s*$/, '');
  localeData[l] = (new Function('return (' + js + ')'))();
  localeKeys[l] = new Set(flatten(localeData[l]));
  console.log(l + ': ' + localeKeys[l].size + ' keys');
}

const enKeys = localeKeys['en-US'];

// Compute "round 4 keys" as keys in en-US that have t-number >= 30 (or the obvious round-4 t-range)
const allEnKeys = [...enKeys];
const t30Plus = allEnKeys.filter(k => {
  const m = k.match(/t(\d+)/);
  return m && parseInt(m[1]) >= 30;
});
console.log('\n=== en-US t30+ keys: ' + t30Plus.length + ' ===');
for (const k of t30Plus.slice(0, 10)) console.log('  ' + k);
console.log('  ...');
for (const k of t30Plus.slice(-5)) console.log('  ' + k);

// For each non-en locale, find which round-4 keys are missing
console.log('\n=== Missing per locale (t30+ keys) ===');
const totalMissingPerLocale = {};
for (const l of locales) {
  if (l === 'en-US') continue;
  const missing = t30Plus.filter(k => !localeKeys[l].has(k));
  totalMissingPerLocale[l] = missing.length;
  console.log(l + ': missing ' + missing.length + ' / ' + t30Plus.length);
  if (missing.length > 0 && missing.length < 20) {
    for (const k of missing) console.log('  - ' + k);
  }
}

// Round 3 keys: t-numbers that should already exist (from p2_p5 report)
// capabilityRegistry t010-t019, collectionCenter t017-t027, delivery t011-t021,
// internalQC t017-t026, packManager t009-t028, projectCenter t018-t027,
// requirementCenter t018-t027, requesterAccept t017-t029, workflowBuilder t034-t038
const round3Keys = [
  ...Array.from({length: 10}, (_, i) => 'capabilityRegistry.t0' + (10 + i)),
  ...Array.from({length: 11}, (_, i) => 'collectionCenter.t0' + (17 + i)),
  ...Array.from({length: 11}, (_, i) => 'delivery.t0' + (11 + i)),
  ...Array.from({length: 10}, (_, i) => 'internalQC.t0' + (17 + i)),
  ...Array.from({length: 20}, (_, i) => 'packManager.t0' + (9 + i)),
  ...Array.from({length: 10}, (_, i) => 'projectCenter.t0' + (18 + i)),
  ...Array.from({length: 10}, (_, i) => 'requirementCenter.t0' + (18 + i)),
  ...Array.from({length: 13}, (_, i) => 'requesterAccept.t0' + (17 + i)),
  ...Array.from({length: 5}, (_, i) => 'workflowBuilder.t0' + (34 + i)),
];
console.log('\n=== Round 3 keys present in en-US: ' + round3Keys.filter(k => enKeys.has(k)).length + ' / ' + round3Keys.length + ' ===');

// Round 4 keys: based on the existing p2_p5/round4-picks.json
const round4Keys = JSON.parse(fs.readFileSync('tests/p2_p5/round4-picks.json', 'utf8'));
console.log('\n=== Round 4 keys in en-US: ' + round4Keys.filter(k => enKeys.has(k)).length + ' / ' + round4Keys.length + ' ===');
const round4Missing = round4Keys.filter(k => !enKeys.has(k));
if (round4Missing.length > 0) {
  console.log('Missing from en-US:');
  for (const k of round4Missing.slice(0, 20)) console.log('  - ' + k);
}

// Check round 4 in each non-en locale
console.log('\n=== Round 4 keys present per locale ===');
for (const l of locales) {
  if (l === 'en-US') continue;
  const present = round4Keys.filter(k => localeKeys[l].has(k));
  const missing = round4Keys.filter(k => !localeKeys[l].has(k));
  console.log(l + ': ' + present.length + ' / ' + round4Keys.length + ' (missing ' + missing.length + ')');
  if (missing.length > 0 && missing.length < 20) {
    for (const k of missing) console.log('  - ' + k);
  }
}
