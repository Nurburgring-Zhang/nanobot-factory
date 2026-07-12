# P10R4-4 Metrics 深度审计 (Prometheus)

**报告**: 12 微服务 Metrics 完整性 + RED/USE 矩阵 + 业务 metric 缺失清单
**日期**: 2026-06-26

---

## 1. 总览

| 维度 | 数量 | 状态 |
|---|---|---|
| 应用的 prometheus_client Counter | **6** | ✅ |
| 应用的 prometheus_client Histogram | **3** | ✅ |
| 应用的 prometheus_client Gauge | **9** | ✅ (含 legacy) |
| **真正 instrumented 的业务 metric** | **0** | ❌ |
| 引用但不存在的 metric (dashboards/rules) | **19+** | ❌ |
| 12 微服务 /metrics 端点挂载 | **12/12** | ✅ |

**评分**: **C+ (60/100)** — 基础 RED 完整, USE 部分, 业务全废。

---

## 2. 12 微服务 /metrics 端点挂载审计

通过 grep `mount_health\(app\)` 在 `backend/services/*/main.py`:

```
agent_service/main.py:64          mount_health(app)
annotation_service/main.py:41    mount_health(app)
asset_service/main.py:53         mount_health(app)
cleaning_service/main.py:28       mount_health(app)
collection_service/main.py:31    mount_health(app)
dataset_service/main.py:69       mount_health(app)
evaluation_service/main.py:40    mount_health(app)
notification_service/main.py:50  mount_health(app)
scoring_service/main.py:39       mount_health(app)
search_service/main.py:65        mount_health(app)
user_service/main.py:43          mount_health(app)
workflow_service/main.py:47      mount_health(app)
```

**100% 挂载 ✅** (12/12 service `mount_health(app)`)

`backend/common/health.py:118-164` 的 `mount_health()` 挂载 3 个端点:
- `/healthz` (liveness)
- `/readyz` (readiness, 默认检查 DB)
- `/metrics` (Prometheus text)

`pytest tests/test_common.py::test_service_health_metrics` 已覆盖 12 × 3 = 36 个端点。

---

## 3. RED 指标完整性 (Rate / Error / Duration)

### 3.1 主应用 (imdf.api._common.metrics)

| Metric | Type | Labels | 实测位置 |
|---|---|---|---|
| `imdf_http_requests_total` | Counter | method, endpoint, status | metrics.py:65 |
| `imdf_http_request_duration_seconds` | Histogram | method, endpoint | metrics.py:71 |
| `imdf_http_request_errors_total` | Counter | method, endpoint, status | metrics.py:78 |

**Histogram buckets** (覆盖 5ms → 30s):
```
(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
```

→ **12 个 bucket**, 业界标准 (5ms-30s 覆盖 latency 99% 场景)

### 3.2 Per-Service (imdf.monitoring.service_metrics)

每个微服务一个独立 `CollectorRegistry`:

| Metric | Type | Labels | 实测位置 |
|---|---|---|---|
| `imdf_requests_total` | Counter | method, endpoint, status_code | service_metrics.py:63 |
| `imdf_request_latency_seconds` | Histogram | method, endpoint | service_metrics.py:69 |
| `imdf_errors_total` | Counter | type | service_metrics.py:76 |
| `imdf_active_connections` | Gauge | (none) | service_metrics.py:82 |
| `imdf_queue_depth` | Gauge | (none) | service_metrics.py:87 |
| `imdf_running_tasks` | Gauge | (none) | service_metrics.py:92 |
| `imdf_memory_rss_bytes` | Gauge | (none) | service_metrics.py:97 |

**Histogram buckets** (多 60s bucket, 13 个):
```
[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0]
```

### 3.3 Legacy (imdf.engines.metrics)

`engines/metrics.py` 是**纯文本生成**的 fallback, 不调 prometheus_client:

```python
# metrics.py:209-282
def _metric(help_line, type_line, name, labels, value):
    lines.append(f"# HELP {name} {help_line}")
    lines.append(f"# TYPE {name} {type_line}")
    lines.append(f'{name}{{{labels_str}}} {value}')
```

→ 在 prometheus_client 不可用时仍能输出 Prometheus text 格式。

