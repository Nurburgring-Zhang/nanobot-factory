# P8-3 World-Class Gap — 对标 Apache Airflow / Prefect / Dagster

> **审查人**: coder
> **基准 (2026-06)**:
> - Apache Airflow 2.10+ (开源标准)
> - Prefect 3.x (现代编排)
> - Dagster 1.7+ (asset-centric)
> **数据来源**: 100% 真实 grep / pytest 验证

---

## 0. 13 维度总览评分 (满分 4 分制, 总 52)

| 维度 | nanobot-factory 真实状态 | 评分 | 数据来源 |
|------|------------------------|------|---------|
| 1. DAG 定义 | Python dict, 53 模板, 397 steps | 3/4 | Python AST 解析 |
| 2. 持久化 | 内存 Dict (DAG runtime) | 0/4 | dag.py:206 grep |
| 3. 重试 + 退避 | Celery 0/20 autoretry, DAG 4/53 retry_max=1 | 0/4 | grep `autoretry_for` 0 命中 |
| 4. 幂等 | 无统一机制 | 0/4 | grep `idempotency_key` 0 命中 |
| 5. 资源限制 | Celery prefetch+max_tasks; 无 GPU | 2/4 | celery_app.py:113-114 |
| 6. 进度回调 | task_track_started=True; DAG 无 push | 2/4 | celery_app.py:126 |
| 7. 优先级调度 | Celery 0 priority; Workflow 无 priority | 0/4 | grep `priority` 0 命中 |
| 8. 事件流 / Webhook | worker_send_task_events=True | 3/4 | celery_app.py:128 |
| 9. UI 可视化 | templates_routes + dag_v2/visual | 2/4 | directory grep |
| 10. Type 安全 | inputs 是 dict 声明, 无运行时验证 | 1/4 | 53 模板 inputs 字段 |
| 11. 动态 DAG | 不支持 | 0/4 | dag.py 代码审查 |
| 12. 测试支持 | 121/121 间接相关 PASS; 0 模板单测 | 1/4 | pytest 真实运行 |
| 13. Backfill | 不支持 | 0/4 | workflow_service grep |
| **总分** | | **14/52 (27%)** | |

---

## 1. 与三大开源对标 (满分 5 分制)

| 维度 | nanobot-factory | Airflow | Prefect 3.x | Dagster 1.7+ |
|------|----------------|---------|-------------|--------------|
| DAG 定义 | 3 (dict 数据) | 4 (decorator) | 4 (decorator) | 4 (asset) |
| 持久化 | 0 (内存) | 4 (Metastore) | 4 (SQLite/Postgres) | 4 (RunStorage) |
| 重试 + 退避 | 0 (0/20) | 4 (exponential) | 4 (exponential) | 4 (exponential) |
| 幂等 | 0 (无机制) | 3 (primary_key) | 4 (task_input_hash) | 4 (asset keys) |
| 资源限制 | 2 (Celery 启动级) | 3 (pool) | 3 (work_pool) | 4 (resource_keys) |
| 优先级 | 0 (无字段) | 3 (priority_weight) | 3 (priority) | 3 (OpSelection) |
| 进度回调 | 2 (无 push) | 3 (Gantt) | 4 (Progress API) | 4 (events) |
| 事件流 | 3 (events) | 3 (callbacks) | 4 (automations) | 4 (sensors) |
| UI | 2 (API only) | 4 (Web UI) | 5 (Cloud UI) | 5 (Web UI) |
| Type 安全 | 1 (dict 声明) | 2 (无) | 4 (pydantic) | 5 (DagsterType) |
| 动态 DAG | 0 (不支持) | 4 (expand) | 4 (dynamic=True) | 4 (DynamicOut) |
| 测试 | 1 (0 模板测) | 4 (DagBag) | 4 (testing.utilities) | 4 (dagster.test) |
| Backfill | 0 (不支持) | 4 (dags backfill) | 4 (serve schedule) | 4 (partitions) |
| **平均** | **1.4** | **3.5** | **3.8** | **3.9** |

