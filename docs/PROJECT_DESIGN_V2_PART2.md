# 智影 (ZhiYing) V2 设计文档 — Part 2: 12 域详对比 (继续)

> **续 Part 1**: 第 4 章数据标注已完成,本章从第 5 章数据治理对比开始

---

## 第 5 章 数据管理 / 治理对比

### 5.1 智影数据治理能力现状

智影的"数据治理"由以下部分构成:
- 14 张 ORM 表 (`models/`)
- 14 条 RELATION_GRAPH 血缘边 (`orchestration/bus.py`)
- EventBus (SQLite WAL)
- DataFlowTracker (`capabilities_v2/dataflow.py`)
- HMAC 审计链 (`engines/audit_chain.py` + `security_r8/`)
- Capability inputs/outputs schema (JSON-Schema)
- 47 Capability 17 域 (17 CapabilityCategory)
- 18 实体类型 (EntityType in bus)

### 5.2 与顶级数据治理平台对比

| 功能 | 智影 | Databricks Unity Catalog | Snowflake Horizon | Apache Polaris | OpenMetadata | Apache Gravitino | Collibra |
|---|---|---|---|---|---|---|---|
| **元数据目录** | ⚠️ 14 表独立 | ✅ 三层 (catalog.schema.table) | ✅ | ✅ (Iceberg REST) | ✅ | ✅ | ✅ |
| **统一权限模型 (RBAC + ABAC)** | ⚠️ role-based 简化 | ✅ 列级/行级/标签 | ✅ | ⚠️ 基础 | ✅ | ⚠️ 基础 | ✅ 企业级 |
| **细粒度访问 (列级)** | ❌ 缺 | ✅ + 动态脱敏 | ✅ | ❌ | ✅ | ❌ | ✅ |
| **跨 workspace/引擎联邦** | ❌ 缺 | ⚠️ (DB 内部) | ✅ | ✅ (Iceberg 多引擎) | ✅ | ✅ (核心) | ✅ |
| **数据血缘 (自动)** | ✅ 14 边 | ✅ 全链路 (SQL+ML) | ✅ | ⚠️ 元数据级 | ✅ (UI 强) | ⚠️ 元数据级 | ✅ |
| **ML 资产治理 (Model/Notebook)** | ❌ 缺 | ✅ 业界领先 | ⚠️ | ❌ | ⚠️ | ❌ | ⚠️ |
| **AI 资产 (Agent/Prompt) 治理** | ⚠️ AgentTask + Celery 预留 | ⚠️ 2025 起 | ⚠️ 2026 起 | ❌ | ⚠️ 早期 | ❌ | ⚠️ |
| **数据质量集成** | ✅ 4 QC 模式 | ✅ (DQE + DLT) | ✅ (Cortex) | ⚠️ 接入 | ✅ (Great Exp) | ⚠️ 接入 | ✅ (企业级) |
| **数据发现 (全文搜索)** | ⚠️ multimodal search | ✅ 强 | ✅ | ⚠️ | ✅ 强 | ✅ | ✅ 强 |
| **数据分类 / 标签** | ⚠️ tags JSON | ✅ 自动 + 手动 | ✅ | ⚠️ | ✅ 自动 + 手动 | ⚠️ | ✅ |
| **数据 SLA 监控** | ⚠️ monitoring | ✅ 强 | ✅ | ❌ | ✅ | ❌ | ✅ |
| **术语表 (Glossary)** | ❌ 缺 | ✅ | ✅ | ❌ | ✅ 强 | ❌ | ✅ 业界领先 |
| **业务语义层 (Semantic Layer)** | ❌ 缺 | ✅ (DBSQL) | ✅ (Cortex) | ⚠️ 接入 Cube/dbt | ✅ | ❌ | ✅ |
| **数据合同 (Data Contract)** | ❌ 缺 | ⚠️ 2025 起 | ⚠️ | ❌ | ⚠️ | ❌ | ✅ |
| **OpenLineage 兼容** | ❌ 缺 | ⚠️ 部分 | ⚠️ | ⚠️ 部分 | ✅ | ⚠️ | ⚠️ |
| **API 标准化 (REST + GraphQL)** | ✅ REST | ✅ | ✅ | ✅ REST (规范) | ✅ REST | ✅ REST | ✅ |
| **多云/跨云** | ⚠️ 单 DB | ⚠️ (DB 平台) | ⚠️ (SF 平台) | ✅ 自托管 | ✅ 自托管 | ✅ 自托管 | ✅ |
| **OSS / 商业版** | 内部 | 商业 + 部分开源 | 商业 | Apache 2.0 | Apache 2.0 | Apache 2.0 | 商业 |

### 5.3 智影可补充的能力

**P1 关键缺口**:

1. **三层命名空间 (catalog.schema.table)** — 业界事实标准
   - 设计: 新增 `imdf/catalog/{catalog}/{schema}/{table}` URL 结构
   - 工作量: 1 工程师 × 1 周

2. **列级访问控制 (Column-level ACL)**
   - 设计: 在 ORM 模型上添加 `column_permissions` JSON 字段
   - 工作量: 1 工程师 × 1 周

3. **动态数据脱敏 (Dynamic Data Masking)**
   - 设计: 查询拦截器 + 正则替换 (PII 已经支持 5 类)
   - 工作量: 1 工程师 × 1 周

4. **ML 资产治理 (Model + Notebook + Experiment)**
   - 设计: 新增 `models/ml_assets.py` 表 + `ModelRegistry` + `ExperimentTracker`
   - 工作量: 2 工程师 × 2 周

5. **AI 资产治理 (Agent + Prompt + Tool)**
   - 设计: 新增 `models/ai_assets.py` 表 + `AgentRegistry` + `PromptRegistry`
   - 工作量: 1 工程师 × 1 周

6. **OpenLineage 兼容 (跨平台血缘)**
   - 设计: 监听 bus_events → emit OpenLineage events
   - 工作量: 1 工程师 × 1 周

7. **术语表 (Glossary)**
   - 设计: 新增 `models/glossary.py` 表 + UI
   - 工作量: 1 工程师 × 1 周

**P2 改进**:

8. **数据合同 (Data Contract)**
9. **业务语义层 (Semantic Layer)**
10. **数据 SLA 监控**
11. **数据分类自动识别 (Auto-tagging)**
12. **数据保留策略 (Retention Policy)**

### 5.4 推荐方案: Catalog Wars 应对

