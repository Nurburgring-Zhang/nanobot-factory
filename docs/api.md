# API Reference — Nanobot Factory

> REST + WebSocket API 完整参考。
>
> Base URL:
> - **Dev**: `http://localhost:8001`
> - **Prod**: `https://nanobot.example.com` (经过 nginx 转发)
>
> 认证: `X-API-Key: <key>` header (开发模式下可省略；生产环境强制)
>
> OpenAPI 文档: `/docs` (Swagger UI) · `/redoc` (ReDoc) · `/openapi.json`

---

## 1. 通用约定

### 1.1 状态码

| 码 | 含义 | 何时 |
|----|------|------|
| 200 | OK | 成功 |
| 201 | Created | 创建资源成功 |
| 204 | No Content | 删除 / 无返回体 |
| 400 | Bad Request | 参数错误 |
| 401 | Unauthorized | 缺 / 错 API key |
| 403 | Forbidden | 权限不足 |
| 404 | Not Found | 资源不存在 |
| 409 | Conflict | 重复 / 冲突 |
| 413 | Payload Too Large | 文件 > 64 MB |
| 422 | Validation Error | Pydantic 校验失败 |
| 429 | Too Many Requests | 触发 rate limit |
| 500 | Internal Server Error | 详见日志 traceback |
| 503 | Service Unavailable | 依赖 (ComfyUI / DB) 不可用 |

### 1.2 错误体

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task 9f8e does not exist",
    "details": { "task_id": "9f8e" },
    "trace_id": "01HX..."
  }
}
```

### 1.3 分页

```http
GET /api/v1/assets?page=2&page_size=50&sort=-created_at
```

```json
{
  "items": [ /* ... */ ],
  "total": 1234,
  "page": 2,
  "page_size": 50,
  "has_next": true
}
```

### 1.4 版本

`/api/v1/...` 是稳定版本；`/airi/...` / `/omni/...` 是与产品同名的功能性路由组（v1 后保留）。

---

## 2. 健康检查

### `GET /healthz` — Liveness

200 即"进程存活 + 事件循环可响应"。

```json
{ "status":"ok", "service":"imdf", "version":"1.0.0", "uptime_seconds": 12.3 }
```

### `GET /readyz` — Readiness

200 = 全部依赖 (DB, disk, redis) 就绪；503 = 任一依赖失败。

```json
{
  "status":"ok",
  "checks": {
    "database":  { "ok": true,  "latency_ms": 2 },
    "disk":      { "ok": true,  "free_mb": 12400 },
    "redis":     { "ok": true,  "latency_ms": 1 }
  }
}
```

### `GET /metrics` — Prometheus

`text/plain; version=0.0.4` 格式，仅供内部 Prometheus 抓取。

---

## 3. 认证

### `POST /api/v1/auth/token`

用 API Key 换取短时 JWT（默认 24h）。

请求：

```json
{ "api_key": "sk-..." }
```

响应：

```json
{ "access_token": "eyJhbGc...", "expires_in": 86400, "token_type": "Bearer" }
```

### `POST /api/v1/auth/refresh`

刷新即将过期的 JWT。

---

## 4. 用户 / 权限 (RBAC)

### 角色

`admin` / `manager` / `annotator` / `reviewer` / `viewer`

### `GET /api/v1/users/me`

返回当前用户详情。

```json
{
  "id": "u_1",
  "name": "Alice",
  "email": "alice@example.com",
  "role": "annotator",
  "created_at": "2026-01-12T08:00:00Z"
}
```

### `GET /api/v1/users`

仅 `admin` / `manager` 可用。支持 `?role=`、`?q=` 搜索。

### `POST /api/v1/users`

`admin` 创建用户。

```json
{ "name":"Bob", "email":"bob@x.com", "role":"annotator", "password":"..." }
```

### `PATCH /api/v1/users/{id}`

更新用户角色 / 启用状态。

---

## 5. 数据资产 (Assets)

### `POST /api/v1/assets/upload`

multipart/form-data 上传单个文件。

```bash
curl -X POST https://nanobot.example.com/api/v1/assets/upload \
  -H "X-API-Key: $KEY" \
  -F "file=@/path/to/image.png" \
  -F "kind=image" \
  -F "tags=product,shoes"