Legacy 输出 metric (12 个):
- `imdf_uptime_seconds`
- `imdf_requests_total` (无 label, 全局)
- `imdf_requests_by_status{status_class}`
- `imdf_requests_by_endpoint{method,endpoint}`
- `imdf_errors_total`
- `imdf_active_connections`
- `imdf_active_ws_connections`
- `imdf_queue_depth`
- `imdf_running_tasks`
- `imdf_memory_rss_bytes`
- `imdf_memory_percent`
- `imdf_request_latency_seconds` (Summary 类型)

---

## 4. USE 指标完整性 (Utilization / Saturation / Errors)

| Metric | 实际 set 调用 | 数据来源 |
|---|---|---|
| `imdf_process_memory_rss_bytes` | ✅ **每次 render() 实时采样** | psutil.Process.memory_info().rss |
| `imdf_process_uptime_seconds` | ✅ **每次 render() 实时采样** | time.monotonic() - _PROCESS_START |
| `imdf_active_connections` | ⚠️ 默认未 set, 永远 0 | 应由 middleware 在 request 开始/结束时 inc/dec |
| `imdf_queue_depth` | ⚠️ 默认未 set | 应由 celery worker 周期上报 |
| `imdf_running_tasks` | ⚠️ 默认未 set | 应由 worker 周期上报 |
| `imdf_memory_rss_bytes` (per-svc) | ✅ `update_memory()` 在 render() 调用 | psutil |

**K8s 层 USE 指标** (来自 node-exporter / cAdvisor / postgres-exporter / redis-exporter):

| 来源 | Metric | 用途 |
|---|---|---|
| node-exporter | `node_cpu_seconds_total{mode}` | node CPU utilization |
| node-exporter | `node_memory_MemAvailable_bytes` | node memory available |
| node-exporter | `node_filesystem_avail_bytes{mountpoint}` | disk free |
| node-exporter | `node_network_receive_bytes_total` | network rx |
| cAdvisor | `container_cpu_usage_seconds_total` | pod CPU |
| cAdvisor | `container_memory_working_set_bytes` | pod memory |
| cAdvisor | `kube_pod_container_status_restarts_total` | restart count |
| postgres-exporter | `pg_stat_activity_count` | active conn |
| postgres-exporter | `pg_replication_lag_seconds` | replica lag |
| redis-exporter | `redis_memory_used_bytes` | Redis mem |
| redis-exporter | `redis_up` | liveness |

→ K8s 层 USE **完整**, 但取决于 exporter 真部署。

---

## 5. 业务指标 — 100% 缺失清单

下面这些 metric 在 `prometheus-rules.yaml` 和 dashboards 引用, 但**代码里 0 实现**:

### 5.1 AI Model 维度 (6 metric, 7 dashboard panel)

| Metric | 出处 | 代码中查找 | 状态 |
|---|---|---|---|
| `imdf_model_calls_total{model, provider, status, env}` | ai_business.json panels 2/3/7 + rules (无) | grep `imdf_model_` in backend → 0 hit | ❌ |
| `imdf_model_fallback_total` | ai_business.json panel 4 | 0 hit | ❌ |
| `imdf_model_cost_usd_total` | ai_business.json panel 5 | 0 hit | ❌ |
| `imdf_model_latency_seconds_bucket{model}` | ai_business.json panel 8 | 0 hit | ❌ |
| `imdf_model_cache_hits_total/misses_total` | ai_business.json panel 9 | 0 hit | ❌ |
| `imdf_model_tokens_total{direction}` | ai_business.json panel 10 | 0 hit | ❌ |

**实际代码路径**: `imdf/engines/model_gateway.py:779-970` 调用 LLM provider, 用 Python `print()` 输出 `body_str = f"{provider}|{model}|{tenant_id}|{success}|{cost_usd:.6f}|{tt}"` 而**不是 `Counter.labels(...).inc()`**。

### 5.2 Pipeline 维度 (2 metric, 1 rule)

| Metric | 出处 | 状态 |
|---|---|---|
| `imdf_pipeline_failures_total` | rules: PipelineFailureRateHigh | ❌ |
| `imdf_pipeline_executions_total` | rules: PipelineFailureRateHigh | ❌ |

**实际路径**: `services/workflow_service/dag_v2/` 应在 node execution 完成时 inc, 但未实现。

