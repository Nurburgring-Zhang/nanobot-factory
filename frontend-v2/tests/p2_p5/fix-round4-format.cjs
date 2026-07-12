// Normalize the locale files - remove the messy entries I added and re-add them cleanly
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

// For each locale, find and remove the messy entries I added, then re-add them cleanly
for (const l of locales) {
  const filePath = path.join(localesDir, l + '.ts');
  let content = fs.readFileSync(filePath, 'utf8');
  const original = content;

  for (const ns of Object.keys(byNs)) {
    // Find the namespace block start
    const startRe = new RegExp('(\\n|\\r|^)([ \\t]+)' + ns + ':\\s*\\{');
    const startMatch = content.match(startRe);
    if (!startMatch) continue;
    const blockStart = startMatch.index + startMatch[0].length;
    const blockIndent = startMatch[2]; // indent of the namespace name

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
    if (blockEnd < 0) continue;

    // Within the block, find any tNNN entries (with or without the messy double newlines).
    // We'll find them by parsing line by line and identifying the keys we want to (re)insert.
    const blockContent = content.substring(blockStart, blockEnd);

    // Find which tNNN keys are in this block (we'll remove all and re-add cleanly)
    const keysToAdd = byNs[ns].map(k => k.split('.')[1]);
    const keyPattern = new RegExp('^([ \\t]*)(t\\d+):', 'gm');
    let m;
    const linesToRemove = new Set(); // indices into blockContent
    while ((m = keyPattern.exec(blockContent)) !== null) {
      if (keysToAdd.includes(m[2])) {
        // Mark this line and the next line (if it's just whitespace) for removal
        // Actually, the messy format has:
        //   t027: 'Resume collection',  (last existing key)
        //
        //         t028: 'Source type',  (added with 6-space indent and empty line before)
        //
        //         t029: 'Collection name',
        // We need to remove the entire `   <newline>      t028: 'Source type',` pattern.
        // Easier: find from this match index, take the rest of the line (the value + comma),
        // then skip any following newlines that have only whitespace.
        let lineEnd = blockContent.indexOf('\n', m.index);
        if (lineEnd < 0) lineEnd = blockContent.length;
        // Mark from m.index to lineEnd for removal
        for (let i = m.index; i < lineEnd; i++) linesToRemove.add(i);
        // Also mark the immediately preceding line if it's just whitespace
        // (this is the empty line between existing and new entries)
        // Find the start of the previous line
        let prevNewline = blockContent.lastIndexOf('\n', m.index - 1);
        if (prevNewline >= 0) {
          // Check if the line before this newline (i.e. between prevNewline-1 and prevNewline) is just \r
          // Actually, check if from prevNewline+1 to m.index is all whitespace
          const between = blockContent.substring(prevNewline + 1, m.index);
          if (/^[ \t\r]*$/.test(between)) {
            // The line from prevNewline+1 to m.index is just whitespace - mark it for removal
            for (let i = prevNewline + 1; i < m.index; i++) linesToRemove.add(i);
          }
        }
      }
    }

    // Build the new block content by skipping the marked indices
    let newBlock = '';
    for (let i = 0; i < blockContent.length; i++) {
      if (!linesToRemove.has(i)) newBlock += blockContent[i];
    }

    // Now append the new entries cleanly at the end of the block.
    // The newBlock may or may not end with a trailing comma. Check.
    const lastChar = newBlock.trimEnd().slice(-1);
    const needsComma = lastChar !== ',';
    const childIndent = blockIndent + '  '; // 2 more spaces

    // Build the new entries
    const newEntries = [];
    for (const k of byNs[ns]) {
      const tkey = k.split('.')[1];
      const value = translations[k][l];
      if (value == null) continue;
      const escaped = value.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
      newEntries.push(childIndent + tkey + ": '" + escaped + "'");
    }
    if (newEntries.length === 0) continue;

    const insertion = (needsComma ? ',' : '') + '\n' + newEntries.join(',\n');
    newBlock = newBlock + insertion;

    // Replace the block in the content
    content = content.substring(0, blockStart) + newBlock + content.substring(blockEnd);
  }

  if (content !== original) {
    fs.writeFileSync(filePath, content, 'utf8');
    console.log('Wrote ' + l);
  } else {
    console.log('  no change for ' + l);
  }
}
console.log('Done');
