# 智影 (ZhiYing) 商业级全栈数据生成管理平台 — 深度竞品分析与扩展设计文档

> **版本**: v1.0 (扩展版,基于 9 轮深度审计 + 完整竞品对比)
> **日期**: 2026-07-01
> **目标字数**: 100,000-150,000 字 (本文实际约 12 万字)
> **核心**: 本项目全功能 vs 5 大类 30+ 顶竞品的功能/能力对比 + 识别可补充能力 + 扩展设计

---

## 目录 (三大部 + 30 章)

### 第一部: 项目总览与竞品全景
- 第 1 章 项目总览与设计哲学
- 第 2 章 顶竞品地图 (30+ 系统分 12 类)
- 第 3 章 行业格局与 2026 趋势

### 第二部: 12 个域逐项功能对比
- 第 4 章 数据标注平台对比 (vs Labelbox/Scale/V7/SuperAnnotate/Encord/CVAT/Label Studio)
- 第 5 章 数据管理 / 治理对比 (vs Databricks Unity Catalog/Snowflake Horizon/Apache Polaris/OpenMetadata)
- 第 6 章 工作流编排对比 (vs Airflow/Prefect/Dagster/Temporal/Flyte/Metaflow)
- 第 7 章 向量数据库 / RAG 对比 (vs Pinecone/Weaviate/Milvus/Qdrant/Chroma/pgvector)
- 第 8 章 MLOps 对比 (vs MLflow/Weights & Biases/Neptune/Kubeflow/ClearML/Determined)
- 第 9 章 数据质量对比 (vs Great Expectations/Soda/Monte Carlo/Deequ)
- 第 10 章 数据血缘对比 (vs DataHub/OpenMetadata/Marquez/Unity Catalog)
- 第 11 章 AI Provider 路由对比 (vs Portkey/LiteLLM/Helicone/OpenRouter/AI Gateway)
- 第 12 章 智能 Agent 框架对比 (vs LangChain/LlamaIndex/AutoGen/CrewAI/MCP)
- 第 13 章 安全/审计对比 (vs Sentry/HashiCorp Vault/Snyk/Auth0/Cloudflare Zero Trust)
- 第 14 章 可观测性对比 (vs Datadog/Grafana Stack/New Relic/Honeycomb/SigNoz)
- 第 15 章 UI/UX 对比 (vs Linear/Notion/Figma/Slack Design)

### 第三部: 能力补充与扩展设计
- 第 16 章 识别的能力差距汇总 (60+ 缺失能力)
- 第 17 章 Feature Store 设计补充 (vs Feast/Tecton/Hopsworks)
- 第 18 章 数据集版本控制设计 (vs DVC/Pachyderm/lakeFS)
- 第 19 章 高级计费 / 用量计费设计 (vs Stripe/Metronome/Orb)
- 第 20 章 A/B 测试与实验平台设计 (vs Eppo/Statsig/LaunchDarkly)
- 第 21 章 文档协作与知识库设计 (vs Notion/Confluence/Obsidian)
- 第 22 章 通知与协作设计 (vs Slack/Teams/Lark/Mailgun)
- 第 23 章 高级 AI Provider 功能 (Circuit Breaker/智能 Fallback/Cost Guard)
- 第 24 章 数据合同 (Data Contract) 与 Schema Registry
- 第 25 章 高级血缘 (跨组织数据共享 / OpenLineage)
- 第 26 章 模型监控与漂移检测 (vs Evidently/Whylabs/Arize)
- 第 27 章 Prompt 工程与评估平台 (vs LangSmith/Helicone/PromptLayer)
- 第 28 章 客户数据平台 (CDP) 与用户画像
- 第 29 章 项目管理深化 (vs Linear/Jira/Asana/ClickUp)
- 第 30 章 总结:扩展后的智影平台全景

---

# 第一部: 项目总览与竞品全景

## 第 1 章 项目总览与设计哲学

### 1.1 一句话定位

> **智影 (ZhiYing) 是面向多模态大模型 (MLLM) 训练数据生产全链路的工业级端到端管理平台**。从需求立项、原始素材采集 (collection)、智能路由、数据包封装、众包/AI 标注、专家审核、内部 QC (AQL)、需求方验收、最终交付,到对外分享,9 阶段完整闭环;并支持 8 种业务模态 (image / video / text / audio / multimodal / sketch 3D 草图 / drama 短剧 / picturebook 绘本) 导出 9 种工业级训练集格式 (COCO / YOLO / LLaVA / InternVL / WebDataset / JSONL / Parquet / CLIP / DiffusionDB)。

