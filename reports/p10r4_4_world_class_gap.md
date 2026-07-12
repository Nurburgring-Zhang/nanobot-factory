# P10R4-4 World-Class Gap Analysis (Datadog / Honeycomb / New Relic / Grafana Cloud 对标)

**报告**: 与业界可观测性 SaaS 对标 + 改进路线图
**日期**: 2026-06-26

---

## 1. 总览对比矩阵

| 能力维度 | nanobot-factory | Datadog | Honeycomb | New Relic | Grafana Cloud |
|---|---|---|---|---|---|
| **Metrics 自动采集** | ⚠️ 12 svc 手动挂 | ✅ SaaS auto | ⚠️ 需 OTel | ✅ auto | ✅ Prom agent |
| **Metrics 业务维度** | ❌ 无 tenant/model | ✅ 全 | ✅ event | ✅ 全 | ✅ 全 |
| **Distributed Tracing** | ❌ SDK 未装 | ✅ APM | ✅ OTel-native | ✅ auto+OTel | ✅ Tempo |
| **Span 业务维度** | ❌ 仅 service.name | ✅ 30+ attrs | ✅ event | ✅ 全 | ✅ |
| **Tail-based sampling** | ❌ head 0.1 | ✅ adaptive | ✅ Refinery | ✅ adaptive | ✅ license |
| **结构化 Logs** | ✅ structlog+JSON | ✅ log mgmt | ⚠️ Honeycomb 不主推 | ✅ Logs in Context | ✅ Loki |
| **3-pillar correlation** | ⚠️ config 有, 数据无 | ✅ 完整 | ✅ BubbleUp | ✅ NRQL cross | ✅ 看 license |
| **Per-tenant 视图** | ❌ 无 | ✅ org/team/env | ✅ team | ✅ workspace | ✅ |
| **SLO 错误预算** | ❌ 无 | ✅ SLO+burn | ✅ SLO | ✅ SLO alert | ✅ license |
| **Exemplar/Trace↔Metric** | ❌ 无 | ✅ auto | ✅ OTel Exemplar | ✅ custom | ✅ |
| **AI/Pipeline 监控** | ❌ 无 (dashboard 引, 未埋) | ✅ AI Observability | ✅ events | ✅ AI Monitoring | ⚠️ 自建 |
| **RBAC / 团队权限** | ⚠️ Grafana viewer 默认 | ✅ granular | ✅ team RBAC | ✅ roles | ✅ |
| **告警去重/抑制** | ✅ inhibit_rules | ✅ 完整 | ✅ | ✅ | ✅ |
| **告警升级 / oncall** | ❌ 无 | ✅ PagerDuty native | ✅ PagerDuty | ✅ VictorOps | ✅ |
| **总评分** | **3.5 / 10** | **9 / 10** | **8.5 / 10** | **8 / 10** | **7.5 / 10** |

---

## 2. 能力维度详细对比

### 2.1 Metrics 自动采集 (5/10)

**业界最佳 (Datadog)**:
- 装 1 个 Agent, 自动采集 100+ 系统 metric (CPU / Mem / Disk / Net / Process)
- APM auto-instrument, 0 代码改动采集业务 metric
- 集成 500+ SaaS (AWS / Azure / GCP / K8s / DB)

**本项目**:
- ⚠️ 12 svc 手动 `mount_health(app)` 才暴露 /metrics
- ⚠️ main app `server.py` 走 nanobot_* 命名, 不一致
- ⚠️ 业务 metric 0 实现, dashboards 全空

**差距**: 业务 metric 100% 缺失, auto-instrument 完全缺位。

### 2.2 Metrics 业务维度 (2/10)

**业界最佳 (Datadog)**:
```python
# Datadog tag 自动注入
ddtrace.Pin.override(datadog_api, tags={
    "tenant_id": tenant.id,
    "tenant_tier": tenant.tier,
    "user_id": user.id,
    "model": model.name,
    "agent_id": agent.id,
    "env": "prod",
    "version": "1.2.3",
})
```

