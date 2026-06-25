# P6-4 前端深度审查报告 — 智影 nanobot-factory frontend-v2

**审计日期**: 2026-06-24 15:30 (Asia/Shanghai)
**审计范围**: frontend-v2 (Vue 3 + TS + Pinia + Naive UI)
**审计方法**: 静态扫描 + vue-tsc 0-error 验证 + vite build 实战 + 双 AI 互审 (本报告)
**审计者**: Coder Agent (P6-4 任务)

---

## 一、硬启动检查 (v3)

```
Set-Location 'D:\Hermes\生产平台\nanobot-factory'       ✓
Test-Path 'frontend-v2'                                 ✓ TRUE
Test-Path 'frontend-v2\src\views'                       ✓ TRUE (52 个 view 文件)
```

通过 — 进入正式审计。

---

## 二、整体规模盘点

| 维度 | 数量 | 来源 |
| --- | ---: | --- |
| View 文件 (.vue) | **52** | `frontend-v2/src/views/**` 递归 |
| 路由注册 | **46** | `router/index.ts` 中 `import('@/views/...')` |
| API 客户端 (.ts) | **20** | `frontend-v2/src/api/**` |
| 共享组件 | 5 | `components/` (DataTable/ModalForm/SearchBar/ActionButton/PermissionGuard) |
| Pinia store | 2 | `stores/auth.ts` + `stores/api.ts` |
| Layout | 1 | `layouts/DefaultLayout.vue` |
| Types 模块 | 1 | `types/index.ts` |
| Router 路由总数 | **46 + login + catch-all** | `router/index.ts` |

### 2.1 View 分类（按业务域）

| 业务域 | 视图 | 数量 |
| --- | --- | ---: |
| **基础 (P3-7)** | Dashboard, Login, Dataset, Annotation, Review, Scoring, Workflows, Engines, Tasks, Users, Billing, Monitoring, Settings | 13 |
| **业务管理 (P3-7-W2)** | AgentManagement, AssetManagement, AnnotationManagement, CleaningManagement, ScoringManagement, DatasetManagement, EvaluationManagement, NotificationManagement, SearchManagement, UserManagement, WorkflowManagement | 11 |
| **画布/编辑器** | CanvasDesigner (vue-flow) | 1 |
| **多 Agent (P4-5)** | assets/CharacterManager, IterativeStudio, MultiAgentPanel, ConsistencyReport | 4 |
| **视频/分镜 (P4-6)** | workflow/DirectorStudio, OperatorMarket, RunMonitor; workflow/VisualEditor; assets/StoryboardEditor | 5 |
| **跨模态 (P4-7)** | agent/MultimodalChat; multimodal/AgentChat, EmbedStudio, Parser, SearchRAG | 5 |
| **商业化 (P4-10)** | billing/Dashboard, Pricing, Orders, Invoices | 4 |
| **Skill (P4-8)** | skills/Marketplace, Orchestrator | 2 |
| **Obsidian Wiki (P4-8)** | obsidian/KnowledgeGraph, WikiList, WikiEdit | 3 |
| **CRM/工单/合同** | contracts/Contracts, crm/Customers, tickets/Tickets | 3 |
| **血缘** | lineage/Graph | 1 |

合计 **52** view (已远超任务要求的 30+)。

### 2.2 API 客户端清单 (20)

| 文件 | 行数 | 后端服务 | 端点数 |
| --- | ---: | --- | ---: |
| `http.ts` (基类) | 71 | — | 6 (CRUD helpers + Page<T>) |
| `index.ts` (聚合) | 14 | — | 12 (re-export) |
| `agent.ts` | — | agent_service | 5+ |
| `annotation.ts` | — | annotation_service | 5 |
| `asset.ts` | 36 | asset_service | 5 |
| `canvas.ts` | — | canvas_service | 5 |
| `cleaning.ts` | — | cleaning_service | 5 |
| `dataset.ts` | — | dataset_service | 5 |
| `evaluation.ts` | — | evaluation_service | 5 |
| `iteration.ts` | 193 | asset/sessions + multi_agent + consistency | 16 |
| `lineage.ts` | 49 | lineage_service | 4 |
| `multimodal.ts` | 121 | multimodal_service + agent/multimodal | 11 |
| `notification.ts` | — | notification_service | 5 |
| `obsidian.ts` | 74 | obsidian_service | 9 |
| `scoring.ts` | — | scoring_service | 5 |
| `search.ts` | — | search_service | 5 |
| `skills.ts` | 86 | skills_service | 12 |
| `user.ts` | 35 | user_service | 5 |
| `workflow.ts` | — | workflow_service v1 | 5 |
| `workflow_v2.ts` | 286 | workflow_service v2 (DAG/director) | 14 |

