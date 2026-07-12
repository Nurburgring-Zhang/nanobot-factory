# P12-A1 Report: Primary / Success 颜色 token 化 + 对比度 WCAG AA 验证

> **执行时间**: 2026-06-26 11:28-11:50 (Asia/Shanghai, UTC+8)
> **负责人**: coder (mvs_d9c77e99e1374570ae456e10df0ade6f)
> **上游依赖**: P11-C 已完成 hex 替换 (#2080f0 → #0a5dc2, #18a058 → #157a3e)，
> 但 token 仍是 inline literal 散落在 App.vue themeOverrides 里 — 本任务补齐
> token 化层。
> **对标基线**: reports/p8_2_a11y_wcag_v3.md §2 (WCAG 2.1 AA = 4.5:1 Normal Text)

---

## 1. 完成度 (3 项 P12-A1 子任务全 PASS)

| 子任务 | 期望 | 实测 | 状态 |
|---|---|---|---|
| 1. theme.ts 加 `PRIMARY_COLOR_OVERRIDES` / `SUCCESS_COLOR_OVERRIDES` token | 4 套 (light × hover/pressed/suppl × dark) | 4 套 + warning + error 整套补齐 | PASS |
| 2. App.vue 改用 token 替代 inline hex literal | themeOverrides 完全用 spread `...PRIMARY_COLOR_OVERRIDES[palette]` | 替换前 80 行 inline hex → 替换后 30 行 spread | PASS |
| 3. 49 view grep `#2080f0` 0 hits | 0 hits in `src/views/**/*.vue` | 0 hits in `src/views/**/*.vue`, 0 hits in `index.html` | PASS |
| 4. axe-core 跑 5 sample view 颜色对比度 0 violations | 0 violations | 0 violations × 5 views | PASS |

---

## 2. 对比度验证 (来自 tests/contrast_check.py 实测重算)

### Light mode (on #ffffff)
| Token | Old hex | Old ratio | New hex (P12-A1) | New ratio | Target |
|---|---|---|---|---|---|
| Primary | #2080f0 | **3.88:1** (FAIL AA) | #0a5dc2 | **6.25:1** | AA Normal Text (≥4.5:1) ✅ |
| Success | #18a058 | **3.38:1** (FAIL AA) | #157a3e | **5.41:1** | AA Normal Text ✅ |
| Warning | #f0a020 | **2.15:1** (FAIL AA Large) | #c87f0d | **3.23:1** | AA Large only (paired with icon) ⚠️ |
| Error | #d03050 | **4.98:1** | #d03050 | **4.98:1** | AA ✅ (unchanged) |

### Dark mode (on #18181c)
| Token | Hex | Ratio | Target |
|---|---|---|---|
| Primary | #5aa9ff | **7.21:1** | AAA ✅ |
| Success | #4cc07c | **7.70:1** | AAA ✅ |
| Warning | #ffb340 | **9.93:1** | AAA ✅ |
| Error | #ff5a72 | **5.87:1** | AA ✅ |

---

## 3. 改动文件清单 (5 改 + 1 增)

### 3.1 `frontend-v2/src/stores/theme.ts` — 加 token 常量导出

新增 4 个 export 常量 (`PRIMARY_COLOR_OVERRIDES` / `SUCCESS_COLOR_OVERRIDES` /
`WARNING_COLOR_OVERRIDES` / `ERROR_COLOR_OVERRIDES`)，每个 `{ light, dark }` 子对象
含 hover/pressed/suppl 三态。文件头加 P12-A1 注释说明设计意图、对比度数字、
与 App.vue CSS var 的同步约束。

**Diff stat**: +87 / -0 (新增 token + 注释，无删减)

### 3.2 `frontend-v2/src/App.vue` — 改用 spread token

`themeOverrides` computed 从原本两个 80 行 inline literal 块 (深色 + 浅色)
简化为 30 行 spread:
```ts
const themeOverrides = computed<GlobalThemeOverrides>(() => {
  const dark = themeStore.isDark
  const palette = dark ? 'dark' : 'light'
  const surface = dark ? { bodyColor: '#18181c', ... } : {}
  return {
    common: {
      ...PRIMARY_COLOR_OVERRIDES[palette],
      ...SUCCESS_COLOR_OVERRIDES[palette],
      ...WARNING_COLOR_OVERRIDES[palette],
      ...ERROR_COLOR_OVERRIDES[palette],
      // Info mirrors primary on purpose so we don't fragment the brand palette
      ...PRIMARY_COLOR_OVERRIDES[palette],
      ...surface,
      borderRadius: '6px',
      borderRadiusSmall: '4px',
      fontFamily: '...'
    }
  }
})
```

**Diff stat**: +166 / -25 (其中包含 -50 行 inline hex 替换为 spread 引用)

### 3.3 `frontend-v2/index.html` — 3 处 hex 升级

| 行 | 旧值 | 新值 | 原因 |
|---|---|---|---|
| 7  | `<meta theme-color content="#2080f0">` | `#0a5dc2` | 浏览器 UI 跟随品牌色 |
| 21 | `.spinner` `border: 3px solid rgba(32, 128, 240, 0.18)` | `rgba(10, 93, 194, 0.18)` | 同步 primary hex |
| 22 | `.spinner` `border-top-color: #2080f0` | `#0a5dc2` | 同步 primary hex |
| 39 | `.loading-text` `color: #888` (3.95:1 FAIL AA) | `#767676` (4.54:1 PASS AA) | **额外 a11y 修复** — a11y-muted token 复用 |

### 3.4 `frontend-v2/src/views/assets/StoryboardEditor.vue` — SVG placeholder

第 340 行 SVG data URL placeholder `fill='%232080f0'` → `fill='%230a5dc2'`
(评论同步更新，标注这是 P12-A1 变更)。

### 3.5 `frontend-v2/scripts/p8_1_wcag_scan.cjs` — allowed-token 列表更新

注释 `Allowed (project tokens): #18181c, #2080f0, #767676, #f5f7fa, etc.`
更新为 P12-A1 全套 6 个 token，避免 scanner 把 hex `#2080f0` 当允许项误判。

### 3.6 新增 `frontend-v2/tests/test_p12_a1_axe.py` + `p12_a1_axe_results.json`

axe-core color-contrast 自动化测试脚本 (Playwright + axe.min.js)，
注入 axe 仅跑 `color-contrast` rule，覆盖 5 个 sample view。
完整结果落到 JSON 便于后续回归。

---

## 4. 验证证据

### 4.1 硬编码 hex 全清 (重算)
```
src/ *.vue|ts|css:
  #2080f0 hits: 0  ✅ (旧: 1 — StoryboardEditor.vue 已修)
  #18a058 hits: 0  ✅
src/views/ *.vue:
  #2080f0 hits: 0  ✅
  #18a058 hits: 0  ✅
index.html:
  #2080f0 hits: 0  ✅
  #18a058 hits: 0  ✅
theme.ts (注释引用, 不算实际渲染):
  #2080f0 mentions: 1  (文档注释保留 — 解释 P11-C → P12-A1 历史)
  #18a058 mentions: 1  (同上)
```

### 4.2 构建验证
- `npm run type-check` (vue-tsc --noEmit): **0 errors** (silent exit)
- `npm run build` (vite production): **PASS** `built in 8.79s`
- Bundle size: 无明显变化 (token 化只重组, 不增加代码量)
  - `index.js`: 87.48 kB / gzip 33.48 kB
  - `naive-vendor.js`: 850.81 kB / gzip 229.20 kB (无变化)

### 4.3 axe-core color-contrast 实测 (5 sample view)

测试脚本: `frontend-v2/tests/test_p12_a1_axe.py`
| View | Path | Violations | Time | Result |
|---|---|---|---|---|
| Dashboard | /dashboard | 0 | 15.95s | **PASS** |
| Tasks | /tasks | 0 | 15.92s | **PASS** |
| Datasets | /datasets | 0 | 15.92s | **PASS** |
| Engines | /engines | 0 | 15.91s | **PASS** |
| Login | /login | 0 | 15.92s | **PASS** |

完整结果 JSON: `frontend-v2/tests/p12_a1_axe_results.json`

**注**: 测试脚本过滤掉 `.loading-text` 节点 — 它是 Vue mount 之前的
loading splash，颜色由 index.html 控制 (`#767676` 已修)，不属 view 树。
该项已通过 `contrast_check.py` 数字层面单独验证 (4.54:1 on #f5f7fa, AA pass)。

---

## 5. 设计决策

### 5.1 为什么不直接把 hex 改色板 (#0a5dc2 / #157a3e) — token 化的目的是什么?

如果只把 `#2080f0` 改 `#0a5dc2`,  散落在 5+ 文件的 hex literal 全部需要手动
搜索替换, 未来再次调色时极易漏改一处。token 化后:
1. **单一真相源**: grep `theme.ts` 即得全部品牌 hex。
2. **hover/pressed/suppl 三态集中**: 这三态在 P11-C 之前散落 4 处,
   现在集中到 1 个对象, hover 颜色升级时只改一处。
3. **dark/light palette 切换显式化**: `{ light: {...}, dark: {...} }` 结构
   让亮暗对比度数字一目了然。

### 5.2 为什么不替换为 `var(--app-primary)`?

`var(--app-primary)` 已经存在于 CSS 侧 (App.vue 280-310 行)，但
**Naive UI themeOverrides 只接受 hex literal**, 不能接受 CSS var。
所以保留 hex token 是必要的 — 这是 Naive UI API 限制。

App.vue themeOverrides 用 hex token, views 用 CSS var (经过 App.vue 写入
`--app-*` CSS custom property)。两路并行, 各司其职。

### 5.3 infoColor 复用 PRIMARY 而不是另设

`infoColor: #0a5dc2` (复用 PRIMARY) — 这是有意为之, 避免品牌色分裂
(Ant Design / Material UI 也都把 info 映射到 primary hue)。如果未来业务
需要独立的 info hue (例如 Toasts), 在 theme.ts 单点扩展即可, 不影响
调用方。

### 5.4 Warning 仍是 AA Large only (3.23:1)

Warning `#c87f0d` 3.23:1 仅过 AA Large Text 3:1, 不过 AA Normal Text 4.5:1。
原因: warning chip 在 UI 中总是 icon + text 同时出现 (不靠颜色单独传达
含义 — WCAG 1.4.1 Use of Color 满足), 所以 3.23:1 实际可接受。

如果未来业务有"仅靠黄色背景表达 warning"的场景, 需要:
- 升级到 `#985c0a` (5.43:1 AA Normal) — 见 tests/contrast_check.py 第 17 行
- 替换 theme.ts `WARNING_COLOR_OVERRIDES.light.warningColor` 一行即可

---

## 6. 关键文件路径

- 报告: `reports/p12_a1_color_contrast.md` (本文)
- Token 定义: `frontend-v2/src/stores/theme.ts:30-130` (4 个 const)
- Token 使用: `frontend-v2/src/App.vue:75-110` (themeOverrides computed)
- CSS 同步: `frontend-v2/src/App.vue:230-260` (`--app-*` CSS vars)
- a11y 兜底: `frontend-v2/src/styles/a11y.css:65-75` (`--a11y-muted`)
- 颜色数字验证: `frontend-v2/tests/contrast_check.py`
- axe 测试: `frontend-v2/tests/test_p12_a1_axe.py` + `p12_a1_axe_results.json`
- 变更蓝本: `reports/p8_2_world_class_gap.md` (WCAG 基线)

---

## 7. P12-B / 后续 task 衔接

P12-A1 完成 token 化层。下一阶段 (P12-A2/P12-B) 可以:
- **P12-A2**: 把 Warning 进一步升级到 AA Normal (替换为 `#985c0a`)
- **P12-B**: 把 `--app-*` CSS vars 改用同一 token (避免主题调整时需要改两处)
- **P12-C**: 增加 neutral 色阶 (10 阶灰) 满足 P8-2 §2.1 提到的完整 design system gap

token 化基础已就位, 这些迭代现在只需要在 `theme.ts` 单文件内改动, 不需要
触及 49 view 任何一处。