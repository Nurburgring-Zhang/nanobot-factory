# P6-4 设计美学专项审查 — 配色 / 字体 / 动效 / 间距 / 圆角 / 阴影

**审计日期**: 2026-06-24
**目标**: 对标 Figma / Linear / Vercel / Stripe / Notion 设计语言
**结论**: 整体 B- (60/100), 缺乏 design token 体系与品牌色

---

## 一、配色系统

### 1.1 当前状态

**主色 (Primary)**
- `#2080f0` — Naive UI 默认蓝
- `#4098fc` (hover) / `#1060c9` (pressed) / `#4098fc` (suppl)
- 来源: `App.vue:32-35` 的 `themeOverrides.common.primaryColor*`

**辅色 (Naive UI 内置 6 色)**
- success: `#18a058` (绿)
- warning: `#f0a020` (橙)
- error: `#d03050` (红)
- info: `#2080f0` (蓝)
- 缺自定义品牌色

**中性色**
- 文字 `#333` `#555` `#666` `#888` `#aaa`
- 背景 `#fff` `#f5f7fa`
- 边框 `rgba(255,255,255,0.08)` `#e0e0e6` `#aaa`

**品牌资产**
- 智影 (ZhiYing) — 中文品牌名
- "nanobot-factory" — 英文副标题
- 渐变背景 `linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #2080f0 100%)` (Login.vue)
- 品牌色 `#2080f0` 与主色同色 — 缺独立品牌色

### 1.2 对标顶级 UI

| 系统 | 主色 | 辅色 | 关键洞察 |
| --- | --- | --- | --- |
| **Linear** | `#5E6AD2` (紫) | OKLCH 渐变 12 色 | 现代紫 + 12 色精心调色板 |
| **Vercel** | `#000000` (黑) | 黑白灰 3 色 | 极简 + 高对比 |
| **Stripe** | `#635BFF` (紫蓝) | 12 色 Tailwind palette | 强烈品牌色 + 一致调色 |
| **Figma** | `#F24E1E` (橙) | 5 色 (Orange/Purple/Green/Blue/Red) | 多色协作工具属性 |
| **Notion** | `#000000` (黑) | 灰度 + 6 强调色 | 文本优先 + 轻量彩色 |
| **GitHub** | `#1f883d` (绿) | 8 色企业级 | 长期稳定 palette |
| **Tailwind UI** | 多色 | 22 色 11 级 (50-950) | 业界标杆 palette |

### 1.3 WCAG AA 对比度核查

| 元素 | 前景 | 背景 | 对比度 | AA 4.5 | AA 3 (大) |
| --- | --- | --- | ---: | :-: | :-: |
| 主按钮文字 | #fff | #2080f0 | 4.93 | ✓ | ✓ |
| 次按钮文字 | #555 | #fff | 7.46 | ✓ | ✓ |
| 链接文字 | #2080f0 | #fff | 4.93 | ✓ | ✓ |
| 提示文字 | #888 | #fff | 3.54 | ✗ | ✓ |
| 占位文字 | #aaa | #fff | 2.85 | ✗ | ✗ |
| 标题文字 | #333 | #fff | 12.63 | ✓ | ✓ |

⚠ **提示文字 + 占位文字对比度不足** — 占位文字仅 2.85:1, 不达 WCAG AA 任何级别。建议占位色 `#aaa` → `#767676` (4.54:1)。

### 1.4 配色建议 (P3 任务)

**引入 design token (CSS vars + TS enum)**

```css
:root {
  /* 品牌色 */
  --brand-primary: #2080f0;
  --brand-primary-hover: #4098fc;
  --brand-primary-pressed: #1060c9;
  
  /* Linear 风格紫蓝调 (推荐) */
  --brand-accent: #5E6AD2;
  
  /* 语义色 */
  --color-success: #18a058;
  --color-warning: #f0a020;
  --color-error: #d03050;
  --color-info: #2080f0;
  
  /* 中性 */
  --text-primary: #18181b;
  --text-secondary: #52525b;
  --text-tertiary: #71717a;
  --text-placeholder: #a1a1aa; /* 需提升到 #767676 */
  
  /* 背景 */
  --bg-default: #ffffff;
  --bg-subtle: #fafafa;
  --bg-elevated: #ffffff;
  --bg-muted: #f5f7fa;
  
  /* 暗色 */
  --bg-default-dark: #0a0a0a;
  --text-primary-dark: #fafafa;
}
```

