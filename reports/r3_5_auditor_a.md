# R3.5 审计员 A 报告 — 前端节点契约业务正确性审计

**审计员**: Mavis 兼 Auditor-A
**视角**: R3.5 修复后 49 节点 IO 契约**业务正确性**(非类型安全 — Auditor-B 范畴)
**审计时间**: 2026-06-18 10:54-11:10 (Asia/Shanghai, UTC+8)
**项目**: imdf 商业级打磨 — 前端 R3 残留修复
**项目根**: `D:\Hermes\生产平台\nanobot-factory\backend\imdf\frontend`

---

## 一、审计范围

| 资产 | 路径 | 数量/规模 |
|------|------|-----------|
| 49 节点源文件 | `src\nodes\imdf_*_node.tsx` | 49 文件 (实际使用 49 个 type key) |
| 节点共享类型 | `src\nodes\types.ts` | 1,200 行,含 NodeDataMap (51) / ALL_NODE_TYPES (51) / NODE_IO_CONTRACTS (47) |
| 节点默认数据 | `src\nodes\defaults.ts` | 318 行,含 DEFAULTS (51) + 3 工厂函数 |
| 上游 R3.5-W1 报告 | `D:\Hermes\生产平台\nanobot-factory\reports\r3_5_w1.md` | 30 节点补全 + 4 TS error 修复 |
| 上游 R3.5-W3 报告 | `D:\Hermes\生产平台\nanobot-factory\reports\r3_5_w3.md` | 49/49 IO 契约验证 PASS |
| 上游 R3-W4 验证 | `D:\Hermes\生产平台\nanobot-factory\reports\r3_w4_verify.md` | R3-W4 验收到 R3.5-W1 的 30 节点补全 |

**审计员职责范围 (与 Auditor-B 区分)**:
- Auditor-A 关注**业务正确性**: 数据契约覆盖场景、默认值用户友好、merge 工厂真合并
- Auditor-B 关注**类型安全**: 0 处 as any、泛型严格、未使用 import/dead code
- Auditor-C 关注**构建与代码质量**: vite build、tsc 全项目、代码异味

---

## 二、6 维度审计框架

本审计从 6 维度评估"业务正确性":

| # | 维度 | 期望 | 实际 | 状态 |
|---|------|------|------|------|
| 1 | **Schema 完整性** — 49 节点都有类型定义 | 49/49 | 47/49 (model3d-preview/panorama3d 缺) | **FAIL** |
| 2 | **DEFAULTS 默认值覆盖** — 49 节点都有默认 data 形态 | 49/49 | 47/49 (同上 2 个缺) | **FAIL** |
| 3 | **mergeDefaultData 工厂正确性** — 49 节点真合并 user + defaults | 49/49 | 47/49 (2 个节点 merge 返回 `{}`) | **FAIL** |
| 4 | **类型契约强制** — 49 节点用 `NodeDataShape<T>` 强类型 | 49/49 | 49/49 ✅ | **PASS** |
| 5 | **IO 契约元数据** — 49 节点有 NODE_IO_CONTRACTS 条目 | 49/49 | 47/49 (同上 2 个缺) | **FAIL** |
| 6 | **跨表一致性** — 4 张基础设施表互通 | 100% | 4 个死类型 + 2 个 ghost 类型 | **FAIL** |

**总体**: 1/6 PASS (类型契约强制) + 4/6 FAIL + 1 N/A (次要)

---

## 三、3 基础模型 (Base Models) 审计

types.ts 定义 3 个**被广泛继承**的基础 interface:

| # | 模型 | 字段 | 被多少 *NodeData 接口 extends |
|---|------|------|----------------------------|
| 1 | `NodeRunStatus` (L22-27) | `status?: 'idle'\|'running'\|'success'\|'error'`, `error?: string\|null`, `lastRunAt?: number` | **41** |
| 2 | `NodePromptOutput` (L30-37) | `prompt?: string`, `promptResolved?: string`, `promptMentions?: MediaMention[]` | **16** |
| 3 | `MediaMention` (L40-47) | `token: string`, `materialId: string`, `kind: 'image'\|'video'\|'audio'\|'text'` | 间接 (被 NodePromptOutput 引用) |

