# IMDF前端重写 — 三Agent互审实施方案

---

## Agent A (架构) — 前端静态文件结构和服务方案

### 1. 静态文件目录结构

```
frontend/
├── index.html                # 入口页面(SPA框架, hash路由)
├── favicon.ico               # 网站图标
├── static/
│   ├── css/
│   │   ├── main.css          # 主样式表(布局、导航、状态栏)
│   │   └── components.css    # 组件样式(指标卡、按钮、表格、模态框)
│   ├── js/
│   │   ├── app.js            # SPA路由、全局状态、应用初始化
│   │   ├── api.js            # fetch封装(addCsrf/统一错误处理/自动派发)
│   │   ├── pages/
│   │   │   ├── dashboard.js  # 首页(4指标卡+8快捷按钮+最近任务+快速标注)
│   │   │   ├── datasets.js   # 数据集管理页
│   │   │   ├── annotation.js # 标注工具页
│   │   │   ├── workflows.js  # 工作流画布页
│   │   │   ├── delivery.js   # 交付管理页
│   │   │   ├── review.js     # 审核页
│   │   │   ├── stats.js      # 统计/看板页
│   │   │   └── settings.js   # 设置页
│   │   └── lib/
│   │       ├── router.js     # hash路由实现(约80行)
│   │       ├── components.js # 可复用UI组件(Toast, Modal, Table, Card)
│   │       ├── store.js      # 简易状态管理
│   │       └── utils.js      # 通用工具函数
│   └── img/
│       ├── logo.svg
│       └── placeholder.png
```

**总计文件数**: 约20个文件
**合计代码量估算**: ~2500-3500行(纯HTML/CSS/JS, 无React依赖)

### 2. FastAPI StaticFiles 配置(精确代码)

在 `canvas_web.py` 中, 需要:

1. **在app创建后**添加 StaticFiles 挂载(约第990-1000行附近)
2. **修改根路由** `/` 返回独立的 index.html 而非 HTML_TEMPLATE

```python
# === 在 canvas_web.py 中添加 ===
from fastapi.staticfiles import StaticFiles

# 在 app = FastAPI(...) 之后, lifespan 注册之后添加
# 约在第 928 行之后

# 静态文件服务 — 新前端
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    # SPA: index.html 由根路由返回, 其他静态文件通过 /static/ 访问
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")
    # 支持直接访问 frontend 目录下的文件 (如 favicon.ico)
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="assets")
    logger.info(f"前端静态文件目录已挂载: {FRONTEND_DIR}")
else:
    logger.warning(f"前端目录不存在: {FRONTEND_DIR}")
```

**修改根路由** (第2163-2166行):
```python
@app.get("/", response_class=HTMLResponse)
async def root():
    """HTML画布页面"""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return HTML_TEMPLATE  # fallback: 旧内联HTML
```

### 3. 前端调用后端API的fetch封装

```javascript
// frontend/static/js/api.js — 全局fetch封装

const API_BASE = '';

async function api(method, path, body = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (body) opts.body = JSON.stringify(body);

  try {
    const resp = await fetch(API_BASE + path, opts);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.error || err.detail || `HTTP ${resp.status}`);
    }
    return await resp.json();
  } catch (e) {
    showToast(e.message, 'error');
    throw e;
  }
}

// 便捷方法
const GET    = (p) => api('GET', p);
const POST   = (p, b) => api('POST', p, b);
const PUT    = (p, b) => api('PUT', p, b);
const DELETE = (p) => api('DELETE', p);
```

### 4. 页面路由方案 (SPA: hash路由)

