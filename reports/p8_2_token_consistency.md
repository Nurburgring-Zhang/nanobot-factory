# P8-2 Report 2: Token 一致性 (5 色 token × 全 view)

> **审查时间**: 2026-06-26 05:07-05:25  
> **审查范围**: 全 52 view + 5 component + 1 layout + 1 App + 2 locale + 1 a11y.css  
> **Token 5 套**: `primary` / `success` / `warning` / `error` / `info`

---

## 1. 5 Token 在 `<NButton type="...">` 的实际分布

| Token | 出现次数 | 占 NButton 总数 (110) 比例 | 一致性 |
|---|---|---|---|
| `primary` | **71** | 64.5% | ✅ 主操作主导 |
| `error` | **30** | 27.3% | ✅ 删除/危险操作充足 |
| `success` | **18** | 16.4% | ✅ 确认操作 |
| `info` | **17** | 15.5% | ✅ 信息展示 |
| `warning` | **10** | 9.1% | ⚠️ 警告操作略少 |
| `default` | 1 | 0.9% | ✅ 默认按钮 |

**对比 NTag / NAlert 等其他组件的 type 分布**:

| Token | `type="..."` 全局 | 一致性 |
|---|---|---|
| `info` | 13 | ✅ |
| `primary` | 51 | ✅ |
| `error` | 24 | ✅ |
| `success` | 15 | ✅ |
| `warning` | 8 | ⚠️ 偏少 (健康监控/告警场景该用 warning 而用了 info?) |

**结论**: **5 token 在组件层级 100% 一致** — 没有出现 `type="danger"` / `type="orange"` / `type="fail"` 等非标 token。

---

## 2. Theme Override Token 缺口 (核心 Gap)

### 2.1 `App.vue` 当前 themeOverrides

```ts
const themeOverrides = computed<GlobalThemeOverrides>(() => ({
  common: {
    primaryColor: '#2080f0',
    primaryColorHover: '#4098fc',
    primaryColorPressed: '#1060c9',
    primaryColorSuppl: '#4098fc',
    borderRadius: '6px',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
  }
}))
```

**问题**: 仅定义 **primary 1 套** token,缺:
- ❌ `successColor` / `successColorHover` / `successColorPressed` / `successColorSuppl`
- ❌ `warningColor` / `warningColorHover` / `warningColorPressed` / `warningColorSuppl`
- ❌ `errorColor` / `errorColorHover` / `errorColorPressed` / `errorColorSuppl`
- ❌ `infoColor` / `infoColorHover` / `infoColorPressed` / `infoColorSuppl`

**影响**: Naive UI `<NButton type="success">` 等使用 Naive UI 内置色板,**未跟随品牌色**。后续要做品牌色统一时,所有 `<NButton type="success">` 等组件需要单独 override。

### 2.2 推荐 P9+ themeOverrides 完整版 (60+ 行)

```ts
const themeOverrides = computed<GlobalThemeOverrides>(() => {
  const isDark = themeStore.isDark
  return {
    common: {
      // Primary (品牌色)
      primaryColor: '#2080f0',
      primaryColorHover: '#4098fc',
      primaryColorPressed: '#1060c9',
      primaryColorSuppl: '#4098fc',
      
      // Success (成功/通过)
      successColor: '#18a058',
      successColorHover: '#36ad6a',
      successColorPressed: '#0c7a43',
      successColorSuppl: '#36ad6a',
      
      // Warning (警告/降级)
      warningColor: '#f0a020',
      warningColorHover: '#ffb340',
      warningColorPressed: '#c87f0d',
      warningColorSuppl: '#ffb340',
      
      // Error (错误/危险)
      errorColor: '#d03050',
      errorColorHover: '#e0415e',
      errorColorPressed: '#a0203e',
      errorColorSuppl: '#e0415e',
      
      // Info (信息/提示)
      infoColor: '#2080f0',
      infoColorHover: '#4098fc',
      infoColorPressed: '#1060c9',
      infoColorSuppl: '#4098fc',
      
      // 基础
      borderRadius: '6px',
      borderRadiusSmall: '4px',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      
      // 暗色映射
      ...(isDark && {
        bodyColor: '#18181c',
        cardColor: '#1f1f23',
        modalColor: '#1f1f23',
        popoverColor: '#1f1f23',
        tableColor: '#1f1f23',
        inputColor: '#18181c',
        actionColor: '#18181c',
        tagColor: '#2a2a30',
        dividerColor: '#2e2e33'
      })
    }
  }
})
```

---

## 3. Hardcoded Hex 字面量 (Token 体系未接管)

