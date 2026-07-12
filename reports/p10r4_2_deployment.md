# P10R4-2: 部署文档 (23 systemd 单元 + 6 deploy 脚本 + 健康检查 + 滚动重启)

> **Date**: 2026-06-26 13:55 (Asia/Shanghai)
> **Author**: coder (P10R4-2 worker)
> **Sources**: `deploy/bare_metal/systemd/*.service` (23 文件) + `deploy/bare_metal/scripts/*.sh` (6 文件) + `install.sh` + `deploy/bare_metal/README.md`

---

## 1. systemd 单元完整清单 (23 个)

### 1.1 Layer 0: 数据层 (3)

| Unit | Description | Port | 启动顺序 |
|------|-------------|------|---------|
| `postgresql.service` | PostgreSQL 15 + pgvector | 5432 | 1 |
| `redis-server.service` | Redis 7 (broker + cache + pub/sub) | 6379 | 2 |
| `minio.service` | MinIO (S3-compatible OSS) | 9000 API / 9001 UI | 3 |

### 1.2 Layer 1: 监控 (6)

| Unit | Description | Port | 启动顺序 |
|------|-------------|------|---------|
| `prometheus.service` | 指标采集 + 存储 | 9090 | 4 |
| `alertmanager.service` | 告警路由 | 9093 | 5 |
| `grafana-server.service` | 8 dashboard | 3000 | 6 |
| `jaeger.service` | 分布式追踪 | 16686 UI / 6831 agent | 7 |
| `loki.service` | 日志聚合 | 3100 | 8 |
| `promtail.service` | journald → Loki | - | 9 |

### 1.3 Layer 2: 应用层 (12 + 2 celery = 14)

| Unit | Port | Workers | 启动顺序 | 关键依赖 |
|------|------|---------|---------|---------|
| `imdf-gateway.service` | **8000** | 4 | 10 | PG + Redis + MinIO |
| `imdf-user.service` | 8001 | 2 | 11 | PG + Redis |
| `imdf-asset.service` | 8002 | 2 | 11 | PG + MinIO |
| `imdf-annotation.service` | 8003 | 2 | 11 | PG + Redis |
| `imdf-cleaning.service` | 8004 | 2 | 11 | PG + Redis + MinIO |
| `imdf-scoring.service` | 8005 | 2 | 11 | PG + Redis + MinIO |
| `imdf-dataset.service` | 8006 | 2 | 11 | PG + MinIO |
| `imdf-evaluation.service` | 8007 | 2 | 11 | PG + Redis |
| `imdf-agent.service` | 8008 | 4 | 11 | PG + Redis + MinIO |
| `imdf-workflow.service` | 8009 | 2 | 11 | PG + Redis + Celery |
| `imdf-notification.service` | 8010 | 2 | 11 | PG + Redis |
| `imdf-search.service` | 8011 | 2 | 11 | PG (pgvector) |
| `imdf-collection.service` | 8012 | 2 | 11 | PG + MinIO |
| `imdf-celery.service` | - (worker) | concurrency 4 | 12 | Redis + PG |
| `imdf-celery-beat.service` | - (scheduler) | - | 12 | Redis |

### 1.4 旁路: 备份 (2)

| Unit | Description | 触发 |
|------|-------------|------|
| `imdf-backup.service` | 调用 backup_cron.sh | oneshot, 由 timer 触发 |
| `imdf-backup.timer` | systemd timer | daily 03:00 + Sun 04:00 |

**总计**: 3 + 6 + 15 + 2 = **26 个 unit** (含 celery×2 + backup×2)

> P7-3 旧报告计 21 unit = 3 (data) + 6 (obs) + 12 (app) — 当时 celery 和 backup 未纳入。

---

## 2. systemd unit 模板 (imdf-gateway.service)

```ini
[Unit]
Description=IMDF api-gateway (uvicorn)
Documentation=https://imdf.example.com/docs
After=network-online.target postgresql.service redis-server.service minio.service
Wants=network-online.target
Requires=postgresql.service redis-server.service minio.service

[Service]
Type=notify              # 支持 sd_notify (watchdog)
User=imdf
Group=imdf
WorkingDirectory=/opt/nanobot-factory
EnvironmentFile=/etc/imdf/imdf.env

ExecStart=/opt/nanobot-factory/venv/bin/uvicorn \
    backend.gateway.main:app \
    --host 0.0.0.0 --port 8000 \
    --workers 4 \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --access-log \
    --log-level info

Restart=always
RestartSec=5
StartLimitBurst=5
StartLimitIntervalSec=60

# ── Hardening (P10R4-1 安全加固) ──
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
LockPersonality=true
MemoryDenyWriteExecute=true
SystemCallArchitectures=native
ReadWritePaths=/opt/nanobot-factory/data /opt/nanobot-factory/logs /opt/nanobot-factory/data/prometheus

# ── Resource limits ──
LimitNOFILE=65536
LimitNPROC=8192
MemoryMax=4G
MemoryHigh=3G
CPUQuota=400%

# ── Logging (journald) ──
StandardOutput=journal
StandardError=journal
SyslogIdentifier=imdf-gateway

# ── Watchdog ──
WatchdogSec=30
NotifyAccess=main

[Install]
WantedBy=multi-user.target
```