→ 8+ 维度, dashboard 任意切片。

**本项目**:
```python
# imdf/api/_common/metrics.py:65
HTTP_REQUESTS_TOTAL = _Counter(
    "imdf_http_requests_total",
    ["method", "endpoint", "status"],  # ← 3 个基础 label, 无业务维度
)
```

→ **0 业务维度** (无 tenant / user / model / agent)。

### 2.3 Distributed Tracing (1/10)

**业界最佳 (Honeycomb)**:
- OTel-native, 装 SDK 即可
- **BubbleUp**: 自动找异常 trace 的共性 attribute
- **Marker**: trace 上手动加注释 (e.g. "deployed v1.2.3")
- **Trace search**: SQL-like 查询 (`WHERE duration > 1s AND error = true`)

**本项目**:
- ❌ OTel SDK 0/9 包安装
- ❌ FastAPI/SQLAlchemy/Redis/httpx 0 instrumentation
- ❌ 业务代码仅 1 处 `_audit_tracer.start_as_current_span()` (但 noop)
- ❌ 跨服务 trace 0
- ❌ 业务 attribute 0

→ **基本框架完整, 实际 0 数据**。

### 2.4 Span 业务维度 (1/10)

**业界最佳 (Datadog APM)**:
```python
span = tracer.current_span()
span.set_tag("tenant.id", tenant.id)
span.set_tag("tenant.tier", tenant.tier)
span.set_tag("model.name", model)
span.set_tag("agent.id", agent_id)
span.set_tag("tool.name", tool_name)
span.set_tag("audit.chain_index", chain_index)
# 30+ 自动 + 任意 custom
```

**本项目**:
- ❌ `service.name="imdf-main"` 仅此 1 个
- ❌ tenant / user / model / agent 0 attribute
- ❌ OTel semantic conv (http.* / db.*) 0 attribute (auto-instrument 未启)

### 2.5 Sampling 策略 (2/10)

**业界最佳 (Honeycomb Refinery / Datadog)**:
```
# Honeycomb Refinery rules
- name: keep_errors
  condition: error != nil
  keep: true              # 100% 保留错误 trace
  
- name: keep_slow
  condition: duration_ms > 1000
  keep: true              # 100% 保留慢 trace
  
- name: sample_normal
  condition: status_code_class = "2xx"
  sample_rate: 0.01       # 1% 正常 trace
```

**本项目**:
```yaml
JAEGER_SAMPLER_TYPE: probabilistic
JAEGER_SAMPLER_PARAM: 0.1     # 10% 全部
```

→ **head-based only, 无 tail / error / slow 特殊处理**。

### 2.6 结构化 Logs (8/10)

**业界最佳 (Datadog / Grafana Loki)**:
- JSON 结构化 + auto-injected trace_id / span_id / host / service
- Log volume control (sampling, dedup)
- PII 自动 redact (Datadog Scrubber)
- Index policy (hot / cold / frozen)

**本项目**:
- ✅ structlog + JSONRenderer + ContextVar trace_id
- ✅ Log level 策略完整
- ✅ 错误堆栈自动 format
- ⚠️ Rotating file 10MB×5, 总 50MB
- ❌ **PII 脱敏 0 实现** (GDPR / CCPA 风险)
- ❌ Log volume control 缺
- ❌ Promtail pipeline regex 错, json parser 缺

### 2.7 3-pillar Correlation (4/10)

**业界最佳 (Datadog / Honeycomb / Grafana 11)**:
- ✅ Metric exemplar → trace
- ✅ Trace → log (by trace_id 自动跳转)
- ✅ Log → metric (由 log 反查关联 metric)
- ✅ BubbleUp 自动找异常 attribute

**本项目**:
- ⚠️ Grafana datasource `tracesToLogsV2` 已配 (Jaeger → Loki)
- ❌ Loki datasource 无 `derivedFields` (log → trace)
- ❌ Prometheus 无 Exemplar
- ❌ 0 实际数据 (tracing 全 noop)

