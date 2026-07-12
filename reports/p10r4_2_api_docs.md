# P10R4-2: API 文档 (OpenAPI 3.0 · 12 微服务)

> **Date**: 2026-06-26 13:55 (Asia/Shanghai)
> **Author**: coder (P10R4-2 worker)
> **Sources**: `docs/api.md` (权威 11KB) + `backend/gateway/main.py` (实际 FastAPI app) + 12 个 service routes 验证
> **配套**: `p10r4_2_readme.md` (项目总览) · `p10r4_2_architecture.md` (架构)

---

## 1. OpenAPI 3.0 元数据

| 字段 | 值 |
|------|-----|
| OpenAPI Version | 3.0.3 |
| Title | Nanobot Factory IMDF API |
| Version | 1.0.0 (匹配 `VERSION` env) |
| Contact | api-support@nanobot-factory.example.com |
| License | MIT |
| Swagger UI | `https://imdf.example.com/docs` |
| ReDoc | `https://imdf.example.com/redoc` |
| OpenAPI JSON | `https://imdf.example.com/openapi.json` |

### 1.1 服务发现

| Service | Port | Mount Path (内部) | Public Path (nginx → gateway) |
|---------|------|-------------------|-------------------------------|
| imdf-gateway | **8000** | `/api/*`, `/airi/*`, `/omni/*`, `/ws/*`, `/healthz`, `/readyz`, `/metrics` | `https://imdf.example.com/...` |
| imdf-user | 8001 | `/api/v1/users/*`, `/api/v1/auth/*` | `→ gateway` |
| imdf-asset | 8002 | `/api/v1/assets/*` | `→ gateway` |
| imdf-annotation | 8003 | `/api/v1/annotations/*`, `/api/v1/datasets/*` | `→ gateway` |
| imdf-cleaning | 8004 | `/api/v1/cleaning/*` | `→ gateway` |
| imdf-scoring | 8005 | `/api/v1/scoring/*` | `→ gateway` |
| imdf-dataset | 8006 | `/api/v1/datasets/*` (also) | `→ gateway` |
| imdf-evaluation | 8007 | `/api/v1/evaluation/*` | `→ gateway` |
| imdf-agent | 8008 | `/api/v1/agents/*`, `/api/v1/mcp/*`, `/api/v1/memory/*` | `→ gateway` |
| imdf-workflow | 8009 | `/api/v1/workflows/*`, `/api/v1/dag/*` | `→ gateway` |
| imdf-notification | 8010 | `/api/v1/notifications/*`, `/ws/notifications` | `→ gateway` |
| imdf-search | 8011 | `/api/v1/search/*` | `→ gateway` |
| imdf-collection | 8012 | `/api/v1/collection/*` | `→ gateway` |

**架构原则**: 8000 gateway 是唯一对外端口,12 个 svc 走内部 HTTP (gateway → service)。客户端**永远不直接访问 8001-8012**。

---

## 2. 鉴权 (JWT + 多租户)

### 2.1 双 token 模式

```yaml
# 流程:
1. POST /api/v1/auth/token        # API Key → JWT
2. POST /api/v1/auth/refresh      # 过期前 5min 续签
3. POST /api/v1/auth/revoke       # 主动登出 (token 黑名单)

# 配置:
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TTL = 86400        # 24h
JWT_REFRESH_TTL = 2592000     # 30d
JWT_ISSUER = "imdf-gateway"
JWT_AUDIENCE = "imdf-api"
JWT_SECRET_KEY = "<32 bytes random>"   # openssl rand -hex 32
```

### 2.2 多租户 (Tenant)

每个 JWT payload 包含:
```json
{
  "sub": "u_alice",
  "tenant_id": "t_acme_corp",
  "tenant_role": "admin",
  "scopes": ["assets:read", "assets:write", "annotations:read"],
  "iat": 1719000000,
  "exp": 1719086400,
  "iss": "imdf-gateway",
  "aud": "imdf-api"
}
```

