// Find all t() references in source code that are missing from en-US
const fs = require('fs');
const path = require('path');

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

// Load en-US keys
const enContent = fs.readFileSync('src/locales/en-US.ts', 'utf8');
const enJs = enContent.replace(/export default\s*/, '').replace(/as const\s*$/, '');
const enObj = (new Function('return (' + enJs + ')'))();
const enKeys = new Set(flatten(enObj));
console.log('en-US has ' + enKeys.size + ' keys');

function walk(dir, exts) {
  let files = [];
  for (const f of fs.readdirSync(dir)) {
    const full = path.join(dir, f);
    const st = fs.statSync(full);
    if (st.isDirectory()) files = files.concat(walk(full, exts));
    else if (exts.some(e => f.endsWith(e))) files.push(full);
  }
  return files;
}

const srcFiles = walk('src', ['.ts', '.vue', '.tsx', '.js']);
console.log('Found ' + srcFiles.length + ' source files');

// Find t() references with quoted keys
const tKeyRe = /\bt\s*\(\s*['"`]([\w\d\.\-_]+)['"`]\s*[),]/g;
const refKeys = new Set();
const keyFileMap = {};
for (const f of srcFiles) {
  const c = fs.readFileSync(f, 'utf8');
  let m;
  while ((m = tKeyRe.exec(c)) !== null) {
    refKeys.add(m[1]);
    if (!keyFileMap[m[1]]) keyFileMap[m[1]] = new Set();
    keyFileMap[m[1]].add(f);
  }
}
console.log('Found ' + refKeys.size + ' unique t() key references');

// Find which references are MISSING from en-US
const missing = [...refKeys].filter(k => !enKeys.has(k));
console.log('References missing from en-US: ' + missing.length);
console.log('\n=== Top 50 most-referenced-but-missing keys (sorted by file count) ===');
const sorted = missing.sort((a, b) => keyFileMap[b].size - keyFileMap[a].size || a.localeCompare(b));
for (let i = 0; i < Math.min(50, sorted.length); i++) {
  const files = [...keyFileMap[sorted[i]]].map(f => f.replace(/^src\//, '')).slice(0, 3);
  console.log((i+1) + '. ' + sorted[i] + ' (in ' + keyFileMap[sorted[i]].size + ' files: ' + files.join(', ') + ')');
}

// Write the full missing list
const full = missing.map(k => ({
  key: k,
  files: [...keyFileMap[k]]
}));
fs.writeFileSync('missing-from-en.json', JSON.stringify(full, null, 2));
console.log('\nWrote missing-from-en.json with ' + full.length + ' keys');
