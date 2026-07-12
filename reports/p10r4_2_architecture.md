# P10R4-2: 架构文档 (System Architecture · 12 微服务 + DB + OSS + 监控)

> **Date**: 2026-06-26 13:55 (Asia/Shanghai)
> **Author**: coder (P10R4-2 worker)
> **Sources**: `docs/architecture.md` (权威 15KB) + `deploy/bare_metal/README.md` + 实际 inventory + P9-5 perf report

---

## 1. 系统总览 (System Topology)

```
                    ┌──────────────────────────────────────────────┐
                    │  nginx (80/443)  · public traffic + static   │
                    └────────────────────┬─────────────────────────┘
                                         │ HTTP
                                ┌────────▼──────────┐
                                │  imdf-gateway     │  :8000 (4 uvicorn workers)
                                │  FastAPI + CORS   │
                                │  + RateLimit      │
                                │  + JWT auth       │
                                │  + Prometheus mw  │
                                └────────┬──────────┘
                                         │ HTTP (internal)
        ┌────────┬────────┬─────────┬─────┴───────┬─────────┬────────┐
        │        │        │         │             │         │        │
   imdf-user imdf-asset imdf-annot imdf-clean  imdf-score imdf-data imdf-eval
   :8001     :8002     :8003     :8004        :8005     :8006     :8007

   imdf-agent imdf-workflow imdf-notif imdf-search imdf-collection
     :8008      :8009        :8010     :8011      :8012

        ┌──────────────────┐         ┌─────────────────────────┐
        │ imdf-celery      │ ──────▶ │  Redis 7  (broker+state) │
        │ imdf-celery-beat │         │  + Celery result backend │
        └──────────────────┘         └─────────────────────────┘

        ┌──────────────────┐         ┌─────────────────────────┐
        │ PostgreSQL 15    │         │  MinIO (S3-compatible)  │
        │ + pgvector       │         │  :9000 API / :9001 UI   │
        └──────────────────┘         └─────────────────────────┘

        ┌──────────────────────────────────────────────────────┐
        │ Prometheus :9090   ·   Grafana :3000 (8 dashboards)  │
        │ Jaeger    :16686   ·   Loki :3100 · Promtail         │
        │ Alertmanager :9093 (21 alert rules)                  │
        └──────────────────────────────────────────────────────┘
```

---

## 2. 12 微服务职责矩阵

| Service | Port | 路径前缀 | 业务边界 | 状态/无状态 |
|---------|------|---------|---------|------------|
| **imdf-gateway** | 8000 | `/api/*`, `/airi/*`, `/omni/*`, `/ws/*` | 路由 + 鉴权 + 限流 | **有状态** (in-flight rate limit) |
| imdf-user | 8001 | `/api/v1/users/*`, `/api/v1/auth/*` | 认证 / 用户 / 多租户 | 无状态 |
| imdf-asset | 8002 | `/api/v1/assets/*` | 资产上传 / 下载 / 元数据 | 无状态 (OSS 状态外部) |
| imdf-annotation | 8003 | `/api/v1/annotations/*` | 5 类标注 + IAA | 无状态 |
| imdf-cleaning | 8004 | `/api/v1/cleaning/*` | 去重 / 质量 / 脱敏 | 异步 (Celery) |
| imdf-scoring | 8005 | `/api/v1/scoring/*` | 美学 / 质量 / 安全评分 | 异步 (Celery) |
| imdf-dataset | 8006 | `/api/v1/datasets/*` | 数据集版本 + 导出 | 无状态 |
| imdf-evaluation | 8007 | `/api/v1/evaluation/*` | 模型评测 + BadCase | 异步 |
| imdf-agent | 8008 | `/api/v1/agents/*`, `/mcp/*`, `/memory/*` | **15 Agent + MCP + MemoryPalace + Hindsight** | **有状态** (memory 持久化) |
| imdf-workflow | 8009 | `/api/v1/workflows/*`, `/dag/*` | DAG v2 工作流 + Visual Editor | 异步 |
| imdf-notification | 8010 | `/api/v1/notifications/*`, `/ws/notifications` | 站内信 + 邮件 + WS 推送 | **有状态** (WS connection) |
| imdf-search | 8011 | `/api/v1/search/*` | FTS + 向量 (pgvector) | 无状态 |
| imdf-collection | 8012 | `/api/v1/collection/*` | HTTP/S3/OSS 拉取 | 异步 (Celery) |

