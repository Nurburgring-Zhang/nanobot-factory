// Normalize locale files: collapse runs of 3+ empty lines to a single empty line
// This is a pure cosmetic fix - JS parsers don't care about empty lines
const fs = require('fs');

const locales = ['en-US', 'zh-CN', 'ja-JP', 'ko-KR', 'fr-FR', 'de-DE', 'es-ES', 'ru-RU', 'ar-SA', 'pt-PT'];

for (const l of locales) {
  const filePath = 'src/locales/' + l + '.ts';
  const content = fs.readFileSync(filePath, 'utf8');
  const original = content;

  // Collapse 3+ consecutive newlines to 2 (single empty line)
  const normalized = content.replace(/\n{3,}/g, '\n\n');

  if (normalized !== original) {
    fs.writeFileSync(filePath, normalized, 'utf8');
    const before = content.length;
    const after = normalized.length;
    console.log(l + ': cleaned (saved ' + (before - after) + ' bytes)');
  } else {
    console.log(l + ': no change');
  }
}