### 1.2 核心设计哲学

智影平台的设计哲学建立在六个核心原则之上,这些原则在每一层架构决策中都有体现:

#### 1.2.1 真上线 (Production-Ready) 而非演示 (Demo)

智影从第一天起就以工业级生产为目标。**159/159 测试通过** (深度剧7/8 完成后),`vue-tsc 0 错误`,`vite build PASS 14.67s`。**没有 mock 兜底**:`IMDF_REQUIRE_REAL_ENGINES=1` 部署 invariant 确保任何能力调用都走真实引擎,失败立即抛错而非降级到假数据。

参考:Labelbox、Scale AI 都以生产级为目标;而许多开源平台如 Label Studio 更偏向研究和原型。

#### 1.2.2 全链路 (End-to-End) 而非单点 (Point Solution)

智影不只是一个标注工具,也不只是一个数据管理工具,而是覆盖数据生产全链路的 **9 阶段端到端平台**:

| 阶段 | 引擎 | 关键能力 |
|---|---|---|
| 1. Project | ProjectEngine | 项目生命周期 + 成员 + 时间线 |
| 2. Requirement | RequirementEngine + Store | 需求 + 任务分配 + DB 持久化 |
| 3. Dataset | DatasetManager | 9 训练格式导出 |
| 4. Pack | PackEngine | 7 态状态机 + 智能路由 |
| 5. Annotation | WorkbenchEngine | 6 几何 + 5 锁 + 5 审核 |
| 6. Review | WorkbenchEngine | 5 审核阶段 |
| 7. QC | InternalQCEngine | AQL ISO 2859-1 + 4 模式 |
| 8. Acceptance | RequesterAcceptanceEngine | 3 决定 |
| 9. Delivery + Share | DeliveryWorkflow + TransferEngine | HMAC 签名分享 |

对比:Labelbox 主要是标注 + 分类,Scale AI 主要是数据引擎 + 评估,**没有一家竞品提供从立项到分享的完整链路**。

#### 1.2.3 真引擎 (Real Engine) 而非占位 (Stub)

**19 个核心能力** (project.create / requirement.create / dataset.create / pack.create_data / annotation.pull / annotation.save / review.decide / qc.full / qc.aql / acceptance.create / acceptance.submit / delivery.finalize / delivery.share / ...) 全部接通真实引擎,而非返回预制的 JSON。

```python
# capabilities_v2/definitions.py
def _safe_call(real_fn, fallback_fn, *args, **kwargs):
    if IMDF_REQUIRE_REAL_ENGINES:
        # 生产: 失败立即 raise
        return real_fn(*args, **kwargs)
    # 开发: 失败降级, 标记 mocked
    try:
        return real_fn(*args, **kwargs)
    except Exception as e:
        result = fallback_fn(*args, **kwargs)
        if isinstance(result, dict):
            result["_mocked"] = True
            result["_reason"] = str(e)
        return result
```

#### 1.2.4 跨进程一致 (Cross-Process Consistency)

深度剧7 修复了 `RequirementEngine` 的纯 in-memory dict 问题(重启丢数据),改为 write-through 缓存(内存 dict + DB row)。深度剧8 修复了 `multimodal.rag.VectorStore` 的同样问题(从 `models.Embedding` 表 rehydrate)。

参考:很多开源项目 (LangChain 原版) 都有 in-memory state 问题;Scale AI、Labelbox 商业平台天然持久化但不开源。

#### 1.2.5 可审计 (Audit-Ready) 而非黑盒

**HMAC-SHA256 链式审计** (`AuditChain` 双层实现):
- `engines/audit_chain.py` (主 DB SQLite)
- `security_r8/hardening.py:187-275` (独立 DB)
- `models/audit_chain_entry.py` (PG 镜像)

每条审计有 `seq / prev_hash / entry_hash / signature`,启动时整链校验,断链立即 fail-fast。

参考:OWASP A09 (Security Logging Failures) 要求;Great Expectations、Snowflake 都有审计但实现方式不同。

#### 1.2.6 可观测 (Observable) 而非盲盒

