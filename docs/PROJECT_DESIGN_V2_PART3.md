# 智影 (ZhiYing) V2 设计文档 — Part 3: 能力差距汇总与扩展设计

> **续 Part 1 + Part 2**: 12 域对比已完成,本章汇总 60+ 缺口 + 15 项扩展设计

---

## 第 16 章 识别的能力差距汇总 (60+ 项)

### 16.1 P1 关键缺口 (高商业价值, 优先补强)

| # | 域 | 缺口 | 商业价值 | 工作量 |
|---|---|---|---|---|
| 1 | 标注 | AI 辅助标注 (SAM/GroundingDINO) | 极高 (5-10× 效率) | 2 周 |
| 2 | 标注 | Active Learning 闭环 | 高 | 1 周 |
| 3 | 标注 | Consensus + IoU 多人投票 | 高 | 1 周 |
| 4 | 标注 | LiDAR / 3D 点云标注 | 中高 | 3 周 |
| 5 | 标注 | CRDT 实时协作 | 中 | 2 周 |
| 6 | 治理 | 三层 Catalog (catalog.schema.table) | 高 | 1 周 |
| 7 | 治理 | 列级 ACL | 高 | 1 周 |
| 8 | 治理 | 动态数据脱敏 | 高 | 1 周 |
| 9 | 治理 | ML 资产治理 (Model + Notebook) | 极高 | 2 周 |
| 10 | 治理 | AI 资产治理 (Agent + Prompt) | 极高 | 1 周 |
| 11 | 治理 | OpenLineage 兼容 | 高 | 1 周 |
| 12 | 编排 | Cron 触发器 | 高 | 1 周 |
| 13 | 编排 | 事件触发器 | 高 | 1 周 |
| 14 | 编排 | 异步执行 (Celery) | 极高 | 2 周 |
| 15 | 编排 | SLA 监控 + 告警 | 中 | 1 周 |
| 16 | 编排 | K8s 原生执行 | 中 | 2 周 |
| 17 | VDB | HNSW 索引 | 极高 | 1 周 |
| 18 | VDB | 量化压缩 (int8/PQ) | 高 | 1 周 |
| 19 | VDB | 混合检索 (BM25+vec) | 极高 | 1 周 |
| 20 | VDB | pgvector 适配 | 高 | 1 周 |
| 21 | VDB | 元数据过滤 (server-side) | 高 | 1 周 |
| 22 | MLOps | Model Registry | 极高 | 1 周 |
| 23 | MLOps | Experiment Tracker | 极高 | 1 周 |
| 24 | MLOps | Model Serving | 极高 | 2 周 |
| 25 | MLOps | Drift Detection | 高 | 1 周 |
| 26 | MLOps | Feature Store (Feast 集成) | 高 | 2 周 |
| 27 | 质量 | 数据 Profile 自动推断 | 高 | 1 周 |
| 28 | 质量 | 跨表引用完整性 | 中 | 1 周 |
| 29 | 质量 | 时序漂移检测 | 高 | 1 周 |
| 30 | 血缘 | 列级血缘 | 极高 | 2 周 |
| 31 | 血缘 | AI 资产血缘 | 高 | 1 周 |
| 32 | 血缘 | OpenLineage 出站 | 高 | 1 周 |
| 33 | 血缘 | 跨组织 lineage | 中 | 1 周 |
| 34 | AI Router | 自动 Fallback | 极高 | 3 天 |
| 35 | AI Router | Circuit Breaker | 极高 | 1 周 |
| 36 | AI Router | 语义缓存 | 高 | 1 周 |
| 37 | AI Router | Prompt 版本管理 | 高 | 1 周 |
| 38 | AI Router | Guardrails (Toxicity/越狱) | 极高 | 1 周 |
| 39 | Agent | Memory 系统 (短+长) | 极高 | 2 周 |
| 40 | Agent | Human-in-the-loop | 极高 | 1 周 |
| 41 | Agent | Streaming Response (SSE) | 高 | 1 周 |
| 42 | Agent | Tool Marketplace | 中 | 2 周 |
| 43 | Agent | A2A 协议 | 中 | 2 周 |
| 44 | Agent | 多 Agent 协作 (CrewAI) | 高 | 3 周 |
| 45 | Agent | Browser Use | 中 | 1 周 |
| 46 | 安全 | SSO (SAML/OIDC) | 极高 | 1 周 |
| 47 | 安全 | MFA | 极高 | 1 周 |
| 48 | 安全 | ABAC (属性级权限) | 高 | 2 周 |
| 49 | 安全 | SCA 依赖扫描 | 高 | 3 天 |
| 50 | 安全 | 合规报告 (GDPR/AI Act) | 极高 | 2 周 |
| 51 | 可观测 | Loki 集中日志 | 高 | 1 周 |
| 52 | 可观测 | SLO/SLI | 高 | 1 周 |
| 53 | 可观测 | RUM (前端) | 中 | 1 周 |
| 54 | 可观测 | Alertmanager | 高 | 1 周 |
| 55 | UI/UX | Command Palette (Cmd+K) | 高 | 1 周 |
| 56 | UI/UX | 内嵌 AI 助手 | 极高 | 2 周 |
| 57 | UI/UX | 键盘快捷键 | 高 | 1 周 |
| 58 | UI/UX | 离线 (PWA) | 中 | 1 周 |
| 59 | 新增域 | Feature Store (独立) | 极高 | 2 周 |
| 60 | 新增域 | Dataset Versioning (DVC) | 极高 | 2 周 |
| 61 | 新增域 | 高级计费 (Stripe 风格) | 极高 | 3 周 |
| 62 | 新增域 | A/B 测试 (Eppo) | 高 | 2 周 |
| 63 | 新增域 | 通知 (Slack/Lark) | 高 | 1 周 |
| 64 | 新增域 | 文档 (Notion 风格) | 中 | 3 周 |
| 65 | 新增域 | Schema Registry (Confluent) | 中 | 2 周 |
| 66 | 新增域 | 漂移检测 (Whylabs) | 高 | 1 周 |
| 67 | 新增域 | Prompt Eval (LangSmith) | 高 | 2 周 |
| 68 | 新增域 | CDP / 用户画像 | 中 | 3 周 |
| 69 | 新增域 | 项目管理 (Linear 风格) | 中 | 2 周 |

**P1 总工作量**: ~120 工程师-周 (按 5 人 × 24 周, 6 个月可达)
**P2 总工作量**: ~50 工程师-周
**P3 总工作量**: ~30 工程师-周

### 16.2 缺口优先级矩阵 (P1 高价值缺口可视化)

```
                          高商业价值
                            ↑
                            │
     标注 AI 辅助 ────────────┤ ── Model Registry
     异步执行 ───────────────┤ ── ML 资产治理
     Model Serving ──────────┤ ── Drift Detection
     HNSW 索引 ──────────────┤ ── Memory
     SSO ───────────────────┤ ── AI 助手
     列级血缘 ───────────────┤ ── Streaming
     OpenLineage ────────────┤ ── Prompt Registry
     Feature Store ──────────┤ ── MLOps 全栈
                            │
     ───────────────────────┼──────────────────────────→
     低工作量                 高工作量
```

### 16.3 商业价值 vs 工作量矩阵

| 象限 | 描述 | 处理 |
|---|---|---|
| Q1: 高价值 + 低工作量 | 三层 Catalog / 列级 ACL / Fallback / 触发器 | **立即做** |
| Q2: 高价值 + 中等工作量 | AI 辅助标注 / Model Registry / Memory / SSO | **6 个月内** |
| Q3: 高价值 + 高工作量 | LiDAR / 异步执行 / MLOps 全栈 / 高级计费 | **12 个月内** |
| Q4: 低价值 + 低工作量 | 椭圆几何 / 触屏优化 | **按需做** |
| Q5: 低价值 + 高工作量 | 跨组织 lineage / Browser Use | **不做** |

---

## 第 17 章 Feature Store 设计补充 (vs Feast/Tecton/Hopsworks)

### 17.1 智影当前状态

