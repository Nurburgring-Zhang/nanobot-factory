// Debug script
const fs = require('fs');
const content = fs.readFileSync('src/locales/en-US.ts', 'utf8');
const ns = 'capabilityRegistry';
const startRe = new RegExp('(\\n|\\r|^)(\\s+)' + ns + ':\\s*\\{');
const startMatch = content.match(startRe);
if (!startMatch) { console.log('No match'); process.exit(1); }
const blockStart = startMatch.index + startMatch[0].length;
const blockIndent = startMatch[2];
console.log('blockIndent:', JSON.stringify(blockIndent));

// Find matching closing brace
let depth = 1;
let inStr = false;
let strCh = '';
let blockEnd = -1;
for (let i = blockStart; i < content.length; i++) {
  const ch = content[i];
  if (inStr && ch === '\\') { i++; continue; }
  if (inStr) {
    if (ch === strCh) inStr = false;
    continue;
  }
  if (ch === "'" || ch === '"' || ch === '`') { inStr = true; strCh = ch; continue; }
  if (ch === '{') depth++;
  else if (ch === '}') {
    depth--;
    if (depth === 0) { blockEnd = i; break; }
  }
}
const blockContent = content.substring(blockStart, blockEnd);
console.log('blockContent length:', blockContent.length);
console.log('blockContent (first 200):', JSON.stringify(blockContent.substring(0, 200)));
console.log('blockContent (last 100):', JSON.stringify(blockContent.substring(blockContent.length - 100)));

// Find existing keys
const existingKeys = new Set();
const keyRe = /^\s*(t\d+):/gm;
let m;
while ((m = keyRe.exec(blockContent)) !== null) existingKeys.add(m[1]);
console.log('existingKeys:', [...existingKeys].sort());