参考 **Snowflake Polaris + Unity Catalog 混合架构**:
- 智影内部使用统一 Catalog API (新增 `catalog/` 路由)
- 接入 Iceberg REST 规范 (跨引擎)
- 加 Model/Agent Registry
- OpenLineage 双向兼容

总计 ~8 工程师-周,可让智影从"独立平台"升级到"开放生态节点"。

---

## 第 6 章 工作流编排对比

### 6.1 智影工作流能力现状

智影的工作流由 `workflow_builder/` (engine.py 754 行 + routes.py 145 行) + `nodes/` (registry.py 562 行 + templates.py 380 行) 构成。

**6 个内置模板** (workflow_builder/engine.py:591-731):
1. `wf_tpl_image_annotation` (5 步)
2. `wf_tpl_video_review` (6 步)
3. `wf_tpl_dpo_preference` (7 步)
4. `wf_tpl_drama_production` (5 步)
5. `wf_tpl_model_evaluation` (4 步)
6. `wf_tpl_ai_annotation` (7 步)

**47 节点类型** (nodes/registry.py):
- 6 dimension (text/image/video/audio/model3d/output)
- 15 capability (llm/comfyui/ppt/script/imgedit/upscale/...)
- 26 function (upload/textsplit/loop/relay/aggregate/...)

**当前限制**:
- 同步执行 (HTTP 同步返回)
- 手动触发 (无 cron / event trigger)
- 无监控 / 重试 / 告警
- 无回填 (backfill)
- 无 SLA

### 6.2 与顶级工作流编排平台对比

| 功能 | 智影 | Airflow | Prefect | Dagster | Temporal | Metaflow | Flyte |
|---|---|---|---|---|---|---|---|
| **DAG 表达** | ✅ | ✅ | ✅ | ✅ | ⚠️ 状态机 | ✅ | ✅ |
| **变量替换 (${n1.output})** | ✅ | ✅ (XCom) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **循环 / 分支** | ⚠️ function 节点 | ✅ | ✅ | ✅ (条件) | ✅ (内置) | ✅ (foreach) | ✅ |
| **触发器 (cron/event/manual)** | ⚠️ 仅 manual | ✅ cron+event | ✅ cron+event | ✅ schedule | ✅ event-driven | ✅ cron+trigger | ✅ cron+event |
| **重试 / 指数退避** | ⚠️ TaskQueue (3 retry) | ✅ | ✅ | ✅ | ✅ 内置 | ✅ | ✅ |
| **SLA 监控** | ❌ 缺 | ✅ 强 | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| **回填 (backfill)** | ❌ 缺 | ✅ 强 | ⚠️ | ✅ | N/A | ✅ | ✅ |
| **多租户隔离** | ⚠️ 用户/项目 | ✅ (RBAC) | ✅ (Workspace) | ✅ | ✅ (Namespace) | ⚠️ | ✅ |
| **可视化编辑器** | ✅ (WorkflowBuilder.vue) | ✅ 强 | ✅ 强 | ✅ (Asset graph) | ⚠️ | ⚠️ | ✅ |
| **Kubernetes 原生** | ❌ 缺 | ✅ (K8sExecutor) | ✅ | ✅ | ✅ | ✅ | ✅ 强 |
| **资产/Asset 中心** | ⚠️ 隐式 | ⚠️ (数据集) | ⚠️ | ✅ 强 | ❌ | ✅ (Artifacts) | ✅ |
| **Webhooks 出站** | ❌ 缺 | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| **插件生态** | ⚠️ 47 节点 | ✅ 1000+ | ✅ 200+ | ✅ 100+ | ✅ SDK | ⚠️ | ✅ |
| **CI/CD 集成** | ❌ 缺 | ✅ 强 | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| **事件驱动 (CloudEvents)** | ❌ 缺 | ⚠️ | ⚠️ | ⚠️ | ✅ 强 | ❌ | ⚠️ |
| **本地开发体验** | ⚠️ | ✅ 强 | ✅ 强 | ✅ 强 | ✅ | ✅ 强 | ✅ 强 |
| **学习曲线** | 中 | 陡 | 平 | 中 | 陡 | 平 | 陡 |

### 6.3 智影可补充的能力 (P1)

1. **Cron 触发器 (Scheduled Trigger)**
   - 设计: 集成 APScheduler, 添加 cron 表达式字段
   - 工作量: 1 工程师 × 1 周

2. **事件触发器 (Event-based Trigger)**
   - 设计: EventBus subscribe → 触发 workflow
   - 工作量: 1 工程师 × 1 周

3. **异步执行 (Async Execution)**
   - 设计: 同步改异步 (Celery / RQ / TaskQueue 升级)
   - 工作量: 2 工程师 × 2 周

4. **回填 (Backfill)**
   - 设计: 给定时间范围, 重新跑历史 pipeline
   - 工作量: 1 工程师 × 1 周

5. **SLA 监控 + 告警**
   - 设计: workflow_runs 加 sla_missed_at 字段 + Prometheus + 告警
   - 工作量: 1 工程师 × 1 周

6. **Kubernetes 原生执行**
   - 设计: KubernetesPodOperator 类似
   - 工作量: 2 工程师 × 2 周

7. **条件分支 (Conditional Branching)**
   - 设计: 节点可定义 if/else 路由
   - 工作量: 1 工程师 × 1 周

**P2**:

8. **回滚 (Rollback)**
9. **重试策略配置 UI**
10. **Webhooks 出站**
11. **Workflow 版本管理 (Git-like)**
12. **数据血缘集成 (DAG ↔ Lineage)**
13. **GraphQL 触发**
14. **跨 Workflow 调用 (Sub-workflow)**
15. **死信队列 (DLQ)**
16. **模板市场 (Marketplace)**

### 6.4 推荐方案

参考 **Prefect + Temporal 双引擎** 思想:
- 智影前端继续用可视化画布
- 后端分两层: 编排层 (DAG 解析) + 执行层 (Celery 异步)
- 加 cron/event 触发
- 加 SLA 监控

总计 ~10 工程师-周。

---

## 第 7 章 向量数据库 / RAG 对比

### 7.1 智影 RAG 能力现状

智影的 RAG 由 `multimodal/rag.py` (243 行) + `multimodal/embedding.py` (1024-d) + `multimodal/multimodal_agent.py` (5 工具) 构成。

