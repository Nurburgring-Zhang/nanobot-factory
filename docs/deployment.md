# Deployment Guide — Nanobot Factory

> 适用版本 **appVersion 1.0.0**。本文档覆盖从单进程到多副本 K8s 的全部部署形态。

## 部署形态总览

| 形态 | 命令 | 适用 | 资源占用 |
|------|------|------|----------|
| 单进程 | `python -m uvicorn backend.server:app` | 开发 | ~250 MB RAM |
| docker compose (app) | `docker compose up -d` | 单机 / 小团队 | 1 GB RAM |
| docker compose (dev) | `docker compose --profile dev up` | 热重载开发 | 1.5 GB RAM |
| K8s 裸 manifest | `kubectl apply -f deploy/k8s/` | 学习 / 调试 | 2 副本起 |
| Helm chart | `helm install nanofab ./deploy/helm/nanobot-factory` | **生产** | 2-10 副本自动伸缩 |
| CI/CD | `.github/workflows/cd.yml` | 自动化 | — |

---

## 1. 单进程 (本地开发)

```bash
# 后端
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_full.txt
python -m uvicorn backend.server:app --reload --port 8001

# 前端 (另一终端)
npm install
npm run dev
# → http://localhost:5173
```

`.env`：

```ini
DEV_MODE=true
LOG_LEVEL=DEBUG
ALLOWED_ORIGINS=http://localhost:5173
```

---

## 2. Docker (单机)

### 2.1 快速开始

```bash
# 生产模式（默认 profile）
docker compose up -d
# → http://localhost:8080

# 验证
curl -fsS http://localhost:8080/healthz
curl -fsS http://localhost:8080/readyz

# 查看日志
docker compose logs -f app

# 停止
docker compose down
```

### 2.2 资源限制

`docker-compose.yml` 已经为 `app` 容器设置：

| 资源 | Request | Limit |
|------|---------|-------|
| CPU | 0.5 | 2.0 |
| Memory | 512 MB | 4 GB |

如需调整：

```bash
# 命令行覆盖
docker compose up -d \
  --scale app=2

# 或改 docker-compose.yml 的 deploy.resources
```

### 2.3 数据持久化

数据落在命名 volume：

| Volume | 容器路径 | 用途 |
|--------|----------|------|
| `nanobot-data` | `/app/data` | SQLite DB + 渲染产物 |
| `nanobot-logs` | `/app/logs` | 应用日志 |
| `nanobot-redis` | `/data` | Redis RDB |

备份：

```bash
docker run --rm -v nanobot-data:/data -v $(pwd):/backup \
    alpine tar czf /backup/data-$(date +%F).tgz -C /data .
```

### 2.4 开发热重载

```bash
docker compose --profile dev up
# → backend: http://localhost:8001  (uvicorn --reload)
# → frontend: http://localhost:5173  (vite HMR)
```

源码以 bind mount 方式挂载进容器；改动即时生效。

### 2.5 故障排查

```bash
# 容器进不去 — 看日志
docker compose logs --tail=200 app

# 进入容器
docker compose exec app sh

# 健康检查失败
docker inspect --format='{{.State.Health.Status}}' nanobot-app
```

---

## 3. Kubernetes (裸 manifest)

### 3.1 前置

- K8s 集群 ≥ 1.25
- `kubectl` 已配置 kubeconfig
- `nginx-ingress` controller
- `cert-manager` (可选，用于 TLS)
- 默认 StorageClass

### 3.2 一键部署

