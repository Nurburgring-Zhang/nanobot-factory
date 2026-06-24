# Architecture — Nanobot Factory

> 适用于 **架构师 / 高级开发 / SRE**。本文档描述系统边界、模块依赖、数据流和关键时序。
> 配合 `docs/api.md` 与源码阅读效果最佳。

---

## 1. 系统鸟瞰

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          Nanobot Factory Platform                          │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌────────────────────┐  ┌────────────────────┐  ┌──────────────────────┐  │
│  │  Web UI (Vue 3)    │  │ Electron Desktop   │  │ Mobile / 3rd-party   │  │
│  │  Element Plus      │  │ (React 18 + Vite)  │  │ via OpenAPI SDK      │  │
│  │  ECharts + Day.js  │  │ Live2D / Pixi / 3D │  │                      │  │
│  └──────────┬─────────┘  └──────────┬─────────┘  └──────────┬───────────┘  │
│             │                       │                       │              │
│             └───────────────────────┴───────────────────────┘              │
│                                    │                                       │
│                                    │  HTTPS / WSS                          │
│                                    ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    nginx (reverse proxy + static)                    │  │
│  │  /healthz, /readyz, /metrics, /api/*, /airi/*, /omni/*, /ws/*       │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                       │
│                                    ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                      FastAPI  (uvicorn, ASGI)                        │  │
│  │  ┌───────────────┬───────────────┬────────────────┬──────────────┐  │  │
│  │  │  IMDF routes  │ Agent routes  │ AIGC routes    │ Admin routes │  │  │
│  │  │  /canvas/*    │ /airi/*       │ /omni/*        │ /api/admin/* │  │  │
│  │  └───────────────┴───────────────┴────────────────┴──────────────┘  │  │
│  │                                                                       │  │
│  │  Middleware: CORS · RateLimit · Robustness · Auth (APIKey/JWT) ·     │  │
│  │             Prometheus · RequestID · Logging                         │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│       │           │            │           │            │          │        │
│       ▼           ▼            ▼           ▼            ▼          ▼        │
│   ┌────────┐ ┌────────┐  ┌─────────┐ ┌─────────┐  ┌─────────┐ ┌────────┐  │
│   │ SQLite │ │ FileSys│  │ Master  │ │ ComfyUI │  │ Redis   │ │ GPU    │  │
│   │  DB    │ │  Local │  │ Agent   │ │ (HTTP)  │  │ cache   │ │ monitor│  │
│   └────────┘ └────────┘  └─────────┘ └─────────┘  └─────────┘ └────────┘  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

部署形态分两种：
- **桌面端 (Electron)** — 内嵌浏览器 + localhost 后端，单用户离线可用。
- **服务端 (Web / K8s)** — 多用户共享后端集群，支持横向扩展。

---

## 2. 模块清单

| 模块 | 路径 | 职责 | 关键依赖 |
|------|------|------|----------|
| `server.py` | `backend/server.py` | FastAPI 实例、中间件、路由注册、lifecycle | uvicorn, fastapi |
| `imdf/api/` | `backend/imdf/api/` | 画布 / 标注 / 模板 / 3D / 云存 / Figma / 版权 / 隐私 | imdf.core, imdf.data |
| `imdf/core/` | `backend/imdf/core/` | 标注引擎、模板引擎、版本管理 | sqlalchemy, PIL |
| `imdf/data/` | `backend/imdf/data/` | 数据访问层 (DAO / Repository) | sqlalchemy, aiosqlite |
| `nanobot_factory/` | `backend/nanobot_factory/` | Agent Cluster、调度器、任务队列 | apscheduler, asyncio |
| `omni_gen_studio/` | `backend/omni_gen_studio/` | ComfyUI 适配、Prompt 解析 | httpx |
| `monitor/` | `backend/monitor.py` | GPU / 内存 / 磁盘监控 | pynvml, psutil |
| `task_queue/` | `backend/task_queue.py` | 异步任务执行 + 进度回报 | asyncio.Queue |
| `healthz.py / readyz.py` | `backend/imdf/api/` | Kubernetes 风格探针 | — |

每个模块按 **routes → services → repositories** 三层切分，禁止跨层调用。

---

## 3. 数据流

### 3.1 数据生产主链路 (Producer → Consumer)

```
User
 │  1. 拖拽节点到画布
 ▼
[Web UI] ──── WS /canvas/ws ────► [canvas_manager.py]
                                       │
                                       │  2. 持久化到 canvas_state table
                                       ▼
                                  [SQLite / data/imdf.db]
                                       │
                                       │  3. Plan 调用
                                       ▼
                       [Master Agent] ──► LLM (DeepSeek)
                                       │
                                       │  4. 输出 DAG
                                       ▼
                          [engine/plan] ──► engine/render
                                       │
                                       │  5. 提交 batch 任务
                                       ▼
                            [TaskQueue] ──► ComfyUI (HTTP)
                                                │
                                                │  6. 进度回调
                                                ▼
                              [WebSocket push → Web UI]
                                       │
                                       │  7. 产物落盘
                                       ▼
                              [data/outputs/{task_id}/]
```

### 3.2 标注工作流

```
uploader ──► upload()  ──► StorageService (sha256 + path)
                          │
                          ▼
                      DB: assets table
                          │
                          ▼
                  annotator_1 ──┐
                  annotator_2 ──┼──► annotations table (versioned)
                  annotator_N ──┘
                          │
                          ▼
                  reviewer ──► approval table
                          │
                          ▼
                  export ──► COCO / YOLO / VOC
```

---

## 4. 关键时序

### 4.1 健康检查

```
k8s livenessProbe (every 20s)
        │
        ▼  HTTP GET /healthz
   nginx ──── proxy_pass ────► uvicorn
                                  │
                                  ▼
                            healthz.py:
                              status = process_alive
                              return {"status":"ok", "uptime":...}
        │
        ▼ 200 OK / fail
   restart if fail ≥ 3 times
```

### 4.2 WebSocket 画布协同

```
Client A ──► WS connect ──► ConnectionManager.add(client_id)
Client B ──► WS connect ──► ConnectionManager.add(client_id)
                              │
A: send {op:"add_node", ...} │
                              ▼
                       broadcast({op:"add_node", ...})  ◄──┐
                              │                            │
                              ▼                            │
                       persist to DB ──────────────────────┘
                              │
                              ▼
                B receives diff and re-renders
```

### 4.3 AIGC 渲染任务

```
Web UI ─► POST /omni/render {prompt, params, batch_size=N}
              │
              ▼
       enqueue Task {id, status="queued"}
              │
              ▼
       TaskExecutor.pick() ──► ComfyUI POST /prompt
              │
              │  poll status (every 1s, timeout 5min)
              ▼
       progress 0..100  ──► WS push {task_id, progress}
              │
              ▼
       done  ──► download outputs ──► write to data/outputs/{id}/
              │
              ▼
       Task {status="completed", artifacts=[...]}
```

---

## 5. 部署拓扑

### 5.1 单机 (docker compose)

```
              ┌──────────────────────────────┐
              │   host:8080                  │
              │   docker compose             │
              │  ┌─────────────────────────┐ │
              │  │ app (nginx + uvicorn)  │ │
              │  └─────────────────────────┘ │
              │  ┌─────────────────────────┐ │
              │  │ redis                   │ │
              │  └─────────────────────────┘ │
              │   volumes: data / logs       │
              └──────────────────────────────┘
```

### 5.2 集群 (K8s / Helm)

```
┌─────────────────────────────────────────────────────────────┐
│  Ingress (nginx-ingress + cert-manager)                     │
│   │                                                          │
│   ▼                                                          │
│  Service (ClusterIP, session affinity for /ws)               │
│   │                                                          │
│   ▼                                                          │
│  Deployment (replicas: 2, HPA: 2..10)                        │
│   │                                                          │
│   ├─ Pod 1 (nginx + uvicorn)                                 │
│   │     ├─ PVC data (50Gi)                                   │
│   │     └─ PVC logs (20Gi)                                   │
│   └─ Pod 2 (nginx + uvicorn)                                 │
│         ├─ PVC data (50Gi)                                   │
│         └─ PVC logs (20Gi)                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 关键设计决策

| 决策 | 原因 |
|------|------|
| **FastAPI + uvicorn** | 异步 IO / OpenAPI 自动生成 / Pydantic 校验 |
| **SQLite (默认) + 可切 Postgres** | 单文件零运维；多副本场景切到 PG 用 Row-Level Lock |
| **WebSocket 而非 SSE** | 双向：客户端可发送 ack / 取消；断线重连语义清晰 |
| **Master Agent + DAG** | 复杂任务拆解为 DAG 节点，便于重试 / 跳过 / 缓存 |
| **读多写少 → Redis cache** | 模板列表 / 用户权限热数据 60s TTL |
| **同容器跑 nginx + uvicorn** | 镜像只一个 Pod 1 个容器；简化 sidecar 拓扑 |
| **readOnlyRootFilesystem + 非 root** | 满足 PSP / PSA restricted 基线 |
| **裸 manifest + Helm chart 双轨** | 学习场景用裸 YAML；生产用 Helm values 覆盖 |

---

## 7. 性能基线

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| `/healthz` p99 | < 5ms | 内置 metrics |
| 静态首页 p99 | < 100ms | nginx access_log + Prometheus |
| 普通 API p99 | < 200ms | 内置 metrics |
| ComfyUI 渲染 | 由 ComfyUI 决定 | task.progress WS 推送 |
| WebSocket 并发 | 5,000 / pod | Locust 压测 |
| GPU 利用率 | 60–80% | `nvidia-smi` exporter |

---

## 8. 安全架构（详见 docs/security.md）

- 鉴权：API Key (X-API-Key header) + 可选 JWT (Bearer)
- 速率限制：slowapi，100 req/min 默认，可按 route 调
- CORS：精确 allowlist，不开 `*`
- CSRF：纯 token (Bearer)，无需 CSRF cookie
- 注入：所有 SQL 用 ORM，所有 shell 调用走 subprocess + shell=False
- 文件上传：MIME sniff + size limit + 路径白名单
- 密钥：全部走环境变量，运行时不在 `/proc/1/environ` 之外暴露

---

_最后更新：2026-06-21 — 适用版本 appVersion 1.0.0_