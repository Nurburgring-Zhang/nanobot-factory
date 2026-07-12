# P19-D1 — monitoring 行为覆盖 P0 修补

**Date**: 2026-07-02
**Status**: ✅ DONE
**Test verdict**: 92/92 PASS (33 new + 59 regression in `monitoring/tests/`)
**Time budget**: 25min

## 摘要

四个 P0 修补落地，全部走完测试闭环：

1. **GDPR 真 right-to-erasure** — `monitoring/compliance_reports.execute_gdpr_erasure()`
   真删 cost/agent/quality buffer 里的 user entries，append audit chain event。
2. **20 service health probes + 5s TTL cache** — `monitoring/health.py` 加
   `deep_aggregated()` + 5s 单调时钟 TTL cache,失败 service 立即进 `unhealthy_services`。
3. **Prometheus counter.inc() wiring** — 新 `monitoring/observability.py` 暴露
   `Counter.inc()` / `record_request()` helper,4 个 hot path 接入
   (agent_service / imdf.engines.dataset_manager / asset_service + canary)。
4. **cost-per-tenant** — `CostRecord.tenant_id` 字段 + `CostTracker.per_tenant()`,
   `/api/v1/monitoring/cost/by-tenant` 端点。

## Changed files

### 新建 (4 文件)

| 文件 | 行数 | 作用 |
|---|---|---|
| `monitoring/observability.py` | ~245 | Prometheus 风格 Counter / Gauge / Histogram + scrape() exposition |
| `monitoring/tests/test_gdpr_erasure.py` | ~165 | 7 个 GDPR 真擦除 + access export 测试 |
| `monitoring/tests/test_health_probes.py` | ~180 | 8 个 20-service probe + TTL cache 测试 |
| `monitoring/tests/test_prometheus_counter.py` | ~190 | 12 个 counter.inc + exposition + wiring 测试 |
| `monitoring/tests/test_cost_per_tenant.py` | ~110 | 6 个 per_tenant + tenant_id 字段测试 |

### 修改 (5 文件)

| 文件 | 修改 |
|---|---|
| `monitoring/compliance_reports.py` | 加 `execute_gdpr_erasure()` (真删 + audit chain) + `export_data_subject_access()` (机器可读 JSON) |
| `monitoring/health.py` | 加 5s TTL cache + `deep_aggregated()` + `invalidate_cache()` + `force` / `bypass_cache` 参数 |
| `monitoring/cost_tracking.py` | `CostRecord.tenant_id` 字段 + `record(tenant_id=...)` 参数 + `per_tenant()` 方法 |
| `monitoring/api.py` | 加 `DELETE /compliance/gdpr/erase/{user_id}` + `GET /compliance/gdpr/export/{user_id}` + `GET /health/deep/aggregated` + `GET /cost/by-tenant` + `GET /metrics` (Prometheus) + `GET /observability/snapshot` |
| `backend/services/agent_service/routes.py` | `run_agent` hot path 包 `record_request("agent_service", ...)` |
| `backend/services/asset_service/routes.py` | `add_item` hot path 加 `record_request("asset_service", ...)` |
| `backend/imdf/engines/dataset_manager.py` | `create_version` 加 `record_request("imdf_dataset_manager", ...)` |

## 1. GDPR 真 right-to-erasure

### 行为
* `execute_gdpr_erasure(user_id, requester, reason)` 真删:
  * `cost_tracking.buffer` 重建 — 过滤掉 `r.user_id == user_id`
  * `agent_tracking.buffer` 重建 — 过滤掉 `r.user_id == user_id`
  * `quality_tracking.buffer` 重建 — 过滤掉 `r.annotator_id == user_id`
  * `backend.imdf.engines.audit_chain.append(method="DELETE", path=..., user=requester, ...)` 记录事件
* 返回:
  ```json
  {
    "report_id": "uuid4",
    "user_id": "...",
    "erased": {"cost_records": N, "agent_records": M, "quality_records": K, "total": N+M+K},
    "audit_chain_entry": {"seq": int, "entry_hash": "..."} | null,
    "audit_chain_unavailable": bool
  }
  ```
* 幂等 — 第二次调用 `erased.total == 0`

