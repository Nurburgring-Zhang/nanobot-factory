# P10R4-4 Dashboards 深度审计 (46 panels)

**报告**: Grafana 仪表盘 + 4 dashboards 完整度审计
**日期**: 2026-06-26

---

## 1. 总览

| 维度 | 状态 |
|---|---|
| Dashboard 数 (去重后) | **4** (Overview / Microservices / Database / AI 业务) |
| 实际 JSON 文件 | **8** (4 × 2 版本, 命名冲突) |
| Total panels (含 row) | **46** (9+10+13+14) |
| Real panels (非 row) | **38** |
| **数据完整度 (4 dashboard 平均)** | **~40%** |
| SLO dashboard | ❌ 缺位 |
| Per-tenant dashboard | ❌ 缺位 |
| 故障排查 dashboard | ❌ 缺位 |

**评分**: **C+ (60/100)** — 46 panels 在, 50% 无数据, 关键 dashboard 缺位。

---

## 2. 8 个 JSON 文件命名冲突审计

```
monitoring/grafana-dashboards/
├── overview.json                  uid=imdf-overview        9 panels
├── microservices.json             uid=imdf-microservices   10 panels
├── database.json                  uid=imdf-database        13 panels
├── ai_business.json               uid=imdf-ai-business     14 panels
├── dashboard-vdp-overview.json    uid=imdf-overview        9 panels  ← 重复!
├── dashboard-vdp-business.json    uid=imdf-microservices   10 panels ← 重复!
├── dashboard-vdp-infrastructure.json  uid=imdf-database    13 panels ← 重复!
└── dashboard-vdp-ai.json          uid=imdf-ai-business     14 panels ← 重复!
```

**问题**: 8 个 JSON → 4 个 uid, **Grafana 会冲突** (后启动的覆盖前面的)。

实测验证 (Python audit):
```
ai_business.json: title='nanobot-factory AI 业务总览 (VDP AI Overview)'  uid='imdf-ai-business'  panels=14
dashboard-vdp-ai.json: title='nanobot-factory AI 业务总览 (VDP AI Overview)'  uid='imdf-ai-business'  panels=14  ← 同 uid
```

→ **内容完全相同**, 是 P3-7 期间生成的 2 套命名 (IMDF 前缀 vs dashboard-vdp 前缀), 应保留一套。

**建议**: 删 `dashboard-vdp-*.json` 4 个文件, 只留 `overview/microservices/database/ai_business.json`。

---

## 3. 4 Dashboard 完整审计

### 3.1 Overview (uid=imdf-overview) — 9 panels

| # | Type | Title | Query | 数据状态 |
|---|---|---|---|---|
| 1 | stat | QPS (total) | `sum(rate(imdf_requests_total[1m]))` | ⚠️ 12 svc 有, imdf-main 无 (server.py 用 nanobot_*) |
| 2 | stat | P99 Latency (s) | `histogram_quantile(0.99, sum(rate(imdf_request_latency_seconds_bucket[5m])) by (le))` | ✅ |
| 3 | stat | Error Rate (%) | `sum(rate(imdf_requests_total{status_code=~"5.."}[5m])) / sum(rate(imdf_requests_total[5m]))` | ✅ |
| 4 | stat | Active Connections | `sum(imdf_active_connections)` | ❌ 默认未 set, 永远 0 |
| 5 | timeseries | Request rate by microservice | `sum by (microservice) (rate(imdf_requests_total[1m]))` | ✅ |
| 6 | timeseries | P95 latency by microservice | `histogram_quantile(0.95, sum by (le, microservice) (rate(imdf_request_latency_seconds_bucket[5m])))` | ✅ |
| 7 | timeseries | Memory RSS by microservice | `sum by (microservice) (imdf_memory_rss_bytes)` | ⚠️ 仅 per-svc set, sum 后可能空 |
| 8 | timeseries | Queue depth & running tasks | `sum(imdf_queue_depth)`, `sum(imdf_running_tasks)` | ❌ 默认未 set |
| 9 | **logs** | Recent error logs (Loki) | `{app="imdf-main"} \|= "level=error"` | ✅ |

**完整度**: **4/9 panel 真有数据 (44%)** + 2 个部分数据 + 3 个永远 0

**改进建议**:
- panel 4 / 8 需在 middleware 加 `active_connections.inc/dec()` 和 `queue_depth.set()`
- panel 1 需 main app 也走 `imdf_*` namespace

### 3.2 Microservices (uid=imdf-microservices) — 10 panels

