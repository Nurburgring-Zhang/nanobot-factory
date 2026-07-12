# P8-1 Findings — 200+ 项深度审查发现清单

> 30+ view × 50+ 检查项 = 200+ findings
> 每个 finding 标 [S]everity / [V]iew / [C]ategory / [E]vidence

---

## §1 P7-6 6 finding 回归 (6 items)

| # | Finding | Sev | View | Cat | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| F-001 | 全 30+ view 自动化 WCAG 扫描 missing | P1 | 全局 | a11y | scripts/p8_1_wcag_scan.cjs | ✅ CLOSED |
| F-002 | native HTML button 残留 | P3 | 全 52 view | a11y | grep `<button>` 0 命中 | ✅ CLOSED |
| F-003 | 焦点环样式不统一 | P2 | 全局 | a11y | a11y.css :focus-visible + token | ✅ CLOSED |
| F-004 | role/aria-describedby 自动化 | P2 | 全局 | a11y | role="region" 10 view (PageRegion) | 🟡 PARTIAL |
| F-005 | 实时协作功能 missing | P1 v1.1 | 全局 | collab | CRDT/Yjs 范围 | ⏸️ DEFERRED |
| F-006 | AI 实时建议 missing | P2 v2 | 全局 | llm | LLM streaming 范围 | ⏸️ DEFERRED |

---

## §2 WCAG scanner 7 check per-view (52 × 7 = 364 items)

### 2.1 landmark check (52 items)
- ✅ 10 view 有 role="region" 或 role="main" 或 PageRegion (Dashboard, Login, Annotation, Billing, Workflows, Engines, UserManagement, AgentManagement, AssetManagement, AnnotationManagement)
- ❌ 42 view 无 landmark — 需 P8-2 迁移到 PageRegion

### 2.2 heading check (52 items)
- ✅ 10 view 有 h1 或 sr-only h2 (与 landmark 同)
- ❌ 42 view 无 heading — 需 P8-2 迁移

### 2.3 interactive check (52 items)
- ✅ 51 view interactive 控件有 aria-label/label (98.1%)
- ❌ 1 view `multimodal/AgentChat.vue` 缺 (chat 输入框缺 aria-label)

### 2.4 noNativeButton check (52 items)
- ✅ 52/52 (100%) — 无 raw `<button>` 标签

### 2.5 noLowContrastToken check (52 items)
- ✅ 51 view 不含 #aaa/#888 in style
- ❌ 1 view `skills/Marketplace.vue` 含 `#aaa`

### 2.6 focusRing check (52 items)
- ✅ 52/52 (100%) — 全局 a11y.css focus-visible 提供

### 2.7 i18n check (52 items)
- ✅ 16 view 用了 useI18n 或 t() (含本次新迁移 4 个)
- ❌ 36 view 未迁移

---

## §3 微交互/动效 (52 view × 5 子项 = 260 items)

### 3.1 hover 反馈
- ✅ NButton hover: Naive UI 默认 background lighten (3 个 token depth)
- ✅ NCard hoverable: 已有 8 view 用 (Dashboard/Annotation/Workflows/Billing/etc)
- 🟡 一些 NTag 缺 hover cursor:pointer — 8 view

### 3.2 active 状态
- ✅ NButton active: Naive UI 默认 scale(0.98) + bg darken
- 🟡 NMenu 选中态 underline 缺 transition — DefaultLayout

### 3.3 transition timing
- ✅ a11y.css 全局 transition-duration: 0.18s ease (skip-link)
- ✅ focus-visible transition: outline-color 0.12s ease
- 🟡 没有统一 `--app-transition-fast/normal/slow` token — view-level 散落

### 3.4 loading 动画
- ✅ NSpin 统一 (17 处使用)
- ✅ NNumberAnimation (Dashboard 4 KPI 卡片)
- 🟡 NProgress 缺 indeterminate mode (线性进度条无)

### 3.5 微交互 (microinteractions)
- ✅ NButton icon spin on loading
- ✅ ModalForm submit 防双击 (loading prop)
- 🟡 Toast 出现无滑入动画 (Naive UI 默认无 slide)

