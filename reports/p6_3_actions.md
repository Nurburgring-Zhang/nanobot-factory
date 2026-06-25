# P6-3: Actions 修复优先级清单 (Attempt 3 刷新版)

**审查日期**: 2026-06-24
**优先级**: P0 (生产阻塞) → P1 (近生产化) → P2 (后续 sprint) → P3 (nice-to-have)

---

## P0 — 生产阻塞 (3 项)

### P0-1: 23 Agent endpoint 无 RBAC/multi-tenant (5-7 人天)

**问题**: `backend/services/agent_service/routes.py:108-160` + `routes_mcp.py` + `routes_memory.py` 全部 endpoint 无 `Depends(auth)`

**影响**: 数据泄露、横向越权、审计追溯缺失

**修复**:
1. `backend/common/middleware/auth.py` 增加 RBAC dependency
2. AgentService route 加 `Depends(require_permission("agent:run:{agent_type}"))`
3. MCP route 加 `Depends(require_permission("agent:mcp"))`
4. Memory route 加 tenant_id 字段强制检查
5. 实现 `/api/v1/agent/tools/audit` (从 tools/registry.py 取审计链)

**Owner**: security team + 架构

---

### P0-2: executor._run_full_auto 是 STUB (10-15 人天)

**问题**: `backend/services/agent_service/executor.py:258-274` `_run_full_auto` 仅返回计划,不调用下游 service。`executor.py:14` 注释明确说 "stub: heavy lifting lives in downstream service"

**影响**: 调用 `/api/v1/agents/{at}/run` 实际**不执行任何业务逻辑**,只返回计划

**修复**:
1. `_run_full_auto` 增加 httpx.AsyncClient 调用下游 service
2. 按 `cfg["downstream_service"]` 路由 (cleaning=8002, scoring=8003 等 12 service)
3. 下游 service 健康检查 (启动时探活)
4. timeout / retry / circuit breaker 整合进下游调用
5. 真实执行结果写 long-term memory + lineage 表

**Owner**: 平台架构 + 12 service owner

---

### P0-3: 测试覆盖 0/5 (15-20 人天)

**问题**: 5 大子系统 (agent_service / executor / mcp / memory_palace / multi_agent) 0 单元测试

**证据**: `backend/tests/` 35 文件无 `test_agent_service*.py` / `test_mcp*.py` / `test_memory_palace*.py`

**修复**:
1. `test_agent_service.py` — agents + executor + 30 endpoint 200/404
2. `test_mcp.py` — JSON-RPC + 5 tools + stdio/SSE
3. `test_memory_palace.py` — 5 表 CRUD + 6 层语义
4. `test_hindsight.py` — 4 层搜索 + L0/L3 retain
5. `test_multi_agent.py` — 5 mode + dispatcher + aggregator
6. `test_skill_orchestrator.py` — 4 策略 + chain

**目标**: 覆盖率 ≥ 70%,CI 必跑

**Owner**: QA + 模块 owner

---

## P1 — 近生产化必修 (9 项)

| # | 问题 | 位置 | 工作量 |
|---|------|------|--------|
| P1-1 | workflow_orchestrator.py:668 import bug | `integrations/multi_agent/workflow_orchestrator.py:668` | 0.5 人天 |
| P1-2 | Circuit breaker 缺失 | `executor.py:196-208` | 1-2 人天 |
| P1-3 | Distributed store (Redis) | `store.py` + `scheduler.py` | 3-5 人天 |
| P1-4 | 7 generation 与 15 base 调度未统一 | `agents.py:262-339` | 5-7 人天 |
| P1-5 | expert_workflow.py _execute_* STUB | `workflow_orchestrator.py:220-265` | 5-7 人天 |
| P1-6 | /api/v1/agent/tools/audit endpoint 缺失 | `routes.py:30` | 1-2 人天 |
| P1-7 | OTel/Prometheus dashboard 缺失 | `common/metrics (P4-1)` | 2-3 人天 |
| P1-8 | Cost/Budget guard 缺失 | `multi_turn.py` | 1-2 人天 |
| P1-9 | MCP auth (OAuth/Bearer) 缺失 | `routes_mcp.py` | 2-3 人天 |