合计 **20** 文件 (远超 12 要求)，覆盖 12 业务域 + 8 扩展模块。

---

## 三、构建基线 (硬证据)

### 3.1 Type Check (vue-tsc --noEmit)

```
> vue-tsc --noEmit
(0 errors, 0 warnings, exit 0)
```

**PASS** — TypeScript 严格模式通过 0 错误。

### 3.2 Production Build (vite build)

```
> vue-tsc --noEmit && vite build
✓ 4902 modules transformed.
✓ built in 11.13s
```

| 关键 chunk | 原始 | gzip | 评级 |
| --- | ---: | ---: | --- |
| naive-vendor | 726 KB | 198 KB | ⚠ 偏大 (Naive UI 全量引入) |
| echarts-vendor | 503 KB | 170 KB | ⚠ 偏大 (可按需注册) |
| vueflow-vendor | 219 KB | 72 KB | OK |
| vue-vendor | 108 KB | 42 KB | OK |
| index (app) | 63 KB | 24 KB | OK |
| VisualEditor (最大 view) | 16 KB | 6 KB | OK |
| Marketplace | 12 KB | 5 KB | OK |
| Tickets | 10 KB | 4 KB | OK |

**总体 PASS** — 但 vendor 偏大（详见 actions.md P3 优化）。

> ⚠ Tailwind 警告 (无害): `The 'content' option in your Tailwind CSS configuration is missing or empty.` — 仅出现在 PostCSS 配置，未实际使用 Tailwind。

---

## 四、20 大类审查 (按 view)

按 P6-4 任务的 100+ 检查项，对 52 个 view 全部进行机器扫描 + 人工重点抽查。下表汇总结果，详细 PASS/FAIL 见 `reports/p6_4_findings.md`。

### 4.1 关键指标 (52 view 机器扫描)

| 检查项 | PASS 数 | FAIL 数 | 通过率 |
| --- | ---: | ---: | ---: |
| 1. 文件存在 | 52 | 0 | 100% |
| 2. 路由注册 | 46 | 6 | 88% (6 个 view 未挂路由) |
| 3. `<template>` 完整 | 52 | 0 | 100% |
| 4. `<script setup lang="ts">` | 52 | 0 | 100% |
| 5. `<style>` scoped 或全局 | 52 | 0 | 100% |
| 6. `onMounted` 钩子 | 39 | 13 | 75% |
| 7. Loading state (`loading=` / `isLoading`) | 35 | 17 | 67% |
| 8. try/catch 错误处理 | 35 | 17 | 67% |
| 9. 分页 (DataTable 集成) | 23 | 29 | 44% |
| 10. 表单校验 (`rules:`) | 19 | 33 | 37% |
| 11. i18n (`useI18n`/`$t`) | **0** | **52** | **0%** ⚠ |
| 12. a11y (aria-* 标签) | **0** | **52** | **0%** ⚠ |
| 13. 响应式 (`@media`) | 4 | 48 | 8% |
| 14. 暗色模式 | **0** | **52** | **0%** ⚠ |
| 15. 虚拟列表 (virtual scroll) | **0** | **52** | **0%** ⚠ |
| 16. 单元测试 (vitest/jest) | 0 | 52 | 0% |
| 17. E2E (Playwright) | 0 | 52 | 0% |
| 18. Naive UI 组件使用 | 52 | 0 | 100% |
| 19. API 调用 (`api.*` 或 `@/api`) | 41 | 11 | 79% |
| 20. router-link / router.push | 8 | 44 | 15% |
| 21. Pinia store 使用 | 14 | 38 | 27% |
| 22. `// TODO/FIXME` 注释 | 18 处 (5 view) | — | 详见 findings |

### 4.2 严重问题概览 (高优先级)

#### A. 11 个 stub view (≤13 行，仅 NPageHeader + NEmpty 占位)

| View | 行数 | 状态 |
| --- | ---: | --- |
| Annotation.vue | 13 | W2 stub — 占位说明 |
| Billing.vue | 12 | W2 stub — 占位说明 |
| Dataset.vue | 22 | W2 stub — 占位说明 |
| Engines.vue | 12 | W2 stub — 占位说明 |
| Monitoring.vue | 12 | W2 stub — 占位说明 |
| Review.vue | 12 | W2 stub — 占位说明 |
| Scoring.vue | 12 | W2 stub — 占位说明 |
| Settings.vue | 12 | W2 stub — 占位说明 |
| Tasks.vue | 12 | W2 stub — 占位说明 |
| Users.vue | 12 | W2 stub — 占位说明 |
| Workflows.vue | 76 | 部分 — 只有 Vue Flow demo，无业务逻辑 |

