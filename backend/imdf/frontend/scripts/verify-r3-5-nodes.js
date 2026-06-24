#!/usr/bin/env node
/**
 * R3.5-W3: 49 节点 IO 契约验证脚本 (ESM)
 * --------------------------------------------------------------------
 * 验证 R3.5-W1 + R3.5-W2 修复后 49 节点文件:
 *   1. 正确 import NodeDataShape (type-only) from './types'
 *   2. 正确 import mergeDefaultData (value) from './defaults'
 *   3. 至少 1 处调用 mergeDefaultData(...)
 *   4. 无 `const d = (data ...) as any` bad pattern (新代码 0 处)
 *   5. 有 IO CONTRACT MARKER 注释
 *
 * Usage:
 *   node scripts/verify-r3-5-nodes.js
 *
 * Exit code:
 *   0 - 全部 PASS
 *   1 - 有 FAIL
 * --------------------------------------------------------------------
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const NODES_DIR = path.join(__dirname, '..', 'src', 'nodes');
const REPORT_FILE = path.join(__dirname, '..', '..', '..', '..', 'reports', 'r3_5_w3.json');

// 4 种 bad pattern 正则 (R3-W4 verify 报告 §3 列出的 30 个原 bad pattern)
const BAD_PATTERNS = [
  { name: 'const d = (data || {}) as any', regex: /const\s+d\s*=\s*\(\s*data\s*\|\|\s*\{\s*\}\s*\)\s*as\s+any/ },
  { name: 'const d = (data as any) || {}', regex: /const\s+d\s*=\s*\(\s*data\s+as\s+any\s*\)\s*\|\|\s*\{\s*\}/ },
  { name: 'const d = data as any',         regex: /const\s+d\s*=\s*data\s+as\s+any\s*;/ },
];

// 期望模式
const REQUIRED_IMPORTS = [
  { name: 'NodeDataShape type import',     regex: /import\s+type\s*\{\s*NodeDataShape\s*\}\s*from\s*['"]\.\/types['"]/ },
  { name: 'mergeDefaultData value import', regex: /import\s*\{[^}]*\bmergeDefaultData\b[^}]*\}\s*from\s*['"]\.\/defaults['"]/ },
];

const REQUIRED_CALLS = [
  { name: 'mergeDefaultData() call', regex: /\bmergeDefaultData\s*\(/ },
];

const REQUIRED_MARKER = [
  { name: 'IO CONTRACT MARKER', regex: /R3-Worker-4\s+IO\s+CONTRACT\s+MARKER/i },
];

/**
 * 列出 src/nodes 下的所有 *_node.tsx 文件
 */
function listNodeFiles() {
  const files = fs.readdirSync(NODES_DIR);
  return files
    .filter((f) => f.endsWith('_node.tsx'))
    .sort();
}

/**
 * 单文件验证
 */