```

返回 201：

```json
{
  "id": "a_8f3e",
  "sha256": "abc...",
  "size_bytes": 142111,
  "kind": "image",
  "mime": "image/png",
  "url": "/api/v1/assets/a_8f3e/raw",
  "tags": ["product","shoes"],
  "created_at": "2026-06-21T08:00:00Z"
}
```

### `POST /api/v1/assets/batch-upload`

批量上传（最多 100 个文件 / 请求）。

### `GET /api/v1/assets`

列表查询。Query 参数：`kind`、`tags`、`created_after`、`created_before`、`page`、`page_size`、`sort`。

### `GET /api/v1/assets/{id}`

详情。

### `GET /api/v1/assets/{id}/raw`

返回原始二进制流。响应头：
- `Content-Type` — 实际 MIME
- `Content-Disposition: inline; filename="..."`
- `Cache-Control: private, max-age=600`

### `DELETE /api/v1/assets/{id}`

软删除（标记 `deleted_at`，后台清理任务 30 天后物理删除）。

---

## 6. 标注 (Annotations)

### 数据模型

```ts
annotation = {
  id: string,
  asset_id: string,
  annotator_id: string,
  type: "bbox" | "polygon" | "keypoint" | "mask" | "obb",
  payload: object,    // 类型相关的几何 / 标签
  labels: string[],
  confidence?: number,
  reviewed_by?: string,
  status: "draft" | "submitted" | "approved" | "rejected",
  version: int,
  created_at: ISO,
  updated_at: ISO
}
```

### `POST /api/v1/annotations`

```json
{
  "asset_id":"a_8f3e",
  "type":"bbox",
  "payload": { "x":12, "y":34, "w":100, "h":80 },
  "labels": ["shoe"]
}
```

### `GET /api/v1/annotations?asset_id=...`

### `PATCH /api/v1/annotations/{id}`

提交 / 修订。

### `POST /api/v1/annotations/{id}/approve` / `/reject`

仅 `reviewer` / `manager`。

### `GET /api/v1/annotations/iaa?dataset_id=...`

返回两个 annotator 的 Inter-Annotator Agreement (Cohen's Kappa)。

---

## 7. 无限画布 (Canvas)

### `GET /airi/canvas/state`

返回当前用户/项目下的整张画布 JSON。

```json
{
  "version": 42,
  "nodes": [
    { "id":"n_1", "type":"image", "x":0, "y":0, "w":512, "h":512, "asset_id":"a_..." },
    { "id":"n_2", "type":"prompt", "x":600, "y":0, "text":"a red shoe" }
  ],
  "edges": [
    { "from":"n_1", "to":"n_2", "kind":"reference" }
  ]
}
```

### `POST /airi/canvas/element`

新增节点。

### `PUT /airi/canvas/element/{id}`

更新节点 (位置 / 属性)。

### `DELETE /airi/canvas/element/{id}`

删除节点。

### WebSocket `/airi/canvas/ws`

双向事件流。

客户端 → 服务端：

```json
{ "op": "add_node", "data": { /* node spec */ } }
{ "op": "move_node", "data": { "id":"n_1", "x": 100, "y": 100 } }
{ "op": "delete_node", "data": { "id": "n_1" } }
{ "op": "ping" }
```

服务端 → 客户端：

```json
{ "op": "node_added",  "data": { /* node */ }, "by":"u_42", "ts":"..." }
{ "op": "node_moved",  "data": {...}, "by":"u_42", "ts":"..." }
{ "op": "pong",        "ts":"..." }
```

事件按房间 (room) 广播，默认房间 = `project:<project_id>`。单房间上限 50 客户端。

---

## 8. Master Agent 编排

### `POST /airi/engine/plan`

输入：自然语言目标 + 当前画布 JSON。

```json
{
  "goal": "生成 4 张不同角度的运动鞋概念图",
  "canvas_state": { /* GET /airi/canvas/state 的返回 */ }
}
```

响应 (LLM 输出经结构化校验)：

```json
{
  "plan_id": "p_5f",
  "tasks": [
    { "id":"t_1", "engine":"comfyui", "params":{ "workflow":"sdxl_txt2img", "prompt":"..." }, "count":4 }
  ],
  "estimated_duration_sec": 180,
  "estimated_cost_usd": 0.12
}
```

### `POST /airi/engine/render`

提交 plan 执行。

```json
{ "plan_id": "p_5f" }
```

响应 202：

```json
{ "batch_id": "b_99", "status": "queued" }
```

---

## 9. AIGC / ComfyUI

### `GET /omni/comfy/status`

```json
{ "reachable": true, "queue_remaining": 2, "version": "0.3.10" }
```

### `POST /omni/comfy/render`

直接提交 ComfyUI workflow。

```json
{ "workflow_json": { /* ComfyUI API format */ }, "count": 4 }
```

### `GET /omni/comfy/render/{batch_id}`

查询 batch 状态。

```json
{
  "batch_id": "b_99",
  "status": "running",         // queued | running | done | failed | cancelled
  "progress": 0.45,
  "items": [
    { "id":"i_1", "status":"done",   "url":"/api/v1/assets/a_xx1/raw" },
    { "id":"i_2", "status":"running" },
    { "id":"i_3", "status":"queued"  },
    { "id":"i_4", "status":"queued"  }
  ]
}
```

### `POST /omni/comfy/render/{batch_id}/cancel`

取消 batch（已开始的单帧会继续跑完以避免半成品）。

---

## 10. Prompt 模板

### `GET /api/v1/prompt-templates`

支持 `?category=`、`?q=`。

### `POST /api/v1/prompt-templates`

```json
{ "name":"shoes-side", "category":"product", "template":"{subject}, side view, white background, {style}" }
```

### `PUT /api/v1/prompt-templates/{id}`

### `DELETE /api/v1/prompt-templates/{id}`

### `GET /api/v1/prompt-templates/categories`

返回分类及计数。

---

## 11. 3D 场景

### `POST /api/3d/scenes`

```json
{ "name":"warehouse", "format":"gltf", "source_url":"https://..." }
```

### `GET /api/3d/scenes/{id}/lod`

返回 LOD 等级列表。

### `GET /api/3d/scenes/{id}/lod/{level}/mesh`

流式下载 GLTF/GLB。

---

## 12. 导出

### `POST /api/v1/exports`

```json
{ "dataset_id":"d_42", "format":"coco", "include_images": true, "split": { "train":0.8, "val":0.1, "test":0.1 } }
```

### `GET /api/v1/exports/{id}`

返回 `status`、`download_url`（24h 有效）。

支持的格式：`coco` / `yolo` / `voc` / `csv` / `parquet` / `custom-json`。

---

## 13. 版权 / 隐私 / 审计

### `POST /api/v1/copyright/scan`

```json
{ "asset_ids":["a_1","a_2"] }
```

### `POST /api/v1/privacy/redact`

```json
{ "asset_id":"a_1", "fields":["face","plate"] }
```

返回 `redacted_url`（24h 有效）。

### `GET /api/v1/audit/events?actor=...&action=...&after=...`

返回审计事件（分页）。每条事件含 `actor`、`action`、`target`、`ip`、`ua`、`ts`。

---

## 14. 监控 / 运维

### `GET /api/v1/ops/dashboard`

聚合数据：CPU、内存、磁盘、活跃任务、活跃 WS。

### `GET /api/v1/ops/tasks?status=running`

任务列表。

### `POST /api/v1/ops/tasks/{id}/cancel`

### `GET /api/v1/ops/gpu`

```json
{ "devices":[ { "index":0, "name":"A100", "util":0.42, "mem_used_mb":18000, "mem_total_mb":40960 } ] }
```

### `GET /api/v1/ops/cluster`

集群节点状态。

---

## 15. SDK / Webhook

### `POST /api/v1/sdk/keys`

创建 SDK key。

### `POST /api/v1/webhooks`

```json
{ "url":"https://your.app/hook", "events":["task.completed","annotation.approved"], "secret":"..." }
```

事件以 `X-Nanobot-Signature: sha256=...` 头签名（HMAC-SHA256）。

---

## 16. 限流

默认：100 req/min/IP。可在 `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW` 环境变量调整。

超限返回 429：

```json
{ "error": { "code":"RATE_LIMITED", "retry_after": 30 } }
```

头：
- `X-RateLimit-Limit: 100`
- `X-RateLimit-Remaining: 0`
- `Retry-After: 30`

---

## 17. SDK 示例 (Python)

```python
from nanobot_sdk import NanobotClient

client = NanobotClient(
    base_url="https://nanobot.example.com",
    api_key="sk-...",
)

# 上传
asset = client.assets.upload("/tmp/shoe.png", tags=["product"])
print(asset.id, asset.url)

# 创建标注
client.annotations.create(asset.id, type="bbox",
    payload={"x":10,"y":10,"w":100,"h":80}, labels=["shoe"])

# 提交渲染
batch = client.aigc.render(workflow="sdxl_txt2img",
                           prompt="a red running shoe",
                           count=4)
print(batch.id, batch.status)

# 异步等待
for ev in client.stream_events(batch.id):
    print(ev.progress, ev.status)
```

---

## 18. OpenAPI / 类型生成

```bash
# 拉 schema
curl https://nanobot.example.com/openapi.json -o schema.json

# 生成 Python client
openapi-python-client generate --path schema.json --config pyproject.toml

# 生成 TypeScript
openapi-typescript schema.json --output ./types/nanobot-api.ts
```

---

_最后更新：2026-06-21 — 适用版本 appVersion 1.0.0_

_详细字段 schema 请直接看 Swagger UI：`/docs`_