---

## 3. 各 svc systemd unit 差异 (摘要)

| Service | Memory | CPU | Workers | 特殊 |
|---------|--------|-----|---------|------|
| imdf-gateway | 4G | 400% | 4 | watchdog, WatchdogSec=30 |
| imdf-user | 2G | 200% | 2 | 标准 |
| imdf-asset | 4G | 200% | 2 | 标准 (大文件流) |
| imdf-annotation | 4G | 300% | 2 | 标准 |
| imdf-cleaning | 4G | 300% | 2 | 标准 |
| imdf-scoring | 4G | 300% | 2 | 标准 |
| imdf-dataset | 2G | 200% | 2 | 标准 |
| imdf-evaluation | 4G | 300% | 2 | 标准 |
| imdf-agent | 6G | 400% | 4 | 高内存 (memory + plugins) |
| imdf-workflow | 4G | 300% | 2 | 标准 |
| imdf-notification | 2G | 200% | 2 | WS 长连接 |
| imdf-search | 4G | 300% | 2 | 标准 (vector) |
| imdf-collection | 4G | 200% | 2 | 标准 |
| imdf-celery | 8G | 400% | concurrency 4 | 大模型加载 (ONNX/Whisper) |
| imdf-celery-beat | 1G | 100% | - | scheduler |

**总资源需求**: ~58 GB RAM, ~36 cores CPU

---

## 4. 6 deploy 脚本

### 4.1 清单

| 脚本 | 用途 | 行数 |
|------|------|------|
| `install.sh` | 一键安装 (apt + venv + user + dirs) | 9111B (~200 行) |
| `start-all.sh` | 按依赖顺序启动所有 unit | 84 行 |
| `stop-all.sh` | 逆序停止所有 unit | ~50 行 |
| `status.sh` | tabular 状态展示 | 60+ 行 |
| `upgrade.sh` | git pull + pip + alembic + 重启 | 180+ 行 |
| `healthcheck.sh` | 30s 内 curl 13 endpoint | 74 行 |
| `backup-db.sh` | legacy pg_dump (被 backup_cron.sh 替代) | 3.1KB |

### 4.2 install.sh 关键步骤

```bash
#!/usr/bin/env bash
# 1) 系统准备
apt update && apt install -y python3.11 python3.11-venv \
  postgresql-15 postgresql-server-dev-15 build-essential git curl \
  nginx redis-server certbot python3-certbot-nginx \
  prometheus grafana

# 2) 创建 imdf 用户
useradd -r -s /bin/bash imdf

# 3) 目录结构
mkdir -p /opt/nanobot-factory/{backend,frontend,data,logs,venv}
mkdir -p /etc/imdf
mkdir -p /var/lib/imdf/{prometheus,grafana,loki,jaeger}
mkdir -p /var/backups/imdf/{db,redis,oss,warm,cold}
chown -R imdf:imdf /opt/nanobot-factory /var/lib/imdf /var/backups/imdf

# 4) Python venv
sudo -u imdf python3.11 -m venv /opt/nanobot-factory/venv
sudo -u imdf /opt/nanobot-factory/venv/bin/pip install \
  -r /opt/nanobot-factory/backend/requirements.txt

# 5) PG 配置 (postgresql.conf + pg_hba.conf + pgvector extension)

# 6) Redis (maxmemory 32GB)

# 7) MinIO + 创建 buckets (imdf-assets / imdf-temp / imdf-archive)

# 8) Prometheus + Alertmanager + Grafana datasources + dashboards

# 9) systemd 单元 (从 deploy/bare_metal/systemd/*.service 复制)

# 10) nginx (config + certbot)

# 11) 启用所有 service + timer
systemctl daemon-reload
systemctl enable --now imdf-gateway imdf-user imdf-asset ... imdf-celery-beat
systemctl enable --now imdf-backup.timer
```

### 4.3 upgrade.sh 升级流程 (8 步)