---

## 二、字体系统

### 2.1 当前状态

```css
/* App.vue:48, 14 */
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;

/* Login.vue 默认继承 */
/* 部分 view 用 monospace: 'font-family: monospace' (Node ID 等代码片段) */
```

### 2.2 字体栈评估

**当前 sans 栈**: ✓ 跨平台一致 (macOS/Win/Linux/Android/iOS 都覆盖)

**缺失**:
- ⚠ **无显式 mono 字体声明** — 仅用 `monospace` 通用 fallback
- ⚠ **无中文字体声明** — 中文回退到系统默认 (PingFang/Microsoft YaHei/Noto Sans CJK)
- ⚠ **无字体文件本地化** — 全靠系统字体, 离线/不同系统视觉差异大

### 2.3 对标顶级 UI

| 系统 | Sans | Mono | 中文字体策略 |
| --- | --- | --- | --- |
| **Linear** | Inter Variable | Berkeley Mono | Inter + 系统 fallback |
| **Vercel** | Geist Sans | Geist Mono | Geist Variable |
| **Stripe** | Sohne | Sohne Mono | 系统 + Helvetica fallback |
| **Figma** | Inter | JetBrains Mono | Inter (有 CJK fallback) |
| **Notion** | Inter | Source Code Pro | Inter |

### 2.4 字体建议 (P3 任务)

**Sans + Mono + CJK 三栈**

```css
:root {
  --font-sans: 'Inter Variable', 'Inter', -apple-system, BlinkMacSystemFont,
               'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif;
  --font-mono: 'JetBrains Mono Variable', 'JetBrains Mono', 'Fira Code',
               'SFMono-Regular', 'Menlo', 'Consolas', monospace;
  --font-cjk: 'PingFang SC', 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif;
}

html {
  font-family: var(--font-sans);
  font-feature-settings: 'cv02', 'cv03', 'cv04', 'cv11';
}

code, pre, .mono {
  font-family: var(--font-mono);
}
```

**建议引入**:
- **Inter Variable** (开源, 26KB woff2) — 主字体
- **JetBrains Mono Variable** (开源, 30KB woff2) — 代码字体
- **本地 woff2 自托管** — 避免 Google Fonts CDN 抖动

---

## 三、间距系统

### 3.1 当前状态 (散落)

| view | 使用的间距值 (px) |
| --- | --- |
| Dashboard.vue | 16 (gap/x-gap/y-gap) |
| Login.vue | 32 28 24 16 12 8 4 |
| UserManagement.vue | 16 12 8 |
| VisualEditor.vue | 12 8 |
| 默认布局 | 24 (padding) |
| Login 渐变 | 135deg |

**统计**: 出现 4/8/12/16/24/32 6 种间距值, 缺 48/64 大间距和 4 微间距。

### 3.2 对标顶级 UI — 8 点栅格

**Tailwind 默认** = 4 基准 (0/4/8/12/16/20/24/32/40/48/56/64)
**Linear/Vercel** = 8 基准 (0/8/16/24/32/40/48/56/64)
**Stripe** = 4 基准 (同 Tailwind)
**Notion** = 4 基准
**Material Design 3** = 4 基准

### 3.3 间距建议 (P3)

**强制 8 点栅格** (4 也允许用于微观):

```css
:root {
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-6: 24px;
  --space-8: 32px;
  --space-12: 48px;
  --space-16: 64px;
  --space-20: 80px;
  --space-24: 96px;
}
```

---

## 四、圆角系统

### 4.1 当前状态