所有数据库行通过 `tenant_id` 隔离 (row-level security)。
Tenant 切换: 业务请求 header `X-Tenant-ID: t_<other>` 需 admin 权限。

### 2.3 RBAC 5 角色

| 角色 | 权限范围 |
|------|---------|
| `admin` | 全平台 + 用户管理 + 计费 |
| `manager` | 项目 + 团队 + 标注审核 |
| `reviewer` | 标注审核 + BadCase |
| `annotator` | 标注创建/编辑 + 上传 |
| `viewer` | 只读 |

---

## 3. 错误码完整表 (13 种)

| 状态码 | 含义 | 触发场景 |
|--------|------|---------|
| **200** | OK | 成功 |
| **201** | Created | 创建资源成功 |
| **204** | No Content | 删除 / 无返回体 |
| **400** | Bad Request | 参数错误 (非 Pydantic) |
| **401** | Unauthorized | 缺 / 错 JWT 或 API Key |
| **403** | Forbidden | 权限不足 / tenant 越界 |
| **404** | Not Found | 资源不存在 |
| **409** | Conflict | 重复 / 业务冲突 (如重复创建同名 dataset) |
| **413** | Payload Too Large | 文件 > 64 MB |
| **422** | Validation Error | Pydantic 校验失败 |
| **429** | Too Many Requests | 触发 rate limit (per-IP/per-user/per-tenant) |
| **500** | Internal Server Error | 详见日志 traceback |
| **503** | Service Unavailable | 依赖 (DB / Redis / OSS / ComfyUI) 不可用 |

