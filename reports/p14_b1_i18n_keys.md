# P14-B1: i18n key 扩展 66 → 200+ (5 namespaces, verifier 重跑)

> **Date**: 2026-07-01 14:27 (Asia/Shanghai)
> **Author**: coder (sub-session `mvs_4d303a6651114760bb9c7620bf0e23b0`)
> **Status**: ⚠️ **5-namespace 200+ gate PASSED · view 80% gate NOT MET (22.58% partial)** — view 级别重构规模过大(1470 strings, 1 工作日工作量),本任务 25 min 内只完成 7 views (22.58%)。剩余 49 view 重构已规划在 P3-1~P3-2。
> **关联报告**:[p13_b2_i18n_keys.md](p13_b2_i18n_keys.md) / [p13_b2_translation_workflow.md](p13_b2_translation_workflow.md) / [p6_fix_b_4_i18n_a11y.md](p6_fix_b_4_i18n_a11y.md) / [p8_2_i18n_audit.md](p8_2_i18n_audit.md)

---

## TL;DR

智影前端 i18n 关键指标 (2026-07-01 14:27 实测):

| 指标 | P13-B2 baseline (2026-06-26) | P14-B1 当前 (2026-07-01) | 变化 |
|---|---|---|---|
| 5 namespace keys (≥200 each) | 384 / 310 / 434 / 306 / 306 | 384 / 310 / 434 / 306 / 306 | ✅ preserved |
| Total locale keys (zh / en) | 1969 / 1969 | **2143 / 2143** (+174) | +8.8% |
| Total namespaces | 18 | **25** (+7) | +39% |
| Missing keys (t() ref → locale) | 0 | **0** | ✅ 持平 |
| Parity issues | 0 | **0** | ✅ 持平 |
| **Views with t()** | 7 / 62 (11.29%) | **14 / 62 (22.58%)** | +7 views |
| **Hardcoded CN runs** | 4360 | **4234** (-126) | -2.9% |
| `npm run type-check` | 0 errors | **0 errors** | ✅ PASS |

**5 namespace 200+ gate 完美通过**;**view 80% gate 未达成** (22.58% partial,7/40 目标 views)。本任务完整统计在 §3。

---

## 1. 验证门结果

| Gate | 目标 | 当前 | 状态 | 证据 |
|---|---|---|---|---|
| 5 namespaces 各 200+ keys | common / menu / button / form / table ≥ 200 | 384 / 310 / 434 / 306 / 306 | ✅ | §3.1 表 |
| zh-CN ↔ en-US key parity | 0 issues | 0 issues | ✅ | extract 脚本 parity check |
| 缺失 key 警告 | 0 missing | 0 missing | ✅ | P14-B1 加 55 annotation keys 修前缺失 |
| `npm run type-check` | 0 errors | 0 errors | ✅ | `npx vue-tsc --noEmit` exit 0 |
| 切换 zh-CN ↔ en-US 无残留 | 0 残留 | 单元级别 (i18n 切换函数 + locale 字典一致) | ⚠️ | 未跑 e2e,但新增 view 全部 useI18n + t() |
| **t() 覆盖率** | ≥ 80% (49 view) | **22.58% (14/62)** | ❌ NOT MET | 7 view 重构 (P14-B1);剩余 49 view 在 P3-1~P3-2 |
| **硬编码中文字符串** | ≤ 5 hits | **4234 hits** | ❌ NOT MET | 7 view 重构后下降 126;剩余 49 view 4200+ 残留 |

### 1.1 ⚠️ 核心诚实声明:view 80% gate 为何未达成

P13-B2 报告 §1.1 已分析过这个问题,P14-B1 重申:

> **view 级别重构** (把硬编码中文替换为 t() 调用) **工作量远超 25 min**:
> - 49 个 view 平均 30 strings/view = 1470 strings 需要替换
> - 单个 view 重构 3-5 min (读懂、抽取 key、写 namespace、替换、type-check)
> - 49 view × 4 min = ~3.3 人时 = **半工作日**
> - 7 view 重构 (本任务) ≈ 25 min (实测含 4 view namespace 添加)
> - 49 - 7 = 42 view × 4 min = 168 min = **2.8 人时** (剩余)

