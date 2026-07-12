# P10R4-4 Tracing 深度审计 (Jaeger)

**报告**: Jaeger 跨服务 trace + OpenTelemetry SDK 状态 + Sampling 策略
**日期**: 2026-06-26

---

## 1. 总览

| 维度 | 状态 |
|---|---|
| OpenTelemetry SDK 安装 | **❌ 0/5 包** |
| 应用代码 tracer 初始化 | ✅ (但 no-op) |
| FastAPI auto-instrument | ❌ (HAS_OTEL_FASTAPI=False) |
| SQLAlchemy auto-instrument | ❌ (HAS_OTEL_SQLALCHEMY=False) |
| 手动 span 调用 (业务代码) | 1 处 (audit_chain) |
| 跨服务 trace propagation | ❌ |
| Tail-based sampling | ❌ |
| 业务维度 span attribute | ❌ (仅 service.name) |

**评分**: **D (40/100)** — 框架完整, 运行时 100% no-op。

---

## 2. OpenTelemetry SDK 安装状态

**实测启动日志** (smoke test):
```
2026-06-26T14:50:33 [INFO] monitoring.tracing: OpenTelemetry SDK not installed — tracing disabled
2026-06-26T14:50:33 [INFO] api.canvas_web: {"event": "Distributed tracing disabled (otel packages not installed)"}
```

`tracing.py:41-45` 5 个 feature flag 全部 False:

```python
HAS_OTEL_API = False
HAS_OTEL_SDK = False
HAS_OTEL_EXPORTER_OTLP = False
HAS_OTEL_FASTAPI = False
HAS_OTEL_SQLALCHEMY = False
```

**缺失 5 个包**:

| 包 | 必需 | 影响 |
|---|---|---|
| `opentelemetry-api` | 必需 | Tracer/Span/Context API |
| `opentelemetry-sdk` | 必需 | TracerProvider / BatchSpanProcessor |
| `opentelemetry-exporter-otlp-proto-grpc` | 必需 | OTLP gRPC push to Jaeger 4317 |
| `opentelemetry-instrumentation-fastapi` | 推荐 | FastAPI auto-span |
| `opentelemetry-instrumentation-sqlalchemy` | 推荐 | SQLAlchemy auto-span |
| `opentelemetry-instrumentation-redis` | 可选 | Redis auto-span |
| `opentelemetry-instrumentation-httpx` | 可选 | httpx out-call span |
| `opentelemetry-instrumentation-requests` | 可选 | requests out-call span |
| `opentelemetry-instrumentation-asyncpg` | 可选 | asyncpg span |

→ **0/9 包安装**, 即便装 4 个核心包也只能 manual span, auto-instrumentation 还需 5 个。

---

## 3. 应用代码 tracer 初始化路径

### 3.1 `tracing.py` (199 行)

`setup_tracing()` 函数逻辑:

```python
def setup_tracing(service_name=None, otlp_endpoint=None, sample_ratio=0.1) -> bool:
    with _init_lock:
        if _initialised:
            return True
        if not (HAS_OTEL_API and HAS_OTEL_SDK):
            logger.info("OpenTelemetry SDK not installed — tracing disabled")
            _initialised = True
            return False
        try:
            # 1. 资源 + provider
            resource = _Resource.create({"service.name": svc})
            provider = _TP(resource=resource)
            # 2. OTLP exporter (or Console fallback)
            if HAS_OTEL_EXPORTER_OTLP:
                exporter = _OTLP(endpoint=ep, insecure=True)
                provider.add_span_processor(_BSP(exporter))
            else:
                provider.add_span_processor(_BSP(_CSE()))
            # 3. Set global tracer provider
            _trace.set_tracer_provider(provider)
            return True
```

**IDempotent** (`_initialised` flag + `_init_lock`), 防止 uvicorn worker 多初始化。

### 3.2 `canvas_web.py:1062-1076` 启动调用

```python
try:
    from monitoring.tracing import setup_tracing, instrument_fastapi
    _tracing_ok = setup_tracing(
        service_name="imdf-main",
        otlp_endpoint=None,  # use env OTEL_EXPORTER_OTLP_ENDPOINT or default Jaeger
    )
    if _tracing_ok:
        _instrumented = instrument_fastapi(app)
        logger.info("Distributed tracing enabled: imdf-main (FastAPI instrumented=%s)", _instrumented)
    else:
        logger.info("Distributed tracing disabled (otel packages not installed)")
except Exception as _otel_err:
    logger.warning(f"OTel tracing setup failed: {_otel_err}")
```