- **VectorStore**: 1024-d cosine 索引, 深度剧8 rehydrate_from_db
- **MultimodalRAG**: search + answer
- **MultimodalAgent**: 5 工具 (image_understand / video_summarize / document_parse / voice_transcribe / cross_modal_search)
- **CrossModalUnderstanding**: 8 任务 (caption/vqa/classification/relation/sentiment/ocr/asr/reasoning)

**当前限制**:
- 单机 in-memory 向量索引
- 无 ANN 索引 (HNSW / IVF / ScaNN)
- 无量化压缩
- 无混合检索 (BM25 + 向量)
- 无分布式

### 7.2 与顶级向量数据库对比

| 功能 | 智影 | Pinecone | Weaviate | Milvus | Qdrant | Chroma | pgvector |
|---|---|---|---|---|---|---|---|
| **托管服务** | ❌ 自托管 | ✅ Serverless | ✅ Cloud | ✅ Zilliz | ✅ Cloud | ⚠️ 实验 | ✅ (PG 云) |
| **本地部署** | ✅ (in-mem) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ (PG) |
| **最大规模** | 10万 (in-mem) | 亿级 | 千万~亿 | 十亿+ | 亿级 | 百万级 | 千万级 |
| **ANN 算法** | ❌ (暴力) | ✅ (HNSW 等) | ✅ (HNSW) | ✅ (HNSW/IVF/...) | ✅ (HNSW) | ⚠️ (HNSW 轻量) | ✅ (IVFFlat/HNSW) |
| **量化压缩 (int8/PQ)** | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| **GPU 加速** | ❌ | ✅ (透明) | ❌ | ✅ | ✅ (可选) | ❌ | ❌ |
| **多向量 (单实体多向量)** | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ (PG 多列) |
| **混合检索 (BM25 + vector)** | ⚠️ semantic_search 独立 | ✅ (sparse-dense) | ✅ (内置 BM25) | ✅ (scalar + vector) | ✅ (full-text) | ⚠️ (仅 metadata) | ✅ (tsvector + vector) |
| **元数据过滤** | ⚠️ JSON filter | ✅ (server-side) | ✅ | ✅ | ✅ | ✅ | ✅ (SQL JOIN) |
| **动态更新** | ✅ (rehydrate) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **P99 延迟** | N/A | <50ms | 30-100ms | 50-200ms | <20ms | 50-150ms | 100-300ms |
| **生态集成 (LangChain/LlamaIndex)** | ⚠️ 简单 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **多租户** | ❌ | ✅ (Project) | ✅ | ✅ | ✅ (collection) | ❌ | ✅ (PG role) |
| **RBAC** | ⚠️ app-level | ✅ | ✅ (Enterprise) | ✅ | ✅ (v1.10+) | ❌ | ✅ (PG 原生) |
| **审计** | ✅ (HMAC) | ⚠️ (云端 log) | ✅ | ✅ | ✅ | ❌ | ✅ (PG log) |
| **CRUD** | ⚠️ (通过 store) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **分片** | ❌ | ✅ 自动 | ✅ | ✅ | ✅ (手动) | ❌ | ✅ (PG 分区) |
| **备份** | ⚠️ (DB 备份) | ✅ 自动 | ✅ (S3) | ✅ (MinIO) | ✅ | ❌ | ✅ (PG) |
| **MCP 集成** | ⚠️ register_mcp_tools | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |

### 7.3 智影可补充的能力 (P1)

1. **HNSW 索引集成** — 必需
   - 设计: 集成 `hnswlib` (Python 包装 C++ HNSW)
   - 工作量: 1 工程师 × 1 周

2. **量化压缩 (int8 / PQ)**
   - 设计: 用 `faiss-cpu` 或 `hnswlib` 的 quantization
   - 工作量: 1 工程师 × 1 周

3. **混合检索 (BM25 + 向量)**
   - 设计: 已有 `semantic_search` (TF-IDF + BM25), 融合到 RAG
   - 工作量: 1 工程师 × 1 周

4. **pgvector 适配**
   - 设计: PG 模式下走 pgvector, SQLite 走 in-memory HNSW
   - 工作量: 1 工程师 × 1 周

5. **向量元数据过滤 (server-side)**
   - 设计: `search(filter={modality: "image", year: 2025})`
   - 工作量: 1 工程师 × 1 周

6. **分布式分片 (亿级以上)**
   - 设计: Milvus 适配器或自实现分片
   - 工作量: 2 工程师 × 3 周

**P2**:

7. **GPU 加速**
8. **多向量 (单实体多向量)**
9. **Reranker (Cohere / bge-reranker)**
10. **Streaming 检索**
11. **向量索引版本管理**
12. **稀疏向量 (SPLADE / BGE-M3)**
13. **WebDataset 集成 (训练时直接消费)**
14. **LlamaIndex / LangChain 完整集成**

### 7.4 推荐方案: 双 VDB 适配

参考 **Databricks Mosaic AI Vector Search** + **Weaviate** 混合:
- 默认 pgvector (PG 用户零成本)
- 大规模时 hnswlib (单机 in-mem, 千万级)
- 超大规模时 Milvus / Qdrant 适配 (P3-2 微服务化)
- 统一 `VectorStore` 接口

总计 ~10 工程师-周。

---

## 第 8 章 MLOps 对比

### 8.1 智影 MLOps 能力现状

智影的 MLOps 实质上由 `capabilities_v2/` + `engines/` + `monitoring/` 构成,但**没有专门的 Model Registry / Experiment Tracker / Model Serving**。

| 当前能力 | 智影 |
|---|---|
| **Experiment Tracking (指标/参数/工件)** | ⚠️ Prometheus metrics |
| **Model Registry** | ❌ 缺 |
| **Model Versioning** | ❌ 缺 |
| **Model Serving / Inference** | ⚠️ AI Provider 调用 |
| **Model Monitoring (Drift)** | ❌ 缺 |
| **A/B Testing for Models** | ❌ 缺 |
| **Feature Store** | ❌ 缺 |
| **Pipeline (Training)** | ⚠️ workflow_builder 雏形 |
| **Reproducibility** | ⚠️ env + requirements.txt |

### 8.2 与顶级 MLOps 平台对比

