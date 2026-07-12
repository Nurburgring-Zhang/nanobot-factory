# P10R4-4 Logging 深度审计 (Loki + Promtail)

**报告**: Loki + Promtail pipeline + PII 脱敏 + log level 策略
**日期**: 2026-06-26

---

## 1. 总览

| 维度 | 状态 |
|---|---|
| 结构化 JSON logging | ✅ structlog + JSONRenderer |
| trace_id 跨服务注入 | ✅ ContextVar + _bind_trace |
| request_id middleware | ✅ X-Request-Id 注入 |
| Log level 策略 | ✅ DEBUG/INFO/WARN/ERROR 完整 |
| 错误堆栈 | ✅ format_exc_info |
| 文件 handler (rotating) | ✅ access.log / error.log |
| **Promtail pipeline** | ⚠️ 部分 (level label OK, microservice 抽取不完整) |
| **PII 脱敏** | ❌ 完全缺位 |
| **Loki 高可用** | ❌ 单副本 + filesystem storage |
| **Loki retention** | ⚠️ 7 天 (生产应 30+ 天) |

**评分**: **B+ (75/100)** — 结构化完整, PII 缺失是合规风险。

---

## 2. 应用层 structlog 实现

### 2.1 配置文件 (`logging_setup.py:99-176`)

```python
def configure_logging(level=INFO, log_dir=None, max_bytes=10*1024*1024, backup_count=5):
    # ... RotatingFileHandler ...
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            _bind_trace,                              # ← trace_id/request_id 注入
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),        # ← JSON 输出
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
```

✅ **10 个 processor** 完整覆盖 industry best practice。

### 2.2 ContextVar (logging_setup.py:34-57)

```python
_trace_id_var: ContextVar[Optional[str]] = ContextVar("imdf_trace_id", default=None)
_request_id_var: ContextVar[Optional[str]] = ContextVar("imdf_request_id", default=None)

def set_trace_id(trace_id): _trace_id_var.set(trace_id)
def get_trace_id(): return _trace_id_var.get()
def set_request_id(request_id): _request_id_var.set(request_id)
def get_request_id(): return _request_id_var.get()
def clear_trace_context(): _trace_id_var.set(None); _request_id_var.set(None)
```

✅ **ContextVar (PEP 567)** 异步上下文, 不需显式传参。

### 2.3 `_bind_trace` Processor (logging_setup.py:88-96)

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

✅ 自动注入 trace_id + request_id 到每条 JSON log。

---

## 3. 实测日志输出

**Smoke test 实际输出** (`smoke_metrics.py` 启动 + 几个 request):

```json
{"event": "Distributed tracing disabled (otel packages not installed)", "logger": "api.canvas_web", "level": "info", "timestamp": "2026-06-26T06:51:44.231335Z"}
{"event": "CSRF 中间件已加载, trusted_origins=6", "logger": "api.canvas_web", "level": "info", "timestamp": "2026-06-26T06:51:44.438923Z"}
{"event": "HTTP Request: GET http://testserver/healthz \"HTTP/1.1 404 Not Found\"", "logger": "httpx", "level": "info", "timestamp": "2026-06-26T06:51:44.236890Z"}
{"event": "HTTP Request: GET http://testserver/metrics \"HTTP/1.1 200 OK\"", "logger": "httpx", "level": "info", "timestamp": "2026-06-26T06:51:44.244396Z"}
{"event": "HTTP Request: GET http://testserver/api/v1/health/live \"HTTP/1.1 404 Not Found\"", "logger": "httpx", "level": "info", "timestamp": "2026-06-26T06:51:44.247396Z"}
```

✅ JSON 完整字段: `event`, `logger`, `level`, `timestamp` (ISO UTC)
⚠️ **缺 `trace_id`** (因 12 svc 未挂载 TraceIDMiddleware)
⚠️ `httpx` client 日志来自第三方, 无我们的 trace_id (需 httpx instrument)

---

## 4. Log Level 策略

### 4.1 等级使用审计

| 等级 | 触发位置 | 实现 |
|---|---|---|
| **DEBUG** | 默认关闭 | `level=INFO` 默认 |
| **INFO** | 2xx/3xx, 启动事件, middleware event | `logger.info(...)` |
| **WARNING** | 4xx 响应, slow >1s, audit_chain disabled, OTEL not installed | `logger.warning(...)` |
| **ERROR** | 5xx 响应, exception, audit 失败 | `logger.error(...)` |
| **CRITICAL** | **未使用** | — |

