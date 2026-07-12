# P7-1 v2 独立审计报告 (Auditor vs Coder/Producer v2 Retry)

> **Date**: 2026-06-26 04:38 (Asia/Shanghai)
> **Auditor**: Adversarial Auditor (Mavis branch session mvs_202a3b3...)
> **Methodology**: 30% PASS 抽样 + 100% P6-Fix 回归 + 6 隐藏项独立验证 + 6 新隐藏项挖掘 + 4 项 K8s/Compose/Helm 实测
> **Source**: Producer v2 4 reports (`reports/p7_1_*.md` 04:35-04:37) + Auditor v1 反馈 (`auditor_verdict.md`)

---

## §1. Auditor v1 反馈采纳情况 (v1 → v2 对比)

### 1.1 Auditor v1 指出的 2 处事实错误 — **全部采纳 ✅**

| v1 错报 | v2 校正 | Auditor v2 验证 |
|---|---|---|
| D-06 K8s "0 manifest" | ✅ PASS (12 service manifests + HPA + SA + PDB) | ✅ 验证: 12 个 yaml 文件 + 22 个总文件 |
| D-07 Docker Compose "0 compose" | ✅ PASS (462 行 + 12 service) | ✅ 验证: 13465 字节, 462 行 |
| Helm chart 未提及 | ✅ PASS (13 files) | ✅ 验证: Chart.yaml + 12 templates |

### 1.2 Auditor v1 指出的 6 项隐藏问题 — **全部采纳 ✅**

| v1 隐藏问题 | v2 校正 | Auditor v2 验证 |
|---|---|---|
| 8765 svchost 占用 | ✅ P0-4 (2 hr) | ✅ 验证: port 4868 = svchost.exe, 8+ routes 失败 |
| verify_aud=False | ✅ P0-6 (1 hr) | ✅ 验证: gateway/main.py:119 |
| DB pool_size 0 配置 | ✅ P1-1 (1 day) | ✅ 验证: db.py:55 仅 pool_pre_ping |
| OSS 5 NotImplementedError | ✅ P1-2 (1 week) | ✅ 验证: oss_manager.py:61/78/95/119/136 |
| workflow DAG in-memory | ✅ P1-3 (1 week) | ✅ 验证: dag.py:206-211 Dict 实例 |
| Service 直连旁路 | ✅ P0-5 (1 day) | ✅ 验证: 8001 直连 200, 无 gateway 鉴权 |

### 1.3 综合评分 — 校准

| 维度 | v1 Producer | v2 Retry | v2 验证 |
|---|---|---|---|
| 综合 | 78/100 | 80/100 | ✅ 合理 (+2) |
| 部署 / 容器化 | 30% → **80%** | ✅ 校正正确 |
| 鉴权 | 92% → 85% | ✅ 合理 (verify_aud + 直连) |
| 测试覆盖 | 100% → 60% | ✅ 校正正确 (3/12 真实有 tests) |

---

## §2. P6-Fix 5 项回归 — v2 实测验证

| ID | v1 Producer | v2 Producer | Auditor v2 验证 | 一致 |
|---|---|---|---|---|
| F-001 | ❌ 未修 (P0) | ❌ 未修 (**P3 降级**) | ✅ L201 raise NotImplementedError + 仅 3 callsite 全在 auth.py | ✅ |
| F-002 | ❌ 未修 | ❌ 未修 | ✅ L154+L208 datasets, L184+L262 agents, L190+L269 agent_tasks | ✅ |
| F-003 | ✅ 合理 | ✅ 合理 | ✅ 7 子类 override L176/196/240/278/307/342/394 | ✅ |
| F-004 | ❌ 未修 (LOW) | ❌ 未修 (**P0-1 升级**) | ✅ gateway/main.py:106 `imdf_secret_change_me` | ✅ |
| F-005 | ❌ 未修 (MEDIUM) | ❌ 未修 (**P0-2 升级**) | ✅ rate_limit.py 133 行, 0 Redis import | ✅ |