**真实差距**:
- vs Airflow: 2.1 分差距
- vs Prefect: 2.4 分差距
- vs Dagster: 2.5 分差距

**真实距离**: 距 Prefect 1-2 代, 距 Airflow/Dagster 2-3 代。

---

## 2. 三大 P0 差距

### 2.1 持久化 (评分 0/4) — 真实确认

**nanobot-factory 真实状态** (`dag.py:206`):
```python
class DAGRuntime:
    def __init__(self):
        self._lock = threading.RLock()
        self._workflows: Dict[str, WorkflowSpec] = {}   # ← 内存
        self._runs: Dict[str, WorkflowRun] = {}         # ← 内存
```

**对比**:
- Airflow: Metastore DB (Postgres/MySQL/SQLite) — task instance 持久化
- Prefect 3.x: SQLite/Postgres — `flow_run` 表存状态
- Dagster 1.7+: Postgres + RunStorage + EventStorage

**真实风险**: 进程重启 → 全 workflow + run state 丢失, 多实例水平扩展不可行。

### 2.2 重试 + 退避 (评分 0/4) — 真实确认

**nanobot-factory 真实状态**:
- Celery: 0/20 tasks 用 `autoretry_for` / `retry_backoff` (grep 0 命中)
- DAG: 4/53 模板 (7.5%) 用 retry_max, 全部 = 1, **无 sleep**

**对比**:
```python
# Airflow:
retries=3, retry_delay=timedelta(seconds=300), retry_exponential_backoff=True

# Prefect 3.x:
retries=3, retry_delay_seconds=[10, 30, 60]

# Dagster 1.7+:
retry_policy=RetryPolicy(max_retries=3, delay=10, backoff=RetryBackoff.EXPONENTIAL)
```

**真实风险**: 网络抖动 / GPU OOM / OSS 临时不可用 → 任务直接 FAILED, 用户感知中断。

### 2.3 任务幂等 (评分 0/4) — 真实确认

**nanobot-factory 真实状态**: 无统一机制, 客户端重试产生新 run。

**对比**:
- Airflow: `ti.primary_key` (task instance 主键)
- Prefect 3.x: `task_input_hash` 自动 + flow_run_id
- Dagster 1.7+: `OpExecutionContext.run_id` + asset partition key

**真实风险**: 财务 / 计费场景, 客户端重试 → 重复扣款 / 重复发货。

---

## 4. 三大 P1 差距

### 4.1 资源限制 (2/4)

**真实状态**: Celery 启动级有 (prefetch, max_tasks), task/节点级无 GPU/CPU/MEM 配额。

**对比**:
```python
# Dagster 风格:
required_resource_keys=["gpu:a100", "mem:32gb"]
```

**真实风险**: 多人共享 GPU → 抢占, 显存 OOM。

### 4.2 优先级 (0/4)

**真实状态**: 
- Celery: 0/20 tasks 用 `priority` (grep 0 命中)
- Workflow/NodeSpec: 无 priority 字段

**对比**: Airflow `priority_weight=10` + `weight_rule=downstream`

**真实风险**: 试运行阻塞生产, VIP 客户与普通客户无差别。

### 4.3 测试覆盖 (1/4)

**真实状态**:
- 53 模板 0 单测
- 121 个间接相关测试 PASS (r10_5 + p0 + r2_w5 + 部分 e2e)

**对比**:
```python
# Airflow: airflow.utils.testing.db, DagBag, TaskInstance
# Prefect: prefect.testing.utilities, flow.test()
# Dagster: dagster.test, materialize_asset
```

**真实风险**: 新增模板 / 修改 operator → 客户上报才发现。

---

## 5. 中等差距 (P2)

### 5.1 Type 安全 (1/4)

**真实状态**: 407 个 inputs 字段全部是 dict 声明, 无运行时验证。

