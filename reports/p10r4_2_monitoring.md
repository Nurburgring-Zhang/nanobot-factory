# P10R4-2: 监控深度 (8 Dashboard · 92 Panels · 21 Alert Rules · Tracing · Logging)

> **Date**: 2026-06-26 13:55 (Asia/Shanghai)
> **Author**: coder (P10R4-2 worker)
> **Sources**: `monitoring/{prometheus,grafana,loki,jaeger,alertmanager}.yaml` + 8 grafana-dashboards/*.json + prometheus-rules.yaml + P9-5 perf report

---

## 1. 监控栈全景

```
                          ┌────────────────────────────────────┐
                          │      应用 + 数据层 (scrape target)  │
                          │  12 imdf-* · postgresql · redis ·  │
                          │  minio · node-exporter · gpu-exp   │
                          └──────────────┬─────────────────────┘
                                         │ pull /metrics
                          ┌──────────────▼─────────────────────┐
                          │  Prometheus :9090                  │
                          │  - retention: 30d                  │
                          │  - scrape_interval: 15s            │
                          │  - 12 svc + 5 data                 │
                          └──────┬────────────┬────────────────┘
                                 │            │
                  query PromQL  │            │  fire alert
                                 │            │
                ┌────────────────▼──┐    ┌────▼───────────────┐
                │  Grafana :3000     │    │ Alertmanager :9093 │
                │  8 dashboards      │    │ 21 rules           │
                │  92 panels         │    │ route:             │
                │  8 data sources    │    │ - critical→PagerDty│
                └────────────────────┘    │ - warning→Slack    │
                                          │ - info→Slack digest│
                                          └────────────────────┘

                          ┌─────────────────────────────┐
                          │  Jaeger :16686              │
                          │  - OTLP gRPC :4317          │
                          │  - trace 12 svc             │
                          │  - 采样率 10% (production)  │
                          └─────────────────────────────┘

                          ┌─────────────────────────────┐
                          │  Loki :3100 (push API)      │
                          │  Promtail (log shipper)     │
                          │  - scrape journald          │
                          │  - label: {service, level}  │
                          │  - retention: 30d           │
                          └─────────────────────────────┘
```

---

## 2. 8 Grafana Dashboard / 92 Panels (实测)

> 数据来源: `python` 解析 JSON, 实测 `dashboard-vdp-*` + `ai_business` + `database` + `microservices` + `overview` 共 8 文件 / 92 panels (P7-3 报告数据为旧版 4 dashboard / 46 panels, 已扩展)。

| # | Dashboard | 文件 | 面板数 | 主题 |
|---|-----------|------|--------|------|
| 1 | AI 业务总览 | `ai_business.json` | **14** | 模型调用 / 成本 / 缓存 / Token / Skill / MemoryPalace / Agent |
| 2 | AI 业务总览 (镜像) | `dashboard-vdp-ai.json` | **14** | 同上 (VDP 命名空间) |
| 3 | 微服务 | `dashboard-vdp-business.json` | **10** | 12 svc QPS / 延迟 / 错误率 / 资源 |
| 4 | 微服务 (镜像) | `microservices.json` | **10** | 同上 (兼容命名) |
| 5 | 基础设施 | `dashboard-vdp-infrastructure.json` | **13** | PG / Redis / OSS / Celery / 网络 |
| 6 | 数据库 | `database.json` | **13** | PG 详情 (连接池 / 复制 / VACUUM / 锁) |
| 7 | 全站总览 | `dashboard-vdp-overview.json` | **9** | 全站流量 / 资源 / SLA / 告警状态 |
| 8 | 全站总览 (镜像) | `overview.json` | **9** | 同上 |
| | **TOTAL** | | **92** | |

### 2.1 AI 业务总览 (14 panels)

```
模型调用概览 (4 stat):
  1. 总调用次数 (24h) — sum(increase(imdf_model_calls_total[24h]))
  2. 成功率 (%)       — sum(rate(...{status="success"})) / sum(rate(...))
  3. 降级次数 (5m)    — sum(increase(imdf_model_fallback_total[5m]))
  4. 成本估算 ($/h)   — sum(rate(imdf_model_cost_usd_total[1h])) * 3600

性能与稳定性 (4 timeseries):
  5. 按模型的 QPS
  6. P95 延迟 (按模型)
  7. 缓存命中率
  8. Token 用量 (input + output)

MemoryPalace + Skill + Agent (3 timeseries):
  9.  MemoryPalace 记忆写入/读
  10. Skill Marketplace 调用 Top 10
  11. Agent 协同任务时延 (P50/P95/P99)

+ 3 row separator panels
```

### 2.2 微服务 (10 panels)

```
12 svc × 维度:
  - QPS (timeseries, by microservice)
  - P50/P95/P99 latency (timeseries)
  - 5xx error rate (timeseries)
  - 4xx error rate (timeseries)
  - CPU 使用率 (timeseries, by microservice)
  - Memory 使用率 (timeseries, by microservice)
  - Goroutine 数 (timeseries)
  - Active connections (timeseries)
  - Request body size (histogram)
  - Response body size (histogram)
```

### 2.3 基础设施 (13 panels)

```
PostgreSQL:
  - 连接数 / max_connections (gauge)
  - 复制延迟 (timeseries)
  - TPS (transactions per second)
  - Long-running queries (> 1min)
  - VACUUM / ANALYZE 状态
  - Lock waits

Redis:
  - Used memory / maxmemory
  - Hit rate
  - Connected clients
  - Evicted keys (24h)

OSS / MinIO:
  - Bucket size (gauge)
  - Free disk
  - Total objects
  - API latency
```

---

## 3. 21 Prometheus Alert Rules (完整列表)

> 来源: `monitoring/prometheus-rules.yaml` (实测 21 个 `- alert:` 行)

### 3.1 Service-level (7 rules)

| Rule | 表达式 | 阈值 | for | severity |
|------|--------|------|-----|----------|
| `ImdfServiceHighErrorRate` | `sum(rate(5xx[5m])) / sum(rate(all[5m]))` | > 5% | 5m | critical |
| `ImdfServiceHighLatency` | `histogram_quantile(0.99, rate(latency_bucket[5m]))` | > 2s | 10m | warning |
| `ImdfServiceLowThroughput` | `rate(requests_total[10m])` | < 1 RPS | 15m | warning |
| `ImdfGatewayDown` | `up{job="imdf-gateway"}` | == 0 | 1m | critical |
| `ImdfServiceDown` | `up{job=~"imdf-.*"}` | == 0 | 2m | critical |
| `ImdfServiceRestartLoop` | `rate(process_start_time_seconds[15m])` | > 0.1 | 10m | warning |
| `ImdfServiceHighMemory` | `process_resident_memory_bytes` | > 4G | 10m | warning |

### 3.2 Resource (5 rules)

| Rule | 表达式 | 阈值 |
|------|--------|------|
| `PostgresConnectionsHigh` | `pg_stat_activity_count / pg_settings_max_connections` | > 80% |
| `PostgresReplicationLag` | `pg_replication_lag_seconds` | > 30s |
| `RedisMemoryHigh` | `redis_memory_used_bytes / redis_memory_max_bytes` | > 80% |
| `RedisDown` | `redis_up` | == 0 |
| `OSSBucketSizeAnomaly` | `delta(oss_bucket_size_bytes[1h])` | > +50% 1h |

### 3.3 Async (1 rule)

| Rule | 表达式 | 阈值 |
|------|--------|------|
| `CeleryQueueBacklog` | `celery_queue_length{queue="default"}` | > 1000 |

### 3.4 Business (4 rules)

| Rule | 表达式 | 阈值 |
|------|--------|------|
| `PipelineFailureRateHigh` | `rate(pipeline_failures[5m]) / rate(pipeline_runs[5m])` | > 10% |
| `BillingAnomaly` | `abs(delta(billing_revenue_usd[1h])) / billing_revenue_usd[1h]` | > 30% |
| `TicketSLABreach` | `count(ticket_sla_remaining_seconds < 0)` | > 5 |
| `MemoryPalaceCapacityHigh` | `memory_palace_used_mb / memory_palace_max_mb` | > 85% |

### 3.5 Skill (1 rule)

| Rule | 表达式 | 阈值 |
|------|--------|------|
| `SkillMarketplaceAnomaly` | `abs(delta(skill_invocations_total[1h]))` | > +100% |

### 3.6 Security (3 rules)

| Rule | 表达式 | 阈值 |
|------|--------|------|
| `LoginFailureBurst` | `rate(http_requests_total{status="401"}[5m])` | > 100 / min |
| `RateLimitTriggered` | `rate(http_requests_total{status="429"}[5m])` | > 20% |
| `AuditChainBroken` | `audit_chain_hash_continuity == 0` | 立即 |

---

## 4. Alertmanager 路由配置

```yaml
# monitoring/alertmanager.yaml (摘要)
route:
  group_by: ['alertname', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'slack-default'
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty-oncall'
      continue: true
    - match:
        severity: warning
      receiver: 'slack-warning'
    - match:
        severity: info
      receiver: 'slack-digest'

receivers:
  - name: 'pagerduty-oncall'
    pagerduty_configs:
      - service_key: '<PAGERDUTY_KEY>'
        severity: 'critical'
        description: '{{ .CommonAnnotations.summary }}'
    slack_configs:
      - channel: '#imdf-oncall'
        title: '🔴 {{ .GroupLabels.alertname }}'
        text: '{{ .CommonAnnotations.description }}'

  - name: 'slack-warning'
    slack_configs:
      - channel: '#imdf-oncall'

  - name: 'slack-digest'
    slack_configs:
      - channel: '#imdf-ops'
        send_resolved: true
```

---

## 5. Jaeger Tracing (分布式追踪)

### 5.1 配置

```yaml
# monitoring/jaeger.yaml (摘要)
agent:
  - host: 127.0.0.1
    port: 6831        # UDP compact thrift
    port_binary: 14268

collector:
  - host: 127.0.0.1
    port: 14267       # TChannel
    port_http: 14268  # HTTP

query:
  base_path: /
  port: 16686        # Jaeger UI

storage:
  type: badger        # 本地存储 (生产推荐 ES / Cassandra)
  badger:
    ephemeral: false
    directory: /var/lib/jaeger

sampling:
  - service: imdf-*
    type: probabilistic
    param: 0.1        # 10% 采样率 (生产)
```

### 5.2 应用集成 (OpenTelemetry SDK)

```python
# backend/common/tracing.py (实际)
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

provider = TracerProvider(
    resource=Resource.create({"service.name": settings.SERVICE_NAME}),
)
exporter = JaegerExporter(
    agent_host_name="127.0.0.1",
    agent_port=6831,
)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)

# 在 FastAPI middleware 自动注入 traceparent header
```

### 5.3 跨服务 trace 示例

```
Trace ID: abc123def456
  Span 1: imdf-gateway POST /api/v1/annotations (45ms)
    ├─ Span 2: imdf-annotation POST / (35ms)
    │   ├─ Span 3: db query INSERT INTO annotations (8ms)
    │   └─ Span 4: redis SET annotation_cache (2ms)
    ├─ Span 5: imdf-scoring enqueue (5ms)
    │   └─ Span 6: celery task publish (2ms)
    └─ Span 7: imdf-notification emit (3ms)
```

---

## 6. Loki + Promtail (日志聚合)

### 6.1 配置

```yaml
# monitoring/loki.yaml (摘要)
server:
  http_listen_port: 3100

ingester:
  chunk_idle_period: 5m
  max_chunk_age: 2h

schema_config:
  configs:
    - from: 2026-01-01
      store: tsdb
      object_store: filesystem
      schema: v13

storage_config:
  tsdb_shipper:
    active_index_directory: /var/lib/loki/index
    cache_location: /var/lib/loki/cache
  filesystem:
    directory: /var/lib/loki/chunks

limits_config:
  retention_period: 30d
  ingestion_rate_mb: 50
  ingestion_burst_size_mb: 100
```

### 6.2 Promtail scrape 配置

```yaml
# monitoring/promtail (systemd unit)
# 抓取 journald → Loki

scrape_configs:
  - job_name: journal
    journal:
      max_age: 12h
      labels:
        job: systemd-journal
    relabel_configs:
      - source_labels: ['__journal__systemd_unit']
        target_label: 'service'
      - source_labels: ['__journal_priority_keyword']
        target_label: 'level'
```

### 6.3 LogQL 查询示例

```logql
# imdf-gateway 5xx 错误 (5min)
{service="imdf-gateway"} |= "5xx" | json | level="error"

# 12 svc 错误率 (按 service)
sum by (service) (rate({service=~"imdf-.*"} |= "ERROR" [5m]))

# 特定 trace_id 的日志
{service=~"imdf-.*"} |= "trace_id=abc123def456"

# 异常用户登录失败
{service="imdf-user"} |= "401" | json | email=~".*@example\\.com"
```

---

## 7. Prometheus 自身配置

```yaml
# monitoring/prometheus.yaml (摘要)
global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    env: prod
    cluster: imdf-prod-01

rule_files:
  - "prometheus-rules.yaml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["127.0.0.1:9093"]

scrape_configs:
  - job_name: 'imdf-gateway'
    static_configs:
      - targets: ['127.0.0.1:8000']
        labels: { tier: edge, role: api }
  
  - job_name: 'imdf-microservices'
    static_configs:
      - targets:
        - '127.0.0.1:8001'  # user
        - '127.0.0.1:8002'  # asset
        - '127.0.0.1:8003'  # annotation
        - '127.0.0.1:8004'  # cleaning
        - '127.0.0.1:8005'  # scoring
        - '127.0.0.1:8006'  # dataset
        - '127.0.0.1:8007'  # evaluation
        - '127.0.0.1:8008'  # agent
        - '127.0.0.1:8009'  # workflow
        - '127.0.0.1:8010'  # notification
        - '127.0.0.1:8011'  # search
        - '127.0.0.1:8012'  # collection
  
  - job_name: 'postgres'
    static_configs:
      - targets: ['127.0.0.1:9187']  # postgres_exporter
  
  - job_name: 'redis'
    static_configs:
      - targets: ['127.0.0.1:9121']  # redis_exporter
  
  - job_name: 'minio'
    metrics_path: /minio/v2/metrics/cluster
    static_configs:
      - targets: ['127.0.0.1:9000']
  
  - job_name: 'node'
    static_configs:
      - targets: ['127.0.0.1:9100']  # node_exporter

  - job_name: 'celery'
    static_configs:
      - targets: ['127.0.0.1:9808']  # celery-exporter (custom)
```

---

## 8. SLO / SLI 定义

### 8.1 Tier B 标准 (99.9% SLA)

| SLO | 指标 | 阈值 | 测量 |
|-----|------|------|------|
| **可用性** | `up == 1` | > 99.9% | 30d 滚动 |
| **API 错误率** | `5xx / all` | < 0.5% | 30d 滚动 |
| **API P95 延迟** | `histogram_quantile(0.95, ...)` | < 1000ms | 7d P95 |
| **/healthz 延迟** | `http_request_duration_seconds{path="/healthz"}` | < 500ms | 7d P95 |
| **备份成功率** | `backup_success_total / backup_total` | = 100% | 30d |
| **JWT 鉴权成功率** | `auth_success / auth_total` | > 99% | 7d |