```bash
sudo deploy/bare_metal/scripts/upgrade.sh v1.7.0

# 内部:
# 0) pre-flight (git repo? venv exists?)
# 1) snapshot current SHA → rollback hint
# 2) git fetch + checkout tag + pull --ff-only
# 3) pip install --upgrade -r requirements.txt
# 4) frontend build (if changed)
# 5) alembic upgrade head (DB migration)
# 6) restart 12 svc (rolling)
# 7) healthcheck.sh (verify)
# 8) rollback if failed (记录 old/new SHA)
```

---

## 5. 健康检查 (5 endpoint per svc)

### 5.1 Endpoint 总览

| Endpoint | 路径 | Liveness/Readiness | 通过条件 |
|----------|------|--------------------|---------|
| `/healthz` | GET | Liveness | 进程存活 + 事件循环 |
| `/readyz` | GET | Readiness | DB + Redis + Disk |
| `/metrics` | GET | - | Prometheus format |
| `/api/queue/health` | GET | Queue | Celery + Redis ping |
| `/api/queue/stats` | GET | Queue | 各队列长度 |

### 5.2 healthcheck.sh 实现 (74 行)

```bash
#!/usr/bin/env bash
LOG="/var/log/imdf-healthcheck.log"
GATEWAY_URL="${IMDF_GATEWAY_URL:-http://127.0.0.1:8000}"
TIMEOUT="${HEALTHCHECK_TIMEOUT:-5}"

# 1) Gateway /api/queue/health
GW_RESP=$(curl -fsS --max-time "${TIMEOUT}" "${GATEWAY_URL}/api/queue/health") || \
  fail "gateway unreachable"

# 2) /readyz (DB + Redis)
RD_RESP=$(curl -fsS --max-time "${TIMEOUT}" "${GATEWAY_URL}/readyz") || \
  fail "readyz unreachable"

# 3) /metrics
curl -fsS --max-time "${TIMEOUT}" "${GATEWAY_URL}/metrics" >/dev/null 2>&1 \
  && ok "metrics endpoint reachable" || fail "metrics unreachable"

# 4) 12 svc /healthz
for port in 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010 8011 8012; do
  curl -fsS --max-time 2 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1 \
    && ok "service :${port} healthy" || fail "service :${port} unhealthy"
done

# 5) Celery + Beat
CELERY_ACTIVE=$(systemctl is-active imdf-celery.service)
BEAT_ACTIVE=$(systemctl is-active imdf-celery-beat.service)
[[ "${CELERY_ACTIVE}" == "active" ]] && ok "celery worker" || fail
[[ "${BEAT_ACTIVE}" == "active" ]] && ok "celery beat" || fail
```

---

## 6. 滚动重启策略

### 6.1 蓝绿 (Blue-Green)

```bash
# Step 1: 启动新版本 (新代码 + 旧 DB 连接)
sudo -u imdf bash -c "cd /opt/nanobot-factory && \
  git pull && venv/bin/pip install -r backend/requirements.txt"

# Step 2: alembic upgrade (无停机 — 加列 nullable)
sudo -u imdf bash -c "cd /opt/nanobot-factory && \
  venv/bin/alembic -c backend/alembic.ini upgrade head"

# Step 3: 重启单 svc (滚动, 旧 worker 处理 in-flight)
for svc in imdf-gateway imdf-user imdf-asset imdf-annotation \
           imdf-cleaning imdf-scoring imdf-dataset imdf-evaluation \
           imdf-agent imdf-workflow imdf-notification imdf-search \
           imdf-collection; do
  sudo systemctl restart "${svc}"
  sleep 10  # 等健康
  status=$(curl -fsS --max-time 2 "http://127.0.0.1:${svc#imdf-}/healthz" 2>/dev/null | jq -r .status)
  [[ "${status}" == "ok" ]] || { echo "FAIL: ${svc}"; break; }
done

# Step 4: 重启 celery worker + beat
sudo systemctl restart imdf-celery imdf-celery-beat
```

### 6.2 全停全启 (维护窗口)

```bash
sudo deploy/bare_metal/scripts/stop-all.sh
# (DB schema 变更, 重启时间 < 5 min)
sudo deploy/bare_metal/scripts/start-all.sh
```

### 6.3 Canary (高级)

```bash
# 节点 A (10%) + 节点 B (90%)
# 1) 新代码部署到节点 A
# 2) nginx upstream: weight 1:9
upstream imdf_gateway {
    server 10.0.1.10:8000 weight=9;   # 旧
    server 10.0.1.11:8000 weight=1;   # 新 (canary)
}
# 3) 监控 30 min, 无异常 → 切 5:5 → 1:9 → 0:10
```

---

## 7. 部署架构 (三层)

