# P7-1 v2: Action Items (Retry 校正, 7 P0 + 5 P1 + 25 P2)

> **Date**: 2026-06-26 04:30
> **Auditor**: Coder (Mavis worker) + Auditor 反馈校正
> **Source**: P6-Fix 5 回归 + 12 service × 12 维度 + 6 新隐藏问题

---

## P0 — Blocker (7 项, 工时 < 1 周)

### P0-1: JWT fail-fast in gateway (F-004 升 P0)

**Severity**: P0 (生产可被弱密钥 `imdf_secret_change_me` 攻破)
**Effort**: 1 hr
**File**: `backend/gateway/main.py:103-107`

**Action**:
```python
def _jwt_secret() -> str:
    sec = (
        os.environ.get("JWT_SECRET_KEY", "").strip()
        or os.environ.get("JWT_SECRET", "").strip()
    )
    if sec in ("imdf_secret_change_me", "change-me-in-production", ""):
        if os.environ.get("IMDF_TEST_MODE", "").lower() in ("1", "true", "yes"):
            return "test-secret-gateway-p7-1-v2"
        raise RuntimeError(
            "JWT_SECRET_KEY environment variable is required "
            "(refusing to start with insecure default). "
            "Set IMDF_TEST_MODE=1 for local dev."
        )
    return sec
```

### P0-2: Redis rate limit 切多副本 (F-005 升 P0)

**Severity**: P0 (k8s HPA 2-3 副本即限流失效)
**Effort**: 2-3 days
**Files**:
- 新建 `backend/gateway/middleware/redis_rate_limit.py`
- 改 `backend/gateway/middleware/rate_limit.py` (factory)
- 改 `backend/gateway/routes.yaml` (RATE_LIMIT_BACKEND env)

**Action**: Redis `INCR` + `EXPIRE` 实现, Redis 不可用降级为本地 in-memory + WARNING log

### P0-3: routes.yaml dedupe + 8765 dead route 修复 (F-002 + P0-4 合并)

**Severity**: P0 (L208 dataset → 8765 broken 路由黑洞)
**Effort**: 30 min
**File**: `backend/gateway/routes.yaml`

**Action**:
```diff
--- routes.yaml
+++ routes.yaml
@@ L208-258 (8 个指向 8765/internal 的路由)
-  - name: dataset-service
-    prefix: /api/v1/datasets
-    upstream: http://127.0.0.1:8765/internal
-    ...
-  - name: annotation-misc
-    prefix: /api/v1/annotation
-    upstream: http://127.0.0.1:8765/internal
-    ...
-  - name: crowd-service
-    ...
-  # etc. 8 个 8765 路由全部删除或重新指向真正 service
+  # P0-4: 8765 port 由 svchost 占用, 8 个路由 502
+  # 解决: 重启 monolith 进程 OR 移除 dead routes OR 改 upstream
+
@@ L262, L269 (2 个 agent-service cosmetic 重复)
-  # ===== P3-3-W1: agent-service (port 8008) =====
-  - name: agent-service
-    prefix: /api/v1/agents
-    upstream: http://127.0.0.1:8008
-    ...
-  - name: agent-service
-    prefix: /api/v1/agent_tasks
-    upstream: http://127.0.0.1:8008
-    ...
```

**P0-4 关联**: 8765 port 解决后, 8 个 dead routes 才能正常工作。
**选项 A**: 重启 monolith 进程, 让 8765 真正工作
**选项 B**: 删除 8 个 dead routes, 业务改用其他 service endpoint
**选项 C**: 改 upstream 到对应 service (e.g. /api/v1/crowd → 新建 crowd-service:8013)

### P0-4: 8765 port 修复 (NEW, Auditor 发现)

**Severity**: P0 (8 dead routes 全部 broken, WSAEADDRINUSE)
**Effort**: 2 hr
**File**: routes.yaml + 重启 monolith

**实测**:
```
Get-NetTCPConnection -LocalPort 8765 → svchost.exe 4868 (Windows 系统进程, 不是 Python monolith)
curl http://127.0.0.1:8765/api/v1/queue/healthz → "远程服务器关闭了连接"
```

**Action**:
1. 确认 monolith 进程是否在跑 (start_server.ps1 / start_all_services.ps1)
2. 若未跑, 启动 monolith 进程
3. 若不需要, 删除 8 个 8765 routes
4. 验证: 8 个路由都返回真 200 + 业务数据

### P0-5: K8s NetworkPolicy 限制 service 直连 (NEW, Auditor 发现)