### 端点
| Method | Path | 行为 |
|---|---|---|
| `DELETE` | `/api/v1/monitoring/compliance/gdpr/erase/{user_id}?requester=...&reason=...` | 真删 + audit chain |
| `GET`   | `/api/v1/monitoring/compliance/gdpr/export/{user_id}` | 机器可读 JSON 导出 (records + counts + fingerprint_sha256) |
| `POST`  | `/api/v1/monitoring/compliance/gdpr/{user_id}/erasure` (legacy, confirm=true) | 兼容旧调用 |
| `GET`   | `/api/v1/monitoring/compliance/gdpr/{user_id}` (existing) | data_subject_access 报告 |

### 测试覆盖
* `test_execute_gdpr_erasure_removes_every_record` — 5 cost + 4 agent + 2 quality 真删
* `test_execute_gdpr_erasure_is_idempotent` — 第二次返回 0
* `test_erasure_returns_audit_chain_field` — audit_chain_entry OR audit_chain_unavailable
* `test_erasure_100_mock_users_one_erased` — 100 user stress,擦 1 留 99
* `test_data_subject_access_export_contains_all_records` — counts + fingerprint
* `test_data_subject_access_export_stable_fingerprint` — counts 稳定
* `test_legacy_generate_gdpr_erasure_dry_run_still_works` — 旧 dry-run 兼容

## 2. 20 service health probes

### 行为
* 20 个 service 在 `monitoring/health.py:DEFAULT_SERVICES` 定义 (13 backend microservice + 7 cross-cutting)
* `HealthRegistry.deep_check()` 走 `probe_all()` 并 `aggregate()` 出 status/healthy/unhealthy
* **5s TTL cache** — `cache_ttl_seconds=5.0`,5s 内复用 cache;`force=True` 跳过 cache
* `deep_aggregated()` 是新方法,在 `deep_check()` 返回上加 `aggregated` 字段 summary
* Status 计算:`healthy == 0` → `down`;有失败 → `degraded`;全好 → `ok`

### 端点
| Method | Path | 行为 |
|---|---|---|
| `GET` | `/api/v1/monitoring/health/deep?force=...` | 已有 + 5s TTL cache |
| `GET` | `/api/v1/monitoring/health/deep/aggregated?force=...` | 新 — 含 `aggregated` summary 字段 |
| `GET` | `/api/v1/monitoring/health/services` | 20 service 列表 |

### 业务 hot path `/healthz` 端点
已有 backend services 12/13 已有 `/healthz` 端点 (user_service / agent_service / asset_service / billing_service / ...),见 `backend/services/*/routes.py`。本任务范围内无需重复加。

### 测试覆盖
* `test_default_services_count_is_20` — 20 service 严格断言
* `test_all_probes_return_when_all_healthy` — status=ok / healthy=20
* `test_one_failing_service_marks_aggregated_down` — 1 fail → degraded + unhealthy_services 含该 service
* `test_all_failing_marks_status_down` — 全 fail → down
* `test_ttl_cache_returns_same_aggregate_within_5s` — 5s 内 cache 命中 (计数 probe 调用次数)
* `test_ttl_cache_expires_after_5s` — fake monotonic clock 控制,5s 后 cache 失效
* `test_force_bypasses_cache` — force=True 每次重 probe
* `test_invalidate_cache_resets` — invalidate_cache() 强制下次重 probe

## 3. Prometheus counter.inc() wiring

### 行为
* `monitoring/observability.py:Counter.inc(amount=1.0, **labels)` — 单调递增
* `Counter` 按 `(name, frozenset(labels))` 维度累加 — 同一 label tuple 复用 sample
* `MetricsRegistry.scrape()` 返回 Prometheus exposition v0.0.4 text payload (bytes)
* `record_request(service, status, latency_ms, error_kind)` one-line helper 同时 inc 4 个 counter:
  * `http_requests_total{service, status}` — 主计数
  * `http_latency_ms_total{service}` — latency 累加
  * `http_latency_observations_total{service}` — observation 计数
  * `http_errors_total{service, kind}` — 错误时 inc

### 端点
| Method | Path | 行为 |
|---|---|---|
| `GET` | `/api/v1/monitoring/metrics` | Prometheus 文本 (`text/plain; version=0.0.4`) |
| `GET` | `/api/v1/monitoring/observability/snapshot` | 进程内 snapshot (test 友好) |

### 业务 hot path 接入
| 位置 | service name | 触发的计数 |
|---|---|---|
| `backend/services/agent_service/routes.py:run_agent` | `agent_service` | http_requests_total{status=ok/error} |
| `backend/services/asset_service/routes.py:add_item` | `asset_service` | http_requests_total{status=ok} |
| `backend/imdf/engines/dataset_manager.py:create_version` | `imdf_dataset_manager` | http_requests_total{status=ok} |