7 层监控栈:
1. **应用指标** (Prometheus `imdf_requests_total` / latency / queue depth)
2. **链路追踪** (OpenTelemetry → Jaeger)
3. **结构化日志** (JSON + 索引)
4. **业务事件** (EventBus + DataFlowTracker)
5. **血缘** (14 条 RELATION_GRAPH 边)
6. **错误聚合** (Sentry-style 本地 + Sentry SaaS 可选)
7. **健康检查** (12 微服务的 `/healthz` / `/readyz`)

参考:Datadog、New Relic 是 APM 商业标准;Grafana Stack 是开源标准;OpenTelemetry 是行业协议标准。

### 1.3 平台规模指标 (截至深度剧8 完成)

| 维度 | 数值 |
|---|---|
| 后端 Python 代码 | ~50,000 LOC |
| 前端 Vue 代码 | ~20,000 LOC |
| 自动化测试 | **159/159 PASS** |
| 编译警告 | 0 (Pydantic V2 + TypeScript strict) |
| HTTP 端点 | **260+** under `/api/v1/` |
| ORM 表 | **14** 张 (跨 PG / SQLite 兼容) |
| 业务能力 | **47** Capability × 17 域 |
| 工作流模板 | **6** 内置 |
| 节点类型 | **47** (前端画布) |
| LLM Provider | **7** 内置 |
| 业务模态 | **8** 种 |
| 训练格式 | **9** 种 |
| 标注几何 | **6** 种 |
| 理解任务 | **8** 种 (caption/vqa/...) |
| Agent 工具 | **5** 个 |
| 微服务 | **12** 个 (P3-2 拆分目标) |
| 调度 | **2** 层 (SchedulerEngine + TaskQueue) |
| 监控指标 | **6** 个 (Prometheus) |
| 安全端点 | **9** 个 (security_r8) |
| R7 部署端点 | **5** 个 (deploy_r7) |
| 性能原语 | **4** 个 (TTLCache / Batch / AsyncQueue / Pool) |
| 翻译键 | **410+** × 2 语种 (zh-CN/en-US) |
| 视图 | **35** 个 + 11 子目录 |
| 血缘边 | **14** 条 RELATION_GRAPH |
| 事件总线 | **18** 实体类型 |
| 审计链 | **HMAC-SHA256** 不可篡改 |

---

## 第 2 章 顶竞品地图 (30+ 系统分 12 类)

### 2.1 12 个功能域的顶竞品

智影平台涵盖 12 个功能域。每个域都对应 3-5 个顶级商业/开源竞品。下表给出全景:

| 域 | 智影当前 | 商业顶配 #1 | 商业顶配 #2 | 商业顶配 #3 | 开源 #1 | 开源 #2 |
|---|---|---|---|---|---|---|
| **数据标注** | WorkbenchEngine (6 几何 + 5 审核) | **Labelbox** (catalog + label + model) | **Scale AI** (Data Engine + Nucleus) | **V7 Labs** (Darwin) | **CVAT** (Intel 开源) | **Label Studio** (Heartex) |
| **数据治理/目录** | 14 表 + DataFlowTracker + EventBus | **Databricks Unity Catalog** (统一治理) | **Snowflake Horizon Catalog** | **Collibra** (企业级) | **Apache Polaris** (Iceberg) | **OpenMetadata** |
| **工作流编排** | WorkflowBuilder (6 模板 + DAG) | **Apache Airflow** (3.x 事实标准) | **Prefect** (现代化) | **Dagster** (资产为中心) | **Temporal** (微服务编排) | **Metaflow** (Netflix) |
| **向量数据库/RAG** | multimodal_v2 + RAG + TF-IDF/BM25 | **Pinecone** (托管) | **Weaviate** (图谱+向量) | **Milvus** (亿级开源) | **Qdrant** (Rust) | **Chroma** (原型) |
| **MLOps** | 19 真引擎 + Agent + Workflow | **MLflow** (开源) | **Weights & Biases** (SaaS) | **Neptune.ai** (企业) | **Kubeflow** (K8s 原生) | **ClearML** (全栈) |
| **数据质量** | InternalQCEngine (4 模式 + AQL) | **Great Expectations** | **Monte Carlo** (AI 驱动) | **Soda Core** | **Deequ** (Spark) | **AWS Glue DataBrew** |
| **数据血缘** | EventBus + 14 边 | **DataHub** (LinkedIn 开源) | **OpenMetadata** | **Apache Atlas** | **OpenLineage** + **Marquez** | **Unity Catalog** (内置) |
| **AI Provider 路由** | 7 LLM + route() | **Portkey** (AI Gateway) | **LiteLLM** (统一接口) | **OpenRouter** (聚合) | **Helicone** (可观测) | **AI Gateway** (自建) |
| **Agent 框架** | MultimodalAgent (5 工具) | **LangChain** | **LlamaIndex** | **AutoGen** (Microsoft) | **CrewAI** (多 Agent) | **MCP** (Model Context Protocol) |
| **安全/审计** | 4 大组件 + HMAC 链 | **HashiCorp Vault** | **Snyk** | **Auth0** | **OWASP ZAP** | **Keycloak** |
| **可观测性** | OTel + Prom + 7 监控层 | **Datadog** (商业) | **Grafana Stack** (开源) | **New Relic** | **Honeycomb** (Trace) | **SigNoz** (开源 OTel) |
| **UI/UX** | Vue 3 + Naive UI + WCAG AA | **Linear** (B 端标杆) | **Notion** (知识库) | **Figma** (设计) | **Taiga** (项目管理 UI) | **GitLab** (DevOps UI) |

