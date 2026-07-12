/**
 * p8_1_bulk_landmark_pass2.cjs — second pass for views with no <div> root.
 *
 * Targets templates that start directly with <NCard ...> or <NPageHeader ...>.
 * Wraps the first 1-3 top-level children inside a <section role="region" ...>
 * with an sr-only h2.
 *
 * Run AFTER p8_1_bulk_landmark.cjs.
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

function relative(p) { return path.relative(ROOT, p).replace(/\\/g, '/'); }

const files = listVueFiles(VIEWS_DIR);
let updated = 0;
const updatedFiles = [];
const skippedFiles = [];

for (const file of files) {
  const raw = fs.readFileSync(file, 'utf8');

  if (/role\s*=\s*["'](region|main|navigation)["']/.test(raw)) { skippedFiles.push(relative(file) + ' [already has landmark]'); continue; }
  if (/<PageRegion\b/.test(raw)) { skippedFiles.push(relative(file) + ' [has PageRegion]'); continue; }

  const tmplStart = raw.indexOf('<template>');
  if (tmplStart === -1) { skippedFiles.push(relative(file) + ' [no template]'); continue; }
  const tmplEnd = raw.indexOf('</template>');
  if (tmplEnd === -1) { skippedFiles.push(relative(file) + ' [no template close]'); continue; }

  // Find the first non-whitespace content after <template>
  const afterTemplate = tmplStart + '<template>'.length;
  let contentStart = afterTemplate;
  while (contentStart < tmplEnd && /\s/.test(raw[contentStart])) contentStart++;

  const baseName = path.basename(file, '.vue').replace(/[^a-zA-Z0-9]/g, '');
  const label = baseName.charAt(0).toLowerCase() + baseName.slice(1) + 'Page';
  const ariaLabel = `${baseName} view region`;

  // Wrap in <section role="region" ...> ... </section>
  const sectionOpen = `\n  <section class="page-root" role="region" aria-label="${ariaLabel}">\n    <h2 class="sr-only">${ariaLabel}</h2>\n  `;
  const sectionClose = `\n  </section>\n`;

  // Insert sectionOpen right after <template> and sectionClose right before </template>
  const newRaw = raw.slice(0, contentStart) + sectionOpen.trimEnd() + '\n' + raw.slice(contentStart, tmplEnd).replace(/^\s+/, '') + sectionClose.trimEnd() + raw.slice(tmplEnd);
  fs.writeFileSync(file, newRaw);
  updated++;
  updatedFiles.push(relative(file));
}

console.log(`\n=== P8-1 Bulk landmark pass 2 (multi-root templates) ===\n`);
console.log(`Updated: ${updated}`);
console.log(`Skipped: ${skippedFiles.length}\n`);
for (const f of updatedFiles) console.log('  + ' + f);
for (const f of skippedFiles) console.log('  · ' + f);