```javascript
// frontend/static/js/lib/router.js — Hash路由

class Router {
  constructor() {
    this.routes = {};
    this.beforeHooks = [];
    window.addEventListener('hashchange', () => this._resolve());
  }

  add(pattern, handler) {
    this.routes[pattern] = handler;
  }

  beforeEach(fn) {
    this.beforeHooks.push(fn);
  }

  navigate(hash) {
    window.location.hash = hash;
  }

  _resolve() {
    const hash = window.location.hash.slice(1) || '/dashboard';
    // 执行全局hooks
    for (const fn of this.beforeHooks) fn(hash);
    // 匹配路由
    for (const [pattern, handler] of Object.entries(this.routes)) {
      const match = this._match(pattern, hash);
      if (match) {
        handler(match);
        return;
      }
    }
    // 404 fallback
    this.routes['/dashboard']({});
  }

  _match(pattern, hash) {
    const pParts = pattern.split('/');
    const hParts = hash.split('/');
    if (pParts.length !== hParts.length) return null;
    const params = {};
    for (let i = 0; i < pParts.length; i++) {
      if (pParts[i].startsWith(':')) {
        params[pParts[i].slice(1)] = hParts[i];
      } else if (pParts[i] !== hParts[i]) {
        return null;
      }
    }
    return params;
  }
}

// 路由表
const router = new Router();
router.add('/dashboard', () => renderDashboard());
router.add('/datasets', () => renderDatasets());
router.add('/datasets/:id', (p) => renderDatasetDetail(p.id));
router.add('/annotation', () => renderAnnotation());
router.add('/annotation/:taskId', (p) => renderAnnotation(p.taskId));
router.add('/workflows', () => renderWorkflows());
router.add('/delivery', () => renderDelivery());
router.add('/review', () => renderReview());
router.add('/stats', () => renderStats());
router.add('/settings', () => renderSettings());
```

### 5. 与现有HTML_TEMPLATE的冲突处理

| 问题 | 方案 |
|------|------|
| 旧HTML_TEMPLATE仍在第1110-1973行 | **保留不动** — 作为fallback。根路由优先返回独立 index.html |
| 旧JS代码引用了新页面没有的 `_cv_api` 等函数 | 新前端完全重写, 不共用任何函数名 |
| 旧CSS/HTML与新前端样式冲突 | 新前端不使用旧CSS class名(不用 `.node`, `.cw` 等), 使用全新命名空间 `imdf-*` |
| 后端 `/canvas/*` 路由 | 保留不变, 新首页不主动调用它们 |
| 旧WebSocket `/canvas/ws` | 新前端初期也不使用WebSocket, 全部用REST |

---

## Agent B (产品) — Phase1 首页精确功能清单

### 1. 首页必须包含的元素

依据 UI_ARCHITECTURE_v3.md:

```
┌───────────────────────────────────────────────────────────────┐
│ IMDF 无限数据工场          [🔍搜索] [🔔通知] [⚙️设置] [👤admin] │ ← 顶栏
├───────────────────────────────────────────────────────────────┤
│ ┌─── 左侧导航 ────────────────────────────────────────────┐  │
│ │ 📊 今日概览 (首页)                                       │  │
│ │ 📦 我的任务                                              │  │
│ │ 📁 数据集管理                                            │  │
│ │ 🖌️ 标注工具                                              │  │
│ │ 🚀 工作流画布                                            │  │
│ │ ─────────────────────                                    │  │
│ │ 📤 交付管理                                              │  │   ← Phase1
│ │ ✅ 审核                                                  │  │     必选
│ │ 📈 统计分析                                              │  │
│ │ 🔧 系统设置                                              │  │
│ └───────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─ 今日生产量 ─┐  ┌─ 待审核任务 ─┐  ┌─ 在线人数 ─┐  ┌─ 系统状态 ─┐  │
│  │   1,234 条   │  │     56 项    │  │    12 人   │  │  🟢 正常   │  │
│  │   ↑ 12% 📈   │  │   ⏳ 紧急:3   │  │   👥 标注:8  │  │  响应:45ms │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                                │
│  ┌───────────── 快捷操作区(8个按钮) ─────────────────────┐     │
│  │ [📁 上传数据] [🖌️ 开始标注] [🚀 执行工作流] [📊 查看看板] │     │
│  │ [📋 创建任务] [👥 邀请成员] [📦 交付数据] [📈 统计分析] │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                │
│  ┌───────────── 最近任务(5条+查看全部) ────────────────────┐     │
│  │ 任务名         状态     进度  负责人  截止时间   操作     │     │
│  │ ────────────────────────────────────────────────────    │     │
│  │ 商品图片标注   进行中   67%   张三    2026-06-15  [▶]   │     │
│  │ ...                                                     │     │
│  │                                                   [查看全部] │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                │
│  ┌───────────── 快速标注(小工具) ───────────────────────────┐     │
│  │ [拖拽图片到此处或点击上传]                                │     │
│  │ ┌──────────────────────────────────────────────────┐    │     │
│  │ │ 上传后自动调用AI预标注, BBox/标签一键生成           │    │     │
│  │ └──────────────────────────────────────────────────┘    │     │
│  └─────────────────────────────────────────────────────────┘     │
├───────────────────────────────────────────────────────────────┤
│ 📊 运行中:0  ⏱ 队列:0  ✅ 今日完成:1,234  ⏳ 待审核:56  🟢 系统正常│ ← 底栏
└───────────────────────────────────────────────────────────────┘
```