```bash
# 1. 创建命名空间 + RBAC
kubectl apply -f deploy/k8s/00-namespace.yaml
kubectl apply -f deploy/k8s/01-serviceaccount.yaml

# 2. 配置
kubectl apply -f deploy/k8s/02-configmap.yaml

# 3. 部署 + 服务
kubectl apply -f deploy/k8s/03-deployment.yaml
kubectl apply -f deploy/k8s/04-service.yaml

# 4. 入口 + 自动伸缩 + PDB
kubectl apply -f deploy/k8s/05-ingress.yaml
kubectl apply -f deploy/k8s/06-hpa.yaml
kubectl apply -f deploy/k8s/07-pdb.yaml

# 5. 等就绪
kubectl -n nanobot-factory wait --for=condition=ready pod \
    -l app.kubernetes.io/name=nanobot-factory --timeout=300s

# 6. 验证
kubectl -n nanobot-factory port-forward svc/nanobot-factory 8080:80
curl -fsS http://localhost:8080/healthz
```

### 3.3 PVC

`03-deployment.yaml` 引用 `nanobot-factory-data` 和 `nanobot-factory-logs` 这两个 PVC。
本仓库未提供（避免绑死 StorageClass）。最小示例：

```yaml
# deploy/k8s/pvc.yaml (本地或私有环境再 apply)
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nanobot-factory-data
  namespace: nanobot-factory
spec:
  accessModes: [ReadWriteOnce]
  resources: { requests: { storage: 50Gi } }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: nanobot-factory-logs
  namespace: nanobot-factory
spec:
  accessModes: [ReadWriteOnce]
  resources: { requests: { storage: 20Gi } }
```

### 3.4 镜像

部署前先 push 镜像：

```bash
docker build -t registry.example.com/nanobot-factory:1.0.0 .
docker push registry.example.com/nanobot-factory:1.0.0

# 修改 03-deployment.yaml 中 image 字段
kubectl -n nanobot-factory set image deploy/nanobot-factory \
    nanobot-factory=registry.example.com/nanobot-factory:1.0.0
```

### 3.5 滚动更新

```bash
# 改 image 触发 rollout
kubectl -n nanobot-factory set image deploy/nanobot-factory \
    nanobot-factory=registry.example.com/nanobot-factory:1.1.0

# 观察
kubectl -n nanobot-factory rollout status deploy/nanobot-factory

# 回滚
kubectl -n nanobot-factory rollout undo deploy/nanobot-factory
```

---

## 4. Helm (生产推荐)

### 4.1 安装

```bash
# 默认
helm upgrade --install nanobot-factory ./deploy/helm/nanobot-factory \
    --namespace nanobot-factory --create-namespace

# 自定义 values
helm upgrade --install nanobot-factory ./deploy/helm/nanobot-factory \
    -f my-prod.yaml \
    --namespace nanobot-factory --create-namespace
```

### 4.2 最小化 values 覆盖示例

```yaml
# my-prod.yaml
image:
  repository: ghcr.io/myorg/nanobot-factory
  tag: "1.1.0"

replicaCount: 3

ingress:
  enabled: true
  hosts:
    - host: nanobot.prod.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - hosts:
        - nanobot.prod.example.com
      secretName: nanobot-prod-tls

config:
  allowedOrigins: "https://nanobot.prod.example.com"
  logLevel: "INFO"
  rateLimitRequests: "500"

autoscaling:
  minReplicas: 3
  maxReplicas: 20

persistence:
  data:
    size: 200Gi
    storageClassName: "ssd-premium"
  logs:
    size: 50Gi
    storageClassName: "standard"
```

### 4.3 升级 / 回滚

```bash
# 升级
helm upgrade nanobot-factory ./deploy/helm/nanobot-factory \
    -f my-prod.yaml --wait --timeout 10m

# 历史
helm history nanobot-factory -n nanobot-factory

# 回滚
helm rollback nanobot-factory 3 -n nanobot-factory
```

### 4.4 卸载

```bash
helm uninstall nanobot-factory -n nanobot-factory

# PVC 默认保留 — 防止数据误删
kubectl -n nanobot-factory delete pvc -l app.kubernetes.io/instance=nanobot-factory
```

### 4.5 完整 values 字段说明

参见 [`deploy/helm/nanobot-factory/values.yaml`](../deploy/helm/nanobot-factory/values.yaml)。

