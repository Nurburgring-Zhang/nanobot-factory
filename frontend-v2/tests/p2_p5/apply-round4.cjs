// Apply round-4 translations to all 9 locale files
const fs = require('fs');
const path = require('path');
const translations = require('./round4-translations.cjs');

const locales = ['en-US', 'zh-CN', 'ja-JP', 'ko-KR', 'fr-FR', 'de-DE', 'es-ES', 'ru-RU', 'ar-SA', 'pt-PT'];
const localesDir = path.join(__dirname, '..', '..', 'src', 'locales');

// Group keys by namespace
const byNs = {};
for (const k of Object.keys(translations)) {
  const ns = k.split('.')[0];
  if (!byNs[ns]) byNs[ns] = [];
  byNs[ns].push(k);
}
console.log('Namespaces:');
for (const ns of Object.keys(byNs)) {
  console.log('  ' + ns + ': ' + byNs[ns].length + ' keys');
}

// For each locale, find the namespace block and add the new keys at the end
for (const l of locales) {
  const filePath = path.join(localesDir, l + '.ts');
  let content = fs.readFileSync(filePath, 'utf8');

  for (const ns of Object.keys(byNs)) {
    // Find the namespace block: e.g. "  collectionCenter: {\n..." and its closing "},"
    // The block ends with "  }," or "  }" depending on whether it's the last namespace
    const startRe = new RegExp('(\\n|\\r|^)(\\s+)' + ns + ':\\s*\\{');
    const startMatch = content.match(startRe);
    if (!startMatch) {
      console.error('  WARN: namespace ' + ns + ' not found in ' + l);
      continue;
    }
    const blockStart = startMatch.index + startMatch[0].length;
    const blockIndent = startMatch[2];

    // Find the matching closing brace
    // Walk through the block, tracking brace depth (and ignoring braces in strings)
    let depth = 1;
    let inStr = false;
    let strCh = '';
    let blockEnd = -1;
    for (let i = blockStart; i < content.length; i++) {
      const ch = content[i];
      // Skip escape sequences
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
    if (blockEnd < 0) {
      console.error('  WARN: no closing brace for ' + ns + ' in ' + l);
      continue;
    }

    // Get the last entry to see if it ends with a trailing comma
    // The block content is content[blockStart..blockEnd]
    const blockContent = content.substring(blockStart, blockEnd);
    const lastNewline = blockContent.lastIndexOf('\n');
    const lastLine = blockContent.substring(lastNewline + 1);
    // If the last line ends with ',' we have a trailing comma, no need to add one
    const hasTrailingComma = lastLine.trimEnd().endsWith(',');
    // The new entries go on a new line, after a comma separator

    // Build the new entries
    const newEntries = [];
    for (const k of byNs[ns]) {
      const tkey = k.split('.')[1]; // e.g. 't028'
      const value = translations[k][l];
      if (value == null) {
        console.error('  WARN: no translation for ' + k + ' in ' + l);
        continue;
      }
      // Escape the value for the locale file (replace ' with \', etc.)
      const escaped = value.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
      newEntries.push(blockIndent + '  ' + tkey + ": '" + escaped + "'");
    }
    if (newEntries.length === 0) continue;

    // Check if any of the new keys already exist in the block
    const existingKeys = new Set();
    const keyRe = /^\s*(t\d+):/gm;
    let m;
    while ((m = keyRe.exec(blockContent)) !== null) existingKeys.add(m[1]);

    const filtered = newEntries.filter(e => {
      const keyMatch = e.match(/^\s*(t\d+):/);
      return keyMatch && !existingKeys.has(keyMatch[1]);
    });

    if (filtered.length === 0) {
      console.log('  ' + l + '/' + ns + ': all keys already present');
      continue;
    }

    // The insertion point: just before blockEnd. We need a comma after the previous entry
    // if there isn't one.
    const before = content.substring(0, blockEnd);
    const after = content.substring(blockEnd);
    let insertion = '';
    if (!hasTrailingComma) insertion = ',';
    insertion += '\n' + filtered.join(',\n') + '\n' + blockIndent;
    content = before + insertion + after;
    console.log('  ' + l + '/' + ns + ': added ' + filtered.length + ' keys');
  }

  fs.writeFileSync(filePath, content, 'utf8');
  console.log('Wrote ' + l);
}
console.log('\nDone!');