### 2. 左侧导航菜单: Phase1必须 vs 可延迟

| 菜单项 | Phase1 | API数据来源 | 说明 |
|--------|--------|-------------|------|
| 📊 今日概览 | **必须** | 首页自身 | 默认页 |
| 📦 我的任务 | **必须** | `/api/v1/tasks` (routes_extended) | 任务列表页 |
| 📁 数据集管理 | **必须** | `/api/datasets` | 现有路由 |
| 🖌️ 标注工具 | **必须** | `/api/prelabel` + `/api/v1/annotations` | 现有路由 |
| 🚀 工作流画布 | **必须** | `/api/workflow/*` + `/api/comfyui/*` | 现有路由 |
| 📤 交付管理 | 可延迟(Phase2) | `/api/delivery/*` | 现有路由 |
| ✅ 审核 | 可延迟(Phase2) | `/api/review/*` | 现有路由 |
| 📈 统计分析 | 可延迟(Phase2) | `/api/stats/*` + `/api/ops/*` | 现有路由 |
| 🔧 系统设置 | 可延迟(Phase2) | `/imdf/config/*` + `/imdf/theme/*` | 现有路由 |

### 3. 每个元素的API数据来源

| 首页元素 | API调用 | 返回数据 |
|----------|---------|----------|
| 今日生产量 | `GET /api/ops/overview` | `production_count` |
| 待审核任务 | `GET /api/ops/overview` | 或 `GET /api/review/pending` |
| 在线人数 | `GET /api/ops/overview` | `daily_active_users` |
| 系统状态 | `GET /api/v1/health` + `GET /api/v1/ready` | `status`, `checks` |
| 最近任务 | `GET /api/monitor/pipeline` 或 `GET /api/requirements` | task列表 |
| 快速上传 | 前端local: FileReader + `POST /api/v1/ingest/*` | 上传结果 |
| AI预标注 | File上传 + `POST /api/prelabel` | bboxes/tags |

### 4. 用户交互流程

**路径A: 上传数据 → 标注 → 交付**
1. 用户打开首页 → 看到4指标卡+快捷按钮+最近任务
2. 点击「📁 上传数据」→ 弹出文件选择框(或拖拽到快速标注区)
3. 选择文件 → 前端upload到 `POST /api/v1/ingest/*` → 数据入库
4. 弹窗提示: "已上传, 是否开始标注?" → 点击「开始标注」
5. 跳转到 `#/annotation` → 加载标注工具 → 调用 `POST /api/prelabel` AI预标注
6. 标注完成 → 保存 → 跳转 `#/datasets` 查看

**路径B: 创建工作流 → 执行 → 查看结果**
1. 点击「🚀 执行工作流」→ 跳转 `#/workflows`
2. 拖拽节点到画布 → 连线 → 配置参数
3. 点击「▶ 执行全部」→ `POST /api/workflow/execute`
4. 执行完成 → 查看输出