```
┌──────────────────────────────────────────────────────────┐
│ Edge (nginx)                                             │
│ - 80/443 + Let's Encrypt                                 │
│ - rate-limit /api/auth/*                                 │
│ - WebSocket upgrade                                      │
│ - client_max_body_size 1G                               │
└──────────────────────┬───────────────────────────────────┘
                       │ /api/* /airi/* /omni/* /ws/*
┌──────────────────────▼───────────────────────────────────┐
│ Application (12 svc + 2 celery)                          │
│ - gateway :8000 (4 workers)                              │
│ - 11 backend svc :8001-8012 (2 workers)                  │
│ - celery worker (concurrency 4, 5 queues)                │
│ - celery beat (scheduler)                                │
└──────────────────────┬───────────────────────────────────┘
                       │ PG + Redis + MinIO
┌──────────────────────▼───────────────────────────────────┐
│ Data + Observability (3 + 6 svc)                         │
│ - PG 15 + pgvector                                       │
│ - Redis 7 (broker + cache + pub/sub)                     │
│ - MinIO (S3-compatible OSS)                              │
│ - Prometheus + Alertmanager + Grafana + Jaeger + Loki    │
└──────────────────────────────────────────────────────────┘
```

---

## 8. 安装步骤 (8 步 — 摘自 deploy/bare_metal/README.md)

### Step 1: 系统准备 (apt install)

```bash
apt update && apt upgrade -y
apt install -y python3.11 python3.11-venv python3.11-dev \
  postgresql-15 postgresql-server-dev-15 build-essential git curl \
  nginx redis-server certbot python3-certbot-nginx \
  prometheus grafana

# 可选: jaeger / minio (binary)
wget -qO /usr/local/bin/jaeger https://github.com/jaegertracing/jaeger/releases/download/v1.55/jaeger-1.55-linux-amd64
chmod +x /usr/local/bin/jaeger

wget -qO /usr/local/bin/minio https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x /usr/local/bin/minio
```

### Step 2: 创建 `imdf` 用户

```bash
useradd -r -s /bin/bash -m -d /home/imdf imdf
mkdir -p /opt/nanobot-factory
chown -R imdf:imdf /opt/nanobot-factory
```

### Step 3: PostgreSQL + pgvector

```bash
sudo -u postgres psql -c "CREATE USER imdf_app WITH PASSWORD '...';"
sudo -u postgres psql -c "CREATE DATABASE imdf OWNER imdf_app;"
sudo -u postgres psql -d imdf -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Step 4: Redis

```bash
sudo systemctl enable --now redis-server
redis-cli ping  # PONG
```

### Step 5: MinIO

```bash
useradd -r -s /sbin/nologin minio-user
mkdir -p /var/lib/minio
chown -R minio-user:minio-user /var/lib/minio
sudo systemctl enable --now minio
# http://<host>:9001 → create buckets: imdf-assets / imdf-temp / imdf-archive
```

### Step 6: 数据库迁移 + seed

```bash
sudo -u imdf bash -c "source /etc/imdf/imdf.env && \
  cd /opt/nanobot-factory && \
  venv/bin/alembic -c backend/alembic.ini upgrade head"
```

### Step 7: systemd 启用 + 启动

```bash
sudo cp deploy/bare_metal/systemd/imdf-*.service /etc/systemd/system/
sudo cp deploy/bare_metal/systemd/{postgresql,redis-server,minio,prometheus,grafana-server,jaeger,loki,promtail}.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo deploy/bare_metal/scripts/start-all.sh
```

### Step 8: nginx + TLS

```bash
sudo cp deploy/bare_metal/configs/nginx-imdf.conf /etc/nginx/sites-available/imdf
sudo ln -sf /etc/nginx/sites-available/imdf /etc/nginx/sites-enabled/imdf
sudo certbot --nginx -d imdf.example.com
sudo systemctl restart nginx
curl -fsS https://imdf.example.com/api/queue/health
```

---

## 9. 多环境 (dev / staging / prod)

### 9.1 环境差异

| 维度 | Dev | Staging | Prod |
|------|-----|---------|------|
| 主机 | 本地 VM | 单独 staging DC | prod DC |
| 数据 | 合成数据 | 脱敏生产数据 | 真实数据 |
| DB | SQLite WAL | PostgreSQL 单机 | PostgreSQL 主从 |
| 备份 | 无 | daily + 7d 保留 | daily + 365d + 异地 |
| 监控 | 基础 | 完整 | 完整 + on-call |
| 域名 | dev.imdf.local | staging.imdf.example.com | imdf.example.com |
| 流量 | < 1 QPS | < 100 QPS | < 10K QPS |
| Workers | 1 | 2 | 4 (gateway) / 2 (svc) |

### 9.2 .env 模板 (deploy/bare_metal/.env.example)

```bash
# /etc/imdf/imdf.env (chmod 600)
ENV=production
SECRET_KEY_BASE=<openssl rand -hex 32>
JWT_SECRET_KEY=<openssl rand -hex 32>

DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=imdf
DB_APP_USER=imdf_app
DB_APP_PASSWORD=<from vault>

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=<from vault>

MINIO_HOST=127.0.0.1
MINIO_PORT=9000
MINIO_ROOT_USER=<from vault>
MINIO_ROOT_PASSWORD=<from vault>

OSS_BUCKET=imdf-assets
OSS_ACCESS_KEY_ID=<from vault>
OSS_ACCESS_KEY_SECRET=<from vault>

CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
CELERY_CONCURRENCY=4
CELERY_QUEUES=default,video,cpu,index,network
CELERY_LOG_LEVEL=info

# Backups
BACKUP_NOTIFY_WEBHOOK=<slack webhook>
HOT_TIER_DAYS=7
WARM_TIER_DAYS=30
COLD_TIER_DAYS=365

# Monitoring
SENTRY_DSN=<from vault>
JAEGER_AGENT_HOST=127.0.0.1
JAEGER_AGENT_PORT=6831
LOKI_URL=http://127.0.0.1:3100

# Rate limit
RATE_LIMIT_PER_IP=60
RATE_LIMIT_PER_USER=600
RATE_LIMIT_PER_TENANT=6000

# Audit chain
AUDIT_CHAIN_SECRET=<openssl rand -hex 32>
```

---

## 10. 安全加固 (P10R4-1 验证 PASS)

| 控制 | 状态 | 说明 |
|------|------|------|
| 非 root user (imdf) | ✅ | 所有 svc 以 `imdf` 运行 |
| NoNewPrivileges | ✅ | 禁止 setuid/setgid |
| PrivateTmp | ✅ | /tmp 隔离 |
| ProtectSystem=strict | ✅ | /usr, /boot 只读 |
| ProtectHome=yes | ✅ | /home, /root 不可访问 |
| ProtectKernelTunables | ✅ | /proc, /sys 受限 |
| RestrictNamespaces | ✅ | 禁止创建新 namespace |
| MemoryDenyWriteExecute | ✅ | 禁止 W^X |
| ReadWritePaths | ✅ | 仅 /opt/.../data 和 /logs 可写 |
| SystemCallArchitectures=native | ✅ | 禁止 32-bit syscall |
| LimitNOFILE=65536 | ✅ | FD 上限 |
| MemoryMax / MemoryHigh | ✅ | 软硬内存限制 |
| CPUQuota=400% | ✅ | CPU 上限 |
| WatchdogSec=30 | ✅ | 30s 健康检查 |
| EnvironmentFile=/etc/imdf/imdf.env (chmod 600) | ✅ | secret 受保护 |
| TLS 1.3 (Let's Encrypt) | ✅ | certbot 自动续 |
| nginx rate-limit /api/auth | ✅ | 10 req/min/IP |
| client_max_body_size 1G | ✅ | 大文件限制 |

---

## 11. 部署验证清单

```yaml
# 安装后必跑:
- [ ] /etc/imdf/imdf.env 已 chmod 600
- [ ] 所有 23 unit active
- [ ] 12 svc /healthz 200
- [ ] /api/queue/health OK
- [ ] /readyz 检查全通过
- [ ] /metrics 暴露 imdf_* 指标
- [ ] 备份 timer 启用
- [ ] certbot 自动续证书
- [ ] nginx rate-limit 生效
- [ ] Grafana 8 dashboard 可访问
- [ ] Alertmanager 21 规则加载
- [ ] Jaeger 收到 trace
- [ ] Loki 收到 log
```

---

## 12. 关键引用

- `deploy/bare_metal/README.md` (15KB, 部署权威)
- `deploy/bare_metal/install.sh` (9KB, 一键安装)
- `deploy/bare_metal/systemd/*.service` (23 文件, 单元模板)
- `deploy/bare_metal/scripts/*.sh` (6 文件, 运维脚本)
- `deploy/bare_metal/configs/*.conf` (10+ 配置: PG, Redis, MinIO, Prometheus, Grafana, Loki, Jaeger, Nginx)
- `deploy/bare_metal/.env.example` (7KB, 环境变量模板)
- `reports/p7_3_deploy.md` (20KB, 历史部署审计)
- `deploy/bare_metal/backup_cron.{service,timer}` (备份 timer)