→ **配置有, 数据无**。

### 2.8 Per-tenant 视图 (0/10)

**业界最佳 (Datadog / Honeycomb)**:
- Datadog: Org → Team → Service → Env → Tenant 5 层 hierarchy
- 每个 tenant 独立 dashboard, SLO, alert
- RBAC: tenant admin 只能看自己 tenant 数据

**本项目**:
- ❌ tenant_id 维度 0
- ❌ 无 per-tenant dashboard
- ❌ 无 per-tenant alert
- ❌ Grafana 默认 viewer 全局可见 (无 row-level security)

### 2.9 SLO 错误预算 (0/10)

**业界最佳 (Datadog / New Relic / sloth / pyrra)**:
```
SLO: 99.9% availability over 30d
Budget: 43.2 minutes/month
Burn rate alerts:
  - 1h short, 5m long: burn > 14.4x → page
  - 6h short, 30m long: burn > 6x → ticket
  - 24h short, 2h long: burn > 3x → log
  - 72h short, 6h long: burn > 1x → log
```

**本项目**:
- ❌ 0 SLO 定义
- ❌ 0 burn-rate alert
- ❌ 0 error budget dashboard
- ❌ 无 sloth / pyrra 部署

### 2.10 Exemplar / Trace ↔ Metric (0/10)

**业界最佳 (OpenMetrics Exemplar)**:
```
imdf_http_requests_total{endpoint="/api/chat"} 1234 \
# {trace_id="abc123",span_id="def456"} 5.0 1700000000
```

→ Grafana 点 metric sample → 跳 trace。

**本项目**: ❌ 0 Exemplar 实现。

### 2.11 AI / Pipeline 监控 (2/10)

**业界最佳 (Datadog AI Observability)**:
- LLM-specific metric (token, cost, latency, hallucination)
- Prompt / completion trace 自动捕获
- 跨 model 对比
- Quality score (eval LLM)

**本项目**:
- ⚠️ AI 业务 dashboard 已定义 14 panel, 引用 `imdf_model_calls_total` 等
- ❌ **0 metric 实际埋点**, dashboard 全空
- ⚠️ `engines/model_gateway.py` 用 `print()` 写日志, 不调 Counter

### 2.12 RBAC / 权限 (5/10)

**业界最佳 (Datadog / Grafana)**:
- Role-based access (admin / editor / viewer)
- Team 隔离 (datacenter / region / service owner)
- API key 粒度权限
- Audit log (谁改了什么)

**本项目**:
- ⚠️ Grafana anonymous viewer enabled (line 211-214)
- ❌ 无团队 / role 配置
- ❌ 无 API key 粒度权限
- ❌ 无 audit log (谁改 dashboard)

### 2.13 告警去重/抑制 (6/10)

**业界最佳**:
- 智能 dedup (相同 alert 1 分钟内合并)
- Inhibition (critical 抑制同 source warning)
- Silence (maintenance window)
- Group by 多维度

**本项目**:
- ✅ inhibit_rules (critical 抑制 warning)
- ✅ group_by ['alertname', 'cluster', 'service']
- ❌ 无 silence 配置
- ⚠️ group_wait 30s (业界默认 10s)

### 2.14 告警升级 / oncall (2/10)

**业界最佳**:
- PagerDuty / Opsgenie / VictorOps 集成
- Escalation policy (L1 5min → L2 15min → L3 30min)
- On-call rotation (weekly)
- Auto-page on severity

**本项目**:
- ⚠️ PagerDuty service_key 是 placeholder (`REPLACE-WITH-PAGERDUTY-SERVICE-KEY`)
- ⚠️ Slack webhook URL 是 placeholder
- ❌ 无 escalation policy
- ❌ 无 on-call rotation

---

## 3. Datadog 完整对标 (按优先级)

### 3.1 Datadog 必装的核心组件