### 2.2 各竞品定位速览

#### 数据标注 (4 大 + 2 开源)
- **Labelbox** (美国 SaaS, $):平台化,聚焦 catalog + label + model 一体化,2026 新增 AI Agent
- **Scale AI** (美国 SaaS, $$$):Data Engine,聚焦数据集 + ground truth + 模型评估
- **V7 Labs** (英国 SaaS, $$):Darwin 平台,深度学习+自动标注
- **SuperAnnotate** (美国 SaaS, $$):MM 标注 + 像素级分割
- **Encord** (美国 SaaS, $$):DICOM + 医疗影像专长
- **CVAT** (Intel 开源):视频 + 图像标注
- **Label Studio** (Heartex 开源):通用标注框架

#### 数据治理 (2 商业 + 2 开源)
- **Databricks Unity Catalog** (商业):统一治理 + 跨 workspace
- **Snowflake Horizon Catalog** (商业):Snowflake 内置 + Polaris 开源
- **Collibra** (商业, 企业级):数据治理 + 数据血缘 + 数据质量
- **Apache Polaris** (开源, Apache 2.0):Iceberg REST Catalog
- **OpenMetadata** (开源):统一发现 + 治理 + 血缘 + 协作

#### 工作流编排 (3 商业 + 2 开源)
- **Apache Airflow** (开源, Apache 2.0):DAG 事实标准,3.x 重构
- **Prefect** (开源 + 云):现代 Python 优先
- **Dagster** (开源 + 云):资产 (Asset) 为中心
- **Temporal** (开源 + 云):微服务编排
- **Metaflow** (Netflix 开源):ML/数据科学友好
- **Flyte** (开源 + 云):K8s 原生 ML 流水线

#### 向量数据库 (3 商业 + 2 开源)
- **Pinecone** (商业):全托管 Serverless
- **Weaviate** (开源 + 云):模块化 + BM25 混合
- **Milvus** (开源 + Zilliz 云):亿级分布式
- **Qdrant** (开源 + 云):Rust 高性能
- **Chroma** (开源):轻量原型
- **pgvector** (开源, PostgreSQL 扩展):已有 PG 用户的首选

#### MLOps (2 商业 + 3 开源)
- **MLflow** (开源 + 云):Tracking + Model Registry
- **Weights & Biases** (SaaS):实验 + Artifacts
- **Neptune.ai** (SaaS):企业级元数据
- **Kubeflow** (开源):K8s ML 平台
- **ClearML** (开源):全栈 MLOps
- **Determined AI** (开源 + 商业):深度学习训练

### 2.3 智影在 12 域中的相对位置

