# P8-4: VisualEditor.vue 三次深度审查 (Vue Flow DAG Canvas)

> **Reviewer**: coder agent · 2026-06-26
> **Source**: `frontend-v2/src/views/workflow/VisualEditor.vue` (557 行)
> **Bundle**: `VisualEditor-*.js` 16.15 kB / gzip 6.33 kB (npm build 6.89s PASS)
> **依赖**: `@vue-flow/core`, `@vue-flow/background`, `@vue-flow/controls`, `@vue-flow/minimap`, `naive-ui`

---

## 一、文件结构总览

```
VisualEditor.vue (557L)
├── <template>     (159L, 3-column grid: marketplace | canvas | config)
├── <script setup> (368L, TypeScript)
│   ├── DAG CRUD state          (180-186)
│   ├── Operator marketplace    (188-209) + filtered computed
│   ├── Node config panel       (211-241)
│   ├── Right-click context menu (243-270)
│   ├── Drag-and-drop           (288-340)
│   ├── DAG CRUD operations     (343-419)
│   ├── Auto-layout client-side (421-450)
│   ├── Run monitor             (452-478)
│   └── localFallbackOps 200+   (480-527)
└── <style scoped> (26L, CSS)
```

---

## 二、三栏布局 (template L31-147)

```
┌──────────┬─────────────────────────┬──────────────┐
│ 算子市场 │     Vue Flow canvas     │   节点配置   │
│  (240px) │      (1fr, 弹性)        │   (320px)    │
│          │                         │              │
│ • search │  ┌─────────┐            │ 节点 ID      │
│ • cat    │  │ input ●─│            │ 类型 tag     │
│ • pills  │  │   │     │            │ 算子 ID      │
│   (200+) │  │ transform            │ 名称 input   │
│          │  │   │                 │ 参数 JSON    │
│ drag to  │  │   condition ◆       │ 错误策略     │
│ canvas   │  │  /  \                │ 超时        │
│          │  │ par_a  par_b         │ [保存][删除] │
│          │  │   \  /               │              │
│          │  │   output            │              │
│          │  └─────────┘            │              │
└──────────┴─────────────────────────┴──────────────┘
```

**优点**:
- ✅ 清晰 3-column grid (CSS grid-template-columns: 240px 1fr 320px)
- ✅ Vue Flow 默认组件 (Background + MiniMap + Controls) 全装
- ✅ fit-view-on-init 自动居中
- ✅ default-edge-options `smoothstep` 视觉清晰

---

## 三、Vue Flow 集成深度审查 (3 轮)

### 3.1 第 1 轮 — 基础功能

| 功能 | 实现 | 行号 | 评分 |
|------|------|------|------|
| Vue Flow canvas | ✅ | L65-77 | 🟢 A |
| Background pattern | ✅ | L74 | 🟢 A |
| MiniMap | ✅ | L75 | 🟢 A |
| Controls (zoom/fit) | ✅ | L76 | 🟢 A |
| v-model:nodes/edges | ✅ | L67-68 | 🟢 A |
| Node click → config panel | ✅ | L71, L272-275 | 🟢 A |
| Right-click context menu | ✅ | L72, L250-270 | 🟢 A |
| `default-edge-options` | ✅ | L70 | 🟢 A |
| Custom node types | ❌ | — | 🔴 **未注册** |

**🔴 关键发现 #1**: Vue Flow 使用默认 node 渲染,虽然 data 里有 `nodeType`,但没有 `nodeTypes` map 注册 7 种自定义节点 (input/transform/condition/loop/parallel/sub_workflow/output)。所有节点看起来一样,只靠 data 区分。

### 3.2 第 2 轮 — 拖拽 + 编辑

#### 3.2.1 Operator drag (L289-292)

```ts
function onOpDragStart(e: DragEvent, op: OperatorItem) {
  e.dataTransfer?.setData('application/x-op', JSON.stringify(op))
  e.dataTransfer!.effectAllowed = 'copy'
}
```