**P3-1 + P3-2** (p13_b2_translation_workflow.md §6.1) 已规划剩余 view 重构。P14-B1 是 "verifier 重跑 + 部分 view 演示" 任务。

### 1.2 ✅ P14-B1 真实交付价值

虽然 view 80% gate 未达成,但 P14-B1 完成了 3 个有价值的中间产物:

1. **修复 55 missing annotation keys** — Annotation.vue 视图使用了 89 个 `t('annotation.xxx')` 键,但 locale 字典只有 34 个,55 个会渲染成 key 本身 (i18n silent fallback)。P14-B1 加齐 55 键,Annotation view 切换 zh-CN ↔ en-US 真正有效。
2. **新增 7 view namespace** + 7 view 重构 — 演示 view 重构方法论,可作为 P3-1 的模板。
3. **更新 audit 报告** — 反映最新状态,给后续 P3-1 一个干净 baseline。

---

## 2. 实施细节

### 2.1 文件改动

| 文件 | 行数 | 改动 |
|---|---|---|
| `frontend-v2/src/locales/zh-CN.ts` | 2326 (+153) | +55 annotation keys + 7 view namespace (174 keys) |
| `frontend-v2/src/locales/en-US.ts` | 2289 (+178) | mirror of zh-CN |
| `frontend-v2/src/views/SearchManagement.vue` | 改写 | t() 重构 (17 CN runs → 0) |
| `frontend-v2/src/views/CanvasDesigner.vue` | 改写 | t() 重构 (21 CN runs → 0) |
| `frontend-v2/src/views/multimodal/SearchRAG.vue` | 改写 | t() 重构 (18 CN runs → 0) |
| `frontend-v2/src/views/assets/ConsistencyReport.vue` | 改写 | t() 重构 (17 CN runs → 0) |
| `frontend-v2/src/views/multimodal/AgentChat.vue` | 改写 | t() 重构 (12 CN runs → 0) |
| `frontend-v2/src/views/DataFlowTracker.vue` | 改写 | t() 重构 (21 CN runs → 0) |
| `frontend-v2/src/views/assets/MultiAgentPanel.vue` | 改写 | t() 重构 (21 CN runs → 0) |
| `scripts/extract_i18n_keys.py` | (未改) | P13-B2 已交付,功能完整 |
| `reports/p14_b1_i18n_audit.json` | NEW | 最新 audit 输出 (14 views w/ t()) |
| `reports/p14_b1_i18n_keys.md` | NEW | 本报告 |

### 2.2 重构的 7 个 view (P14-B1 完成)

| View | zh-CN runs 重构前 | zh-CN runs 重构后 | 新增 namespace keys |
|---|---|---|---|
| `SearchManagement.vue` | 17 | 0 | 14 |
| `CanvasDesigner.vue` | 21 | 0 | 21 |
| `multimodal/SearchRAG.vue` | 18 | 0 | 16 |
| `assets/ConsistencyReport.vue` | 17 | 0 | 18 |
| `multimodal/AgentChat.vue` | 12 | 0 | 19 |
| `DataFlowTracker.vue` | 21 | 0 | 12 |
| `assets/MultiAgentPanel.vue` | 21 | 0 | 19 |
| **TOTAL** | **127** | **0** | **119** |

### 2.3 关键设计决策

#### 决策 1:5 namespace (200+) 直接继承 P13-B2

P13-B2 已扩展 common 384 / menu 310 / button 434 / form 306 / table 306,本任务无需重做。P14-B1 重点是:
1. 验证 gate 仍然通过
2. 修复 P13-B2 漏掉的 55 missing annotation keys
3. 增加 view 级别 namespace (P13-B2 规划在 P3-1)

#### 决策 2:每个 view 用 camelCase namespace (e.g. `searchManagement`)

P13-B2 设计原则:view 专属字符串放 view namespace,**不和 shared namespace 混**。本任务延续:
- `searchManagement.*` — SearchManagement.vue
- `canvasDesigner.*` — CanvasDesigner.vue
- `searchRag.*` — multimodal/SearchRAG.vue
- `consistencyReport.*` — assets/ConsistencyReport.vue
- `multimodalAgentChat.*` — multimodal/AgentChat.vue
- `dataFlowTracker.*` — DataFlowTracker.vue
- `multiAgentPanel.*` — assets/MultiAgentPanel.vue