| 功能 | 智影 | MLflow | W&B | Neptune | Kubeflow | ClearML | Determined | Metaflow |
|---|---|---|---|---|---|---|---|---|
| **Experiment Tracking** | ⚠️ | ✅ 强 | ✅ 强 | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Model Registry** | ❌ | ✅ | ✅ Artifacts | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| **Model Versioning** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Model Serving** | ❌ | ✅ | ⚠️ (Inference) | ⚠️ | ✅ (KFServing) | ✅ | ✅ | ✅ |
| **Auto-scaling Inference** | ❌ | ⚠️ | ⚠️ | ⚠️ | ✅ (KServe) | ✅ | ✅ | ✅ |
| **Drift Detection** | ❌ | ⚠️ | ✅ | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ |
| **Feature Store** | ❌ | ⚠️ | ⚠️ | ⚠️ | ✅ (Feast) | ⚠️ | ⚠️ | ⚠️ |
| **Pipeline (Training)** | ⚠️ | ✅ | ✅ Sweeps | ✅ | ✅ Pipelines | ✅ Pipelines | ✅ | ✅ |
| **Hyperparameter Tuning** | ❌ | ⚠️ | ✅ 强 | ✅ | ✅ (Katib) | ✅ (Optuna) | ✅ | ✅ |
| **GPU 调度** | ❌ | ❌ | ✅ (云) | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| **Reproducibility** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Artifacts Storage** | ⚠️ 文件 | ✅ S3/MinIO | ✅ S3 | ✅ | ✅ | ✅ | ✅ | ✅ S3 |
| **Webhooks** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |
| **CI/CD 集成** | ❌ | ✅ | ✅ | ✅ | ✅ (Tekton) | ✅ | ⚠️ | ⚠️ |
| **可视化对比** | ❌ | ⚠️ | ✅ 强 | ✅ | ⚠️ | ✅ | ✅ | ⚠️ |
| **团队协作** | ⚠️ | ✅ | ✅ 强 | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |
| **权限 (RBAC)** | ⚠️ | ⚠️ | ✅ 强 | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |

### 8.3 智影可补充的能力 (P1)

1. **Model Registry (CRUD + Versioning)**
   - 设计: 新增 `models/registry.py` 表 (`model_id` / `version` / `artifact_path` / `metrics` / `tags` / `created_at`)
   - 工作量: 1 工程师 × 1 周

2. **Experiment Tracker (Parameters + Metrics + Artifacts)**
   - 设计: `models/experiment.py` + `Experiment` 类 (类似 torch.utils.tensorboard)
   - 工作量: 1 工程师 × 1 周

3. **Model Serving (REST/gRPC endpoint)**
   - 设计: 集成 `BentoML` 或 `Ray Serve` (P3-2 微服务化)
   - 工作量: 2 工程师 × 2 周

4. **Drift Detection (Data + Model + Concept)**
   - 设计: 集成 `Evidently` 或 `whylogs`
   - 工作量: 1 工程师 × 1 周

5. **Feature Store (Online + Offline)**
   - 设计: 集成 `Feast` (P2 优先级)
   - 工作量: 2 工程师 × 2 周

6. **Hyperparameter Tuning**
   - 设计: 集成 `Optuna` + workflow_builder
   - 工作量: 1 工程师 × 1 周

### 8.4 推荐方案: 智影 MLOps 补强路线图

参考 **W&B + BentoML + Evidently** 组合:
- Model Registry + Experiment Tracker (1 周)
- Model Serving (BentoML 集成, 2 周)
- Drift Detection (1 周)
- Feature Store (Feast 集成, 2 周)

总计 ~6 工程师-周。

---

## 第 9 章 数据质量对比

### 9.1 智影数据质量能力现状

智影有 4 种 QC 模式:
- `full_check` - 全量
- `sample_check(rate)` - 比例
- `aql_sample(aql_level, lot_size)` - ISO 2859-1 AQL
- `stratified_sample(strata)` - 分层

**4 类缺陷**:
- label / geometry / format / completeness

**OpenCV 注入点**: `register_cv_detector(name, fn)` 留扩展。

### 9.2 与顶级数据质量平台对比

| 功能 | 智影 | Great Expectations | Soda | Monte Carlo | Deequ | AWS Glue DataBrew |
|---|---|---|---|---|---|---|
| **声明式 (YAML/Python)** | ⚠️ 编程式 | ✅ Expectations Suite | ✅ SodaCL | ❌ (AI 驱动) | ✅ Spark | ✅ 无代码 UI |
| **统计自动推断 (auto)** | ❌ | ✅ (Profiler) | ✅ (Discovery) | ✅ 业界领先 | ✅ | ⚠️ |
| **Schema 验证** | ⚠️ 隐式 | ✅ | ✅ | ✅ | ✅ | ✅ |
| **数值范围 / 分布** | ✅ (geometry 校验) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **唯一性 / 完整性** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **跨表引用 (referential)** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **时序 / 漂移检测** | ❌ | ⚠️ (第三方) | ⚠️ | ✅ 强 | ✅ | ⚠️ |
| **AI 驱动异常发现** | ❌ | ❌ | ⚠️ | ✅ 业界领先 | ❌ | ⚠️ |
| **集成 dbt / Airflow** | ⚠️ workflow | ✅ | ✅ | ✅ | ✅ (Spark) | ✅ (Glue) |
| **AQL / ISO 2859-1** | ✅ 业界领先 | ❌ | ❌ | ❌ | ❌ | ❌ |
| **QC Report 导出** | ✅ HTML/JSON | ✅ (Data Docs) | ✅ | ✅ | ⚠️ | ✅ |
| **数据谱 (Data Profiling)** | ⚠️ get_qc_stats | ✅ 强 | ✅ | ✅ | ✅ | ✅ |
| **告警 (Slack/Email)** | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| **自定义 Rule** | ✅ (OpenCV) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **实时 vs 批** | ⚠️ 批 | ⚠️ 批 | ✅ 批+流 | ✅ 实时 | ✅ 批+流 | ✅ 批 |
| **数据合同 (Data Contract)** | ❌ | ⚠️ 2025 | ⚠️ | ⚠️ | ❌ | ❌ |
| **与 Catalog 集成** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ (Glue) |

### 9.3 智影可补充的能力 (P1)

1. **数据 Profile 自动推断**
   - 设计: 启动时扫数据集, 推断每列 min/max/distribution/unique/count
   - 工作量: 1 工程师 × 1 周

2. **跨表引用完整性 (Referential Integrity)**
   - 设计: 跨数据集/资产检查 FK
   - 工作量: 1 工程师 × 1 周

3. **时序漂移检测 (Drift Detection)**
   - 设计: 集成 `Evidently` (data + target + concept drift)
   - 工作量: 1 工程师 × 1 周