### 5.3 Billing / 计费维度 (1 metric, 1 rule)

| Metric | 出处 | 状态 |
|---|---|---|
| `imdf_billing_charges_usd_total` | rules: BillingAnomaly | ❌ |

→ 应在 `services/billing/routes.py` 计费完成后 inc。

### 5.4 Auth / Security (2 metric, 2 rule)

| Metric | 出处 | 状态 |
|---|---|---|
| `imdf_auth_login_failures_total` | rules: LoginFailureBurst | ❌ |
| `imdf_rate_limit_triggered_total` | rules: RateLimitTriggered | ❌ |

→ 应在 `services/user_service/auth.py` 登录失败时 inc。

### 5.5 Audit Chain (2 metric, 1 rule)

| Metric | 出处 | 状态 |
|---|---|---|
| `imdf_audit_chain_last_block_index` | rules: AuditChainBroken | ❌ |
| `imdf_audit_chain_expected_index` | rules: AuditChainBroken | ❌ |

→ `imdf/engines/audit_chain.py` 有完整审计链逻辑 (235 行), 但**未导出 metric**, 只在每次 append 后写 DB。

### 5.6 MemoryPalace (3 metric, 1 rule + 1 dashboard panel)

| Metric | 出处 | 状态 |
|---|---|---|
| `imdf_memory_palace_size_bytes` | rules: MemoryPalaceCapacityHigh | ❌ |
| `imdf_memory_palace_quota_bytes` | rules: MemoryPalaceCapacityHigh | ❌ |
| `imdf_memory_palace_ops_total{operation}` | dashboard panel 12 | ❌ |

→ `backend/services/agent_service/memory/` 应周期性 gauge.set()。

### 5.7 Skill Marketplace (1 metric, 1 rule + 1 dashboard)

| Metric | 出处 | 状态 |
|---|---|---|
| `imdf_skill_invocations_total{skill}` | rules: SkillMarketplaceAnomaly + dashboard panel 13 | ❌ |

→ 应在 plugin registry invoke 后 inc。

### 5.8 Agent 任务维度 (1 metric, 1 dashboard)

| Metric | 出处 | 状态 |
|---|---|---|
| `imdf_agent_task_duration_seconds_bucket` | dashboard panel 14 (P50/P95/P99) | ❌ |

→ 应在 `agents/base.py` 任务完成时 observe。

### 5.9 Ticket SLA (1 metric, 1 rule)

| Metric | 出处 | 状态 |
|---|---|---|
| `imdf_tickets_sla_breach_count{priority}` | rules: TicketSLABreach | ❌ |

→ `backend/tickets/sla_monitor.py:221` 有 `_persist_breach_alerts()`, 但未导出 metric。

### 5.10 Celery Queue (1 metric, 1 rule)

| Metric | 出处 | 状态 |
|---|---|---|
| `celery_queue_length{queue="default"}` | rules: CeleryQueueBacklog | ❌ |

→ Celery 未集成 (项目状态 0 celery), 引用了但永远 no data。

### 5.11 OSS Bucket (1 metric, 1 rule)

| Metric | 出处 | 状态 |
|---|---|---|
| `oss_bucket_size_bytes{bucket="imdf-assets"}` | rules: OSSBucketSizeAnomaly | ❌ |

→ 无 OSS exporter, 引用了但永远 no data。

---

## 6. Cardinality 风险评估

| Metric 类型 | 当前 labels | 估算 series 数 | 风险 |
|---|---|---|---|
| `imdf_http_requests_total` | method (5), endpoint (~50 路由), status (4) | 1000 | 低 ✅ |
| `imdf_http_request_duration_seconds` | method (5), endpoint (~50) | 250 buckets × 250 = 62.5K | 中 ⚠️ |
| `imdf_db_queries_total` | operation (5) | 5 | 低 ✅ |
| `imdf_cache_operations_total` | cache (3), op (4) | 12 | 低 ✅ |
| 假想 `imdf_model_calls_total` | model (10), provider (5), status (3), env (3) | 450 | 中 ✅ |
| 假想 `imdf_billing_charges_usd_total` | tenant_id (潜在 1000+) | 高 | ❌ 高 |

→ **加 tenant_id label 需谨慎**, 应先做 tenant 数量评估 + Prometheus 存储规划。