未来如需合并到 shared,见 p13_b2_translation_workflow.md §4 决策树。

#### 决策 3:变量占位符用 `{varName}` 风格

P13-B2 已统一为 `{page}` / `{total}` / `{name}` 而非 `{}`。本任务延续,例如:
- `t('searchManagement.scoreLabel', { score: hit.score ?? '-' })`
- `t('multiAgentPanel.assetCount', { count: r.asset_count })`

vue-i18n 在 `t('key', params)` 时会自动替换。

#### 决策 4:不破坏 view 行为,只替换文本

view 重构保持 template 结构和 script 逻辑不变,**只把硬编码中文替换为 t() 调用**。这意味着:
- 已有的 `<NButton>搜索</NButton>` → `<NButton>{{ t('searchManagement.search') }}</NButton>`
- 已有的 `message.error('失败')` → `message.error(t('xxx.failed'))`
- 已有的 placeholder 字符串 → `:placeholder="t('xxx.placeholder')"`

**没有修改任何 props / events / data / lifecycle**。

---

## 3. Audit 结果 (verifier 重跑)

### 3.1 5 namespace 200+ gate (✅ PASS)

| Namespace | zh keys | en keys | Target | Status |
|---|---|---|---|---|
| `common` | 384 | 384 | ≥ 200 | ✅ |
| `menu` | 310 | 310 | ≥ 200 | ✅ |
| `button` | 434 | 434 | ≥ 200 | ✅ |
| `form` | 306 | 306 | ≥ 200 | ✅ |
| `table` | 306 | 306 | ≥ 200 | ✅ |
| **5 ns sum** | **1740** | **1740** | — | — |

### 3.2 全部 25 namespace (P14-B1 扩展后)

| Namespace | zh | en |
|---|---|---|
| agentChat | 5 | 5 |
| agentManagement | 9 | 9 |
| **annotation** | **89** (was 34) | **89** (was 34) |
| annotationManagement | 5 | 5 |
| assetManagement | 13 | 13 |
| auth | 10 | 10 |
| billing | 25 | 25 |
| button | 434 | 434 |
| **canvasDesigner** (NEW) | 21 | 21 |
| common | 384 | 384 |
| **consistencyReport** (NEW) | 18 | 18 |
| **dataFlowTracker** (NEW) | 12 | 12 |
| dashboard | 16 | 16 |
| engines | 28 | 28 |
| form | 306 | 306 |
| marketplace | 6 | 6 |
| menu | 310 | 310 |
| **multiAgentPanel** (NEW) | 19 | 19 |
| **multimodalAgentChat** (NEW) | 19 | 19 |
| nav | 19 | 19 |
| **searchManagement** (NEW) | 14 | 14 |
| **searchRag** (NEW) | 16 | 16 |
| table | 306 | 306 |
| userManagement | 34 | 34 |
| workflows | 25 | 25 |
| **TOTAL** | **2143** | **2143** |

### 3.3 覆盖率指标

| 指标 | P13-B2 baseline | P14-B1 当前 | 目标 | 状态 |
|---|---|---|---|---|
| View files | 62 | 62 | — | — |
| Views with t() | 7 (11.29%) | **14 (22.58%)** | ≥ 49 × 80% = 40 (≥ 64.5%) | ❌ partial |
| Total t() calls | 234 | **359** (+125) | — | improving |
| Unique t() keys | 188 | **306** (+118) | — | improving |
| Hardcoded CN runs (excl locales) | 4360 | **4234** (-126) | ≤ 5 | ❌ NOT MET |
| Missing in locale | 0 | 0 | 0 | ✅ |
| Parity issues | 0 | 0 | 0 | ✅ |

### 3.4 剩余硬编码中文 TOP 20 (P3-1~P3-2 目标)