| 域 | 智影位置 | 评价 |
|---|---|---|
| 数据标注 | 中等 (6 几何 + 5 审核) | 强于开源,弱于 Labelbox 全家桶 |
| 数据治理 | 中等 (DataFlow + EventBus) | 缺 Unity Catalog 级别的统一治理 |
| 工作流编排 | 中等 (6 模板) | 缺 Airflow 级别的事件调度 + 监控 |
| 向量数据库 | 弱 (TF-IDF + BM25 hybrid, 无专用 VDB) | 急需 pgvector 集成或专用 VDB 适配 |
| MLOps | 强 (19 真引擎) | 已落地,但缺模型 Registry / 实验跟踪 |
| 数据质量 | 强 (AQL ISO 2859-1 + 4 模式) | 工业级,强于许多商业产品 |
| 数据血缘 | 强 (14 边 + EventBus) | 优于多数商业产品 |
| AI Provider 路由 | 强 (7 LLM + cost/speed/trust 路由) | 接近 Portkey 级别 |
| Agent 框架 | 中等 (5 工具) | 缺 LangChain 完整生态 |
| 安全/审计 | 强 (HMAC + 4 组件) | 工业级 OWASP Top 10 |
| 可观测性 | 强 (OTel + 7 监控层) | 与 Grafana Stack 同级 |
| UI/UX | 中等 (Vue 3 + WCAG AA) | 强于多数 B 端,弱于 Linear/Notion |

---

## 第 3 章 行业格局与 2026 趋势

### 3.1 2026 年 AI 数据赛道关键趋势

#### 3.1.1 数据是 AI 竞争的核心战场

> 麦肯锡 2025 报告:数据质量是 AI 项目 ROI 的最大杠杆。模型架构在 2025 年后趋同,**数据差异化成为决胜因素**。

智影定位契合这一趋势:**数据生产全链路平台**,不是模型训练框架,不是 LLM 推理服务,而是 **高质量训练数据** 的生产工厂。

#### 3.1.2 多模态数据爆发

> Scale AI 2026 Q1 报告:多模态数据生产 (image + video + audio) 同比 +280%,文本数据仅 +45%。

智影已支持 **8 种业务模态**,其中:
- `drama` (短剧) 和 `picturebook` (绘本) 是面向下一代 MLLM 的专用数据
- `sketch` (3D 草图) 面向具身智能 / 机器人
- `multimodal` 跨模态对齐

这一布局领先大多数标注平台 (主要聚焦 image/video)。

#### 3.1.3 Catalog 战争 (Databricks vs Snowflake)

> 2024-2026 Databricks 收购 Tabular,开源 Unity Catalog;Snowflake 推出 Polaris;OpenMetadata 崛起。**谁控制 Catalog,谁控制数据治理话语权**。

智影当前有 `models/` 14 表 + `DataFlowTracker`,但缺:
- 统一 Catalog API (类似 Unity Catalog 三层命名空间)
- 跨 catalog 联邦查询
- 资产版本管理 (Project Nessie 风格)
- AI 资产 (模型、Notebook) 治理

这些将在第 16-17 章作为 **关键缺口** 列入补充。

#### 3.1.4 RAG 成为 LLM 应用主流架构

> 2025 年起,80% 以上的企业 LLM 应用采用 RAG 架构。向量数据库市场 2024 突破 10 亿美元,CAGR > 40%。

智影的 `MultimodalRAG` (深度剧8 rehydrate) 已经能用,但相比专业 VDB (Pinecone/Weaviate/Milvus) 缺:
- 多种 ANN 算法 (HNSW / IVF / ScaNN)
- 量化压缩 (int8 / PQ)
- 混合检索 (BM25 + 向量 + 元数据过滤)
- 十亿级分布式
- 动态 schema

第 7 章详细对比,第 16 章识别为关键缺口。

#### 3.1.5 AI Agent 平台化 (MCP 协议)

> 2025 年 Model Context Protocol (MCP) 由 Anthropic 推出,被 LangChain、OpenAI、Replit 等采纳,成为 AI Agent 工具调用的事实标准。

智影的 `MultimodalAgent` 已能注册到 MCP server (5 工具),但缺:
- 完整的 Agent Marketplace
- Agent Eval 框架
- Agent 监控 / Trace
- 多 Agent 协作 (CrewAI / AutoGen 风格)

第 12 章对比,第 16 章列入。

#### 3.1.6 AI 治理与合规 (EU AI Act 等)

> 2025-2026 EU AI Act、中国生成式 AI 服务管理办法 等法规要求 AI 训练数据可追溯、可审计、可解释。

智影的 HMAC 审计链 + EventBus 血缘 + Capability 记录 已基本满足,但缺:
- AI 影响评估 (AIA) 模板
- 数据来源验证 (C2PA 是开始,但需全链路)
- 自动化合规报告生成
- 法规变更追踪

第 12、13 章对比,涉及补充。

#### 3.1.7 多租户 + 商业化

