// Debug regex match - simpler
const fs = require('fs');
const content = fs.readFileSync('src/locales/en-US.ts', 'utf8');
const ns = 'capabilityRegistry';
// Try simpler regex without escape sequences
const startRe = new RegExp('^(\\s+)' + ns + ':\\s*\\{', 'm');
const startMatch = content.match(startRe);
console.log('Match found:', !!startMatch);
if (startMatch) {
  console.log('  index:', startMatch.index);
  console.log('  full match:', JSON.stringify(startMatch[0].substring(0, 50)));
}

// Also test: is `\\s+` being interpreted as something else?
const re2 = new RegExp('\\s+');
console.log('re2 test:', re2.test('  '));

const re3 = new RegExp('(\\n|^)(\\s+)' + ns + ':');
const m3 = content.match(re3);
console.log('re3 match:', !!m3);