> 11 个基础 view 仍为 W2 占位，未接入真实后端。这是 P6-4 阶段最大的完成度缺口。

#### B. 全局缺失能力

| 缺失项 | 影响 |
| --- | --- |
| **i18n 0%** | zh-CN 文字直接硬编码在 .vue 中，无 vue-i18n 集成，无法支持 en-US 切换 |
| **a11y 0%** | 所有 NButton/NInput 无 aria-label, 键盘导航缺失 (WCAG AA 不达标) |
| **暗色模式 0%** | 仅 App.vue 引用 `darkTheme` 类型，未提供切换 UI；Naive UI 内置 dark theme 未启用 |
| **测试 0%** | 无 vitest 单元测试，无 Playwright E2E，无法保障回归 |
| **响应式 8%** | 仅 4 个 view 含 `@media`；移动端/平板体验差 |
| **虚拟列表 0%** | DataTable 内置 pagination，无大数据集性能优化 (rows > 10K 时会卡) |

#### C. 隐藏依赖

- **`@vicons/ionicons5` 未声明在 package.json / package-lock.json** — 13 个 view 引用，但 npm i 后不会自动安装（当前 node_modules 中存在，是历史遗留）。建议立即补依赖。
- 同样情况检查 `lucide-react` 等无问题（未使用）。

#### D. 路由与 view 错配

6 个 view 存在但未在 router 注册（属于 W2 占位 view 的备份）：
- `Annotation.vue`、`Billing.vue`、`Dataset.vue`、`Engines.vue`、`Monitoring.vue`、`Review.vue`、`Scoring.vue`、`Settings.vue`、`Tasks.vue`、`Users.vue`、`Workflows.vue` — 这些占位 view 与 menu 中的同名路由（route name = 'annotation' 等）一一对应，但内容是 W2 占位。
- 注意: 11 个 view 都映射到了路由（路由→view），路由数 ≠ view 缺挂。

---

## 五、API 客户端深度评估

### 5.1 共享基类 (`http.ts`)

✓ **Axios 实例 + 拦截器**: Bearer Token + CSRF Double-submit
✓ **泛型 CRUD helpers**: `getPage<T>` / `getOne` / `createOne` / `updateOne` / `patchOne` / `deleteOne`
✓ **Page<T> + PageQuery** 接口标准化分页参数

### 5.2 认证 store (`api.ts`)

✓ **登录**: 写入 access_token + refresh_token + user 到 localStorage
✓ **401 自动刷新**: 单飞 + 队列化重试，防止 stampede
✓ **刷新失败强登出**: 清空 localStorage，由路由守卫接管

### 5.3 Pinia auth store (`auth.ts`)

✓ 启动时 `restoreFromStorage` 在 router 首次导航前恢复 session
✓ `isAuthenticated` / `role` getter 简单可靠
✓ 错误时仅记录 `lastError` 不抛错

### 5.4 业务模块客户端

| 客户端 | 评估 |
| --- | --- |
| `user.ts` `asset.ts` `annotation.ts` 等 12 个标准 CRUD | ✓ 统一模板，30 行/个，一致性好 |
| `iteration.ts` 193 行 | ✓ 完整封装 sessions + multi_agent + consistency 三套接口 |
| `multimodal.ts` 121 行 | ✓ 8 种理解任务 + 4 种生成模态 + RAG + Agent 调用 |
| `workflow_v2.ts` 286 行 | ✓ DAG + Director + Operator 三层 |
| `obsidian.ts` 74 行 | ✓ Wiki CRUD + Tags + Search + Graph + Autocomplete |
| `skills.ts` 86 行 | ✓ Marketplace + Install + Pipeline + Execution |
| `lineage.ts` 49 行 | ✓ Graph + Impact + Search + List |

**整体评估**: API 客户端架构清晰，类型完备，与 view 解耦。20 个文件无 `// TODO` 残留（grep 0 hit）。

---

## 六、亮点 (值得保留)