智影**没有 Feature Store**,导致:
- 模型训练特征和在线特征可能不一致 (training-serving skew)
- 特征复用困难
- 特征血缘不可追溯

### 17.2 顶级 Feature Store 对比

| 功能 | Feast | Tecton | Hopsworks | AWS SageMaker Feature Store | Databricks Feature Store | 智影 (扩展) |
|---|---|---|---|---|---|---|
| **Online (低延迟)** | ✅ Redis | ✅ DynamoDB | ✅ MySQL | ✅ | ✅ | 设计: Redis 适配 |
| **Offline (高吞吐)** | ✅ Parquet/S3 | ✅ S3 | ✅ Hudi | ✅ | ✅ Delta Lake | 设计: Parquet |
| **Feature Registry** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计: 新增 `feature_registry` 表 |
| **Feature Lineage** | ⚠️ | ✅ | ✅ | ✅ | ✅ | 设计: 继承 EventBus |
| **时间点正确性 (Point-in-time)** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计: TTL + asof join |
| **Transformation (On-Demand)** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计: SQL + Python UDF |
| **Monitoring (Drift)** | ⚠️ | ✅ 强 | ✅ | ✅ | ✅ | 设计: 集成 Evidently |
| **Feature Versioning** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计: 扩展 store |
| **Backfill** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计: workflow_builder |
| **Streaming Ingestion** | ⚠️ | ✅ 强 | ✅ | ✅ (Kinesis) | ✅ | 设计: Kafka 适配 |
| **低代码 UI** | ⚠️ | ✅ | ✅ | ✅ | ✅ | 设计: Vue 3 + Naive |
| **Multi-tenant** | ⚠️ | ✅ | ✅ | ✅ | ✅ | 设计: 集成 RBAC |
| **Open Source** | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ 自建 |

### 17.3 智影 Feature Store 设计

#### 17.3.1 数据模型

```python
# models/feature_store.py
class FeatureGroup(Base):
    __tablename__ = "feature_groups"
    id: str  # fg_<8-hex>
    name: str
    description: str
    entity: str  # 关联实体 (user / asset / project)
    owner: str
    version: int  # 默认 1
    source_query: str  # SQL 视图或 Python 表达式
    transformation: Optional[str]
    ttl_days: int = 30
    online_enabled: bool = False
    offline_enabled: bool = True
    created_at: datetime
    updated_at: datetime

class FeatureView(Base):
    __tablename__ = "feature_views"
    id: str
    feature_group_id: str
    name: str  # feature 名称
    dtype: str  # int/float/string/bool/vector
    description: str
    default_value: Optional[Any]
    validation_rules: dict  # min/max/regex
    created_at: datetime

class FeatureValue(Base):
    __tablename__ = "feature_values"
    entity_key: str  # user_<8-hex>
    feature_group_id: str
    feature_name: str
    value: Any  # JSON
    event_ts: datetime  # 时间点
    created_at: datetime
```

#### 17.3.2 API 设计

```python
# engines/feature_store_engine.py
class FeatureStoreEngine:
    def create_feature_group(name, entity, source_query, ttl_days=30) -> FeatureGroup
    def add_feature_view(group_id, name, dtype, validation_rules) -> FeatureView
    def materialize_online(group_id) -> int  # 把 offline → online
    def get_online_features(entity_key, feature_names) -> Dict[str, Any]  # < 10ms
    def get_historical_features(entity_keys, feature_names, asof_ts) -> DataFrame
    def get_feature_lineage(feature_name) -> Dict  # 上游 + 下游
    def backfill(group_id, start, end) -> int
    def validate_drift(group_id) -> Report
```

#### 17.3.3 工作量
- 数据模型: 1 工程师 × 3 天
- Engine: 2 工程师 × 2 周
- UI: 1 工程师 × 1 周
- 集成 Model Registry / 实验跟踪: 1 工程师 × 1 周
- **总计**: ~5 工程师-周

---

## 第 18 章 数据集版本控制设计 (vs DVC/Pachyderm/lakeFS)

### 18.1 智影当前状态

智影的 `assets` / `datasets` / `packs` 表没有版本控制,导致:
- 数据集迭代无法回滚
- 实验可复现性差
- 数据集 vs 模型血缘断裂

### 18.2 顶级数据集版本控制对比

| 功能 | DVC | Pachyderm | lakeFS | Delta Lake | 智影 (扩展) |
|---|---|---|---|---|---|
| **基于 Git (commit/branch)** | ✅ | ⚠️ | ✅ | ⚠️ | 设计: 简化版 |
| **基于对象存储 (S3/MinIO)** | ✅ | ✅ | ✅ | ⚠️ | 设计: MinIO |
| **大文件 (GB/TB)** | ✅ | ✅ | ✅ | ✅ | 设计: 切分 chunk |
| **不可变快照** | ⚠️ | ✅ | ✅ | ✅ | 设计: snapshot |
| **数据血缘** | ⚠️ dvc.yaml | ✅ | ✅ | ⚠️ | 设计: 集成 EventBus |
| **跨云** | ✅ | ✅ | ✅ | ✅ | 设计: 自定义 |
| **元数据 Schema** | ⚠️ | ✅ | ✅ | ✅ | 设计: Pydantic |
| **HTTP API** | ⚠️ | ✅ | ✅ | ✅ | 设计: FastAPI |
| **Open Source** | ✅ | ✅ | ✅ | ✅ | ✅ |

### 18.3 智影 Dataset Versioning 设计

```python
# models/dataset_version.py
class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    id: str  # dsv_<12-hex>
    dataset_id: str  # ds_<8-hex>
    version: str  # "1.0.0" / git-like hash
    parent_version_id: Optional[str]  # 父版本
    branch: str  # main / dev / experiment-1
    snapshot_path: str  # S3/MinIO 路径
    size_bytes: int
    files_count: int
    schema_hash: str  # 列 schema 的 hash
    stats: dict  # 行数/列数/分布
    created_by: str
    created_at: datetime
    message: str  # commit message
    tags: List[str]

class DatasetVersionDiff(Base):
    __tablename__ = "dataset_version_diffs"
    from_version_id: str
    to_version_id: str
    added_files: List[str]
    removed_files: List[str]
    modified_files: List[str]
    added_rows: int
    removed_rows: int
    schema_changes: dict
```

**API**:
- `POST /api/v1/datasets/{ds_id}/versions` 创建新版本 (commit)
- `GET /api/v1/datasets/{ds_id}/versions` 列出所有版本
- `GET /api/v1/datasets/{ds_id}/versions/{version}/diff?from=...` 看 diff
- `POST /api/v1/datasets/{ds_id}/versions/{version}/checkout` 切版本
- `POST /api/v1/datasets/{ds_id}/branches` 创建分支
- `POST /api/v1/datasets/{ds_id}/branches/{branch}/merge` 合并分支

**工作量**: 1 工程师 × 2 周

---

## 第 19 章 高级计费 / 用量计费设计 (vs Stripe/Metronome/Orb)

### 19.1 智影当前状态

智影有 `business/billing.py`:
- `UsageMeter` (in-memory + JSONL)
- `TieredPricing` (Free/Pro/Enterprise)
- `InvoiceEngine` (月度发票)
- `InMemoryUsageStore` / `JsonlUsageStore`

但缺:
- 复杂定价模型 (混合固定费 + 用量 + 阶梯)
- 实时用量监控
- 自动开票 (税务计算)
- 订阅管理 (升降级、暂停、恢复)
- 多币种
- 支付集成 (Stripe / 支付宝 / 微信)

### 19.2 顶级计费平台对比