**Severity**: P0 (service 直连公网可绕过 gateway 鉴权)
**Effort**: 1 day
**File**: 新建 `k8s/network-policies.yaml`

**实测**:
```bash
curl -H "X-User: admin" http://127.0.0.1:8001/api/v1/users
→ 200 (auth 0 强制, 业务旁路 gateway)
```

**Action**:
```yaml
# k8s/network-policies.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-direct-service-access
  namespace: nanobot-factory
spec:
  podSelector: {}
  policyTypes:
    - Ingress
  ingress:
    # Only gateway pod can access service pods
    - from:
        - podSelector:
            matchLabels:
              app: gateway
      ports:
        - protocol: TCP
          port: 8001  # user-service
        - protocol: TCP
          port: 8002  # asset-service
        # ... 12 services
---
# K8s Service type=ClusterIP (default), 不暴露 NodePort
# 外部访问只能通过 gateway Service (type=LoadBalancer) + Ingress
```

### P0-6: JWT verify_aud=True (NEW, Auditor 发现)

**Severity**: P0 (token 跨服务重放)
**Effort**: 1 hr
**File**: `backend/gateway/main.py:115-121`, `backend/common/auth.py:240`

**实测**:
```python
# backend/gateway/main.py:115-121
_jose_jwt.decode(
    token,
    _jwt_secret(),
    algorithms=["HS256"],
    options={"verify_aud": False},  # ← 危险
)
```

**Action**:

```python
# 1. JWT 签发加 aud claim (auth.py:232-240)
def issue_access_token(username, role="viewer", ttl_minutes=None):
    ...
    payload = {
        "sub": username,
        "role": role,
        "aud": "nanobot-factory",  # ← 新增
        "type": "access",
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl * 60,
    }
    return jwt.encode(payload, _secret(), algorithm=_algo())

# 2. gateway 验签 verify_aud=True (gateway/main.py:115-121)
_jose_jwt.decode(
    token,
    _jwt_secret(),
    algorithms=["HS256"],
    audience="nanobot-factory",  # ← 强制验证
)
```

### P0-7: /openapi.json /docs 公网暴露 (NEW, Auditor 发现)

**Severity**: P0 (暴露 12 service 全部内部 endpoint 给公网)
**Effort**: 4 hr
**File**: K8s Ingress + Service type=ClusterIP

**实测**:
```
curl http://127.0.0.1:8000/openapi.json → 200
curl http://127.0.0.1:8000/docs → 200
curl http://127.0.0.1:8001/openapi.json → 200 (service 直连)
curl http://127.0.0.1:8001/docs → 200
```

**Action**:
1. K8s 12 service Service type=ClusterIP (default), 不暴露 NodePort
2. 仅 gateway Service type=LoadBalancer + Ingress 暴露 :80/:443
3. Ingress 加 `nginx.ingress.kubernetes.io/whitelist-source-range` 限定 client IP
4. 验证: `curl <公网 IP>/api/v1/users` 走 gateway → 401 无 auth;
         `curl <公网 IP>:8001/api/v1/users` → connection refused (ClusterIP 不暴露)

---

## P1 — Important (5 项, 工时 1-2 周)

### P1-1: DB pool_size 显式配置 + pool metrics (NEW, Auditor 发现)

**Severity**: P1 (12 service 部署到 Postgres 即连接耗尽)
**Effort**: 1 day
**File**: `backend/common/db.py:122` `_build_engine`

**实测**:
```python
# db.py:55 — 0 pool_size
return create_engine(
    db_url,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_pre_ping=True,
    # 缺: pool_size / max_overflow / pool_recycle / pool_timeout
)
```

**SQLAlchemy 默认**:
- pool_size = 5
- max_overflow = 10
- 每 service = 15 连接

**12 service × 15 = 180 个连接** → Postgres 默认 max_connections=100 → **第 7 service 起拒绝**