| 组件 | 作用 | 本项目状态 |
|---|---|---|
| Datadog Agent | 主机 / 容器 metric | ❌ 用 prometheus 替代 |
| Datadog APM | auto-instrument 业务 | ❌ 用 OTel (未装) |
| Datadog Log Management | 集中 log | ❌ 用 Loki |
| Datadog Synthetics | 黑盒监控 | ❌ 无 |
| Datadog RUM | 前端监控 | ⚠️ 前端有 log 上报 |
| Datadog Incident | 故障响应 | ❌ 无 |
| Datadog Security | 安全监控 | ⚠️ 部分 (P10R4-1 已做) |
| Datadog Cost Management | 云成本 | ❌ 无 |
| Datadog LLM Observability | AI 监控 | ❌ 无 |

### 3.2 替代方案对比 (Loki + Prom + Jaeger vs Datadog)

| 维度 | Loki+Prom+Jaeger | Datadog |
|---|---|---|
| 月成本 (1000 服务) | $5K (云资源) | $30K (per host) |
| 运维复杂度 | 高 (5 组件) | 低 (SaaS) |
| 业务 metric 灵活度 | 中 (PromQL) | 高 (DatadogQL) |
| 跨服务 trace | 中 (需 OTel 装) | 高 (auto) |
| 集成生态 | 低 | 高 (700+ 集成) |
| 数据主权 | ✅ 自有 | ❌ SaaS |
| Lock-in | ❌ 无 | ⚠️ 高 |

→ **自建栈灵活, 但需补 1 人月工作**; **Datadog 即开即用, 但成本 6x**。

---

## 4. Honeycomb 完整对标

### 4.1 Honeycomb 核心优势

| 能力 | Honeycomb | 本项目 |
|---|---|---|
| Wide events | ✅ JSON event 一行一记录, 任意字段 query | ❌ 无 event 模型 |
| BubbleUp | ✅ 自动找异常 trace 的共性 attribute | ❌ 无 |
| Trace search SQL-like | ✅ `WHERE duration > 1s AND env=prod` | ❌ 无 (要等 OTel 装) |
| Marker | ✅ trace 手动加注释 (deploy / config) | ❌ 无 |
| Refinery (sampler) | ✅ tail-based 开源 | ❌ 无 |

### 4.2 替代

- Wide events → 自建 audit/event 表 + Loki
- BubbleUp → Datadog Watchdog (SaaS 独有) / 自研 ML
- Trace search → 等 OTel 装好 + TraceQL (Grafana Tempo)
- Marker → Grafana annotations (半替代)
- Refinery → 装 Refinery (open source)

---

## 5. New Relic 完整对标

### 5.1 New Relic 核心能力

| 能力 | New Relic | 本项目 |
|---|---|---|
| NRQL (SQL-like) | ✅ | ❌ (用 PromQL + LogQL) |
| APM auto-instrument | ✅ | ❌ |
| Logs in Context | ✅ 自动注入 trace_id | ⚠️ 半自动 |
| AI Monitoring | ✅ | ❌ |
| Errors Inbox | ✅ | ❌ |
| Workflows | ✅ 自动响应 | ❌ |
| APM 360 | ✅ 跨服务依赖图 | ❌ |

### 5.2 New Relic 替代

- NRQL → PromQL + LogQL (覆盖 80% 用例)
- APM → OTel + 业务 metric (需 1 人月)
- Logs in Context → 已有 (ContextVar)
- AI Monitoring → Datadog LLM Observability (SaaS 独有)
- Errors Inbox → Alertmanager + 自建 dashboard

---

## 6. Grafana Cloud 对标

### 6.1 Grafana Cloud 组件

| 组件 | OSS 自建 | Grafana Cloud 托管 |
|---|---|---|
| Grafana | ✅ | ✅ (托管) |
| Prometheus | ✅ | ✅ (Mimir 兼容) |
| Loki | ✅ | ✅ |
| Tempo (trace) | ❌ (用 Jaeger) | ✅ |
| Pyroscope (profiling) | ❌ | ✅ |
| Faro (RUM) | ❌ | ✅ |
| k6 (synthetic) | ❌ | ✅ |
| Beyla (auto-instrument) | ❌ | ✅ |

