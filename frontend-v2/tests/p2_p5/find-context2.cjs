// Find files containing t020-t029 references
const fs = require('fs');
const path = require('path');

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
const targets = ['capabilityRegistry.t020', 'capabilityRegistry.t021', 'capabilityRegistry.t022', 'capabilityRegistry.t023', 'capabilityRegistry.t024', 'capabilityRegistry.t025', 'capabilityRegistry.t026', 'capabilityRegistry.t027', 'capabilityRegistry.t028', 'capabilityRegistry.t029'];
for (const f of srcFiles) {
  const c = fs.readFileSync(f, 'utf8');
  for (const t of targets) {
    if (c.includes(t)) {
      const idx = c.indexOf(t);
      const start = Math.max(0, idx - 80);
      const end = Math.min(c.length, idx + 200);
      console.log(`-- ${t} in ${f} --`);
      console.log(c.substring(start, end));
      console.log('');
    }
  }
}