**P1 合计**: 21-31 人天

---

## P2 — 后续 sprint (5 项)

| # | 项目 | 工作量 |
|---|------|--------|
| P2-1 | Vector embedding 召回 (PG/pgvector) | 5-7 人天 |
| P2-2 | Prompt 版本控制 (git-like) | 3-5 人天 |
| P2-3 | Few-shot / CoT 模板库 | 5-7 人天 |
| P2-4 | SOUL.md 多进程文件锁 | 1 人天 |
| P2-5 | MemoryPalace SQLite → Postgres 迁移 | 3-5 人天 |

---

## P3 — nice-to-have (3 项)

| # | 项目 | 工作量 |
|---|------|--------|
| P3-1 | BaseAgent 抽象类 (OOP 替代 dict) | 3-5 人天 |
| P3-2 | Agent-to-agent mTLS 加密 | 5-7 人天 |
| P3-3 | README + 架构图 + curl 示例 | 1-2 人天 |

---

## 总工作量估算

| 优先级 | 项数 | 人天 |
|--------|------|------|
| P0 | 3 | 30-42 |
| P1 | 9 | 21-31 |
| P2 | 5 | 17-25 |
| P3 | 3 | 9-14 |
| **合计** | **20** | **77-112 人天** |

8-12 人 × 1-2 sprint (4-8 周)

---

## 修复优先级矩阵

| 严重度 | P0 | P1 | P2 | P3 | 总 |
|--------|----|----|----|----|----|
| 安全 | 1 | 2 | 0 | 1 | 4 |
| 正确性 | 1 | 4 | 1 | 0 | 6 |
| 性能 | 0 | 2 | 1 | 0 | 3 |
| 可维护性 | 1 | 1 | 2 | 2 | 6 |
| **小计** | **3** | **9** | **5** | **3** | **20** |

---

## 推荐 Sprint 顺序

**Sprint 1 (P0)**: 测试 (15-20) + RBAC (5-7) + executor (10-15) — 平行推进
**Sprint 2 (P1)**: import bug (0.5) + audit endpoint (1-2) + circuit breaker (1-2) + budget (1-2) + MCP auth (2-3) + generation 整合 (5-7) + expert 真实化 (5-7)
**Sprint 3 (P1 后期)**: distributed store (3-5) + OTel dashboard (2-3)
**Sprint 4+**: vector embedding + prompt version + few-shot

---

## 责任矩阵 RACI

| 项目 | R (执行) | A (问责) | C (咨询) | I (知情) |
|------|---------|---------|---------|---------|
| P0-1 RBAC | security team | architect | service owner | PM |
| P0-2 executor | agent team | 平台架构 | 下游 owner | PM |
| P0-3 测试 | QA | 模块 owner | 架构师 | PM |
| P1-* | 模块 owner | 平台架构 | architect | PM |

---

## 验收标准 DoD

- [ ] P0 全部完成 + CI 通过 + 测试覆盖 ≥ 70%
- [ ] P1 全部完成 + 文档更新 + 1 sprint 灰度
- [ ] 23 agent endpoint 全部回归测试 PASS
- [ ] security pen test 通过 (OWASP)
- [ ] load test 1000 并发 P95 < 500ms
- [ ] Grafana dashboard + 21 alert 部署 + oncall 演练

---

## 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| P0-2 涉及 12 下游 service 整合 | 高 | 分阶段:先 5 核心,再扩 |
| P0-3 测试覆盖率 ≥ 70% 难达成 | 中 | 优先级 executor + memory + mcp |
| P1-3 Redis 改造影响单进程性能 | 中 | 保留 in-mem fallback + 双写 |
| P1-5 expert 真实化依赖 LLM provider | 高 | 与 P2-3 (LLM provider) 联合 |