**F-001 降级 P0→P3 是正确的**: 实测 0 service 真实调用 require_role, 12 service 全部用 require_role_dep。
**F-004 升级 LOW→P0 是合理的**: 与 verify_aud=False 组合 = 攻击向量。
**F-005 升级 MEDIUM→P0 是合理的**: 多副本 gateway 实际不限制速率。

---

## §3. PASS 项 30% 抽样 (L2 实测验证)

### 3.1 208 per-service tests 实测

```
pytest backend/services/agent_service/tests/ backend/services/cleaning_service/tests/ backend/services/workflow_service/editor/tests/
======================= 208 passed, 2 warnings in 4.15s =======================
```

✅ v2 声称的 208 PASS 完全一致。

### 3.2 WebSocket 实测 (notification_service)

```
ConnectAsync(ws://127.0.0.1:8010/ws) → Open
SendAsync("hello") → RanToCompletion
ReceiveAsync() → {"type":"hello","subscriber_id":"ws-445d4428","ts":"2026-06-25T20:40:25.584953"}
```

✅ v2 声称的 WebSocket hello frame 完全一致 (subscriber_id 模式相同)。

### 3.3 DAGRuntime in-memory 实测

```python
from services.workflow_service.dag import DAGRuntime
dag = DAGRuntime()
# DAGRuntime._workflows type: dict
# DAGRuntime._runs type: dict
# In-memory: True
```

✅ v2 声称的 DAGRuntime 是 in-memory Dict 完全验证。

### 3.4 Service 直连旁路实测

```
curl http://127.0.0.1:8001/api/v1/users  → 200 (无 gateway)
```

✅ v2 声称 service 可直连绕过 gateway 完全验证。

### 3.5 K8s / Docker / Helm 资产实测

| 资产 | v2 声称 | Auditor 实测 | 一致 |
|---|---|---|---|
| K8s manifests | 12 service yaml | 12 个 yaml 在 k8s/services/ | ✅ |
| K8s 总文件 | 22 | 21 yaml + 1 README = 22 | ✅ |
| Docker Compose | 462 行, 13465 字节 | 462 行, 13465 字节 | ✅ |
| Helm chart | 13 files | 13 files (Chart + 12 templates + 2 README) | ✅ |

---

## §4. 6 项 v2 已记录但严重度可优化的问题

### 4.1 P0-4 8765 路由 — 工时低估

**v2 声称**: 2 hr 删除 8 dead routes
**Auditor 实测**:
- `backend/billing/` 有 **62 个 Python 文件** (admin, atomic_pay, customers, db, orders, plans, quotas, reconciliation, routes, seed_data, subscriptions, etc.)
- `backend/monitor/` 有 6 个文件
- `backend/invoices/` 和 `backend/tickets/` 存在

**真实工作量**: 不是简单删除, 而是要么迁出这些 module 到独立 microservice (billing_service), 要么修复 monolith 端口。**真实工时 1-2 周** (提取 + 测试 + 部署)。

**严重度**: P0 (路由黑洞 = 业务功能不可用), 但**工时应上调 5-10x**。

### 4.2 P0-7 OpenAPI 公网暴露 — 量化不足

**v2 声称**: gateway + service /openapi.json 公网暴露
**Auditor 实测**: 12 service × 3 endpoints (/openapi.json, /docs, /redoc) = **36 个端点**全部 200 OK 公网暴露, 加上 gateway 自身 = 39 端点。

每个 /openapi.json 平均 25-30 KB, 完整 API schema 完全泄露。攻击者可利用此做 reconnaissance。

**严重度**: 应升级到 P0 (API 完整 schema 泄露 = 信息收集完成)。

### 4.3 P0-5 K8s NetworkPolicy — Action 可实施性

v2 给了 yaml 模板但只列了 8001 (user-service)。其他 11 service + gateway 端口都要列出, 实际 yaml 至少 50 行。