### 6.2 替代

- Tempo → 用 Jaeger (但功能较弱)
- Pyroscope → 自建 + eBPF (复杂)
- Faro → 前端有部分日志, 但无 RUM
- k6 → 已有 locust (P9-5-W1)
- Beyla → eBPF auto-instrument (替代 OTel SDK 的一部分)

---

## 7. 改进路线图 (按 P0 → P2)

### P0 — 必修 (1 人月)

| 工作 | 影响 | 工作量 |
|---|---|---|
| 装 OTel SDK + 5 instrumentation | Tracing 100% 失效修复 | 1 天 |
| 12 svc main.py 加 setup_tracing + TraceIDMiddleware | 跨服务 trace | 半天 |
| 补 14+ 业务 metric (model/pipeline/billing/skill/audit/ticket/memory) | dashboards 0→85% | 5 天 |
| 加 tenant_id label (HTTP/DB/Cache metric) | per-tenant 视图 | 1 天 |
| 加 tenant_id ContextVar + _bind_tenant processor | 3 维度关联 | 0.5 天 |
| PII 脱敏 (structlog processor + Promtail regex) | GDPR/CCPA 合规 | 1 天 |
| 替换 PagerDuty / Slack 真实凭据 | 生产告警可用 | 0.5 天 |

**总**: ~10 天 = 2 人周

### P1 — 重要 (1 人月)

| 工作 | 影响 | 工作量 |
|---|---|---|
| SLO burn-rate alert (per-service) | SRE 标准 | 3 天 |
| OpenMetrics Exemplar | metric ↔ trace | 2 天 |
| httpx.AsyncClient event_hooks (跨服务 propagation) | 跨服务 trace 完整 | 1 天 |
| Per-tenant dashboard (template variable) | 多租户可观测 | 2 天 |
| Incident triage dashboard | 故障响应 | 2 天 |
| Loki → S3/GCS backend | HA | 2 天 |
| Grafana HA (replicas: 2 + PVC) | HA | 1 天 |

**总**: ~13 天 = 2.5 人周

### P2 — nice-to-have (持续)

- Tail-based sampling (Refinery)
- Audit / Compliance dashboard
- Pipeline 业务 dashboard
- Cost / Billing dashboard
- Auto-instrument (Beyla / eBPF)
- Frontend RUM (Faro)
- Synthetic monitoring (k6 cloud)

---

## 8. 总评分

| 类别 | 评分 | 满分 | 备注 |
|---|---|---|---|
| Metrics 基础设施 | **7/10** | 10 | Prometheus + 12 svc 接入 OK |
| Metrics 业务维度 | **0/10** | 10 | 14+ 业务 metric 0 实现 |
| Tracing 基础设施 | **3/10** | 10 | OTel SDK 未装 |
| Tracing 业务维度 | **0/10** | 10 | 无 span attribute |
| Logging 基础设施 | **8/10** | 10 | structlog + JSON 完整 |
| Logging 合规 | **0/10** | 10 | PII 脱敏 0 |
| 3-pillar correlation | **4/10** | 10 | config 有, 数据无 |
| Per-tenant 视图 | **0/10** | 10 | tenant_id 维度 0 |
| SLO 错误预算 | **0/10** | 10 | 0 SLO, 0 burn-rate |
| Alerting | **5/10** | 10 | 21 规则形式, 47% 失效 |
| Dashboards | **6/10** | 10 | 46 panels, 40% 数据完整 |
| RBAC / 权限 | **5/10** | 10 | Grafana 基础 OK |
| 升级 / oncall | **2/10** | 10 | placeholder 凭据 |
| **总评分** | **3.5/10** | 10 | 框架完整, 数据严重缺失 |

---

## 9. 与 Honeycomb 的核心差距 (业界 "可观测性 2.0" 标准)

### 9.1 Wide Events 模型