| # | Type | Title | Query | 数据状态 |
|---|---|---|---|---|
| 1 | row | Per-Microservice | — | — |
| 2 | timeseries | Request rate (QPS) per microservice | `sum by (microservice) (rate(imdf_requests_total[1m]))` | ✅ |
| 3 | timeseries | P50 latency per microservice | `histogram_quantile(0.50, ...)` | ✅ |
| 4 | timeseries | P99 latency per microservice | `histogram_quantile(0.99, ...)` | ✅ |
| 5 | timeseries | 5xx error rate per microservice | `sum by (microservice) (rate(imdf_requests_total{status_code=~"5.."}[5m])) / sum by (microservice) (rate(imdf_requests_total[5m]))` | ✅ |
| 6 | row | Resource | — | — |
| 7 | timeseries | Memory RSS per microservice | `sum by (microservice) (imdf_memory_rss_bytes)` | ⚠️ |
| 8 | row | Connections | — | — |
| 9 | timeseries | Active connections per microservice | `sum by (microservice) (imdf_active_connections)` | ❌ 永远 0 |
| 10 | **traces** | Recent traces for $microservice | Jaeger query | ⚠️ Jaeger 空, traces panel 无数据 |

**完整度**: **5/7 real panel 有数据 (71%)** + 1 个 Jaeger 空 + 1 个永远 0

**改进建议**:
- panel 9 需 middleware active_connections
- panel 10 需 OTel SDK 装 + 真实流量

### 3.3 Database (uid=imdf-database) — 13 panels

| # | Type | Title | Query | 数据状态 |
|---|---|---|---|---|
| 1 | row | PostgreSQL | — | — |
| 2 | timeseries | Active connections | `pg_stat_activity_count` | ⚠️ 需 postgres-exporter |
| 3 | timeseries | Transactions per second (commit+rollback) | `rate(pg_stat_database_xact_commit[5m]) + rate(pg_stat_database_xact_rollback[5m])` | ⚠️ 需 exporter |
| 4 | timeseries | Tuples fetched vs inserted | `pg_stat_database_tup_fetched / pg_stat_database_tup_inserted` | ⚠️ 需 exporter |
| 5 | timeseries | Database size | `pg_database_size_bytes` | ⚠️ 需 exporter |
| 6 | timeseries | Slow queries (IMDF listener) | `rate(imdf_db_slow_queries_total[5m])` | ✅ (`api/_common/slow_query.py` 埋点) |
| 7 | row | Redis | — | — |
| 8 | timeseries | Cache hit ratio | `rate(imdf_cache_operations_total{op="hit"}[5m]) / sum(rate(imdf_cache_operations_total[5m]))` | ✅ |
| 9 | timeseries | Redis memory usage | `redis_memory_used_bytes` | ⚠️ 需 redis-exporter |
| 10 | timeseries | Redis ops/sec | `rate(redis_commands_total[5m])` | ⚠️ 需 exporter |
| 11 | timeseries | Connected clients | `redis_connected_clients` | ⚠️ 需 exporter |
| 12 | timeseries | Keyspace hit ratio | `rate(redis_keyspace_hits_total[5m]) / (rate(redis_keyspace_hits_total[5m]) + rate(redis_keyspace_misses_total[5m]))` | ⚠️ 需 exporter |
| 13 | timeseries | Evicted keys | `rate(redis_evicted_keys_total[5m])` | ⚠️ 需 exporter |

**完整度**: **2/11 real panel 有数据 (18%)** + 9 个需 exporter 部署

**改进建议**:
- 部署 postgres-exporter (`prometheus.yaml:138` static_config 已配)
- 部署 redis-exporter (`prometheus.yaml:143` 已配)
- 装上后 9 个 panel 立刻有数据

### 3.4 AI 业务 (uid=imdf-ai-business) — 14 panels

| # | Type | Title | Query | 数据状态 |
|---|---|---|---|---|
| 1 | row | 模型调用概览 | — | — |
| 2 | stat | 总调用次数 (24h) | `sum(increase(imdf_model_calls_total{env=~"$env", model=~"$model"}[24h]))` | ❌ |
| 3 | stat | 成功率 (%) | `sum(rate(imdf_model_calls_total{status="success",...}[5m])) / sum(rate(imdf_model_calls_total{...}[5m]))` | ❌ |
| 4 | stat | 降级次数 (5m) | `sum(increase(imdf_model_fallback_total{...}[5m]))` | ❌ |
| 5 | stat | 成本估算 ($/h) | `sum(rate(imdf_model_cost_usd_total{...}[1h])) * 3600` | ❌ |
| 6 | row | 性能与稳定性 | — | — |
| 7 | timeseries | 按模型的 QPS | `sum by (model) (rate(imdf_model_calls_total{...}[1m]))` | ❌ |
| 8 | timeseries | P95 延迟 (按模型) | `histogram_quantile(0.95, sum by (le, model) (rate(imdf_model_latency_seconds_bucket{...}[5m])))` | ❌ |
| 9 | timeseries | 缓存命中率 | `sum(rate(imdf_model_cache_hits_total[5m])) / (sum(rate(hits[5m])) + sum(rate(misses[5m])))` | ❌ |
| 10 | timeseries | Token 用量 (input+output) | `sum by (direction) (rate(imdf_model_tokens_total[5m])) * 60` | ❌ |
| 11 | row | MemoryPalace + Skill + Agent | — | — |
| 12 | timeseries | MemoryPalace 记忆写入/秒 | `sum by (operation) (rate(imdf_memory_palace_ops_total[...}[1m]))` | ❌ |
| 13 | timeseries | Skill Marketplace 调用 Top 10 | `topk(10, sum by (skill) (rate(imdf_skill_invocations_total{...}[5m])))` | ❌ |
| 14 | timeseries | Agent 协同任务时延 (P50/P95/P99) | `histogram_quantile(0.50/0.95/0.99, sum by (le) (rate(imdf_agent_task_duration_seconds_bucket{...}[5m])))` | ❌ |