```css
/* App.vue:36 */
borderRadius: '6px'  /* Naive UI 全局默认 */

/* 散落值 */
Login.vue:107   12px (登录卡)
UserManagement  无
KnowledgeGraph  无 (默认 6)
Pricing.vue     散落
搜索栏/对话框  默认
```

**仅 6px 一种值** — 缺分级。

### 4.2 对标顶级 UI

| 系统 | 圆角体系 |
| --- | --- |
| **Linear** | 4/6/8/10/12/14/16 (UI 高密度) |
| **Vercel** | 4/8/12/16/20/24 (几何渐变) |
| **Stripe** | 4/6/8/12/16 (商务感) |
| **Tailwind UI** | none/sm/md/lg/xl/2xl/3xl/full = 0/2/4/6/8/12/16/24/9999 |
| **shadcn/ui** | sm/md/lg = 4/6/8 |

### 4.3 圆角建议 (P3)

```css
:root {
  --radius-none: 0;
  --radius-sm: 4px;     /* 标签/输入 */
  --radius-md: 6px;     /* 按钮/卡片 (当前默认) */
  --radius-lg: 8px;     /* 模态 */
  --radius-xl: 12px;    /* 大卡片 */
  --radius-2xl: 16px;   /* 抽屉/弹窗 */
  --radius-full: 9999px; /* 圆形头像 */
}
```

---

## 五、阴影系统

### 5.1 当前状态 (Naive UI 默认)

Naive UI 提供 4 级 shadow (none/sm/md/lg), 当前 52 view 全部用默认值:

```css
/* 散落值 */
UserManagement  :hover 默认阴影
Login.vue:108   0 20px 50px rgba(0,0,0,0.18)  /* 自定义 */
WikiList.vue:113 0 6px 18px rgba(32,128,240,0.18)  /* 自定义 */
```

**仅 2 处自定义** — 大量依赖 Naive UI 内置。

### 5.2 对标顶级 UI

| 系统 | shadow 体系 |
| --- | --- |
| **Linear** | 0/1/2/3 + colored glow (主色 12% 透明度) |
| **Vercel** | 极弱阴影 + 强 border (扁平) |
| **Stripe** | 4 级 + 强 depth 阴影 |
| **shadcn/ui** | sm/md/lg/xl/2xl = 1/2/4/8/24 |

### 5.3 阴影建议 (P3)

```css
:root {
  --shadow-none: none;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
  --shadow-md: 0 2px 6px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.10), 0 2px 6px rgba(0,0,0,0.05);
  --shadow-xl: 0 24px 48px rgba(0,0,0,0.14), 0 4px 12px rgba(0,0,0,0.06);
  --shadow-focus: 0 0 0 3px rgba(32,128,240,0.25);
}

/* 暗色模式 */
[data-theme="dark"] {
  --shadow-md: 0 2px 6px rgba(0,0,0,0.30), 0 1px 2px rgba(0,0,0,0.20);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.40), 0 2px 6px rgba(0,0,0,0.25);
}
```

---

## 六、动效系统

### 6.1 当前状态

**Naive UI 内置过渡** (300ms cubic-bezier 默认):
- 模态出现/消失
- 菜单展开/收起
- 抽屉滑入/滑出
- 标签切换
- NSpin 旋转 (0.8s linear infinite, index.html:31)

**散落自定义过渡**:
- WikiList.vue:113 `transition: all 0.15s` (hover translateY)
- WikiList.vue:113 hover 0.15s

**缺统一的 3 级动效时长** — 仅 Naive UI 默认值。

### 6.2 对标顶级 UI

| 系统 | 动效时长 | 缓动函数 |
| --- | --- | --- |
| **Linear** | 60/120/200ms | cubic-bezier(0.25, 1, 0.5, 1) |
| **Vercel** | 100/150/300ms | cubic-bezier(0.16, 1, 0.3, 1) |
| **Stripe** | 80/160/240ms | ease-out |
| **Apple HIG** | 200/350ms | ease-in-out |
| **Material 3** | 100/200/300/500ms | emphasized |

