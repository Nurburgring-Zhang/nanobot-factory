# 裸机部署方案 (Bare-metal Deployment)

## 概述
**禁止 Docker / Kubernetes / 容器**,改用裸机进程 + systemd + 本地服务方式部署 nanobot-factory VDP-2026。

## 服务器 / 本机需求

### 硬件最低配置
| 角色 | CPU | RAM | Disk | OS |
|------|-----|-----|------|-----|
| **all-in-one (开发/小团队)** | 8 核 | 32 GB | 1 TB SSD | Ubuntu 22.04 LTS / Windows Server 2022 |
| **production (中型团队)** | 16 核 (12+ service 独立进程) | 64 GB | 2 TB SSD + 4 TB HDD | Ubuntu 22.04 LTS |
| **GPU 推理 (AI 算子)** | + NVIDIA RTX 4090 / A100 | + 24 GB VRAM | - | - |

### 软件依赖 (本地安装,非容器)
- **Python 3.11+** (`pyenv` 或系统包)
- **PostgreSQL 15+** (含 `pgvector` 扩展,需从源码或 apt 装)
- **Redis 7+** (apt)
- **Node.js 20+** (nvm)
- **MinIO Server** (二进制下载,作 S3 兼容对象存储)
- **Nginx** (反代 + 静态文件)
- **systemd** (服务管理)
- **可选**: Prometheus + Grafana + Jaeger (二进制下载)

## 服务架构 (12 微服务 + 网关)

| 端口 | 服务 | systemd unit | 启动命令 |
|------|------|-------------|---------|
| 8000 | api-gateway | `imdf-gateway.service` | `uvicorn backend.gateway.main:app --host 0.0.0.0 --port 8000 --workers 4` |
| 8001 | user-service | `imdf-user.service` | `uvicorn backend.services.user_service.main:app --port 8001 --workers 2` |
| 8002 | asset-service | `imdf-asset.service` | `uvicorn backend.services.asset_service.main:app --port 8002 --workers 2` |
| 8003 | annotation-service | `imdf-annotation.service` | `uvicorn backend.services.annotation_service.main:app --port 8003 --workers 2` |
| 8004 | cleaning-service | `imdf-cleaning.service` | `uvicorn backend.services.cleaning_service.main:app --port 8004 --workers 2` |
| 8005 | scoring-service | `imdf-scoring.service` | `uvicorn backend.services.scoring_service.main:app --port 8005 --workers 2` |
| 8006 | dataset-service | `imdf-dataset.service` | `uvicorn backend.services.dataset_service.main:app --port 8006 --workers 2` |
| 8007 | evaluation-service | `imdf-evaluation.service` | `uvicorn backend.services.evaluation_service.main:app --port 8007 --workers 2` |
| 8008 | agent-service | `imdf-agent.service` | `uvicorn backend.services.agent_service.main:app --port 8008 --workers 2` |
| 8009 | workflow-service | `imdf-workflow.service` | `uvicorn backend.services.workflow_service.main:app --port 8009 --workers 2` |
| 8010 | notification-service | `imdf-notification.service` | `uvicorn backend.services.notification_service.main:app --port 8010 --workers 2` |
| 8011 | search-service | `imdf-search.service` | `uvicorn backend.services.search_service.main:app --port 8011 --workers 2` |
| 8012 | collection-service | `imdf-collection.service` | `uvicorn backend.services.collection_service.main:app --port 8012 --workers 2` |
| - | celery worker | `imdf-celery.service` | `celery -A backend.imdf.celery_app worker --loglevel=info --concurrency=4` |
| - | celery beat | `imdf-celery-beat.service` | `celery -A backend.imdf.celery_app beat --loglevel=info` |
| - | prometheus | `prometheus.service` | `prometheus --config.file=/etc/prometheus/prometheus.yml` |
| - | grafana | `grafana-server.service` | `grafana-server` |
| - | jaeger | `jaeger.service` | `jaeger-all-in-one` |
| - | nginx | `nginx.service` | `nginx` |

## 部署步骤 (裸机 all-in-one)

### 1. 系统准备
```bash
# Ubuntu 22.04
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev \
  postgresql-15 postgresql-server-dev-15 build-essential \
  redis-server nginx git curl

# pgvector 扩展 (PostgreSQL 15)
sudo apt install -y postgresql-15-pgvector

# MinIO (二进制)
wget https://dl.min.io/server/minio/release/linux-amd64/minio -O /usr/local/bin/minio
chmod +x /usr/local/bin/minio
mkdir -p /var/lib/minio
useradd -r minio-user
chown minio-user /var/lib/minio

# Node.js 20
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y nodejs

# Python deps
cd /opt/nanobot-factory
python3.11 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. PostgreSQL + pgvector
```bash
sudo -u postgres psql
CREATE DATABASE imdf;
\c imdf
CREATE EXTENSION IF NOT EXISTS vector;
CREATE USER imdf_app WITH PASSWORD 'change_me_in_production';
GRANT ALL PRIVILEGES ON DATABASE imdf TO imdf_app;
```

### 3. Redis
```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server
redis-cli ping  # PONG
```

### 4. MinIO
```bash
# /etc/default/minio
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=change_me_in_production
MINIO_VOLUMES=/var/lib/minio
MINIO_OPTS="--address :9000 --console-address :9001"

