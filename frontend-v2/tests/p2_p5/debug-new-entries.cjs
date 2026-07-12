// Debug newEntries
const translations = require('./round4-translations.cjs');
const byNs = {};
for (const k of Object.keys(translations)) {
  const ns = k.split('.')[0];
  if (!byNs[ns]) byNs[ns] = [];
  byNs[ns].push(k);
}

const ns = 'capabilityRegistry';
const existingKeys = new Set(['t000', 't001', 't002', 't003', 't004', 't005', 't006', 't007', 't008', 't009', 't010', 't011', 't012', 't013', 't014', 't015', 't016', 't017', 't018', 't019']);
const blockIndent = '\n  ';
const locale = 'en-US';
const newEntries = [];
for (const k of byNs[ns]) {
  const tkey = k.split('.')[1];
  const value = translations[k][locale];
  const escaped = value.replace(/\\/g, '\\\\').replace(/'/g, "\\'");
  newEntries.push(blockIndent + '    ' + tkey + "': '" + escaped + "'");
}
console.log('newEntries:');
for (const e of newEntries) console.log('  ' + JSON.stringify(e));

const filtered = newEntries.filter(e => {
  const keyMatch = e.match(/^\s*(t\d+):/);
  return keyMatch && !existingKeys.has(keyMatch[1]);
});
console.log('\nfiltered count:', filtered.length);
for (const e of filtered) console.log('  ' + JSON.stringify(e));