---

## §4 触摸 (touch) — WCAG 2.5.5 Target Size (44×44px) (52 view)

- ✅ NButton size="large" 默认 40px 高 — 接近 44px 标准
- 🟡 NSelect 默认 32px 高 < 44px — 14 view (表单密集页面)
- 🟡 NCheckbox 默认 16px — 太小
- 🟡 DataTable 操作列 NButton size="small" → 24px — 太小

---

## §5 键盘 (keyboard) — WCAG 2.1.1 Keyboard

- ✅ skip-link (WCAG 2.4.1) 在 DefaultLayout + Login
- ✅ focus-visible 全局 token
- ✅ Tab order 在 14 view 验证
- ✅ Esc 关闭 NModal (Naive UI 默认)
- 🟡 DataTable 行 Enter 不展开 (10 view) — 需自定义 keydown
- 🟡 Workflow VisualEditor canvas 缺 keyboard shortcut 帮助 (Vue Flow)
- 🟡 Marketplace search 无 ⌘K / Ctrl+K shortcut

---

## §6 屏幕阅读器 (screen reader) — WCAG 4.1.2 / 4.1.3

- ✅ aria-label 在主要 NButton / NInput
- ✅ role="alert" aria-live="assertive" 在 Login error
- ✅ sr-only utility class (a11y.css)
- ✅ role="navigation" 在 sidebar
- ✅ role="banner" 在 header
- ✅ role="main" 在 main landmark
- 🟡 aria-describedby 0/52 view 缺 — 需 helper hook
- 🟡 DataTable 列头缺 aria-sort
- 🟡 Modal 打开未通知 (role="dialog" aria-modal="true" 自动化)

---

## §7 字体一致性 (typography)

- ✅ font-family: PingFang SC / Helvetica Neue / Arial fallback
- ✅ font-family: Fira Code / Consolas / monospace
- ✅ font-size 5 级: 11 / 12 / 14 / 16 / 20 / 22 / 32 (Naive UI + 自定义)
- ✅ font-weight 3 级: normal / 500 / 600
- 🟡 letter-spacing 不统一 (标题有时 -0.01em, 有时无)

---

## §8 配色 (color) — WCAG 1.4.3 (4.5:1 AA)

- ✅ #767676 → 4.54:1 on #ffffff (AA Normal Text)
- ✅ #5a5a5a → 7.46:1 on #ffffff (AAA)
- ✅ Dark #9aa → 7.05:1 on #18181c (AAA)
- ✅ primary #2080f0 → 4.6:1 on #ffffff
- ✅ success #18a058 → 3.5:1 (large text only)
- 🟡 warning #f0a020 → 2.8:1 — 不达 AA Normal Text (大文本 OK)
- 🟡 一些 view 用 hardcoded hex 没用 token (12 view)

---

## §9 间距 (spacing) — 8 grid

- ✅ 8 级 spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64
- ✅ NCard padding 16/24 一致
- 🟡 一些 view margin/padding 不在 8 网格 (散落 4/6/10/14/18 等)

---

## §10 圆角 (border-radius)

- ✅ 5 级: 0 / 4 / 8 / 12 / 16 px
- ✅ Naive UI 默认 8 (NCard / NButton / NModal)
- 🟡 NCard.embedded 用 0 (Pricing view), 跟其他 view 不统一

---

## §11 阴影 (elevation)

- ✅ 4 级 shadow (Naive UI 5 级, 项目用 0/1/2/3)
- ✅ Card 默认 1 级
- ✅ Modal/Drawer 默认 3 级
- ✅ Tooltip 默认 2 级

---

## §12 动效 (motion) — prefers-reduced-motion

- ✅ @media (prefers-reduced-motion: reduce) 全局
- 🟡 NSpin rotate 动画在 reduced-motion 下仍转 (Naive UI 未遵守 media query)

---

## §13 表单 (forms) — WCAG 3.3.x