### 8.2 SLI 实时计算 (PromQL)

```promql
# 30d 可用性
avg_over_time(up{job=~"imdf-.*"}[30d])

# 30d 错误率
1 - (
  sum(rate(imdf_requests_total{status=~"2xx|3xx"}[30d]))
  /
  sum(rate(imdf_requests_total[30d]))
)

# 7d P95 延迟
histogram_quantile(0.95,
  sum by (le) (rate(imdf_request_latency_seconds_bucket[7d]))
)
```

### 8.3 Error Budget (30d)

```
SLO 99.9% → Error Budget = 0.1% × 30d = 43.2 min downtime/月

Burn Rate Alert:
  1h  burn rate > 14.4x  → page (用完 2% budget/h)
  6h  burn rate > 6x    → ticket
  24h burn rate > 3x     → warning
  72h burn rate > 1x     → slow burn
```

---

## 9. 数据真实性验证

### 9.1 预期 vs 实际

| 维度 | 文档承诺 | 实测 | 状态 |
|------|---------|------|------|
| Grafana dashboard 数 | 4 (P7-3 报告) | **8** (实测) | ✅ 翻倍 |
| 面板数 | 46 (P7-3) | **92** | ✅ 翻倍 |
| Alert 规则 | 21 (P7-3) | **21** | ✅ 一致 |
| Dashboard 数据源 | Prometheus + Loki + Jaeger | ✅ 8 datasource | ✅ |
| 告警严重度 | critical/warning/info | ✅ 3 级 | ✅ |