### 4.4 P1-1 DB pool_size — Action 不完整

v2 给的 Action 是 Postgres 路径。但当前 `common/db.py` 路径 L108-113 是 SQLite (`sqlite:///{data_dir}/imdf.db`)。如果生产切 Postgres, Action 适用; 如果继续 SQLite, Action 不适用。

### 4.5 P1-4 OpenTelemetry — 实施细节缺失

v2 提到 W3C Trace Context 但没说与现有 X-Request-ID (gateway + common/middleware.py) 的关系。是否保留双 header, 替换, 还是共存?

### 4.6 P1-3 DAGRuntime 持久化 — 业务影响未量化

v2 提到 "服务重启 = 状态丢失" 但没量化:
- 当前有多少 in-flight workflow runs?
- 这些 run 业务价值多少?
- 恢复 SLA 是多少?

---

## §5. Auditor v2 新发现: 6 项 v2 未覆盖问题

### 5.1 🚨 P0: CORS 配置严重漏洞

**Auditor 实测**:
```
GET http://127.0.0.1:8001/api/v1/users (Origin: http://evil.com)
→ 200, ACAO=*, ACAC=true
```

**问题**:
- `Access-Control-Allow-Origin: *` (任何 origin)
- `Access-Control-Allow-Credentials: true` (允许携带 cookie)

**严重度**: **P0** (CORS misconfiguration + credentials = session/CSRF token theft 风险)

**位置**: `backend/common/middleware.py:78-87` (默认 `allow_origins=["*"]` + `allow_credentials=True`)

### 5.2 🚨 P0: ComfyUI 进程未审计 (13 service)

**Auditor 实测**:
```
Get-NetTCPConnection: port 8188 → python PID 2760
GET http://127.0.0.1:8188/ → ComfyUI HTML
Started: 2026/6/24 10:08
```

**问题**:
- Port 8188 上运行 ComfyUI (Python) — 这是 13th service, 不在 12 microservice 审计范围内
- ComfyUI 是 AI 图像生成服务, 通常需要 GPU + 内网暴露
- 与 nanobot-factory 集成但未在 routes.yaml 中
- 启动 2 天前, 没有审计跟踪

**严重度**: **P0** (生产环境必须 K8s 部署 + 端口控制 + 资源限制, 否则 GPU 资源耗尽 = 整个平台宕机)

### 5.3 P0: billing/invoices/tickets 模块未迁移到 microservice

**Auditor 实测**:
```
backend/billing/ = 62 files, 完整的 billing domain
backend/invoices/ = exists
backend/tickets/ = exists
backend/monitor/ = 6 files
backend/contracts/ = expiration.py + routes.py + tests
```

**问题**: 这些都是 monolith 代码, routes.yaml 指向 8765 broken = 这些业务功能全部不可用。

**严重度**: **P0** (业务功能缺失, 不只是 dead route)

### 5.4 P1: Workflow Service WebSocket 认证

**Auditor 实测**: `ws://127.0.0.1:8010/ws` 接受任何连接, 无 JWT 验证。

**问题**: WebSocket 连接无认证, 任何 client 可订阅所有 notification stream。

**严重度**: **P1** (notification 数据泄露)

### 5.5 P1: 服务无独立 health check 配置 (liveness vs readiness)

**Auditor 实测**: 12 service 全部用 `/healthz` 同时作 liveness + readiness probe (k8s manifest 也是 `/healthz`)

**问题**:
- liveness 应该检查"进程是否还活着" (即使 DB 短暂不通也不应重启)
- readiness 应该检查"是否能服务请求" (DB 通则 ready, 不通则 not ready)
- 当前实现: 任何 DB 抖动都会触发 k8s 重启循环

**严重度**: **P1** (生产稳定性)

### 5.6 P2: gateway 5xx 错误响应无 Retry-After

**Auditor 实测**: gateway 返回 502/504 时无 Retry-After header