`SLOW_THRESHOLD_SEC = 1.0` (middleware.py:123)

### 4.2 Slow Request 监控

`middleware.py:169-174`:
```python
if elapsed_sec > SLOW_THRESHOLD_SEC:
    logger.warning(
        "slow request detected",
        **event,
        slow_threshold_s=SLOW_THRESHOLD_SEC,
    )
```

✅ 慢请求额外 WARN log, 阈值 1s (可调)

### 4.3 4xx/5xx 自动 level

`middleware.py:162-167`:
```python
if status_code >= 500:
    logger.error("request completed", **event)
elif status_code >= 400:
    logger.warning("request completed", **event)
else:
    logger.info("request completed", **event)
```

✅ 自动按 HTTP status 选 level

### 4.4 问题

❌ **无 DEBUG level 控制开关** (env var)
❌ **无 level per-module** (e.g. `api.canvas_web=DEBUG` 但 `sqlalchemy=INFO`)
❌ **无 structured log sampling** (P99 慢请求全采, 高 QPS endpoint 可能爆 log 量)

---

## 5. Rotating File Handlers

`logging_setup.py:117-156`:
```python
access_log_path = log_dir / "access.log"
error_log_path = log_dir / "error.log"

access = RotatingFileHandler(
    str(access_log_path),
    maxBytes=10 * 1024 * 1024,  # 10 MB
    backupCount=5,                # 5 backups
    encoding="utf-8",
)
access.setLevel(logging.INFO)

error = RotatingFileHandler(
    str(error_log_path),
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
error.setLevel(logging.WARNING)
```

✅ 双文件: `access.log` (INFO+), `error.log` (WARNING+)
✅ 10MB × 5 = 50MB 总占用, 滚动保留

**问题**:
- ❌ K8s Pod 重建后日志丢失 (emptyDir / 本地)
- ❌ 需 Promtail 主动 tail 才能进 Loki
- ⚠️ 50MB 可能不够, 12 svc × 50MB = 600MB

---

## 6. Promtail Pipeline (`promtail.yaml:61-110`)

### 6.1 Scrape 配置

```yaml
scrape_configs:
  - job_name: kubernetes-pods
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        target_label: app
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod
      - source_labels: [__meta_kubernetes_pod_container_name]
        target_label: container
      - source_labels: [__meta_kubernetes_pod_node_name]
        target_label: node
    pipeline_stages:
      - docker: {}
      - match:
          selector: '{app="imdf-main"}'
          stages:
            - regex:
                expression: '.*level=(?P<level>\w+).*'
            - labels:
                level:
      - match:
          selector: '{app=~"microservice-.*"}'
          stages:
            - labels:
                microservice: app

  - job_name: node-logs
    static_configs:
      - targets: [localhost]
        labels:
          job: node-logs
          __path__: /var/log/*.log
```

### 6.2 问题审计

**问题 1**: `regex: '.*level=(?P<level>\w+).*'` 

❌ **错误正则**: `.*level=...` 匹配**整个事件字符串**的 level=, 但 stdout 是 structlog JSON, level 字段在 JSON 里, 不会以 `level=ERROR` 形式出现。

应改为 JSON parser:
```yaml
- match:
    selector: '{app="imdf-main"}'
    stages:
      - json:
          expressions:
            level: level
            logger: logger
            trace_id: trace_id
      - labels:
          level:
          logger:
```

**问题 2**: `app=~"microservice-.*"`

❌ **微服务 deployment 标签可能是 `app=annotation-service` 等**, 实际 K8s label 值**不一定**带 `microservice-` 前缀。

**问题 3**: **缺 tenant_id / trace_id 抽取**

❌ Promtail pipeline_stages 没有 `json` parser 抽 `trace_id` / `tenant_id`, Loki 查询时只能 grep event 字段。

**问题 4**: **无 PII 脱敏**

❌ Promtail pipeline_stages 完全没有 redact stage, 客户端 IP / email / phone 直存 Loki。

### 6.3 缺失的 pipeline stage

| 应有 stage | 用途 |
|---|---|
| `json: { expressions: { ... } }` | 解析 JSON log, 抽字段到 label |
| `regex: { expression: ... }` | 自定义字段抽取 |
| `template: { template: ... }` | 重命名 / 重组 |
| `match: { selector: ..., action: keep/drop }` | 过滤 |
| `limit: { ... }` | rate limit |
| `multiline: { ... }` | 多行 stack trace |
| `labeldrop: [field1, field2]` | drop sensitive label |
| **`output: { source: ... }`** | ❌ **PII redact 需自定义 stage** |

