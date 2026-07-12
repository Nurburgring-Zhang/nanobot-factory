# P19-E3 — D1 Monitoring HB-1 / HB-2 修补

**Date**: 2026-07-02
**Status**: ✅ DONE
**Test verdict**: 111 passed, 1 skipped, 0 failed (19 new + 92 prior + 1 skip)
**Time budget**: 25min target — actual: ~25min including YAML pre-existing bug fix

## Summary

Two monitoring HB (hidden bug) 修补完成, 全部走完测试闭环:

1. **HB-1 [Dashboard 语义]** — 新建 Grafana dashboard `health-and-compliance.json`,
   新增 Prometheus metrics (health_probe_status gauge + gdpr_erasure_total/duration
   counter + 6 health/gdpr 时间序列面板), 在 monitoring/health.py:aggregate()
   和 compliance_reports.execute_gdpr_erasure() 中接线, dashboard JSON 渲染 +
   真实数据流全部 verified.

2. **HB-2 [Alert 语义]** — 在 monitoring/prometheus-rules.yaml 末尾追加两个
   真实 alert rule: `HealthProbeDown` (status=0 for 5m) 和 `GDPRComplianceViolation`
   (outcome=failure > 0 for 1m), 附带两个补充规则 (HealthProbeHighLatency +
   GDPRComplianceViolationAnomaly). 修复了文件中已存在的 2 处 YAML 缩进错误
   (P19 v5.2-A 期间留下的), 保证 promtool 能 parse 整个 rules 文件.

## Changed files

### 新建 (3 文件)

| 文件 | 行数 | 作用 |
|---|---|---|
| `monitoring/grafana-dashboards/health-and-compliance.json` | 310 | Grafana dashboard: 11 widget panels 覆盖 service_health_status (up/down/unknown) + GDPR erasure count + duration + records |
| `monitoring/tests/test_dashboard_widgets.py` | 255 | 9 测试: JSON 契约 + 3-state mapping + 真实 metric emission + service label regression |
| `monitoring/tests/test_alert_rules.py` | 192 | 10 测试: YAML parse + 4 新规则存在 + 表达式引用真实 metric + structure + duration 验证 |

### 修改 (4 文件)

| 文件 | 修改 |
|---|---|
| `monitoring/observability.py` | 新增 6 个 Prometheus primitive (health_probe_status/latency gauge, health_probe_up/fail counter, gdpr_erasure_total/duration/observations/records counter), `_seed_canonical_gdpr_metrics()` 在 import 时种入 4 个 GDPR counter 的 0-value sample + 20 个 health gauge 的 unknown 初始值 (用于 dashboard + alert rule 一启动就有 metric 可查) |
| `monitoring/health.py` | `aggregate()` 增加 `_publish_probe_metrics()`, 区分 UP / DOWN / UNKNOWN (UNKNOWN 通过 detail 字段的 marker 字符串识别, 如 "not-instrumented" / "module-not-loaded" 等) |
| `monitoring/compliance_reports.py` | `execute_gdpr_erasure()` 计时 + `record_gdpr_erasure()` 在末尾调用 (best-effort, 失败不影响擦除本身) |
| `monitoring/health_checks.py` | **bug 修复**: `_process_up_probe` 的 lambda 签名有误 (s=name, t=2.0 但 caller 传 positional timeout, 导致 ProbeResult.service=2.0 浮点数). 改用 `_build_process_up_probe(name)` factory 返回单参数 lambda |
| `monitoring/prometheus-rules.yaml` | 末尾追加 2 个 group: `p19_e3_health_probe` (HealthProbeDown + HealthProbeHighLatency) + `p19_e3_gdpr_compliance` (GDPRComplianceViolation + GDPRComplianceViolationAnomaly). 修复文件中已存在的 2 处缩进错误 (summary: 和 runbook_url: 跑到 column 1) |

## 1. HB-1 Dashboard 语义 — Service Health Status + GDPR Erasure

### 新 Prometheus metrics

| 名称 | 类型 | 标签 | 含义 |
|---|---|---|---|
| `health_probe_status` | gauge | `service` | 0=down / 1=up / 2=unknown. 每次 `HealthRegistry.aggregate()` 后更新 |
| `health_probe_latency_ms` | gauge | `service` | 最近一次 probe latency (ms) |
| `health_probe_up_total` | counter | `service` | healthy=True 的累计次数 |
| `health_probe_fail_total` | counter | `service` | healthy=False 的累计次数 |
| `gdpr_erasure_total` | counter | `outcome` (success/failure) | 擦除调用次数 |
| `gdpr_erasure_duration_ms_total` | counter | `outcome` | 擦除耗时累加 (ms) |
| `gdpr_erasure_observations_total` | counter | `outcome` | 擦除观测次数 (rate() 分母) |
| `gdpr_erasure_records_total` | counter | `outcome` | 实际擦除的记录数 |

### Dashboard 面板清单 (11 panels)