**总 47 个 *NodeData 接口** 加上 **AudioUploadNodeData (extends UploadNodeData)** + **IdeaNodeDataShape** + **MaterialPreviewSectionData** + **MaterialThumbnailData** = **51 个类型**登记进 NodeDataMap。

**Result: PASS** ✅ — 3 模型定义清晰,继承结构合理。`NodeRunStatus` 几乎全节点共用 (41/47),`NodePromptOutput` 是 prompt 节点的契约基础 (16/47),`MediaMention` 是 @素材 引用机制的基础。

---

## 四、5 项验收项 (Acceptance Criteria) — 详细 PASS/FAIL

### 验收项 1: 49 节点全部在 NodeDataMap / ALL_NODE_TYPES / DEFAULTS / NODE_IO_CONTRACTS 4 表中登记

**检查方法**:
1. 解析 4 张表的 key 数量 (brace-depth tracking + regex)
2. 提取 49 个 _node.tsx 文件的 `mergeDefaultData('KEY', ...)` 第一个参数
3. 对 4 张表做交叉对比

**证据** (4 张表的 key 数量):

| 表 | key 数量 | 位置 |
|----|--------|------|
| NodeDataMap | **51** | types.ts:489-541 |
| ALL_NODE_TYPES | **51** | types.ts:544-560 |
| DEFAULTS | **51** | defaults.ts:36-317 |
| NODE_IO_CONTRACTS | **47** | types.ts:606-1200 |
| _node.tsx 实际使用 | **49** | src/nodes/*_node.tsx |

**关键不匹配 (Adversarial Probe)**:

| 方向 | 类型 | 数量 |
|------|------|------|
| 在 _node.tsx 用但**不在** NodeDataMap | `model3d-preview`, `panorama3d` | 2 (ghost 类型) |
| 在 _node.tsx 用但**不在** ALL_NODE_TYPES | 同上 | 2 |
| 在 _node.tsx 用但**不在** DEFAULTS | 同上 | 2 |
| 在 _node.tsx 用但**不在** NODE_IO_CONTRACTS | 同上 | 2 |
| 在 4 张表里登记但**无任何** _node.tsx 消费 | `idea_shortcut`, `audio-upload`, `material-preview-section`, `material-thumbnail` | 4 (死类型) |

**Result: FAIL** ❌

- 2 个 ghost 类型节点 (model3d-preview, panorama3d) 违反 4 表一致性
- 4 个死类型 (idea_shortcut, audio-upload, material-preview-section, material-thumbnail) 在 4 张表里全数登记但无 _node.tsx 消费 — 是"未使用死代码"占据 IO 契约表

---

### 验收项 2: mergeDefaultData 工厂真合并 user data + defaults (47/49 + 2 FAIL)

**检查方法**: 写独立 ESM 测试脚本到 `$env:TEMP/real_audit_XXXX.mjs`,复制 51 个 DEFAULTS 条目 + `mergeDefaultData` 函数,对 49 个 type key 跑 4 个场景。

**证据 (实际 node 脚本输出)**:

```
=== Test 1: mergeDefaultData with user=undefined (defaults-only) ===
  EMPTY: model3d-preview
  EMPTY: panorama3d
  Result: 2/49 empty

=== Test 2: mergeDefaultData with partial user (defaults preserved?) ===
  Result: 0/49 shallow  (47/47 正确;2 个空 defaults 无法 shallow merge)

=== Test 3: mergeDefaultData with user=null (should NOT throw) ===
  Result: 0/49 threw
```

**真实生产代码 (defaults.ts:26-32)**:
```ts
export function mergeDefaultData<T extends NodeTypeKey>(type, user) {
  const base = DEFAULTS[type] as unknown as Record<string, unknown>;
  return { ...base, ...(user ?? {}) } as NodeDataMap[T];
}
```

**当 type key 不在 DEFAULTS 时**:
- `DEFAULTS['model3d-preview']` = `undefined`
- `{ ...undefined, ...(user ?? {}) }` = `user ?? {}`
- 行为: **不应用任何默认值,仅返回 user data**

**用户场景影响** (从 `mergeDefaultData('image', { model: 'dall-e-3' })` 实际输出):
- `image` 节点: `{"model":"dall-e-3","ratio":"1:1","size":"1024x1024","n":1,"referenceImages":[],"status":"idle"}` ✅ 正确
- `model3d-preview` 节点: `{"size":{"w":800,"h":600}}` ❌ 缺 `status: 'idle'` 和其他 defaults

**Result: FAIL** ❌

- 47/49 节点的 merge 行为正确 (user override 优先,其余 defaults 保留)
- 2/49 节点的 merge 行为错误: 返回 `{}` (user=undefined) 或仅 user data (user 已设)
- 这 2 个节点在生产环境**不会有 status='idle' 状态机启动**

---

### 验收项 3: defaults.ts 默认值符合用户常见场景 (47/49 PASS)

**检查方法**: 读 51 个 DEFAULTS 条目,逐项评估用户拖入/工作流加载场景的友好度。

**证据 (关键 defaults 评估)**:

| 节点 | 关键默认 | 评估 |
|------|---------|------|
| `image` | `model: 'gpt-image-2'`, `ratio: '1:1'`, `size: '1024x1024'`, `n: 1` | ✅ 主流模型 + 1:1 比例 |
| `audio` | `model: 'tts-1'`, `voice: 'alloy'`, `speed: 1.0`, `pitch: 1.0` | ✅ OpenAI TTS 标准 |
| `llm` | `model: 'gpt-4o-mini'`, `temperature: 0.7`, `maxTokens: 2048` | ✅ 主流 + 平衡参数 |
| `video` | `kind: 'veo'`, `ratio: '16:9'`, `duration: 5`, `fps: 24` | ✅ Google Veo + 16:9 |
| `grok-oauth-agent` | `model: 'grok-2'`, `oauthToken: ''` | ⚠️ 需用户配 OAuth |
| `rh-config` | `baseUrl: 'https://www.runninghub.cn'`, `maxConcurrent: 3` | ⚠️ 硬编码 URL |
| `portrait-master` | `presetId: 'default'`, `viewId: 'front'`, `language: 'zh'` | ✅ 拖入即用 |
| `pose-master` | `presetId: 'standing'`, `viewId: 'front'`, `shotId: 'full-body'`, 12 字段全填 | ✅ 极完整 |
| `text-split` | `separator: '\n'`, `maxChunkSize: 2000` | ✅ 文本分段标准 |
| `seedance` | `mode: 'omni'`, `duration: 5`, `ratio: '16:9'` | ✅ 即梦模式 |

**47/49 节点 (有 defaults 的) 全部 PASS** ✅

**3 项次要问题 (⚠️)**:
1. **硬编码模型名易过时**: `'gpt-image-2'`, `'gpt-4o-mini'`, `'tts-1'`, `'grok-2'` 没有版本探测,上游 OpenAI/xAI 更新时不会自动适配
2. **rh-config.baseUrl 硬编码** `'https://www.runninghub.cn'` — RunningHub 改域名需改源码
3. **4 个节点无 status='idle'**: `placeholder`, `group-box`, `material-preview-section`, `material-thumbnail` 的 DEFAULTS 缺 `status` 字段,与 NodeRunStatus 契约不一致 (虽然这 4 个不是真实工作流节点,但若被 React Flow 渲染/拖入,运行态契约会破)

**Result: PASS 整体 (47/47) + 3 项次要问题** ⚠️

---

### 验收项 4: 49 节点都用 NodeDataShape&lt;T&gt; 强类型

**检查方法**: 读 49 个 _node.tsx 文件首两行,验证 import + 后续使用。

**证据 (49/49 文件首两行)**:
```ts
import type { NodeDataShape } from './types';
import { mergeDefaultData } from './defaults';
```

**49 个文件的 type key 唯一性**: ✅ (49 唯一 type key, 无重复)

**49 个文件 mergeDefaultData 调用**:
- `mergeDefaultData('<key>', (data as Partial<NodeDataShape<'<key>'>>) || undefined)` 模式 47/49
- `mergeDefaultData('model3d-preview' as never, (data as Partial<NodeDataShape<'model3d-preview'>>) || undefined) as any` 模式 1/49 (model3d-preview, R3.5-W1 加了 `as never` 兜底)
- `mergeDefaultData('panorama3d', (p.data as Partial<NodeDataShape<'panorama3d'>>) || undefined)` 模式 1/49 (panorama3d, **未加 `as never`** — R3.5-W1 漏修)

**Result: PASS** ✅

49/49 节点使用 NodeDataShape&lt;T&gt; 强类型 + 49/49 实际调用 mergeDefaultData。这是 R3.5-W1 的核心交付,确实完成。

---

### 验收项 5: IO CONTRACT MARKER 注释与实际代码一致

**检查方法 (Adversarial)**: 读 2 个问题文件的 IO CONTRACT MARKER 注释 (line 11-21),与实际代码对比。

**证据 (imdf_panorama3d_node.tsx + imdf_model3d_preview_node.tsx 的 marker)**:
```
/**
 * ─── R3-Worker-4 IO CONTRACT MARKER ────────────────────────────────
 * 类型 key : panorama3d / model3d-preview
 * 组件     : Panorama3dNode / Model3dPreviewNode
 * Data in  : NodeDataShape<'panorama3d'> (用户/上游配置 + 节点自身状态)
 * Data out : imageUrl/videoUrl/audioUrl/prompt/outputText 写回 data
 * 默认值   : mergeDefaultData('panorama3d', p.data) → defaults.ts   ← 撒谎
 * IO 文档   : NODE_IO_CONTRACTS → 类型 'panorama3d'                 ← 撒谎
 * onChange : useUpdateNodeData(id).update(patch) 浅合并到 data
 * ────────────────────────────────────────────────────────────────────
 */
