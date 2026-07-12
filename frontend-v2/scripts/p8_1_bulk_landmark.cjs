/**
 * p8_1_bulk_landmark.cjs — bulk-rewrites views to add role=region + sr-only h2.
 *
 * For every .vue file in src/views that does NOT yet have:
 *   - role="region" or role="main" or role="navigation"
 *   - a PageRegion wrapper
 *   - a sr-only h2 heading
 * …we inject:
 *   - role="region" + aria-label on the root <div>
 *   - a <h2 class="sr-only">  inside the root
 *
 * The script is intentionally conservative: it only touches the FIRST
 * <div ...>...</div> pair in <template>. Views with complex multi-root
 * templates are skipped (logged to skip list).
 *
 * Run:  node scripts/p8_1_bulk_landmark.cjs
 */

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const VIEWS_DIR = path.join(ROOT, 'src', 'views');

function listVueFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listVueFiles(full));
    else if (entry.isFile() && entry.name.endsWith('.vue')) out.push(full);
  }
  return out;
}

function relative(p) {
  return path.relative(ROOT, p).replace(/\\/g, '/');
}

// Find first <div ...> ... </div> pair inside <template>. Returns [startIdx, endIdx, openingTag].
function findFirstTemplateDiv(content) {
  const tmplStart = content.indexOf('<template>');
  if (tmplStart === -1) return null;
  const tmplEnd = content.indexOf('</template>');
  if (tmplEnd === -1) return null;
  const tmpl = content.slice(tmplStart, tmplEnd);

  // Find first <div ...> (NOT <div .../>)
  const openRe = /<div\b[^>]*>/g;
  let m;
  while ((m = openRe.exec(tmpl)) !== null) {
    const openingTag = m[0];
    // Self-closing? skip
    if (openingTag.endsWith('/>')) continue;
    // Find matching </div>
    let depth = 1;
    let i = openRe.lastIndex;
    const rest = tmpl.slice(i);
    const tagRe = /<div\b[^>]*>|<\/div>/g;
    let inner;
    while ((inner = tagRe.exec(rest)) !== null) {
      if (inner[0].startsWith('</div')) {
        depth--;
        if (depth === 0) {
          const divStart = tmplStart + m.index;
          const divEnd = tmplStart + i + inner.index + inner[0].length;
          return { divStart, divEnd, openingTag };
        }
      } else {
        // skip self-closing
        if (!inner[0].endsWith('/>')) depth++;
      }
    }
  }
  return null;
}

const files = listVueFiles(VIEWS_DIR);
let updated = 0;
let skipped = 0;
const updatedFiles = [];
const skippedFiles = [];

for (const file of files) {
  const raw = fs.readFileSync(file, 'utf8');

  // Skip if already has landmark or PageRegion or sr-only h2
  if (/role\s*=\s*["'](region|main|navigation)["']/.test(raw)) { skipped++; skippedFiles.push(relative(file) + ' [already has landmark]'); continue; }
  if (/<PageRegion\b/.test(raw)) { skipped++; skippedFiles.push(relative(file) + ' [has PageRegion]'); continue; }
  if (/<h2[^>]*class\s*=\s*["'][^"']*sr-only[^"']*["']/.test(raw)) { skipped++; skippedFiles.push(relative(file) + ' [has sr-only h2]'); continue; }

  const found = findFirstTemplateDiv(raw);
  if (!found) { skipped++; skippedFiles.push(relative(file) + ' [no <div> in template]'); continue; }

  const { divStart, divEnd, openingTag } = found;
  // Check the opening tag already has class attribute
  const hasClass = /class\s*=\s*["'][^"']*["']/.test(openingTag);
  let newOpening = openingTag;
  // Inject role="region" aria-label="..." (label uses filename)
  const baseName = path.basename(file, '.vue').replace(/[^a-zA-Z0-9]/g, '');
  const label = baseName.charAt(0).toLowerCase() + baseName.slice(1) + 'Page';
  const ariaLabel = `${baseName} view region`;
  if (hasClass) {
    newOpening = openingTag.replace(/<div\b/, `<div role="region" aria-label="${ariaLabel}"`);
  } else {
    newOpening = openingTag.replace(/<div\b/, `<div class="page-root" role="region" aria-label="${ariaLabel}"`);
  }

  // Inject sr-only h2 right after the opening tag
  const inner = raw.slice(divStart + openingTag.length, divEnd - '</div>'.length);
  const newInner = `\n    <h2 class="sr-only">${ariaLabel}</h2>\n    ${inner.trim()}\n  `;

  const newRaw = raw.slice(0, divStart) + newOpening + newInner + '</div>' + raw.slice(divEnd);
  fs.writeFileSync(file, newRaw);
  updated++;
  updatedFiles.push(relative(file));
}

console.log(`\n=== P8-1 Bulk landmark injection ===\n`);
console.log(`Updated: ${updated}`);
console.log(`Skipped: ${skipped}`);
console.log(`\nUpdated files:`);
for (const f of updatedFiles) console.log('  + ' + f);
console.log(`\nSkipped files:`);
for (const f of skippedFiles) console.log('  · ' + f);