**Action**:
```python
# backend/common/db.py:122 (_build_engine)
def _build_engine(db_url: str) -> Engine:
    ...
    if db_url.startswith(("postgres", "postgresql")):
        try:
            from db.postgres import build_pg_engine_kwargs
            return create_engine(
                normalize_pg_url(db_url),
                **build_pg_engine_kwargs(url),
                pool_size=5,           # ← 显式
                max_overflow=10,       # ← 显式
                pool_recycle=3600,     # 1 hr 回收
                pool_timeout=30,       # 30s 等连接
                pool_pre_ping=True,
            )
        ...

# P1-1.2: pool metrics 暴露 Prometheus
from prometheus_client import Gauge
DB_POOL_SIZE = Gauge("db_pool_size", "Pool size", ["service"])
DB_POOL_CHECKED_OUT = Gauge("db_pool_checked_out", "Checked out", ["service"])
DB_POOL_OVERFLOW = Gauge("db_pool_overflow", "Overflow", ["service"])

@event.listens_for(engine, "checkout")
def _on_checkout(dbapi_conn, conn_record, conn_proxy):
    DB_POOL_CHECKED_OUT.labels(service=os.environ.get("SERVICE_NAME")).inc()

@event.listens_for(engine, "checkin")
def _on_checkin(dbapi_conn, conn_record):
    DB_POOL_CHECKED_OUT.labels(service=os.environ.get("SERVICE_NAME")).dec()
```

### P1-2: OSS 模块 5 NotImplementedError 实现 (NEW, Auditor 发现)

**Severity**: P1 (生产 OSS upload/download/sign 不可用)
**Effort**: 1 week
**File**: `backend/oss_manager.py:61/78/95/119/136`

**实测**:
```
oss_manager.py:61  raise NotImplementedError("必须由具体的AI服务实现")
oss_manager.py:78  raise NotImplementedError
oss_manager.py:95  raise NotImplementedError
oss_manager.py:119 raise NotImplementedError
oss_manager.py:136 raise NotImplementedError
```

**Action**: 实现 5 个 stub:
1. `upload (L61)` → Aliyun OSS / AWS S3 SDK
2. `download (L78)` → 同上
3. `delete (L95)` → 同上
4. `sign_url (L119)` → presigned URL
5. `list_objects (L136)` → 同上

### P1-3: workflow_service DAGRuntime 持久化 (NEW, Auditor 发现)

**Severity**: P1 (service 重启 = workflow run state 丢失)
**Effort**: 1 week
**File**: `backend/services/workflow_service/dag.py:206`

**实测**:
```python
# dag.py:206
class DAGRuntime:
    def __init__(self) -> None:
        self._workflows: Dict[str, WorkflowSpec] = {}
        self._runs: Dict[str, WorkflowRun] = {}  # ← in-memory
```

**Action**: 用 SQLite 替代 `Dict[str, WorkflowRun]`
```python
# dag.py:206
class DAGRuntime:
    def __init__(self, db_url: str = "sqlite:///data/workflows.db"):
        from sqlalchemy import create_engine, Table, Column, String, JSON, DateTime
        self.engine = create_engine(db_url)
        # create_all workflows + runs tables
```

### P1-4: OpenTelemetry + W3C Trace Context

**Severity**: P1 (跨 service 追踪不可见)
**Effort**: 1 week
**Files**: 新建 `backend/common/observability.py`

**Action**:
```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor


def setup_otel(app, service_name, otlp_endpoint="localhost:4317"):
    provider = TracerProvider()
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument()


def propagate_traceparent(request):
    return request.headers.get("traceparent", "")
```

### P1-5: F-001 require_role 死代码清理 (P0→P1 降级)

**Severity**: P1 (v1 Producer 标 P0, Auditor 校正 P3, v2 保守 P1)
**Effort**: 1 hr
**File**: `backend/common/auth.py:188-203`

**实测**:
- 0 service 真实调用 `require_role` (grep 全 backend 仅 3 hits, 全在 auth.py)
- 12 service 全部用 `require_role_dep` (正确版本)
- 误调概率 0

**Action (Option A - 彻底删除)**:
```python
# 1. 删除 L188-203 require_role 函数
# 2. 从 L245 __all__ 移除
# 3. 验证: from common.auth import require_role → ImportError
```

**Action (Option B - 降级为 alias)**:
```python
def require_role(*allowed_roles: str):
    """DEPRECATED: use require_role_dep instead. Will be removed in v0.9.0."""
    import warnings
    warnings.warn(
        "require_role is deprecated, use require_role_dep instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return require_role_dep(*allowed_roles)
```

**推荐 Option B** (向后兼容, 给下游时间迁移)

---

## P2 — Nice-to-have (25 项, 工时 3 月)

### P2 改进项 (按维度)

#### 测试覆盖 (9 项, 工时 4 weeks)
- P2-1: user_service 补基础 unit test
- P2-2: asset_service 补基础 unit test
- P2-3: annotation_service 补基础 unit test
- P2-4: scoring_service 补基础 unit test
- P2-5: dataset_service 补基础 unit test
- P2-6: evaluation_service 补基础 unit test
- P2-7: notification_service 补基础 unit test
- P2-8: search_service 补基础 unit test
- P2-9: collection_service 补基础 unit test