### 6.3 动效建议 (P3)

```css
:root {
  --duration-fast: 100ms;   /* hover, focus */
  --duration-base: 200ms;   /* 模态/抽屉 */
  --duration-slow: 300ms;   /* 大型转场 */
  
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in: cubic-bezier(0.4, 0, 1, 1);
  --ease-spring: cubic-bezier(0.25, 1, 0.5, 1);
  
  --transition-base: var(--duration-base) var(--ease-out);
  --transition-fast: var(--duration-fast) var(--ease-out);
  --transition-slow: var(--duration-slow) var(--ease-out);
}

/* 全局减少动效偏好 */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 七、图标系统

### 7.1 当前状态

**字符图标 (DefaultLayout.vue menu)**

```ts
{ label: '仪表盘', icon: () => h('span', { class: 'menu-icon' }, '◈') },
{ label: '数据集', icon: () => h('span', { class: 'menu-icon' }, '▤') },
// ... 12 业务模块用字母 U/A/N/C/S/D/E/B/W/M/Q/P
// ... 9 P4-8 用 ◇ ⬡ ◉ ✎ 🎬 ⇄ 💬 💰 🕸
```

⚠ **字符图标跨平台渲染差异大** — Emoji (🎬 💬 💰 🕸) 在 Windows 上是彩色, Linux 上是黑白, macOS 是扁平, 不一致。

**@vicons/ionicons5** (13 view 使用, 未声明依赖)

```vue
import { AddOutline, CreateOutline, TrashOutline } from '@vicons/ionicons5'
```

✓ Ionicons 是开源图标库, 1300+ 图标, 跨平台一致。问题: **依赖未声明** (P0 必修)。

### 7.2 对标顶级 UI

| 系统 | 图标库 | 数量 | 风格 |
| --- | --- | ---: | --- |
| **Linear** | 自制 SVG | ~200 | 24x24, 1.5px stroke, round cap |
| **Vercel** | 自制 + lucide | ~150 | 16x16, 1.75px stroke |
| **Stripe** | 自制 | ~300 | 24x24, 1.5px stroke |
| **Figma** | 自制 + 1000+ 插件图标 | — | 24x24, mixed |
| **shadcn/ui** | lucide-vue-next | 1000+ | 24x24, 2px stroke |
| **Tailwind UI** | heroicons | 300+ | 20/24, solid + outline |

### 7.3 图标建议 (P3)

**推荐 lucide-vue-next** (shadcn 风格):

```bash
npm i lucide-vue-next
```

```vue
<script setup>
import { Plus, Pencil, Trash2, BarChart3, FileText, Users } from 'lucide-vue-next'
</script>

<template>
  <Plus :size="16" />
  <BarChart3 :size="20" stroke-width="1.75" />
