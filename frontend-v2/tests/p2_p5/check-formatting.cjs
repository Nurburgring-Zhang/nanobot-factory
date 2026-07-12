// Find the count of empty lines between consecutive content in each locale
const fs = require('fs');
const locales = ['en-US', 'zh-CN', 'ja-JP', 'ko-KR', 'fr-FR', 'de-DE', 'es-ES', 'ru-RU', 'ar-SA', 'pt-PT'];

for (const l of locales) {
  const content = fs.readFileSync('src/locales/' + l + '.ts', 'utf8');
  const lines = content.split('\n');

  // Find max consecutive empty lines
  let maxEmpty = 0;
  let cur = 0;
  let totalEmpty = 0;
  for (const line of lines) {
    if (line.trim() === '') {
      cur++;
      totalEmpty++;
      if (cur > maxEmpty) maxEmpty = cur;
    } else {
      cur = 0;
    }
  }

  // Count blocks with 5+ consecutive empty lines
  cur = 0;
  let badBlocks = 0;
  for (const line of lines) {
    if (line.trim() === '') {
      cur++;
    } else {
      if (cur >= 5) badBlocks++;
      cur = 0;
    }
  }

  console.log(l + ': ' + lines.length + ' lines, ' + totalEmpty + ' empty, max-consec=' + maxEmpty + ', blocks-5+=' + badBlocks);
}