---

## 5. CI/CD

`.github/workflows/ci.yml`：lint + test + build + docker + helm。
`.github/workflows/cd.yml`：push tag `v*.*.*` 或 manual dispatch → 部署 staging → production。
`.github/workflows/pr-preview.yml`：每个 PR 自动起独立 preview 环境，关闭 PR 自动清理。
`.github/dependabot.yml`：npm + pip + GitHub Actions + docker 基础镜像的每周依赖更新。

### 必需的 Secrets

| Secret | 用途 |
|--------|------|
| `STAGING_KUBECONFIG` | base64 编码的 staging 集群 kubeconfig |
| `PROD_KUBECONFIG` | base64 编码的生产集群 kubeconfig |
| `PREVIEW_KUBECONFIG` | preview 集群 kubeconfig |
| `SLACK_WEBHOOK` | Slack 通知 |
| `CODECOV_TOKEN` | (可选) Codecov |

### Tag 触发发布

```bash
git tag v1.1.0
git push origin v1.1.0
# → CI 跑完整测试 + build image
# → CD 自动部署 staging → 等你 approve → production
```

---

## 6. 反向代理 / TLS

### 6.1 cert-manager + letsencrypt (推荐)

```yaml
# deploy/k8s/05-ingress.yaml 已包含
cert-manager.io/cluster-issuer: letsencrypt-prod
```

### 6.2 自签证书 (测试)

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=nanobot.example.com"

kubectl create secret tls nanobot-factory-tls \
  --cert=tls.crt --key=tls.key -n nanobot-factory
```

### 6.3 反向代理 / nginx 之外

如果用 Apache、HAProxy、Cloudflare，请确保：
- WebSocket 透传（Upgrade / Connection 头）
- `proxy_read_timeout ≥ 300s`（ComfyUI 长任务）
- 客户端真实 IP 通过 `X-Forwarded-For` 传递

---

## 7. 健康 / 监控

| 端点 | 用途 | 监控 |
|------|------|------|
| `/healthz` | 进程存活 | k8s livenessProbe |
| `/readyz` | 依赖就绪 | k8s readinessProbe |
| `/metrics` | Prometheus | Prometheus scrape |

Prometheus 配置示例：

```yaml
scrape_configs:
  - job_name: nanobot-factory
    metrics_path: /metrics
    static_configs:
      - targets: ['nanobot-factory.nanobot-factory.svc:80']
```

Grafana 推荐面板：
- 请求速率 / p50/p95/p99 latency
- /healthz 失败次数 (按副本)
- WS 连接数
- 任务队列长度
- GPU 利用率 (来自 ComfyUI 节点 exporter)

---

## 8. 安全清单

完整列表见 [`security.md`](./security.md)。部署相关：

- [ ] 改 `JWT_SECRET` 为 32+ 随机字符
- [ ] 设置 `ALLOWED_ORIGINS` 精确列表（不用 `*`）
- [ ] 启用 TLS（cert-manager / 自签 / 反代）
- [ ] 关闭 `DEV_MODE` / `CORS_ALLOW_ALL`
- [ ] 限制 SSH / kubectl 入口网络
- [ ] 镜像推到私有 registry，开启 image scan
- [ ] 启用 audit log (k8s + 应用层)

---

## 9. 容量规划

| 用户规模 | 副本数 | 内存 / 副本 | PVC | 备注 |
|----------|--------|-------------|-----|------|
| ≤ 10 并发 | 2 | 1 GB | data 20 GB / logs 5 GB | 入门 |
| 10–50 并发 | 4 | 2 GB | data 100 GB / logs 20 GB | 中小团队 |
| 50–200 并发 | 8 | 4 GB | data 500 GB / logs 50 GB | 生产 |
| ≥ 200 并发 | 10+ | 4 GB+ | 按实际 + 监控 | 启用 HPA |

---

_最后更新：2026-06-21 — 适用版本 appVersion 1.0.0_