---

## 7. Custom / Per-tenant / Per-model / Per-agent 维度

**当前 labels 全局**:

| Metric | Labels |
|---|---|
| HTTP 请求类 | method, endpoint, status / status_code |
| DB | operation (select/insert/update/delete) |
| Cache | cache, op (hit/miss/set/delete) |
| Process | (none) |

**缺失维度** (业务要求但未实现):

| 维度 | 影响 | 建议 |
|---|---|---|
| `tenant_id` | 多租户隔离, per-tenant 成本/SLO | middleware 注入 (有 ContextVar, 但未透传到 metric label) |
| `user_id` | per-user 分析 | 同上 |
| `model` / `provider` | LLM 路由分析 | `engines/model_gateway.py` 注入 |
| `agent_id` | per-agent 性能 | `agents/base.py` 注入 |
| `trace_id` | metric-trace 关联 (Exemplar 模式) | OpenMetrics Exemplar |

→ **所有业务维度 label 缺失**, dashboards 即使 metric 存在也无法 per-tenant 切片。

---

## 8. OTLP Push vs Pull

`prometheus.yaml:34-40`:
```yaml
otlp:
  receiver:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318
```

→ **OTLP push receiver 已 enable** (line 247 `--enable-feature=otlp-write-receiver`)

但应用代码:
- ❌ 0 处调用 OTLP gRPC client push
- ❌ 0 处使用 prometheus_client 的 push_to_gateway
- ❌ 只有 `pushgateway.monitoring.svc.cluster.local:9091` scrape job, 但应用未 push

→ **OTLP push 框架就绪, 实际 0 调用**。短任务 (celery worker / 离线 batch) 应用 push, 但项目目前 0 celery + 0 batch push。

---

## 9. 实测验证命令

```powershell
# 1. 启动 uvicorn (main app + 12 svc 任意一个)
cd D:\Hermes\生产平台\nanobot-factory\backend
python -m uvicorn server:app --host 0.0.0.0 --port 8765

# 2. curl /metrics
$r = Invoke-WebRequest http://localhost:8765/metrics
# 期望: nanobot_* namespace (legacy server.py), 或 imdf_* (canvas_web via /metrics/json 间接)

# 3. curl /healthz /readyz (main 入口会 404, 12 svc 才挂载)
$r1 = Invoke-WebRequest http://localhost:8001/healthz -UseBasicParsing  # user_service
$r2 = Invoke-WebRequest http://localhost:8001/metrics -UseBasicParsing
# 期望: HTTP 200, /metrics 含 imdf_* metric

# 4. 验证业务 metric (应 no data)
$r = Invoke-WebRequest http://localhost:8001/metrics -UseBasicParsing
($r.Content -split "`n") | Where-Object { $_ -match '^imdf_(model_|pipeline_|billing_|audit_chain_|skill_)' }
# 期望: 0 行
```

---

## 10. Metrics 改进优先级

### P0 — 阻塞业务 dashboard

1. **埋点 19+ 业务 metric** (model_calls, pipeline_failures, billing_charges, audit_chain_last_block_index, etc.) — 估 2-3 人天
2. **加 tenant_id label** 到 HTTP/DB/Cache metric — 1 人天

### P1 — 增强维度

3. **加 model/provider/agent label** — 1 人天
4. **修复 `server.py` vs `imdf.api._common.metrics.py` 双 metric 路径** (选其一) — 1 人天
5. **OTel Exemplar** 把 trace_id 附在 metric — 2 人天

### P2 — nice-to-have

6. **Cardinality 监控** + 高基维度 alert
7. **Metric 自描述文件** (.json per metric)
8. **Business metric unit test** (每次 inc 后断言)

---

## 11. 总结

- **基础 RED/USE 完整** ✅
- **12 svc /metrics 挂载** ✅
- **业务 metric 100% 缺失** ❌ — 这是阻塞业务 dashboard 唯一的根因
- **tenant_id / model / agent 维度 0 实现** ❌
- **server.py vs imdf 双 metric 路径** ⚠️ (legacy nanobot_* 命名冲突)

**建议**: 把本审计作为 P11 / P12 sprint 的 P0-1 任务, 集中补 19+ 业务 metric + tenant_id 维度, 估 1 人周工作量。