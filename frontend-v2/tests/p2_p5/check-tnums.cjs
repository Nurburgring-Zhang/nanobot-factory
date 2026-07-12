// Get max t-numbers per namespace in en-US
const fs = require('fs');
const content = fs.readFileSync('src/locales/en-US.ts', 'utf8');
let js = content.replace(/export default\s*/, '').replace(/as const\s*$/, '');
const enUS = (new Function('return (' + js + ')'))();

function flatten(obj, prefix='') {
  const out = [];
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? prefix + '.' + k : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) out.push(...flatten(v, full));
    else if (typeof v === 'string') out.push(full);
  }
  return out;
}
const enKeys = flatten(enUS);
console.log('en-US has ' + enKeys.length + ' keys');

// Get the max t-number per namespace
const byNs = {};
const allByNs = {};
for (const k of enKeys) {
  const ns = k.split('.')[0];
  if (!allByNs[ns]) allByNs[ns] = [];
  allByNs[ns].push(k);
  const m = k.match(/t(\d+)/);
  if (m) {
    const t = parseInt(m[1]);
    if (!byNs[ns] || t > byNs[ns]) byNs[ns] = t;
  }
}
console.log('\nTotal keys per namespace:');
for (const [ns, arr] of Object.entries(allByNs)) {
  console.log('  ' + ns + ': ' + arr.length + ' keys (max t' + (byNs[ns] || 0) + ')');
}

// Find t-numbers > 50 or so
console.log('\nKeys with t-number >= 30 per namespace:');
for (const [ns, arr] of Object.entries(allByNs)) {
  const bigT = arr.filter(k => {
    const m = k.match(/t(\d+)/);
    return m && parseInt(m[1]) >= 30;
  });
  if (bigT.length > 0) console.log('  ' + ns + ': ' + bigT.length + ' keys: ' + bigT.join(', '));
}