| 功能 | Stripe Billing | Metronome | Orb | Maxio | Chargebee | 智影 (扩展) |
|---|---|---|---|---|---|---|
| **订阅管理** | ✅ 强 | ✅ | ✅ | ✅ | ✅ 强 | 设计 |
| **用量计费** | ✅ | ✅ 业界领先 | ✅ 业界领先 | ✅ | ⚠️ | 设计 |
| **复杂定价模型** | ✅ | ✅ 强 | ✅ 强 | ✅ | ✅ | 设计 |
| **混合 (固定 + 用量)** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **阶梯定价** | ✅ | ✅ 强 | ✅ 强 | ✅ | ✅ | 设计 |
| **多币种** | ✅ 135+ | ✅ | ✅ | ✅ | ✅ | 设计 (10+) |
| **税务计算 (TaxJar/Avalara)** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **发票 + PDF** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **支付集成** | ✅ (Stripe) | ⚠️ | ⚠️ | ✅ | ✅ | 设计 (Stripe/支付宝/微信) |
| **Dunning (欠款管理)** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **Revenue Recognition** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **Webhook 出站** | ✅ 强 | ✅ | ✅ | ✅ | ✅ | 设计 |
| **Custom Dashboard** | ⚠️ | ✅ 强 | ✅ 强 | ✅ | ✅ | 设计 |
| **Forecast / 预测** | ⚠️ | ✅ 强 | ✅ 强 | ⚠️ | ⚠️ | 设计 |
| **Multi-tenant** | ⚠️ | ✅ 强 | ✅ | ✅ | ✅ | 设计 |
| **价格实验 (A/B pricing)** | ⚠️ | ✅ | ✅ | ⚠️ | ⚠️ | 设计 |
| **Self-service Portal** | ✅ 强 | ✅ | ⚠️ | ✅ | ✅ 强 | 设计 |
| **Quote-to-Cash** | ✅ | ⚠️ | ⚠️ | ✅ | ✅ 强 | 设计 |

### 19.3 智影高级计费设计

```python
# business/billing_v2.py
class PricingModel(BaseModel):
    """支持混合定价:固定费 + 用量 + 阶梯 + 分级"""
    base_fee: Decimal = Decimal(0)
    components: List[PricingComponent]  # 多个组件叠加

class PricingComponent(BaseModel):
    metric: str  # "api_calls" / "storage_gb" / "users" / "tokens"
    unit: str  # "count" / "gb_hour" / "month"
    pricing_type: Literal["flat", "tiered", "volume", "graduated"]
    tiers: List[PricingTier]  # 阶梯
    free_quota: int = 0
    overage_multiplier: Decimal = Decimal(1.5)

class PricingTier(BaseModel):
    up_to: Optional[Decimal]  # 上限
    unit_price: Decimal  # 单价 (cents)
    flat_fee: Decimal = Decimal(0)

class Subscription(BaseModel):
    tenant_id: str
    plan_id: str
    pricing_model: PricingModel
    start_at: datetime
    end_at: Optional[datetime]
    status: Literal["active", "paused", "canceled", "trial"]
    payment_method_id: Optional[str]

class UsageEvent(BaseModel):
    tenant_id: str
    metric: str
    quantity: Decimal
    timestamp: datetime
    idempotency_key: str
    metadata: dict

class Invoice(BaseModel):
    tenant_id: str
    period_start: datetime
    period_end: datetime
    line_items: List[LineItem]
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    status: Literal["draft", "open", "paid", "void", "uncollectible"]
    due_at: datetime
```

**新 API 端点**:
- `POST /api/v1/billing/plans` 创建定价方案
- `POST /api/v1/billing/subscriptions` 订阅
- `POST /api/v1/billing/usage` 记录用量 (idempotency_key)
- `GET /api/v1/billing/usage/{tenant}?period=YYYY-MM` 用量查询
- `POST /api/v1/billing/invoices/generate` 生成发票
- `POST /api/v1/billing/invoices/{id}/pay` 支付
- `GET /api/v1/billing/forecast?tenant=X` 预测
- `POST /api/v1/billing/experiments` 价格 A/B 实验

**工作量**: 2 工程师 × 3 周

---

## 第 20 章 A/B 测试与实验平台设计 (vs Eppo/Statsig/LaunchDarkly)

### 20.1 智影当前状态

智影**没有 A/B 测试能力**,只有 capability 的固定行为。

### 20.2 顶级 A/B 实验平台对比

| 功能 | Eppo | Statsig | LaunchDarkly | Optimizely | Split.io | 智影 (扩展) |
|---|---|---|---|---|---|---|
| **Feature Flag** | ✅ | ✅ 强 | ✅ 业界领先 | ✅ | ✅ | 设计 |
| **A/B 实验 (统计显著)** | ✅ 业界领先 | ✅ 强 | ⚠️ | ✅ 强 | ✅ | 设计 |
| **多变量测试 (MVT)** | ✅ | ✅ | ⚠️ | ✅ | ✅ | 设计 |
| **分层实验 (Layered)** | ✅ | ✅ 强 | ⚠️ | ✅ | ✅ | 设计 |
| **贝叶斯 / 频率派** | ✅ 贝叶斯 | ✅ 两种 | N/A | ✅ | ✅ | 设计 (贝叶斯) |
| **Allocation 流量分桶** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 (哈希分桶) |
| **Mutual Exclusion (互斥)** | ✅ | ✅ | ⚠️ | ✅ | ✅ | 设计 |
| **Holdout (对照组)** | ✅ | ✅ | ⚠️ | ✅ | ✅ | 设计 |
| **Metrics 集成** | ✅ | ✅ 强 | ⚠️ | ✅ | ✅ | 设计 |
| **统计显著性 (p-value, CI)** | ✅ 强 | ✅ 强 | N/A | ✅ | ✅ | 设计 (scipy) |
| **Sequential Testing** | ✅ | ✅ | N/A | ✅ | ✅ | 设计 (mSPRT) |
| **CUPED 方差缩减** | ✅ | ✅ | N/A | ✅ | ⚠️ | 设计 |
| **CUPED + 贝叶斯** | ✅ | ✅ | N/A | ⚠️ | ⚠️ | 设计 |
| **结果可视化** | ✅ 强 | ✅ 强 | ⚠️ | ✅ | ✅ | 设计 (ECharts) |
| **Alerting** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **A/B/n + 灰度发布** | ✅ | ✅ | ✅ 强 | ✅ | ✅ | 设计 |
| **Feature Experimentation** | ✅ | ✅ 强 | ✅ 强 | ✅ | ✅ | 设计 |

### 20.3 智影 A/B 实验设计

```python
# experiments/experiment_engine.py
class Experiment(Base):
    __tablename__ = "experiments"
    id: str  # exp_<12-hex>
    name: str
    hypothesis: str
    primary_metric: str
    secondary_metrics: List[str]
    variants: List[Variant]  # control / treatment_a / treatment_b
    allocation: float  # 0.0-1.0
    layer: str  # experiment layer
    started_at: datetime
    ended_at: Optional[datetime]
    status: Literal["draft", "running", "stopped", "won", "lost"]
    owner: str
    tags: List[str]

class Variant(BaseModel):
    name: str
    weight: float  # 0.0-1.0
    payload: dict  # 任意 JSON 配置

class ExperimentAssignment(Base):
    __tablename__ = "experiment_assignments"
    experiment_id: str
    subject_key: str  # user / session
    variant: str
    assigned_at: datetime

class ExperimentEvent(Base):
    __tablename__ = "experiment_events"
    experiment_id: str
    variant: str
    subject_key: str
    metric: str
    value: float
    timestamp: datetime
```

**API**:
- `POST /api/v1/experiments` 创建
- `POST /api/v1/experiments/{id}/start` 启动
- `GET /api/v1/experiments/{id}/assignments?subject=X` 获取分配
- `POST /api/v1/experiments/{id}/events` 记录事件
- `GET /api/v1/experiments/{id}/results?metrics=...` 实时结果
- `GET /api/v1/experiments/{id}/analysis` 统计显著性分析 (贝叶斯 + 频率派 + CUPED + Sequential)

**工作量**: 2 工程师 × 2 周

---

## 第 21 章 文档协作与知识库设计 (vs Notion/Confluence/Obsidian)

### 21.1 智影当前状态

智影有 `obsidian/` 路由 (KnowledgeGraph / WikiList / WikiEdit),但功能浅。

### 21.2 顶级文档协作平台对比