function verifyFile(file) {
  const filepath = path.join(NODES_DIR, file);
  const content = fs.readFileSync(filepath, 'utf8');
  const findings = {
    file,
    hasTypeImport: false,
    hasDefaultsImport: false,
    mergeDefaultDataCalls: 0,
    badPatternHits: [],
    hasMarker: false,
    typeKey: null,
    pass: true,
    notes: [],
  };

  // 1. 必需 imports
  for (const check of REQUIRED_IMPORTS) {
    if (check.regex.test(content)) {
      if (check.name.includes('NodeDataShape')) findings.hasTypeImport = true;
      if (check.name.includes('mergeDefaultData')) findings.hasDefaultsImport = true;
    }
  }

  // 2. 调用次数 (排除 JSDoc 注释行)
  const callMatches = [];
  const codeOnlyLines = content.split('\n').filter(
    (line) => !line.trim().startsWith('*') && !line.trim().startsWith('//') && !line.trim().startsWith('/*')
  );
  const codeOnlyContent = codeOnlyLines.join('\n');
  const realCallMatches = codeOnlyContent.match(/\bmergeDefaultData\s*\(/g) || [];
  const allCallMatches = content.match(/\bmergeDefaultData\s*\(/g) || [];
  findings.mergeDefaultDataCalls = realCallMatches.length;
  findings.totalMentionCount = allCallMatches.length;

  // 3. bad pattern
  for (const bp of BAD_PATTERNS) {
    if (bp.regex.test(content)) {
      findings.badPatternHits.push(bp.name);
    }
  }

  // 4. marker
  for (const m of REQUIRED_MARKER) {
    if (m.regex.test(content)) findings.hasMarker = true;
  }

  // 5. 提取 type key (从 IO CONTRACT MARKER 注释)
  const markerMatch = content.match(/类型\s*key\s*[:：]\s*(\S+)/);
  if (markerMatch) findings.typeKey = markerMatch[1];

  // 判断 PASS / FAIL
  const errors = [];
  if (!findings.hasTypeImport) errors.push('缺 NodeDataShape type import');
  if (!findings.hasDefaultsImport) errors.push('缺 mergeDefaultData value import');
  if (findings.mergeDefaultDataCalls < 1) errors.push('mergeDefaultData 调用次数为 0');
  if (findings.badPatternHits.length > 0) errors.push(`发现 ${findings.badPatternHits.length} 处 bad pattern`);
  if (!findings.hasMarker) errors.push('缺 IO CONTRACT MARKER 注释');

  if (errors.length > 0) {
    findings.pass = false;
    findings.notes = errors;
  }

  return findings;
}

/**
 * 主入口
 */
function main() {
  const files = listNodeFiles();
  if (files.length === 0) {
    console.error('ERROR: 未找到 _node.tsx 文件 in', NODES_DIR);
    process.exit(2);
  }

  console.log(`[R3.5-W3] 验证 ${files.length} 节点 IO 契约\n`);
  console.log('目录:', NODES_DIR);
  console.log('='.repeat(80));

  const results = [];
  let passCount = 0;
  let failCount = 0;

  for (const file of files) {
    const r = verifyFile(file);
    results.push(r);
    if (r.pass) {
      passCount++;
      console.log(`  PASS  ${file.padEnd(45)} calls=${r.mergeDefaultDataCalls}  type=${r.typeKey || '?'}`);
    } else {
      failCount++;
      console.log(`  FAIL  ${file.padEnd(45)} calls=${r.mergeDefaultDataCalls}  type=${r.typeKey || '?'}`);
      for (const n of r.notes) console.log(`         - ${n}`);
    }
  }

  // 全局统计 - 实际代码调用次数
  const totalRealCalls = results.reduce((s, r) => s + r.mergeDefaultDataCalls, 0);
  const totalMentions = results.reduce((s, r) => s + r.totalMentionCount, 0);
  console.log(`\n实际代码 mergeDefaultData() 调用总数: ${totalRealCalls} (含 doc comment 共 ${totalMentions} 处)`);

  console.log('='.repeat(80));
  console.log(`总计: ${files.length} 节点 | PASS: ${passCount} | FAIL: ${failCount}`);
  console.log();

  // bad pattern 总数
  const totalBad = results.reduce((s, r) => s + r.badPatternHits.length, 0);
  console.log(`全局 'const d = (data ...) as any' bad pattern: ${totalBad} 处`);

  // 缺失 import 节点
  const missingTypeImport = results.filter((r) => !r.hasTypeImport).map((r) => r.file);
  const missingDefaultsImport = results.filter((r) => !r.hasDefaultsImport).map((r) => r.file);
  if (missingTypeImport.length > 0) {
    console.log(`缺 NodeDataShape import 节点: ${missingTypeImport.length} 个`);
  }
  if (missingDefaultsImport.length > 0) {
    console.log(`缺 mergeDefaultData import 节点: ${missingDefaultsImport.length} 个`);
  }

  // 写 JSON 报告
  const summary = {
    timestamp: new Date().toISOString(),
    nodesDir: NODES_DIR,
    totalFiles: files.length,
    pass: passCount,
    fail: failCount,
    totalBadPatterns: totalBad,
    missingTypeImport,
    missingDefaultsImport,
    files: results,
  };

  // 确保 reports 目录存在 (相对 project root)
  const reportDir = path.dirname(REPORT_FILE);
  if (!fs.existsSync(reportDir)) {
    fs.mkdirSync(reportDir, { recursive: true });
  }
  fs.writeFileSync(REPORT_FILE, JSON.stringify(summary, null, 2), 'utf8');
  console.log(`\nJSON 报告已写入: ${REPORT_FILE}`);

  // 退出码
  process.exit(failCount > 0 ? 1 : 0);
}

main();
