# P1-C-W2 报告 — 5 业务页 API 集成 (Attempt 2)

> **Status**: 完成 (vs Attempt 1 主动 abort, Attempt 2 经 verifier 反馈后实际落地代码)
> **Date**: 2026-06-22 03:00+ Asia/Shanghai
> **Worker**: coder / p1_c-w2-business-pages

## 1. 概览

按 verifier feedback (Attempt 1) 要求,本任务在 Attempt 2 中实际落地代码:
- 新建 `js/client.js`(三态 + i18n + RBAC + CSRF + Bearer 注入)
- 新建 `js/utils/error.js`(错误描述 / 列表解析 / RBAC 注入)
- 新建 `js/pages/tasks.js`(覆盖 business.js 中的 renderTasks/loadTasks,使用新的 `/api/tasks/*` 端点)
- 重构 4 个业务页 (`template-market` / `datasets` / `eval-review` / `pipeline`) 的所有 `apiGet/apiPost/apiDelete` 调用为 `httpGet/httpPost/httpDelete` 三态包装
- 在 `index.html` 中按依赖顺序挂载新脚本

所有 7 个 JS 文件均通过 `node --check` 语法验证。

## 2. 端点集成清单 (per page)

### tasks.js (新建)
| 端点 | 方法 | 实现 |
|------|------|------|
| `/api/tasks?page=&status=&assignee=` | GET | `loadTasks()` (line ~110) |
| `/api/tasks` | POST | `TASKS_create()` (line ~213) |
| `/api/tasks/{id}/assign` | POST | `TASKS_assign()` (line ~225) |
| `/api/tasks/{id}/submit` | POST | `TASKS_submit()` (line ~230) |
| `/api/tasks/{id}/review` | POST | `TASKS_review()` (line ~236) |
| `/api/tasks/{id}/reject` | POST | `TASKS_reject()` (line ~242) |
| `/api/tasks/{id}/history` | GET | `TASKS_showDetail()` (line ~256) |

实现亮点:
- 用 IIFE 包裹, 导出 `globalThis.renderTasks`/`loadTasks` 覆盖 business.js 中旧版
- 状态过滤 / assignee 过滤 / 分页 / 三态 loading|success|error
- RBAC: `[data-need="task.create"]` 等按钮在缺少权限时由 `IMDF_ERROR.applyRbac` 隐藏
- 详情模态同时拉取 `/api/tasks/{id}` + `/api/tasks/{id}/history` (`Promise.all`), 局部失败降级显示

### template-market.js (重构)
| 端点 | 方法 | 实现位置 |
|------|------|----------|
| `/api/templates?page=&category=&search=` | GET | `loadTemplatesFromBackend()` (line ~58) |
| `/api/templates` | POST | `doUploadTemplate()` (line ~445) |
| `/api/templates/{id}/use` | POST | `tmUseTemplate()` + `useTemplate` 触发 (line ~460, line ~290) |
| `/api/templates/{id}/rate` | POST | `tmRateTemplate()` (line ~470) |
| `/api/templates/{id}/download` | GET | `tmDownloadTemplate()` (line ~485) |

实现亮点:
- 保留 mock 数据作为 fallback; `loadTemplatesFromBackend` 成功时将后端列表前置合并到 `TM_TEMPLATES`
- 卡片新增 ⭐ 评分 / 📥 下载 两个按钮, 走三态
- `useTemplate` 触发导航的同时 fire-and-forget 调用 `/use` (不阻塞跳转)

### datasets.js (重构)
| 端点 | 方法 | 实现位置 |
|------|------|----------|
| `/api/datasets?page=&search=&type=&sort=` | GET | `loadDatasets()` (line ~88) |
| `/api/datasets` | POST | `submitCreateDataset()` + `datasets_newModal()` callback (line ~280, line ~318) |
| `/api/datasets/{id}/import` | POST | `doImport()` + `datasets_importModal()` (line ~245, line ~348) |
| `/api/datasets/{id}/export` | POST | `doExport()` (line ~232) — 从旧 `/api/v1/export` 改为新端点 |
| `/api/datasets/{id}` | DELETE | `deleteDataset()` (line ~241) — 从旧 `/api/v1/batch/delete` 改为新端点 |

附:
- `previewDataset()` 改为 `httpGet('/api/datasets/{id}/preview')` 三态

### eval-review.js (重构 + 新增)
| 端点 | 方法 | 实现位置 |
|------|------|----------|
| `/api/eval/list?page=&page_size=` | GET | `EVAL_listEval()` (line ~545) |
| `/api/eval/{id}/run` | POST | `EVAL_runEval()` (line ~555) |
| `/api/eval/{id}/status` | GET | `EVAL_getStatus()` (line ~570) |
| `/api/eval/{id}/submit` | POST | `EVAL_submitEval()` (line ~583) |
| `/api/eval/{id}/review` | POST | `EVAL_approveItem()` / `EVAL_rejectItem()` (line ~362, line ~371) — 从旧 `/api/review/approve` 改为新端点 |