```

**与实际代码对比**:

| Marker 声称 | 实际 |
|------------|------|
| `Data in: NodeDataShape<'panorama3d'>` | `NodeDataShape<'panorama3d'>` 解析为 `Record<string, unknown>` (fallback,因 panorama3d 不在 NodeDataMap) |
| `Data out: imageUrl/videoUrl/audioUrl/prompt/outputText` | 实际代码用 `panoramaGenerationMode`/`panoramaSourceUrl`/`panoramaPanelMode` 等 panorama 专属字段 |
| `默认值: mergeDefaultData('panorama3d', p.data) → defaults.ts` | `DEFAULTS['panorama3d']` 是 `undefined`,merge 返回 `{}` |
| `IO 文档: NODE_IO_CONTRACTS → 类型 'panorama3d'` | NODE_IO_CONTRACTS 数组里没有 'panorama3d' |

**Result: FAIL** ❌ — 2 个节点的 IO CONTRACT MARKER 都在"撒谎"。R3-W4 验证报告 §3.3 已经识别这是"marker 撒谎"问题,要求补 `*NodeData` 接口 + 3 处表登记。R3.5-W1 只补了 model3d-preview 的 `as never` cast,**没补 panorama3d 也没补 2 个节点的类型表登记**。

---

## 五、Adversarial Probes (对抗探针)

### 探针 1: panorama3d 的 TypeScript 类型检查

**方法**: 读 `D:\Hermes\生产平台\nanobot-factory\reports\r3_5_w3_tsc_nodes.log`,查 panorama3d 相关 tsc 错误。

**证据 (从 r3_5_w3_tsc_nodes.log 复制原文)**:
```
src/nodes/imdf_panorama3d_node.tsx(1069,30): error TS2345: 
  Argument of type '"panorama3d"' is not assignable to parameter of type 
  '"image" | "video" | "audio" | "text" | "seedance" | "idea" | "bp" | "combine" | 
  "resize" | "upscale" | "remove-bg" | "frame-extractor" | "frame-pair" | "grid-crop" | 
  "grid-editor" | ... 35 more ... | "audio-upload"'.

