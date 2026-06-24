# R6.5 Final Gate v2 — 架构真相 + 错位记录

**验收时间**: 2026-06-22 02:30 (Asia/Shanghai)
**plan**: R6.5 plan_f798b424 (cancel 2026-06-20 23:33)
**最终评估**: 🔴 **FAIL (架构错位 100% — Vue 3 SPA 无法接入实际项目)**

---

## 一、架构真相 (P1-B1 W1+W2 主动验证后发现)

### 1.1 nanobot-factory 真实前端架构
**主前端目录**: `D:\Hermes\生产平台\nanobot-factory\backend\imdf\frontend\`

**架构栈**:
- **Electron + Vite + React + xyflow + TypeScript**
  - 来自 `package.json`: `name: "imdf-canvas-frontend"`, `keywords: ["react", "xyflow", "electron", "vite"]`
  - `vite.config.ts` 存在
  - `tsconfig.json` + `tsconfig.nodes.json` 存在
  - `npm run build` 走 `tsc -b && vite build`
- **实际页面写法**: vanilla JS + HTML 模板字符串(`onclick` 直接绑定函数)
  - 35+ 页面在 `js/pages/` (dashboard/canvas/business/audit-logs/transfer-center/model-manager 等)
  - `index.html:151` 有 `<script src="/js/app.js">` 入口
- **T8mars/T8-penguin-canvas** 项目 (README 写明是 React-flow 节点编辑器)

### 1.2 R6.5 错位
- R6.5 plan prompt 假设前端是 **Vue 3 + Element Plus CDN** 项目
- 写了 25 文件 Vue 3 SPA 到 `frontend/` 目录
- **实际项目是 React + Vite**,不是 Vue 3
- R6.5 产物无法迁移到实际前端(架构不兼容)

### 1.3 错位证据
| 项 | R6.5 plan 假设 | 项目实际 |
|---|--------------|---------|
| 前端框架 | Vue 3 + Element Plus | **React + Vite + xyflow** |
| 状态管理 | Pinia | **vanilla JS 全局变量** |
| 路由 | Vue Router 4 | **多页面 + hash anchor** |
| 主前端目录 | `frontend/` | **`backend/imdf/frontend/`** |
| 页面写法 | `.vue` SFC | **`.js` 模板字符串** |

### 1.4 R6.5 产物状态
- 25 个文件在 `D:\Hermes\生产平台\nanobot-factory\frontend\`
- **未接入主应用**(没有任何地方 import 它)
- 主应用 `backend/imdf/frontend/index.html` 没引用 R6.5 SPA
- `js/app.js` (R6.5) 与 `backend/imdf/frontend/js/app.js` (实际) 路径冲突

---

## 二、修复方案 (3 选项)

### 选项 A — 废弃 R6.5 产物 (推荐)
**理由**: R6.5 Vue 3 SPA 与项目 React + Vite 架构不兼容,迁移成本高且破坏主应用。
**操作**:
- 删除或归档 `frontend/` 目录
- 标记 R6.5 为"架构探索实验",不计入生产交付
- 真实前端 = `backend/imdf/frontend/` 已有 35+ 完整页面

### 选项 B — 改造 R6.5 SPA 为 React
**理由**: R6.5 的 RBAC + 三态 + a11y + i18n 设计有商业价值
**操作**:
- 把 R6.5 4 三态组件重写为 React 组件 (`.jsx`)
- RBAC + a11y + i18n 改用 React hooks (useContext / useReducer)
- 集成到 `backend/imdf/frontend/src/components/`
**代价**: 2-3 天重写

### 选项 C — 双前端并存
**理由**: 让 Vue 3 SPA 作为 alt 入口(如 admin 控制台)
**操作**:
- 把 R6.5 改造为独立部署 (vite.config 改端口)
- 与 React SPA 并存
**代价**: 部署复杂度 +2,运维成本 +50%

---

## 三、当前交付物修正

### 3.1 R6.5 实际贡献
- ❌ 0 页面接入主应用
- ✅ RBAC 矩阵 (26 actions × 6 roles) — 设计可参考
- ✅ 三态组件设计 (loading/empty/error/async) — 设计可参考
- ✅ a11y 配色 (5.91-15.56 对比度) — 可复用
- ✅ 80 i18n key (zh-CN/en-US) — 可参考

### 3.2 P1-B1 W1+W2 实际产出 (在正确路径)
- `backend/imdf/frontend/js/pages/audit-logs.js` (445 行)
- `backend/imdf/frontend/js/pages/transfer-center.js` (608 行)
- `backend/imdf/frontend/js/pages/model-manager.js` (735 行)
- 这 3 个页面**真的接入主前端**(`index.html:151` 已有 script tag)

---

## 四、给用户的状态

**R6.5 真相**:plan prompt 假设错误(Vue 3),项目实际是 React + Vite。R6.5 25 文件未接入主应用。

**修复方向**:
- **选项 A (推荐)**: 废弃 R6.5,改用 `backend/imdf/frontend/` 已有的 35+ 完整 vanilla JS 页面
- **选项 B**: 把 R6.5 三态+RBAC+ i18n 重写为 React 组件 (2-3 天)
- **选项 C**: 双前端并存 (运维成本高)

---

**R6.5 终判 v2: FAIL — 架构错位 100% (Vue 3 → React), 25 文件未接入. R6.5 RBAC/a11y/i18n 设计可参考复用,需要按实际 React 架构重写.**