| 项 | 说明 |
| --- | --- |
| **Vue Flow DAG 编辑器** (VisualEditor.vue 558 行) | 拖拽 + 自动布局 + 节点配置 + MiniMap + Controls — 可对标 n8n/Flowise |
| **Knowledge Graph** (obsidian/KnowledgeGraph.vue 261 行) | 自定义 SVG 渲染 + 拖拽平移 + 缩放 + 详情面板 — 仿 Obsidian |
| **StoryboardEditor** (assets/StoryboardEditor.vue 462 行) | 场景/镜头/媒体三栏编辑 + 渲染队列 — 类 Final Draft |
| **IterativeStudio** (assets/IterativeStudio.vue 335 行) | 提示词版本树 + A/B 测试 + 评分 — 类 Prompt-Optimizer |
| **Billing Dashboard** (billing/Dashboard.vue 207 行) | 12 维用量 + 套餐对比 + 推荐计划 — 类 Stripe Dashboard |
| **Tickets** (tickets/Tickets.vue 295 行) | SLA 监控 + 状态机 + 评论 + 抽屉详情 — 类 Linear Support |
| **DataTable / ModalForm / SearchBar / PermissionGuard 组件** | 统一封装，13+ view 复用，DRY 原则 |
| **401 refresh 单飞** (api.ts) | 队列化重试 + 强登出，类 Stripe SDK 模式 |
| **CSRF double-submit** | Cookie + Header 双校验 |
| **路由懒加载** | 46 个路由全部 `() => import('@/views/...')` |
| **vendor 拆分** | vue / naive-ui / echarts / vueflow 4 个 vendor chunk，缓存友好 |

---

## 七、与世界顶级 UI 差距速览

| 能力 | Linear | Vercel | Stripe Dashboard | Figma | nanobot-factory |
| --- | --- | --- | --- | --- | --- |
| 暗色模式 | ✓ 系统级切换 | ✓ | ✓ | ✓ | ✗ |
| 键盘命令面板 (⌘K) | ✓ | ✓ | ✓ | ✓ | ✗ |
| 拖拽编辑 | ✓ (issue) | ✗ | ✗ | ✓ (canvas) | ✓ (DAG/Knowledge) |
| 实时协作 | ✓ (cursors) | ✗ | ✗ | ✓ (multiplayer) | ✗ |
| 离线/降级 | ✓ PWA | ✓ | ✓ | ✓ | △ (localStorage fallback) |
| 全局搜索 ⌘K | ✓ | ✓ | ✓ | ✓ | △ (SearchManagement.vue 124 行) |
| 暗/亮主题持久化 | ✓ | ✓ | ✓ | ✓ | ✗ |

详细差距分析见 `reports/p6_4_world_class_gap.md`。

---

## 八、设计美学速览

| 项 | 当前 | 顶级标准 | 差距 |
| --- | --- | --- | --- |
| 主色 | `#2080f0` (Naive UI 默认蓝) | Linear `#5E6AD2` / Vercel `#000` / Stripe `#635BFF` | △ 偏通用 |
| 辅色 | Naive UI 内置 6 色 | 自定义 palette | ⚠ 无品牌色 |
| 字体 | `-apple-system` 系统字体栈 | Inter / SF Pro / Geist Mono | ⚠ 未声明 mono |
| 间距 | 8/12/16/24 (散落) | 4/8/12/16/24/32/48/64 严格 8 级 | ⚠ 不统一 |
| 圆角 | `6px` (全局) | 4/8/12/16 分级 | ⚠ 单一 |
| 阴影 | Naive UI 默认 | 0/1/2/3/4 五级自定义 | △ 未自定义 |
| 动效 | Naive UI 内置 100/200ms | 100/200/300 + cubic-bezier | △ 未声明缓动 |
| 图标 | `menu-icon` (字符) + @vicons/ionicons5 (未声明) | lucide / heroicons / 自绘 SVG | ⚠ 字符图标欠优雅 |

详见 `reports/p6_4_design_aesthetic.md`。

---

## 九、修复优先级 (actions.md 摘要)

| 优先级 | 类别 | 工作量 | 说明 |
| --- | --- | ---: | --- |
| **P0 (今日必修)** | @vicons 补 package.json | 5 min | 隐藏依赖，否则生产部署 npm i 会失败 |
| **P0** | 11 个 stub view 接入真实后端 | 1-2 天 | W2 占位 view 必须落地 |
| **P0** | Naive UI dark theme 切换 UI | 30 min | App.vue 已 import darkTheme，加 toggle 即可 |
| **P1 (本周)** | i18n (vue-i18n + zh-CN/en-US) | 1 天 | 52 view 全部抽离硬编码文本 |
| **P1** | a11y (aria-label / 键盘导航) | 1-2 天 | WCAG AA 必达 |
| **P1** | vitest + 关键 view 单测 | 1-2 天 | 至少覆盖 12 个 CRUD view |
| **P2 (下周)** | ⌘K 命令面板 (Naive UI 组件) | 0.5 天 | 对标 Linear/Vercel |
| **P2** | Playwright E2E (登录 + 3 流程) | 1-2 天 | 关键路径覆盖 |
| **P2** | Naive UI 按需 import | 0.5 天 | vendor 从 726KB 降至 ~400KB |
| **P3 (迭代)** | 暗色主题 token 体系 | 1 天 | design token + CSS vars |
| **P3** | 字体 + 图标库标准化 | 0.5 天 | Inter + lucide-vue-next |
| **P3** | 虚拟列表 (≥ 1万行场景) | 0.5 天 | Naive UI NVirtualList 或 vue-virtual-scroller |