src/nodes/imdf_panorama3d_node.tsx(1072,55): error TS2339: 
  Property 'panoramaGenerationMode' does not exist on type 'IdeaNodeData | ...'

src/nodes/imdf_panorama3d_node.tsx(1073,39): error TS2339: 
  Property 'panoramaSourceUrl' does not exist on type ...

src/nodes/imdf_panorama3d_node.tsx(1076,7): error TS2339: 
  Property 'panoramaPanelMode' does not exist on type ...
```

**对比证据 (model3d-preview_node.tsx:196 vs panorama3d_node.tsx:1069)**:
```ts
// model3d-preview (line 196, 已加 as never 兜底):
const d = mergeDefaultData('model3d-preview' as never, 
  (data as Partial<NodeDataShape<'model3d-preview'>>) || undefined) as any;

// panorama3d (line 1069, 无 as never — R3.5-W1 漏修):
const d = mergeDefaultData('panorama3d', 
  (p.data as Partial<NodeDataShape<'panorama3d'>>) || undefined);
```

**Result: FAIL** ❌ — panorama3d 触发 **1 TS2345 + 14 TS2339** 错误。**R3.5-W1 报告和 R3.5-W3 报告均失实**, 声称"panorama3d 与 model3d-preview 同样用 `as never` 兜底"是错的。

---

### 探针 2: mergeDefaultData 浅合并行为

**方法**: 独立 ESM 脚本,验证嵌套对象 (如 `referenceImages: string[]`, `inputs: Record<string, unknown>`, `apps: Array<{...}>`) 在 user override 时是替换还是深合并。

**证据 (node 脚本输出)**:
```
=== Adversarial: nested object override (shallow merge check) ===
  referenceImages: ["a.png"]
  Note: defaults.referenceImages was [] but new value overwrites (shallow merge is correct here)