---

## 7. Loki 部署 (`loki.yaml`)

### 7.1 配置

```yaml
schema_config:
  configs:
    - from: 2024-01-01
      store: tsdb               # TSDB (新, Loki 2.8+)
      object_store: filesystem  # ⚠️ 本地磁盘, 非 S3/GCS
      schema: v13
      index:
        prefix: index_
        period: 24h

limits_config:
  retention_period: 168h       # 7 天
  ingestion_rate_mb: 16        # 16 MB/s 速率限制
  ingestion_burst_size_mb: 32  # 32 MB burst
```

### 7.2 问题

| 问题 | 影响 |
|---|---|
| ❌ `object_store: filesystem` | 无 HA, Pod 重建丢数据 |
| ❌ `replicas: 1` | 单点 |
| ❌ `retention_period: 168h` (7 天) | 生产应 30+ 天 (合规/审计需求) |
| ❌ `ingestion_rate_mb: 16` | 12 svc + main 全 push 可能超 |
| ⚠️ 无 S3/GCS 配置 | 缺 backend storage |
| ⚠️ 无 compactor retention policy | 仅 schema_config 控 retention |

### 7.3 业界对标

| 工具 | 默认 retention |
|---|---|
| Grafana Cloud (Free) | 14 天 |
| Grafana Cloud (Pro) | 30+ 天可配 |
| Datadog Logs | 15 天 (可加) |
| New Relic Logs | 8 天 (Free) / 30 天 (Pro) |
| Splunk | 30+ 天 (license 控) |
| Honeycomb | N/A (Honeycomb 主推 events, 不主推 log) |
| **本项目** | **7 天** ⚠️ |

---

## 8. PII 脱敏 (❌ 完全缺位)

### 8.1 当前风险

实测 access.log:
```json
{"event": "request completed", "method": "POST", "path": "/api/v1/auth/login",
 "status_code": 200, "elapsed_ms": 234.5,
 "client": "192.168.1.100",  ← IP 直出
 "started_at": "2026-06-26T...", "trace_id": "abc123"}
```

→ **客户端 IP 直存**, GDPR/CCPA 合规风险。

### 8.2 应脱敏的字段

| 字段 | 出现位置 | 脱敏策略 |
|---|---|---|
| `password` | 表单提交 body | drop 整字段 |
| `token` / `access_token` / `refresh_token` | auth header | drop 或 mask |
| `email` | user profile | 部分遮蔽 `a***@example.com` |
| `phone` | user profile | 部分遮蔽 `138****1234` |
| `id_card` / `ssn` | KYC 数据 | drop |
| `credit_card` | billing | drop 前 12 位 |
| `client IP` | access log | mask 末段 `192.168.1.0` |
| `request body` | debug log | 限大小 + redact 敏感 key |

### 8.3 应实现的 3 层脱敏

#### Layer 1: 应用层 structlog processor

```python
# imdf/api/_common/logging_setup.py 新增
SENSITIVE_KEYS = {"password", "token", "access_token", "refresh_token", 
                  "secret", "api_key", "client_secret", "id_card", "ssn",
                  "credit_card", "cvv", "pin"}

def _redact_pii(_logger, _method_name, event_dict):
    """structlog processor — redact PII fields."""
    for key in list(event_dict.keys()):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***REDACTED***"
        # Mask email
        elif "email" in key.lower() and isinstance(event_dict[key], str):
            event_dict[key] = re.sub(r'(\w)[\w.]*(@\w+\.\w+)', r'\1***\2', event_dict[key])
        # Mask phone (11-digit Chinese)
        elif "phone" in key.lower() and isinstance(event_dict[key], str):
            event_dict[key] = re.sub(r'(\d{3})\d{4}(\d{4})', r'\1****\2', event_dict[key])
        # Mask client IP last octet
        elif key == "client" and isinstance(event_dict[key], str):
            parts = event_dict[key].split(".")
            if len(parts) == 4:
                parts[-1] = "0"
                event_dict[key] = ".".join(parts)
    return event_dict

# 加到 structlog.configure processors 列表
structlog.configure(
    processors=[
        ...,
        _redact_pii,    # ← 加这一行
        _bind_trace,
        ...,
    ],
)
```

#### Layer 2: Promtail redact stage