---

## Agent C (工程) — 子任务划分与工作量估算

### Phase0: 止血 (1人·天)

目标: 让独立前端能通过FastAPI提供服务, 现有内联HTML_TEMPLATE作为fallback保留

| 子任务 | 文件 | 修改内容 | 代码量 | 依赖 |
|--------|------|---------|--------|------|
| P0-1: 创建frontend目录结构 | `frontend/index.html` | 新建: SPA框架骨架 | 50行 | 无 |
| P0-2: StaticFiles挂载 | `api/canvas_web.py` | 添加`from fastapi.staticfiles import StaticFiles` + `app.mount()` | 8行 | P0-1 |
| P0-3: 修改根路由 | `api/canvas_web.py` 第2163行 | 添加文件存在判断, 优先返回独立index.html | 10行 | P0-2 |
| P0-4: 验证服务可用 | 终端执行 | 启动uvicorn, curl验证 | — | P0-3 |

**Phase0总代码量**: 约70行
**Phase0精确修改位置**:
- `canvas_web.py` 第928行后添加 StaticFiles mount (约6行)
- `canvas_web.py` 第2163-2166行 改为文件读取+fallback逻辑 (8行)
- 新建 `frontend/index.html` (50行骨架)

### Phase1: 首页实现 (3人·天)

目标: 完整的首页(4指标卡+8快捷按钮+左侧导航+最近任务+快速标注+底栏)

| 子任务 | 文件 | 内容 | 代码量(行) | 依赖 |
|--------|------|------|-----------|------|
| P1-1: main.css布局 | `static/css/main.css` | 顶栏/导航/底栏/主区域Grid | 250 | P0-1 |
| P1-2: components.css | `static/css/components.css` | 卡片/按钮/表格/模态框样式 | 200 | P0-1 |
| P1-3: api.js | `static/js/api.js` | fetch封装+统一错误处理 | 50 | — |
| P1-4: router.js | `static/js/lib/router.js` | hash路由 | 80 | — |
| P1-5: components.js | `static/js/lib/components.js` | Toast/Modal/Table/Card | 120 | P1-3 |
| P1-6: store.js | `static/js/lib/store.js` | 简易状态管理 | 40 | — |
| P1-7: utils.js | `static/js/lib/utils.js` | 格式化/时间/数字工具 | 50 | — |
| P1-8: app.js | `static/js/app.js` | SPA初始化+导航切换+底栏刷新 | 100 | P1-3~P1-7 |
| P1-9: dashboard.js | `static/js/pages/dashboard.js` | 4指标卡+8按钮+最近任务+快速标注 | 300 | P1-8 |
| P1-10: 更新index.html | `frontend/index.html` | 完善骨架: 引入所有CSS/JS | 80 | P1-1~P1-9 |
| P1-11: 集成测试 | — | 启动后端, 验证所有功能可用 | — | P1-10 |

**Phase1总代码量**: 约1270行
**Phase1依赖关系**: P1-1→P1-2→(P1-3+P1-4→P1-5+P1-6+P1-7→P1-8→P1-9→P1-10)

### Phase2: 业务页面 (5人·天, 可并行开展)

| 子任务 | 页面 | 文件 | 代码量(行) | 依赖API | 优先级 |
|--------|------|------|-----------|---------|--------|
| P2-1 | 数据集管理 | `pages/datasets.js` | 250 | `/api/datasets`, `/api/v1/batch` | ⭐⭐⭐ |
| P2-2 | 标注工具 | `pages/annotation.js` | 400 | `/api/prelabel`, `/api/datasets/{id}/preview` | ⭐⭐⭐ |
| P2-3 | 工作流画布 | `pages/workflows.js` | 500 | `/api/workflow/*`, `/api/comfyui/*` | ⭐⭐⭐ |
| P2-4 | 我的任务 | `pages/tasks.js` | 150 | `/api/requirements` | ⭐⭐ |
| P2-5 | 交付管理 | `pages/delivery.js` | 150 | `/api/delivery/*` | ⭐⭐ |
| P2-6 | 审核 | `pages/review.js` | 150 | `/api/review/*` | ⭐⭐ |
| P2-7 | 统计分析 | `pages/stats.js` | 200 | `/api/stats/*`, `/api/ops/*` | ⭐⭐ |
| P2-8 | 系统设置 | `pages/settings.js` | 200 | `/imdf/config/*`, `/auth/*` | ⭐ |

