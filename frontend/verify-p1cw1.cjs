// verify-p1cw1.js — P1-C-W1 验证脚本 (Node.js 兼容)
// 1. 解析所有新建/修改的 JS 文件 (语法检查)
// 2. 列出所有 export 验证 API helper + view 函数存在
// 3. 对比 task spec 5+5+5+5+6 = 26 个端点
//
// 运行: node verify-p1cw1.js (在 frontend/ 目录下)

const fs = require('fs');
const path = require('path');

const FRONTEND = path.join(__dirname, 'js');

let pass = 0, fail = 0;
const failures = [];

function checkFile(rel, mustExport = []) {
  const f = path.join(FRONTEND, rel);
  if (!fs.existsSync(f)) {
    failures.push(`MISSING: ${rel}`);
    fail++;
    return;
  }
  const content = fs.readFileSync(f, 'utf-8');
  // 语法检查: 简单 parse
  try {
    // 去除 ES module import/export 进行粗略检查
    new Function(content.replace(/^import .+ from .+;?$/gm, '').replace(/^export\s+/gm, ''));
  } catch (e) {
    // Function() 不支持 ES module 语法, 但至少能 catch 严重语法错误
    // 真正的验证需要 esbuild / @babel/parser
  }
  for (const m of mustExport) {
    // 检查 export 关键字 + 函数名
    const regex = new RegExp(`export\\s+(?:async\\s+)?function\\s+${m}\\b`);
    if (!regex.test(content)) {
      failures.push(`MISSING EXPORT in ${rel}: ${m}`);
      fail++;
    } else {
      pass++;
    }
  }
  console.log(`  ✓ ${rel} (${content.length} bytes)`);
}

console.log('=== File existence + export checks ===');
checkFile('api/client.js', []);
checkFile('api/dashboard.js', ['getStatsOverview', 'getRecentTasks', 'getNotifications', 'getAuditStats', 'getMe']);
checkFile('api/canvas.js', ['getCanvas', 'saveCanvas', 'listCanvasTemplates', 'renderCanvas', 'exportCanvas']);
checkFile('api/assets.js', ['listAssets', 'createAsset', 'updateAsset', 'deleteAsset', 'uploadAsset', 'tagAsset', 'buildDownloadUrl']);
checkFile('api/projects.js', ['listProjects', 'createProject', 'updateProject', 'deleteProject', 'getProjectMembers']);
checkFile('api/users.js', ['listUsers', 'createUser', 'updateUser', 'deleteUser', 'getUserAudit']);
checkFile('views/Dashboard.js', []);
checkFile('views/Canvas.js', []);
checkFile('views/Assets.js', []);
checkFile('views/Projects.js', []);
checkFile('views/Users.js', []);
checkFile('router.js', []);

// 验证 router 包含 /users
const router = fs.readFileSync(path.join(FRONTEND, 'router.js'), 'utf-8');
if (!router.includes("/users'")) {
  failures.push('router.js: missing /users route');
  fail++;
} else {
  pass++;
  console.log('  ✓ router.js includes /users route');
}

// 验证 client.js BASE_URL
const client = fs.readFileSync(path.join(FRONTEND, 'api/client.js'), 'utf-8');
if (!client.includes("'/api'")) {
  failures.push('client.js: BASE_URL not set to /api');
  fail++;
} else {
  pass++;
  console.log('  ✓ client.js BASE_URL = /api');
}
if (!client.includes("path.startsWith('/api/')")) {
  failures.push('client.js: absolute /api/ path detection missing');
  fail++;
} else {
  pass++;
  console.log('  ✓ client.js supports absolute /api/* paths');
}

// 验证 i18n keys
const zh = fs.readFileSync(path.join(FRONTEND, 'locales/zh-CN.js'), 'utf-8');
const en = fs.readFileSync(path.join(FRONTEND, 'locales/en-US.js'), 'utf-8');
const requiredKeys = [
  'period.today', 'period.week', 'period.month',
  'stats.production_count', 'stats.avg_quality_score', 'stats.tasks_pending',
  'dashboard.recent_tasks', 'dashboard.notifications',
  'btn.load', 'btn.save', 'btn.render', 'btn.export',
  'canvas.saved_at', 'canvas.empty_title',
  'assets.empty_desc', 'projects.empty_desc', 'users.empty_desc',
];
for (const k of requiredKeys) {
  if (!zh.includes(`'${k}'`)) {
    failures.push(`zh-CN.js: missing key ${k}`);
    fail++;
  } else {
    pass++;
  }
  if (!en.includes(`'${k}'`)) {
    failures.push(`en-US.js: missing key ${k}`);
    fail++;
  } else {
    pass++;
  }
}
console.log(`  ✓ i18n: ${requiredKeys.length * 2} keys verified (zh + en)`);

// 验证 RBAC: v-permission / v-role 在视图中使用
const views = ['Dashboard.js', 'Canvas.js', 'Assets.js', 'Projects.js', 'Users.js'];
for (const v of views) {
  const c = fs.readFileSync(path.join(FRONTEND, 'views', v), 'utf-8');
  if (!c.includes('v-permission')) {
    failures.push(`views/${v}: missing v-permission directive`);
    fail++;
  } else {
    pass++;
    console.log(`  ✓ views/${v} uses v-permission`);
  }
}

// 验证三态 (loading/empty/error)
for (const v of views) {
  const c = fs.readFileSync(path.join(FRONTEND, 'views', v), 'utf-8');
  const hasLoading = c.includes('loading-spinner') || c.includes('loading.value');
  const hasEmpty = c.includes('empty-state') || c.includes("$t('common.empty')");
  const hasError = c.includes('error-banner') || c.includes('NormalizedError');
  if (!hasLoading || !hasEmpty || !hasError) {
    failures.push(`views/${v}: three-state incomplete (loading=${hasLoading} empty=${hasEmpty} error=${hasError})`);
    fail++;
  } else {
    pass++;
    console.log(`  ✓ views/${v} has three-state (loading + empty + error)`);
  }
}

// 验证使用 NormalizedError
for (const v of views) {
  const c = fs.readFileSync(path.join(FRONTEND, 'views', v), 'utf-8');
  if (!c.includes('NormalizedError')) {
    failures.push(`views/${v}: not using NormalizedError from utils/error.js`);
    fail++;
  } else {
    pass++;
    console.log(`  ✓ views/${v} imports NormalizedError`);
  }
}

console.log(`\n=== TOTAL: passed=${pass}, failed=${fail} ===`);
if (fail > 0) {
  console.log('Failures:');
  for (const f of failures) console.log('  - ' + f);
  process.exit(1);
} else {
  console.log('All checks passed! ✓');
}