旁路 worker (不占端口):
- **imdf-celery** — 5 queues (default / video / cpu / index / network), concurrency 4
- **imdf-celery-beat** — 周期任务 (P0/P1 cron + WebSocket 心跳)

---

## 3. 数据流 (Pipeline)

```
   ┌─────────────┐  采集  ┌─────────────┐  清洗  ┌─────────────┐
   │   User      │ ─────▶ │ collection  │ ─────▶ │  cleaning   │
   │  (upload)   │        │  :8012      │        │   :8004     │
   └─────────────┘        └──────┬──────┘        └──────┬──────┘
                                 │                      │
                                 ▼                      ▼
                          ┌──────────────┐       ┌──────────────┐
                          │  OSS (MinIO) │       │ PostgreSQL   │
                          │  + metadata  │       │  assets +    │
                          │  in PG       │       │  cleaning_   │
                          │              │       │  rules       │
                          └──────┬───────┘       └──────┬───────┘
                                 │                      │
                                 ▼                      ▼
   ┌─────────────┐  预标注  ┌──────────────┐   精标  ┌──────────────┐
   │  prelabel   │ ◀────── │ annotation   │ ──────▶ │ annotation   │
   │  agent      │         │   :8003      │         │   :8003      │
   │             │         │  (draft)     │         │  (final)     │
   └─────────────┘         └──────┬───────┘         └──────┬───────┘
                                 │                        │
                                 ▼                        ▼
                          ┌──────────────┐         ┌──────────────┐
                          │  scoring     │         │   review     │
                          │   :8005      │         │  (reviewer)  │
                          │              │         │  approval    │
                          └──────┬───────┘         └──────┬───────┘
                                 │                        │
                                 ▼                        ▼
                          ┌──────────────────────────────────────┐
                          │  evaluation :8007 (mAP / FID / CLIP) │
                          │  + badcase cluster                   │
                          └────────────────┬─────────────────────┘
                                           │
                                           ▼
                          ┌──────────────────────────────────────┐
                          │  dataset :8006 (versioning + export) │
                          │  + COCO / YOLO / VOC / JSON / Parquet │
                          └────────────────┬─────────────────────┘
                                           │
                                           ▼
                          ┌──────────────────────────────────────┐
                          │  collection endpoint (管理)          │
                          │  + workflow DAG :8009 (reproducible) │
                          └──────────────────────────────────────┘
```

**关键节点**:
- 所有 stage 输出 → PostgreSQL 持久化 + OSS 持久化 (双写)
- 异步任务 (cleaning / scoring / evaluation) → Celery + Redis queue
- 评分后触发 evaluation 任务 (auto via Celery chain)
- 任意环节可触发 MemoryPalace 写入 (long-term memory)

---

## 4. 部署架构 (Bare-Metal systemd)

### 4.1 操作系统 / 硬件 (Tier B 标准 99.9% SLA)

| Role | CPU | RAM | Disk | Notes |
|------|-----|-----|------|-------|
| all-in-one dev | 8 cores | 32 GB | 1 TB SSD | Ubuntu 22.04 LTS |
| production (12 svc) | **16 cores** | **64 GB** | **2 TB SSD + 4 TB HDD** | Ubuntu 22.04 LTS |
| GPU AI ops | + RTX 4090 / A100 | + 24 GB VRAM | - | Optional, separate node |

### 4.2 systemd 单元分层

```yaml
# Layer 0: OS / 基础设施
  postgresql.service       # PG 15 + pgvector
  redis-server.service     # Redis 7 (broker + cache)
  minio.service            # S3-compatible OSS

# Layer 1: Observability
  prometheus.service       # :9090, scrape 12 svc + node-exporter
  alertmanager.service     # :9093, 21 alert rules
  grafana-server.service   # :3000, 8 dashboards
  jaeger.service           # :16686 (Jaeger UI) / :6831 (agent UDP)
  loki.service             # :3100 (ingest) / :9096 (push)
  promtail.service         # log shipper

# Layer 2: Application (依赖 Layer 0)
  imdf-gateway.service     # :8000 (4 workers)
  imdf-user.service        # :8001 (2 workers)
  imdf-asset.service       # :8002
  imdf-annotation.service  # :8003
  imdf-cleaning.service    # :8004
  imdf-scoring.service     # :8005
  imdf-dataset.service     # :8006
  imdf-evaluation.service  # :8007
  imdf-agent.service       # :8008 (4 workers, agent-heavy)
  imdf-workflow.service    # :8009
  imdf-notification.service# :8010
  imdf-search.service      # :8011
  imdf-collection.service  # :8012

# Layer 3: Async (依赖 Layer 0+2)
  imdf-celery.service      # 5 queues × concurrency 4
  imdf-celery-beat.service # scheduler

# 旁路: 备份 (systemd timer, 不在主链)
  imdf-backup.timer        # daily 03:00 + Sun 04:00
  imdf-backup.service      # 调用 backup_cron.sh
```