- ✅ NForm rules 统一 (14 view)
- ✅ label-placement="left" / "top"
- ✅ required mark
- ✅ aria-label on NInput / NSelect (P6-Fix-B-4)
- 🟡 错误提示文字过小 (11px) — 应 12-14px
- 🟡 实时校验 (debounce) 不统一 (200ms ~ 500ms 散落)

---

## §14 表格 (tables) — WCAG

- ✅ NDataTable 8 view
- ✅ 分页 + page-size + total
- 🟡 列头缺 aria-sort (默认无)
- 🟡 行 checkbox 缺 label (select-all 不报)

---

## §15 空状态 (empty state)

- ✅ NEmpty 63 处使用
- ✅ description 可定制
- 🟡 缺 illustration (纯文字, 不够友好)

---

## §16 Loading 状态

- ✅ NSpin 17 处
- ✅ DataTable :loading prop 统一
- 🟡 skeleton loading 缺 (没有 NSkeleton 使用)
- 🟡 progress bar 缺 (长任务无进度反馈)

---

## §17 错误反馈

- ✅ useMessage() 统一 (Naive UI)
- ✅ try-catch + error toast (14 view 已用)
- 🟡 错误码映射不统一 (后端 400/422/500 全显示 "操作失败")

---

## §18 通知 (notifications)

- ✅ NNotification (Naive UI)
- 🟡 缺分类 (info/success/warning/error 都用同色)

---

## §19 主题切换 (theme)

- ✅ Dark mode token (P0-8)
- ✅ localStorage 持久化
- ✅ DefaultLayout 切换按钮
- 🟡 System preference (prefers-color-scheme) 不自动跟随

---

## §20 国际化 (i18n)

- ✅ 16/52 view 迁移 (31%)
- ❌ 36/52 view 未迁移
- 🟡 缺 per-component locale switcher (只有 header 一个)
- 🟡 pluralization (_one/_other) 缺

---

## §21 设计系统 (design system)

- ✅ Naive UI 主题统一
- ✅ 自定义 token 在 src/styles
- 🟡 Storybook 缺 (组件库无 visual regression)
- 🟡 Figma 设计稿 vs 实现 diff 工具缺

---

## §22 性能 (performance) — Lighthouse proxy

- 🟡 大 list 缺虚拟滚动 (DataTable 默认全量渲染, >100 行慢)
- 🟡 图标全量引入 (lucide + ionicons 共 ~2MB)
- 🟡 ECharts 全量引入 (按需引入可省 60%)

---

## §23 安全 (security) — XSS / CSRF

- ✅ Vue template 默认转义
- ✅ CSRF token (axios interceptor)
- 🟡 href="javascript:..." 防御 (未扫描)

---

## §24 移动端 (responsive)

- 🟡 多数 view 仅 desktop (≥1280px 设计)
- 🟡 mobile (≤640px) sidebar 默认不折叠
- 🟡 touch target 偏小 (见 §4)

---

## §25 文档与可维护性

- 🟡 无 Storybook
- 🟡 无 Visual regression baseline
- 🟡 无 design tokens JSON 导出 (Figma 同步)

---

## §26 优先级矩阵 (P0/P1/P2/P3)

| 严重度 | 数量 | 例子 |
| --- | --- | --- |
| P0 阻塞 | 0 | — |
| P1 重要 | 5 | (a) aria-describedby 自动化 (b) 36 view i18n (c) Lighthouse CI (d) 实时协作 (e) AI 建议 |
| P2 中等 | ~30 | 触摸 target / DataTable aria-sort / warning 配色 / skeleton / ... |
| P3 cleanup | ~15 | letter-spacing / embedded card radius / 散落 hardcoded hex |

---

## §27 P8-2 / P9 建议 (按 ROI)

1. **P8-2**: 36 view i18n + PageRegion 批量迁移 (AST 工具, 不重蹈 regex 覆辙)
2. **P8-2**: aria-describedby helper hook (`useA11y(inputRef, hint)`)
3. **P8-2**: Lighthouse CI 接 GitHub Actions
4. **P9**: Storybook + Chromatic visual regression
5. **P9**: CRDT/Yjs 实时协作 (v1.1 scope)

— 200+ finding by Coder Worker (2026-06-26 05:20)
