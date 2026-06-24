# Nanobot Factory

> AIGC 数据生产与管理平台 — FastAPI 后端 + Vue 3 / React 18 Web UI + Electron 桌面端
>
> _Infinite Multimodal Data Foundry (IMDF) · 智影数据工场_

[![CI](https://github.com/MiniMax-AI/nanobot-factory/actions/workflows/ci.yml/badge.svg)](https://github.com/MiniMax-AI/nanobot-factory/actions/workflows/ci.yml)
[![CD](https://github.com/MiniMax-AI/nanobot-factory/actions/workflows/cd.yml/badge.svg)](https://github.com/MiniMax-AI/nanobot-factory/actions/workflows/cd.yml)
[![Helm](https://img.shields.io/badge/Helm-0.1.0-blue)](./deploy/helm/nanobot-factory)
[![License](https://img.shields.io/badge/License-MIT-green)](./LICENSE)

Nanobot Factory 是一个一站式的多模态数据生产平台，覆盖 **采集 → 标注 → 质检 → 训练样本导出**
全流程。内置 Master Agent 编排引擎，可对接 ComfyUI / Diffusers / 自研模型后端；提供无限画布 (Infinite
Canvas) 协作、3D 场景管理、Prompts 模板库、版权审计、数据脱敏等模块。

## ✨ 主要特性

| 模块 | 能力 |
|------|------|
| **数据画布** | 拖拽式无限画布、WebSocket 实时协同、节点 + 连线 + 图层管理 |
| **Master Agent** | 基于 LLM 的任务分解与执行编排（DeepSeek / 本地模型） |
| **AIGC 工作台** | ComfyUI 集成、Prompt 模板库、参数化 batch 渲染 |
| **3D 场景** | Three.js 场景管理、LOD / GLTF 资产导入导出 |
| **标注系统** | 矩形 / 多边形 / 关键点 / 语义分割 / OBB 五种标注 + IAA 一致性校验 |
| **质检 / 审计** | 多 reviewer 工作流、版权检测、隐私字段脱敏 |
| **数据导出** | COCO / YOLO / Pascal VOC / 自定义 schema、增量导出 |
| **运维面板** | GPU 监控、任务队列、Cluster Scheduler、Prometheus 指标 |
| **多端** | Web (Vue 3) / Electron 桌面 / 命令行 |

## 🚀 快速开始 (本地开发)

### 前置依赖
- Python ≥ 3.10
- Node.js ≥ 20
- (可选) Docker ≥ 24, Docker Compose v2

### 5 步启动

```bash
# 1. 克隆 & 准备
git clone https://github.com/MiniMax-AI/nanobot-factory.git
cd nanobot-factory

# 2. Python 依赖
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements_full.txt

# 3. Node 依赖
npm install

# 4. 启动后端 (端口 8001)
cd backend && python -m uvicorn server:app --reload --port 8001
# 4'. 启动前端 (端口 5173) — 在另一个终端
npm run dev

# 5. 打开浏览器
# http://localhost:5173      → Web UI (Vue 3)
# http://localhost:5173/airi → Canvas 工作台
# http://localhost:8001/docs → OpenAPI 文档
```

### 一键 Docker 启动

```bash
# 生产模式
docker compose up -d
# open http://localhost:8080

# 开发热重载
docker compose --profile dev up
```

## 📦 部署

| 方式 | 命令 | 适用 |
|------|------|------|
| **本地** | `python -m uvicorn backend.server:app` | 开发 |
| **Docker** | `docker compose up` | 单机 / 小团队 |
| **K8s (裸 manifest)** | `kubectl apply -f deploy/k8s/` | 学习 / 调试 |
| **Helm** | `helm install nanofab ./deploy/helm/nanobot-factory` | 生产 |
| **CI/CD** | `.github/workflows/cd.yml` | 自动化 |

详细的部署矩阵、参数调优、回滚策略见 **[docs/deployment.md](./docs/deployment.md)**。

## 📚 文档

| 文档 | 内容 |
|------|------|
| [docs/architecture.md](./docs/architecture.md) | 系统架构图、模块划分、数据流、关键时序 |
| [docs/api.md](./docs/api.md) | REST + WebSocket API 完整参考 |
| [docs/deployment.md](./docs/deployment.md) | Docker / K8s / Helm / CI/CD 部署指南 |
| [docs/runbook.md](./docs/runbook.md) | 6 个常见故障的处置 SOP |
| [docs/user-guide.md](./docs/user-guide.md) | 终端用户使用手册（数据生产流程） |
| [docs/security.md](./docs/security.md) | 安全模型、密钥管理、审计、合规清单 |

## 🏗️ 仓库结构

```
nanobot-factory/
├── backend/                  # FastAPI 后端
│   ├── server.py             # 主入口 (uvicorn backend.server:app)
│   ├── imdf/                 # Infinite Multimodal Data Foundry 包
│   │   └── api/              # FastAPI 路由
│   ├── nanobot_factory/      # Cluster / Agent 子模块
│   └── omni_gen_studio/      # ComfyUI 集成
├── frontend/                 # Web UI (Vue 3 CDN SPA)
│   ├── index.html            # 主入口
│   └── js/                   # 组件 / store / 路由
├── src/                      # Electron 桌面端 (React 18)
│   ├── renderer/             # Vite 渲染进程
│   └── main/                 # Electron 主进程
├── deploy/
│   ├── k8s/                  # 8 个裸 manifest
│   ├── helm/nanobot-factory/ # Helm chart
│   ├── nginx/                # nginx.conf (容器内)
│   └── entrypoint.sh         # 容器启动脚本
├── tests/                    # pytest (unit/integration/e2e)
├── docs/                     # 7 篇文档
├── .github/workflows/        # ci.yml / cd.yml / pr-preview.yml
├── Dockerfile                # 多阶段构建
├── docker-compose.yml        # 2 profiles (prod + dev)
├── package.json
├── pyproject.toml
├── requirements_full.txt
└── README.md                 # ← 你正在读的文件
```

## 🤝 贡献

1. Fork → 创建 feature branch (`git checkout -b feat/awesome`)
2. 提交前跑本地检查：
   ```bash
   ruff check backend/
   pytest tests/unit -m "not slow"
   npm run build
   helm lint deploy/helm/nanobot-factory
   ```
3. 提 PR；CI 会自动：lint → test → build → docker build → preview deploy。
4. 合并后自动部署到 staging；tag push (`v*.*.*`) → production。

## 📄 License

MIT — see [`LICENSE`](./LICENSE).

---

_Built with ❤️ by MiniMax Agent · 2026_