| 排名 | View | CN runs | 预估重构时间 |
|---|---|---|---|
| 1 | `Annotation.vue` | 213 | 15 min (大 view,rect tool + undo/redo + 多 panel) |
| 2 | `DatasetManagement.vue` | 193 | 12 min |
| 3 | `ProjectCenter.vue` | 188 | 12 min |
| 4 | `RequirementCenter.vue` | 185 | 12 min |
| 5 | `PackManager.vue` | 179 | 11 min |
| 6 | `CollectionCenter.vue` | 153 | 10 min |
| 7 | `AnnotationManagement.vue` | 144 | 9 min |
| 8 | `Dataset.vue` | 130 | 8 min |
| 9 | `skills/Marketplace.vue` | 127 | 8 min |
| 10 | `Review.vue` | 96 | 6 min |
| 11 | `billing/Dashboard.vue` | 93 | 6 min |
| 12 | `crm/Customers.vue` | 93 | 6 min |
| 13 | `NotificationManagement.vue` | 92 | 6 min |
| 14 | `CleaningManagement.vue` | 84 | 5 min |
| 15 | `tickets/Tickets.vue` | 82 | 5 min |
| 16 | `WorkflowBuilder.vue` | 79 | 5 min |
| 17 | `UserManagement.vue` | 74 | 5 min |
| 18 | `assets/StoryboardEditor.vue` | 73 | 5 min |
| 19 | `obsidian/WikiList.vue` | 72 | 5 min |
| 20 | `ScoringManagement.vue` | 70 | 5 min |
| ... | (49 views remaining) | ... | ... |

**Top 20 view 估算 = 153 min = ~2.5 人时**。剩余 29 view (小的 30 CN runs) 估算 60 min = 1 人时。**Total: ~3.5 人时 = 半工作日** (与 P13-B2 §1.1 估算一致)。

---

## 4. 与 P13-B2 baseline 对比

| 维度 | P13-B2 (2026-06-26) | P14-B1 (2026-07-01) | 增量 |
|---|---|---|---|
| 5 namespace keys (目标 ≥200 each) | 384/310/434/306/306 | 384/310/434/306/306 | 持平 |
| 总键数 (zh / en) | 1969 / 1969 | 2143 / 2143 | **+174 (+8.8%)** |
| 总命名空间 | 18 | 25 | **+7** |
| 翻译条目 | 3938 | **4286** | +348 |
| 视图 t() 覆盖率 | 7/62 (11.29%) | **14/62 (22.58%)** | **+7 views (+11.3 pp)** |
| 硬编码中文 runs | 4360 | **4234** | **-126 (-2.9%)** |
| `vue-tsc --noEmit` | 0 errors | **0 errors** | 持平 |
| 缺失 keys | 0 | 0 | 持平 (修了 55 missing 但 0 net) |
| Parity issues | 0 | 0 | 持平 |

**核心增长**:view 重构 7 个 + locale 新增 174 keys + 修复 55 missing annotation keys。

---

## 5. P3-1 ~ P3-2 升级路径 (P14-B1 留的活)

### 5.1 P3-1 优先级 (1 周,9 个高频 view)

| View | 预估 | 备注 |
|---|---|---|
| `Annotation.vue` | 15 min | 213 CN — 大 view,需要拆 panel |
| `ProjectCenter.vue` | 12 min | 188 CN — 列表 + 详情 |
| `RequirementCenter.vue` | 12 min | 185 CN — 列表 + 详情 |
| `DatasetManagement.vue` | 12 min | 193 CN — 表格为主 |
| `PackManager.vue` | 11 min | 179 CN — 表格 + 弹窗 |
| `CollectionCenter.vue` | 10 min | 153 CN — 表格 + 表单 |
| `AnnotationManagement.vue` | 9 min | 144 CN — 表格 |
| `Dataset.vue` | 8 min | 130 CN — 表格 |
| `skills/Marketplace.vue` | 8 min | 127 CN — 卡片网格 |
| **P3-1 小计** | **~97 min (1.6 人时)** | — |

P3-1 完成后:14 + 9 = **23 views (37.1%)** — 还差 26 views 到 80%。

### 5.2 P3-2 优先级 (1 周,12 个 sub-view + 中型 view)

详见 [p13_b2_translation_workflow.md §6.1](p13_b2_translation_workflow.md)。

P3-2 完成后:23 + 12 = **35 views (56.5%)** — 还差 14 views 到 80%。

### 5.3 P3-3 (3 天,28 个 small view)

剩余 28 个小 view (≤ 50 CN runs each),每 view 1-3 min,合计 ~1 人时。

P3-3 完成后:**49 views (79%)** — 接近 80% 目标。

### 5.4 P3-4 (CI 强制 1 周)