4. **告警集成 (Slack/Email/Webhook)**
   - 设计: notification_service 升级
   - 工作量: 1 工程师 × 1 周

5. **Data Docs (HTML 报告 + 可视化)**
   - 设计: 类似 GE Data Docs
   - 工作量: 1 工程师 × 1 周

**P2**:

6. **数据合同**
7. **Schema 演进追踪**
8. **AI 驱动异常发现**
9. **跨 catalog QC**

总计 ~5 工程师-周。

---

## 第 10 章 数据血缘对比

### 10.1 智影血缘能力现状

- 14 条 RELATION_GRAPH 边 (`orchestration/bus.py`)
- EventBus 自动记录 18 实体类型
- DataFlowTracker 记录 capability 调用的 entity
- HMAC 审计链 (审计 + lineage)

### 10.2 与顶级血缘平台对比

| 功能 | 智影 | DataHub | OpenMetadata | Apache Atlas | OpenLineage + Marquez | Unity Catalog |
|---|---|---|---|---|---|---|
| **自动采集** | ✅ 14 边 | ✅ 强 (Metadata Ingest) | ✅ 强 | ✅ | ✅ (标准) | ✅ |
| **实时流** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **跨平台 (Airflow/Spark/dbt)** | ⚠️ bus | ✅ | ✅ | ✅ | ✅ 强 (标准) | ⚠️ |
| **UI 渲染** | ✅ DataFlowTracker.vue | ✅ 业界领先 | ✅ 强 | ⚠️ | ✅ (Marquez) | ✅ |
| **影响分析 (upstream/downstream)** | ✅ bus.query | ✅ | ✅ | ✅ | ✅ | ✅ |
| **列级血缘** | ❌ | ✅ | ✅ | ✅ | ✅ (Facet) | ✅ |
| **业务术语映射** | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| **OpenLineage 兼容** | ❌ | ✅ | ✅ | ⚠️ | ✅ (原生) | ⚠️ |
| **跨组织 (Data Sharing)** | ❌ | ⚠️ | ⚠️ | ⚠️ | ✅ | ⚠️ |
| **AI 资产 (Model/Notebook/Agent) 血缘** | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| **元数据版本** | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| **实时事件流 (Kafka/Pulsar)** | ⚠️ bus SQLite | ✅ (Kafka) | ✅ | ✅ | ✅ | ⚠️ |
| **搜索** | ⚠️ multimodal search | ✅ 强 | ✅ 强 | ✅ | ✅ | ✅ |
| **API 标准化** | ✅ REST | ✅ REST + GraphQL | ✅ REST | ✅ REST | ✅ 标准 | ✅ |

### 10.3 智影可补充的能力 (P1)

1. **OpenLineage 兼容 (出站 emit)**
   - 设计: bus_events → OpenLineage events
   - 工作量: 1 工程师 × 1 周

2. **列级血缘 (Column-level Lineage)**
   - 设计: 在 capability.outputs 中加 `column_lineage` 字段
   - 工作量: 2 工程师 × 2 周

3. **AI 资产血缘 (Model + Notebook + Agent + Prompt)**
   - 设计: 扩展 `EntityType` enum
   - 工作量: 1 工程师 × 1 周

4. **跨组织数据共享**
   - 设计: 加 `share_token` 字段 + 联邦 lineage 查询
   - 工作量: 1 工程师 × 1 周

5. **元数据版本 (Time Travel)**
   - 设计: `bus_events` 加 version + 历史回放
   - 工作量: 1 工程师 × 1 周

### 10.4 推荐方案

参考 **OpenLineage 标准**:
- bus_events 增强为 OpenLineage 兼容事件
- 加列级血缘
- 加 AI 资产血缘
- 加跨组织 lineage

总计 ~6 工程师-周。

---

## 第 11 章 AI Provider 路由对比

### 11.1 智影 AI Provider 路由能力现状

智影的 AI Provider 路由由 `providers/registry.py` 构成:
- 7 内置 LLM (openai/claude/deepseek/qwen/doubao/comfyui/mock)
- 4 多模态生成器 (openai_compatible/volcengine/jimeng_cli/comfyui)
- `route(family, prefer='cost'|'speed'|'trust', exclude)` 选优
- `record_call(provider_id, ...)` 写 `provider_calls` 表 + 算 cost

### 11.2 与顶级 AI Gateway 平台对比

| 功能 | 智影 | Portkey | LiteLLM | Helicone | OpenRouter | Cloudflare AI Gateway | Bifrost |
|---|---|---|---|---|---|---|---|
| **统一 API (OpenAI 协议)** | ⚠️ | ✅ | ✅ 强 | ⚠️ | ✅ | ✅ | ✅ |
| **多 provider 路由** | ✅ cost/speed/trust | ✅ 强 | ✅ | ⚠️ | ✅ (聚合) | ✅ | ✅ |
| **自动 Fallback** | ❌ 缺 | ✅ | ✅ | ⚠️ | ✅ | ✅ | ✅ |
| **Circuit Breaker** | ❌ 缺 | ✅ | ✅ | ⚠️ | ⚠️ | ✅ | ✅ |
| **重试 + 退避** | ⚠️ TaskQueue 3 retry | ✅ 强 | ✅ | ✅ | ✅ | ✅ | ✅ |
| **缓存 (语义 + 精确)** | ⚠️ TTLCache 通用 | ✅ 强 | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| **限流 (per-tenant/per-key)** | ⚠️ RateLimiter 60/min | ✅ 强 | ✅ | ⚠️ | ⚠️ | ✅ 强 | ✅ |
| **可观测 (Latency/Cost/Errors)** | ✅ Prometheus | ✅ 强 | ✅ | ✅ 强 | ⚠️ | ✅ | ✅ |
| **Guardrails (PII/Toxicity)** | ⚠️ PII 脱敏 | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| **Prompt 版本管理** | ❌ 缺 | ✅ | ⚠️ | ⚠️ | ❌ | ❌ | ✅ |
| **A/B Testing for Prompts** | ❌ 缺 | ✅ | ⚠️ | ⚠️ | ❌ | ❌ | ⚠️ |
| **Fine-tuning 管理** | ❌ 缺 | ✅ | ⚠️ | ⚠️ | ❌ | ❌ | ⚠️ |
| **On-prem 部署** | ✅ | ✅ | ✅ | ❌ (云) | ❌ | ❌ | ✅ |
| **BYOK (自备 Key)** | ✅ Vault | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Multi-modal (image/video/audio)** | ✅ 4 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Streaming 支持** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **MCP 集成** | ⚠️ register_mcp | ✅ | ✅ | ⚠️ | ❌ | ⚠️ | ✅ |
| **Audit / Compliance** | ✅ HMAC | ✅ | ⚠️ | ⚠️ | ⚠️ | ✅ | ✅ |
| **Open Source** | ✅ | ⚠️ 部分 | ✅ | ❌ | ❌ | ❌ | ✅ (Go) |