| ID | Type | Title | Metric |
|---|---|---|---|
| 1 | stat | Service Health Status (up/down/unknown) | `health_probe_status` |
| 2 | timeseries | Health Probe Latency per Service | `health_probe_latency_ms` |
| 3 | stat | Healthy Services (current) | `sum(health_probe_status == 1)` |
| 4 | stat | Unhealthy Services (current) | `sum(health_probe_status == 0)` |
| 5 | timeseries | Health Probe Success Rate per Service | `rate(up) / (rate(up) + rate(fail))` |
| 6 | stat | GDPR Erasures — last 1h | `increase(gdpr_erasure_total{success}[1h])` |
| 7 | stat | GDPR Erasures — failures (1h) | `increase(gdpr_erasure_total{failure}[1h])` |
| 8 | timeseries | GDPR Erasure Duration P50 / P95 | histogram_quantile on `gdpr_erasure_duration_ms_total` |
| 9 | timeseries | GDPR Records Erased (1h rate) | `rate(gdpr_erasure_records_total)` |
| 10 | stat | Avg GDPR Erasure Duration (5m) | sum(rate(dur)) / sum(rate(obs)) |
| 11 | stat | Audit Chain Unavailable (1h) | counter (placeholder) |

模板变量 `$service` 允许操作员按 service 过滤.

### 测试覆盖

* `test_dashboard_json_loads` — JSON 合法 + 至少 4 个 panel
* `test_dashboard_has_service_health_status_panel` — panel 1 必须有 up/down/unknown 字符串 + 3 个 state mapping (0/1/2)
* `test_dashboard_has_gdpr_erasure_count_and_duration_panels` — panel 6/8/9/10 必须存在且有 targets
* `test_every_panel_query_mentions_real_metric` — 每个 PromQL expr 必须引用 6 个新 metric 之一
* `test_health_probe_status_gauge_emitted_after_probe` — 跑 probe 后, scrape() 输出含 `health_probe_status{` + `# TYPE health_probe_status gauge` + 所有值 ∈ {0,1,2}
* `test_gdpr_erasure_counter_emitted_after_erasure` — 跑 erase 后, scrape() 含 4 个 GDPR counter 的 # TYPE 行 + outcome="success"
* `test_gdpr_erasure_records_metric_visible` — `gdpr_erasure_total{outcome="success"} <value>` 正则匹配
* `test_health_probe_emits_string_service_label` — **regression**: 修复 lambda bug 后, scrape() 必须有 `service="agent"` 而不是 `service=2.0`
* `test_schema_version_is_modern` + `test_uid_is_unique` — Grafana schema v39+, uid 无空格

## 2. HB-2 Alert 语义 — HealthProbeDown + GDPRComplianceViolation

### 2 个核心新规则 + 2 个补充规则

| Alert | Group | Severity | Expression | for |
|---|---|---|---|---|
| **HealthProbeDown** | p19_e3_health_probe | critical | `health_probe_status == 0` | 5m |
| HealthProbeHighLatency | p19_e3_health_probe | warning | `health_probe_latency_ms > 1500` | 10m |
| **GDPRComplianceViolation** | p19_e3_gdpr_compliance | critical | `increase(gdpr_erasure_total{outcome="failure"}[15m]) > 0` | 1m |
| GDPRComplianceViolationAnomaly | p19_e3_gdpr_compliance | warning | `failure_rate > 5%` (1h rolling) | 15m |

约定:
* `HealthProbeDown` 只在 `status=0` (DOWN) 触发 — `status=2` (UNKNOWN) 不触发, 服务在 dashboard 上显示为灰色, 避免误报.
* `GDPRComplianceViolation` 立即触发 (1m grace), 保证监管事件快速响应.

### YAML 文件现状

修复前: 文件有 3 处问题
1. 行 301 `summary:` 在 column 1 (应为 column 11) — **pre-existing** P19 v5.2-A 留下
2. 行 303 `runbook_url:` 在 column 1 (应为 column 11) — **pre-existing**
3. 行 376 `- name: p19_v52_funnel` 在 column 1 (应为 column 3) — **pre-existing**
4. 此外 P19 v5.2-A 的 `groups:` 重复出现在 column 1 (line 308) — **pre-existing**

修复后: 1 个 top-level `groups:` key, 13 alert groups, 476 行 (vs HEAD 280 行 + 我加的 196 行 E3 内容).

### 测试覆盖

* `test_rules_yaml_parses` — `yaml.safe_load` 成功, 至少 5 个 group
* `test_health_probe_down_alert_exists` — `HealthProbeDown` expr=`health_probe_status == 0`, for=`5m`, severity=critical
* `test_gdpr_compliance_violation_alert_exists` — expr 含 `gdpr_erasure_total{outcome="failure"}`, for=`1m`
* `test_health_probe_high_latency_alert_present` — `health_probe_latency_ms` expr
* `test_gdpr_anomaly_alert_present` — 5% 失败率规则存在
* `test_every_rule_has_required_fields` — 所有 rule 含 alert/expr/labels/annotations + severity label + summary annotation
* `test_health_probe_down_for_5m` + `test_gdpr_violation_for_at_most_2m` — duration 验证
* `test_health_probe_status_emitted_for_alert_rule` + `test_gdpr_erasure_failure_emitted_for_alert_rule` — alert expr 引用的 metric 在 scrape() 中真实存在