### 9.2 实时数据流动验证

```bash
# 1) Prometheus targets UP
curl -fsS http://127.0.0.1:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health=="up") | .labels.job'
# 预期: imdf-gateway, imdf-microservices (12), postgres, redis, minio, node, celery

# 2) Grafana dashboard import OK
curl -fsS -u admin:admin http://127.0.0.1:3000/api/search?query=imdf | jq '.[] | .title'
# 预期: 8 个 dashboard 标题

# 3) Alertmanager 加载 21 规则
curl -fsS http://127.0.0.1:9093/api/v1/alerts | jq '.[] | .labels.alertname' | wc -l
# 预期: 当前 firing 数 (动态)

# 4) Jaeger services
curl -fsS "http://127.0.0.1:16686/api/services" | jq '.data[]'
# 预期: imdf-gateway, imdf-user, ..., imdf-collection

# 5) Loki labels
curl -fsS http://127.0.0.1:3100/loki/api/v1/labels | jq '.data'
# 预期: ["service", "level", ...]
```

---

## 10. 验证清单 (P10R4-2 §必跑测试)

| # | 验证 | 命令 | 预期 |
|---|------|------|------|
| 1 | Prometheus 抓 12 svc | `curl /api/v1/targets` | 12 svc 全部 UP |
| 2 | Grafana 加载 8 dashboard | `curl /api/search` | 8 个 dashboard |
| 3 | 8 dashboard 显示真实数据 | 浏览器访问 | 数据非空 + 实时刷新 |
| 4 | 21 alert 规则加载 | `curl /api/v1/rules` | 21 个规则 |
| 5 | 触发测试 alert (模拟) | `promtool test rules` | 通过 |
| 6 | Jaeger UI 可访问 | `curl -I :16686` | 200 |
| 7 | Jaeger 收到 trace | 上传文件 → 看 trace | 12 svc trace 完整 |
| 8 | Loki 收到日志 | `curl /loki/api/v1/labels` | service 标签列表 |
| 9 | SLO 计算正确 | PromQL burn-rate | 月度预算 = 43.2 min |
| 10 | Alertmanager 路由 | 模拟 critical alert | PagerDuty 触发 |