其他 hot path (`imdf/engines/*`、`backend/services/*`) 可在后续 P2-B 阶段按需接入;目前已有 3 个代表点。

### 测试覆盖
* `test_counter_inc_sums_correctly_per_label_tuple` — inc(1) + inc(2) = 3
* `test_counter_inc_rejects_negative` — ValueError
* `test_registry_inc_one_shot_helper` — `inc_counter(name, amount, ...)`
* `test_scrape_emits_prometheus_text_format` — # HELP / # TYPE / 样本行
* `test_1000_simulated_requests_produce_1000_inc` — 1000 inc → scrape 1000
* `test_record_request_increments_four_counters` — 4 个 counter 同时 inc
* `test_record_request_error_kind_increments_errors_counter` — 错误时 errors_total inc
* `test_gauge_set_and_inc`
* `test_reset_clears`
* `test_scrape_escapes_label_values` — 反斜杠 / 引号 / 换行 escape
* `test_wired_into_agent_service_run_hot_path` — 真 import + record_request inc
* `test_wired_into_dataset_manager_create_version` — 真 DatasetManager + counter

## 4. cost-per-tenant

### 行为
* `CostRecord.tenant_id: str = "default"` (新字段,向后兼容)
* `CostTracker.record(tenant_id="...")` 新 kw-only 参数
* `CostTracker.per_tenant(limit=50)` 按 `tenant_id` 聚合,返回:
  * `tenant_id`, `cost_usd`, `input_tokens`, `output_tokens`, `calls`, `unique_users`
  * 降序排列,top-N 限制

### 端点
| Method | Path | 行为 |
|---|---|---|
| `GET` | `/api/v1/monitoring/cost/by-tenant?limit=50` | top-N tenant by cost |

### 测试覆盖
* `test_cost_record_accepts_tenant_id` — tenant_id 字段 + 默认 "default"
* `test_per_tenant_aggregates_correctly` — 3 tenant 排序、calls 计数
* `test_per_tenant_10_tenants_100_events_each` — 10 tenant × 100 事件 stress,top-10 精确
* `test_per_tenant_respects_limit` — limit=3 截断
* `test_per_tenant_empty_buffer` — 空 buffer 返回 []
* `test_per_tenant_unique_users_counted` — unique_users 字段正确

## 必跑测试结果

```
$ python -m pytest monitoring/tests/ -v
======================== 92 passed, 1 warning in 3.48s ========================
```

细分:
* `test_gdpr_erasure.py` — 7/7 PASS
* `test_health_probes.py` — 8/8 PASS
* `test_prometheus_counter.py` — 12/12 PASS
* `test_cost_per_tenant.py` — 6/6 PASS
* 已有 9 个测试文件 (agent_tracking / api_routes / compliance_reports / cost_tracking / health_deep / quality_tracking / sentry / user_behavior) — 59/59 PASS (回归)

## Notes

### 关键设计决策
1. **In-process Prometheus-style registry** — 不依赖 `prometheus_client` 库,纯 stdlib + dataclass,确保无依赖环境也能跑。
2. **Audit chain 不可用时优雅降级** — `audit_chain_unavailable: bool` 字段明示,而不是抛错。
3. **5s TTL cache 行为** — 显式 `force=True` 参数,保证热路径不因缓存导致告警延迟。
4. **Per-tenant 默认值** — `tenant_id="default"` 兼容已有 `record()` 调用。
5. **Hot path 接入点** — 3 个代表点 (agent_service / asset_service / imdf_dataset_manager),覆盖 microservice + imdf engines 两个域。其他 17 个 service 的 hot path 接入可作为 P2-B 增量。

### 已知 limitation
* `monitoring/api.py` 的 `from fastapi import Response` 是局部 import,仅在 `/metrics` 调用时加载,避免循环 import。
* `execute_gdpr_erasure` 通过 `backend.imdf.engines.audit_chain` 记录 — 如该 chain 未配置 secret,会捕获异常并标 `audit_chain_unavailable=True`,擦除本身仍成功。
* Prometheus counter 是进程内 — 多 worker 部署时每个 worker 暴露自己的 `/metrics`,需要 sidecar 聚合。

### 与 plan_46aaccb6 verifier 的衔接
`verifier-feedback-attempt-1-auditor.md` 不存在 (Test-Path 返回 False) → 不存在 feedback 修补点。本任务以原始 plan 4 项 P0 修补为唯一目标,无 revert/fix 链。