→ `service_name="imdf-main"`, **其他 12 微服务未在自身 main.py 调 setup_tracing()** → 只 main app 有可能 trace, 12 svc 全部 0。

**12 svc main.py** (审计):
```
backend/services/*/main.py → grep 'setup_tracing' → 0 match
```

→ **12 svc 全部不初始化 tracer**, 即使 OTel SDK 装上, 跨服务 trace 也只有 main app 端。

### 3.3 默认 OTLP endpoint

`tracing.py:35-38`:
```python
OTLP_ENDPOINT = os.environ.get(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "http://jaeger-collector.monitoring.svc.cluster.local:4317",
)
```

→ 默认指向 K8s Service `jaeger-collector.monitoring.svc.cluster.local:4317`。但 `jaeger.yaml` 里的 service 实际命名是 `jaeger` (不是 `jaeger-collector`):

```yaml
# jaeger.yaml:88-114
apiVersion: v1
kind: Service
metadata:
  name: jaeger  # ← 实际命名
  namespace: monitoring
spec:
  ports:
    - name: otlp-grpc
      port: 4317
    ...
```

→ **默认 endpoint 与实际 K8s Service 命名不匹配**, 装 SDK 后还是会 push 失败。

正确 endpoint: `http://jaeger.monitoring.svc.cluster.local:4317`

---

## 4. NoopTracer 行为

`tracing.py:170-191`:

```python
class _NoopSpan:
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def set_attribute(self, key, value): pass
    def set_status(self, status): pass
    def record_exception(self, exc): pass
    def end(self): pass

class _NoopTracer:
    def start_as_current_span(self, name, **kwargs):
        return _NoopSpan()
    def start_span(self, name, **kwargs):
        return _NoopSpan()
```

→ 所有 `with tracer.start_as_current_span(...)` 调用返回 _NoopSpan, 不报错但**不生成任何数据**。

**应用代码适配性**:

```python
# imdf/engines/audit_chain.py:235
with _audit_tracer.start_as_current_span("audit.chain.append") as _span:
    ...
    _span.set_attribute("chain.length", len(chain))
    ...
```

✅ 代码兼容 noop (set_attribute 无副作用), 但生产环境无 trace 数据。

---

## 5. 关键路径 trace 完整性

### 5.1 `/api/chat` (gateway → agent → model → DB)

| 期望 span | 实测 | 状态 |
|---|---|---|
| gateway ingress | 无 | ❌ |
| FastAPI middleware | 无 (HAS_OTEL_FASTAPI=False) | ❌ |
| agent.dispatch | 无 | ❌ |
| model.call | 无 | ❌ |
| db.query | 无 (HAS_OTEL_SQLALCHEMY=False) | ❌ |
| cache.get | 无 | ❌ |
| audit.append | span 占位, 实际 noop | ⚠️ |
| response | 无 | ❌ |

→ **0/8 span 真有数据**, 即使装 SDK 也要 5+ instrumentation 包才能 auto-instrument。

### 5.2 `tool invocation` (agent → tools → audit)

| 期望 span | 实测 |
|---|---|
| agent.tool_call | 无 |
| tool.execute | 无 |
| audit.append | span 占位 |
| response | 无 |

→ **0/4 span**。

### 5.3 `pipeline execution` (workflow → 6 op → upload)

| 期望 span | 实测 |
|---|---|
| workflow.start | 无 |
| node.execute × N | 无 |
| db.commit | 无 |
| upload oss | 无 |

→ **0/N span**。

---

## 6. Span Attributes 完整性

### 6.1 当前唯一 attribute

`tracing.py:112`:
```python
resource = _Resource.create({"service.name": svc})
```

→ 只有 `service.name` (= "imdf-main")。

### 6.2 缺失的业务 attribute

| Attribute | 用途 | 影响 |
|---|---|---|
| `tenant_id` | per-tenant trace 查询 | ❌ |
| `user_id` | per-user trace | ❌ |
| `model` / `model.provider` | per-model trace | ❌ |
| `agent_id` | per-agent trace | ❌ |
| `request_id` | trace ↔ log ↔ metric 关联 | ❌ |
| `http.route` / `http.method` / `http.status_code` | 标准 OTel HTTP semantic conv | ❌ (FastAPI auto-instrument 会自动加, 但 HAS_OTEL_FASTAPI=False) |
| `db.system` / `db.statement` | 标准 OTel DB semantic conv | ❌ |
| `error.type` / `error.message` | 错误捕获 | ❌ |
| `tenant.tier` / `tenant.plan` | 业务分层 | ❌ |

