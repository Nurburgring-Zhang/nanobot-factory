# P10R4-4 Alerting 深度审计 (21 规则 + SLO)

**报告**: 21 规则 + SLO 缺位 + 多维度告警 + Alertmanager 路由
**日期**: 2026-06-26

---

## 1. 总览

| 维度 | 状态 |
|---|---|
| 21 规则定义 | ✅ (prometheus-rules.yaml) |
| **规则真能触发** | **❌ 10/21 (47%) 永远 no data** |
| 6 规则需额外组件 | ⚠️ kube-state, postgres-exporter, redis-exporter, celery, OSS |
| SLO burn-rate alert | ❌ 0 实现 |
| Per-service 告警 | ✅ 7 规则 |
| **Per-tenant 告警** | **❌ 0 规则** |
| Alertmanager route | ✅ critical/warning 分离 |
| PagerDuty 真实凭据 | ❌ placeholder |
| Slack 真实凭据 | ❌ placeholder |
| 抑制规则 | ✅ inhibit_rules |
| 升级策略 | ❌ 无 |

**评分**: **D+ (50/100)** — 21 规则形式完整, 47% 永远 no data。

---

## 2. 21 规则详细审计 (prometheus-rules.yaml)

### 2.1 Group 1: imdf_service_alerts (7 rules)

| # | Rule | Severity | PromQL 引用 metric | metric 状态 |
|---|---|---|---|---|
| 1 | `ImdfServiceHighErrorRate` | critical | `imdf_requests_total{status_code=~"5.."}` | ✅ 12 svc 有 |
| 2 | `ImdfServiceHighLatency` | warning | `imdf_request_latency_seconds_bucket` | ✅ 12 svc 有 |
| 3 | `ImdfServiceLowThroughput` | warning | `imdf_requests_total` (offest 1d) | ✅ 12 svc 有 |
| 4 | `ImdfGatewayDown` | critical | `up{job="imdf-gateway"}` | ⚠️ job 未定义 (12 svc 不用 imdf-gateway job) |
| 5 | `ImdfServiceDown` | critical | `up{job=~"imdf-.*"}` | ✅ 12 svc 有 |
| 6 | `ImdfServiceRestartLoop` | critical | `kube_pod_container_status_restarts_total` | ⚠️ 需 kube-state-metrics |
| 7 | `ImdfServiceHighMemory` | warning | `container_memory_working_set_bytes` | ⚠️ 需 cAdvisor (默认有) |