sudo systemctl enable minio
sudo systemctl start minio
# 浏览器访问 http://localhost:9001 创建 bucket (imdf-assets / imdf-temp / imdf-archive)
```

### 5. 数据库迁移 + 数据 seed
```bash
cd /opt/nanobot-factory
source venv/bin/activate
export IMDF_P2_DB_URL=postgresql://imdf_app:change_me@localhost:5432/imdf
export JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
export REDIS_URL=redis://localhost:6379/0
export OSS_ENDPOINT=localhost:9000
export OSS_ACCESS_KEY_ID=minioadmin
export OSS_ACCESS_KEY_SECRET=change_me_in_production
export OSS_BUCKET=imdf-assets

alembic upgrade head
python -m backend.imdf.db.init_db
```

### 6. systemd unit 模板 (复制 12 份)
```ini
# /etc/systemd/system/imdf-gateway.service
[Unit]
Description=imdf api-gateway
After=network.target postgresql.service redis-server.service minio.service

[Service]
Type=simple
User=imdf
WorkingDirectory=/opt/nanobot-factory
Environment="PATH=/opt/nanobot-factory/venv/bin:/usr/bin"
Environment="IMDF_P2_DB_URL=postgresql://imdf_app:change_me@localhost:5432/imdf"
Environment="JWT_SECRET=..."
Environment="REDIS_URL=redis://localhost:6379/0"
ExecStart=/opt/nanobot-factory/venv/bin/uvicorn backend.gateway.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 7. 启动所有服务
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now imdf-gateway \
  imdf-user imdf-asset imdf-annotation imdf-cleaning \
  imdf-scoring imdf-dataset imdf-evaluation imdf-agent \
  imdf-workflow imdf-notification imdf-search imdf-collection \
  imdf-celery imdf-celery-beat

sudo systemctl status imdf-gateway  # 验证 active (running)
curl http://localhost:8000/api/queue/health  # {"status":"ok",...}
```

### 8. Nginx 反代 (公网入口)
```nginx
# /etc/nginx/sites-available/imdf
upstream imdf_gateway {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name imdf.example.com;

    client_max_body_size 1G;

    location /api/ {
        proxy_pass http://imdf_gateway;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location / {
        root /opt/nanobot-factory/frontend-v2/dist;
        try_files $uri $uri/ /index.html;
    }
}

server {
    listen 443 ssl http2;
    server_name imdf.example.com;
    ssl_certificate /etc/letsencrypt/live/imdf.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/imdf.example.com/privkey.pem;
    # 复用上面 location
}
```

### 9. 监控 (Prometheus + Grafana)
```bash
# Prometheus 配置
sudo tee /etc/prometheus/prometheus.yml <<'EOF'
global:
  scrape_interval: 15s
scrape_configs:
  - job_name: 'imdf-services'
    static_configs:
      - targets:
        - localhost:8000  # gateway
        - localhost:8001  # user
        # ... 12 services
EOF
sudo systemctl enable --now prometheus

# Grafana (apt 装)
sudo systemctl enable --now grafana-server
# 浏览器 http://localhost:3000 配 Prometheus data source + import dashboard
```

## 服务重启 / 监控 / 备份

```bash
# 查看所有 imdf 服务状态
sudo systemctl status 'imdf-*' --no-pager

# 重启单个服务
sudo systemctl restart imdf-gateway

# 看实时日志
sudo journalctl -u imdf-gateway -f

# 数据库备份 (cron 每日 3am)
0 3 * * * pg_dump -U imdf_app imdf | gzip > /backup/imdf-$(date +\%Y\%m\%d).sql.gz
```

## 防火墙

```bash
sudo ufw allow 80,443/tcp  # 公网
sudo ufw allow from 192.168.1.0/24 to any port 8000-8012  # 内网微服务
sudo ufw allow 9000:9001/tcp from 192.168.1.0/24  # MinIO 内网
sudo ufw enable
```

## 监控指标端点 (已就位 P3-8)
- `http://host:8000/metrics` - Prometheus text format
- `http://host:8000/healthz` - liveness
- `http://host:8000/readyz` - readiness (DB connected)
- `http://host:8000/api/queue/health` - Celery worker 状态

## 14 链接研究 → P4 启动

P3 完成,等用户帮 clone 14 链接后,启动 P4 综合研究 + 12 微服务深度优化。