**完整度**: **0/11 real panel 有数据 (0%)** — 全部 no data

**改进建议**: **必须补业务 metric** (`imdf_model_calls_total` 等 6 个), 否则 dashboard 永远空。

---

## 4. 缺失的关键 Dashboard

### 4.1 SLO Dashboard (❌ 缺位)

应有但缺:

```
SLO Dashboard (uid=imdf-slo)
├── 总体 SLO status (stat)
│   ├── 可用性 SLO 99.9% (当前 99.95%, budget 75% remaining)
│   ├── 延迟 SLO P95 < 500ms (当前 350ms, budget 90%)
│   └── 错误预算燃烧率 (1h / 6h / 24h / 7d windows)
├── per-service SLO grid (table)
│   ├── service name
│   ├── SLO target
│   ├── current SLI
│   ├── budget remaining
│   └── burn rate
└── SLO 趋势图 (timeseries × 4)
    ├── 30-day rolling
    ├── 7-day
    ├── 1-day
    └── burn rate alert history
```

### 4.2 Per-Tenant Dashboard (❌ 缺位)

应有但缺:

```
Tenant Dashboard (uid=imdf-tenant-acme)
├── stat: tenant tier / QPS / cost / latency / error rate
├── timeseries: tenant cost over time (USD)
├── timeseries: tenant request volume
├── table: top endpoints for tenant
├── logs: tenant-specific logs (LogQL: tenant_id="acme")
└── traces: tenant-specific traces (TraceQL: tenant.id="acme")
```

### 4.3 故障排查 Dashboard (Incident Triage) ❌

应有但缺 (Datadog Incident / New Relic NRQL 有专门视图):

```
Incident Dashboard
├── 当前 firing alerts (alert list)
├── service 健康地图 (heatmap)
├── error budget consumption (per-service)
├── 最近 deploy (deploy markers)
├── 最近 config change (annotation)
├── 关联 logs (text search with trace_id)
└── 关联 traces (timeline + flamegraph)
```

### 4.4 Pipeline 业务 Dashboard (❌)

应有但缺:

```
Pipeline Dashboard
├── stat: 当前运行 pipeline 数
├── stat: 24h 失败率
├── stat: 平均执行时长
├── timeseries: pipeline executions by status
├── timeseries: pipeline latency P50/P95/P99
├── table: top failing templates
└── logs: pipeline error logs
```

### 4.5 Audit / 合规 Dashboard (❌)

应有但缺:

```
Audit Dashboard
├── stat: audit chain 完整性 (last block index vs expected)
├── stat: 24h audit entries
├── timeseries: audit entries by type
├── timeseries: chain integrity score
└── logs: audit log events (LogQL: logger="audit")
```

---

## 5. 模板与变量审计

### 5.1 AI 业务 dashboard 的 template variables

```json
{
  "name": "model",
  "type": "query",
  "datasource": {"type": "prometheus", "uid": "Prometheus"},
  "query": "label_values(imdf_model_calls_total, model)",
  "refresh": 1,
  "includeAll": true,
  "multi": true
},
{
  "name": "provider",
  "type": "query",
  "query": "label_values(imdf_model_calls_total, provider)",
  ...
},
{
  "name": "env",
  "type": "custom",
  "query": "prod,staging,dev",
  ...
}
```

✅ Template 变量设计完整 (model / provider / env)。

⚠️ 但 `label_values(imdf_model_calls_total, model)` 在 metric 不存在时**永远返回空列表**, 整个 dashboard 实际 dropdown 也是空的。

### 5.2 其他 dashboard 缺变量

- overview.json: 无 template variable (✅ 简单 dashboard 不需要)
- microservices.json: 无 template variable (但应该有 `microservice` dropdown)
- database.json: 无 template variable (但应该有 `datname` dropdown)

---

## 6. 注释 (Annotations) 审计

### 6.1 AI 业务 dashboard 配 2 个 annotation