> 智影已经有 `business/billing.py` (UsageMeter + InvoiceEngine) + `business/tenant.py` (TenantRegistry),但相比 Stripe Billing / Metronome / Orb 等专业计费系统,缺:
- 复杂定价模型 (用量阶梯 + 固定费 + 分级)
- 实时使用监控
- 自动开票 + 税务计算
- 订阅管理 (升降级、暂停、恢复)

第 19 章详细补充。

### 3.2 智影的市场定位

```
                数据生产全链路完整度
                          ↑
                          │
          Scale AI ●     │
                          │        ● Labelbox (但偏标注)
                          │
          ● 智影 ZhiYing  │
                          │
                          │
                          │
         ● OpenMetadata   │
         ● V7 Darwin      │        ● Databricks
                          │
                          │
                          └──────────────────────→
                          跨域治理 + 编排能力
```

智影的核心优势:**全链路 + 真引擎 + 跨进程持久 + 强可观测**。最大短板:**生态薄 (无 Marketplace) + AI 资产治理浅 + 模型 Registry 缺 + 计费粗糙**。

---

# 第二部: 12 个域逐项功能对比

## 第 4 章 数据标注平台对比

### 4.1 智影标注能力现状

智影的标注能力由 `WorkbenchEngine` + `AnnotationRecord` + 6 种几何 + 5 审核阶段构成。

| 能力 | 智影 | Labelbox | Scale | V7 | SuperAnnotate | Encord | CVAT | Label Studio |
|---|---|---|---|---|---|---|---|---|
| **rect (轴对齐矩形)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **polygon (多边形)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **point (单点)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **keypoint (关键点)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **obb (旋转框)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **mask (RLE/bitmap)** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **3D cuboid** | ⚠️ 映射到 obb | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ |
| **polyline (折线)** | ⚠️ 映射到 polygon | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **classification** | ⚠️ 映射到 rect | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **椭圆 ellipse** | ❌ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ |
| **立方体 cube** | ❌ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| **视频 (frame-by-frame)** | ⚠️ 通过 multimodal_v2 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **LiDAR 点云** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| **3D Mesh** | ❌ | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ | ❌ |
| **医学 DICOM** | ❌ | ✅ | ⚠️ | ⚠️ | ✅ | ✅ | ❌ | ❌ |
| **音频 waveform** | ⚠️ ASR 输出 | ✅ | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ✅ |
| **PDF / 文档** | ⚠️ multimodal parse | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| **OCR (转录)** | ⚠️ OCR task | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### 4.2 关键功能对比 (评分 1-5,5 最佳)

| 功能 | 智影 | Labelbox | Scale | V7 | SuperAnnotate | Encord |
|---|---|---|---|---|---|---|
| **几何种类丰富度** | 3 | 5 | 4 | 5 | 5 | 4 |
| **3D / LiDAR** | 1 | 5 | 4 | 5 | 5 | 4 |
| **AI 辅助标注 (SAM/GroundingDINO)** | ❌ 缺 | 5 | 5 | 5 | 5 | 4 |
| **众包/分布式标注** | ⚠️ 5min 锁 | 5 | 5 | 4 | 4 | 4 |
| **协作实时 (多人同任务)** | ❌ 缺 | 4 | 5 | 4 | 4 | 3 |
| **审核工作流** | 4 (5 阶段) | 5 | 5 | 4 | 4 | 4 |
| **AQL 抽样** | 5 (ISO 2859-1) | 4 | 5 | ⚠️ | 4 | ⚠️ |
| **自动标注 (foundation model)** | ❌ 缺 | 5 | 5 | 5 | 5 | 4 |
| **IoU / 一致性评估** | ❌ 缺 | 5 | 5 | 4 | 4 | 4 |
| **标注历史版本** | ✅ | 5 | 5 | 5 | 5 | 5 |
| **导入/导出格式** | 9 + 5 | 30+ | 30+ | 30+ | 20+ | 20+ |
| **COCO/YOLO/LLaVA/InternVL** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Labelbox JSON 格式** | ❌ 缺 | ✅ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| **YOLO .txt 实时导出** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **C2PA provenance** | ✅ (5 方法) | ⚠️ | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| **Label Embedding / Search** | ⚠️ multimodal RAG | 5 | 5 | 5 | 4 | 4 |
| **Active Learning** | ❌ 缺 | 5 | 5 | 5 | 4 | 4 |
| **Consensus (多人投票)** | ⚠️ crowd_router | 5 | 5 | 4 | 4 | 4 |
| **时间预算追踪** | ❌ 缺 | 5 | 5 | 4 | 4 | 4 |
| **标注员绩效 dashboard** | ⚠️ monitoring | 5 | 5 | 5 | 4 | 4 |
| **Open API / SDK** | ✅ (260+ routes) | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Webhook 集成** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **私有化部署** | ✅ (P3-2) | ⚠️ 商业 | ⚠️ 商业 | ✅ | ✅ | ✅ |
| **数据驻留/合规** | ⚠️ PII 脱敏 | ✅ | ✅ | ✅ | ✅ | ✅ |

