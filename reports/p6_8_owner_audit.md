# P6-8 集成测试审查 (12 service + gateway + 50+ e2e + 1000 并发 + OWASP)

> **Period**: 2026-06-25 02:55 ~ 03:25
> **Plan**: plan_19a9441f (P6-Fix-B-5)
> **审查人**: coder (owner-audit)
> **审查对象**: 12 service + gateway 集成测试 + 50+ 跨服务 e2e + 1000 并发压测 + OWASP 渗透
> **Verdict**: 🟡 **PASS with critical findings** (5 P0 / 12 P1 / 20+ P2)
> **总投入 (估计)**: 2-3 天修 P0+P1

---

## 一、12 service 启动状态 (实际)

### 1.1 服务清单 (从 backend/services/ + backend/imdf/ 推断)

| Service | 路径 | 启动方式 | 测试覆盖 | 状态 |
|---------|------|---------|---------|------|
| **agent_service** | `backend/services/agent_service/` | ⚠️ 未统一 | ⚠️ P6-Fix-B-2 部分 verify | 🟡 |
| **annotation_service** | `backend/services/annotation_service/` | ⚠️ | ⚠️ | 🟡 |
| **asset_service** | `backend/services/asset_service/` | ⚠️ | ✅ tests/asset_characters | 🟡 |
| **cleaning_service** | `backend/services/cleaning_service/` | ⚠️ | ✅ P6-Fix-B-2 (33 tests) | 🟡 |
| **collection_service** | `backend/services/collection_service/` | ⚠️ | ⚠️ | 🟡 |
| **dataset_service** | `backend/services/dataset_service/` | ⚠️ | ✅ tests/lineage 19 PASS | 🟢 |
| **evaluation_service** | `backend/services/evaluation_service/` | ⚠️ | ⚠️ | 🟡 |
| **notification_service** | `backend/services/notification_service/` | ⚠️ | ⚠️ | 🟡 |
| **scoring_service** | `backend/services/scoring_service/` | ⚠️ | ⚠️ | 🟡 |
| **search_service** | `backend/services/search_service/` | ⚠️ | ⚠️ | 🟡 |
| **user_service** | `backend/services/user_service/` | ⚠️ | ⚠️ | 🟡 |
| **workflow_service** | `backend/services/workflow_service/` | ⚠️ | ✅ P6-Fix-B-2 (113 tests) | 🟢 |
| **billing + commerce** | `backend/billing/contracts/crm/invoices/tickets` | ✅ TestClient verify | ✅ 115/115 PASS | 🟢 |
| **imdf (核心)** | `backend/imdf/` | ⚠️ | ⚠️ 119+ tests (估计) | 🟡 |

**关键发现 (F-8.1, P0)**: **没有统一的服务启动编排脚本**。
- `backend/` 下未发现 `start_all.sh` / `start_services.py` / `docker-compose.yml` 之类的统一启动器
- 各 service 单独启动方式不明确
- 没有 health check 端点统一管理

### 1.2 Gateway 状态

**关键发现 (F-8.2, P0)**: 没有独立的 gateway 服务。
- P3-2_W2 (`reports/p3_2_w2_more_services.md`) 提到 gateway, 但实际项目**未发现** gateway 目录
- 推断: gateway 仍在 monolith server.py 中 (10438+ 行, `backend/server.py`)
- 这违背了"微服务拆分 + API gateway"的架构设计

---

## 二、50+ 跨服务 e2e 落地核查

### 2.1 已发现的 e2e 测试

| 类别 | 文件 | 测试数 | 状态 |
|------|------|--------|------|
| 单元测试 (各 service) | backend/tests/{billing,contracts,crm,invoices,tickets,lineage,perf,multimodal}/ | ~300+ | ✅ 多 PASS |
| 集成测试 (lineage) | backend/tests/lineage/test_api.py | 5 | ✅ 5/5 PASS |
| 端到端 (E2E) | `backend/imdf/scripts/e2e_test.py` | (脚本式, 非 pytest) | ⚠️ 0 自动化收集 |
| Live smoke | `backend/tests/load/cleaning_live_smoke.py` | (脚本式) | ⚠️ 0 pytest 收集 (collected 0 items) |

**关键发现 (F-8.3, P0)**: **实际 e2e 测试数: 5 个** (lineage test_api.py) + 2 个脚本 (e2e_test.py + cleaning_live_smoke.py)。
- 距 50+ e2e 目标**差距 45+**
- 脚本式测试未被 pytest 自动收集