| 功能 | Notion | Confluence | Obsidian | Coda | Slab | 智影 (扩展) |
|---|---|---|---|---|---|---|
| **Block-based 编辑** | ✅ 业界领先 | ⚠️ | ✅ | ✅ | ✅ | 设计 |
| **Slash Command** | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | 设计 |
| **双向链接** | ⚠️ | ❌ | ✅ 强 | ⚠️ | ⚠️ | 设计 |
| **Graph View** | ⚠️ | ❌ | ✅ 强 | ⚠️ | ⚠️ | 设计 |
| **嵌入式数据库** | ✅ 强 | ⚠️ | ❌ | ✅ | ⚠️ | 设计 |
| **模板系统** | ✅ 强 | ✅ | ⚠️ | ✅ 强 | ✅ | 设计 |
| **权限 (细粒度)** | ✅ 强 | ✅ 强 | ❌ | ✅ | ✅ 强 | 设计 (继承 RBAC) |
| **版本历史** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **评论 + Mention** | ✅ 强 | ✅ 强 | ⚠️ | ✅ | ✅ | 设计 |
| **Markdown 兼容** | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | 设计 |
| **Export (PDF/MD/HTML)** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **AI 助手** | ✅ 业界领先 | ⚠️ | ⚠️ | ✅ | ⚠️ | 设计 (集成 multimodal_agent) |
| **实时协作 (多人)** | ✅ 强 | ✅ 强 | ❌ | ✅ | ✅ | 设计 (CRDT) |
| **API / 集成** | ✅ 强 | ✅ 强 | ⚠️ | ✅ | ⚠️ | 设计 |
| **权限 Inheritance** | ✅ | ✅ | ❌ | ✅ | ✅ | 设计 |

### 21.3 智影文档设计

```python
# knowledge/wiki_engine.py
class WikiPage(Base):
    __tablename__ = "wiki_pages"
    id: str  # wiki_<12-hex>
    title: str
    slug: str  # url-friendly
    content_md: str  # Markdown 原文
    content_json: dict  # 块结构 (block-based)
    parent_id: Optional[str]
    project_id: Optional[str]
    owner: str
    tags: List[str]
    permissions: dict  # RBAC 继承
    created_at: datetime
    updated_at: datetime
    version: int

class WikiLink(Base):
    __tablename__ = "wiki_links"
    from_page_id: str
    to_page_id: str
    context: str  # 链接周围文本

class WikiComment(Base):
    __tablename__ = "wiki_comments"
    page_id: str
    content: str
    author: str
    parent_id: Optional[str]
    resolved: bool
    created_at: datetime
```

**工作量**: 2 工程师 × 3 周 (block editor + CRDT 是大头)

---

## 第 22 章 通知与协作设计 (vs Slack/Teams/Lark/Mailgun)

### 22.1 智影当前状态

智影 `notification_service` (P3-2 拆分目标) 雏形,当前 in-process 弹窗。

### 22.2 顶级通知/协作平台对比

| 功能 | Slack | Microsoft Teams | Lark/飞书 | Mailgun | SendGrid | 智影 (扩展) |
|---|---|---|---|---|---|---|
| **即时消息** | ✅ 业界领先 | ✅ | ✅ | N/A | N/A | 设计 |
| **频道 (Channel)** | ✅ | ✅ | ✅ | N/A | N/A | 设计 |
| **DM / 群聊** | ✅ | ✅ | ✅ | N/A | N/A | 设计 |
| **文件共享** | ✅ | ✅ | ✅ | N/A | N/A | 设计 |
| **视频会议** | ✅ | ✅ | ✅ | N/A | N/A | 不做 |
| **Webhook 集成** | ✅ 强 | ✅ | ✅ | N/A | N/A | 设计 |
| **Bot / App** | ✅ 强 | ✅ | ✅ | N/A | N/A | 设计 (智影 Agent) |
| **Email 投递** | ⚠️ | ⚠️ | ⚠️ | ✅ 业界领先 | ✅ | 设计 (Mailgun 集成) |
| **Email 模板** | ⚠️ | ⚠️ | ⚠️ | ✅ | ✅ | 设计 |
| **Open Rate / Click Rate** | N/A | N/A | N/A | ✅ | ✅ | 设计 |
| **Bounce / Complaint** | N/A | N/A | N/A | ✅ | ✅ | 设计 |
| **A/B Email** | N/A | N/A | N/A | ✅ | ✅ | 设计 |
| **DMARC / DKIM / SPF** | N/A | N/A | N/A | ✅ | ✅ | 设计 |
| **SMS (Twilio)** | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ | 设计 (Twilio 集成) |
| **Push (Web/Mobile)** | ✅ | ✅ | ✅ | N/A | N/A | 设计 (Web Push) |
| **Alerting (PagerDuty)** | ✅ | ✅ | ✅ | N/A | N/A | 设计 (集成 PagerDuty) |

### 22.3 智影通知设计

```python
# notification/notification_engine.py
class NotificationChannel(Base):
    __tablename__ = "notification_channels"
    id: str
    tenant_id: str
    channel_type: Literal["email", "sms", "push", "slack", "lark", "teams", "webhook", "in_app"]
    config: dict  # {email: "...", webhook_url: "...", ...}
    enabled: bool
    created_at: datetime

class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    id: str
    name: str  # "qc_failed" / "delivery_ready" / "share_accessed"
    channel_type: str
    subject: str  # email 用
    body_md: str  # Markdown 模板,支持 {{ variable }}
    variables: List[str]
    locale: str  # i18n

class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id: str
    channel_id: str
    template_id: str
    recipient: str
    payload: dict
    status: Literal["queued", "sent", "delivered", "failed", "bounced"]
    sent_at: Optional[datetime]
    delivered_at: Optional[datetime]
    opened_at: Optional[datetime]
    clicked_at: Optional[datetime]
    error: Optional[str]
```

**Event 触发**:
- 智影内部 EventBus 上 `qc.failed` / `delivery.ready` / `share.accessed` 等事件触发通知
- 集成: Mailgun (email) / Twilio (SMS) / Slack (webhook) / Lark (webhook) / PagerDuty (alerting)

**工作量**: 1 工程师 × 1 周

---

## 第 23 章 高级 AI Provider 功能 (Circuit Breaker/智能 Fallback/Cost Guard)

### 23.1 智影当前能力

智影的 `providers/registry.py`:
- ✅ 7 LLM + 路由 (cost/speed/trust)
- ✅ 4 多模态生成器
- ✅ record_call (cost 记录)
- ❌ 自动 Fallback (manual `exclude`)
- ❌ Circuit Breaker
- ❌ 语义缓存
- ❌ Cost Budget (超预算熔断)
- ❌ Streaming Response

### 23.2 顶级 AI Gateway 对比 (Portkey / LiteLLM / Helicone)

| 功能 | Portkey | LiteLLM | Helicone | OpenRouter | Bifrost | Cloudflare AI Gateway | 智影 (扩展) |
|---|---|---|---|---|---|---|---|
| **Fallback Chain** | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | 设计 |
| **Circuit Breaker** | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | ✅ | 设计 |
| **语义缓存** | ✅ | ✅ | ✅ 强 | ⚠️ | ✅ | ✅ | 设计 |
| **Cost Budget Alert** | ✅ | ⚠️ | ✅ | ⚠️ | ✅ | ✅ | 设计 |
| **Streaming (SSE)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **Rate Limit (per-tenant)** | ✅ 强 | ✅ | ⚠️ | ⚠️ | ✅ | ✅ 强 | 设计 |
| **Guardrails** | ✅ | ✅ | ⚠️ | ❌ | ✅ | ⚠️ | 设计 |
| **Prompt Version** | ✅ | ⚠️ | ⚠️ | ❌ | ✅ | ❌ | 设计 |
| **A/B Test Prompts** | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ | ❌ | 设计 |
| **Fine-tuning** | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ | ❌ | 设计 |
| **Virtual Key (per-team)** | ✅ | ✅ | ✅ | ⚠️ | ✅ | ✅ | 设计 |
| **Load Balancing** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **On-prem** | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | 设计 (✅) |
| **Open Source** | ⚠️ | ✅ | ❌ | ❌ | ✅ | ❌ | ✅ |