✅ MIME type 自定义 (`application/x-op`),可携带完整 op metadata

#### 3.2.2 Drop zone (L326-340)

```ts
function setupDropZone() {
  if (!canvasEl.value) return
  canvasEl.value.addEventListener('dragover', e => e.preventDefault())
  canvasEl.value.addEventListener('drop', e => {
    e.preventDefault()
    const raw = e.dataTransfer?.getData('application/x-op')
    // ...
    addOpAt(op, e.clientX - rect.left, e.clientY - rect.top)
  })
}
```

- ✅ dragover + drop 都 preventDefault
- ✅ 用 canvasEl.getBoundingClientRect() 转换坐标
- 🟡 drop 在 `canvasEl` (NCard) 而非 Vue Flow canvas 内部 — Vue Flow 有自己的 `onDrop` / `onDragOver` 钩子
- 🟡 onUnmounted 没清理 listener — **memory leak** (NodeJS garbage 会回收但理想是 removeEventListener)

#### 3.2.3 Double-click add (L294-296)

```ts
function onOpDoubleClick(op: OperatorItem) {
  addOpAt(op, 100 + nodes.value.length * 40, 100 + nodes.value.length * 30)
}
```

✅ 备用添加方式,位置自动递增

#### 3.2.4 Edge creation

🔴 **关键发现 #2**: **没有显式 edge creation 逻辑**。Vue Flow 默认支持在 node handle 之间拖拽创建 edge,但 VisualEditor 没:
- 写 `onConnect` handler
- 自定义 handle 类型 (`<Handle type="source" position="right" />`)
- 注册 7 种节点类型的自定义组件

→ 用户在两个 node handle 之间拖拽能创建 edge (Vue Flow 默认),但:
- 创建的 edge 没有 `edgeType` (data/control/error/retry)
- 没有 `condition` 表达式
- 没有 `sourceHandle` / `targetHandle` 命名

### 3.3 第 3 轮 — 持久化 + Run + 错误处理

#### 3.3.1 DAG CRUD (L367-419)

- ✅ listDAGs (L345)
- ✅ loadDag (L367-376): `getDAGVisual(id, 'LR')` → assign nodes + edges
- ✅ create DAG (L378-400): 走 `/dag` POST,**失败 fallback 到本地创建**
- 🟡 saveConfig (L223-226) **只 message.success,实际没 PATCH** 到 backend — 任务说 "保存到 DAG" 是假的

#### 3.3.2 Auto-layout (L402-450)

- ✅ server: `recomputeLayout(id, 'dagre', direction, true)` → 持久化 positions
- 🟡 client fallback: `autoLayoutClient()` (L421-450) — 简化 layered 算法,无 dagre 的 edge crossing 优化

#### 3.3.3 Run (L452-478)

- ✅ sync run: `runDAG(id, {}, 'manual', true)` → 阻塞返回完整 result
- 🟡 backend async 用 `BackgroundTasks` (routes.py:346),前端仍 sync 调
- 🔴 **runDAG sync=true** 在 6 节点 demo 0.85s,**100 节点 + 60s/节点 会导致 HTTP timeout** (uvicorn 默认 60s)
- 🟡 local simulated run (L455-465) — 没 backend 时 fallback,但 `local-${Date.now()}` 不是真实 run_id

#### 3.3.4 错误处理

```ts
catch (e: any) {
  error.value = e?.message || String(e)
}
```

- 🟡 axios error 经常 `e.message = "Network Error"`,无 response 显示
- 🟡 没有 retry / exponential backoff
- 🟡 没有 toast notification (只 NAlert)

---

## 四、Operator Marketplace (200+) 深度

### 4.1 Backend 真源 (L355-363)