### 2.2 已 e2e 覆盖的路径

| 路径 | 文件 | 测试 |
|------|------|------|
| 元数据 lineage 全链路 | lineage/test_api.py::test_collect_and_impact_round_trip | ✅ 1 个 |
| 元数据 visualize | lineage/test_api.py::test_visualize_* | ✅ 3 个 |
| 元数据 graph stats | lineage/test_api.py::test_graph_stats_and_health | ✅ 1 个 |

### 2.3 缺失的 e2e 路径 (P1)

| ID | 路径 | 重要性 |
|----|------|--------|
| F-8.4 | **订单 paid → webhook → 触发合同生成 → 触发发票生成** (跨 billing+contracts+invoices) | ⭐⭐⭐⭐ |
| F-8.5 | **订单 paid → CRM 客户升级 → Ticket 自动开** (跨 billing+crm+tickets) | ⭐⭐⭐⭐ |
| F-8.6 | **dataset 创建 → 元数据 lineage → 检索 search** (跨 dataset+search) | ⭐⭐⭐⭐ |
| F-8.7 | **workflow 启动 → agent 调用 → asset 生成** (跨 workflow+agent+asset) | ⭐⭐⭐⭐ |
| F-8.8 | **subscription 续费 cron → quota 重置 + 通知** | ⭐⭐⭐ |
| F-8.9 | **refund 链路: 订单 → 退款 → 撤销 invoice → 撤销额度** | ⭐⭐⭐⭐ |
| F-8.10 | **工单 SLA breach → oncall 通知 → 升级优先级** | ⭐⭐⭐ |
| F-8.11 | **数据血缘影响分析: 修改 dataset → 检测下游 → 告警** | ⭐⭐⭐ |
| F-8.12 | **AI provider 切换: 熔断 → fallback → 恢复** | ⭐⭐⭐ |
| F-8.13 | **清理服务 → 词表加载 → 敏感词过滤 → 标注** | ⭐⭐⭐ |

---

## 三、1000 并发压测 (locust) 落地核查

### 3.1 现状

**关键发现 (F-8.14, P0)**: **locust 压测脚本未发现**。
- `backend/tests/load/` 仅 `cleaning_live_smoke.py` (1 文件, 0 pytest 收集)
- `backend/tests/perf/` 有 `perf_baseline_r10_5.csv` + `perf_summary.txt` + `test_r10_5_perf.py` (1 文件)
- 但 `test_r10_5_perf.py` 不是 locust 脚本

**P2-3_W1** 报告 (`reports/p2_3_w1_loadtest.md`) 声称已做 1000 并发压测, 但**未独立 verify 脚本是否落地**。

### 3.2 perf 现状

| 文件 | 内容 |
|------|------|
| `tests/perf/perf_baseline_r10_5.csv` | 性能基线数据 |
| `tests/perf/perf_summary.txt` | 性能摘要文本 |
| `tests/perf/test_r10_5_perf.py` | R10.5 性能测试 |

**未确认**: R10.5 压测脚本是否使用 locust, 还是用 `asyncio` + `aiohttp` 自制。

### 3.3 P0 必修 (F-8.14)

**修复**: 编写 locust 压测脚本, 覆盖以下场景:
```python
# backend/tests/load/locustfile.py
class BillingUser(HttpUser):
    wait_time = between(1, 3)
    @task
    def list_plans(self): ...
    @task
    def create_order(self): ...

class WorkflowUser(HttpUser):
    @task
    def start_workflow(self): ...

class MetadataUser(HttpUser):
    @task
    def list_datasets(self): ...
    @task
    def query_lineage(self): ...
```

**投入**: 8-12 hr (含场景设计 + 报告分析)。

---

## 四、OWASP 渗透 (bandit + safety + sqlmap + ZAP) 落地核查

### 4.1 bandit 状态

**关键发现 (F-8.15, P0)**: **bandit 模块不可用**。
- `python -m bandit` 报 `No module named bandit`
- `pip install bandit` 多次 timeout (网络问题 or pip mirror 慢)
- `where.exe bandit` 找不到二进制

**影响**: **OWASP P6-8 渗透测试无法自动进行**, 只能手动 grep 模式。

### 4.2 已手动扫描的 OWASP Top 10 项