### 23.3 智影 AI Gateway 增强设计

```python
# providers/gateway.py
class AIGateway:
    """智影 AI Gateway - 统一 LLM/多模态调用入口"""
    
    def __init__(self, registry, cache, breaker, cost_guard):
        self.registry = registry  # ProviderRegistry
        self.cache = cache        # SemanticCache
        self.breaker = breaker    # CircuitBreaker
        self.cost_guard = cost_guard  # CostGuard
    
    async def invoke(
        self,
        family: str,
        prompt: str,
        *,
        prefer: Literal["cost", "speed", "trust", "balanced"] = "balanced",
        cache: bool = True,
        max_cost_cents: Optional[int] = None,
        tenant_id: Optional[str] = None,
        stream: bool = False,
        **kwargs,
    ) -> AIResponse:
        # 1. Cost Guard 检查
        if max_cost_cents and self.cost_guard.would_exceed(tenant_id, max_cost_cents):
            raise CostLimitExceeded(tenant_id=tenant_id)
        
        # 2. Circuit Breaker 检查
        if self.breaker.is_open(family):
            # 自动 fallback 到另一 provider
            family = self.breaker.get_fallback(family)
        
        # 3. 语义缓存查找
        if cache:
            hit = self.cache.lookup(prompt)
            if hit:
                return AIResponse(**hit, cached=True)
        
        # 4. 路由 + 调用
        provider = self.registry.route(family, prefer=prefer)
        try:
            response = await provider.invoke(prompt, stream=stream, **kwargs)
        except Exception as e:
            # 5. Fallback chain
            for fallback in self.registry.get_fallbacks(family, exclude=[provider.id]):
                try:
                    response = await fallback.invoke(prompt, stream=stream, **kwargs)
                    self.breaker.record_success(fallback.family)
                    break
                except Exception:
                    self.breaker.record_failure(fallback.family)
                    continue
            else:
                self.breaker.record_failure(family)
                raise
        
        # 6. 写缓存
        if cache:
            self.cache.store(prompt, response)
        
        # 7. 记录 + 成本
        self.registry.record_call(provider.id, model=kwargs.get("model"), input_tokens=..., output_tokens=..., latency_ms=..., status="ok")
        self.cost_guard.record(tenant_id, cost_cents=response.cost_cents)
        
        return response
```

**工作量**: 2 工程师 × 2 周

---

## 第 24 章 数据合同 (Data Contract) 与 Schema Registry

### 24.1 智影当前状态

智影的 ORM 表定义是硬编码的,没有 Schema Registry,无法:
- 在数据集/资产层定义 schema (列 + 类型 + 约束)
- 强制 Producer/Consumer 之间的契约
- Schema 演进追踪

### 24.2 顶级 Schema Registry 对比

| 功能 | Confluent Schema Registry | Apicurio | Karapace | 智影 (扩展) |
|---|---|---|---|---|
| **Schema 版本管理** | ✅ 强 | ✅ | ✅ | 设计 |
| **Avro / Protobuf / JSON Schema** | ✅ | ✅ | ✅ | 设计 (JSON Schema) |
| **兼容性检查 (Back/Forward/Full)** | ✅ 强 | ✅ | ✅ | 设计 |
| **Producer/Consumer 契约** | ✅ 强 | ✅ | ✅ | 设计 |
| **REST API** | ✅ | ✅ | ✅ | 设计 |
| **Schema 演化** | ✅ | ✅ | ✅ | 设计 |
| **多语言 SDK** | ✅ 20+ | ✅ | ✅ | 设计 (Python) |
| **CI/CD 集成** | ✅ | ✅ | ✅ | 设计 |
| **跨 Cluster 复制** | ✅ | ⚠️ | ⚠️ | 设计 |
| **数据质量集成** | ⚠️ | ⚠️ | ⚠️ | 设计 (集成 InternalQC) |
| **与 Catalog 集成** | ⚠️ | ✅ | ⚠️ | 设计 (集成 Catalog) |
| **Open Source** | ⚠️ (Confluent) | ✅ | ✅ | ✅ |

### 24.3 智影 Schema Registry 设计

```python
# models/schema_registry.py
class Schema(Base):
    __tablename__ = "schemas"
    id: str  # schema_<12-hex>
    subject: str  # "datasets.coco.images" 类似
    version: int
    schema_json: dict  # JSON Schema
    compatibility: Literal["backward", "forward", "full", "none"]
    created_at: datetime
    created_by: str
    description: str

class SchemaCompatibility(Base):
    __tablename__ = "schema_compatibility_checks"
    from_version: int
    to_version: int
    is_compatible: bool
    breaking_changes: List[dict]
    checked_at: datetime

class SchemaAttachment(Base):
    __tablename__ = "schema_attachments"
    schema_id: str
    resource_type: str  # "dataset" / "pack" / "asset"
    resource_id: str
```

**API**:
- `POST /api/v1/schemas` 注册 schema
- `GET /api/v1/schemas/{subject}/versions` 列出版本
- `POST /api/v1/schemas/{subject}/compatibility-check` 检查兼容性
- `POST /api/v1/schemas/attach` 附加到资源

**工作量**: 1 工程师 × 2 周

---

## 第 25 章 高级血缘 (跨组织数据共享 / OpenLineage)

### 25.1 智影当前能力

- 14 条 RELATION_GRAPH 边
- EventBus 自动记录
- DataFlowTracker

### 25.2 OpenLineage 标准

OpenLineage 是 Linux Foundation 下的数据血缘标准,被 Airflow/Spark/Databricks/Snowflake 广泛支持。

**核心概念**:
- **Run**: 一次 Job 执行
- **Job**: 任务定义
- **Dataset**: 输入/输出数据集
- **Event**: START / COMPLETE / FAIL / OTHER

### 25.3 智影 OpenLineage 适配器设计

```python
# orchestration/openlineage_adapter.py
class OpenLineageAdapter:
    """把智影 EventBus 事件转换为 OpenLineage 标准"""
    
    def emit_start(self, run: WorkflowRun):
        event = {
            "eventType": "START",
            "eventTime": run.started_at.isoformat(),
            "run": {"runId": run.id, "facets": {...}},
            "job": {"namespace": "imdf", "name": run.workflow_id},
            "inputs": [...],  # 智影 assets
            "outputs": [...],  # 智影 assets
            "producer": "imdf.ai/0.9.0",
        }
        # 发送到 OpenLineage backend (Marquez / DataHub / ...)
        self.transport.emit(event)
```

**事件流**:
- `capability.invoke_start` → OL START
- `capability.invoke_complete` → OL COMPLETE
- `capability.invoke_fail` → OL FAIL
- 转换 `inputs`/`outputs` 到 OL Dataset

**双向兼容**:
- 智影消费外部 OL 事件 (Airflow/Spark/dbt) → 写到 EventBus
- 智影 emit 事件到外部 OL backend

**工作量**: 1 工程师 × 2 周

---

## 第 26 章 模型监控与漂移检测 (vs Evidently/Whylabs/Arize)

### 26.1 智影当前状态

智影**没有模型监控**,无法:
- 检测训练-服务 skew
- 检测数据漂移 (data drift)
- 检测目标漂移 (target drift)
- 检测概念漂移 (concept drift)
- 监控模型性能衰减

### 26.2 顶级模型监控平台对比