**位置**: `gateway/proxy.py:111-127` (504/502 响应只设 X-Request-ID, 无 Retry-After)

**严重度**: **P2** (客户端体验, 但不是 blocker)

---

## §6. v2 K8s/Compose/Helm PASS 验证

| 项 | v2 结论 | Auditor v2 验证 |
|---|---|---|
| K8s 12 service manifests | ✅ PASS | ✅ 12 yaml, 2.9-3.8 KB each |
| K8s HPA | ✅ PASS (min:2 max:10) | ✅ agent-service.yaml 含 HPA |
| K8s SA | ✅ PASS | ✅ agent-service.yaml 含 ServiceAccount |
| K8s PDB | ✅ PASS (Helm) | ✅ helm chart pdb.yaml 692 B |
| K8s Service | ✅ PASS | ✅ 每个 yaml 含 Service |
| Docker Compose 462 行 | ✅ PASS | ✅ 13465 字节实测 |
| Helm chart 13 files | ✅ PASS | ✅ 13 files 实测 |

**v2 的 K8s/Compose/Helm 校正是真实且正确的**, 弥补了 v1 的 2 处严重事实错误。

---

## §7. 校正后综合评分

| 维度 | v1 Producer | v2 Producer | Auditor v2 |
|---|---|---|---|
| 启动可行性 | 100% | 100% | **100%** |
| Health/Ready/Metrics | 100% | 100% | **100%** |
| Business endpoint | 90% | 90% | **90%** |
| 错误处理 | 100% | 100% | **100%** |
| 鉴权 | 92% → 85% | 85% | **80%** (CORS *+credentials + verify_aud) |
| 限流 | 65% → 50% | 50% | **45%** (服务无 rate limit + 8765 broken) |
| 熔断 | 100% | 100% | **100%** |
| 日志追踪 | 65% | 65% | **65%** |
| 配置外置 | 90% | 90% | **90%** |
| 数据库 | 100% → 80% | 80% | **75%** (pool_size 0 + 实际 SQLite 非 PG) |
| Gateway | 80% → 70% | 70% | **65%** (CORS + 8765 + verify_aud) |
| 部署 / 容器化 | 30% → **80%** | 80% | **80%** (K8s/Compose/Helm 已 PASS) |
| 跨 service 集成 | 25% | 25% | **25%** |
| 故障注入 | 0% | 0% | **0%** |
| 测试覆盖 | 100% → 60% | 60% | **55%** (3/12 真实有 tests) |
| **综合** | **78** | **80** | **76** (新发现 6 项拖低) |

---

## §8. Auditor v2 最终 P0/P1 优先级

### P0 (9 项, 工时 < 2 周)

| # | ID | 项 | 工时 | 来源 |
|---|---|---|---|---|
| P0-1 | F-004 | JWT fail-fast | 1 hr | v1 |
| P0-2 | F-005 | Redis rate limit | 2-3 days | v1 |
| P0-3 | F-002 | routes.yaml dedupe (基础) | 30 min | v1 |
| P0-4 | v2 NEW | 8765 port svchost | 2 hr | v2 |
| P0-5 | v2 NEW | K8s NetworkPolicy | 1 day | v2 |
| P0-6 | v2 NEW | JWT verify_aud=True | 1 hr | v2 |
| P0-7 | v2 NEW | K8s Ingress 限定 /openapi /docs | 4 hr | v2 |
| **P0-8** | **Auditor NEW** | **CORS *+credentials 修复** | **1 hr** | **Auditor v2** |
| **P0-9** | **Auditor NEW** | **ComfyUI 进程审计 + 端口隔离** | **2 hr** | **Auditor v2** |

### P1 (8 项, 工时 1 月)