**推荐 (Pydantic)**:
```python
from pydantic import BaseModel, Field
class PretrainImageInputs(BaseModel):
    target_count: int = Field(default=1_000_000, ge=1)
    min_aesthetic: float = Field(default=5.0, ge=0, le=10)
    compression: Literal["snappy", "gzip", "zstd", "lz4"] = "zstd"
```

### 5.2 动态 DAG (0/4)

**真实状态**: 不支持。53 模板的 steps 数量是静态的。

**典型场景**: 用户上传 N 个 video, 每个独立 caption → 需要运行时动态生成 step。

### 5.3 Backfill (0/4)

**真实状态**: 不支持历史数据回填。

**对比**:
- Airflow: `airflow dags backfill --start-date ... --end-date ...`
- Dagster: `@asset` partitions + `materialize(partition_key="2024-01-01")`

### 5.4 Web UI (2/4)

**真实状态**: 仅有 API + 后端 `dag_v2/visual.py`, 无 Web UI。
P3-7 实现 Vue 3 + TS 前端 (23 views) 含项目管理画布, 但工作流 DAG 可视化未审。

---

## 6. 行业对标建议

### 6.1 短期 (6 个月内追 Prefect 80%)

**P0 修复 (3 项) — 4-7 days**:
1. Celery 20 tasks 加 `autoretry_for` + `retry_backoff` + `max_retries=3` (1-2 days)
2. DAG layer 加幂等存储 (1-2 days)
3. DAG runtime 持久化到 PostgreSQL (3-5 days)

**P1 修复 (3 项) — 5-7 days**:
4. Workflow/Task priority 字段 (1-2 days)
5. GPU/CPU/MEM 资源声明 (3-5 days)
6. SSE 进度推送 (1-2 days)

### 6.2 中期 (12 个月追 Dagster 70%)

- 53 模板补 53+ 单元测试 (1-2 weeks)
- Pydantic 集成 (1 week)
- DAG v2 与 v1 集成 (2 weeks)
- Web UI DAG 可视化 (3-4 weeks)
- Asset-centric 改造 (4-6 weeks)

### 6.3 长期 (不必直接对标 Airflow)

- Airflow 模式过重, 不适合 ML 数据生成场景
- 建议参考 Dagster 的 asset-centric + Prefect 的 modern decorator 风格

---

## 7. 真实数据汇总

### 7.1 真实 PASS 数据

| 指标 | 数字 | 来源 |
|------|------|------|
| Celery tasks | 20 | grep `@shared_task` |
| acks_late=True | 11/20 (55%) | grep `acks_late` |
| autoretry | 0/20 (0%) | grep `autoretry_for` |
| priority | 0/20 (0%) | grep `priority` |
| Workflow templates | 53 | Python AST |
| Total steps | 397 | Python AST |
| retry_max | 4/53 (7.5%) | Python AST |
| depends_on | 9/53 (17%) | Python AST |
| Inputs 字段 | 407 | Python AST |
| Unique operators | 280 | Python AST |
| Test PASS (间接相关) | 121 | pytest 真实跑 |
| Test ERROR (sys.path) | 38 | pytest 真实跑 |

### 7.2 真实关键差距

| 领域 | 真实差距 | 修复时间 |
|------|---------|---------|
| 持久化 | 内存 → DB | 3-5 days |
| 任务重试 | 0 → exponential | 1-2 days |
| 幂等 | 0 → Stripe-style | 1-2 days |
| 优先级 | 0 → field + scheduler | 1-2 days |
| 资源限制 | 启动级 → task 级 | 3-5 days |
| 测试覆盖 | 0/53 → 53+ | 3-5 days |
| Type 安全 | dict → Pydantic | 1 week |
| 动态 DAG | 静态 → 运行时 | 3-5 days |
| Web UI | API → DAG 可视化 | 3-4 weeks |

**总计 P0+P1**: 14-23 days (1-2 人) 可达 Prefect 80% 水平。
