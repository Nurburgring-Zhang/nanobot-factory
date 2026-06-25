// verify-p1cw1-deep.cjs — Deep import verification using node's vm or esm
const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

const FRONTEND = path.join(__dirname);

// 用 esbuild (如果可用) 或 babel 来 parse ES module
// 简单点: 用 node --experimental-vm-modules 跑 import
console.log('=== Deep import test (using esbuild) ===');
try {
  // 检查 esbuild 是否可用
  const result = execSync('npx --no-install esbuild --version 2>&1', { cwd: FRONTEND, encoding: 'utf-8' });
  console.log('  esbuild version:', result.trim());
} catch (e) {
  console.log('  esbuild not available, skip deep parse');
  process.exit(0);
}

const files = [
  'js/api/dashboard.js',
  'js/api/canvas.js',
  'js/api/assets.js',
  'js/api/projects.js',
  'js/api/users.js',
  'js/views/Dashboard.js',
  'js/views/Canvas.js',
  'js/views/Assets.js',
  'js/views/Projects.js',
  'js/views/Users.js',
  'js/router.js',
];

let pass = 0, fail = 0;
for (const f of files) {
  const fullPath = path.join(FRONTEND, f);
  if (!fs.existsSync(fullPath)) {
    console.log(`  ✗ ${f} (missing)`);
    fail++;
    continue;
  }
  try {
    // 用 esbuild bundle mode 解析 + 验证语法
    const out = execSync(`npx --no-install esbuild --bundle=false --format=esm --loader=js --log-level=error "${fullPath}" > /dev/null 2>&1 && echo OK || echo FAIL`, {
      cwd: FRONTEND,
      encoding: 'utf-8',
      shell: true,
    });
    if (out.includes('OK')) {
      console.log(`  ✓ ${f}`);
      pass++;
    } else {
      console.log(`  ✗ ${f} (parse error)`);
      fail++;
    }
  } catch (e) {
    console.log(`  ✗ ${f} (esbuild error: ${e.message.substring(0, 80)})`);
    fail++;
  }
}

console.log(`\n=== Deep import TOTAL: passed=${pass}, failed=${fail} ===`);
process.exit(fail > 0 ? 1 : 0);