```ts
try {
  const res = await listOperatorMarket()
  opCatalog.value = (res as any).items || res
  if (opCatalog.value.length < 50) {
    opCatalog.value = [...opCatalog.value, ...localFallbackOps()]
  }
} catch {
  opCatalog.value = localFallbackOps()
}
```

🔴 **关键发现 #3**: 当 backend 返回 < 50 op 时,**混入 synthetic ops**。localFallbackOps() (L481-527) 生成 14 类别 × 10 个 + 60 个 `synth.op-N`,共 200 个假 op,**与真实 marketplace 数据视觉无法区分**。

### 4.2 localFallbackOps (L481-527)

```ts
function localFallbackOps(): OperatorItem[] {
  const cats = [
    { cat: 'data-input', ... },
    { cat: 'data-output', ... },
    { cat: 'transform', ... },
    // 14 categories × 10 names = 140
  ]
  // pad to 200 with synthetic IDs
  while (out.length < 200 && pad < 100) {
    out.push({ id: `synth.op-${pad}`, name: `op-${pad}`, ... })
  }
}
```

🔴 **设计 smell**: 这是一个 "假装有 200 op" 的占位符,与 backend 的真实 200 op marketplace **冲突**。当 backend 实际返回 200 时,代码会绕过这个 fallback;但 fallback 仍存在作为占位 — P5 应彻底删除。

### 4.3 搜索 + 筛选 (L193-209)

```ts
const filteredOps = computed(() => {
  let list = opCatalog.value
  if (opSearch.value) {
    const kw = opSearch.value.toLowerCase()
    list = list.filter(o => o.name.toLowerCase().includes(kw) || ...)
  }
  if (opCategoryFilter.value) {
    list = list.filter(o => o.category === cat)
  }
  return list
})
```

- ✅ 搜索按 name/id/tags
- 🟡 客户端 substring,backend 已有 token-based inverted index (operators.py:605-610) 但未用
- 🟡 无 fuzzy / 拼音 / 缩写搜索

---

## 五、WebSocket 集成 — **未连接** (critical)

### 5.1 前端尝试连接