#### 跨 service (3 项, 工时 2 weeks)
- P2-10: 跨 service 集成测试 (5+ 流程)
- P2-11: chaos engineering (chaos-mesh)
- P2-12: 公开 OpenAPI schema (P6-1 已规划)

#### 弹性 (4 项, 工时 1 month)
- P2-13: graceful shutdown drain in-flight request
- P2-14: idempotency keys (P1-8 webhooks 已有 retry 但无 idempotency)
- P2-15: bulkhead 隔离 (thread pool per route)
- P2-16: exception 转 retry-after header (5xx → Retry-After)

#### 可观测性 (3 项, 工时 2 weeks)
- P2-17: alert rules (ServiceDown / HighErrorRate / HighLatency)
- P2-18: DB connection pool metrics 暴露
- P2-19: 业务 KPI dashboard (Grafana)

#### 配置 / Secret (2 项, 工时 1 week)
- P2-20: secret rotation 支持 (kid claim)
- P2-21: feature flag 框架 (LaunchDarkly / 自实现)

#### K8s / 部署 (2 项, 工时 1 week)
- P2-22: K8s ResourceQuota
- P2-23: K8s NetworkAttachmentDefinition (CNI 多网卡)

#### 限流 (2 项, 工时 1 week)
- P2-24: 限流 per-route 维度 (e.g. upload vs read)
- P2-25: 限流降级策略 (Redis 不可用 → 本地 in-memory + warning)

---

## Effort Roll-up (v2 Retry)

| Priority | Items | Total Effort | Calendar Time |
|---|---|---|---|
| P0 | 7 | ~1 week (F-005 2-3 days 大头) | 1 week |
| P1 | 5 | ~5 weeks (DB pool + OSS + DAG + OTel + F-001) | 5 weeks |
| P2 | 25 | ~12 weeks (9 service tests + 跨 service + 弹性 + 可观测) | 3 months |
| **TOTAL** | **37** | **~18 weeks** | **~5 months** |

---

## Suggested Sprint Plan (v2 Retry 校正)

### Sprint 1 (本周, ~1 周)
- **P0-1** (F-004): JWT fail-fast (1 hr)
- **P0-3** (F-002): routes.yaml dedupe (30 min)
- **P0-4**: 8765 port 修复 (2 hr)
- **P0-6**: JWT verify_aud=True (1 hr)
- **P0-7**: /openapi.json /docs K8s Ingress 限定 (4 hr)
- **P0-5**: K8s NetworkPolicy (1 day)
- **P0-2** (F-005): Redis rate limit (2-3 days)

### Sprint 2 (下周)
- **P1-5**: F-001 require_role 死代码清理 (1 hr)
- **P1-1**: DB pool_size + metrics (1 day)
- **P1-2**: OSS stub 实现 (1 week)

### Sprint 3-4 (1 月)
- **P1-3**: workflow DAGRuntime 持久化 (1 week)
- **P1-4**: OpenTelemetry + W3C Trace Context (1 week)

### Sprint 5-8 (2-3 月)
- **P2-1~25**: 25 项 P2 改进

---

## v1 → v2 关键差异 (Action Items)

| 项 | v1 Producer | v2 Auditor 校正 |
|---|---|---|
| P0-1 JWT fail-fast | LOW → P0 | LOW → P0-1 (P6-1 LOW 升 P0) |
| P0-2 Redis rate limit | MEDIUM → P0 | MEDIUM → P0-2 (校正) |
| P0-3 routes.yaml dedupe | LOW → P0 | LOW → P0-3 (含 8765 合并) |
| P0-4 8765 svchost | 未提 | **NEW P0-4** |
| P0-5 K8s NetworkPolicy | 未提 | **NEW P0-5** |
| P0-6 JWT verify_aud | 未提 | **NEW P0-6** |
| P0-7 /openapi.json 公网暴露 | 未提 | **NEW P0-7** |
| P1-1 DB pool_size | 未提 | **NEW P1-1** |
| P1-2 OSS stub | 提了未量化 | **NEW P1-2** (5 stub 量化) |
| P1-3 DAG 持久化 | 提了 | **NEW P1-3** (升 P2→P1) |
| P1-4 OTel | P1 | P1-4 (保留) |
| P1-5 F-001 require_role | P0 | P0 → **P1-5** (降级) |

---

**Action Items 完成**: 2026-06-26 04:30 (Asia/Shanghai)
