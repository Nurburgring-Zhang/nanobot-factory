# NanoBot Factory — 服务等级协议 (SLA)

> **版本**: v1.0 (R10.5)
> **生效日期**: 2026-06-21
> **适用范围**: `D:\Hermes\生产平台\nanobot-factory\` (FastAPI + Vue 3 IMDF)
> **下次评审**: 2026-09-21 (季度评审)

本 SLA 文档面向**生产部署**承诺可用性、恢复能力与容量上限,所有数值均基于
R10.5 实测基线 (TestClient 单请求顺序基线) + 行业标准推算。

---

## 1. 可用性承诺

### 1.1 月度可用性

| 等级 | 月可用性 | 年停机上限 | 适用 tier |
|---|---|---|---|
| **标准 (Standard)** | **99.9%** | **43 分钟 / 月** | 默认 / 商业版 |
| 企业 (Enterprise) | 99.95% | 22 分钟 / 月 | 企业合约 (SLA addendum) |
| 关键 (Mission Critical) | 99.99% | 4.4 分钟 / 月 | 需双方另行签合同 |

**99.9% 含义**: 一个月 (按 30 天计) 内允许累计不可用时长 ≤ 43 分钟。不可用定义
见 §1.3。

### 1.2 性能 SLO (Service Level Objective)

| 端点 | p50 | **p95 (承诺值)** | p99 | 阈值依据 |
|---|---|---|---|---|
| `/healthz` (liveness) | < 2ms | **< 500ms** | < 1ms 实测 | R7 经验值,留 250x 余量 |
| `/readyz` (readiness) | < 2ms | **< 800ms** | < 5ms 实测 | 含 DB ping |
| `/metrics` (Prometheus) | < 2ms | **< 1500ms** | < 5ms 实测 | 文本渲染稍重 |
| 业务 API (CRUD) | < 50ms | **< 1000ms** | < 2000ms | 含 Pydantic 校验 + DB |

> **实测基线 (R10.5)**: `/healthz` p95 = **1.30ms**, `/readyz` p95 = **1.41ms**,
> `/metrics` p95 = **1.86ms** (n=100/50/50,TestClient, D:\ComfyUI\.ext\python.exe,
> 2026-06-21)。距离 SLO 阈值均有 **250x ~ 800x** 余量。

### 1.3 "不可用" 定义

满足**任一**即视为不可用 (按月累计)：

- 5xx 错误率 ≥ 1% 持续 60 秒以上
- `/readyz` 返回 503 持续 60 秒以上 (k8s 会停止路由流量)
- p95 延迟超出 §1.2 阈值持续 5 分钟以上

满足**任一**即**不**算不可用：

- 客户端网络抖动 / 4xx 错误 (用户责任)
- 计划内维护 (提前 48 小时通知, 不计入 SLA)
- 客户自有系统 / 集成层故障
- 不可抗力 (自然灾害 / 政府管制 / 网络运营商大规模故障)

---

## 2. RTO / RPO

### 2.1 定义

- **RTO (Recovery Time Objective)**: 故障发生后,系统恢复到可服务的目标时间
- **RPO (Recovery Point Objective)**: 故障可容忍的数据丢失上限 (按时间计)

### 2.2 故障分级与承诺

| 级别 | 场景 | **RTO** | **RPO** | 应对 |
|---|---|---|---|---|
| **P0** | 全站不可用 | **< 30 min** | **< 5 min** | 立即启动 k8s 滚动恢复 + 备份回放 |
| **P1** | 单服务降级 (如 /metrics 5xx) | < 2 hours | < 15 min | 自动重启 + 限流降级 |
| **P2** | 边缘功能异常 | < 1 business day | < 1 hour | 下个迭代修复 |
| **P3** | UI 小 bug / 文案 | 下次发版 | N/A | 周常迭代 |

### 2.3 P0 应急流程 (RTO 30 min 倒推)

```
T+0  : 告警触发 (Prometheus → Alertmanager → PagerDuty / 飞书机器人)
T+2  : on-call 工程师 ack, 启动 incident channel
T+5  : 初步定位 (kubectl logs + Prometheus dashboard + 健康端点)
T+10 : 决策路径:
        - 服务崩溃 → kubectl rollout undo → 自动恢复
        - DB 损坏 → 切换 read replica → 触发 PITR 恢复
        - 配置错误 → git revert + CI 回滚