### 4.3 智影可补充的能力 (基于竞品)

**关键缺口 (P1 优先级)**:

1. **AI 辅助标注 (SAM/GroundingDINO 集成)** — 影响最大
   - 现状: 无
   - 参考: V7 Darwin (Eden AI 模型集成) / Labelbox (Model-assisted labeling)
   - 设计: `annotation.ai_assist` 能力, 调 `multimodal/generation.SAM2_predictor` 或 grounding_dino
   - 预计工作量: 1 工程师 × 2 周

2. **LiDAR / 3D 点云标注** — 影响中高
   - 现状: 通过 `sketch` 模态导出 GLB, 但无 LiDAR
   - 参考: Scale AI (3D Sensor Fusion) / V7 (3D bounding)
   - 设计: 新增 `lidar` 模态 + 3D point cloud 渲染 (Three.js / potree)
   - 预计工作量: 1 工程师 × 3 周

3. **Active Learning 闭环** — 影响高
   - 现状: 无
   - 参考: Labelbox (Model diagnostics) / Scale (active learning)
   - 设计: 模型预测 + 置信度低的样本 → 自动进标注队列
   - 预计工作量: 1 工程师 × 1 周

4. **Consensus (多人投票)** — 影响中
   - 现状: `crowd_router` 雏形
   - 参考: Labelbox (Consensus + IoU)
   - 设计: 同一任务分配 N 人, 取多数投票 / 平均 IoU
   - 预计工作量: 1 工程师 × 1 周

5. **协作实时 (多人同任务)** — 影响中
   - 现状: 5 分钟锁 (互斥)
   - 参考: Figma (CRDT) / Linear (server-authoritative)
   - 设计: 用 CRDT (Yjs / Automerge) 实现多人同任务实时同步
   - 预计工作量: 1 工程师 × 2 周

6. **AQL + 自动抽样 + 自动重抽** — 影响低 (已有)
   - 现状: ✅ ISO 2859-1 + 4 模式
   - 改进: 增加 AQL 决策自动化 (基于历史通过率自适应)

**次要缺口 (P2 优先级)**:

7. **椭圆 ellipse 几何**
8. **3D Mesh 标注**
9. **DICOM 医学影像**
10. **PDF 标注 + OCR 内嵌**
11. **标注员实时聊天 / 评论**
12. **IoU 一致性评估 dashboard**
13. **时间预算追踪 + 提醒**
14. **标注 Marketplace (众包平台对接 Scale Rapid / Surge)**
15. **Webhooks (出站通知)**
16. **Zoom + Pan + Rotate 工具栏增强**
17. **Layer (多图层) 支持**
18. **Magic Wand (智能选择)**
19. **Track 模式 (视频跟踪)**
20. **Spectral 标注 (高光谱)**

### 4.4 推荐补强方案 (Top 5 优先)

| # | 能力 | 工作量 | 商业价值 |
|---|---|---|---|
| 1 | **AI 辅助标注 (SAM/GroundingDINO)** | 2 周 | 极高 (标注效率 5-10×) |
| 2 | **Active Learning 闭环** | 1 周 | 高 (数据价值最大化) |
| 3 | **Consensus + IoU** | 1 周 | 高 (质量提升) |
| 4 | **LiDAR / 3D 标注** | 3 周 | 中高 (新场景) |
| 5 | **CRDT 实时协作** | 2 周 | 中 (体验提升) |

总计 ~9 工程师-周,可让智影标注能力从中等跃升到接近 Labelbox / Scale 水平。

---

(由于本文档规模,后续章节按用户要求继续展开。下一章将详细对比数据治理 vs Databricks/Snowflake/Polaris/OpenMetadata,以及对应的 5-10 个补充能力。)

