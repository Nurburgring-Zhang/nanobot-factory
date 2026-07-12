// Pick the 100 round-4 keys to add (skip already-added round-1, -2, -3 keys)
const fs = require('fs');
const path = require('path');
const data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'missing-from-en.json'), 'utf8'));

// Already added in round 1, 2, 3 (per P2 P2, P2 P4, P2 P5 reports):
// P2 P2: 100 keys (mostly existing common, form, menu, etc.)
// P2 P4: 100 keys (capabilityRegistry t000-t003, packManager t000-t008, etc.)
// P2 P5 (round 3): capabilityRegistry t010-t019, collectionCenter t017-t027,
//                  delivery t011-t021, internalQC t017-t026, packManager t009-t028,
//                  projectCenter t018-t027, requirementCenter t018-t027,
//                  requesterAccept t017-t029, workflowBuilder t034-t038

// Group by namespace
const byNs = {};
for (const item of data) {
  const ns = item.key.split('.')[0];
  if (!byNs[ns]) byNs[ns] = [];
  byNs[ns].push(item.key);
}

// Sort each namespace by the numeric t-number
function tnum(k) {
  const m = k.match(/t(\d+)/);
  return m ? parseInt(m[1]) : 0;
}
for (const ns of Object.keys(byNs)) {
  byNs[ns].sort((a, b) => tnum(a) - tnum(b));
}

console.log('=== Current missing keys per namespace ===');
for (const ns of Object.keys(byNs)) {
  console.log(ns + ': ' + byNs[ns].length + ' keys — ' + byNs[ns].slice(0, 5).join(', ') + ' ... ' + byNs[ns].slice(-3).join(', '));
}

// Strategy: pick the next 100 lowest-numbered t-keys that come RIGHT after
// the round-3 set. This means:
//   - capabilityRegistry t020+ (10 keys, since round 3 had t010-t019)
//   - collectionCenter t028+ (since round 3 had t017-t027)
//   - delivery t022+ (since round 3 had t011-t021)
//   - internalQC t027+ (since round 3 had t017-t026)
//   - packManager t029+ (since round 3 had t009-t028)
//   - requesterAccept t030+ (since round 3 had t017-t029)
// Total: 10 + 45 + 11 + 13 + 21 = 100 (stop at 21 from packManager)

const picks = [];

const cap = (byNs['capabilityRegistry'] || []).filter(k => tnum(k) >= 20);
picks.push(...cap.slice(0, 10));

const col = (byNs['collectionCenter'] || []).filter(k => tnum(k) >= 28);
picks.push(...col.slice(0, 100)); // take all 45 (max 100 - need 90 more)

const del = (byNs['delivery'] || []).filter(k => tnum(k) >= 22);
picks.push(...del.slice(0, 100));

const iqc = (byNs['internalQC'] || []).filter(k => tnum(k) >= 27);
picks.push(...iqc.slice(0, 100));

const pk = (byNs['packManager'] || []).filter(k => tnum(k) >= 29);
picks.push(...pk.slice(0, 100));

// Take only the first 100
const finalPicks = picks.slice(0, 100);
console.log('\n=== Final 100 picks ===');
console.log('Total: ' + finalPicks.length);

// Group picks by namespace
const finalByNs = {};
for (const k of finalPicks) {
  const ns = k.split('.')[0];
  if (!finalByNs[ns]) finalByNs[ns] = [];
  finalByNs[ns].push(k);
}
for (const ns of Object.keys(finalByNs)) {
  console.log(ns + ': ' + finalByNs[ns].length + ' keys — ' + finalByNs[ns].join(', '));
}

fs.writeFileSync(path.join(__dirname, 'round4-picks.json'), JSON.stringify(finalPicks, null, 2));
console.log('\nWrote round4-picks.json');
