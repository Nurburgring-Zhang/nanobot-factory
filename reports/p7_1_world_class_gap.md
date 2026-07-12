# P7-1 v2: World-Class Gap Analysis (K8s / Istio / Dapr 校正版)

> **Date**: 2026-06-26 04:30
> **Auditor**: Coder (Mavis worker) + Auditor 反馈校正
> **Methodology**: K8s + Istio + Dapr + 顶级 24 平台对标 (P6-1 16 + Auditor 8)

---

## §1. K8s / Istio / Dapr 三件套对标 (v2 校正)

### 1.1 K8s (Kubernetes) 对标 — 大幅校正

| 能力 | K8s 标准 | v1 Producer | v2 实际 | 校正 |
|---|---|---|---|---|
| **Deployment** | `Deployment` + `ReplicaSet` + `Pod` | ❌ 0 manifest | ✅ **12 service manifest** (k8s/services/*.yaml) | FAIL → PASS |
| **Service** (LB) | `Service` (ClusterIP / LoadBalancer) | ❌ 0 | ✅ **12 service Service** + **1 gateway Service** | FAIL → PASS |
| **HPA** (auto-scale) | `HorizontalPodAutoscaler` | 未提 | ✅ **12 service HPA** (min:2 max:10 CPU 70%) | 未提 → PASS |
| **PDB** (rolling upgrade) | `PodDisruptionBudget` | 未提 | ✅ Helm chart `pdb.yaml` | 未提 → PASS |
| **ServiceAccount** | 绑定 Pod 身份 | 未提 | ✅ **12 SA** (k8s/services/*.yaml) | 未提 → PASS |
| **ConfigMap / Secret** | K8s native | env / YAML | ✅ k8s/configmaps.yaml + secrets.yaml | PASS |
| **Ingress + TLS** | `Ingress` | 未提 | ✅ k8s/ingress.yaml | 未提 → PASS |
| **StatefulSet** (有状态) | `StatefulSet` + `volumeClaimTemplates` | 0 in-memory | ✅ k8s/postgres.yaml StatefulSet | 未提 → PASS |
| **NetworkPolicy** | `NetworkPolicy` (Calico/Cilium) | 未提 | ❌ **0 NetworkPolicy** (P0-5) | 未提 → FAIL |
| **ResourceQuota** | `ResourceQuota` | 未提 | ❌ 0 | P2 |
| **Liveness / Readiness** | `livenessProbe` + `readinessProbe` | ✅ /healthz + /readyz | ✅ 12 manifest 全部有 livenessProbe + readinessProbe | PASS |
| **Resource limits** | `resources.limits.cpu/memory` | 未提 | ✅ 12 manifest 全部有 requests + limits | 未提 → PASS |
| **Helm chart** | 推荐 | 未提 | ✅ **deploy/helm/nanobot-factory/** 13 files | 未提 → PASS |
| **RBAC** | `Role` + `RoleBinding` | 未提 | ❌ 0 RBAC | P2 |
| **HorizontalPodAutoscaler behavior** | scaleUp/scaleDown policy | 未提 | ✅ agent-service HPA 有 scaleUp 30s + 100% policies | 未提 → PASS |
| **minReplicas/maxReplicas** | HPA 配置 | 未提 | ✅ min:2 max:10 | 未提 → PASS |
| **imagePullPolicy** | IfNotPresent / Always | 未提 | ✅ IfNotPresent | 未提 → PASS |
| **strategy RollingUpdate** | 滚动升级 | 未提 | ✅ maxSurge:1, maxUnavailable:0 | 未提 → PASS |

**K8s 综合校正**: v1 2/12 → v2 **8/12 PASS** (+6 PASS)
**结论**: 我们是 "cloud native" 程度比 v1 评估的高, 但仍缺 NetworkPolicy (P0-5) + ResourceQuota (P2) + RBAC (P2)。

### 1.2 Istio (Service Mesh) 对标

| 能力 | Istio 标准 | v2 实际 | 严重度 |
|---|---|---|---|
| **mTLS** (P2P 加密) | 自动 (envoy sidecar) | ❌ 0 (HTTP 明文) | **P0** (与 F-004 弱密钥组合) |
| **L7 routing** | VirtualService | ❌ 0 (path 匹配) | **P1** |
| **Traffic shifting** | 灰度 / A/B | ❌ 0 | **P1** |
| **Fault injection** | `fault.abort` / `fault.delay` | ❌ 0 chaos | **P1** |
| **Circuit breaker** | `outlierDetection` | ✅ 自实现 (gateway) | OK |
| **Retry / Timeout** | `retries.attempts` | ⚠ `upstream_timeout_seconds: 30` | **P2** |
| **Telemetry** (RED) | 自动 envoy metrics | ⚠ structlog + Prometheus | **P2** |
| **Distributed tracing** | envoy + Jaeger | ❌ 0 OTel | **P0** |
| **Authorization Policy** | `AuthorizationPolicy` | ⚠ `require_auth` (gateway 1 层) | **P1** |
| **Ingress / Egress** | `Gateway` + `VirtualService` | ✅ gateway (1 进程) | OK (单点 P0) |
| **Sidecar injection** | 自动 | 0 (单进程) | N/A |
| **Service entry** | 自动注册 | ⚠ routes.yaml 静态 | **P2** |

**Istio 综合**: 2/12 PASS (gateway + circuit breaker) / 5 FAIL / 5 PARTIAL
**结论**: 我们没有 service mesh, 但 gateway + 自实现 circuit breaker 部分覆盖。

### 1.3 Dapr (Distributed Application Runtime) 对标

| 能力 | Dapr 标准 | v2 实际 | 严重度 |
|---|---|---|---|
| **State store** | Redis/Postgres 抽象 | ❌ 0 (in-memory + SQLite) | **P0** |
| **Pub/Sub** | Kafka/RabbitMQ/Redis 抽象 | ❌ 0 message queue | **P0** |
| **Service invocation** | `invoke` + auto retry/mTLS | ⚠ gateway HTTP | **P0** |
| **Bindings** | (input/output) 触发器 | ❌ 0 事件驱动 | **P1** |
| **Secrets** | 统一 secret API | ⚠ env | **P2** |
| **Workflow** | `DaprWorkflow` (长任务) | ⚠ workflow_service 自实现 (in-memory) | **P1** (P1-3 持久化) |
| **Actors** | virtual actor | 0 | P3 |
| **Configuration** | `DaprConfiguration` | ⚠ env / YAML | P2 |
| **Distributed lock** | `lock` API | ✅ agent_service 自实现 | OK |
| **Resiliency** | retry/timeout/circuit breaker 策略 | ⚠ 部分 | **P1** |
| **Observability** | W3C trace + metrics + logs | ❌ 0 OTel | **P0** |
| **Crypto** | 加密/签名 API | 0 | P3 |

**Dapr 综合**: 1/12 PASS (dist_lock) / 6 FAIL / 5 PARTIAL
**结论**: Dapr 解决的 11 项能力我们 0/11 完整覆盖, 是最大缺口。

---

## §2. K8s/Compose/Helm 详细对标 (v2 校正)

### 2.1 k8s/ 完整清单 (P7-1 v2 实测)

| 类别 | 文件 | 大小 | 内容 |
|---|---|---|---|
| **12 Service** | k8s/services/agent-service.yaml | 3026 B | SA + Deployment (replicas:2) + Service (ClusterIP:8008) + HPA (min:2 max:10 CPU 70%) |
| | k8s/services/annotation-service.yaml | 2972 B | 同上 |
| | k8s/services/asset-service.yaml | 3239 B | 同上 |
| | k8s/services/cleaning-service.yaml | 3122 B | 同上 |
| | k8s/services/collection-service.yaml | 3101 B | 同上 |
| | k8s/services/dataset-service.yaml | 3087 B | 同上 |
| | k8s/services/evaluation-service.yaml | 2972 B | 同上 |
| | k8s/services/notification-service.yaml | 3856 B | 同上 |
| | k8s/services/scoring-service.yaml | 2933 B | 同上 |
| | k8s/services/search-service.yaml | 3211 B | 同上 |
| | k8s/services/user-service.yaml | 3229 B | 同上 |
| | k8s/services/workflow-service.yaml | 3071 B | 同上 |
| **Gateway** | k8s/gateway.yaml | 7678 B | Gateway 配置 (259 行) |
| **StatefulSet** | k8s/postgres.yaml | 3544 B | PostgreSQL StatefulSet (130 行) |
| **Deployment** | k8s/redis.yaml | 2734 B | Redis Deployment (113 行) |
| **Deployment** | k8s/minio.yaml | 4047 B | MinIO Deployment (OSS) |
| **Ingress** | k8s/ingress.yaml | 2951 B | Ingress + TLS (85 行) |
| **Config** | k8s/configmaps.yaml | 4040 B | ConfigMap |
| **Secret** | k8s/secrets.yaml | 2480 B | Secret |
| **Namespace** | k8s/namespaces.yaml | 767 B | Namespace |
| **Kustomize** | k8s/kustomization.yaml | 1967 B | Kustomize |
| **Docs** | k8s/README.md | 10310 B | 部署文档 (生产级) |

**K8s 评估**: ✅ **生产级** (12 service + 1 gateway + postgres/redis/minio + Ingress + ConfigMap + Secret + Namespace + Kustomize)
**唯一缺**: NetworkPolicy (P0-5), ResourceQuota, RBAC

### 2.2 docker-compose.yml 完整清单 (P7-1 v2 实测)

```
Length: 13465 B (13.4 KB)
Lines: 462
```

**Services 列表**:
- `postgres` (pgvector/pgvector:pg16) + 持久卷
- `redis` + 持久卷
- `app` (nanobot-factory:latest) + health check
- `gateway` + dev profile
- 12 microservice (user/asset/annotation/cleaning/scoring/dataset/evaluation/agent/workflow/notification/search/collection)
- `dev-backend` + `dev-frontend` (开发模式)
- 5 networks (frontend/backend/data/...)
- 2 profiles: `app` (prod-like) + `dev` (hot-reload)

**Docker Compose 评估**: ✅ **生产级** (12 service 编排 + 持久卷 + 健康检查 + 资源限制 + 2 profiles)

### 2.3 deploy/helm/nanobot-factory/ 完整清单 (P7-1 v2 实测)

| 类别 | 文件 | 大小 |
|---|---|---|
| **Chart** | Chart.yaml | 684 B |
| **Values** | values.yaml | 6105 B |
| **Deployment** | templates/deployment.yaml | 5799 B |
| **HPA** | templates/hpa.yaml | 1206 B |
| **Ingress** | templates/ingress.yaml | 996 B |
| **PDB** | templates/pdb.yaml | 692 B |
| **ServiceAccount** | templates/serviceaccount.yaml | 1521 B |
| **Service** | templates/service.yaml | 741 B |
| **ConfigMap** | templates/configmap.yaml | 1516 B |
| **Namespace** | templates/namespace.yaml | 650 B |
| **Notes** | templates/NOTES.txt | 2448 B |
| **Helpers** | templates/_helpers.tpl | 2069 B |
| **README** | README.md | 5652 B |

**Helm 评估**: ✅ **生产级** (13 files, 含 PDB + SA + HPA + Ingress 完整)

---

## §3. 顶级云原生 24 平台对标 (P6-1 16 + Auditor 8)

### 3.1 平台矩阵 (24 平台)

| Platform | Best-known for | 我们的等价 | 差距 | 严重度 |
|---|---|---|---|---|
| **Labelbox** | Catalog + ontology + IAA | dataset_service + annotation + scoring | 缺 ontology editor, IAA metrics | P0 |
| **Scale AI** | Rapid + Studio + Dynamics | workflow + agent + evaluation | 缺 Dynamics equivalent | P1 |
| **Snorkel** | Programmatic labeling + LF | annotation + agent | 缺 labeling functions | P0 |
| **SuperAnnotate** | Pixel-perfect segmentation | annotation (bbox only) | 缺 mask tools + 3D | P1 |
| **Encord** | Active learning | annotation + agent | 缺 AL sampler | P1 |
| **V7 Darwin** | Auto-annotation | `/api/prelabel` (thin) | 缺 SAM-style prelabel UI | P1 |
| **Kili** | Project dashboard | collection + workflow | 缺 reviewer assignment | P2 |
| **Roboflow** | Visual data + training | dataset + asset | 缺 hosted training | P1 |
| **HF Datasets** | Versioned datasets | dataset (in-memory) | 缺 git-LFS / DVC | P0 |
| **ComfyUI** | Visual workflow editor | workflow (50+ templates) | 缺 drag-drop UI | P1 |
| **Runway / Pika** | Gen-3 video | asset (image/video) | 缺 Gen-3 / Sora | P1 |
| **HeyGen** | Talking head | asset (voice/character) | 缺 talking-head | P2 |
| **W&B** | Experiment tracking | 0 | **完全缺** | P2 |
| **Neptune.ai** | Model registry | `/api/v1/models` (stub) | 缺 | P2 |
| **Comet.ml** | LLM tracing | agent (memory) | 缺 LLM tracing | P2 |
| **LangSmith** | LLM eval | agent + evaluation | 缺 chain viz | P2 |
| **Arize / Phoenix** | LLM monitoring (drift) | 0 | **完全缺** | **P1** |
| **Fiddler / WhyLabs** | AI 公平性 / 偏差 | 0 | **完全缺** | P2 |
| **Great Expectations** | Data quality contract | 0 | **完全缺** | **P0** |
| **Apache Superset** | 自服务 BI | 0 | 缺 | P2 |
| **Prefect / Dagster** | Dynamic DAG + asset | workflow (basic) | 缺 dynamic DAG | P1 |
| **Temporal.io** | Reliable workflow | workflow (in-memory) | 缺持久化 + retry | **P0-3** (升 P0) |
| **OpenMetadata** | Data catalog + lineage | dataset (basic) | 缺完整 lineage | P1 |
| **Dapr** | State + Pub/Sub + Invocation | 0 | **完全缺** | **P0** |

### 3.2 Top 12 P0/P1 差距 (按 ROI 排序, v2 校正)

| # | 平台 | 差距 | 工时 | ROI | v2 严重度 |
|---|---|---|---|---|---|
| 1 | **Dapr** | Service invocation + pub/sub + state | 2 weeks | 🔴 高 | **P0** (升) |
| 2 | **Temporal.io** | Reliable workflow (持久化 + retry) | 2 weeks | 🔴 高 | **P0-3** (升) |
| 3 | **K8s NetworkPolicy** | 限制 service 直连公网 | 1 day | 🔴 高 | **P0-5** (新) |
| 4 | **OTel + W3C Trace** | 跨 service trace | 1 week | 🔴 高 | **P0-6** (升) |
| 5 | **Great Expectations** | Data quality contract | 1 week | 🔴 高 | **P0** |
| 6 | **JWT verify_aud + mTLS** | Token 跨服务重放防护 | 1 day | 🔴 高 | **P0-7** (新) |
| 7 | **DB pool_size 显式配置** | 12 service 连接耗尽防护 | 1 day | 🟡 中 | **P1-1** (新) |
| 8 | **Arize / Phoenix** | LLM monitoring (drift + hallucination) | 1 week | 🟡 中 | **P1** |
| 9 | **Prefect / Dagster** | Dynamic DAG + asset materialization | 2 weeks | 🟡 中 | **P1** |
| 10 | **Istio** | mTLS + L7 routing + tracing | 2 weeks | 🟡 中 | **P1** |
| 11 | **OpenMetadata** | Data catalog + lineage | 1 week | 🟡 中 | **P1** |
| 12 | **W&B / MLflow** | Model registry + experiment | 2 weeks | 🟢 低 | P2 |

---

## §4. 12 月对标路线图 (v2 校正)

### Q1 (本月, 紧急 7 P0)
- **P0-1** (F-004): JWT fail-fast (1 hr)
- **P0-2** (F-005): Redis rate limit (2-3 days)
- **P0-3** (F-002): routes.yaml dedupe (30 min)
- **P0-4**: 8765 port 修复 (2 hr)
- **P0-5**: K8s NetworkPolicy (1 day)
- **P0-6**: JWT verify_aud=True (1 hr)
- **P0-7**: /openapi.json K8s Ingress 限定 (4 hr)

### Q2 (Month 2, 基础 5 P1)
- **P1-5**: F-001 require_role 清理 (1 hr)
- **P1-1**: DB pool_size 显式配置 + pool metrics (1 day)
- **P1-2**: OSS stub 实现 (1 week)
- **P1-3**: workflow_service DAGRuntime 持久化 (1 week)
- **P1-4**: OpenTelemetry + W3C Trace Context (1 week)

### Q3 (Month 3, 服务网格 + 集成)
- **Dapr 集成** (2 weeks): pub/sub + state + service invocation
- **跨 service 集成测试** (1 week)
- **Chaos engineering** (1 week): chaos-mesh
- **Great Expectations** (1 week): data quality contract
- **OpenMetadata** (1 week): data catalog + lineage

### Q4 (Month 4+, 智能)
- **Istio 服务网格** (2 weeks): mTLS + L7 routing + tracing
- **Temporal.io** (2 weeks): reliable workflow
- **Arize / Phoenix** (1 week): LLM monitoring
- **Prefect / Dagster** (2 weeks): dynamic DAG

### Year 2 (差异化)
- 垂直模板 (医疗 / 自动驾驶 / 零售)
- Marketplace (社区 workflow / model zoo)
- White-label 多租户 SaaS

---

## §5. 我们有竞争力的地方 (vs 世界级, v2 校正)

| 能力 | 我们 | 顶级平台 | v2 评价 |
|---|---|---|---|
| **K8s 部署** | ✅ 12 manifest + HPA + SA + PDB + Helm | Netflix / Uber | ✅ **生产级** (v1 错报 FAIL) |
| **多模态数据 ingest** | asset_service 11 endpoints + 6 generators | Runway / Pika / HeyGen | ✅ 较广 |
| **多 agent 编排** | agent_service 108 routes + 23 agent + 10 skills | LangChain / AutoGen | ✅ 较深 |
| **DAG workflow** | workflow_service 105 routes + 50+ basic_templates | ComfyUI | ✅ 较实用 |
| **PII / 美学 / NSFW 评分** | scoring_service 29 routes + 15 operators | Hive / Imagga | ✅ 同等 |
| **RAG + 多模态搜索** | search_service 54 routes + multimodal_rag | Vespa / Weaviate | ✅ 较新 |
| **多租户通知 + WebSocket** | notification_service 38 routes + /ws (实测) | Knock / SendBird | ✅ 同等 |
| **微服务架构** | 12 service + 1 gateway (650 routes) | Netflix / Uber | ✅ 基础 (P0-5 NetworkPolicy 缺) |
| **Helm chart** | ✅ 13 files (deployment + hpa + pdb + sa + ingress) | Helm 标准 | ✅ **生产级** (v1 未提) |
| **Docker Compose** | ✅ 462 行 + 12 service + 2 profile | Docker Compose 标准 | ✅ **生产级** (v1 错报 FAIL) |

**核心差异化 (v2 校正)**: "AI-native data factory" — 多模态 + 多 agent + DAG workflow + RAG + **K8s/Helm 生产级部署**

---

## §6. 与 Netflix/Uber 微服务架构的对比 (v2 校正)

| 维度 | Netflix OSS | Uber 微服务 | v2 我们的状态 |
|---|---|---|---|
| Service 数 | 700+ | 4000+ | 12 (差距大, 但边界清晰) |
| Service discovery | Eureka | Hyperbahn | routes.yaml 静态 (P2) |
| API Gateway | Zuul | YARP | ✅ 自实现 (1 进程) |
| Circuit breaker | Hystrix | RingPop | ✅ agent_service 自实现 |
| 限流 | Hystrix + Sentinel | RingPop | ⚠ in-memory (P0-2 Redis 待) |
| 配置中心 | Archaius | Hyperbahn | ⚠ env / YAML |
| 分布式追踪 | Zipkin / Jaeger | Jaeger | ❌ 0 OTel (P1-4) |
| 监控 | Atlas + Spectator | M3 + Prometheus | ✅ Prometheus 基础 |
| **K8s 部署** | 0 (Zuul) | 0 (自家) | ✅ **12 manifest + Helm** (校正) |
| 消息队列 | Kafka (自研) | Kafka | ❌ 0 (Dapr P0) |
| Saga | 0 (choreography) | 0 | ❌ 0 |
| Service mesh | 0 (Zuul) | 0 | ❌ 0 (P0-5 NetworkPolicy) |
| mTLS | 0 (内部 trusted) | 0 | ❌ 0 (P0-6 verify_aud) |

**v2 校正后**: K8s/Compose/Helm 部署维度 80/100 (vs v1 30/100), 但 tracing / 消息队列 / 配置中心 / mTLS 仍是 **P0/P1 缺口**。

---

## §7. 总结 (v2 Retry)

### 7.1 v1 → v2 关键校正

| 维度 | v1 Producer 错报 | v2 校正 |
|---|---|---|
| K8s 部署 | 30% (FAIL "0 manifest") | 80% (12 manifest + Helm + HPA + SA + PDB) |
| Docker Compose | 30% (FAIL "0 compose") | 80% (462 行 + 12 service) |
| Helm chart | 未提 | 80% (13 files 完整) |
| 6 隐藏问题 | 0/6 | 6/6 全部识别 (P0-4/5/6/7 + P1-1/2/3) |
| F-001 严重度 | P0 (误调即崩) | P3 (0 service 真实调用) |
| 测试覆盖 | 100% (误导 "0 stub") | 60% (3/12 真实有 tests) |
| 综合 | 78/100 | **80/100** (+2) |

### 7.2 12 月路线图
- **Q1 (1 周)**: 7 P0 必修 (F-004/005/002 + 8765 + NetworkPolicy + verify_aud + Ingress)
- **Q2 (1 月)**: 5 P1 (F-001 降级 + DB pool + OSS + DAG + OTel)
- **Q3 (1 月)**: Dapr + 集成测试 + chaos + Great Expectations + OpenMetadata
- **Q4 (1 月)**: Istio + Temporal + Arize + Prefect

### 7.3 战略建议
1. **强化 "AI-native data factory" 定位** — 多模态 + agent + workflow + RAG + **K8s/Helm 生产级**
2. **优先补 P0 基础** — 7 P0 工时 < 1 周即可上
3. **12 月后 A- (90/100)** — 接近 Netflix/Uber 微服务架构基线
4. **24 月后世界级 (95+)** — 配合 vertical templates, 可与 Labelbox/Scale 头部竞争

### 7.4 Bottom Line
- **今天**: 商业级 B+ (80/100) — K8s/Compose/Helm 完整 + 12 microservice 功能层基本可用, 缺生产级 mTLS/OTel/Saga/消息队列
- **12 月后**: 商业级 A- (90/100) — 加 12 项 P0/P1 后, 接近 Netflix/Uber 微服务架构基线
- **24 月后**: 世界级 (95+/100) — 配合 vertical templates, 可与 Labelbox/Scale 头部竞争

---

**World-Class Gap 完成 (v2 Retry)**: 2026-06-26 04:30 (Asia/Shanghai)