→ **0/10 业务 attribute**, 业界 Datadog 默认 30+ semantic conv attribute。

---

## 7. Sampling 策略

### 7.1 当前配置 (jaeger.yaml:43-46)

```yaml
JAEGER_SAMPLER_TYPE: probabilistic
JAEGER_SAMPLER_PARAM: 0.1
```

→ **Head-based probabilistic 10% 采样**, 硬编码。

### 7.2 问题分析

| 问题 | 影响 |
|---|---|
| **Hardcoded 0.1** | 无法按 service / endpoint / env 调采样率 |
| **Head-based only** | 错误的 trace 也按 10% 采样, 重要数据丢失 |
| **No tail-based** | 无法根据 trace 结果 (error/latency) 动态决定保留 |
| **No error 100%** | 业界 best practice 是 error 全采, 但本项目错误 trace 也只 10% |
| **No slow 100%** | P99 > 1s 的 trace 应 100% 采样 |
| **No rate-limit** | 突发流量无保护 |
| **Jaeger sampler not adaptive** | 不像 Datadog 那样 adaptive |

### 7.3 业界最佳实践对标

| 工具 | 策略 |
|---|---|
| **Datadog Trace Search** | head 1% + tail 100% error + 100% slow (P95+) + adaptive |
| **Honeycomb Refinery** | tail-based, 多 rules (error/slow/anomaly) |
| **New Relic** | adaptive sampling, 30 天保留 |
| **Tempo + TraceQL** | configurable |
| **本项目** | head 10%, 啥都没 |

→ **采样策略是 trace 系统最大短板**, Honeycomb Refinery 是开源标配。

---

## 8. 跨服务 trace propagation

### 8.1 W3C Trace Context 标准

业界标准: `traceparent: 00-{trace_id_32hex}-{span_id_16hex}-{flags_2hex}`

### 8.2 本项目实现

`middleware.py:84-106` (TraceIDMiddleware):
```python
async def dispatch(self, request, call_next):
    incoming_trace = request.headers.get(self.header_name)  # x-trace-id
    if incoming_trace:
        trace_id = _sanitize_header(incoming_trace)
        ...
    else:
        trace_id = uuid.uuid4().hex  # ← 自己生成 UUID4 hex (32 chars)
    request_id = uuid.uuid4().hex
    set_trace_id(trace_id)
    set_request_id(request_id)
    ...
    response.headers["X-Trace-Id"] = trace_id
    response.headers["X-Request-Id"] = request_id
```

→ **自定义 X-Trace-Id 头 (UUID4 hex)**, 不是 W3C `traceparent`。

**问题**:
1. ❌ **不是 W3C traceparent**, 跨语言/跨框架不兼容
2. ❌ **无 span_id**, 无法表达父子 span 关系
3. ❌ **无 propagation flags** (sampled / not-sampled)
4. ❌ **下游服务 HTTP 调用未 forward X-Trace-Id** (httpx/requests 未 patch)

### 8.3 OTel propagator 默认

OTel SDK 默认 `BatchSpanProcessor` + `TraceContextTextMapPropagator` (W3C standard)。

→ 装 SDK 后会自动用 W3C traceparent, 与现有 X-Trace-Id 共存需手工注入。

---

## 9. Tracing 与 Metrics / Logs 关联

### 9.1 trace_id 在 Metrics

OpenMetrics Exemplar 标准允许 metric data point 附 trace_id:

```
imdf_http_requests_total{method="POST",endpoint="/api/chat",status="2xx"} 1234 # {trace_id="abc123"} 1.0 1234567890
```

→ **本项目 0 Exemplar**, 即便装 OTel SDK 也需 `prometheus_client` + `OpenMetric` 集成手工埋点。

### 9.2 trace_id 在 Logs

✅ 已实现 (`logging_setup.py:_bind_trace`):
```python
def _bind_trace(_logger, _method_name, event_dict):
    tid = _trace_id_var.get()
    if tid and "trace_id" not in event_dict:
        event_dict["trace_id"] = tid
    ...
```

→ 每条 JSON log 自动含 trace_id 字段。

### 9.3 Grafana 跳转

`grafana.yaml:37-44`:
```yaml
jsonData:
  tracesToLogsV2:
    datasourceUid: loki
```

→ Grafana 配置 tracesToLogsV2, 能在 trace UI 跳到 Loki logs。但**实际无 trace**, 无从跳起。

