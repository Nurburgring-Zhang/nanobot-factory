// Debug regex match
const fs = require('fs');
const content = fs.readFileSync('src/locales/en-US.ts', 'utf8');
const ns = 'capabilityRegistry';
const startRe = new RegExp('(\\n|^)(\\s+)' + ns + ':\\s*\\{\\n');
const startMatch = content.match(startRe);
console.log('Match found:', !!startMatch);
if (startMatch) {
  console.log('  index:', startMatch.index);
  console.log('  full match:', JSON.stringify(startMatch[0].substring(0, 50)));
}