### 11.3 智影可补充的能力 (P1)

1. **自动 Fallback Chain**
   - 设计: `route(exclude=...)` 失败后自动尝试 `route(exclude=[failed]+previous)`
   - 工作量: 1 工程师 × 3 天

2. **Circuit Breaker (熔断)**
   - 设计: 记录连续失败, 超过阈值熔断 60s
   - 工作量: 1 工程师 × 1 周

3. **语义缓存 (Semantic Cache)**
   - 设计: `query_hash` → response 缓存 (基于 LSH)
   - 工作量: 1 工程师 × 1 周

4. **Prompt 版本管理**
   - 设计: 新增 `models/prompt.py` 表 + version
   - 工作量: 1 工程师 × 1 周

5. **A/B Testing for Prompts**
   - 设计: 多版本并行 + 流量分配 + 效果对比
   - 工作量: 1 工程师 × 1 周

6. **Guardrails 增强**
   - 设计: 集成 `Guardrails AI` 或自实现 (toxicity / PII / 越狱检测)
   - 工作量: 1 工程师 × 1 周

**P2**:

7. **Fine-tuning 工作流**
8. **Streaming response (SSE/WebSocket)**
9. **Rate limit per-tenant (精细化)**
10. **Cost budget alerting**

### 11.4 推荐方案

参考 **Portkey + LiteLLM** 组合:
- 自动 Fallback + Circuit Breaker
- 语义缓存
- Prompt Registry + A/B
- Guardrails

总计 ~6 工程师-周。

---

## 第 12 章 智能 Agent 框架对比

### 12.1 智影 Agent 能力现状

智影的 Agent 由 `multimodal/multimodal_agent.py` 构成:
- 5 工具: image_understand / video_summarize / document_parse / voice_transcribe / cross_modal_search
- 关键词路由表 (`_TOOL_KEYWORDS`)
- `_default_plan` 规划算法
- `register_mcp_tools()` MCP 桥接

### 12.2 与顶级 Agent 框架对比

| 功能 | 智影 | LangChain | LlamaIndex | AutoGen (Microsoft) | CrewAI | Semantic Kernel | MCP |
|---|---|---|---|---|---|---|---|
| **多工具调用** | ✅ 5 | ✅ 100+ | ⚠️ 8 | ✅ | ✅ | ✅ | ✅ (协议) |
| **规划算法 (ReAct/Plan-Execute)** | ⚠️ 简化 | ✅ ReAct/CoT | ✅ | ✅ | ✅ | ✅ | N/A |
| **Memory (短/长)** | ❌ 缺 | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **RAG 集成** | ✅ VectorStore | ✅ | ✅ 强 | ⚠️ | ⚠️ | ✅ | ⚠️ |
| **多 Agent 协作** | ❌ 缺 | ⚠️ (LangGraph) | ❌ | ✅ 强 | ✅ 强 | ⚠️ | ❌ |
| **人类反馈 (Human-in-the-loop)** | ❌ 缺 | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ |
| **Streaming** | ❌ 缺 | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| **Eval 框架** | ❌ 缺 | ✅ LangSmith | ✅ | ⚠️ | ⚠️ | ⚠️ | ❌ |
| **Tracing** | ⚠️ OTel | ✅ LangSmith | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| **Prompt Template 管理** | ❌ 缺 | ✅ | ⚠️ | ✅ | ✅ | ✅ | ❌ |
| **MCP 集成** | ✅ register | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (原生) |
| **A2A (Agent-to-Agent)** | ❌ 缺 | ⚠️ | ❌ | ✅ | ✅ | ⚠️ | ❌ |
| **多模态** | ✅ 强 | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |
| **Browser Use** | ❌ 缺 | ✅ | ❌ | ✅ | ✅ | ⚠️ | ⚠️ |
| **Code Execution (Sandbox)** | ❌ 缺 | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ |
| **Structured Output** | ⚠️ | ✅ 强 | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| **工具市场** | ❌ 缺 | ⚠️ | ❌ | ✅ | ✅ | ⚠️ | ✅ |
| **回滚 / 错误恢复** | ⚠️ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ |
| **Multi-Step Reasoning** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |

### 12.3 智影可补充的能力 (P1)

1. **Memory 系统 (短期 + 长期)**
   - 设计: Redis (短) + PG (长) + RAG (语义)
   - 工作量: 2 工程师 × 2 周

2. **人类反馈 (Human-in-the-loop)**
   - 设计: Agent 决策前 `confirm()` 端点
   - 工作量: 1 工程师 × 1 周

3. **Streaming Response (SSE)**
   - 设计: FastAPI SSE + 智影 Agent invoke stream
   - 工作量: 1 工程师 × 1 周

4. **Tool Marketplace**
   - 设计: MCP 工具市场 (类似 Smithery / Glama)
   - 工作量: 1 工程师 × 2 周

5. **A2A 协议 (Agent-to-Agent)**
   - 设计: 集成 Google A2A 协议
   - 工作量: 2 工程师 × 2 周

6. **多 Agent 协作 (CrewAI 风格)**
   - 设计: Crew(role, goal, backstory) + Tasks
   - 工作量: 2 工程师 × 3 周

7. **Browser Use / Computer Use**
   - 设计: 集成 Playwright + Anthropic Computer Use
   - 工作量: 1 工程师 × 1 周

8. **Code Sandbox (e2b)**
   - 设计: 集成 e2b 或自实现 Docker 沙箱
   - 工作量: 1 工程师 × 1 周

**P2**:

9. **Prompt Template 注册中心**
10. **Eval 框架 (Agent Benchmark)**
11. **Agent Trace UI**
12. **Agent 性能 dashboard**

### 12.4 推荐方案

参考 **LangChain + AutoGen + MCP** 组合:
- 短期补 Memory + HITL + Streaming
- 中期加 Tool Marketplace + A2A
- 长期支持 Browser Use + Code Sandbox