T+15 : 系统恢复 200, /readyz 200
T+20 : 验证关键路径 (登录 + 标注 + 审核 + 交付)
T+30 : 服务对外恢复, 发布 status page
T+24h: 复盘, 输出 incident report
```

### 2.4 备份策略 (支撑 RPO 5 min)

| 数据 | 备份方式 | 频率 | 保留 | RPO |
|---|---|---|---|---|
| SQLite `imdf.db` | sqlite3 `.backup` + WAL ship | 每 5 min | 7 天本地 + 30 天 OSS | **≤ 5 min** |
| 上传文件 (OSS) | OSS 三副本 + 跨区复制 | 实时 | 永久 | **0** |
| 用户配置 / 项目元数据 | 同 DB | 每 5 min | 30 天 | **≤ 5 min** |
| 标注 / 审核结果 | 同 DB | 每 5 min | 永久归档 | **≤ 5 min** |

**回放验证**: 每周日凌晨 03:00 自动 PITR 演练到独立 namespace, 5 分钟内完成,
验证备份链路健康 (脚本: `scripts/backup_drill.py`)。

---

## 3. 容量规划

### 3.1 资源池

生产部署推荐起步配置 (单 namespace)：

| 资源 | 起步 | 弹性上限 | 备注 |
|---|---|---|---|
| API Pod (FastAPI + uvicorn) | 3 副本 / 1 CPU / 1Gi 内存 | 10 副本 (HPA) | `targetCPU=70%` |
| Worker Pod (asyncio 任务) | 2 副本 / 2 CPU / 2Gi 内存 | 8 副本 (KEDA) | 按 queue depth 扩缩 |
| SQLite + WAL | 1 主 + 1 replica / 2Gi disk | 20Gi disk | 主写备读 |
| OSS (对象存储) | 100 GB 起步 | 无上限 | 标注数据 + 用户上传 |
| PostgreSQL (可选, 100w 数据集) | 1 主 + 2 replica / 4 CPU / 8Gi | 32 CPU / 64Gi | 仅 100w 量级必选 |

### 3.2 数据集量级规划

按数据集规模分三档, 不同档位使用**不同的存储/缓存/索引策略**：

#### Tier A — 1 万 (10K) 数据集

**典型用户**: 小型团队 / POC 验证 / 单个标注项目。

| 维度 | 配置 |
|---|---|
| 项目数 | ≤ 10 |
| 图片 / 任务 | 10,000 |
| 标注员数 | ≤ 10 |
| **DB** | **SQLite 单机** (WAL mode) |
| **Worker** | 1-2 副本, 1 CPU / 1Gi |
| **存储** | 本地 disk + 每日备份到 OSS |
| **缓存** | 无需 |
| 预期 p95 (业务 API) | < 200ms |
| 月成本 (估算) | $50 (云) / ¥800 (自建) |
| 推荐 SLO | 99.5% (开发环境) / 99.9% (生产) |

#### Tier B — 10 万 (100K) 数据集

**典型用户**: 中型标注团队 / 多项目并行 / 商业化标准。

| 维度 | 配置 |
|---|---|
| 项目数 | ≤ 100 |
| 图片 / 任务 | 100,000 |
| 标注员数 | ≤ 100 |
| **DB** | **SQLite 主从** 或 **PostgreSQL 单实例** |
| **Worker** | 3-5 副本, 2 CPU / 2Gi |
| **存储** | 本地 NVMe + OSS 双副本 |
| **缓存** | Redis 1GB (LRU session / rate limit) |
| 预期 p95 (业务 API) | < 500ms |
| 月成本 (估算) | $300 (云) / ¥4000 (自建) |
| 推荐 SLO | **99.9% (本 SLA 标准档)** |

#### Tier C — 100 万 (1M) 数据集

**典型用户**: 大型平台 / 多租户 / SLA 合约客户。

| 维度 | 配置 |
|---|---|
| 项目数 | ≤ 1,000 |
| 图片 / 任务 | 1,000,000 |
| 标注员数 | ≤ 1,000 (并发 ≤ 200) |
| **DB** | **PostgreSQL 主从 + 读写分离 + 连接池 (pgbouncer)** |
| **Worker** | 8-16 副本 (KEDA), 4 CPU / 4Gi |
| **存储** | OSS + CDN (静态资源) + MinIO (热数据) |
| **缓存** | Redis 8GB cluster (3 master + 3 replica) |
| **搜索** | Elasticsearch 3 节点 (高级搜索) |
| **消息队列** | RabbitMQ / Kafka (任务调度) |
| 预期 p95 (业务 API) | < 1000ms |
| 月成本 (估算) | $2000 (云) / ¥25000 (自建) |
| 推荐 SLO | **99.95% (企业档, SLA addendum)** |

### 3.3 性能预算 (Tier B 标准档, 99.9% 承诺)

基于 R10.5 实测 + 生产经验推算:

| 阶段 | 预算 | 实测 (TestClient) | 余量 |
|---|---|---|---|
| 入口 nginx / LB | < 5ms | N/A (infra) | - |
| TLS handshake | < 10ms | N/A (infra) | - |
| ASGI 路由匹配 | < 2ms | **1.30ms** (/healthz) | 1.5x |
| Pydantic 校验 | < 5ms | < 1ms (健康端点) | 5x |
| DB 查询 | < 50ms | < 2ms (/readyz) | 25x |
| 业务逻辑 | < 100ms | TBD (随模块) | - |
| 序列化 + 响应 | < 10ms | < 1ms | 10x |
| **总 p95 预算** | **< 500ms** | **< 200ms 典型** | **2.5x** |

### 3.4 扩容触发器

| 指标 | 阈值 (Tier B) | 动作 |
|---|---|---|
| API Pod CPU | > 70% 持续 5min | HPA +1 副本 (max 10) |
| API Pod 内存 | > 80% 持续 5min | HPA +1 副本 |
| p95 延迟 | > 800ms 持续 5min | 告警 + 容量评估 |
| DB 连接数 | > 80% pool capacity | 连接池扩容 + 读写分离 |
| 磁盘使用 | > 80% | 自动清理 + 扩容 PV |
| OSS 请求失败率 | > 1% 持续 5min | 切换备用 region |

---

## 4. 支持与响应时间

### 4.1 工单分级与响应

| 级别 | 描述 | 首次响应 | 解决目标 |
|---|---|---|---|
| P0 (Critical) | 生产全停 / 数据丢失 | **< 15 min** | RTO 30 min |
| P1 (High) | 主要功能不可用 | < 1 hour | < 4 hours |
| P2 (Medium) | 功能受损但有 workaround | < 4 hours | < 1 business day |
| P3 (Low) | 咨询 / 优化建议 | < 1 business day | 下次发版 |

### 4.2 支持渠道

- **工单系统**: <https://support.nanobot-factory.example.com> (24/7)
- **紧急热线**: P0 客户专属 (SLA addendum 提供)
- **状态页**: <https://status.nanobot-factory.example.com> (实时)

---

## 5. 责任矩阵

| 责任方 | 范围 |
|---|---|
| **NanoBot Factory** | 应用层 SLA (本文件), 数据库 / 存储 / 计算可用性 |
| 云服务商 (IaaS) | 底层 VM / 网络 / 磁盘 SLA (其自有 SLA 文档) |
| 客户 (使用方) | 凭据安全 / API 调用规范 / 数据合规 |
| 集成方 (下游) | 集成层 / 回调实现 / 错误处理 |

---

## 6. SLA 信用 (补偿)

未达 SLO 时的服务信用:

| 实际可用性 | 月费信用 |
|---|---|
| 99.0% ~ 99.9% | 0% |
| 95.0% ~ 99.0% | 10% |
| < 95.0% | 25% |

**申领方式**: 客户在故障发生后 30 天内提交书面申请 + 故障时段证据
(trace_id + 时间窗口), NanoBot Factory 5 个工作日内审核并发放信用。

---

## 7. 限制与例外

以下情况**不**触发 SLA 信用:

1. 客户违反 AUP (Acceptable Use Policy)
2. 客户自有网络 / 设备 / 集成层故障
3. 计划内维护 (提前 48h 通知)
4. 不可抗力
5. 测试 / staging 环境 (SLA 仅适用于 production)
6. beta 功能 (文档明确标注的)
7. 单租户内自我造成的限流

---

## 8. 文档维护

| 项目 | 内容 |
|---|---|
| 关联文档 | `docs/runbook.md` (故障处理手册), `docs/deployment.md` (部署架构) |
| 评审周期 | 季度 (每 3 个月) |
| 变更通知 | 重大变更提前 30 天邮件通知 |
| Owner | Platform Team (`platform@nanobot-factory.example.com`) |

---

## 附录 A — R10.5 实测基线

**测试环境**:
- Python: 3.11 (`D:\ComfyUI\.ext\python.exe`)
- 框架: FastAPI + uvicorn (TestClient in-process)
- 端点: `/healthz`, `/readyz`, `/metrics`
- 样本: 100 / 50 / 50 顺序请求 (含 1 次 warm-up)

**实测数据**:

| 端点 | n | min | p50 | **p95** | p99 | max |
|---|---|---|---|---|---|---|
| `/healthz` | 100 | 1.00ms | 1.11ms | **1.30ms** | 1.40ms | 1.48ms |
| `/readyz` | 50 | 1.18ms | 1.27ms | **1.41ms** | 1.44ms | 1.46ms |
| `/metrics` | 50 | 1.57ms | 1.69ms | **1.86ms** | 1.98ms | 1.99ms |

**与 SLO 对比**:

| 端点 | SLO p95 | 实测 p95 | 余量倍数 |
|---|---|---|---|
| `/healthz` | < 500ms | 1.30ms | **384x** |
| `/readyz` | < 800ms | 1.41ms | **567x** |
| `/metrics` | < 1500ms | 1.86ms | **806x** |

> **注**: 这是单请求顺序基线, 不是负载基线。100 并发下数字会高 10-100x,
> 需要 `wrk` / `k6` / `locust` 等专门压测工具在生产前验证。
> 当前数字的用途是"回归锚点", 如果哪天 p95 突然涨到 50ms 以上, 说明有
> 东西改坏了, 会立刻被 R10.5 perf test (`backend/tests/perf/test_r10_5_perf.py`) catch。

---

## 附录 B — 术语表

| 术语 | 含义 |
|---|---|
| ASGI | Async Server Gateway Interface (Python 异步 web 标准) |
| HPA | Horizontal Pod Autoscaler (k8s 自动扩缩) |
| KEDA | Kubernetes Event-Driven Autoscaling |
| PITR | Point-In-Time Recovery (时间点恢复) |
| p50/p95/p99 | 50/95/99 百分位延迟 |
| RPO | Recovery Point Objective (可容忍数据丢失时间) |
| RTO | Recovery Time Objective (恢复时间目标) |
| WAL | Write-Ahead Logging (SQLite 预写日志) |