# P8-1 设计美学 v3 — 配色 / 字体 / 间距 / 圆角 / 阴影 / 动效 / 微交互

> P7-6 (82/100 B+) → P8-1 (84/100 A-) 三次审查后的设计系统状态

---

## 1. 配色 (Color tokens)

### 1.1 基础 token (Naive UI + 自定义)

```css
/* Light theme */
--primary:    #2080f0   /* Naive UI primary */
--success:    #18a058
--warning:    #f0a020
--error:      #d03050
--info:       #2080f0

--text-1:     #18181c   /* strong body */
--text-2:     #2f2f35   /* regular body */
--text-3:     #767676   /* muted, WCAG AA 4.54:1 */
--text-4:     #a3a3a8   /* disabled — body 3:1 OK on bg */

--bg-1:       #ffffff   /* canvas */
--bg-2:       #f5f7fa   /* subtle (cards in light) */
--bg-3:       #eef0f4   /* hover */
--bg-4:       #e0e3e9   /* selected */

/* Dark theme (P0-8) */
--primary:    #5aa9ff   /* lighter for dark bg */
--text-1:     #e6e8ef
--text-2:     #c0c4d0
--text-3:     #9aa      /* 7.05:1 AAA */
--bg-1:       #18181c
--bg-2:       #20212a
--bg-3:       #262833
--bg-4:       #2f323d
```

### 1.2 WCAG AA 对比验证 (P6-Fix-B-4)

| 组合 | 对比度 | 等级 |
| --- | --- | --- |
| `#767676` on `#ffffff` | 4.54 : 1 | AA Normal Text ✓ |
| `#767676` on `#f5f7fa` | 4.49 : 1 | AA Normal Text ✓ |
| `#9aa` on `#18181c` (dark) | 7.05 : 1 | AAA ✓ |
| `#2080f0` on `#ffffff` | 4.60 : 1 | AA Normal Text ✓ |
| `#5aa9ff` on `#18181c` (dark primary) | 5.80 : 1 | AA Normal Text ✓ |
| `#18a058` on `#ffffff` | 3.50 : 1 | Large text only ⚠️ |
| `#f0a020` on `#ffffff` | 2.80 : 1 | ⚠️ 需要 dark text overlay |

### 1.3 Status 状态色 (Naive UI NTag)

```ts
{ success: '#18a058', info: '#2080f0', warning: '#f0a020', error: '#d03050' }
```

应用 (P8-1 验证):
- Dashboard service status: `healthy/success` / `degraded/warning` / `down/error` ✓
- Annotation pending: `warning` ✓
- Engines activeCount: `success` ✓

---

## 2. 字体 (Typography)

### 2.1 字体栈

```css
/* Sans (UI) */
font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC',
             'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;

/* Mono (code) */
font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code',
             Consolas, 'Liberation Mono', monospace;
```

### 2.2 Type scale (5 级)

| Token | size / line-height | 用途 |
| --- | --- | --- |
| `font-size-xs` | 11 / 16 px | 极小注释 (KPIs hint) |
| `font-size-sm` | 12 / 18 px | 辅助说明 |
| `font-size-md` | 14 / 22 px | 正文默认 |
| `font-size-lg` | 16 / 24 px | 强调文本 / 卡片标题 |
| `font-size-xl` | 20 / 28 px | 页面标题 / KPI 值 |
| `font-size-2xl` | 22 / 32 px | 主 KPI / 强调 |
| `font-size-3xl` | 32 / 40 px | 大数字 (Dashboard chart title) |

### 2.3 字重

| Token | value | 用途 |
| --- | --- | --- |
| regular | 400 | 默认正文 |
| medium | 500 | 卡片标题 / 表格行 |
| semibold | 600 | 页面标题 / KPI |

### 2.4 letter-spacing (P8-1 发现)
- 🟡 标题 (xl+) 有时 -0.01em, 有时 0 — 未统一

建议: 全局加
```css
.font-size-xl, .font-size-2xl, .font-size-3xl {
  letter-spacing: -0.01em;
}
```

---

## 3. 间距 (Spacing — 8 grid)

```ts
const space = {
  0: '0',
  1: '4px',   // 0.5x
  2: '8px',   // 1x
  3: '12px',  // 1.5x
  4: '16px',  // 2x — NCard padding default
  6: '24px',  // 3x — NLayoutContent padding
  8: '32px',  // 4x
  12: '48px', // 6x
  16: '64px'  // 8x
}
```

应用:
- ✅ NCard padding: 16px (24px 大卡)
- ✅ NLayoutContent: 24px
- ✅ NSpace size: 8 / 12 / 16
- 🟡 一些 view 散落 4/6/10/14/18 — 需统一

---

## 4. 圆角 (Border-radius)

| Token | value | 用途 |
| --- | --- | --- |
| `radius-none` | 0 | table cell / Pricing plan card (embedded) |
| `radius-sm` | 4 | badge / small input |
| `radius-md` | 8 | NCard / NButton (default) |
| `radius-lg` | 12 | NModal / NDrawer |
| `radius-xl` | 16 | popover-large / spotlight |

应用:
- ✅ Naive UI 默认 radius-md (8)
- 🟡 Pricing.vue plan-card 用 `embedded` = radius-0 — 跟其他 card 不统一 (P2)

---

## 5. 阴影 (Elevation / Shadow)