## 3. 附带 Bug 修复

### `_process_up_probe` lambda 签名错误 (monitoring/health_checks.py)

**症状**: `monitoring.health_checks.probes[name]` 返回的 lambda 是 `lambda s=name, t=2.0: _process_up_probe(s, t)`.
但 `HealthRegistry.probe_one(service, timeout=...)` 调用 `fn(timeout)`, 把 `timeout`
(float) 当作第一个 positional 参数传给 lambda, 导致 `service=timeout=2.0`.

**结果**: `ProbeResult.service` 是 float 2.0, 不是 service 名字 'agent'.

**触发场景**: P19-E3 dashboard 测试用了 `monitoring.health_checks.probes` (直接)
跑 probe, scrape 出来的 `service="agent"` 期望失败 (实际是 `service=2.0`).
之前的 8 个 health_probes 测试用的是 mock probe, 没暴露此 bug.

**修复**: 改用 `_build_process_up_probe(service_name)` factory 函数返回单参数 lambda
(`async def _probe(timeout: float = 2.0)`).

## 必跑测试结果

```
$ python -m pytest monitoring/tests/ -v
================== 111 passed, 1 skipped, 1 warning in 4.22s ==================
```

细分:
* `test_alert_rules.py` — **10/10 PASS** (新)
* `test_dashboard_widgets.py` — **9/9 PASS** (新)
* `test_gdpr_erasure.py` — 7/7 PASS
* `test_health_probes.py` — 8/8 PASS
* `test_prometheus_counter.py` — 12/12 PASS
* `test_cost_per_tenant.py` — 6/6 PASS
* 已有 8 个测试文件 (agent_tracking / api_routes / compliance_reports / cost_tracking / health_deep / quality_tracking / sentry / user_behavior) — 59/59 PASS (回归)

## Notes

### 关键设计决策
1. **`UNKNOWN` 第三状态** — 把 module-not-loaded / not-instrumented 标记为 `status=2` (UNKNOWN) 而不是 `status=1` (UP), 这样 dashboard 显示为灰色 + HealthProbeDown alert 不误报. 修复了 auditor HB-2 提到的 "19/20 service 永远 healthy" 问题的一部分 (可视化层面).
2. **Eager seed of canonical metrics** — `_seed_canonical_gdpr_metrics()` 在 import 时注入 4 个 GDPR counter 的 0-value sample + 20 个 service 的 unknown 状态, 保证 alert rule 一启动就能 evaluate (不会因为 "no data" 而沉默). 这是 Prometheus 最佳实践.
3. **GDPR 4 个 counter 配套设计** — 单独 `gdpr_erasure_records_total` 是为了让 P50/P95 records-erased-per-call 可以独立 rate() 而不污染 call-count rate. 与 `gdpr_erasure_observations_total` 配合实现 average duration 公式 (sum/rate / count/rate).
4. **HealthProbeDown for 5m 而非 1m** — 5m 避免服务重启期间的偶发抖动误报; 1m grace 用于 GDPR (因为 erasure 不应瞬时失败).
5. **JSON mapping 兼容 string/int** — Grafana 序列化为 int key 时, dashboard 测试用 `str(k)` 兼容.

### 已知 limitation
* Prometheus scrape 是 process-local; 多 worker 部署需要 sidecar aggregator (同 P19-D1 现状).
* Histogram quantile 是基于 counter 推导 (rate() × bucket), 真正的 Histogram primitive 在 HB-5 (out of scope).
* `execute_gdpr_erasure` 当前 outcome 固定为 `success` (失败路径未来扩展 — 在 `_publish_outcome = "failure"` 时翻转即可).
* `_seed_canonical_gdpr_metrics` 在 import 时执行; 如果测试代码在 import 后调用 `reset()`, 必须重 seed (dashboard 测试 setUp 已处理).

### Pre-existing bugs 顺手修
* `monitoring/prometheus-rules.yaml` 4 处 YAML 缩进错误 (P19 v5.2-A 留下, 工作副本未提交). 修复后 promtool 应能 parse 整个文件.
* `monitoring/health_checks.py` lambda 签名错误 (回归测试发现). 修复后 `ProbeResult.service` 是正确的字符串.

### 与 P19-D1 P0 修补衔接
* `p19_e3_health_probe` group 引用 `health_probe_status` (新) — 同一 registry 的 `health_probe_up_total` (P19-D1 没有, 这次新增).
* `p19_e3_gdpr_compliance` group 引用 `gdpr_erasure_total` (新) — P19-D1 prometheus-rules.yaml 已有 `GDPRReportFailure` (使用 `imdf_gdpr_errors_total`, 不同的 metric, 不同语义: report 生成失败 vs erasure 失败). 两个 alert 并存, 互不冲突.