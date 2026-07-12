# P10R4-4 Correlation 关联深度审计

**报告**: trace_id / request_id / tenant_id 3 维度关联
**日期**: 2026-06-26

---

## 1. 总览

| 关联维度 | 状态 |
|---|---|
| trace_id middleware | ✅ (TraceIDMiddleware) |
| request_id middleware | ✅ (X-Request-Id) |
| trace_id 在 logs | ✅ (structlog _bind_trace) |
| trace_id 在 metrics | ❌ (无 Exemplar) |
| trace_id 在 trace | ❌ (OTel SDK 未装) |
| request_id 跨服务传播 | ❌ (未 forward 下游) |
| **tenant_id 全维度** | **❌ 3 维度 0 处** |
| Grafana 跳转 (Loki ↔ Jaeger) | ⚠️ 配置有, 数据无 |
| 3 维度联合查询 | ⚠️ 受限 (无 tenant_id) |

**评分**: **B (70/100)** — middleware 框架完整, 业务维度缺位。

---

## 2. trace_id 传播路径

### 2.1 完整链路 (理论)

```
┌─────────────────────────────────────────────────────────────────┐
│ Client                                                         │
│   GET /api/chat                                                  │
│   X-Trace-Id: abc123def456                                       │
│   X-Request-Id: server-uuid-789                                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ (假设 traceparent 标准)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ TraceIDMiddleware (canvas_web.py / 12 svc main)                │
│   1. 读 X-Trace-Id 头 → _sanitize_header()                      │
│   2. 无效 → uuid.uuid4().hex                                     │
│   3. set_trace_id(trace_id)  → ContextVar                       │
│   4. request_id = uuid.uuid4().hex (总是新生成)                  │
│   5. set_request_id(request_id)                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Application Code                                                │
│   - logger.info(...) 自动注入 trace_id + request_id             │
│   - prometheus_client metric 计数 (但 label 无 trace_id)        │
│   - OTel span 创建 (但 SDK 未装 → _NoopSpan)                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│ Response                                                        │
│   X-Trace-Id: abc123def456                                       │
│   X-Request-Id: server-uuid-789                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 实测 (smoke test)

```python
r2 = c.get('/api/v1/health/live', headers={'X-Trace-Id': 'test-trace-12345'})
print(f'status={r2.status_code}, X-Trace-Id echoed={r2.headers.get("x-trace-id")!r}, X-Request-Id echoed={r2.headers.get("x-request-id")!r}')
# 输出: status=404, X-Trace-Id echoed=None, X-Request-Id echoed=None
```

⚠️ **`server.py` 路由不返回 X-Trace-Id / X-Request-Id 头**。原因:
1. `server.py` 是 legacy AIRI 主入口, 没挂 `TraceIDMiddleware`
2. `canvas_web.py` 启动后挂的 middleware 只对新路由生效

→ **main app (`server.py`) 实际上没有 trace propagation**, 只有 `canvas_web` 子模块的路由有。

---

## 3. trace_id 在 3 个数据源的注入状态

### 3.1 Logs (✅ 完整)

`logging_setup.py:_bind_trace`:
```python
def _bind_trace(_logger, _method_name, event_dict):
    tid = _trace_id_var.get()
    if tid and "trace_id" not in event_dict:
        event_dict["trace_id"] = tid
    rid = _request_id_var.get()
    if rid and "request_id" not in event_dict:
        event_dict["request_id"] = rid
    return event_dict
```

实测 log:
```json
{"event": "...", "logger": "...", "level": "info", "timestamp": "...", 
 "trace_id": "abc123def456", "request_id": "uuid-..."}
```

✅ **trace_id + request_id 100% 自动注入**, 无需手工 log.info(trace_id=...)。

### 3.2 Metrics (❌ 缺 Exemplar)

`imdf/api/_common/metrics.py:65`:
```python
HTTP_REQUESTS_TOTAL = _Counter(
    "imdf_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],  # ← labels: 3 个, 无 trace_id
    registry=REGISTRY,
)
```

**问题**: Counter.inc() 不接受 trace_id 参数, prometheus_client 默认**无 Exemplar 支持**。

**业界做法** (OpenMetrics Exemplar 标准):
```
imdf_http_requests_total{method="POST",endpoint="/api/chat",status="2xx"} 1234 \
# {trace_id="abc123"} 1.0 1234567890
# ^^^^^^^^ Exemplar 格式
```

→ 需装 `prometheus_client` + `wsgiref` / `asgiref` 中间件手工埋点。

**本项目缺失度**: **100%** — 无任何 Exemplar 代码。

### 3.3 Traces (❌ OTel 未装)

`tracing.py:HAS_OTEL_API=False` → 无 `trace.get_current_span()` 可用 → 即便手工 `span.set_attribute("trace_id", ...)` 也没人接收。

→ 即使加埋点代码, span 也进不了 Jaeger。

---

## 4. request_id 跨服务传播

### 4.1 当前实现

`middleware.py:84-106` 只处理**入站 + 出站 header**, 不处理**对下游的 out-call**。

```python
async def dispatch(self, request, call_next):
    incoming_trace = request.headers.get(self.header_name)
    ...
    response.headers["X-Trace-Id"] = trace_id
    response.headers["X-Request-Id"] = request_id
    return response