### 3.1 错误响应统一格式

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "Task 9f8e does not exist",
    "details": { "task_id": "9f8e" },
    "trace_id": "01HX...",
    "request_id": "req_abc123"
  }
}
```

### 3.2 429 Rate Limit 详情

| Scope | Default | 配额 |
|-------|---------|------|
| Per-IP | 60 req/min | `RATE_LIMIT_PER_IP` |
| Per-User | 600 req/min | `RATE_LIMIT_PER_USER` |
| Per-Tenant | 6000 req/min | `RATE_LIMIT_PER_TENANT` |
| `/api/auth/*` | 10 req/min/IP | nginx 强制 |

`Retry-After` header 返回剩余秒数。

---

## 4. Endpoint 详表 (按服务分组)

### 4.1 imdf-gateway (:8000) — 公共入口

| Method | Path | 用途 | Auth |
|--------|------|------|------|
| GET | `/healthz` | Liveness 探针 | 无 |
| GET | `/readyz` | Readiness (DB+Redis+disk) | 无 |
| GET | `/metrics` | Prometheus 指标 | 无 (内网) |
| GET | `/docs` | Swagger UI | 无 |
| GET | `/redoc` | ReDoc UI | 无 |
| GET | `/openapi.json` | OpenAPI 3.0 规范 | 无 |
| GET | `/api/queue/health` | 队列健康 (Celery + Redis) | 无 |
| GET | `/api/queue/stats` | 队列统计 | admin |
| WS  | `/ws/canvas/{session_id}` | 无限画布实时协同 | JWT |
| WS  | `/ws/notifications` | 实时通知推送 | JWT |

### 4.2 imdf-user (:8001) — 用户 / 认证

| Method | Path | 用途 | 权限 |
|--------|------|------|------|
| POST | `/api/v1/auth/token` | API Key → JWT | 公开 |
| POST | `/api/v1/auth/refresh` | 刷新 JWT | JWT |
| POST | `/api/v1/auth/revoke` | 注销 token | JWT |
| GET  | `/api/v1/users/me` | 当前用户详情 | JWT |
| GET  | `/api/v1/users` | 用户列表 (分页/搜索) | admin/manager |
| POST | `/api/v1/users` | 创建用户 | admin |
| PATCH | `/api/v1/users/{id}` | 更新用户角色/状态 | admin |
| DELETE | `/api/v1/users/{id}` | 软删除 | admin |
| POST | `/api/v1/users/{id}/reset-password` | 重置密码 | admin |
| GET  | `/api/v1/tenants/me` | 当前 tenant 详情 | JWT |
| GET  | `/api/v1/tenants` | tenant 列表 | admin |

### 4.3 imdf-asset (:8002) — 资产

| Method | Path | 用途 |
|--------|------|------|
| POST | `/api/v1/assets/upload` | 单文件 multipart 上传 |
| POST | `/api/v1/assets/batch-upload` | 批量上传 (≤100/请求) |
| GET  | `/api/v1/assets` | 列表 (kind/tags/时间过滤 + 分页) |
| GET  | `/api/v1/assets/{id}` | 详情 |
| GET  | `/api/v1/assets/{id}/raw` | 原始二进制流 |
| GET  | `/api/v1/assets/{id}/thumbnail` | 缩略图 (256x256) |
| PATCH | `/api/v1/assets/{id}` | 更新元数据 (tags / kind) |
| DELETE | `/api/v1/assets/{id}` | 软删除 (30 天后清理) |
| POST | `/api/v1/assets/{id}/duplicate` | 复制资产 |
| POST | `/api/v1/assets/{id}/share` | 生成分享链接 (TTL) |

### 4.4 imdf-annotation (:8003) — 标注

| Method | Path | 用途 |
|--------|------|------|
| POST | `/api/v1/annotations` | 创建标注 (bbox/polygon/keypoint/mask/obb) |
| GET  | `/api/v1/annotations` | 列表 (asset_id / annotator_id / status 过滤) |
| GET  | `/api/v1/annotations/{id}` | 详情 |
| PATCH | `/api/v1/annotations/{id}` | 更新 |
| DELETE | `/api/v1/annotations/{id}` | 软删除 |
| POST | `/api/v1/annotations/{id}/submit` | 提交审核 |
| POST | `/api/v1/annotations/{id}/approve` | 通过 (reviewer) |
| POST | `/api/v1/annotations/{id}/reject` | 驳回 (reviewer) |
| GET  | `/api/v1/annotations/iaa?dataset_id=...` | Inter-Annotator Agreement (Cohen's Kappa) |
| POST | `/api/v1/datasets` | 创建数据集 |
| GET  | `/api/v1/datasets` | 列表 |
| GET  | `/api/v1/datasets/{id}` | 详情 |
| GET  | `/api/v1/datasets/{id}/export` | 导出 (coco/yolo/voc/json) |

### 4.5 imdf-cleaning (:8004) — 清洗

| Method | Path | 用途 |
|--------|------|------|
| POST | `/api/v1/cleaning/jobs` | 创建清洗任务 (去重/质量/脱敏) |
| GET  | `/api/v1/cleaning/jobs/{id}` | 任务状态 |
| GET  | `/api/v1/cleaning/jobs/{id}/report` | 清洗报告 (去重率/质量分布) |
| POST | `/api/v1/cleaning/dedup` | 哈希去重 (perceptual hash) |
| POST | `/api/v1/cleaning/quality-filter` | 质量分过滤 |
| POST | `/api/v1/cleaning/desensitize` | PII 脱敏 (人脸/车牌/邮箱) |
| GET  | `/api/v1/cleaning/rules` | 规则列表 |
| POST | `/api/v1/cleaning/rules` | 新增规则 |

### 4.6 imdf-scoring (:8005) — 评分

| Method | Path | 用途 |
|--------|------|------|
| POST | `/api/v1/scoring/jobs` | 创建评分任务 (美学/质量/安全) |
| GET  | `/api/v1/scoring/jobs/{id}` | 状态 |
| GET  | `/api/v1/scoring/jobs/{id}/results` | 评分结果 (per-asset score) |
| POST | `/api/v1/scoring/aesthetic` | 美学评分 (LAION aesthetic predictor) |
| POST | `/api/v1/scoring/quality` | 质量分 (BRISQUE / MUSIQ) |
| POST | `/api/v1/scoring/safety` | 安全审核 (NSFW / violence classifier) |
| POST | `/api/v1/scoring/batch` | 批量评分 |

### 4.7 imdf-dataset (:8006) — 数据集管理

| Method | Path | 用途 |
|--------|------|------|
| POST | `/api/v1/datasets` | 创建数据集 (含 versioning) |
| GET  | `/api/v1/datasets` | 列表 |
| GET  | `/api/v1/datasets/{id}` | 详情 (含版本树) |
| GET  | `/api/v1/datasets/{id}/versions` | 版本历史 |
| POST | `/api/v1/datasets/{id}/versions` | 新增版本 (immutable) |
| GET  | `/api/v1/datasets/{id}/versions/{v}/export` | 导出 (coco/yolo/voc/json/parquet) |
| POST | `/api/v1/datasets/{id}/tags` | 打标签 |
| POST | `/api/v1/datasets/{id}/share` | 公开分享 |

### 4.8 imdf-evaluation (:8007) — 评测 + BadCase

| Method | Path | 用途 |
|--------|------|------|
| POST | `/api/v1/evaluation/jobs` | 创建模型评测任务 |
| GET  | `/api/v1/evaluation/jobs/{id}` | 状态 |
| GET  | `/api/v1/evaluation/jobs/{id}/metrics` | mAP / FID / CLIP-score |
| POST | `/api/v1/evaluation/badcase` | 上报 BadCase |
| GET  | `/api/v1/evaluation/badcase` | BadCase 列表 |
| POST | `/api/v1/evaluation/badcase/{id}/cluster` | 聚类分析 |
| GET  | `/api/v1/evaluation/leaderboard` | 模型排行榜 |

### 4.9 imdf-agent (:8008) — Agent + MCP + Memory

| Method | Path | 用途 |
|--------|------|------|
| GET  | `/api/v1/agents/types` | 15 主 Agent 清单 |
| POST | `/api/v1/agents/dispatch` | 派发任务给指定 Agent |
| GET  | `/api/v1/agents/tasks/{id}` | 任务状态 |
| GET  | `/api/v1/agents/tasks` | 任务列表 (按 type / status 过滤) |
| GET  | `/api/v1/mcp/tools` | MCP 工具列表 |
| POST | `/api/v1/mcp/tools/{name}/invoke` | 调用 MCP 工具 |
| GET  | `/api/v1/mcp/resources` | MCP 资源列表 |
| GET  | `/api/v1/mcp/prompts` | MCP prompt 模板 |
| POST | `/api/v1/memory/store` | MemoryPalace 记忆存储 |
| GET  | `/api/v1/memory/recall` | 记忆检索 (向量 + 时间衰减) |
| GET  | `/api/v1/memory/hindsight` | Hindsight 反思日志 |

### 4.10 imdf-workflow (:8009) — DAG v2 + Visual Editor

| Method | Path | 用途 |
|--------|------|------|
| POST | `/api/v1/workflows` | 创建工作流 (DAG JSON) |
| GET  | `/api/v1/workflows` | 列表 |
| GET  | `/api/v1/workflows/{id}` | 详情 (含 DAG 拓扑) |
| PATCH | `/api/v1/workflows/{id}` | 更新 DAG |
| POST | `/api/v1/workflows/{id}/run` | 触发执行 |
| GET  | `/api/v1/workflows/{id}/runs` | 执行历史 |
| GET  | `/api/v1/workflows/{id}/runs/{rid}` | 单次执行状态 |
| POST | `/api/v1/workflows/{id}/runs/{rid}/cancel` | 取消执行 |
| GET  | `/api/v1/dag/operators` | 39 个 op.editor.* 算子清单 |
| GET  | `/api/v1/dag/operators/{op_id}` | 算子详情 + schema |

### 4.11 imdf-notification (:8010)

| Method | Path | 用途 |
|--------|------|------|
| GET  | `/api/v1/notifications` | 当前用户通知列表 |
| PATCH | `/api/v1/notifications/{id}/read` | 标记已读 |
| POST | `/api/v1/notifications/send` | 发送通知 (admin) |
| POST | `/api/v1/notifications/email` | 邮件发送 (SMTP) |
| WS  | `/ws/notifications` | 实时推送 (WebSocket) |

### 4.12 imdf-search (:8011)

| Method | Path | 用途 |
|--------|------|------|
| GET  | `/api/v1/search?q=...` | 全文搜索 (PostgreSQL FTS) |
| GET  | `/api/v1/search/vector?q=...&k=10` | 向量检索 (pgvector cosine) |
| GET  | `/api/v1/search/hybrid?q=...` | 混合检索 (RRF) |
| POST | `/api/v1/search/index` | 重建索引 |

### 4.13 imdf-collection (:8012) — 采集

| Method | Path | 用途 |
|--------|------|------|
| POST | `/api/v1/collection/jobs` | 创建采集任务 (HTTP/S3/OSS pull) |
| GET  | `/api/v1/collection/jobs/{id}` | 状态 |
| GET  | `/api/v1/collection/sources` | 数据源列表 |
| POST | `/api/v1/collection/sources` | 新增数据源 |
| POST | `/api/v1/collection/sources/{id}/sync` | 触发同步 |

---

## 5. 商业化 endpoint (P7-2 PASS, 570 tests)

### 5.1 billing (订阅 / 支付)

| Path | 用途 |
|------|------|
| `POST /api/v1/billing/subscriptions` | 创建订阅 |
| `GET  /api/v1/billing/subscriptions/{id}` | 订阅详情 |
| `PATCH /api/v1/billing/subscriptions/{id}` | 升降级 / 暂停 |
| `POST /api/v1/billing/subscriptions/{id}/cancel` | 取消 (period end) |
| `POST /api/v1/billing/payments/charge` | 单次扣款 (Stripe / Alipay / WeChat) |
| `POST /api/v1/billing/payments/{id}/refund` | 全额/部分退款 |
| `POST /api/v1/billing/webhooks/stripe` | Stripe webhook (verify_webhook) |
| `POST /api/v1/billing/webhooks/alipay` | Alipay webhook |
| `POST /api/v1/billing/webhooks/wechat` | WeChat webhook |
| `GET  /api/v1/billing/invoices` | 账单列表 |
| `GET  /api/v1/billing/invoices/{id}` | 账单详情 |

### 5.2 contracts (合同)

`POST /api/v1/contracts` `GET /api/v1/contracts` `POST /api/v1/contracts/{id}/sign` `GET /api/v1/contracts/expiring?days=30`

### 5.3 invoices (发票)

`POST /api/v1/invoices` `POST /api/v1/invoices/{id}/issue` `POST /api/v1/invoices/{id}/red-letter` `POST /api/v1/invoices/tax-bureau/submit`

### 5.4 crm (客户)

`POST /api/v1/crm/leads` `GET /api/v1/crm/leads/top?limit=10` `POST /api/v1/crm/segments` `GET /api/v1/crm/segments/{id}/match`

### 5.5 tickets (工单)

`POST /api/v1/tickets` `POST /api/v1/tickets/{id}/merge` (合并) `POST /api/v1/tickets/{id}/split` (拆分) `GET /api/v1/tickets/sla-breach`

---

## 6. Swagger UI 验证 (期望结果)

```bash
# 1) 启动 gateway
cd D:\Hermes\生产平台\nanobot-factory
.\venv\Scripts\python.exe -m uvicorn backend.gateway.main:app --host 0.0.0.0 --port 8000

# 2) 浏览器访问
#    http://localhost:8000/docs     (Swagger UI)
#    http://localhost:8000/redoc    (ReDoc)
#    http://localhost:8000/openapi.json (machine-readable)

# 3) 验证 healthz
curl -fsS http://localhost:8000/healthz | python -m json.tool
# 预期:
# {
#   "status": "ok",
#   "service": "imdf",
#   "version": "1.0.0",
#   "uptime_seconds": 12.3
# }

# 4) 验证 readyz
curl -fsS http://localhost:8000/readyz | python -m json.tool
# 预期: status=ok + 3 checks ok + 各 latency_ms < 5

# 5) 验证 metrics
curl -fsS http://localhost:8000/metrics | head -10
# 预期: # HELP / # TYPE / imdf_requests_total / imdf_request_latency_seconds_bucket ...
```

---

## 7. 示例代码 (curl / Python / JavaScript)

### 7.1 curl — 完整登录 → 上传 → 标注 → 导出流程

```bash
# Step 1: 获取 token
TOKEN=$(curl -fsS -X POST http://localhost:8000/api/v1/auth/token \
  -H "Content-Type: application/json" \
  -d '{"api_key":"sk-your-key"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# Step 2: 上传资产
ASSET_ID=$(curl -fsS -X POST http://localhost:8000/api/v1/assets/upload \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "file=@./test.jpg" \
  -F "kind=image" \
  -F "tags=test,demo" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Step 3: 创建标注
curl -fsS -X POST http://localhost:8000/api/v1/annotations \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"asset_id\":\"${ASSET_ID}\",
    \"type\":\"bbox\",
    \"payload\":{\"x\":12,\"y\":34,\"w\":100,\"h\":80},
    \"labels\":[\"shoe\"]
  }"

# Step 4: 提交审核
curl -fsS -X POST "http://localhost:8000/api/v1/annotations/${ASSET_ID}/submit" \
  -H "Authorization: Bearer ${TOKEN}"

# Step 5: 导出 COCO
curl -fsS "http://localhost:8000/api/v1/datasets/ds_xxx/versions/1/export?format=coco" \
  -H "Authorization: Bearer ${TOKEN}" -o annotations.json
```

### 7.2 Python — 异步 SDK 模式

```python
import httpx
import asyncio

class IMDFClient:
    def __init__(self, base_url: str, api_key: str):
        self.base = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=30.0)
        self.api_key = api_key
        self.token: str | None = None

    async def login(self) -> None:
        r = await self.client.post(f"{self.base}/api/v1/auth/token",
                                    json={"api_key": self.api_key})
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def _hdr(self) -> dict:
        if not self.token:
            raise RuntimeError("call .login() first")
        return {"Authorization": f"Bearer {self.token}"}

    async def list_assets(self, kind: str = "image", page: int = 1):
        r = await self.client.get(f"{self.base}/api/v1/assets",
                                   params={"kind": kind, "page": page},
                                   headers=self._hdr())
        r.raise_for_status()
        return r.json()

    async def upload(self, file_path: str, kind: str = "image", tags: list[str] = None):
        with open(file_path, "rb") as f:
            r = await self.client.post(
                f"{self.base}/api/v1/assets/upload",
                headers=self._hdr(),
                files={"file": (file_path, f, "application/octet-stream")},
                data={"kind": kind, "tags": ",".join(tags or [])},
            )
        r.raise_for_status()
        return r.json()

    async def create_annotation(self, asset_id: str, bbox: dict, labels: list[str]):
        r = await self.client.post(
            f"{self.base}/api/v1/annotations",
            headers={**self._hdr(), "Content-Type": "application/json"},
            json={"asset_id": asset_id, "type": "bbox",
                  "payload": bbox, "labels": labels},
        )
        r.raise_for_status()
        return r.json()

    async def __aenter__(self):
        await self.login()
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

# Usage
async def main():
    async with IMDFClient("http://localhost:8000", "sk-your-key") as c:
        assets = await c.list_assets(kind="image", page=1)
        print(f"total assets: {assets['total']}")

asyncio.run(main())
```

### 7.3 JavaScript (Node.js + fetch)

```javascript
const BASE = "http://localhost:8000";

async function login(apiKey) {
  const r = await fetch(`${BASE}/api/v1/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!r.ok) throw new Error(`login failed: ${r.status}`);
  return (await r.json()).access_token;
}

async function listAssets(token, kind = "image", page = 1) {
  const r = await fetch(`${BASE}/api/v1/assets?kind=${kind}&page=${page}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok) throw new Error(`list failed: ${r.status}`);
  return r.json();
}

async function uploadAsset(token, filePath, kind = "image") {
  const fs = await import("fs");
  const buf = fs.readFileSync(filePath);
  const blob = new Blob([buf]);
  const form = new FormData();
  form.append("file", blob, filePath);
  form.append("kind", kind);
  const r = await fetch(`${BASE}/api/v1/assets/upload`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  if (!r.ok) throw new Error(`upload failed: ${r.status}`);
  return r.json();
}

// Usage
(async () => {
  const token = await login("sk-your-key");
  const assets = await listAssets(token);
  console.log(`total assets: ${assets.total}`);
})();
```

---

## 8. WebSocket 接口

### 8.1 无限画布实时协同 `/ws/canvas/{session_id}`

```javascript
const ws = new WebSocket(`wss://imdf.example.com/ws/canvas/${sessionId}`, {
  headers: { Authorization: `Bearer ${token}` }
});

ws.onopen = () => {
  // 加入会话
  ws.send(JSON.stringify({
    type: "join",
    user: { id: "u_alice", name: "Alice", color: "#5aa9ff" }
  }));
};

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  switch (msg.type) {
    case "node_added":    /* {node: {...}} */ break;
    case "node_moved":    /* {node_id, x, y} */ break;
    case "node_updated":  /* {node_id, props} */ break;
    case "selection":     /* {user_id, node_ids} */ break;
    case "cursor":        /* {user_id, x, y} */ break;
    case "user_joined":   /* {user: {...}} */ break;
    case "user_left":     /* {user_id} */ break;
  }
};
```

### 8.2 通知推送 `/ws/notifications`

```javascript
const ws = new WebSocket(`wss://imdf.example.com/ws/notifications`, {
  headers: { Authorization: `Bearer ${token}` }
});