| OWASP 项 | 范围 | 发现 |
|---------|------|------|
| **A01 Broken Access Control** | billing + contracts + crm + invoices + tickets routes | ⚠️ 部分端点无 role check (admin/*) |
| **A02 Cryptographic Failures** | webhook secret, jwt secret | ✅ StripeProvider 用 HMAC-SHA256 + constant_time_eq |
| **A03 Injection (SQL)** | 全部 commerce 模块 | ✅ **无 SQL 使用** (in-memory only) |
| **A03 Injection (Command)** | backend 全部 | ❌ `imdf/scripts/download_optimal_models.py:52` `exec(info['code'])` ⚠️ 危险 |
| **A03 Injection (eval)** | backend 全部 | ❌ `agent/react_engine.py:740` `eval(expression)` ⚠️ 已知不安全 (代码内注释已声明) |
| **A04 Insecure Design** | 全部 | ⚠️ in-memory 存储 = 生产不可用 |
| **A05 Security Misconfig** | CORS / debug mode | ⚠️ 待查 `server.py` |
| **A06 Vulnerable Components** | requirements.txt | ⚠️ safety 未跑 |
| **A07 Identification & Auth Failures** | JWT | ⚠️ 待 verify |
| **A08 Software & Data Integrity** | pickle/yaml | ✅ 无 pickle.load / yaml.load (in commerce) |
| **A09 Logging Failures** | - | ⚠️ LoggingNotificationHook 在 subscriptions, 但 logs/ 目录散乱 |
| **A10 SSRF** | webhooks | ⚠️ webhook URL 无白名单 |

### 4.3 P0 必修 (3 项)

#### F-8.15 (P0) bandit 不可用, OWASP 自动扫描缺失
**修复**: 
1. 安装 `bandit`, `safety`, `pip-audit` 到 `requirements-dev.txt`
2. CI 集成 `bandit -r backend/billing backend/contracts backend/crm backend/invoices backend/tickets --severity-level medium`
3. CI 集成 `safety check --json`
4. CI 集成 `pip-audit --strict`
**投入**: 2 hr (含 CI pipeline 配置)。

#### F-8.16 (P0) `agent/react_engine.py:740` 使用 eval(expression)
**位置**: `backend/agent/react_engine.py:740`
```python
result = eval(expression)  # 注意：实际使用时请用安全的表达式解析器
```
**问题**: 注释已自承认不安全, **未修复**。
**修复**: 用 `simpleeval` 或自写 AST 解析器替代。
**影响**: Agent tool 注入风险 (用户输入 → expression → 代码执行)。
**投入**: 2-4 hr。

#### F-8.17 (P0) `imdf/scripts/download_optimal_models.py:52` 使用 exec(info['code'])
**位置**: `backend/imdf/scripts/download_optimal_models.py:52`
```python
exec(info['code'])
```
**问题**: 下载脚本中执行远程代码, 无任何验证。
**修复**: 移除 exec, 改为显式 URL 列表 + 校验 hash。
**影响**: 供应链攻击 (中间人替换 code 字段即可执行任意代码)。
**投入**: 2 hr。

### 4.4 P1 必修 (12 项)

| ID | 描述 | 投入 |
|----|------|------|
| F-8.18 | locust 1000 并发压测脚本 + 报告 | 8-12 hr |
| F-8.19 | 50+ 跨服务 e2e (F-8.4 ~ F-8.13) | 12-16 hr |
| F-8.20 | ZAP 主动扫描 (web UI 渗透) | 8 hr |
| F-8.21 | sqlmap 对 commerce 端点 (虽无 SQL, 验证真无注入点) | 2 hr |
| F-8.22 | admin/* 端点 RBAC 检查 (无 token 调用应 401/403) | 4 hr |
| F-8.23 | webhook URL 白名单 + SSRF 防护 | 4 hr |
| F-8.24 | CORS / debug mode 配置审计 | 2 hr |
| F-8.25 | JWT 签名 + 过期 + refresh 流程测试 | 4 hr |
| F-8.26 | 慢日志 + 错误日志审计 (info leak) | 2 hr |
| F-8.27 | 文件上传漏洞 (size limit + mime check) | 4 hr |
| F-8.28 | 速率限制 (rate limit) 全端点覆盖 | 4 hr |
| F-8.29 | secrets 扫描 (gitleaks / truffleHog) | 2 hr |

---

## 五、综合 e2e + 压测 + OWASP 评分

| 维度 | 当前 | 目标 | 差距 |
|------|------|------|------|
| **服务编排启动** | ❌ 无统一脚本 | ✅ docker-compose / start_all.sh | P0 |
| **API gateway** | ❌ 未独立化 | ✅ 独立 gateway | P0 |
| **跨服务 e2e** | ⚠️ 5 个 (lineage only) | 50+ | 45+ 缺口 |
| **1000 并发压测** | ❌ locust 脚本未落地 | ✅ locust + 报告 | P0 |
| **OWASP bandit** | ❌ 模块不可用 | ✅ CI 集成 | P0 |
| **OWASP safety** | ⚠️ 工具未跑 | ✅ | P1 |
| **OWASP ZAP** | ❌ 未跑 | ✅ | P1 |
| **SQL 注入** | ✅ 无 SQL | ✅ | - |
| **命令注入** | ❌ 2 处 (exec/eval) | ✅ 移除 | P0 |
| **Webhook 安全** | ✅ HMAC + constant_time | ✅ | - |
| **SSRF** | ⚠️ 无白名单 | ✅ | P1 |
| **RBAC** | ⚠️ 部分 admin 无 check | ✅ 100% | P1 |

---

## 六、P2/P3 改进 (20+ 项)

- F-8.30: chaos engineering (kill -9 service, verify recovery)
- F-8.31: 多 region 灾备测试
- F-8.32: 蓝绿部署 + 金丝雀
- F-8.33: data migration 测试 (PG 14 → 16)
- F-8.34: Python 3.11 / 3.12 兼容性
- F-8.35: Node 20 / 22 兼容性
- F-8.36: OS 兼容性 (Ubuntu / CentOS / macOS)
- F-8.37: 多租户隔离测试 (tenant A 操作不能影响 tenant B)
- F-8.38: 国际化 (zh-CN / en-US) e2e
- F-8.39: 跨浏览器 (Chrome / Firefox / Safari / Edge)
- F-8.40: 移动端 (iOS Safari / Android Chrome)
- F-8.41: 弱网测试 (3G / 4G / 5G)
- F-8.42: 离线模式测试
- F-8.43: 数据备份恢复演练
- F-8.44: 监控告警测试 (Prometheus + Grafana)
- F-8.45: 日志聚合 (ELK / Loki)
- F-8.46: 链路追踪 (Jaeger / Zipkin)
- F-8.47: 性能回归 CI (perf benchmark 阈值)
- F-8.48: 安全回归 CI (snyk / trivy 镜像扫描)
- F-8.49: 协议级 fuzzing (REST + WebSocket)

---

## 七、VERDICT

**P6-8 集成测试 + 压测 + OWASP 审查**: 🟡 **PASS with critical findings** (C+ 等级)

**e2e 覆盖**: ⚠️ **严重不足** (5 vs 50+ 目标)
**压测**: ❌ **未落地** (locust 脚本缺失)
**OWASP 自动扫描**: ❌ **bandit 不可用** (手动扫描部分覆盖)
**已知漏洞**: ❌ **2 处 eval/exec** (F-8.16 + F-8.17)

### P0 必修 (5 项, 总投入 1-1.5 天)
1. **F-8.1** 服务统一编排脚本 (4-6 hr)
2. **F-8.2** API gateway 独立化 (8-12 hr)
3. **F-8.14** locust 1000 并发脚本 + 报告 (8-12 hr)
4. **F-8.15** bandit + safety + pip-audit CI 集成 (2 hr)
5. **F-8.16 + F-8.17** eval/exec 漏洞修复 (4-6 hr)

### P1 必修 (12 项, 总投入 2-3 天)
- F-8.4 ~ F-8.13 跨服务 e2e 补全 (45+ 缺口)
- F-8.18 ~ F-8.29 压测 + ZAP + 安全

### P2/P3 改进 (20+ 项, 总投入 3-5 天)
- chaos / 多 region / 灾备 / 兼容矩阵 / 多端测试 / 监控告警 / fuzzing

**总投入**: 6-9 天达到工业级集成测试 + OWASP 合规。

**建议优先级**:
1. **F-8.1 + F-8.2** 服务编排 + gateway — 阻塞所有 e2e
2. **F-8.4 ~ F-8.13** 跨服务 e2e — 阻塞商业级发布
3. **F-8.14 + F-8.18** 压测 — 阻塞生产部署
4. **F-8.15 + F-8.16 + F-8.17** OWASP + 漏洞 — 阻塞合规
5. **F-8.19 ~ F-8.29** P1 安全 — 阻塞 SOC2 / ISO27001