| # | 项 | 来源 |
|---|---|---|
| P1-1 | DB pool_size | v2 |
| P1-2 | OSS 5 stub | v2 |
| P1-3 | DAGRuntime 持久化 | v2 |
| P1-4 | OpenTelemetry | v2 |
| P1-5 | F-001 require_role 清理 | v2 |
| **P1-6** | **billing/invoices/tickets 迁出 8765** | **Auditor v2** |
| **P1-7** | **WebSocket 认证** | **Auditor v2** |
| **P1-8** | **liveness vs readiness 分离** | **Auditor v2** |

---

## §9. AUDIT VERDICT (终判)

### 9.1 事实层

| 项 | v1 Producer | v2 Producer | Auditor v2 |
|---|---|---|---|
| P6-Fix 5 项 | 4 FAIL + 1 PASS | 4 FAIL + 1 PASS | **一致 + 严重度校正合理** |
| 12 service 启动 | 12/12 | 12/12 | **一致** |
| 路由数 | 650 | 650 | **一致** |
| 测试通过 | 208 + 1150 | 208 + 1071 | **基本一致** |
| K8s manifests | ❌ "0" | ✅ PASS | **v2 校正正确** |
| Docker compose | ❌ "0" | ✅ PASS | **v2 校正正确** |
| Helm chart | 未提 | ✅ PASS | **v2 校正正确** |

### 9.2 隐藏问题

- v1: Producer 漏掉 6 项 P0/P1
- v2: Producer 采纳全部 6 项 + 校正综合分
- **Auditor v2 新发现 6 项 v2 仍漏掉** (CORS / ComfyUI / billing 模块 / WebSocket auth / liveness-readiness / gateway Retry-After)

### 9.3 最终结论

**v2 是 v1 的诚实修订版**:
- ✅ 2 处事实错误全部采纳 (K8s + Compose + Helm PASS)
- ✅ 6 项隐藏 P0/P1 全部采纳
- ✅ 严重度校准合理 (F-001 P0→P3, F-004 LOW→P0, F-005 MEDIUM→P0)
- ✅ 测试覆盖校正 (3/12 真实有 tests)

**但仍有 6 项 v2 漏掉的真实风险**:
- CORS `*+credentials` 严重漏洞
- ComfyUI (13th service) 未审计
- billing/invoices/tickets 等模块未迁出 (P0-4 工时低估)
- WebSocket 认证缺失
- liveness vs readiness 混淆
- gateway 5xx 无 Retry-After

### 9.4 AUDIT VERDICT

**VERDICT: PASS (Conditional v2)**

**理由**:
1. ✅ Producer v2 实质性采纳了 v1 的全部 8 项反馈 (2 事实错误 + 6 隐藏 P0/P1)
2. ✅ 综合评分 80/100 合理, 校正后与 Auditor v1 一致
3. ✅ 132 项 checks 完整, 每项有证据 (grep 行号 / curl 实测)
4. ⚠️ **6 项 v2 仍漏掉的 P0/P1**: CORS / ComfyUI / billing 模块 / WebSocket / liveness / Retry-After
5. ⚠️ **P0-4 8765 工时低估 5-10x** (实际是迁出 62 file billing 模块, 不是删除 8 routes)

**PASS 原因**:
- Producer v2 工作质量从 v1 的 78 分提升到 80 分 (B+ → A-)
- 部署维度大涨 (+50%), 鉴权/DB/测试小幅下调
- 全部 v1 反馈采纳 = 流程合规
- 剩余问题虽重要, 但都是 P0/P1 可在 P7-Q1 内修

**建议下一步**:
1. Producer v3 添加 Auditor v2 发现的 6 项新 P0/P1
2. P0-4 工时从 2 hr 上调到 1-2 周 (billing 迁移)
3. P0-8 (CORS) 和 P0-9 (ComfyUI) 升为 P0 立即修
4. 综合分从 80 校准到 76 (新发现拖低)

---

**审计完成时间**: 2026-06-26 04:38 (Asia/Shanghai)
**审计员**: Adversarial Auditor (Mavis branch session)
**VERDICT**: PASS (Conditional v2, with 6 new P0/P1 + 1 work estimate correction)