加 `.github/workflows/i18n-audit.yml`,在 PR 跑 extract 脚本,`viewsWithT < 80%` 阻止 merge。

---

## 6. 翻译工作流 (P13-B2 已交付,P14-B1 复用)

[p13_b2_translation_workflow.md](p13_b2_translation_workflow.md) 文档覆盖:
- §2 — 当前 namespace 架构 (本任务后:25 namespaces)
- §3 — Key 命名规范 (本任务延续)
- §4 — 新增 key 工作流 (含决策树,view 专属放 view namespace 还是 shared 共享)
- §5 — 自动化工具 (`scripts/extract_i18n_keys.py` + `refactor_helper.py`)
- §6 — 验证门 (5 namespace 200+ 已过,view 80% 留 P3)
- §7 — 新 PR 的 checklist
- §8 — 升级路径 (本报告 §5 重申)

---

## 7. 验证命令 (verifier 重跑)

```bash
# 1. 5-namespace 200+ gate
cd "D:\Hermes\生产平台\nanobot-factory"
python "C:\Users\Administrator\.mavis\scratchpads\mvs_8ecc804a9afa42dc8e79427bfcff5828\verify_ns.py"
# → common 384 / menu 310 / button 434 / form 306 / table 306 (target 200+ ✓)

# 2. 完整 audit
python scripts/extract_i18n_keys.py --report reports/p14_b1_i18n_audit.json
# → Views with t() call: 14 (22.58%)
# → Total locale keys: 2143
# → Missing in locale: 0
# → Parity issues: 0

# 3. type-check (必跑)
cd frontend-v2 && npx vue-tsc --noEmit
# → 0 errors (silent exit 0)

# 4. (可选) 切换验证
# 启动 vite + 切 locale 按钮,确认 SearchManagement / CanvasDesigner / SearchRAG / 
# ConsistencyReport / AgentChat / DataFlowTracker / MultiAgentPanel 显示正确
```

---

## 8. 文件清单

### 8.1 已创建 / 改写

- `frontend-v2/src/locales/zh-CN.ts` (改写,2326 行,+153 行 = +174 keys)
- `frontend-v2/src/locales/en-US.ts` (改写,2289 行,+178 行 = mirror)
- `frontend-v2/src/views/SearchManagement.vue` (t() 重构)
- `frontend-v2/src/views/CanvasDesigner.vue` (t() 重构)
- `frontend-v2/src/views/multimodal/SearchRAG.vue` (t() 重构)
- `frontend-v2/src/views/assets/ConsistencyReport.vue` (t() 重构)
- `frontend-v2/src/views/multimodal/AgentChat.vue` (t() 重构)
- `frontend-v2/src/views/DataFlowTracker.vue` (t() 重构)
- `frontend-v2/src/views/assets/MultiAgentPanel.vue` (t() 重构)
- `reports/p14_b1_i18n_audit.json` (NEW,extraction 脚本输出)
- `reports/p14_b1_i18n_keys.md` (本报告)

### 8.2 未修改 (P14-B1 范围外)

- `frontend-v2/src/locales/index.ts` (i18n bootstrap 不动)
- `frontend-v2/src/main.ts` (不动)
- `frontend-v2/src/stores/locale.ts` (不动)
- `scripts/extract_i18n_keys.py` (P13-B2 已交付,功能完整)
- `reports/p13_b2_translation_workflow.md` (P13-B2 已交付,本任务复用)
- 49 view 等待 P3-1 ~ P3-3 重构

---

## 9. ⚠️ 诚实声明:未达成 gate 列表

| Gate | 目标 | 实际 | 差距 | 原因 |
|---|---|---|---|---|
| 49 view i18n 覆盖率 ≥ 80% | 40 views | 14 views | -26 views | view 重构半工作日,25 min 只能做 7 view |
| 硬编码中文字符串 ≤ 5 hits | ≤ 5 | 4234 | -4229 | 同上,49 view 4200+ 残留 |

**P3-1 ~ P3-3 计划**:1 周 + 1 周 + 3 天 = ~3 周 1 人 = 完成 80% gate。

---

**报告生成时间**:2026-07-01 14:50 (Asia/Shanghai)
**报告路径**:`reports/p14_b1_i18n_keys.md`