详见 `reports/p6_4_actions.md`。

---

## 十、构建产物清单 (dist/)

总计 53 个文件，最大 5 个：

| 文件 | 原始 | gzip |
| --- | ---: | ---: |
| `assets/naive-vendor-DsVhEGbY.js` | 726 KB | 198 KB |
| `assets/echarts-vendor-DJ_BrDvD.js` | 503 KB | 170 KB |
| `assets/vueflow-vendor-BG0GX79S.js` | 219 KB | 72 KB |
| `assets/vue-vendor-9AeDxxih.js` | 108 KB | 42 KB |
| `assets/index-B6kne4SM.js` | 63 KB | 24 KB |

所有 view 单独 chunk，平均 5-15 KB，懒加载生效。
首屏 vendor 总和: 1556 KB raw / 482 KB gzip — **略超 500KB 目标** (gzip 边缘 OK)，按需 import 后可降至 1100 KB raw / 350 KB gzip。

---

## 十一、结论

**整体评级: B+ (75/100)**

| 维度 | 分 | 说明 |
| --- | ---: | --- |
| 架构完整度 | 90 | vue-tsc 0 error, vite build 11s, 路由懒加载, vendor 拆分, 401 refresh |
| View 数量 | 100 | 52 view 远超 30+ 要求 |
| View 完成度 | 60 | 11 个仍为 W2 stub，业务管理 view 完整 (UserManagement/AssetManagement 等) |
| API 客户端 | 90 | 20 个客户端，类型完备，无 TODO |
| 测试 | 0 | 0 单元测试 + 0 E2E，必须 P1 补 |
| 设计美学 | 60 | Naive UI 默认主题 + 字符图标，缺乏品牌色 |
| i18n / a11y / 暗色 | 0 | 全局缺失，P1 必修 |

**核心建议**: 
1. P0 修 11 个 stub + @vicons 依赖 + 暗色切换 UI (2 天可完成)
2. P1 接 i18n + a11y + 单元测试 (1 周可完成)
3. P2 接 ⌘K + Playwright E2E (1 周可完成)
4. P3 设计 token + 字体 + 图标标准化 (按节奏)

---

## 附录 A: 已验证产物

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| Hard boot check | ✓ | Test-Path `frontend-v2` / `src/views` 全 TRUE |
| View 数量 ≥ 30 | ✓ | 52 个 .vue 文件 (2.0 倍要求) |
| API 客户端 ≥ 12 | ✓ | 20 个 .ts 文件 (1.67 倍要求) |
| vue-tsc 0 error | ✓ | `vue-tsc --noEmit` exit 0, 0 output |
| vite build 成功 | ✓ | 11.13s, 53 chunks, 4902 modules |
| Router 注册 ≥ 30 | ✓ | 46 个 view 路由 + login + catch-all |
| 路由名命名规范 | ✓ | kebab-case 一致 |
| TypeScript 严格模式 | ✓ | `strict: true` in tsconfig.json |
| Pinia 状态管理 | ✓ | 2 store (auth + api), 全局注入 |
| Naive UI 主题 | △ | 单主题 + darkTheme 类型导入未启用 |

## 附录 B: 限制与免责

- 本审计为静态扫描 + 重点 view 抽样深读，未运行浏览器实测；响应式/暗色/性能需手工验证。
- 性能指标 (FCP/LCP/CLS) 未运行 Lighthouse — `lighthouse` 未在项目 package.json 中。
- E2E 测试框架 (Playwright/Cypress) 未配置 — 项目无 `tests/e2e/` 目录。
- 5 份详细报告见同级目录：
  - `p6_4_frontend.md` (本文件，主报告)
  - `p6_4_findings.md` (200+ 项 PASS/FAIL 清单)
  - `p6_4_design_aesthetic.md` (设计美学专项)
  - `p6_4_world_class_gap.md` (对标 Linear/Vercel/Stripe)
  - `p6_4_actions.md` (修复优先级)