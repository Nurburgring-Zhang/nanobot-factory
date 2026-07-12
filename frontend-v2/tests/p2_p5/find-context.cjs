// Find context of t020-t029 in CapabilityRegistry.vue
const fs = require('fs');
const c = fs.readFileSync('src/views/CapabilityRegistry.vue', 'utf8');
const re = /\bt\s*\(\s*['`]capabilityRegistry\.t02\d['`]\s*\)/g;
let m;
while ((m = re.exec(c)) !== null) {
  const start = Math.max(0, m.index - 100);
  const end = Math.min(c.length, m.index + 200);
  console.log('---');
  console.log(c.substring(start, end));
}