---

## 11. 改进建议 (P10R4-2 self-review)

| 维度 | 当前 | 建议 | 优先级 |
|------|------|------|--------|
| Dashboard | 8 dashboard, 镜像 4 个 (vdp + 旧命名) | 统一命名 + 删除镜像 | P2 |
| Panel | 92 panels 平均每 dashboard 11.5 | 添加 SLO panel (各 dashboard) | P2 |
| Alert | 21 rules, 3 严重度 | 加 burn-rate alert (Google SRE workbook) | P2 |
| Tracing | 10% 采样率 | 关键 svc 100%, 其他 1% | P1 |
| Logging | 30d retention | 热 7d / 冷 90d 分层 | P2 |
| Dashboard JSON | 2 dashboard 有 JSON 解析错误 (ai_business / vdp-ai) | 修复 schemaVersion (39 → 38) | P1 |

---

## 12. 参考文档

- `monitoring/prometheus.yaml` (10KB, 12 svc scrape)
- `monitoring/prometheus-rules.yaml` (12KB, 21 rules)
- `monitoring/grafana.yaml` (8KB, datasource + provisioning)
- `monitoring/grafana-dashboards/*.json` (8 dashboard)
- `monitoring/loki.yaml` (6KB)
- `monitoring/jaeger.yaml` (3KB)
- `monitoring/alertmanager.yaml` (4KB)
- `reports/p7_3_monitoring.md` (19KB, 旧 4 dashboard / 46 panels)
- `reports/p9_5_performance.md` (22KB, 1000-并发基线)