ws.onmessage = (event) => {
  const notif = JSON.parse(event.data);
  // { id, type, title, body, link, severity, timestamp }
  showToast(notif);
};
```

---

## 9. 版本兼容 (Deprecation Policy)

| 项 | 承诺 |
|----|------|
| `/api/v1/*` | **永久稳定**, 至少维持 24 个月 |
| 旧路径 `/airi/`, `/omni/` | 保留至 2027-06, 仅 bug fix |
| Header `X-API-Version: YYYY-MM` | 客户端可选指定, 默认 latest |
| Breaking change | 提前 90 天公告 + 新路径 + 双轨运行 |
| Deprecation header | `Deprecation: true` + `Sunset: Sat, 01 Jan 2028 00:00:00 GMT` |

---

## 10. 验证清单 (P10R4-2 §必跑测试)

| # | 验证 | 命令 | 预期 |
|---|------|------|------|
| 1 | OpenAPI 可访问 | `curl http://localhost:8000/openapi.json \| jq .info.title` | `"Nanobot Factory IMDF API"` |
| 2 | Swagger UI | `curl -I http://localhost:8000/docs` | `200 OK, text/html` |
| 3 | /healthz | `curl http://localhost:8000/healthz` | `{"status":"ok",...}` |
| 4 | /readyz | `curl http://localhost:8000/readyz` | `{"checks":{"database":{"ok":true,...}}}` |
| 5 | /metrics | `curl http://localhost:8000/metrics \| head -5` | Prometheus exposition format |
| 6 | 401 unauth | `curl http://localhost:8000/api/v1/users/me` | `401` + `WWW-Authenticate: Bearer` |
| 7 | Token issue | `curl -X POST .../auth/token -d '{"api_key":"bad"}'` | `401` |
| 8 | Validation 422 | POST 缺字段 | `422` + Pydantic errors |
| 9 | 429 rate limit | 1000x fast requests | 部分 `429` + `Retry-After` |
| 10 | 12 svc /healthz | for port in 8001..8012: curl /healthz | 全部 `{"status":"ok"}` |

