// Count zh-CN === en-US matches
const fs = require('fs');

const rawEn = fs.readFileSync('src/locales/en-US.ts', 'utf8');
const rawZh = fs.readFileSync('src/locales/zh-CN.ts', 'utf8');
let enJs = rawEn.replace(/export default\s*/, '').replace(/as const\s*$/, '');
let zhJs = rawZh.replace(/export default\s*/, '').replace(/as const\s*$/, '');
const en = new Function('return (' + enJs + ')')();
const zh = new Function('return (' + zhJs + ')')();

function flatten(o, p) {
  const out = {};
  for (const [k, v] of Object.entries(o)) {
    const full = p ? p + '.' + k : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) Object.assign(out, flatten(v, full));
    else if (typeof v === 'string') out[full] = v;
  }
  return out;
}

const enFlat = flatten(en);
const zhFlat = flatten(zh);
let match = 0;
const matches = [];
for (const k of Object.keys(enFlat)) {
  if (k in zhFlat && zhFlat[k] === enFlat[k]) {
    match++;
    matches.push(k);
  }
}
console.log('zh-CN === en-US match count:', match);
console.log('First 30 matches:');
for (const k of matches.slice(0, 30)) console.log('  -', k, '=', JSON.stringify(enFlat[k]));