| 功能 | Evidently | Whylabs | Arize | Fiddler | Superwise | Mona | 智影 (扩展) |
|---|---|---|---|---|---|---|---|
| **Data Drift** | ✅ 强 | ✅ 强 | ✅ 强 | ✅ | ✅ | ✅ | 设计 |
| **Target Drift** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **Concept Drift** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **Model Performance** | ✅ | ✅ | ✅ 业界领先 | ✅ 强 | ✅ | ✅ | 设计 |
| **Prediction Drift** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **Bias / Fairness** | ✅ | ✅ | ✅ 强 | ✅ | ✅ | ⚠️ | 设计 |
| **Explainability (SHAP/LIME)** | ✅ | ⚠️ | ✅ | ✅ 业界领先 | ✅ | ⚠️ | 设计 |
| **Data Quality + Drift** | ✅ 业界领先 | ✅ | ✅ | ✅ | ✅ | ⚠️ | 设计 (集成 QC) |
| **LLM Monitoring** | ✅ (2024+) | ✅ | ✅ | ⚠️ | ✅ | ✅ | 设计 |
| **Real-time** | ✅ | ✅ 强 | ✅ 强 | ✅ | ✅ 强 | ✅ 强 | 设计 |
| **Alerting** | ✅ | ✅ 强 | ✅ | ✅ | ✅ | ✅ | 设计 |
| **Dashboard** | ✅ 强 | ✅ 强 | ✅ 强 | ✅ | ✅ | ✅ | 设计 |
| **Open Source** | ✅ | ⚠️ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Self-host** | ✅ | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ | 设计 (✅) |

### 26.3 智影模型监控设计

```python
# monitoring/model_monitor.py
class ModelMonitor(Base):
    __tablename__ = "model_monitors"
    id: str
    model_id: str  # 关联 Model Registry
    name: str
    description: str
    reference_dataset_id: str  # 训练集 (基线)
    current_dataset_id: str  # 当前生产数据
    drift_config: dict  # {data: {p_value: 0.05}, target: {...}, concept: {...}}
    metrics: List[str]  # accuracy / f1 / mae / ...
    alert_thresholds: dict
    enabled: bool
    created_at: datetime

class DriftReport(Base):
    __tablename__ = "drift_reports"
    id: str
    monitor_id: str
    timestamp: datetime
    data_drift_score: float
    target_drift_score: float
    concept_drift_score: float
    feature_drift: dict  # 每个特征 p-value + drift type
    predictions_drift: dict
    alerts: List[str]
```

**集成 Evidently AI**:
```python
# 推荐: 集成 Evidently 而不是自实现
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset, TargetDriftPreset

def generate_drift_report(reference_data, current_data, model_id):
    report = Report(metrics=[DataDriftPreset(), TargetDriftPreset()])
    report.run(reference_data=reference_data, current_data=current_data)
    return report
```

**工作量**: 1 工程师 × 1 周 (集成 Evidently)

---

## 第 27 章 Prompt 工程与评估平台 (vs LangSmith/Helicone/PromptLayer)

### 27.1 智影当前状态

智影的 prompt 是硬编码在能力中的字符串,没有:
- Prompt 模板版本管理
- Prompt 评估
- Few-shot 学习支持
- A/B 测试

### 27.2 顶级 Prompt 平台对比

| 功能 | LangSmith | Helicone | PromptLayer | Langfuse | Pezzo | 智影 (扩展) |
|---|---|---|---|---|---|---|
| **Prompt 版本** | ✅ 强 | ✅ | ✅ 强 | ✅ 强 | ✅ | 设计 |
| **Prompt 模板 (变量替换)** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **Few-shot 管理** | ✅ | ⚠️ | ✅ | ✅ | ✅ | 设计 |
| **Prompt Eval** | ✅ 强 | ⚠️ | ✅ | ✅ | ✅ | 设计 |
| **A/B Test Prompts** | ✅ | ⚠️ | ✅ | ✅ | ✅ | 设计 |
| **Trace (token + cost + latency)** | ✅ 业界领先 | ✅ 强 | ✅ | ✅ 强 | ✅ | 设计 (集成 OTel) |
| **Dataset 管理** | ✅ 强 | ⚠️ | ✅ | ✅ | ✅ | 设计 (集成 Datasets) |
| **Human Feedback (评分)** | ✅ | ⚠️ | ✅ | ✅ | ✅ | 设计 |
| **Auto Eval (LLM-as-judge)** | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | 设计 |
| **Open Source** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Self-host** | ❌ | ❌ | ❌ | ✅ | ✅ | 设计 (✅) |
| **与 LangChain 集成** | ✅ | ✅ | ✅ | ✅ | ⚠️ | 设计 |

### 27.3 智影 Prompt 平台设计

```python
# prompts/prompt_registry.py
class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    id: str  # ptmpl_<12-hex>
    name: str
    description: str
    current_version: int
    created_at: datetime
    owner: str
    tags: List[str]

class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id: str
    template_id: str
    version: int
    content: str  # 含 {{variable}} 占位符
    variables: List[str]
    model: str  # 目标模型
    temperature: float
    max_tokens: int
    few_shot_examples: List[dict]
    parent_version: Optional[int]
    commit_message: str
    created_at: datetime
    created_by: str

class PromptEval(Base):
    __tablename__ = "prompt_evals"
    id: str
    prompt_version_id: str
    dataset_id: str  # 测试集
    metrics: List[str]  # accuracy / bleu / llm_judge
    scores: dict
    results: List[dict]
    judge_model: Optional[str]  # LLM-as-judge 用
    created_at: datetime
```

**Eval 方法**:
- 规则匹配 (正则、关键词)
- LLM-as-judge (GPT-4 评分 1-5)
- Human feedback (标注员打分)
- BLEU/ROUGE (与参考答案对比)
- Cost / Latency 指标

**工作量**: 2 工程师 × 2 周

---

## 第 28 章 客户数据平台 (CDP) 与用户画像

### 28.1 智影当前状态

智影 `auth_routes.users_db` 是 in-memory + DB,但缺:
- 跨域用户统一识别
- 用户行为追踪
- 用户画像
- 群组分群
- 营销自动化

### 28.2 顶级 CDP 对比

| 功能 | Segment | mParticle | Twilio Engage | RudderStack | Snowplow | 智影 (扩展) |
|---|---|---|---|---|---|---|
| **跨域识别 (ID stitching)** | ✅ 强 | ✅ 强 | ✅ | ✅ 开源 | ✅ 开源 | 设计 |
| **Event 收集 (SDK)** | ✅ 多端 | ✅ | ✅ | ✅ | ✅ | 设计 (集成 EventBus) |
| **Real-time Pipeline** | ✅ | ✅ 强 | ✅ | ✅ | ✅ 强 | 设计 |
| **用户档案 (Profile)** | ✅ 强 | ✅ 强 | ✅ | ✅ | ✅ | 设计 |
| **行为分群 (Segment)** | ✅ 强 | ✅ | ✅ | ✅ | ✅ | 设计 |
| **身份合并 (Identity Resolution)** | ✅ | ✅ 强 | ✅ | ✅ | ✅ | 设计 |
| **预测分群 (AI)** | ✅ | ✅ | ✅ | ⚠️ | ✅ | 设计 |
| **Destination (100+)** | ✅ 强 | ✅ 强 | ✅ | ✅ 强 | ✅ 强 | 设计 (Webhook) |
| **数据治理 (Consent)** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **GDPR / CCPA** | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 (继承 PII) |
| **Open Source** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |

### 28.3 智影 CDP 设计

```python
# cdp/identity_engine.py
class Identity(Base):
    __tablename__ = "user_identities"
    user_id: str  # 智影主 ID
    anonymous_id: str  # 匿名 ID (cookie / device)
    channel: str  # "web" / "ios" / "api" / "agent"
    merged_at: datetime
    traits: dict  # {email, phone, name, ...}

class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id: str
    traits: dict  # 静态属性
    computed_traits: dict  # 计算属性 (lifetime_value, last_active, ...)
    segments: List[str]
    last_event_at: datetime
    created_at: datetime

class UserSegment(Base):
    __tablename__ = "user_segments"
    id: str
    name: str
    definition: dict  # SQL-like: {event: "page_viewed", filter: {path: "/admin"}}
    computed_user_ids: List[str]
    computed_at: datetime
    sync_to: List[str]  # destination IDs
```

**工作量**: 2 工程师 × 3 周

---

## 第 29 章 项目管理深化 (vs Linear/Jira/Asana/ClickUp)

### 29.1 智影当前状态

智影的 `projects` 表 + `project_members` + `project_timeline_events`,但功能浅,主要是项目元数据。

### 29.2 顶级 PM 平台对比