RunMonitor.vue:62:
```ts
const url = `${proto}://${location.host}/api/v1/workflow/dag/runs/ws`
const ws = new WebSocket(url)
```

### 5.2 Backend 实际提供

```bash
$ grep -n 'websocket\|WebSocket\|@router\.websocket' backend/services/workflow_service/dag_v2/routes.py
# (empty)
```

🔴 **关键发现 #4**: **`/api/v1/workflow/dag/runs/ws` endpoint 在 backend 不存在**。
- backend 只有 `editor_routes.py:565` 的 `/render/{rid}/ws` (render job,不是 DAG run)
- RunMonitor.vue 会在 `ws.onerror` 时 silent 退化到 `disconnected`,然后走 `setInterval(1500ms)` 轮询 `getRun()`
- 用户看到的 "WebSocket: connected" badge 永远不亮

### 5.3 进度推进 UI

- 🟡 VisualEditor 只在 `onRun()` 用 sync 调,无 live progress
- 🟡 RunMonitor 有 live progress 但靠 polling,非真 WS

---

## 六、缺失功能 (vs ComfyUI / Rete.js / 商业 DAG 编辑器)

### 6.1 ComfyUI 已实现,我们缺失

| 功能 | ComfyUI | VisualEditor | 严重度 |
|------|---------|--------------|--------|
| 自定义节点 UI (per type) | ✅ | ❌ | 🔴 高 |
| 撤销/重做 (Ctrl+Z/Y) | ✅ | ❌ | 🔴 高 |
| 实时预览 (sample at any node) | ✅ | ❌ | 🔴 高 |
| 子图 (group/nested subgraph) | ✅ | ❌ | 🟡 中 |
| 节点搜索 palette (Ctrl+P) | ✅ | 🟡 仅 marketplace | 🟡 中 |
| 节点复制/粘贴 | ✅ (Ctrl+C/V) | 🟡 仅 duplicate | 🟡 中 |
| 多选 + 批量操作 | ✅ | ❌ | 🟡 中 |
| Edge labels (in/out name) | ✅ | ❌ | 🟡 中 |
| Edge 表达式编辑 | ✅ | ❌ | 🟡 中 |
| 节点注释 / sticky note | ✅ | ❌ | 🟡 中 |
| 主题切换 (dark/light) | ✅ | 🟡 默认 naive-ui | 🟢 低 |
| Export PNG / SVG | ✅ | ❌ | 🟡 中 |
| Import / Export DAG JSON | ✅ | 🟡 import-flow endpoint 存在,前端没 UI | 🟡 中 |
| Mini-map 缩略图 | ✅ | ✅ | 🟢 ok |
| Group / Collapsible | ✅ | ❌ | 🟡 中 |

### 6.2 缺失 Top 5 — P5 必修

1. **撤销/重做 (Undo/Redo)** — 任何编辑器必备;需 history stack + Ctrl+Z/Y 绑定
2. **自定义节点类型** — 7 种 nodeType 视觉区分 (input 圆形 / output 圆形 / condition 菱形 / parallel 六边形 等)
3. **WebSocket DAG progress** — `POST /dag/runs/ws` 端点 (mirror `render/{rid}/ws`)
4. **Real-time preview** — 节点右侧抽屉显示 sample output (需 P5 真算子)
5. **Save node config to backend** — `saveConfig()` (L223) 实际不调 PATCH;加 `updateDAG(id, {nodes: ...})` 调用

---

## 七、代码质量

### 7.1 TypeScript 类型

```ts
const nodes = ref<any[]>([])  // 🔴 any!
const edges = ref<any[]>([])  // 🔴 any!
const configNode = ref<any | null>(null)  // 🔴 any!
```

🔴 关键位置用 `any[]`,运行时无类型保护;应:
```ts
import type { FlowNode, FlowEdge } from '@/api/workflow_v2'
const nodes = ref<FlowNode[]>([])
```

### 7.2 Naive UI 使用

- ✅ NCascader / NSelect / NInput / NInputNumber / NCard / NTag / NAlert / NScrollbar / NDropdown 全 named import
- ✅ useMessage (L176) 正确使用
- 🟡 `NEmpty` 描述中文混英文 (L83: "右键节点 → 配置 / 点击 运行 查看日志")

### 7.3 Vue 3 Composition API

- ✅ `<script setup lang="ts">`
- ✅ `ref`, `computed`, `onMounted`, `watch`
- 🟡 缺 `onUnmounted` 清理 dragover/drop listener + WebSocket

### 7.4 样式

```css
.editor-grid {
  display: grid;
  grid-template-columns: 240px 1fr 320px;
  gap: 12px;
  min-height: 640px;
}
.canvas-host { height: 640px; ... }
```

- 🟡 hard-coded 640px 高度 — 移动端/小屏不友好
- 🟡 缺 responsive (1024px 以下 stack 列)

---

## 八、安全

- 🟡 `window.prompt('新建 DAG 名称?', ...)` (L379) — XSS 风险低 (Naive UI 渲染 escape) 但 UX 差
- 🟡 `JSON.parse(raw)` try/catch OK,但 try 块内 `addOpAt(op, ...)` 不验证 op 字段
- 🟡 onDrop 坐标 `e.clientX - rect.left` 在 iframe / shadow DOM 中会错位
- 🟡 no CSRF token (axios 默认带 cookie 但 API 应验证 origin)

---

## 九、Performance

### 9.1 启动

- 3 个并发 API call: listDAGs + listOperatorMarket + setupDropZone
- 真实 build 后 16.15 kB / 6.33 kB gzip — 合理

### 9.2 运行时

- filteredOps computed 200+ op × substring search — O(n) per keystroke
- 🟡 大 marketplace (1000+) 会卡顿,需 debounce 或 server-side search

### 9.3 autoLayoutClient

```ts
function autoLayoutClient(direction: 'LR' | 'TB') {
  // simple layered: BFS + assign x = layer * step
}
```

- O(V+E),Python 等价在 server (`dagre_layout`),client 是 fallback
- 🟡 无 edge crossing 优化 (dagre.js 才有)

---

## 十、Reproducible

### 10.1 Build

```bash
$ cd frontend-v2 && npm run build
# VisualEditor-BZNEncAS.js  16.15 kB │ gzip: 6.33 kB
# ✓ built in 6.89s
```

### 10.2 Backend WS Gap Check

```bash
$ grep -n '@router.websocket' backend/services/workflow_service/dag_v2/routes.py
# (no output — gap confirmed)