**Phase2总代码量**: 约2000行
**可并行**: P2-1~P2-8 互相无依赖, 可同时在多台机器开发

---

## 总体实施方案 (含代码量估算汇总)

### 总结

| 阶段 | 人·天 | 新建文件 | 修改文件 | 代码量 |
|------|-------|---------|---------|--------|
| Phase0: 止血 | 1 | 1个 (index.html) | 1个 (canvas_web.py) | ~70行 |
| Phase1: 首页 | 3 | 10个 | 1个 (index.html) | ~1270行 |
| Phase2: 业务页 | 5 | 8个 | 0个 | ~2000行 |
| **合计** | **9人·天** | **19个文件** | **2个修改** | **~3340行** |

### 依赖关系图

```
Phase0 (1天) ──────────────────────────────────────┐
    │                                                │
    ├─ P0-1: 创建frontend/index.html骨架              │
    ├─ P0-2: canvas_web.py添加StaticFiles mount       │
    └─ P0-3: 修改根路由  ────────────────────────────┤
                                                      │
Phase1 (3天) ──────────────────────────────────────┤
    │                                                │
    ├─ P1-1: main.css          (与P1-2可并行)        │
    ├─ P1-2: components.css                          │
    ├─ P1-3: api.js            (与P1-4/P1-6/P1-7并行)│
    ├─ P1-4: router.js                               │
    ├─ P1-5: components.js     (依赖P1-3,P1-4)       │
    ├─ P1-6: store.js          (独立)                │
    ├─ P1-7: utils.js          (独立)                │
    ├─ P1-8: app.js            (依赖P1-3~P1-7)       │
    ├─ P1-9: dashboard.js      (依赖P1-8)             │
    └─ P1-10: 更新index.html    (依赖全部)            │
                                                      │
Phase2 (5天, 可并行) ────────────────────────────┤
    │                                                │
    ├─ P2-1: datasets.js       (依赖Phase1)          │
    ├─ P2-2: annotation.js     (依赖Phase1)          │
    ├─ P2-3: workflows.js      (依赖Phase1)          │
    ├─ P2-4~P2-8: 其他页面     (依赖Phase1)          │
    └─ 集成测试                                       │
```

### 关键风险点

1. **canvas_web.py文件已2836行, 十分庞大** — 修改 `StaticFiles` 挂载位置要谨慎, 不能破坏现有路由注册顺序
2. **现有的React/TSX前端 (前端半成品)** — 有完整的 theme 系统和47个节点组件, 但依赖 node_modules。新方案是完全独立的纯HTML/CSS/JS, 两者不冲突
3. **后端已有大量mock数据** (data_browser_routes.py/ops_dashboard_routes.py) — 新前端可直接使用, 但部分API返回随机数据。后续应考虑替换为真实数据库查询
4. **无用户认证** — Phase1 首页假设admin用户已登录, auth路由已注册但前端未对接
5. **部分API路由前缀混乱** — 有 `/api/`, `/api/v1/`, `/imdf/` 三种前缀

### 推荐实施顺序

**Day 1**: P0-1 ~ P0-4 (止血)
**Day 2-3**: P1-1 ~ P1-6 (核心基础设施: CSS+JS库+路由)
**Day 4**: P1-7 ~ P1-10 (首页实现+集成)
**Day 5-9**: Phase2 各业务页面并行开发