总计 ~10 工程师-周。

---

## 第 13 章 安全/审计对比

### 13.1 智影安全/审计能力现状

智影的安全由 `security_r8/hardening.py` (371 行) + `security_r8/routes.py` (102 行) + `engines/audit_chain.py` (420 行) 构成。

**4 大安全组件**:
- `RateLimiter` (60/min 固定窗口)
- `redact_pii` (5 类正则脱敏)
- `SecretsVault` (8 默认 secret)
- `AuditChain` (HMAC-SHA256)

**9 个端点** (`/api/v1/security/*`):
- `/redact` (PII 脱敏)
- `/rate-limit/check`
- `/audit/tail`, `/audit/verify`, `/audit/append`
- `/secrets` (list), `/secrets/get`, `/secrets/rotate`
- `/health`

### 13.2 与顶级安全平台对比

| 功能 | 智影 | HashiCorp Vault | Snyk | Auth0 | OWASP ZAP | Keycloak | OneTrust |
|---|---|---|---|---|---|---|---|
| **密钥管理 (KMS)** | ✅ Vault | ✅ 业界领先 | ⚠️ | ⚠️ | ❌ | ⚠️ | ⚠️ |
| **密钥轮换** | ✅ | ✅ 自动 | N/A | ✅ | N/A | ✅ | ⚠️ |
| **PII 脱敏** | ✅ 5 类 | ⚠️ (Transform) | ❌ | ⚠️ | ❌ | ⚠️ | ✅ 强 |
| **限流 (Rate Limiting)** | ✅ 60/min | ⚠️ | ❌ | ✅ | ❌ | ✅ | ❌ |
| **审计日志** | ✅ HMAC 链 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **RBAC** | ⚠️ role-based | ✅ (Policy) | ✅ | ✅ 强 | ⚠️ | ✅ 强 | ✅ |
| **ABAC (属性级)** | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| **SSO (SAML/OIDC)** | ⚠️ JWT only | ⚠️ | ⚠️ | ✅ 强 | ❌ | ✅ 强 | ⚠️ |
| **MFA** | ❌ 缺 | ⚠️ | ⚠️ | ✅ 强 | ❌ | ✅ | ✅ |
| **依赖漏洞扫描 (SCA)** | ❌ | ❌ | ✅ 业界领先 | ❌ | ⚠️ | ❌ | ❌ |
| **DAST (动态扫描)** | ❌ | ❌ | ⚠️ | ❌ | ✅ 强 | ❌ | ❌ |
| **SAST (静态扫描)** | ❌ | ❌ | ✅ | ❌ | ⚠️ | ❌ | ❌ |
| **CSPM (云安全)** | ❌ | ⚠️ | ✅ | ⚠️ | ❌ | ❌ | ✅ |
| **数据分类 / 标签** | ⚠️ tags JSON | ⚠️ | ⚠️ | ⚠️ | ❌ | ⚠️ | ✅ 强 |
| **数据驻留 / 区域** | ❌ | ⚠️ | ⚠️ | ✅ | ❌ | ⚠️ | ✅ |
| **GDPR 合规** | ⚠️ PII | ⚠️ | ⚠️ | ✅ | ❌ | ⚠️ | ✅ 业界领先 |
| **EU AI Act 合规** | ⚠️ AuditChain | ⚠️ | ⚠️ | ⚠️ | ❌ | ❌ | ✅ |
| **审计链不可篡改** | ✅ HMAC 业界领先 | ⚠️ | ⚠️ | ⚠️ | ❌ | ⚠️ | ⚠️ |
| **SBOM / 软件物料清单** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ⚠️ |
| **Secret Leak Detection** | ❌ | ⚠️ | ✅ | ⚠️ | ❌ | ⚠️ | ⚠️ |

### 13.3 智影可补充的能力 (P1)

1. **SSO 集成 (SAML/OIDC)**
   - 设计: 集成 `python-saml` 或 `authlib`
   - 工作量: 1 工程师 × 1 周

2. **MFA 多因素认证**
   - 设计: TOTP (RFC 6238)
   - 工作量: 1 工程师 × 1 周

3. **细粒度 ABAC (属性级权限)**
   - 设计: Cedar / OPA 集成
   - 工作量: 2 工程师 × 2 周

4. **SCA 依赖漏洞扫描**
   - 设计: 集成 `safety` / `pip-audit` / `Snyk CLI`
   - 工作量: 1 工程师 × 3 天

5. **DAST 动态扫描**
   - 设计: 集成 OWASP ZAP
   - 工作量: 1 工程师 × 1 周

6. **GDPR/AI Act 合规报告**
   - 设计: 自动生成合规报告
   - 工作量: 1 工程师 × 2 周

**P2**:

7. **SBOM**
8. **Secret Leak Detection**
9. **CSPM**
10. **数据分类自动识别**

### 13.4 推荐方案

参考 **HashiCorp Vault + Auth0 + Snyk** 组合:
- Vault 升级 (生产级)
- Auth0 集成 (SSO/MFA)
- Snyk CLI 集成 (SCA)
- 合规报告

总计 ~8 工程师-周。

---

## 第 14 章 可观测性对比

### 14.1 智影可观测性现状

- Prometheus: 6 指标 (imdf_requests_total / latency / queue_depth / running_tasks / memory_rss / active_connections)
- OpenTelemetry: setup_tracing() → Jaeger
- 12 微服务的 `/metrics` / `/healthz` / `/readyz`
- EventBus: 业务事件
- DataFlowTracker: 业务流转
- 错误聚合: errorReporter.ts (前端)
- 结构化日志: JSON
- HMAC 审计链: 安全审计

### 14.2 与顶级可观测性平台对比