### 4.3 systemd 安全加固 (imdf-gateway.service 摘录)

```ini
[Service]
User=imdf
Group=imdf
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
ReadWritePaths=/opt/nanobot-factory/data /opt/nanobot-factory/logs

# Resource limits
LimitNOFILE=65536
MemoryMax=4G
MemoryHigh=3G
CPUQuota=400%

# Watchdog (30s) → Type=notify
WatchdogSec=30
NotifyAccess=main
```

### 4.4 健康探针 (K8s 风格)

| Endpoint | 用途 | 通过条件 |
|----------|------|---------|
| `GET /healthz` | Liveness | 进程存活 + 事件循环 OK |
| `GET /readyz` | Readiness | DB + Redis + Disk 全 OK |
| `GET /metrics` | Prometheus | exposition format |
| `GET /api/queue/health` | 队列健康 | Celery worker + Redis ping |

### 4.5 反向代理 (nginx)

```nginx
# /etc/nginx/sites-available/imdf
upstream imdf_gateway {
    server 127.0.0.1:8000 fail_timeout=0;
    keepalive 64;
}

server {
    listen 443 ssl http2;
    server_name imdf.example.com;

    # 1G upload limit (asset uploads)
    client_max_body_size 1G;

    # Rate limit
    limit_req_zone $binary_remote_addr zone=auth:10m rate=10r/m;
    location /api/auth/ {
        limit_req zone=auth burst=5 nodelay;
        proxy_pass http://imdf_gateway;
    }

    location / {
        proxy_pass http://imdf_gateway;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket upgrade
    location /ws/ {
        proxy_pass http://imdf_gateway;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 5. 安全架构

### 5.1 5 层防御

```
Layer 1: 边缘 (nginx)
  - TLS 1.3 (Let's Encrypt certbot)
  - /api/auth/* rate-limit 10 req/min/IP
  - client_max_body_size 1G
  - OWASP CRS (optional modsec)

Layer 2: 网关 (imdf-gateway :8000)
  - JWT 验证 (HS256, 32-byte secret)
  - RBAC 5 角色 (admin/manager/reviewer/annotator/viewer)
  - 多租户隔离 (X-Tenant-ID + row-level security)
  - Rate limit (per-IP / per-user / per-tenant)
  - CORS whitelist
  - Prometheus 中间件

Layer 3: 服务 (12 svc)
  - Pydantic 校验 (Request body / Query / Path)
  - 业务校验 (业务规则 + 状态机)
  - SQL 注入防护 (ORM / parameterized query)

Layer 4: 数据 (PG + Redis + OSS)
  - PostgreSQL row-level security (tenant_id 隔离)
  - Redis ACL (per-service key prefix)
  - OSS bucket policy (private + signed URL)
  - 加密: at-rest LUKS, in-transit TLS

Layer 5: 审计 (audit_chain)
  - 不可篡改日志 (Merkle chain, 每条 entry hash + prev_hash)
  - 90 天本地 + 365 天 OSS 归档
```

### 5.2 OWASP Top 10 覆盖 (P10R4-1 验证 PASS)

| OWASP | 状态 | 关键控制 |
|-------|------|---------|
| A01 Broken Access Control | ✅ | JWT + RBAC + tenant_id RLS |
| A02 Cryptographic Failures | ✅ | bcrypt 密码 + AES-256-GCM OSS + TLS 1.3 |
| A03 Injection | ✅ | ORM 全参化 + Pydantic + SSRF 3 层防御 |
| A04 Insecure Design | ✅ | Threat model + STRIDE review |
| A05 Security Misconfig | ✅ | systemd hardening + CIS benchmark |
| A06 Vulnerable Components | ✅ | bandit B-级 0, pip-audit 0 CVE |
| A07 Auth Failures | ✅ | JWT TTL 24h + refresh + revoke + brute force lock |
| A08 Software/Data Integrity | ✅ | audit_chain Merkle + signature verification |
| A09 Logging Failures | ✅ | Loki 聚合 + Sentry/structlog + 21 alert |
| A10 SSRF | ✅ | IP 黑名单 + DNS 解析阻断 + 出口 firewall |

---

## 6. Agent 架构 (P9-2 已建)

### 6.1 5 层架构

```
┌────────────────────────────────────────────────────────────┐
│  Layer 5: 应用                                              │
│  - MasterAgent (orchestrator)                              │
│  - ReflexionAgent (self-evolution)                         │
│  - WorkflowOrchestrator                                    │
└──────────────────┬─────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────┐
│  Layer 4: Multi-Agent 协作                                │
│  - DispatcherAgent (任务派发)                              │
│  - ClusterManager (sub-agent 注册 + 负载均衡)             │
└──────────────────┬─────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────┐
│  Layer 3: 领域 Agent                                       │
│  - 15 主 Agent (requirement → quality)                     │
│  - 36 派生 Agent (CanvasAgent × 10 + Director/Storyboard +) │
└──────────────────┬─────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────┐
│  Layer 2: BaseAgent (抽象基类)                             │
│  - backend/imdf/agents/base.py:123                         │
│  - 生命周期: init → plan → execute → reflect → done        │
│  - Plugin 注入: memory / tool / skill / hindsight          │
└──────────────────┬─────────────────────────────────────────┘
                   │
┌──────────────────▼─────────────────────────────────────────┐
│  Layer 1: 基础设施                                         │
│  - PluginRegistry (40+ plugin slots)                       │
│  - MemoryPalace (long-term memory, semantic recall)        │
│  - Hindsight (reflective journal)                          │
│  - MCP Bridge (Model Context Protocol)                     │
│  - Tool/Skill Marketplace                                  │
└────────────────────────────────────────────────────────────┘
```

### 6.2 15 主 Agent 流水线

| 顺序 | Agent | 默认优先级 | 下游服务 |
|------|-------|----------|---------|
| 1 | requirement_parser | 9 | imdf-agent |
| 2 | data_collection | 7 | imdf-collection |
| 3 | cleaning | 6 | imdf-cleaning |
| 4 | prelabel | 5 | imdf-annotation |
| 5 | fine_annotation | 4 | imdf-annotation |
| 6 | review | 8 | imdf-evaluation |
| 7 | scoring | 5 | imdf-scoring |
| 8 | filtering | 5 | imdf-dataset |
| 9 | export | 3 | imdf-dataset |
| 10 | evaluation | 6 | imdf-evaluation |
| 11 | badcase_analysis | 7 | imdf-evaluation |
| 12 | feedback | 4 | imdf-notification |
| 13 | memory | 3 | imdf-agent (MemoryPalace) |
| 14 | scheduling | 8 | imdf-agent (Scheduler) |
| 15 | quality | 9 | imdf-evaluation |

### 6.3 4 大子系统

#### MemoryPalace (记忆宫殿)

```python
# 抽象层 (backend/agent/memory_palace.py)
class MemoryPalace:
    async def store(self, key: str, value: any, ttl: int = 86400*30):
        """向量化存储 (pgvector) + 持久化到 PG + Redis 缓存"""
    
    async def recall(self, query: str, k: int = 10, threshold: float = 0.7):
        """向量检索 + 时间衰减 (recency weight)"""
    
    async def forget(self, key: str):
        """软删除 (墓碑 30 天后清理)"""
```

#### Hindsight (反思日志)

```python
# 抽象层 (backend/agent/hindsight.py)
class Hindsight:
    async def record(self, task_id: str, agent: str, decision: str, outcome: str):
        """记录决策-结果对,用于后续 RLHF / 离线分析"""
    
    async def analyze(self, period: timedelta = timedelta(days=7)):
        """聚合分析: 决策模式 / 成功率 / 失败根因"""
```

#### PluginRegistry (40+ 插槽)

```python
# 抽象层 (backend/agent/plugin_registry.py)
class PluginRegistry:
    SLOTS = {
        "memory": MemoryPalace,
        "hindsight": Hindsight,
        "tool_executor": ToolExecutor,
        "skill_runner": SkillRunner,
        "model_caller": ModelCaller,
        "vector_search": VectorSearch,
        # ... 35+ more
    }
```

#### MCP (Model Context Protocol)

```python
# 抽象层 (backend/agent/mcp_bridge.py)
class MCPBridge:
    async def list_tools(self) -> list[Tool]:
        """获取所有可用 MCP tool (含外部 server)"""
    
    async def invoke(self, tool_name: str, args: dict) -> any:
        """调用 MCP tool, 带 OAuth 鉴权"""
    
    async def list_resources(self) -> list[Resource]:
        """列出 MCP resource (含 file/db)"""
    
    async def list_prompts(self) -> list[PromptTemplate]:
        """列出 prompt 模板"""
```

---

## 7. 数据模型 (PostgreSQL 15 + pgvector)

### 7.1 核心表 (简版)

```sql
-- 租户 / 用户
tenants (id, name, plan, created_at)
users   (id, tenant_id, email, role, hashed_pwd, created_at)
sessions(id, user_id, jwt_jti, expires_at)

-- 资产
assets  (id, tenant_id, sha256, size, kind, mime, url, tags[], metadata jsonb, created_at, deleted_at)

-- 标注
annotations (id, asset_id, annotator_id, type, payload jsonb, labels[], status, version, created_at)

-- 数据集
datasets (id, tenant_id, name, latest_version, created_at)
dataset_versions (id, dataset_id, version, manifest jsonb, immutable, created_at)

-- Agent
agent_types (id, name, capabilities, default_priority, downstream_service)
agent_tasks (id, agent_type, status, payload, result, started_at, finished_at)

-- Memory
memory_entries (id, tenant_id, vector vector(1024), content, importance, created_at, expires_at)
hindsight_logs (id, task_id, agent, decision, outcome, score, created_at)

-- Workflow
workflows   (id, tenant_id, name, dag jsonb, version, created_at)
workflow_runs(id, workflow_id, status, started_at, finished_at, logs jsonb)

-- 商业化
subscriptions (id, tenant_id, plan, status, current_period_end)
payments      (id, tenant_id, amount, currency, provider, status, idempotency_key)
invoices      (id, tenant_id, amount, vat_amount, status, pdf_url)
contracts     (id, tenant_id, counterparty, terms, signed_at, expires_at)
crm_leads     (id, tenant_id, contact, score, status, owner_id)
tickets       (id, tenant_id, subject, priority, status, sla_deadline, assignee_id)

-- 审计
audit_chain (id, prev_hash, hash, actor, action, target, timestamp)
```

### 7.2 向量索引 (pgvector)

```sql
-- HNSW 索引 (cosine distance)
CREATE INDEX idx_memory_vector ON memory_entries 
USING hnsw (vector vector_cosine_ops) WITH (m=16, ef_construction=64);

-- ANN 查询
SELECT id, content, 1 - (vector <=> $1) AS similarity
FROM memory_entries
WHERE tenant_id = $2
ORDER BY vector <=> $1
LIMIT 10;
```

---

## 8. 监控架构

### 8.1 指标流向

```
12 imdf-* svc ──┐
PG/Redis/MinIO  ├──▶ Prometheus (:9090) ──▶ Grafana (:3000)
node-exporter   │                    │
GPU exporter    │                    ├──▶ Alertmanager (:9093)
                 │                    │     └─▶ Slack / PagerDuty / 飞书
                 │
                 ├──▶ Jaeger (distributed tracing)
                 │
                 └──▶ Loki (log aggregation)
                      └─▶ Grafana Loki data source
```

### 8.2 8 个 Grafana Dashboard / 92 panels

| Dashboard | 面板数 | 主题 |
|-----------|--------|------|
| ai_business.json | 14 | 模型调用 / 成本 / 缓存 / Token |
| dashboard-vdp-ai.json | 14 | AI 业务总览 (与 ai_business 镜像) |
| dashboard-vdp-business.json | 10 | 微服务 (12 svc QPS / 延迟 / 错误) |
| dashboard-vdp-infrastructure.json | 13 | DB / Redis / OSS 性能 |
| dashboard-vdp-overview.json | 9 | 全站总览 (流量 / 资源 / SLA) |
| database.json | 13 | PG 详情 (连接池 / 复制 / VACUUM) |
| microservices.json | 10 | 微服务 (镜像 vdp-business) |
| overview.json | 9 | 全站 (镜像 vdp-overview) |
| **TOTAL** | **92** | |

### 8.3 21 Prometheus 告警规则

**类别分布**:
| 类别 | 数量 | 规则 |
|------|------|------|
| Service-level | 7 | HighErrorRate / HighLatency / LowThroughput / GatewayDown / ServiceDown / ServiceRestartLoop / HighMemory |
| Resource | 5 | PostgresConnections / PostgresReplicationLag / RedisMemory / RedisDown / OSSBucketSize |
| Async | 1 | CeleryQueueBacklog |
| Business | 4 | PipelineFailureRate / BillingAnomaly / TicketSLABreach / MemoryPalaceCapacity |
| Skill | 1 | SkillMarketplaceAnomaly |
| Security | 3 | LoginFailureBurst / RateLimitTriggered / AuditChainBroken |

---

## 9. 数据流详图 (WebSocket 实时协同)

```
   User A (browser)                    User B (browser)
       │                                    │
       │ WS /ws/canvas/sess_xxx             │ WS /ws/canvas/sess_xxx
       │                                    │
       └──────────────┬─────────────────────┘
                      │
              ┌───────▼────────┐
              │  nginx (WSS)   │
              └───────┬────────┘
                      │
              ┌───────▼────────┐
              │ imdf-gateway   │ ← JWT 验证 + tenant 隔离
              │   :8000        │
              └───────┬────────┘
                      │ broadcast (Redis pub/sub)
              ┌───────▼────────┐
              │  Redis 7       │ ← canvas:{session_id} channel
              └───────┬────────┘
                      │
              ┌───────▼────────┐
              │ imdf-workflow  │ ← 持久化 canvas_state (PG)
              │   :8009        │ ← 异步落盘 (Celery)
              └────────────────┘
```

---

## 10. 扩展性 (Scaling Patterns)

### 10.1 垂直扩展 (Scale Up)

```bash
# 单实例升级
sudo systemctl edit imdf-gateway
# 添加:
[Service]
MemoryMax=8G      # 4G → 8G
CPUQuota=800%     # 400% → 800% (8 cores)
```

### 10.2 水平扩展 (Scale Out — 应用层)

```bash
# 加 1 个 gateway worker 节点
# 1) 安装 + 配置 (重复 install.sh + .env)
# 2) nginx upstream 加新节点:
upstream imdf_gateway {
    server 10.0.1.10:8000;   # 原
    server 10.0.1.11:8000;   # 新
    keepalive 64;
}
# 3) sudo nginx -s reload
```

### 10.3 Celery 水平扩展

```bash
# 改 /etc/imdf/imdf.env
CELERY_CONCURRENCY=8       # 4 → 8
CELERY_QUEUES=default,video,cpu,index,network,priority   # 加队列

# 加 worker 节点
sudo -u imdf bash -c "cd /opt/nanobot-factory && \
  venv/bin/celery -A backend.imdf.celery_app:celery_app worker \
    --loglevel=info --concurrency=8 \
    --queues=default,video,cpu,index,network \
    --hostname=imdf-celery@worker-02"
```

### 10.4 DB 扩展 (P9-5 P0 路径)

```
Tier A (10K)  → SQLite WAL (current)
Tier B (100K) → PostgreSQL 15 + pgvector (P2-1 已落地)
Tier C (1M)   → PostgreSQL 主从 + pgbouncer + Redis cluster
```

---

## 11. 故障转移 (HA / DR)

### 11.1 应用层 (Active-Active)

- 12 svc 全部 stateless (除 imdf-notification WS / imdf-agent memory)
- WS state → Redis pub/sub (可水平扩)
- Memory → 持久化 PG (任意节点可读)

### 11.2 DB 层 (Active-Passive 主备)

```yaml
primary:
  host: pg-primary.imdf.local
  port: 5432
  replication: synchronous

standby:
  host: pg-standby.imdf.local
  port: 5432
  lag_threshold: 30s
  auto_failover: pg_auto_failover (or repmgr)
```

**RTO**: < 5 min (自动切换) · **RPO**: < 30s (sync rep)

### 11.3 OSS (Multi-AZ + Cross-Region)

```bash
# MinIO 多副本
mc admin replicate add minio-cluster https://minio-secondary:9000 \
   --access-key $MINIO_ACCESS --secret-key $MINIO_SECRET

# 或异地复制
mc mirror --preserve --quiet minio-primary/imdf-assets s3-cold-archive/imdf-assets/
```

**RPO**: 0 (同步多副本) · **RTO**: < 1 min (DNS 切换)

---

## 12. 参考文档

- `deploy/bare_metal/README.md` — 部署权威 (15KB)
- `docs/architecture.md` — 旧版架构 (15KB, 7 层图)
- `docs/sla.md` — SLA + RTO/RPO + 容量规划
- `docs/security.md` — OWASP + 5 层防御
- `reports/p9_5_performance.md` — 1000-并发基线
- `reports/p7_3_monitoring.md` — 监控深度 (4 dashboard 46 panels)
- `reports/p7_3_backup.md` — 3-tier 备份
- `reports/p7_3_deploy.md` — systemd 单元