$ grep -n '@router.websocket' backend/services/workflow_service/editor_routes.py
# 565:@router.websocket("/render/{rid}/ws")  (render job only, NOT DAG runs)
```

### 10.3 Drop Listener Leak Check

```ts
// Vue Flow uses Vue lifecycle, but addEventListener on canvasEl.value
// is NOT removed in onUnmounted (which doesn't exist in this file)
```

→ `mavis-trash` candidate for fix: add `onUnmounted` cleanup.

---

## 十一、三轮审查评级

| 维度 | 评级 | 备注 |
|------|------|------|
| Vue Flow 集成 | 🟢 B+ | 默认组件全装,但缺自定义 node 类型 |
| Drag-drop | 🟢 B+ | MIME + 坐标转换 OK,但 listener leak |
| Marketplace | 🟢 B | search + filter OK,但 localFallback 200 个假 op 污染 |
| Edge creation | 🟡 C | Vue Flow 默认,无 edgeType/condition |
| Undo/Redo | 🔴 D | 无 |
| Custom node UI | 🔴 D | 无 |
| WebSocket | 🔴 D | 前端连的 endpoint 不存在 |
| Auto-layout | 🟢 B+ | server dagre + client fallback |
| Save node config | 🔴 D | saveConfig() 假保存 |
| Real-time preview | 🔴 D | 无 |
| TS 类型 | 🟡 C | 多处 `any[]` |
| 错误处理 | 🟡 C | catch message 无 fallback |
| Responsive | 🟡 C | hard-coded 640px |
| 安全 | 🟡 B- | 无 CSRF 但 input validation OK |
| 性能 | 🟢 B+ | 16 kB gzip,200+ op filter OK |

**Overall**: 🟡 **C+ (6.5/10)** — Vue Flow 集成到位, **缺 5 大关键功能** (undo/redo, custom node, WS, preview, save)。**P5 必修** 这 5 项才能达到 ComfyUI 80% UX 水平。

---

## 十二、P5 修复路线图 (按 ROI)

### 立即修 (1-2h, P5 sprint 1)

1. 删 `localFallbackOps()` (VisualEditor.vue:481-527) — 后端真有 200 op,不需要兜底
2. 加 `onUnmounted` 清理 dragover/drop listener
3. `saveConfig()` 真正调用 `updateDAG(id, {nodes: ...})`
4. RunMonitor WebSocket URL 改成 fallback `/render/ws` 或加 backend `/dag/runs/ws` endpoint

### 中期 (P5 sprint 2, 半天)

5. 7 个自定义 Vue Flow node 组件 (InputNode / TransformNode / ConditionNode / ...)
6. 撤销/重做: history stack + Ctrl+Z/Y
7. 修复 TS 类型 (`any[]` → `FlowNode[]`)

### 长期 (P8+)

8. 子图 / group / sticky note
9. Export PNG/SVG (用 Vue Flow `toImage` 或 html2canvas)
10. Edge label 编辑 + condition 表达式
11. Multi-select + bulk delete
12. Real-time preview (每节点 mini thumbnail,需 P5 真算子)