| 功能 | Linear | Jira | Asana | ClickUp | Monday.com | Trello | Notion | 智影 (扩展) |
|---|---|---|---|---|---|---|---|---|
| **Issue / Task** | ✅ 业界领先 | ✅ 强 | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **Subtask / Sub-issue** | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ | 设计 |
| **Roadmap (时间轴)** | ✅ 强 | ✅ | ✅ | ✅ 强 | ✅ 强 | ⚠️ | ✅ | 设计 |
| **Sprint / Iteration** | ✅ | ✅ 强 | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | 设计 |
| **Backlog 排序** | ✅ 业界领先 | ✅ | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | 设计 |
| **Triage (智能分诊)** | ✅ 业界领先 | ⚠️ | ❌ | ⚠️ | ❌ | ❌ | ❌ | 设计 (AI) |
| **Cycle (Sprint 报告)** | ✅ 强 | ✅ | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | 设计 |
| **Custom Workflow** | ✅ | ✅ 强 | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | 设计 |
| **Automation** | ✅ | ✅ 强 | ✅ | ✅ 强 | ✅ | ⚠️ | ⚠️ | 设计 |
| **Integrations (100+)** | ✅ 强 | ✅ 业界领先 | ✅ | ✅ | ✅ | ✅ | ✅ | 设计 |
| **GitHub 集成** | ✅ 业界领先 | ✅ 强 | ⚠️ | ✅ | ⚠️ | ⚠️ | ⚠️ | 设计 |
| **Slack 集成** | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | 设计 |
| **Roadmap Gantt** | ✅ | ✅ | ✅ | ✅ 强 | ✅ 强 | ⚠️ | ⚠️ | 设计 |
| **时间追踪** | ⚠️ | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ | ⚠️ | 设计 |
| **依赖 (Blocking)** | ✅ 强 | ✅ 强 | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | 设计 |
| **风险/阻碍报告** | ✅ | ⚠️ | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | 设计 |
| **AI 辅助** | ✅ (Linear Asks) | ✅ (Atlassian AI) | ⚠️ | ✅ | ⚠️ | ❌ | ✅ | 设计 (集成 multimodal_agent) |

### 29.3 智影项目管理设计

```python
# project_management/issues.py
class Issue(Base):
    __tablename__ = "issues"
    id: str  # ISS_<8-hex>
    project_id: str
    title: str
    description_md: str
    type: Literal["epic", "story", "task", "bug", "subtask"]
    status: Literal["backlog", "todo", "in_progress", "in_review", "done", "canceled"]
    priority: Literal["P0", "P1", "P2", "P3"]
    assignee: Optional[str]
    reporter: str
    labels: List[str]
    parent_issue_id: Optional[str]  # 用于 Subtask
    sprint_id: Optional[str]
    estimate: Optional[float]  # story points / hours
    due_date: Optional[datetime]
    blocked_by: List[str]  # 依赖的 issue IDs
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime]

class Sprint(Base):
    __tablename__ = "sprints"
    id: str
    project_id: str
    name: str
    goal: str
    start_at: datetime
    end_at: datetime
    status: Literal["planned", "active", "completed"]

class Roadmap(Base):
    __tablename__ = "roadmaps"
    id: str
    project_id: str
    name: str
    start_date: date
    end_date: date
    milestones: List[dict]  # [{date, title, issue_ids: []}]
```

**API**:
- CRUD issue / sprint / roadmap
- 拖拽排序 (backlog priority)
- 状态机 (workflow)
- 依赖 (blocked_by)
- 自动化 (issue 状态变化时触发 webhook / workflow)
- AI 辅助: 智能分诊、相似 issue 检测、自动生成描述

**工作量**: 2 工程师 × 3 周

---

## 第 30 章 总结:扩展后的智影平台全景

### 30.1 扩展后智影架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Frontend (Vue 3 SPA, PWA)                       │
│  35+ 视图 + 7 组件 + Command Palette + AI 助手 + 实时协作          │
└─────────────────────────────────────────────────────────────────────┘
                                  ↕ HTTPS/JWT/SSO+MFA
┌─────────────────────────────────────────────────────────────────────┐
│              API Gateway (FastAPI + AI Gateway + SSO)               │
│  260+ 业务 routes + 9 security + 5 deploy_r7 + 12 monitoring        │
│  + AI Gateway (7 LLM + Fallback + Circuit Breaker + 语义缓存)       │
└─────────────────────────────────────────────────────────────────────┘
                                  ↕
┌────────────────── 12 微服务 (P3-2 完整化) ─────────────────────────┐
│  user / asset / annotation / dataset / workflow / agent /         │
│  collection / cleaning / scoring / evaluation / search / billing   │
│  + 12 新增: feature_store / experiment / mlops / monitor /         │
│             cdp / notification / schema_registry / ...             │
└─────────────────────────────────────────────────────────────────────┘
                                  ↕
┌────────────────── 7 层数据 + 治理 ──────────────────────────────────┐
│  ① ORM (14+ 表)     ② Schema Registry (JSON Schema)               │
│  ③ PackStore (SQLite) ④ SemanticAssets (HNSW + BM25 + pgvector)   │
│  ⑤ Dataset Versioning (DVC 风格)  ⑥ Feature Store (Feast 风格)     │
│  ⑦ Model Registry (MLflow 风格)                                    │
│  + Catalog (三层命名空间) + DataFlow (OpenLineage 兼容)            │
└─────────────────────────────────────────────────────────────────────┘
                                  ↕
┌────────────────── 8 大引擎层 ─────────────────────────────────────┐
│  Project / Requirement / Pack / Workbench / QC / Acceptance /      │
│  Delivery / Transfer + AI Provider + Agent (5 工具 + Memory + MCP) │
│  + Experiment Engine (A/B) + Model Serving (BentoML)                │
└─────────────────────────────────────────────────────────────────────┘
                                  ↕
┌────────────────── 智能 / RAG / 评估栈 ─────────────────────────────┐
│  MultimodalRAG (HNSW + pgvector + 1024-d + Hybrid)                 │
│  MultimodalAgent (5 工具 + Memory + Streaming + A2A + Browser Use) │
│  Prompt Registry + Eval (LLM-as-judge + Human)                     │
│  Model Monitor (Drift Detection via Evidently)                      │
└─────────────────────────────────────────────────────────────────────┘
                                  ↕
┌────────────────── 调度 + 工作流 + 自动化 ──────────────────────────┐
│  SchedulerEngine (APScheduler cron) + TaskQueue (Celery async)    │
│  WorkflowBuilder (DAG + 6 模板 + 47 节点 + Cron/Event trigger)    │
│  Experiment Engine (A/B Test + Bayesian + Sequential + CUPED)      │
│  Webhooks (出站) + Automation (Trigger → Action)                   │
└─────────────────────────────────────────────────────────────────────┘
                                  ↕
┌────────────────── 可观测性 (7 层) ──────────────────────────────────┐
│  Prometheus Metrics + Loki Logs + OTel/Jaeger Trace +              │
│  Sentry-style Errors + RUM (前端) + Synthetic + SLO/SLI +            │
│  Alertmanager + Continuous Profiling (Pyroscope)                    │
└─────────────────────────────────────────────────────────────────────┘
                                  ↕
┌────────────────── 协作 / 通知 / 计费 ──────────────────────────────┐
│  Notification (Email/SMS/Slack/Lark/Webhook/Push)                  │
│  Documentation (Notion 风格, Block-based + AI)                      │
│  Billing (Subscription + Usage + Invoice + Stripe/支付宝)          │
│  Project Management (Linear 风格, Issue + Sprint + Roadmap)        │
│  Customer Data Platform (Segment 风格, Identity + Profile + Segment)│
└─────────────────────────────────────────────────────────────────────┘
                                  ↕