**Honeycomb 设计哲学**: 每个请求一行 JSON event, 包含所有上下文:

```json
{
  "trace_id": "abc123",
  "span_id": "def456",
  "service": "imdf-main",
  "endpoint": "/api/chat",
  "method": "POST",
  "status": 200,
  "duration_ms": 234,
  "tenant_id": "acme",
  "tenant_tier": "enterprise",
  "user_id": "u-12345",
  "model": "gpt-4",
  "agent_id": "agent-7",
  "prompt_tokens": 1234,
  "completion_tokens": 567,
  "cost_usd": 0.045,
  "cache_hit": false,
  "error_type": null,
  "tool_invoked": "search_web",
  "timestamp": "2026-06-26T14:00:00Z"
}
```

→ **任意字段可查询**, BubbleUp 自动找异常模式。

**本项目**: ❌ 没有 event 模型, 只有 metric (聚合) + log (单行) 分离。

### 9.2 BubbleUp 自动归因

**Honeycomb**: "为什么 /api/chat 的 P99 从 200ms 涨到 800ms?"
→ BubbleUp 自动对比正常 vs 异常 trace, 给出:
- 87% 异常 trace 来自 tenant=acme
- 92% 异常 trace 用 model=gpt-4
- 78% 异常 trace 调了 tool=search_web

→ **秒级归因**, 不用手工 grep。

**本项目**: ❌ 无 BubbleUp, 故障定位靠人工 log search。

### 9.3 结构化事件 vs 非结构化日志

**传统 (本项目)**: log 行
```
[2026-06-26 14:00:00] INFO: chat request completed in 234ms
```

→ grep 慢, 无字段索引。

**Honeycomb**: 1 行 JSON event
```json
{"event": "chat_completed", "duration_ms": 234, "tenant_id": "acme", "model": "gpt-4", ...}
```

→ SQL-like 查询秒级。

---

## 10. 立即可执行 (P0 摘要)

```bash
# 1. 装 OTel (1 小时)
pip install \
  opentelemetry-api opentelemetry-sdk \
  opentelemetry-exporter-otlp-proto-grpc \
  opentelemetry-instrumentation-fastapi \
  opentelemetry-instrumentation-sqlalchemy \
  opentelemetry-instrumentation-redis \
  opentelemetry-instrumentation-httpx
echo ">> requirements.txt"

# 2. 修 jaeger endpoint (5 分钟)
# canvas_web.py:1063 otlp_endpoint="http://jaeger.monitoring.svc.cluster.local:4317"

# 3. 12 svc 加 setup_tracing (2 小时)
# 在每个 services/*/main.py 加:
# from monitoring.tracing import setup_tracing, instrument_fastapi
# setup_tracing(service_name="<svc>", otlp_endpoint="...")
# instrument_fastapi(app)

# 4. 删 dashboard-vdp-*.json (5 分钟)
rm monitoring/grafana-dashboards/dashboard-vdp-*.json

# 5. 替换 alertmanager placeholder (30 分钟)
kubectl create secret generic alertmanager-secrets \
  --from-literal=pagerduty-service-key=$PD_KEY \
  --from-literal=slack-webhook-url=$SLACK_URL \
  -n monitoring
# alertmanager.yaml 改 secretKeyRef

# 6. 加 PII 脱敏 (半天)
# logging_setup.py 加 _redact_pii processor
# promtail.yaml 加 multiline + json parse stage
```

---

## 11. 总结

| 维度 | 本项目 | 业界最佳 | 差距 |
|---|---|---|---|
| 总评分 | **3.5/10** | 9/10 (Datadog) | **5.5 分** |
| P0 必修工作量 | — | — | **2 人周** |
| P1 重要工作量 | — | — | **2.5 人周** |
| P2 nice-to-have | — | — | **持续** |

→ **与 Datadog 等 SaaS 的核心差距不是"采集", 是"业务维度"和"自动化"**。补 2-3 人月工作量, 可达 7/10 业界中上水平。