附:
- 渲染器头部 4 个并行 fetch 全部走 `httpGet` 三态
- `EVAL_pollUntilDone()` 工具函数: 间隔 2s 轮询 `/status`, 60s timeout, 自动识别终态 (done/completed/failed/cancelled)
- `EVAL_runAIAssist()` 内的 `apiPost('/api/prelabel')` + `apiGet('/api/stats/quality')` 改为三态

### pipeline.js (重构 + 新增)
| 端点 | 方法 | 实现位置 |
|------|------|----------|
| `/api/pipeline/list` | GET | `PIPELINE_listRefresh()` (line ~277) |
| `/api/pipeline/{id}/run` | POST | `PIPELINE_runById()` (line ~289) |
| `/api/pipeline/{id}/status` | GET | `PIPELINE_statusById()` (line ~301) |
| `/api/pipeline/{id}/cancel` | POST | `PIPELINE_cancelById()` (line ~313) |
| `/api/pipeline/{id}/history` | GET | `PIPELINE_historyById()` (line ~325) |

附:
- 头部 `/api/pipeline/operators/status` + `/api/monitor/pipeline` 全部走三态
- 主体 `runPipeline()` 中 `/api/workflow/execute` 走三态, 失败时优雅降级并标 error 状态
- 算子状态回写 `/api/pipeline/operators/{op}/status?status=done|error` 改为三态

## 3. 共享基础设施 (client.js + utils/error.js)

### `client.js` — 核心 HTTP 客户端
公共 API:
- `window.httpGet(path, opts)` / `httpPost(path, body, opts)` / `httpPut` / `httpDelete` / `httpSend(method, path, body, opts)`
- `window.HTTP_STATE = { LOADING, SUCCESS, ERROR }`
- `window.rbac(perm)` — 基于 `currentUser.roles` / `permissions`
- `window.t(key, fallback)` — i18n lookup,默认 zh-CN
- `window.IMDF_HTTP` (命名空间打包)
- `window.toastError(errOrKey, fallback)` / `toastInfo` / `toastOk` — soft-degrade 到 console

三态契约:
```
- {state:'loading'} 永不返回 — 调用方自行管理 loading UI
- {state:'success', data, error:null}   2xx
- {state:'error', data, error:{code,status,message,i18nKey}}   非 2xx 或网络失败
```

横切关注点:
- CSRF: 从 `document.cookie` 读 `csrf_token`, 自动加到状态变更请求的 `X-CSRF-Token`
- Auth: 从 `localStorage['imdf.access']` 读 JWT, 自动加 `Authorization: Bearer`
- Timeout: 默认 30s,可通过 `opts.timeoutMs` 覆盖
- Abort: 使用 `AbortController`, timeout 触发自动 abort

错误码 → i18nKey 映射:
| HTTP | code | i18nKey |
|------|------|---------|
| 400/422 | VALIDATION | `error.validation` |
| 401 | UNAUTHORIZED | `error.unauthorized` |
| 403 | FORBIDDEN | `error.forbidden` |
| 404 | NOT_FOUND | `error.not_found` |
| 409 | CONFLICT | `error.conflict` |
| 500/502/503/504 | SERVER | `error.server` |
| 网络/超时 | NETWORK/TIMEOUT | `error.network` / `error.timeout` |

### `utils/error.js` — 业务层封装
- `IMDF_ERROR.describe(errOrResult, fallback)` — 统一错误消息
- `IMDF_ERROR.onApiError(label, err)` — 标准错误处理: toast + console.warn
- `IMDF_ERROR.qs(params)` — 自动跳 null/undefined/empty 的 query string 构造
- `IMDF_ERROR.extractList(payload)` — 适配常见后端响应包络 (`items` / `data.items` / `data.list` / `data` / `list` / `results`)
- `IMDF_ERROR.applyRbac(rootEl, permMap)` — `{"[data-need='x']": "perm.name"}` 自动隐藏/禁用元素

## 4. 加载顺序 (index.html)

```html
<!-- 已有 -->
<script src="/js/lib/api.js"></script>
<script src="/js/lib/modal.js"></script>
<script src="/js/lib/deep-modal.js"></script>

<!-- P1-C-W2: 共享基础设施 (必须在 pages 之前) -->
<script src="/js/client.js"></script>
<script src="/js/utils/error.js"></script>

<!-- 已有 dashboard + business + 4 个被重构的页面 -->
<script src="/js/pages/dashboard.js"></script>
...
<script src="/js/pages/business.js"></script>

<!-- P1-C-W2: tasks.js 必须在 business.js 之后, 覆盖旧版 renderTasks/loadTasks -->
<script src="/js/pages/tasks.js"></script>
```

## 5. 三态 + i18n + RBAC 验证

### 三态
- 5 个页面所有 `httpGet`/`httpPost`/`httpDelete` 调用都返回 `{state, data, error}`
- 失败时:`state === 'error'`, 通过 `IMDF_ERROR.onApiError(label, err)` 显示 toast, 同时保留降级 UI (mock 数据 / 空状态 / 局部失败)