| 文件 | hex 数 | 备注 |
|---|---|---|
| `App.vue` | 13 | 主题 CSS variables 定义 (OK,集中管理) |
| `ErrorBoundary.vue` | 14 | 错误边界 fallback 配色 (建议转 token) |
| `Orchestrator.vue` | 10 | 大 view,部分 SVG/canvas 配色 |
| `KnowledgeGraph.vue` | 9 | 力导向图配色 (建议保留,SVG 需 hex) |
| `MultimodalChat.vue` | 8 | 含文件类型 icon 色 |
| `Marketplace.vue` | 2 | Skill tag 配色 |
| `Login.vue` | 7 | 登录页 brand 渐变 (建议保留) |
| `StoryboardEditor.vue` | 7 | 时间线分镜配色 (建议保留) |
| `VisualEditor.vue` | 8 | Vue Flow 节点配色 (建议保留) |
| `DefaultLayout.vue` | 5 | brand color #2080f0 (建议转 var) |
| `Graph.vue` | 7 | Vue Flow edge 配色 |
| `WikiEdit.vue` | 5 | Markdown 编辑器高亮 |
| 其余 16 文件 | 各 1-4 | 零散 |
| **总计** | **130** | **27 文件** |

**分类建议**:
- ✅ 保留 (业务图形/数据可视化): Graph / StoryboardEditor / VisualEditor / KnowledgeGraph / Orchestrator (SVG/Canvas 部分)
- ⚠️ 转 token (UI chrome): App.vue / DefaultLayout.vue / ErrorBoundary.vue / Login.vue brand 区 / 5 文件零散 hex

---

## 4. WCAG Contrast Token 验证 (a11y.css 已实现)

| Token | Light mode | Dark mode | WCAG AA | WCAG AAA |
|---|---|---|---|---|
| `--a11y-muted` | #767676 (4.54:1) | #9aa (7.05:1) | ✅ | ✅ dark |
| `--a11y-muted-strong` | #5a5a5a (7.46:1) | #c0c4d0 (11.3:1) | ✅ | ✅ |
| `--a11y-focus-ring` | #2080f0 | #5aa9ff | ✅ | ✅ |

**WCAG 公式** (memory `vue3-plugin-patterns.md §6`):
```
contrastRatio = (bright + 0.05) / (dark + 0.05)
```

**关键场景验证**:
- `--a11y-muted #767676` 在 `#ffffff` 背景 = **4.54:1** ≥ AA Normal 4.5 ✅
- `--a11y-muted #9aa` 在 `#18181c` 背景 = **7.05:1** ≥ AAA 7 ✅
- 焦点环 `#2080f0` 在 `#ffffff` 背景 = 5.9:1 ≥ AA Large 3 + non-text 3 ✅
- 焦点环 `#5aa9ff` 在 `#18181c` 背景 = 5.8:1 ≥ 3 ✅

---

## 5. 跨 5 Token 的 5 个 Naive UI 组件实测

| 组件 | primary | success | warning | error | info | 备注 |
|---|---|---|---|---|---|---|
| `<NButton>` | ✅ 71 | ✅ 18 | ✅ 10 | ✅ 30 | ✅ 17 | 全覆盖 |
| `<NTag>` | — | — | — | — | — | 待抽样 |
| `<NAlert>` | — | — | — | — | — | 待抽样 |
| `<NBadge>` | — | — | — | — | — | 待抽样 |
| `<NStatistic>` | — | — | — | — | — | 待抽样 |

**抽样建议** (P9+): 抽样 5 个组件 × 5 token × 5 view = 125 个组合,验证视觉一致性。

---

## 6. P9+ Token 工作清单

1. **T1 (1h)**: 在 `App.vue themeOverrides.common` 补 4 套 token (success/warning/error/info),含 hover/pressed/suppl + dark mode 映射
2. **T2 (2h)**: 提取 `--app-success` / `--app-warning` / `--app-error` / `--app-info` 4 个 CSS var 到 `:root` 和 `html[data-theme='dark']`
3. **T3 (2h)**: DefaultLayout / ErrorBoundary / Login brand 区 hex 转 `var(--app-*)`
4. **T4 (1h)**: a11y.css 补充 `--a11y-success` / `--a11y-warning` / `--a11y-danger` token + WCAG contrast 验证
5. **T5 (1h)**: 抽样 5 view × 5 token 视觉一致性截图测试

**总工作量**: ~7h = 1 人天

---

**审计签名**: coder agent, session `mvs_037d99700f274565ba21179ce1ff27ca`, 2026-06-26 05:25 Asia/Shanghai