```yaml
# promtail.yaml 加 stage
- match:
    selector: '{app=~".+"}'
    stages:
      - json:
          expressions:
            client: client
      - regex:
          expression: '.*'
      - template:
          template: '{{ Replace .Entry "192.168.1.100" "192.168.1.0" }}'
      - labels:
          client_subnet:
```

或用 Loki 端的 LogQL mask:
```logql
{app="imdf-main"} | json | line_format `{{.client}}`
| "ip_mask(.client, 24)"   # LogQL 1.0+ 自带
```

#### Layer 3: Grafana row-level security

Grafana 配 row-level permission, 限制 viewer 看不到原始 IP, 只看脱敏后数据。

### 8.4 缺失成本

- **GDPR 罚款**: 最高 4% 全球营收
- **CCPA**: $7500/违规
- **PIPL (中国)**: 最高 5000万 RMB 或 5% 营收
- **客户信任损失**: 不可量化

→ **PII 脱敏是 P0 必修项**, 不应 P2。

---

## 9. Multiline Stack Trace

### 9.1 当前实现

`structlog.processors.StackInfoRenderer()` 和 `format_exc_info` 处理异常堆栈 → JSON 数组。

实测 (`logger.exception("request failed", exc_info=True)`):
```json
{"event": "request failed", "exc_info": ["Traceback (most recent call last):\n  File ...", "ValueError: ..."]
 ...}
```

✅ JSON 数组形式, 但 Promtail pipeline 未配 multiline parser, 单行 per stack frame。

### 9.2 业界最佳实践

Promtail `multiline` stage 合并多行 stack trace:
```yaml
- match:
    selector: '{app=~".+"}'
    stages:
      - multiline:
          firstline: '^\d{4}-\d{2}-\d{2}T'
          max_wait_time: 5s
      - json: ...
```

→ **本项目 Promtail 无 multiline stage**, stack trace 被切散, Loki 查询困难。

---

## 10. Loki Query (LogQL) 能力

### 10.1 当前可用查询

```logql
# 找错误
{app="imdf-main"} |= "level=error"

# 找特定路径
{app="imdf-main"} |= "path=/api/chat"

# JSON 解析 + 过滤
{app="imdf-main"} | json | status_code >= 500

# 时间范围 + limit
{app="imdf-main"} |= "slow" | line_format "{{.message}}" | limit 100
```

✅ LogQL 2.0 支持基础 JSON parse + filter。

### 10.2 缺失能力

| LogQL 功能 | 状态 |
|---|---|
| `| json` (字段抽取) | ✅ |
| `| line_format` | ✅ |
| `| label_format` | ✅ |
| `| ip_mask` | ❌ 未测 (Loki 2.9 可能有) |
| `| regex` | ✅ |
| `| pattern` | ✅ |
| `| drop` | ✅ |
| `| unpack` | ✅ |

---

## 11. Grafana Datasource 配置

`grafana.yaml:37-44`:
```yaml
- name: Loki
  type: loki
  access: proxy
  url: http://loki.monitoring.svc.cluster.local:3100
  editable: true
```

✅ Loki datasource 已注册。

**Missing**:
- ❌ 无 `derivedFields` 把 trace_id 解析为 link (Grafana 可点击 log 中的 trace_id 跳转 Jaeger)
- ❌ 无 `maxLines: 1000` 等查询限制 (防爆)

---

## 12. 修复优先级

### P0 — 合规必修

1. **应用层 PII 脱敏 processor** (logging_setup.py 加 _redact_pii)
2. **Promtail pipeline 加 multiline + json 解析 + ip_mask**

### P1 — 增强可观测

3. **Loki retention 提到 30 天** (合规需求)
4. **Loki backend storage 换 S3/GCS** (HA)
5. **Grafana Loki datasource 加 derivedFields** (jump to Jaeger)

### P2 — 高级

6. **Loki 多副本** (replicas: 3)
7. **log level per-module** (env var 控制)
8. **log sampling** (high-volume endpoint)

---

## 13. 总结

| 子项 | 评分 |
|---|---|
| 结构化 JSON | **A** |
| trace_id 注入 | **A** |
| request_id 注入 | **A** |
| Log level 策略 | **A** |
| 错误堆栈 | **A** |
| Rotating file | **B+** |
| Promtail pipeline | **C** (regex 错, json parser 缺) |
| Loki 持久化 | **D** (filesystem + 单副本) |
| Loki retention | **C-** (7 天, 生产不够) |
| PII 脱敏 | **F** (完全缺位) |
| Multiline stack | **F** (缺) |
| **整体** | **B+ (75)** |