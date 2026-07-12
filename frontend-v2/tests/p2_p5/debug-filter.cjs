// Debug filter
const e = "\n      t020': 'Status'";
const re = /^\s*(t\d+):/;
const m = e.match(re);
console.log('match:', m);
if (m) console.log('  m[1]:', m[1]);
else console.log('  NO MATCH');

// Try with m flag
const re2 = /^\s*(t\d+):/m;
const m2 = e.match(re2);
console.log('match (m flag):', m2);
if (m2) console.log('  m2[1]:', m2[1]);