```json
{
  "name": "Model Deployments",
  "expr": "changes(imdf_model_version_info[5m]) > 0"
},
{
  "name": "Incidents",
  "expr": "ALERTS{alertstate=\"firing\", severity=\"critical\"}"
}
```

✅ Model deploys + incidents annotation

### 6.2 其他 dashboard 缺 annotation

- overview.json: 无 annotation
- microservices.json: 无 annotation
- database.json: 无 annotation

**应有 annotation**:
- Deploy events (K8s deployment change)
- Alert firing (cross-dashboard 一致)
- Config change (git push)
- DB migration

---

## 7. Datasource 配置审计

`grafana.yaml:17-44`:
```yaml
datasources:
  - name: Prometheus  url=http://prometheus.monitoring.svc.cluster.local:9090  isDefault=true
  - name: Jaeger      url=http://jaeger-query.monitoring.svc.cluster.local:16686  tracesToLogsV2.uid=loki
  - name: Loki        url=http://loki.monitoring.svc.cluster.local:3100
```

✅ 3 datasource 完整。

**缺失**:
- ❌ 无 `derivedFields` (Loki → Jaeger jump via trace_id)
- ❌ 无 PostgreSQL datasource (业务表直查)
- ❌ 无 Alertmanager datasource (alert 列表)

---

## 8. 命名 / uid 冲突解决

### 8.1 问题

8 JSON 文件, 4 unique uid → Grafana provisioning 时**后启动的覆盖前面的**。

### 8.2 解决方案

```bash
# 删除 dashboard-vdp-*.json 4 个文件
rm monitoring/grafana-dashboards/dashboard-vdp-*.json
```

保留:
- `overview.json` (uid=imdf-overview)
- `microservices.json` (uid=imdf-microservices)
- `database.json` (uid=imdf-database)
- `ai_business.json` (uid=imdf-ai-business)

### 8.3 备选方案

保留两套, 给 dashboard-vdp-* 加 `tags=["imdf", "vdp"]` 与原版区分, 或 `uid` 加后缀:
- `dashboard-vdp-overview.json` → uid=`imdf-overview-vdp`
- ...

→ 推荐方案 1 (删除), 避免重复维护。

---

## 9. 实际数据流验证 (smoke test)

实测 `server.py` 启动后:

```
GET /metrics → 200, body 1559 bytes
$ body 第一行: nanobot_requests_total{method="GET_/healthz"} 1
```

→ **server.py 输出 `nanobot_*`**, 但 dashboards 查 `imdf_*` → **完全不匹配**。

如果生产用 server.py 当 main 入口, **Overview dashboard 全部 panel 显示 "No data"**。

---

## 10. Grafana Deployment 资源

`grafana.yaml:217-224`:
```yaml
resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 1Gi
```

→ 1 副本, **单点** (HA 需 replicas: 2+)

→ 无 PVC / emptyDir, **dashboard 修改会丢** (e.g. UI 修改 / datasource config)

---

## 11. 改进优先级

### P0 — 必修

1. **补业务 metric** (imdf_model_calls_total 等 6+ 个) → AI dashboard 0/11 → 11/11 有数据
2. **删 dashboard-vdp-*.json 4 文件** → 解决 uid 冲突
3. **统一 metric namespace** (server.py 走 nanobot_* vs 12 svc 走 imdf_*) → 选一个

### P1 — 重要

4. **加 SLO Dashboard** (per-service error budget + burn rate)
5. **加 per-tenant Dashboard** (template variable: tenant_id)
6. **加 incident triage Dashboard** (故障排查专用)
7. **Grafana replicas: 2** (HA)
8. **持久化 Grafana storage** (PVC)

### P2 — nice-to-have

9. **template variable** 加到 microservices / database dashboard
10. **annotations** 加到所有 dashboard
11. **PostgreSQL / Alertmanager datasource** (跨数据源查询)
12. **trace_id → Loki/Jaeger 跳转** (derivedFields)

---

## 12. 总结

| 子项 | 评分 |
|---|---|
| 4 dashboard 数 | **A** |
| 46 panels (含 row) | **A** |
| Overview 完整度 | **44%** |
| Microservices 完整度 | **71%** |
| Database 完整度 | **18%** (需 exporter) |
| AI 业务 完整度 | **0%** (需业务 metric) |
| 平均完整度 | **40%** |
| SLO dashboard | **F** |
| Per-tenant dashboard | **F** |
| Trace/Logs panel 集成 | **B** (各 1 个) |
| Template variable | **C** (仅 AI 业务) |
| Annotations | **C** (仅 AI 业务) |
| Datasource 关联 | **C** (3 datasource 配, 跳转少) |
| **整体** | **C+ (60)** |

**总洞察**: 46 panels **形式**完整, **数据**严重缺失。补业务 metric + exporter 是 P0, dashboard 完整度可从 40% 跳到 85%+。