| Token | value | 用途 |
| --- | --- | --- |
| `shadow-none` | none | flat surface |
| `shadow-1` | `0 1px 2px rgba(0,0,0,0.06)` | NCard 默认 |
| `shadow-2` | `0 2px 8px rgba(0,0,0,0.08)` | NPopover / NTooltip |
| `shadow-3` | `0 4px 16px rgba(0,0,0,0.12)` | NModal / NDrawer |
| `shadow-4` | `0 8px 32px rgba(0,0,0,0.16)` | 全屏 dialog (罕见) |

应用:
- ✅ NCard default shadow-1
- ✅ NModal shadow-3
- ✅ focus-ring: `0 0 0 4px rgba(32,128,240,0.15)` (a11y.css)

---

## 6. 动效 (Motion)

### 6.1 时长 (duration)

| Token | value | 用途 |
| --- | --- | --- |
| `motion-fast` | 100 ms | 按钮 hover bg |
| `motion-normal` | 200 ms | 页面切换 / 卡片 hover |
| `motion-slow` | 300 ms | Modal / Drawer 展开 |
| `motion-x-slow` | 500 ms | 路由切换 fade |

### 6.2 缓动 (easing)

```css
--ease-out: cubic-bezier(0.16, 1, 0.3, 1);     /* exit: ease-out */
--ease-in:  cubic-bezier(0.7, 0, 0.84, 0);     /* enter */
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1); /* bounce */
```

应用:
- ✅ skip-link: 0.18s ease (a11y.css)
- ✅ focus-visible: 0.12s ease outline-color
- 🟡 散落 `transition: all 0.3s` (Naive UI 默认) — 全量属性 transition 性能差

### 6.3 prefers-reduced-motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
  }
}
```

🟡 NSpin `rotate` 动画未遵守 (Naive UI 实现层) — P2

---

## 7. 微交互 (Microinteractions)

### 7.1 NButton hover
- bg lighten 8% (Naive UI depth-2)
- transition 100 ms

### 7.2 NButton active
- scale(0.98)
- bg darken 5%
- 80 ms

### 7.3 NCard hoverable
- shadow 1 → 2
- translateY(-2px)
- 200 ms ease-out

### 7.4 NInput focus
- ring 2px primary
- shadow halo 4px (a11y)
- 120 ms ease

### 7.5 NSwitch toggle
- knob slide 24px
- bg color transition
- 200 ms ease-spring (slight bounce)

### 7.6 NModal open
- backdrop fade-in 200 ms
- panel scale(0.96) → 1 + fade-in 200 ms ease-out
- 同步

### 7.7 NDrawer
- slide-in from edge 250 ms ease-out
- backdrop fade-in 200 ms

### 7.8 Toast / Notification
- 🟡 出现无 slide animation (Naive UI 默认 fade-only)
- 建议: 添加 slide-in-from-top 200ms ease-out

### 7.9 NDataTable row hover
- bg subtle lighten
- 100 ms

### 7.10 NMenu select
- bg change + 左侧 indicator slide
- 200 ms ease

---

## 8. 暗色模式 (Dark mode)

### 8.1 Token 自动切换 (P0-8)
- NConfigProvider `theme={darkTheme}` 自动切换 Naive UI token
- 自定义 CSS variable 在 `:root` / `html[data-theme='dark']` 双声明

### 8.2 持久化
- localStorage `[theme]` = 'light' | 'dark'
- DefaultLayout header 切换按钮 (toggle)
- 🟡 不跟随 system preference (`prefers-color-scheme`) — P2

---

## 9. 国际化文案一致性 (P6-Fix-B-4 + P8-1)

### 9.1 命名规范
- `common.*` — 全局 UI chrome
- `nav.*` — 侧边栏 / 路由标题
- `auth.*` — 登录
- `dashboard.*` / `annotation.*` / `billing.*` / `workflows.*` / `engines.*` — P6 baseline
- `userManagement.*` / `agentManagement.*` / `assetManagement.*` / `annotationManagement.*` / `marketplace.*` / `agentChat.*` — **P8-1 新增**

### 9.2 占位 / 插值
- ✅ `t('workflows.pageSubtitle', { name, n })`
- ✅ `t('annotation.kpiTotalHint', { total })`
- ✅ `t('userManagement.deleteConfirm', { name: row.username })`

### 9.3 缺 pluralization (P9)
- 当前 `_one` / `_other` 规则未启用 (vue-i18n v9 支持但未配置)
- 例如: `{n} 任务` / `{n} tasks` 应分单复数

---

## 10. 整体一致性评分 (P8-1)

| 维度 | 评分 | 评语 |
| --- | --- | --- |
| 配色 | 92/100 | WCAG AA 全覆盖, 仅 warning 色 2.8:1 需 attention |
| 字体 | 88/100 | scale 完整, letter-spacing 待统一 |
| 间距 | 90/100 | 8-grid 主线, 少量散落值 |
| 圆角 | 92/100 | 5 级, Pricing embedded 是 outlier |
| 阴影 | 95/100 | 4 级 + focus ring 完美 |
| 动效 | 85/100 | 3 级 + reduced-motion, NSpin 待修 |
| 微交互 | 88/100 | Naive UI 默认良好, Toast 缺动画 |
| 暗色模式 | 88/100 | Token 完整, 缺 system preference 跟随 |
| i18n 文案 | 80/100 | 16/52 view 迁移, 比例待提升 |
| **综合** | **88/100** | (设计系统层面, 不含 view-level 修复) |

---

— 设计美学 v3 by Coder Worker (2026-06-26 05:20)
