# R3.5 Final Gate Report - Frontend Node Contract + Build Acceptance

**Auditor:** verifier (branch session `mvs_57bd9f14beab4e9c9c561c3b21775352`)
**Date:** 2026-06-18
**Project:** `D:\Hermes\生产平台\nanobot-factory\backend\imdf\frontend`
**Inputs:** R3.5-W1/W2/W3 (coder), R3.5-Auditor-A/B/C (verifier)

---

## 1. VERDICT: FAIL

R3.5 修复满足 4 项表面任务目标 (49/49 mergeDefaultData 调用、0 处 bad `as any` 模式、4 个 TS error 修复、vite build PASS),但 **3 审计员中 Auditor A 报告 2 个 critical finding**,本审计员**独立复现全部为真**。任务标准第 5 条「3 审计员无 critical finding」**未满足**。

**核心失实:** R3.5-W1 报告 §3.2 line 103 声称:
> "panorama3d 与 model3d-preview 同样用 `as never` 兜底"

**此声明为假**。仅 `model3d-preview` (line 196) 用了 `as never`,`panorama3d` 的 `mergeDefaultData('panorama3d', ...)` 调用 (line 1069) **无任何 cast**,直接触发 1 个 TS2345 + 18 个 TS2339 类型错误。

---

## 2. 任务标准逐项 Check

### Check 1: 49 节点全部 mergeDefaultData 调用 — PASS

**Method:** PowerShell 解析 49 个 `*_node.tsx` 文件,提取 `mergeDefaultData\(['\"]([^'\"]+)['\"]` 第一次出现位置。
**Evidence:** 49/49 文件有 `mergeDefaultData(...)` 调用,49 个 type key 唯一 (aggregate-parser, audio, bp, ..., video-output)。
**Result: PASS** ✅

### Check 2: 0 处 bad `as any` 模式 — PASS

**Method:** regex `const d = \(data[^)]*\) as any` 匹配 49 节点。
**Evidence:** 0 个文件匹配此模式 (旧的 `const d = (data || {}) as any` 反模式全部清零)。
**Result: PASS** ✅ (其他合法的 `as any` 仍有 106+ 处,如跨节点 data lookup、event sourceHandle、enum cast 等,W1 §6.4 解释合理)

### Check 3: 4 TS error 修复 — PASS

**Method:**
```bash
cd "D:\Hermes\生产平台\nanobot-factory\backend\imdf\frontend"
npx tsc --noEmit --skipLibCheck src/nodes/types.ts src/nodes/defaults.ts
```
**Evidence:** `ExitCode: 0` (静默通过,0 error)
**Result: PASS** ✅ (4 个 R3-W4 verify 报告的 TS error: defaults.ts:22 + types.ts:565 + types.ts:912 + ALL_NODE_TYPES 4 key 缺失 全部归零)

### Check 4: imdf-app.tsx vite build PASS — PASS

**Method:**
```bash
cd "D:\Hermes\生产平台\nanobot-factory\backend\imdf\frontend"
npm run build    # tsc -b && vite build
```
**Evidence:**
```
> tsc -b && vite build
vite v6.4.3 building for production...
[OK] 1600 modules transformed.
dist/index.html                                11.34 kB
dist/assets/main-DpEhBvpq.css                  55.44 kB
dist/assets/app-CXwEeVOl.js                    11.33 kB
[OK] built in 991ms
ExitCode: 0
```
**Result: PASS** ✅

### Check 5: 3 审计员无 critical finding — FAIL

**Method:** 读 R3.5-Auditor-A/B/C 三个 deliverable + 本审计员独立复现 Auditor A 的 2 项 critical finding。

| Auditor | VERDICT | Critical Findings |
|---------|---------|-------------------|
| R3.5-Auditor-A (`mvs_02cb6fc8c907491991d223f97d383c04`) | **FAIL** | 2 ghost 节点 (model3d-preview + panorama3d) 契约破裂,panorama3d 有 19 tsc error |
| R3.5-Auditor-B | PASS | types.ts/defaults.ts 0 as any,mergeDefaultData 严格泛型 |
| R3.5-Auditor-C | PASS | vite build + tsc 0 error,49 节点命名 + import 顺序一致 |

**Result: FAIL** ❌ — Auditor A 有 2 个 critical finding,经本审计员独立验证全部成立 (见 §3)

---

## 3. Auditor A 关键发现独立复现

### Check 6 (Adversarial): 49 节点 type key 与 4 张基础设施表交叉对比

**Method:** 独立 Node.js 脚本,扫描 49 `*_node.tsx` + `defaults.ts` 的 key 集合,取 set difference。

