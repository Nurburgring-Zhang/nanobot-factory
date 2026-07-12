// Check actual missing keys referenced in views
const fs = require('fs');

function flatten(obj, prefix) {
  const out = new Set();
  function walk(o, p) {
    for (const [k, v] of Object.entries(o)) {
      const full = p ? p + '.' + k : k;
      if (v && typeof v === 'object' && !Array.isArray(v)) walk(v, full);
      else if (typeof v === 'string') out.add(full);
    }
  }
  walk(obj, prefix || '');
  return out;
}

const rawEn = fs.readFileSync('src/locales/en-US.ts', 'utf8');
let enJs = rawEn.replace(/export default\s*/, '').replace(/as const\s*$/, '');
const en = flatten(new Function('return (' + enJs + ')')());
console.log('en-US keys:', en.size);

const views = [
  'src/views/ProjectCenter.vue',
  'src/views/RequirementCenter.vue',
  'src/views/InternalQC.vue',
  'src/views/RequesterAccept.vue',
  'src/views/Review.vue',
  'src/views/WorkflowBuilder.vue',
  'src/views/CapabilityRegistry.vue',
  'src/views/CollectionCenter.vue',
  'src/views/Delivery.vue',
  'src/views/PackManager.vue',
];
const referenced = new Set();
for (const v of views) {
  if (!fs.existsSync(v)) continue;
  const content = fs.readFileSync(v, 'utf8');
  const re = /\bt\(\s*['"]([^'"]+)['"]/g;
  let m;
  while ((m = re.exec(content)) !== null) {
    referenced.add(m[1]);
  }
}
console.log('Total unique t() refs in views:', referenced.size);
const missing = [...referenced].filter(k => !en.has(k));
console.log('Missing from en-US:', missing.length);
if (missing.length > 0) {
  console.log('Missing keys:');
  for (const k of missing) console.log('  -', k);
}