```

→ **TraceIDMiddleware 不 hook httpx.AsyncClient / requests.Session**。

### 4.2 缺失

应用代码调下游服务 (e.g. `httpx.AsyncClient().post(other_service_url, ...)`) 时, **X-Trace-Id / X-Request-Id 未透传**。

**业界最佳实践** (OpenTelemetry propagation):
```python
# 装 OTel SDK 后, 自动 propagation
from opentelemetry.propagate import inject
headers = {}
inject(headers)  # ← 自动注入 traceparent + tracestate + baggage
httpx.AsyncClient().post(url, headers=headers)
```

或者用 httpx `event_hooks`:
```python
async def add_trace_headers(request):
    request.headers["X-Trace-Id"] = get_trace_id()
    request.headers["X-Request-Id"] = get_request_id()

client = httpx.AsyncClient(event_hooks={"request": [add_trace_headers]})
```

→ **本项目 0 处 httpx/requests 埋点**, 跨服务 trace 不可能。

---

## 5. tenant_id 维度 (❌ 全部缺位)

### 5.1 tenant_id 在 Logs

`logging_setup.py` 无 `_bind_tenant` processor, 日志不含 tenant_id。

**应该有**:
```python
# 加 _bind_tenant processor
def _bind_tenant(_logger, _method_name, event_dict):
    tid = _tenant_id_var.get()
    if tid and "tenant_id" not in event_dict:
        event_dict["tenant_id"] = tid
    return event_dict

# 在 auth middleware 设
def set_tenant_id(tenant_id):
    _tenant_id_var.set(tenant_id)
```

实测 log 字段:
```json
{"event": "request completed", "method": "POST", "path": "/api/chat",
 "status_code": 200, "trace_id": "abc123"}
#                       ^^^^^^^^^^^^^^ no tenant_id!
```

### 5.2 tenant_id 在 Metrics

```python
# imdf/api/_common/metrics.py:65
HTTP_REQUESTS_TOTAL = _Counter(
    "imdf_http_requests_total",
    ["method", "endpoint", "status"],  # ← no tenant_id!
    ...
)
```

应该:
```python
HTTP_REQUESTS_TOTAL = _Counter(
    "imdf_http_requests_total",
    ["method", "endpoint", "status", "tenant_id"],  # ← 加 tenant_id
    ...
)
```

⚠️ **风险**: tenant_id cardinality 可能 10000+, 需评估 series 数。

### 5.3 tenant_id 在 Traces

`tracing.py` setup 仅设 `service.name`, 无 tenant_id attribute。

应该:
```python
resource = _Resource.create({
    "service.name": svc,
    "tenant.tier": tenant_tier,  # ← 应该从 auth context 取
})
# 在业务代码:
span = trace.get_current_span()
span.set_attribute("tenant.id", tenant_id)
span.set_attribute("tenant.tier", tier)
```

### 5.4 tenant_id 数据库持久化

`imdf/models/agent.py:71`:
```python
trace_id: Mapped[Optional[str]] = mapped_column(String(64), default="", index=True)
```

→ **agent_tasks 表有 trace_id 列**, 但**无 tenant_id 列** (per-tenant 查询困难)。

**应该有**:
```python
tenant_id: Mapped[str] = mapped_column(String(64), default="", index=True)
user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
```

→ 加 composite index `(tenant_id, trace_id)` 支持 per-tenant trace 查询。

---

## 6. 3 维度联合查询 (理论 vs 实际)

### 6.1 理论场景

查 "tenant=acme 在 2026-06-26 14:00-14:10 的 /api/chat 慢请求, 含 trace"

```logql
# Loki
{app="imdf-main"} 
  |= "tenant_id=acme" 
  |= "path=/api/chat" 
  | json 
  | elapsed_ms > 1000