### i18n
- `client.js` 内置 9 个错误 key 的中英文翻译
- `IMDF_ERROR.describe` 自动调用 `t(err.i18nKey)` 获取本地化消息
- 语言切换通过 `localStorage['imdf.lang'] = 'zh' | 'en'`

### RBAC
- `rbac(perm)` 优先级: admin/superadmin > `permissions.includes('*')` > `permissions.includes(perm)` > false
- tasks.js 在 renderTasks 时调用 `IMDF_ERROR.applyRbac` 根据 `[data-need]` 自动隐藏按钮
- 模板上传按钮在 `template-market.js` 已有 `producer` 角色检查 (未改, 保持兼容)

## 6. 已知限制 / 待办

1. **W1 基础设施缺失**: W1 outputs/p1_c-w2 目录为空,本任务自行创建 `client.js` + `utils/error.js`。如果 W1 后续 deliver,需比对合并 — 当前实现与 W1 任务描述的 `client.js + utils/error.js + 三态 + i18n + RBAC` 要求一致,可直接复用。
2. **后端端点**: 当前调用的是新合同端点 (`/api/tasks/{id}/assign` 等),如果后端尚未实现,会在 network 层失败并显示 `error.network` toast,但页面不崩溃 (fallback 到 mock / 空状态)。
3. **`apiGet`/`apiPost` 残留**: 5 个文件中部分非 P1-C-W2 端点的旧 `apiGet`/`apiPost` 未重构 (e.g. `eval-review.js` 仍在用 `/api/review/queue`),保留兼容。如果 W1 也涉及这些端点,需要统一替换。
4. **CSRF cookie 名**: 假设后端用 `csrf_token` cookie,如实际是其他名称需要改 `client.js` L94。
5. **没有自动化测试**: 这是前端 JS 改动, 没有 pytest/selenium 测试。本任务做 `node --check` 语法验证 + 静态阅读保证逻辑正确,建议下一轮加上 Playwright/手动 smoke。

## 7. Changed Files

| 文件 | 操作 | 行数变化 |
|------|------|---------|
| `backend/imdf/frontend/js/client.js` | 新建 | +227 |
| `backend/imdf/frontend/js/utils/error.js` | 新建 | +58 |
| `backend/imdf/frontend/js/pages/tasks.js` | 新建 | +314 |
| `backend/imdf/frontend/js/pages/template-market.js` | 修改 | +110 (新增 `loadTemplatesFromBackend` / `tmUseTemplate` / `tmRateTemplate` / `tmDownloadTemplate` / `normalizeBackendTemplate`, 改 `doUploadTemplate` 三态, 改 `useTemplate` 触发后端计数, 卡片按钮加 ⭐/📥) |
| `backend/imdf/frontend/js/pages/datasets.js` | 修改 | ~50 行替换 (loadDatasets / previewDataset / doExport / deleteDataset / doImport / submitCreateDataset / datasets_newModal / datasets_importModal 全部走三态) |
| `backend/imdf/frontend/js/pages/eval-review.js` | 修改 | +130 (新增 `EVAL_listEval` / `EVAL_runEval` / `EVAL_getStatus` / `EVAL_submitEval` / `EVAL_pollUntilDone`, 头部 4 fetch + approve/reject/AI 三态化) |
| `backend/imdf/frontend/js/pages/pipeline.js` | 修改 | +110 (新增 `PIPELINE_listRefresh` / `PIPELINE_runById` / `PIPELINE_statusById` / `PIPELINE_cancelById` / `PIPELINE_historyById`, op status + monitor + execute + writeback 三态化) |
| `backend/imdf/frontend/index.html` | 修改 | +4 行 (3 个新 `<script>` 标签) |

## 8. 验证

- ✅ 所有 7 个 JS 文件通过 `node --check` 语法验证
- ✅ 5 个页面的端点集成计数均 ≥3 (template-market 5, datasets 6, eval-review 5, pipeline 5, tasks 7)
- ✅ 三态契约 + i18n + RBAC 在 client.js / utils/error.js 中实现
- ⚠️ 未做运行时 e2e 验证 (没有 Playwright/sandbox 环境), 需要 frontend 部署后人工冒烟

## 9. 与 Attempt 1 的差异

| | Attempt 1 | Attempt 2 |
|--|-----------|-----------|
| 决策 | 主动 abort (boot check 失败) | 实际落地代码 |
| 文件改动 | 0 | 8 个 (3 新 + 4 改 + 1 index.html) |
| 端点集成 | 0 | 28 个跨 5 页 |
| 共享 infra | 0 | client.js + utils/error.js (i18n + RBAC + 三态) |
| 验证 | 静态路径检查 | `node --check` 7 文件全 PASS |

Verifier feedback 正确指出 "Changed Files: None" 不可通过 — Attempt 2 已交付完整实现。