┌────────────────── 安全 / 合规 / 治理 ──────────────────────────────┐
│  Vault (密钥管理) + SSO (SAML/OIDC) + MFA + ABAC + PII 脱敏 +      │
│  Rate Limit + AuditChain (HMAC) + SCA (Snyk) + GDPR/AI Act 报告   │
└─────────────────────────────────────────────────────────────────────┘
```

### 30.2 扩展后智影定位

**从"工业级数据生产平台"升级为"AI 时代全栈数据基础设施"**:

- 不仅是数据生产 (9 阶段)
- 包含数据治理 (Catalog + Schema + Lineage + Quality)
- 包含 MLOps (Registry + Serving + Monitor + Feature Store)
- 包含 AI Gateway (Fallback + Cache + Cost Guard)
- 包含 Agent 平台 (Memory + MCP + A2A + Tool Marketplace)
- 包含协作 (Notion + Linear + Slack 风格)
- 包含计费 (Stripe 风格)
- 包含可观测 (7 层全栈)

### 30.3 扩展后市场规模

| 阶段 | 智影 | 智影 V2 (扩展) |
|---|---|---|
| **TAM 估计** | $50B (数据标注 + 数据管理) | $500B (AI 全栈基础设施) |
| **核心场景** | 数据生产 | AI 项目全生命周期 |
| **目标客户** | 标注团队 / 数据团队 | AI 公司 / 企业 AI 部门 / MLOps 团队 / Agent 开发 |
| **差异化** | 端到端 + 真引擎 + 跨进程 | + 完整生态 (Catalog/MLOps/Agent/Obs) + AI 治理 |

### 30.4 实施路线图 (12 个月)

| 季度 | 工作量 | 重点 |
|---|---|---|
| **2026 Q3** | 30 周 | P1 最高 ROI: AI 辅助标注 + Model Registry + 三层 Catalog + HNSW + 异步执行 + SSO/MFA + Command Palette |
| **2026 Q4** | 30 周 | P1 中: Feature Store + Drift Detection + 列级血缘 + OpenLineage + Prompt Registry + Experiment A/B + 高级计费 |
| **2027 Q1** | 30 周 | P1 末: LiDAR + 文档协作 + A2A + K8s + 通知 + Schema Registry + AI 助手 |
| **2027 Q2** | 30 周 | P2: 多 Agent 协作 + 跨组织 lineage + CDP + 项目管理深化 |

**总投入**: ~120 工程师-周 (按 5 人团队 24 周 = 6 个月达 P1 完毕, 12 个月达 P1+P2)

### 30.5 量化收益预期

- **标注效率**: AI 辅助标注 5-10× → 人力成本 -50% 到 -80%
- **ML 训练**: Feature Store + Model Registry → 训练-服务 skew -90%
- **RAG 质量**: HNSW + 混合检索 + 1024-d → 检索准确度 +20% 到 +50%
- **AI 治理**: AuditChain + 完整 Lineage → 合规成本 -70%
- **运营成本**: Loki + Alertmanager + Auto-Fallback → 故障恢复时间 -60%
- **商业化**: Stripe 风格计费 + Self-service Portal → 客户自助开通 +200%

### 30.6 关键风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 工作量超出预期 (120 周) | 中 | 高 | 分阶段交付, 每 2 周 sprint review |
| 性能回退 (新功能影响性能) | 中 | 中 | 性能基准测试 1000 ops + Prometheus SLO 监控 |
| 数据安全 (新模块引入漏洞) | 中 | 极高 | 强制 code review + SCA 扫描 + 渗透测试 |
| 用户接受度 (UI 大改) | 低 | 中 | 渐进式 UI 改进 + 保留旧入口 + 用户培训 |
| 竞争加剧 (新玩家) | 中 | 中 | 差异化: 端到端 + 真引擎 + 跨 DB + 跨进程持久 |

### 30.7 总结

智影 V2 完成后,将:
1. **从数据生产平台升级为 AI 全栈基础设施** — 涵盖数据生产 + 治理 + MLOps + Agent + 协作
2. **从国内市场扩展到全球市场** — 英文文档 + GDPR + EU AI Act 合规
3. **从 200+ 端点扩展到 1000+ 端点** — 每个新域 30-50 端点
4. **从 14 表扩展到 30+ 表** — 新增 Feature Store / Schema Registry / Model Registry 等
5. **从 47 capability 扩展到 100+** — 12 个新域
6. **从 9 阶段管线升级为完整 AI 生命周期** — 数据 → 模型 → 部署 → 监控
7. **从手工迁移到自动化编排** — Cron + Event + A2A + Webhook

智影 V2 = 商业级数据生产 + AI 时代全栈基础设施,可与 Databricks + Snowflake + DataHub + LangChain + Labelbox 竞争,定位 **"AI 时代的 Snowflake"** 或 **"多模态数据的 Databricks"**。

---

## 附录 A: 完整 P1 缺口清单 (60+ 项)

(详见第 16 章, 共 69 项 P1 缺口)

## 附录 B: 完整 P2 缺口清单 (30+ 项)

(详见第 16 章后扩展)

## 附录 C: 关键文件路径速查

| 域 | 主入口 | 现状 | 扩展 |
|---|---|---|---|
| 数据标注 | `engines/workbench_engine.py` (734 行) | 6 几何 + 5 审核 | + AI 辅助 + Active Learning + LiDAR + CRDT |
| 数据治理 | `models/__init__.py` + `orchestration/bus.py` (545 行) | 14 表 + 14 边 | + 三层 Catalog + ML 资产治理 + OpenLineage |
| 工作流 | `workflow_builder/engine.py` (754 行) | DAG + 6 模板 | + Cron + Event + Async + SLA + K8s |
| 向量数据库 | `multimodal/rag.py` (243 行) | 1024-d + in-mem | + HNSW + pgvector + 量化 + 混合 |
| MLOps | (缺) | 无 | 新增 Model Registry + Experiment + Serving + Drift + Feature Store |
| 数据质量 | `engines/internal_qc_engine.py` (967 行) | 4 模式 + AQL | + Profile + 漂移 + 跨表引用 + 告警 |
| 数据血缘 | `orchestration/bus.py` (545 行) | 14 边 | + 列级 + AI 资产 + OpenLineage |
| AI Provider | `providers/registry.py` (328 行) | 7 LLM + 路由 | + Fallback + 熔断 + 缓存 + Guardrails |
| Agent | `multimodal/multimodal_agent.py` (260 行) | 5 工具 | + Memory + HITL + Streaming + A2A + Tool Marketplace |
| 安全/审计 | `security_r8/hardening.py` (371 行) | 4 组件 | + SSO + MFA + ABAC + SCA + 合规报告 |
| 可观测 | `monitoring/` (199+189+104 行) | OTel + Prom | + Loki + SLO + RUM + Alertmanager + Profiling |
| UI/UX | `frontend-v2/src/` | Vue 3 + Naive | + Cmd+K + AI 助手 + 快捷键 + PWA |

## 附录 D: 实施成本估算

| 类别 | 工程师-周 | 工程师-月 (4 周) | 团队规模 (5 人) |
|---|---|---|---|
| P1 (69 项) | 120 | 30 个月-人 | **6 个月** |
| P2 (30 项) | 50 | 12.5 个月-人 | 2.5 个月 |
| P3 (20 项) | 30 | 7.5 个月-人 | 1.5 个月 |
| **总计** | **200** | **50 个月-人** | **10 个月** |

## 附录 E: 商业价值评估

| 类别 | 量化价值 | 说明 |
|---|---|---|
| **TAM 扩展** | 10× (50B → 500B) | 从数据生产 → AI 全栈 |
| **客户单价** | 5-10× (从标注团队到企业 AI 部门) | 高价值客户 |
| **运营成本** | -30% 到 -50% | 自动化 + 自助 |
| **竞争力** | 从"中国本土玩家" → "全球玩家" | 国际化 + 合规 |
| **估值** | $1B → $10B+ (10×) | 类比 Snowflake ($80B) + Databricks ($60B) |

---

**文档完成时间**: 2026-07-01
**总章节**: 30 + 5 附录
**目标字数**: 100,000-150,000 字 (实际约 12 万字)
**核心**: 智影 V1 + 60+ P1 缺口识别 + 15 项扩展设计 + 12 个月实施路线图

> **智影 V2 — 工业级数据生产平台 → AI 时代全栈基础设施,真上线 ready,真商业化 ready,真全球化 ready。**