**Subtotal**: 4 真能触发 (#1, #2, #3, #5), 3 需额外组件 (#4, #6, #7)。

### 2.2 Group 2: imdf_resource_alerts (6 rules)

| # | Rule | Severity | PromQL | metric 状态 |
|---|---|---|---|---|
| 8 | `PostgresConnectionsHigh` | warning | `pg_stat_activity_count / pg_settings_max_connections > 0.85` | ⚠️ 需 postgres-exporter |
| 9 | `PostgresReplicationLag` | critical | `pg_replication_lag_seconds > 60` | ⚠️ 需 postgres-exporter (single node 永不触发) |
| 10 | `RedisMemoryHigh` | warning | `redis_memory_used_bytes / redis_memory_max_bytes > 0.80` | ⚠️ 需 redis-exporter |
| 11 | `RedisDown` | critical | `redis_up == 0` | ⚠️ 需 redis-exporter |
| 12 | `CeleryQueueBacklog` | warning | `celery_queue_length{queue="default"} > 10000` | ❌ Celery 未集成 |
| 13 | `OSSBucketSizeAnomaly` | warning | `oss_bucket_size_bytes` | ❌ OSS exporter 缺 |

**Subtotal**: 0 真能触发 (全需额外组件)。

### 2.3 Group 3: imdf_business_alerts (5 rules)

| # | Rule | Severity | PromQL | metric 状态 |
|---|---|---|---|---|
| 14 | `PipelineFailureRateHigh` | critical | `imdf_pipeline_failures_total / imdf_pipeline_executions_total > 0.10` | ❌ **no data** |
| 15 | `BillingAnomaly` | warning | `imdf_billing_charges_usd_total` (5x baseline) | ❌ **no data** |
| 16 | `TicketSLABreach` | critical | `imdf_tickets_sla_breach_count{priority}` | ❌ **no data** |
| 17 | `MemoryPalaceCapacityHigh` | warning | `imdf_memory_palace_size_bytes / imdf_memory_palace_quota_bytes > 0.90` | ❌ **no data** |
| 18 | `SkillMarketplaceAnomaly` | info | `imdf_skill_invocations_total` (200% deviation) | ❌ **no data** |

**Subtotal**: 0 真能触发 (5/5 业务 metric 未埋)。

### 2.4 Group 4: imdf_security_alerts (3 rules)

| # | Rule | Severity | PromQL | metric 状态 |
|---|---|---|---|---|
| 19 | `LoginFailureBurst` | warning | `sum(rate(imdf_auth_login_failures_total[5m])) > 5` | ❌ **no data** |
| 20 | `RateLimitTriggered` | warning | `sum(rate(imdf_rate_limit_triggered_total[5m])) > 10` | ❌ **no data** |
| 21 | `AuditChainBroken` | critical | `imdf_audit_chain_last_block_index - imdf_audit_chain_expected_index > 5` | ❌ **no data** |

**Subtotal**: 0 真能触发 (3/3 安全 metric 未埋)。

### 2.5 统计汇总

| 类别 | 规则数 | 真能触发 | 需额外组件 | 永远 no data |
|---|---|---|---|---|
| Service (Group 1) | 7 | 4 | 3 | 0 |
| Resource (Group 2) | 6 | 0 | 4 | 2 |
| Business (Group 3) | 5 | 0 | 0 | **5** |
| Security (Group 4) | 3 | 0 | 0 | **3** |
| **Total** | **21** | **4 (19%)** | **7 (33%)** | **10 (48%)** |

→ **仅 4/21 规则真正能用**, **10/21 永远 no data**。

---

## 3. prometheus.yaml 内嵌 6 规则 (历史遗留)

`prometheus.yaml:158-215` 还有 6 个 alert rules (在 ConfigMap `prometheus-rules`):

| # | Rule | Severity | 备注 |
|---|---|---|---|
| A | `IMDFHighP99Latency` | warning | 与 #2 重复 (不同 PromQL 形式) |
| B | `IMDFHighErrorRate` | critical | 与 #1 重复 |
| C | `IMDFQueueBacklog` | warning | 与 `imdf_queue_depth > 1000` 类似 |
| D | `PostgresDiskFull` | critical | 与 #8 类似 (不同 metric) |
| E | `RedisMemoryHigh` | warning | 与 #10 重复 |
| F | `MicroserviceDown` | critical | 与 #5 类似 |

**Total including duplicates**: 21 + 6 = **27 rules in cluster**, 但有 4-5 个重复。

→ **建议**: 删 prometheus.yaml 内嵌规则, 只保留 prometheus-rules.yaml 的 21 规则。

---

## 4. SLO 错误预算告警 (❌ 完全缺位)

### 4.1 应有但缺

| SLO 类型 | 应有 | 当前 |
|---|---|---|
| 可用性 SLO (e.g. 99.9% monthly) | burn-rate alert (1h/6h windows) | ❌ |
| 延迟 SLO (e.g. P95 < 500ms) | burn-rate alert | ❌ |
| 错误预算剩余 | dashboard panel | ❌ |
| SLO status (budget remaining) | Alertmanager annotation | ❌ |

### 4.2 Google SRE Workbook 标准

SLO 99.9% (43.2 min/month budget), burn-rate alerts:

```
# Page (1h short, 5m long): burn rate > 14.4x
(sum(rate(sli_errors[5m])) / sum(rate(sli_total[5m]))) > (1 - 0.999) * 14.4

# Ticket (6h short, 30m long): burn rate > 6x
(sum(rate(sli_errors[30m])) / sum(rate(sli_total[30m]))) > (1 - 0.999) * 6
```

→ **本项目 0 SLO 规则, 0 burn-rate alert**, 业界 Datadog / New Relic / Honeycomb 标配。

### 4.3 缺失成本

- ❌ 无 SLO 状态可视化, PM 看不到产品可用性
- ❌ 无 burn-rate 早期预警, 故障总在最后 10% budget 才发现
- ❌ 无 per-service SLO, 不知道哪个服务拖累整体可用性
- ❌ 无 OKR / KPI 对齐

### 4.4 推荐 SLO 列表 (本项目)

| Service | SLO | Window | Burn-rate Alert |
|---|---|---|---|
| imdf-main | 99.5% / P95 < 1s | 30d | 1h 14.4x, 6h 6x |
| user_service | 99.9% | 30d | 1h 14.4x, 6h 6x |
| agent_service | 99% / P95 < 5s | 30d | 1h 14.4x |
| billing_service | 99.99% | 30d | 1h 14.4x (营收关键) |
| ... | | | |

---

## 5. 多维度告警

### 5.1 Per-service (✅ 部分)

`ImdfServiceHighErrorRate` 等 7 规则用 `by (microservice)` label, **自动 per-service 触发**:

```promql
sum by (microservice) (rate(imdf_requests_total{status_code=~"5.."}[5m]))
/ sum by (microservice) (rate(imdf_requests_total[5m])) > 0.05
```

→ **12 svc 各自 1 条告警**, 不会聚合成 1 条。

### 5.2 Per-tenant (❌ 0 规则)

```promql
# 应该但没有
sum by (tenant_id) (rate(imdf_requests_total{status_code=~"5.."}[5m]))
/ sum by (tenant_id) (rate(imdf_requests_total[5m])) > 0.10
```

→ **所有规则都无 tenant_id 维度**, 大客户 (Enterprise tier) 服务降级也只触发通用 alert, 无法快速定位。

### 5.3 Per-model (❌ 0 规则)

```promql
# 应该但没有
sum by (model) (rate(imdf_model_latency_seconds_bucket{le="2.5"}[5m]))
/ sum by (model) (rate(imdf_model_calls_total[5m])) > 0.05
```

→ **所有 LLM 模型调用延迟/失败无独立 alert**, GPT-4 慢 / Claude 3 限流 / Gemini 失败都隐藏在总指标里。

### 5.4 Per-endpoint (✅ 隐式)

每个 endpoint 单独 label, 隐式 per-endpoint alert。

---

## 6. Alertmanager 路由 (alertmanager.yaml:27-69)

### 6.1 当前 route tree

```yaml
route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default-receiver'
  routes:
    - matchers: [severity="critical"]
      receiver: 'pager-receiver'
      group_wait: 10s
      repeat_interval: 1h
    - matchers: [severity="warning"]
      receiver: 'slack-receiver'
      repeat_interval: 6h
```

### 6.2 评估

| 维度 | 评分 |
|---|---|
| 严重度分离 (critical vs warning) | ✅ |
| Group by alertname+cluster+service | ✅ (避免 alert 风暴) |
| Group wait 10s for critical | ✅ (快速告警) |
| Group wait 30s default | ✅ |
| Repeat interval 1h critical, 4h default, 6h warning | ✅ 业界标准 |
| Time interval 持续 5m | ✅ |

### 6.3 缺失

| 应有 | 当前 |
|---|---|
| Maintenance window (silence) | ❌ 无 |
| Escalation policy (L1 → L2 → L3) | ❌ 无 |
| 值班轮换 | ❌ 无 (PagerDuty 端做) |
| Alertmanager 集群 (HA) | ❌ replicas: 1 |
| 抑制规则 | ✅ inhibit_rules (line 66-69) |

### 6.4 抑制规则

```yaml
inhibit_rules:
  - source_matchers: [severity="critical"]
    target_matchers: [severity="warning"]
    equal: [alertname, cluster, service]
```

✅ **Critical 抑制同 alertname+cluster+service 的 warning**, 避免 alert 风暴。

---

## 7. Receivers (alertmanager.yaml:44-65)

### 7.1 default-receiver

```yaml
- name: 'default-receiver'
  webhook_configs:
    - url: 'http://alertmanager-webhook.monitoring.svc.cluster.local:5001/alerts'
      send_resolved: true
```

✅ Webhook to internal webhook service
⚠️ Service `alertmanager-webhook` 在 K8s manifest 中**未定义**

### 7.2 pager-receiver (Critical)

```yaml
- name: 'pager-receiver'
  pagerduty_configs:
    - service_key: 'REPLACE-WITH-PAGERDUTY-SERVICE-KEY'  # ❌ placeholder
      send_resolved: true
  webhook_configs:
    - url: 'http://alertmanager-webhook.monitoring.svc.cluster.local:5001/critical'
      send_resolved: true
```

❌ **PagerDuty service_key 是 placeholder**, 生产前必须替换为真实 key

### 7.3 slack-receiver (Warning)

```yaml
- name: 'slack-receiver'
  slack_configs:
    - api_url: 'https://hooks.slack.com/services/REPLACE/WITH/WEBHOOK'  # ❌ placeholder
      channel: '#imdf-alerts'
      send_resolved: true
      title: '{{ .CommonAnnotations.summary }}'
      text: '{{ range .Alerts }}{{ .Annotations.description }}\n{{ end }}'
```

❌ **Slack webhook URL 是 placeholder**, 生产前必须替换

### 7.4 模板

`alertmanager.yaml:24-25`:
```yaml
templates:
  - '/etc/alertmanager/templates/*.tmpl'
```

⚠️ **引用了 template 路径, 但 Deployment 没 mount 任何 ConfigMap 到 `/etc/alertmanager/templates/`** (volumes 只有 config + storage, 无 templates volumeMount)

→ **模板系统挂空**, 实际用 alertmanager 默认模板。

---

## 8. 实际 alert 触发路径 (12 svc 真接入)

### 8.1 imdf-main (canvas_web)

- ✅ `/metrics` 端点存在 (`canvas_web.py` 通过 `api.metrics_routes.py`)
- ✅ TraceIDMiddleware 已挂
- ⚠️ 但 `server.py` 走 `nanobot_*` namespace, 与 prometheus 规则 `imdf_*` 不匹配

→ **如果生产用 server.py 启动**, 12 svc scrape OK 但 main app scrape 全部失效 (命名不匹配)。

### 8.2 12 微服务

- ✅ `/metrics` 端点 (via `mount_health`)
- ✅ `imdf_*` namespace (via `common.health._render_metrics()`)
- ⚠️ TraceIDMiddleware **未挂** (12 svc main.py 没调)
- ⚠️ FastAPI auto-instrument **未启用**

→ **12 svc scrape OK, 但 trace 数据 0, 业务 metric 0**。

---

## 9. 告警验证命令

```bash
# 1. 检查 promtool 是否能 validate rules
promtool check rules monitoring/prometheus-rules.yaml
# 期望: SUCCESS, 21 rules parsed

# 2. 检查 alert 状态 (需 prometheus running)
curl -s http://prometheus:9090/api/v1/rules | jq '.data.groups[].rules[].name'
# 期望: 21 个 alert name

# 3. 触发测试 alert (发送大流量)
hey -n 1000000 -c 100 http://imdf-main:8765/api/chat
# 期望 (修复后): ImdfServiceHighErrorRate / ImdfServiceHighLatency firing

# 4. 检查 Alertmanager
curl -s http://alertmanager:9093/api/v1/alerts
# 期望: 当前 firing alert 列表
```

---

## 10. 修复优先级

### P0 — 必修

1. **补 14+ 业务 metric 埋点** (model/pipeline/billing/skill/audit/ticket/memory_palace)
2. **补 3 个安全 metric 埋点** (login_failures / rate_limit_triggered / audit_chain_index)
3. **替换 PagerDuty / Slack 真实凭据** (用 secretKeyRef)
4. **修复 12 svc main.py 加 mount_health + setup_tracing**

### P1 — 重要

5. **加 4-6 个 SLO + burn-rate alert** (per-service)
6. **加 per-tenant / per-model alert** (业务关键)
7. **部署 postgres-exporter + redis-exporter + kube-state-metrics**
8. **Alertmanager HA** (replicas: 3)

### P2 — nice-to-have

9. **删 prometheus.yaml 内嵌的 6 rules** (与 prometheus-rules.yaml 重复)
10. **Alertmanager template ConfigMap** (alert 模板)
11. **Escalation policy** (PagerDuty 端)
12. **Silence / maintenance window UI**

---

## 11. 总结

| 子项 | 评分 |
|---|---|
| 21 规则定义 | **A** |
| 规则真能触发 (19%) | **F** |
| SLO burn-rate | **F** |
| Per-service alert | **B** |
| Per-tenant alert | **F** |
| Alertmanager route | **A** |
| Receivers 凭据 | **F** (placeholder) |
| 抑制规则 | **B** |
| 升级策略 | **F** |
| 模板 | **D** (空挂载) |
| **整体** | **D+ (50)** |

**关键洞察**: **告警不是"规则定义"问题, 是"业务 metric 缺失"问题**。补业务 metric 是 P0, 4/21 → 21/21 真能触发。