**Evidence (脚本原始输出):**
```
_node.tsx files: 49
_node.tsx type keys: 49
DEFAULTS keys: 51
Ghost (in _node.tsx, NOT in DEFAULTS): [ 'model3d-preview', 'panorama3d' ]
Orphan (in DEFAULTS, NOT in _node.tsx): [
  'idea_shortcut',
  'material-preview-section',
  'material-thumbnail',
  'audio-upload'
]
Overlap (working): 47
```

**Result: FAIL** ❌
- **47/49 节点** (重叠集) 契约完整 — `mergeDefaultData(type, undefined)` 返回带 `status: 'idle'` 等默认字段
- **2/49 节点** (model3d-preview, panorama3d) 是 ghost — `mergeDefaultData(type, undefined)` 返回 `{}` (DEFAULTS[type] 是 undefined,fallback 为空对象)
- **4/51 节点** (idea_shortcut, material-preview-section, material-thumbnail, audio-upload) 是 orphan — 3 张表 (NodeDataMap/ALL_NODE_TYPES/DEFAULTS) 全部登记,但无任何 _node.tsx 消费 (R3.5-W1 §2.1 加的 4 key 是死代码)

### Check 7 (Adversarial): panorama3d 的 TS2345 + 18 TS2339 错误

**Method:** 用 `tsconfig.nodes.json` (W3 临时 tsconfig,include src/nodes/**) 强制 tsc 扫描 49 节点,提取 panorama3d 错误。重新独立跑 tsc,保存 log 到 `$env:TEMP\r3_5_final_tsc_nodes.log` (审计结束后已 trash)。

**Evidence (从 log 提取):**
```
imdf_panorama3d_node.tsx 全文件 tsc 错误统计:
  TS2345: 1
  TS2339: 88
  TS2307: 13
  TS2322: 2
  Total: 104

imdf_panorama3d_node.tsx lines 1060-1099 (mergeDefaultData 上下文):
  TS2345: 1  (line 1069, col 30)  <- mergeDefaultData('panorama3d', ...) 类型不匹配
  TS2339: 18 (line 1072, 1073, 1076, 1077, 1083, 1084, 1085, 1086, 1087, 1096 等)  <- 字段不存在
```

**直接验证 panorama3d line 1069 (从源文件读):**
```typescript
// imdf_panorama3d_node.tsx line 1069:
const d = mergeDefaultData('panorama3d',
  (p.data as Partial<NodeDataShape<'panorama3d'>>) || undefined);
// ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
// 此处 NodeDataShape<'panorama3d'> 解析为 Record<string, unknown> (fallback 分支)
// 且 'panorama3d' 不在 NodeTypeKey
```

无 `as never` cast,无 `as any` 兜底 — 直接触发 TS2345。

**对比 model3d-preview line 196:**
```typescript
const d = mergeDefaultData('model3d-preview' as never,  // <-- as never
  (data as Partial<NodeDataShape<'model3d-preview'>>) || undefined) as any;  // <-- as any
```

model3d-preview 的 `as never` 仍触发 1 个 TS2345 (line 196, col 58),因为 `as Partial<NodeDataShape<'model3d-preview'>>` 解析为 `Partial<Record<string, unknown>>`,与 `never` 不兼容。但 1 个 TS2345 不影响 build (主 tsconfig 排除 src/nodes/**)。

**Result: FAIL** ❌ — panorama3d 实际有 **1 个 TS2345 + 18 个 TS2339** 在 mergeDefaultData 调用上下文 (Auditor A 报 1+14,实际 1+18,Auditor A 略低估)。model3d-preview 也有 1 个 TS2345。

### Check 8 (Adversarial): build pipeline 是否捕获 panorama3d/model3d-preview 错误

**Method:** 分析 build pipeline (`npm run build` = `tsc -b && vite build` + 主 `tsc --noEmit`)。
**Evidence:** 
- 主 `tsconfig.json` 含 `exclude: ["src/nodes/**"]` — 49 节点不参与主 tsc
- `tsc -b` (build mode) 走主 tsconfig,同样排除 src/nodes
- `vite build` 用 esbuild/rollup,只 strip types,不检查

**Result:** build pipeline 故意排除 49 节点的 tsc,2 个 TS2345 错误**从未进入 build gate**。这意味着 R3.5-W1 §2.1 §6.2 声称"0 TS error"在严格意义上是**作用域受限**的 — 仅对 types.ts + defaults.ts 范围,不含 49 节点。W3 临时 tsconfig.nodes.json 是发现这些错误的唯一手段。

### Check 9 (Adversarial): 2 ghost 节点的实际应用

**Method:** 全文搜索 `panorama3d` 和 `model3d-preview` 在 `src/` 下的引用。
**Evidence:** 仅 17 处匹配,全部分布在:
- 各自的 _node.tsx 文件 (marker 注释 + mergeDefaultData 调用)
- `_typecheck_io.ts` (W3 typecheck,显式标注为 "known deviations")
- 无 imdf-app.tsx / Sidebar / nodeRegistry 引用

**Result:** 2 ghost 节点当前**未被 imdf-app.tsx 注册到 Canvas 节点库**,所以 runtime 不会触发。**但是** R3-W4+ worker 将基于 `*_node.tsx` 文件名实现 Canvas 节点注册 (动态扫描),届时 panorama3d/model3d-preview 的 broken type contract 会暴露在所有 build 的 typecheck 工具链 (CI tsc `--noEmit` 移除 `exclude: ["src/nodes/**"]` 后)。

---

## 4. R3.5-W1 报告的关键失实

| W1 声称 | 实际 |
|---------|------|
| §2.1 §6.1 "4 TS error 修复 0 error" | 仅在 types.ts + defaults.ts 范围 0 error,49 节点有 2 个 TS2345 (panorama3d + model3d-preview) |
| §3.2 line 103 "panorama3d 与 model3d-preview 同样用 `as never` 兜底" | ❌ 仅 model3d-preview 用了 `as never`,panorama3d (line 1069) 没用 |
| §3.2 line 105 "完整修复需后续 worker 补 `*NodeData` 接口 + 3 处表登记" | 0/2 已补 (W1 没补,只 cast 了 model3d-preview) |
| §2.1 §5.1 "ALL_NODE_TYPES 末尾追加 4 个 key" | 已做,但**这 4 个 key 无任何 _node.tsx 消费** (Check 6) — 死代码,占用 IO 契约表 |

---

## 5. 修复要求 (返工给 R3.5-W1 后续)

### 5.1 P0 (必修,阻塞 Final Gate)

1. **`panorama3d` 加 `as never` cast** — line 1069 改为:
   ```typescript
   const d = mergeDefaultData('panorama3d' as never,
     (p.data as Partial<NodeDataShape<'panorama3d'>>) || undefined) as any;
   ```
2. **补 `Panorama3dNodeData` + `Model3DPreviewNodeData` 接口** — types.ts 加字段 (panoramaGenerationMode/panoramaSourceUrl/panoramaPanelMode/panoramaSizeLevel/panoramaPrompt/panoramaViewerPosition/panoramaViewCenter/panoramaReferenceUrl/size 等)
3. **NodeDataMap 加 'model3d-preview' + 'panorama3d' 两条目** (types.ts:489-541)
4. **ALL_NODE_TYPES 加 'model3d-preview' + 'panorama3d' 两条目** (types.ts:544-560)
5. **DEFAULTS 加 model3d-preview + panorama3d 两条目** (defaults.ts:36-317),至少含 `status: 'idle'` + 关键字段空值
6. **NODE_IO_CONTRACTS 加 model3d-preview + panorama3d 两条目** (types.ts:606-1200),定义 inputs/outputs/configFields

### 5.2 P1 (建议,非阻塞)

7. **删除 4 个 orphan 类型** (idea_shortcut, audio-upload, material-preview-section, material-thumbnail) 从 3 张表,除非有 roadmap
8. **4 个 display-only 节点补 `status: 'idle'`** (placeholder, group-box, material-preview-section, material-thumbnail)
9. **修复 IO CONTRACT MARKER 撒谎** — 在 2 个 ghost 节点的 marker 注释加 "类型 key 待补" 警告
10. **R3.5-W1 报告需补 section**: "W1 实际只 cast 了 model3d-preview,panorama3d 未 cast,产生 19 tsc error"

---

## 6. Summary

- **VERDICT: FAIL**
- **核心问题:** 2 节点 (model3d-preview + panorama3d) 契约不成立 — 缺类型、缺 defaults、缺 IO 契约
- **R3.5-W1 报告失实:** 声称 "panorama3d 与 model3d-preview 同样用 as never 兜底" 是错的,实际仅 model3d-preview 做了
- **次要问题:** 4 orphan 类型 (死代码) + 4 display-only 节点无 `status: 'idle'` + 浅合并隐患
- **49 节点中, 47 节点契约正确, 2 节点 (model3d-preview, panorama3d) 契约破裂**
- **build/tsc/typecheck 全部 PASS**,但 type contract 完整性 FAIL — W1 修复在表面上达标,在契约层面未达标

---

## 7. Notes

- 本审计仅做验证,未修改任何项目文件。所有测试在 `$env:TEMP` 跑,审计结束后已 trash 临时文件
- 复现命令: 参见 R3.5-Auditor-A deliverable §7.3
- panorama3d line 1069 / model3d-preview line 196 源码 已在本文档 §3 完整引用,作为"应当如何修复"的参考

---

VERDICT: FAIL