| 功能 | 智影 | Datadog | Grafana Stack | New Relic | Honeycomb | SigNoz | Elastic Observability |
|---|---|---|---|---|---|---|---|
| **Metrics (Prometheus)** | ✅ | ✅ | ✅ 强 | ✅ | ⚠️ | ✅ | ✅ |
| **Tracing (OTel/Jaeger)** | ✅ | ✅ | ✅ Tempo | ✅ | ✅ 强 | ✅ | ✅ |
| **Logging (聚合)** | ⚠️ 文件 | ✅ 强 | ✅ Loki | ✅ | ⚠️ | ✅ | ✅ 业界领先 |
| **APM (应用性能)** | ⚠️ | ✅ 业界领先 | ⚠️ | ✅ 业界领先 | ✅ | ✅ | ✅ |
| **Real User Monitoring (RUM)** | ❌ | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ | ✅ |
| **Synthetic Monitoring** | ❌ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ✅ |
| **业务 KPI dashboard** | ⚠️ monitoring | ✅ 强 | ✅ 强 | ✅ 强 | ✅ | ✅ | ✅ |
| **告警 (Alertmanager)** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **SLO/SLI 跟踪** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Error Tracking (Sentry 风格)** | ⚠️ 前端 | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ | ✅ |
| **Profiling (Continuous)** | ❌ | ✅ (Continuous) | ⚠️ Pyroscope | ⚠️ | ⚠️ | ⚠️ | ✅ |
| **Database 监控** | ⚠️ | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ | ✅ |
| **AI Cost Tracking** | ✅ record_call | ✅ | ⚠️ | ✅ | ⚠️ | ⚠️ | ⚠️ |
| **Anomaly Detection (AI)** | ❌ | ✅ Watchdog | ✅ | ✅ | ✅ (BubbleUp) | ⚠️ | ✅ |
| **On-prem 部署** | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ | ✅ |
| **Open Source** | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ | ⚠️ (部分) |
| **价格** | 自建 | $$$ | 免费 (自建) | $$$ | $$ | 免费 (自建) | $$ |

### 14.3 智影可补充的能力 (P1)

1. **Loki 集中日志**
   - 设计: 集成 Loki + Promtail
   - 工作量: 1 工程师 × 1 周

2. **SLO/SLI 跟踪**
   - 设计: `slo_definitions` 表 + PromQL
   - 工作量: 1 工程师 × 1 周

3. **RUM (Real User Monitoring)**
   - 设计: 前端 SDK + 后端 ingest
   - 工作量: 1 工程师 × 1 周

4. **告警 (Alertmanager)**
   - 设计: Alertmanager 集成 + 通知渠道
   - 工作量: 1 工程师 × 1 周

5. **Continuous Profiling (Pyroscope)**
   - 设计: 集成 Pyroscope
   - 工作量: 1 工程师 × 3 天

**P2**:

6. **Anomaly Detection (AI 异常发现)**
7. **Database 深度监控 (慢查询 / 锁)**
8. **Synthetic Monitoring**
9. **PII 自动告警**
10. **Cost Guard (AI 调用超预算自动熔断)**

总计 ~5 工程师-周。

---

## 第 15 章 UI/UX 对比

### 15.1 智影 UI/UX 现状

- Vue 3 + Pinia + Naive UI
- 35 视图 + 11 子目录
- 5 token 主题 (light/dark/auto)
- WCAG AA (部分 AAA)
- i18n (zh-CN / en-US, 410+ 键)
- 7 命名空间
- Skip-link / focus-visible / 减动效

### 15.2 与顶级 B 端工具 UI 对比

| 功能 | 智影 | Linear | Notion | Figma | Slack | Jira |
|---|---|---|---|---|---|---|
| **响应式 (mobile-first)** | ⚠️ | ✅ | ✅ | ⚠️ | ✅ | ✅ |
| **暗色模式 (3 态)** | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| **键盘快捷键 (Cmd+K)** | ❌ | ✅ 强 | ✅ 强 | ✅ 强 | ✅ | ⚠️ |
| **Command Palette** | ❌ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |
| **拖拽 (DnD)** | ⚠️ 部分 | ✅ | ✅ | ✅ 强 | ⚠️ | ✅ |
| **实时协作 (多人光标)** | ❌ | ✅ (Pro) | ✅ | ✅ 强 | ✅ | ⚠️ |
| **离线工作 (PWA)** | ❌ | ⚠️ | ✅ | ⚠️ | ⚠️ | ❌ |
| **Touch / 手势** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| **AI 助手 (内嵌)** | ❌ | ✅ (Linear Asks) | ✅ (Notion AI) | ✅ (Figma AI) | ✅ (Slack AI) | ✅ (Atlassian AI) |
| **In-line 注释** | ❌ | ✅ | ✅ | ✅ 强 | ✅ | ✅ |
| **历史版本 (Time Machine)** | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| **权限可见性 (透明)** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **A11y WCAG** | AA | AAA | AA | AA | AA | AA |
| **i18n** | ✅ 2 语种 | ✅ 5+ | ✅ 10+ | ✅ 20+ | ✅ 20+ | ✅ 20+ |
| **Performance (Lighthouse)** | ⚠️ | 90+ | 85+ | 90+ | 80+ | 75+ |
| **Component Library** | Naive UI | 自研 | 自研 | 自研 | 自研 | Atlassian Design |
| **Design System** | ⚠️ 主题 | ✅ 完整 | ✅ 完整 | ✅ 业界领先 | ✅ | ✅ |

### 15.3 智影可补充的 UI/UX 能力 (P1)

1. **Command Palette (Cmd+K)**
   - 设计: 跨视图快速跳转 + 动作触发
   - 工作量: 1 工程师 × 1 周

2. **AI 助手 (内嵌)**
   - 设计: `multimodal/multimodal_agent.ts` 包装 + UI Chat 面板
   - 工作量: 1 工程师 × 2 周

3. **键盘快捷键**
   - 设计: 类似 Linear 的 G+I (Go to Inbox) 等
   - 工作量: 1 工程师 × 1 周

4. **离线工作 (PWA)**
   - 设计: Vite PWA 插件 + Workbox
   - 工作量: 1 工程师 × 1 周

5. **历史版本 + 撤销/重做**
   - 设计: Time-Travel Debugging 风格
   - 工作量: 1 工程师 × 1 周

6. **Touch / 手势优化**
   - 设计: VueUse + 触屏适配
   - 工作量: 1 工程师 × 3 天

**P2**:

7. **实时协作 (多人光标)**
8. **In-line 注释**
9. **Lighthouse 95+ 优化**
10. **PWA 移动端 App**
11. **Voice Input (Web Speech API)**
12. **AR 预览 (3D 模型)**

总计 ~6 工程师-周。

---

# 第三部 (待续)

第 16-30 章 (15 章) 详细列出识别出的 60+ 缺口,Feature Store / DVC / 计费 / A/B / 文档协作 / 通知 / Schema Registry / 漂移检测 / Prompt 工程 / CDP / 项目管理 等的扩展设计,详见 V2 设计文档 Part 3。

---