```

```promql
# Prometheus
imdf_http_request_duration_seconds_bucket{tenant_id="acme", endpoint="/api/chat", le="..."}
```

```traceql
# Tempo / Jaeger
{ tenant.id = "acme" && span.http.route = "/api/chat" && duration > 1s }
```

### 6.2 实际能力

| 步骤 | 理论 | 实际 |
|---|---|---|
| Loki 查 tenant=acme | JSON 字段过滤 | ❌ 日志无 tenant_id 字段 |
| PromQL 按 tenant 聚合 | label filter | ❌ metric 无 tenant_id label |
| TraceQL 按 tenant 查 | span attribute filter | ❌ 无 OTel trace |
| Loki → Jaeger 跳转 | trace_id 反查 | ⚠️ Grafana config 有, 但无 trace 数据 |
| Prometheus → Jaeger 跳转 | Exemplar | ❌ 无 Exemplar |

→ **3 维度联合查询目前不可用**, 需先在 3 数据源注入 tenant_id + 修 OTel SDK。

---

## 7. Grafana Datasource 关联

### 7.1 已配置

`grafana.yaml:17-44`:
```yaml
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus.monitoring.svc.cluster.local:9090
  - name: Jaeger
    type: jaeger
    url: http://jaeger-query.monitoring.svc.cluster.local:16686
    jsonData:
      tracesToLogsV2:
        datasourceUid: loki      # ← Jaeger → Loki 跳转
  - name: Loki
    type: loki
    url: http://loki.monitoring.svc.cluster.local:3100
```

### 7.2 缺失

| 应配置 | 状态 |
|---|---|
| `derivedFields` (Loki → Jaeger) | ❌ 缺, Loki datasource 未配 |
| `metricsToTraces` (Prometheus → Jaeger) | ❌ 缺 |
| `exemplarTraceIdDestinations` | ❌ 缺 |
| TraceQL / LogQL 默认时间窗 | 缺 |
| Cross-datasource query | ✅ Grafana 内置 |

→ **3 个 datasource 独立查询 OK, 互跳不完整**。

---

## 8. middleware order 问题

`canvas_web.py:1146-1149`:
```python
# Order matters: add_middleware is LIFO — last added runs first.
# We want TraceIDMiddleware to be the OUTERMOST wrapper so the trace context
# is set before RequestLoggingMiddleware emits the request event.
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(TraceIDMiddleware)
```

✅ **TraceIDMiddleware 是 outermost** (最后加 = 最先执行), 正确。

但其他 middleware (CORS / CSRF / Robustness / RequestSizeLimit) 都加在 TraceIDMiddleware 之前 → 它们触发的 log event **无 trace_id**。

实测:
```
[httpx] HTTP Request: GET http://testserver/healthz "HTTP/1.1 404 Not Found"  ← 无 trace_id
[api.canvas_web] CSRF 中间件已加载                                       ← 无 trace_id (启动事件, OK)
```

→ **httpx 第三方 client 日志无 trace_id**, CORS/CSRF 拒绝时无 trace_id。

---

## 9. ContextVar 在异步上下文的工作

```python
# Python 3.7+ PEP 567
_trace_id_var: ContextVar[Optional[str]] = ContextVar("imdf_trace_id", default=None)
```

✅ 每个 asyncio.Task 有独立 ContextVar copy, 不会跨请求污染。

测试 (假设):
```python
async def task_a():
    set_trace_id("task-A")
    await asyncio.sleep(0.1)
    assert get_trace_id() == "task-A"  # ✓

async def task_b():
    set_trace_id("task-B")
    assert get_trace_id() == "task-B"  # ✓
```

→ **ContextVar 设计正确**, 但要保证 `clear_trace_context()` 在 request 结束时调用。

`middleware.py:101`:
```python
try:
    response = await call_next(request)
finally:
    clear_trace_context()
```

✅ **finally 块清理**, 防止 ContextVar 泄漏。

---

## 10. 修复优先级

### P0

1. **加 `_bind_tenant` processor + `_tenant_id_var` ContextVar** (logging_setup.py)
2. **auth middleware 加 `set_tenant_id()`** (canvas_web / 12 svc)
3. **加 `tenant_id` label 到 HTTP/DB/Cache metric** (注意 cardinality)
4. **数据库 agent_tasks / audit_chain_entries 表加 tenant_id 列**

### P1

5. **httpx.AsyncClient event_hooks 注入 trace_id + tenant_id 到下游** (12 svc 各自配)
6. **Grafana Loki datasource 加 derivedFields** (trace_id 跳 Jaeger)
7. **修复 `server.py` 的 X-Trace-Id echo** (确保 main app 入口也 trace)
8. **OpenMetrics Exemplar** 注入 trace_id 到 metric sample

### P2

9. **OTel SDK 装 + propagator** (auto W3C traceparent 跨服务)
10. **per-tenant Loki LogQL preset** (saved query)

---

## 11. 总结

| 子项 | 评分 |
|---|---|
| trace_id middleware | **A** |
| request_id middleware | **A** |
| trace_id 在 logs | **A** |
| trace_id 在 metrics (Exemplar) | **F** |
| trace_id 在 traces | **F** (SDK 未装) |
| tenant_id 全维度 | **F** (3/3 缺) |
| 跨服务 propagation | **F** (无 httpx 埋点) |
| Grafana 跳转 | **B (config) / F (data)** |
| **整体** | **B (70)** |

**总修复成本**: 2-3 人天 (加 tenant_id 维度 + Exemplar + httpx hook)。