```

**Result: PASS 当前场景** ✅ (DEFAULTS 都是空容器) **+ 设计隐患** ⚠️

- 一级字段正确合并 (user override 优先,其余 defaults 保留) ✅
- 嵌套对象是**替换**, 不是深合并
- 当前 DEFAULTS 中所有 `inputs`/`referenceImages`/`apps`/`posePeople` 都是 `{}`/`[]`, 所以**短期内无实际损失**
- **隐患**: 后续添加预填资源时,user 加载 workflow 会**丢失** defaults 里的预填项

---

### 探针 3: panorama3d 触发 TS2345 错误是否被项目 tsc 捕获

**方法**: 读 tsconfig.json (`strict: false`, `exclude: ["src/nodes/**"]`),确认 panorama3d 的 TS2345 错误在项目级 tsc 中不会暴露。

**证据 (tsconfig.json 关键字段)**:
```json
"strict": false,
"exclude": [
  "node_modules",
  "dist",
  "src/nodes/**"
]
```

**Result: 设计上隔离** ✅ **+ 警示** ⚠️

`strict: false` + `src/nodes/**` exclude 双重作用,使 panorama3d 的 TS2345 错误在 `npm run type-check` 中不会暴露。R3.5-W3 报告里用临时 `tsconfig.nodes.json` 显式 include src/nodes 才捕获到该错误 (r3_5_w3_tsc_nodes.log:645)。**生产 CI 若只用项目 tsc,会漏掉 panorama3d 的 type contract 破裂**。

---

## 六、R3.5-W1 / R3.5-W3 报告的关键失实

| 报告 | 声称 | 实际 |
|------|------|------|
| R3.5-W1 §3.2 (line 103) | "panorama3d 与 model3d-preview 同样用 `as never` 兜底" | ❌ panorama3d 实际**未加** as never (line 1069 仍为 `mergeDefaultData('panorama3d', ...)`) |
| R3.5-W1 §3.2 (line 105) | "完整修复需后续 worker 补 *NodeData 接口 + 3 处表登记" | ❌ 补了 0/2 个 (R3.5-W1 没补,只补了 model3d-preview 的 cast) |
| R3.5-W1 §2.1 §5.1 | "ALL_NODE_TYPES 末尾追加 4 个 key: idea_shortcut, material-preview-section, material-thumbnail, audio-upload" | ✅ 已做,但**这 4 个 key 无任何 _node.tsx 消费** — 是死代码,无价值 |
| R3.5-W3 §3.1 (deliverable.md line 5) | "R3.5-W1 报告的'49/49 节点使用 mergeDefaultData'" | ✅ 但未验证 49 节点中 2 个的 DEFAULTS 实际可用性 — 49/49 调用是真的,49/49 defaults 存在是**假**的 (实际 47/49) |
| R3.5-W3 §3.1 (notes 3.1) | "model3d-preview / panorama3d 未在 NodeDataMap — 2 个 type key 缺失,代码用 as never 兜底" | ❌ 模型3d-preview 用了 as never,**panorama3d 没用** (且产生 1 TS2345 + 14 TS2339 错误) |

---

## 七、修复要求 (R3-W4+ worker 接手)

### 7.1 P0 (必修,阻塞)

1. **补 `Model3DPreviewNodeData` + `Panorama3dNodeData` 接口** 在 types.ts,定义 `panoramaGenerationMode`/`panoramaSourceUrl`/`panoramaPanelMode`/`panoramaSizeLevel`/`panoramaPrompt`/`panoramaViewerPosition`/`panoramaViewCenter`/`size: {w, h}` 等字段
2. **NodeDataMap 加 'model3d-preview' + 'panorama3d' 两条目** (types.ts:489-541)
3. **ALL_NODE_TYPES 加 'model3d-preview' + 'panorama3d' 两条目** (types.ts:544-560)
4. **DEFAULTS 加 model3d-preview + panorama3d 两条目** (defaults.ts:36-317),至少含 `status: 'idle'` + 关键字段空值
5. **NODE_IO_CONTRACTS 加 model3d-preview + panorama3d 两条目** (types.ts:606-1200),定义 inputs/outputs/configFields
6. **修 panorama3d 的 TS2345 错误** — 加 `as never` cast (临时兜底) 或引用新 Model3dPreviewNodeData / Panorama3dNodeData 接口

### 7.2 P1 (建议)

7. **删除 4 个未使用的派生类型**: `idea_shortcut`, `audio-upload`, `material-preview-section`, `material-thumbnail` (从 NodeDataMap / ALL_NODE_TYPES / DEFAULTS 全部移除)。如确有 roadmap,加注释说明
8. **4 个 display-only 节点补 `status: 'idle'`**: `placeholder`, `group-box`, `material-preview-section`, `material-thumbnail` 的 DEFAULTS 加 `status: 'idle'` 以符合 NodeRunStatus 契约
9. **修复 IO CONTRACT MARKER 撒谎** — 在 imdf_panorama3d_node.tsx + imdf_model3d_preview_node.tsx 的 marker 注释里,加 "⚠️ 类型 key 待补" 警告
10. **硬编码模型名加版本探测** — `'gpt-image-2'`, `'gpt-4o-mini'`, `'tts-1'`, `'grok-2'` 改成 `'gpt-image-2@2026-06'` 风格或从 provider 列表动态取最新

### 7.3 P2 (长期)

11. **考虑深合并** — `mergeDefaultData` 改成对 `Record<string, unknown>` 和 `unknown[]` 类型的字段做深合并 (lodash.merge 风格),避免嵌套资源丢失。当前 DEFAULTS 都是空容器,无影响,但 `referenceImages`/`inputs`/`apps`/`posePeople` 后续添加预填资源时会暴露
12. **tsconfig 移除 `exclude: ["src/nodes/**"]`** — 节点依赖 (SmartImage/LoopingVideo/MentionPromptInput 等) 落地后,移除 exclude 让项目 tsc 覆盖所有 49 节点
13. **`strict: true`** — 当前 `strict: false` 掩盖了大量类型不安全路径,后续 worker 应逐步打开

---

## 八、建议 (Recommendations)

### 8.1 决策建议: **manual_retry** (人工重试,任务级重试)

**理由**:

1. **修复范围明确可控**: 2 个节点的 5 处表登记 + 1 个 TS2345 修复,均不需重新设计架构,30-60 分钟可完成
2. **可机械操作**: 模板与 R3.5-W1 已成功的 30 节点补全一致
3. **修复路径已文档化**: 详见 §7.1 P0 列表

**不选 reject 的理由**: R3.5-W1 的 30 节点补全是 100% PASS 的,仅 2 个特殊节点 (model3d-preview/panorama3d) 漏修,reject 会浪费 R3.5-W1 的全部成果

**不选 owner_override 的理由**: 这是常规 worker 任务级重试可解决的问题,不需要 owner 介入决策

### 8.2 详细修复步骤 (给 worker)

```bash
# 1. 在 types.ts 添加缺失接口 (在 AudioUploadNodeData 后面)
export interface Model3DPreviewNodeData extends NodeRunStatus {
  size?: { w: number; h: number };
  // ... 其他 model3d-preview 实际使用的字段
}
export interface Panorama3dNodeData extends NodeRunStatus {
  panoramaGenerationMode?: 'preview' | 'text';
  panoramaSourceUrl?: string;
  panoramaPanelMode?: 'preview' | 'text';
  // ... 其他 panorama 实际使用的字段
}

# 2. NodeDataMap / ALL_NODE_TYPES / DEFAULTS / NODE_IO_CONTRACTS 4 表全数登记这 2 个 key

# 3. panorama3d_node.tsx:1069 加 as never (临时兜底) 或等接口补完
const d = mergeDefaultData('panorama3d' as never, ...) as any;
```

### 8.3 验证清单 (修复后必须跑)

```bash
cd "D:\Hermes\生产平台\nanobot-factory\backend\imdf\frontend"
# 1. 4 张表都含 49 个真实节点 + 4 个辅助 type (或删 4 辅助 type 后 49 个)
# 2. panorama3d 0 TS2345 错误
npx tsc --noEmit --project tsconfig.nodes.json 2>&1 | Select-String "panorama3d"
# 期望: 0 匹配
# 3. mergeDefaultData 49/49 返回非空对象
node -e "..."  # 跑 Check 5 同等测试
# 4. NODE_IO_CONTRACTS 含 49 entries (不再是 47)
```

---

## 九、最终评分

| 验收项 | 评分 | 状态 |
|--------|------|------|
| 1. 49 节点全部在 4 张表登记 | 47/49 = 95.9% | ❌ FAIL |
| 2. mergeDefaultData 真合并 (47/49 + 2 ghost) | 47/49 = 95.9% | ❌ FAIL |
| 3. defaults.ts 默认值用户友好 | 47/47 = 100% (有 defaults 的节点) | ✅ PASS (3 项次要问题) |
| 4. 49 节点用 NodeDataShape&lt;T&gt; 强类型 | 49/49 = 100% | ✅ PASS |
| 5. IO CONTRACT MARKER 与代码一致 | 47/49 = 95.9% | ❌ FAIL |
| 6. 跨表一致性 (4 表互通) | 0 个 ghost + 0 个 dead | ❌ FAIL |
| **总分** | **4/6 维度 FAIL** | **FAIL** |

**Auditor-A 终判**: R3.5 修复后前端节点契约业务正确性 **FAIL**。47/49 节点契约完整、merge 工厂正确工作、默认值用户友好,但 **2 个节点 (model3d-preview + panorama3d) 契约破裂** — 缺类型、缺 defaults、缺 IO 契约、缺类型安全 cast,panorama3d 还有 15 个 TypeScript 编译错误。

**决策建议**: **manual_retry** (任务级重试),由 R3.5-W4+ worker 按 §7.1 P0 列表机械修复。

---

## 十、附录

### 10.1 完整证据 (供后续 verifier 复现)

```powershell
# 1. 49 _node.tsx 提取 type key
$nodeDir = "D:\Hermes\生产平台\nanobot-factory\backend\imdf\frontend\src\nodes"
$keys = @()
foreach ($f in Get-ChildItem -LiteralPath $nodeDir -File -Filter "*_node.tsx") {
  $content = Get-Content -LiteralPath $f.FullName -Raw
  if ($content -match "mergeDefaultData\(['""]([^'""]+)['""]") { $keys += $matches[1] }
}
$keys | Sort-Object -Unique | Measure-Object

# 2. 4 张表 key 数量对比
$types = Get-Content "$nodeDir\types.ts" -Raw
$defaults = Get-Content "$nodeDir\defaults.ts" -Raw
# NodeDataMap 51 / ALL_NODE_TYPES 51 / DEFAULTS 51 / NODE_IO_CONTRACTS 47

# 3. mergeDefaultData 行为测试 (写到 $env:TEMP/audit.mjs)
# 4. tsc 反查 panorama3d 错误
Select-String -Path "D:\Hermes\生产平台\nanobot-factory\reports\r3_5_w3_tsc_nodes.log" -Pattern "panorama3d" -SimpleMatch
```

### 10.2 工具栈

- 静态分析: PowerShell + regex (brace-depth tracking for nested objects)
- 独立 ESM 脚本 (写到 $env:TEMP) 模拟 mergeDefaultData 行为
- 复用 R3.5-W3 报告 `r3_5_w3_tsc_nodes.log` 反查 tsc 错误
- 复用 R3-W4 报告 `r3_w4_verify.md` 对比历史失败项
- 复用 R3.5-W1 报告 `r3_5_w1.md` + R3.5-W2 报告 `r3_5_w2.md` + R3.5-W3 报告 `r3_5_w3.md` 对比声称

### 10.3 不修改任何项目文件

本审计仅做验证,未修改 types.ts / defaults.ts / 任何 _node.tsx。所有测试在 $env:TEMP 跑,未污染 git tree。

---

**报告结束**