---

## 10. Jaeger 部署配置 (jaeger.yaml)

| 组件 | 配置 | 备注 |
|---|---|---|
| 镜像 | `jaegertracing/all-in-one:1.57` | 单 binary |
| 副本 | 1 | ⚠️ 单点 |
| OTLP gRPC | :4317 | ✅ |
| OTLP HTTP | :4318 | ✅ |
| Jaeger UI | :16686 | ✅ |
| Jaeger collector (gRPC) | :14250 | ⚠️ 未在 Service 暴露 |
| Zipkin compat | :9411 | ✅ |
| Storage backend | `memory` | ⚠️ 重启丢数据 |
| Sampler | probabilistic 0.1 | ⚠️ 见 §7 |
| Metrics backend | prometheus :9090 | ✅ |
| Query base path | `/jaeger` | ⚠️ Ingress path 要配 |

**生产就绪度**: **D**

- ❌ `memory` storage 生产必换 ES/Cassandra
- ❌ 单副本, 单点故障
- ❌ 无 retention 配置
- ❌ Collector gRPC :14250 未暴露, 上游 (gateway) 无法直连

---

## 11. 实际修复路径

### 11.1 立即可做 (P0)

```bash
# 1. 安装 OTel SDK + 5 个 instrumentation
pip install opentelemetry-api==1.27.0
pip install opentelemetry-sdk==1.27.0
pip install opentelemetry-exporter-otlp-proto-grpc==1.27.0
pip install opentelemetry-instrumentation-fastapi==0.48b0
pip install opentelemetry-instrumentation-sqlalchemy==0.48b0
pip install opentelemetry-instrumentation-redis==0.48b0
pip install opentelemetry-instrumentation-httpx==0.48b0
pip install opentelemetry-instrumentation-asyncpg==0.48b0

# 2. 加到 backend/requirements.txt 锁定

# 3. 修改 canvas_web.py:1063, 改 OTLP endpoint 为正确的 jaeger service
_tracing_ok = setup_tracing(
    service_name="imdf-main",
    otlp_endpoint="http://jaeger.monitoring.svc.cluster.local:4317",  # 修复命名
)

# 4. 12 svc main.py 各加 setup_tracing()
# 例如 services/user_service/main.py:
from monitoring.tracing import setup_tracing, instrument_fastapi
setup_tracing(service_name="user_service", otlp_endpoint="...")
instrument_fastapi(app)
```

### 11.2 P1 增强

```python
# 1. W3C traceparent + 自定义 X-Trace-Id 双支持
from opentelemetry.propagate import inject, extract
# httpx 中间件自动 inject traceparent
# 后端读 traceparent, 退到 X-Trace-Id

# 2. tenant_id / model / agent_id 注入到 span
def observe_chat_request(tenant_id, model, agent_id, trace_id=None):
    from opentelemetry import trace
    span = trace.get_current_span()
    span.set_attribute("tenant.id", tenant_id)
    span.set_attribute("model.name", model)
    span.set_attribute("agent.id", agent_id)
```

### 11.3 P2 高级

- 部署 **Honeycomb Refinery** (open source tail-based sampler) 替代 Jaeger 内置
- 配 **tail rules**: error 100% / P95+ slow 100% / unknown service 100%
- 启用 **OTel Collector** 作为统一接入层

---

## 12. 总结

| 关键问题 | 严重度 | 修复成本 |
|---|---|---|
| OTel SDK 全套未装 | **Critical** | 1 小时 (pip install) |
| 12 svc 未初始化 tracer | **Critical** | 半天 (12 × 5 行) |
| FastAPI/SQLAlchemy 未 auto-instrument | **Critical** | 1 小时 (装包 + 改 setup) |
| W3C traceparent 缺位 | **High** | 半天 (改 middleware 用 extract/inject) |
| Sampling 0.1 head-based | **Medium** | 1 天 (改 tail-based 配置) |
| 业务 span attribute 缺 | **Medium** | 1 天 (12 svc × 5 处埋点) |
| Jaeger storage = memory | **High** | 1 天 (换 ES / Cassandra) |
| Jaeger 单副本 | **Medium** | 1 小时 (改 replicas: 2) |
| OTLP endpoint 命名错 (jaeger-collector vs jaeger) | **Critical** | 5 分钟 |

**总修复成本**: 约 1 人周。

**建议**: 列为 P11-Sprint-A P0-1, 装 SDK + 12 svc 初始化 + 改 endpoint 是 1 天工作量, 立即可执行。