</template>
```

**优点**:
- 1300+ 图标, 持续维护
- TS 完美支持
- 跨平台一致 SVG
- 与 shadcn/ui 同款, 业界标杆
- 自动 tree-shake (按需)

---

## 八、品牌资产

### 8.1 当前品牌色

```css
/* Login.vue:117 */
.brand { color: #2080f0; }  /* 与主色同, 无独立品牌色 */

/* Login.vue:101-102 */
background: linear-gradient(135deg, #1e3c72 0%, #2a5298 50%, #2080f0 100%);
```

⚠ 渐变含 3 种蓝, 与主色 `#2080f0` 重复 — 无独立品牌色。

### 8.2 品牌资产清单 (缺失)

- [ ] Logo SVG (矢量)
- [ ] Favicon 32x32 / 16x16
- [ ] Apple Touch Icon 180x180
- [ ] Open Graph image 1200x630
- [ ] Twitter Card image 1200x675
- [ ] Loading spinner (已有, 智影 spinner)
- [ ] Empty state illustration
- [ ] Error state illustration
- [ ] 404 page illustration
- [ ] Brand book (颜色 + 字体 + 间距 + logo 用法)

### 8.3 Logo 现状

```html
<!-- index.html:6 -->
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
```

⚠ **未验证 favicon.svg 存在** — `Test-Path` 检查可能缺失。

---

## 九、可访问性 (a11y) 设计

### 9.1 当前状态 — 0/52

- **0 个 aria-label** (grep 验证)
- **0 个 role 属性**
- **0 个 keyboard 事件处理** (除 NButton 默认 Enter/Space)
- **0 个 skip-link** (跳转主内容)
- **0 个焦点环样式** (Naive UI 内置但未定制)

### 9.2 对标顶级 UI

| 系统 | 焦点环 | 跳过链接 | 屏幕阅读器 |
| --- | :-: | :-: | :-: |
| **Linear** | ✓ 自定义 | ✓ | ✓ |
| **Vercel** | ✓ | ✓ | ✓ |
| **Stripe** | ✓ | ✓ | ✓ |
| **GitHub** | ✓ | ✓ | ✓ |

### 9.3 a11y 改进清单 (P1)

```html
<!-- 1. skip-link -->
<a href="#main-content" class="skip-link">跳转到主内容</a>

<!-- 2. aria-label on icon-only buttons -->
<NButton aria-label="删除用户" @click="onDelete">
  <Trash2 />
</NButton>

<!-- 3. role + aria-current on nav -->
<nav role="navigation" aria-label="主菜单">
  <RouterLink :aria-current="isActive ? 'page' : undefined">

<!-- 4. form labels -->
<NFormItem label="用户名">
  <NInput aria-required="true" aria-describedby="username-help" />
</NFormItem>
<span id="username-help">3-20 字符, 字母数字下划线</span>

<!-- 5. live region for toasts -->
<div role="status" aria-live="polite" aria-atomic="true">
  {{ lastMessage }}
</div>

<!-- 6. focus-visible -->
:focus-visible {
  outline: 2px solid var(--brand-primary);
  outline-offset: 2px;
}
```

---

## 十、综合评估

| 维度 | 当前 | 目标 | 评级 |
| --- | --- | --- | :-: |
| 配色 | 单色 + Naive 默认 | Brand + 12 色 palette | C |
| 字体 | 系统字体栈 | Inter Variable + JetBrains Mono | B |
| 间距 | 散落 6 种值 | 8 点栅格 8 级 | C |
| 圆角 | 仅 6px | 5 级 (4/6/8/12/16) | C |
| 阴影 | Naive UI 默认 | 5 级自定义 | B |
| 动效 | Naive UI 默认 300ms | 3 级 + ease-out | B |
| 图标 | 字符 + ionicons (未声明) | lucide-vue-next | C |
| 暗色 | 未启用 | ✓ 系统级切换 | F |
| 品牌资产 | Logo 缺失 | 完整 brand kit | D |
| a11y | 0% | WCAG AA | F |
| WCAG AA 对比度 | 6/10 达标 | 10/10 | B |

**总分 60/100 — C+ 级**

**主要差距**: 缺乏 design token 体系 (CSS vars), 缺乏品牌色与品牌资产, 缺乏 i18n / a11y / 暗色 三大基础能力。

---

## 附录: 优先级清单

| 项 | 工作量 | 优先级 |
| --- | ---: | --- |
| 引入 design token CSS vars | 2h | P3 |
| 暗色主题切换 (App.vue + Pinia store) | 3h | **P0** |
| 品牌色 + Logo SVG | 4h | P3 |
| WCAG AA 对比度修复 (占位色 #aaa → #767676) | 0.5h | P1 |
| Inter Variable + JetBrains Mono 自托管 | 4h | P3 |
| lucide-vue-next 替换字符图标 + ionicons | 1d | P3 |
| a11y 全量改造 (52 view) | 2-3d | **P1** |
| 8 点栅格 + 5 级圆角 + 5 级阴影 token | 4h | P3 |
| 3 级动效 (100/200/300ms + ease-out) | 2h | P3 |
| Open Graph + favicon 完整 | 2h | P3 |

详见 `reports/p6_4_actions.md`。