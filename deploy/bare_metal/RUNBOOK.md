# VDP-2026 nanobot-factory — Bare-Metal Cluster Runbook

**P22-P2b** — Real cluster deploy guide. All commands assume a clean
Ubuntu 22.04 LTS / Debian 12 host (or any systemd-equipped Linux).
For Docker/Kubernetes, see `deploy/helm/README.md` and `deploy/k8s/`
instead.

## 0. Architecture at a glance

```
                                  ┌────────────────────────┐
   Public internet ── 443 ───────►│     nginx (TLS)        │
                                  │  /api/*  → gateway    │
                                  │  /*     → frontend    │
                                  └────────┬───────────────┘
                                           │
                  ┌────────────────────────┼────────────────────────┐
                  │                        │                        │
            ┌─────▼─────┐         ┌────────▼────────┐         ┌─────▼─────┐
            │  Gateway  │         │  Domain APIs    │         │  Celery   │
            │  :8000    │         │  8001..8012     │         │  worker   │
            │  4 uvicorn│         │  user/agent/    │         │  5 queues │
            │  workers  │         │  annotation/... │         │           │
            └─────┬─────┘         └────────┬────────┘         └─────┬─────┘
                  │                        │                        │
                  └────────────┬───────────┴────────────┬───────────┘
                               │                        │
                  ┌────────────▼──────┐      ┌───────────▼──────────┐
                  │   postgresql      │      │   redis-server        │
                  │   :5432           │      │   :6379               │
                  └───────────────────┘      └───────────────────────┘
                                                     │
                                          ┌──────────▼──────────┐
                                          │   minio (S3)         │
                                          │   :9000              │
                                          └─────────────────────┘
```

Services exposed (per `deploy/bare_metal/systemd/`):

| Port  | Service          | systemd unit               |
|-------|------------------|-----------------------------|
| 8000  | API gateway      | imdf-gateway.service        |
| 8001  | User service     | imdf-user.service           |
| 8002  | Agent service    | imdf-agent.service          |
| 8003  | Annotation svc   | imdf-annotation.service     |
| 8004  | Asset service    | imdf-asset.service          |
| 8005  | Cleaning service | imdf-cleaning.service       |
| 8006  | Collection svc   | imdf-collection.service     |
| 8007  | Dataset service  | imdf-dataset.service        |
| 8008  | Evaluation svc   | imdf-evaluation.service     |
| 8009  | Workflow service | imdf-workflow.service       |
| 8010  | Notification svc | imdf-notification.service   |
| 8011  | Scoring service  | imdf-scoring.service        |
| 8012  | Search service   | imdf-search.service         |
| -     | Celery worker    | imdf-celery.service         |
| -     | Celery scheduler | imdf-celery-beat.service    |
| -     | Cluster monitor  | imdf-monitor.service        |
| -     | Cluster target   | imdf-cluster.target         |
| 5432  | PostgreSQL       | postgresql.service          |
| 6379  | Redis            | redis-server.service        |
| 9000  | MinIO (S3)       | minio.service               |

---

## 1. First-time install

### 1.1 Prereqs

```bash
# OS packages
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip postgresql-14 redis-server \
                    nginx certbot python3-certbot-nginx

# imdf service account
sudo useradd -r -m -d /var/lib/imdf -s /bin/bash imdf
```

### 1.2 Clone + venv

```bash
sudo -u imdf git clone https://github.com/Nurburgring-Zhang/nanobot-factory.git /opt/nanobot-factory
cd /opt/nanobot-factory
sudo -u imdf python3.11 -m venv venv
sudo -u imdf venv/bin/pip install -r requirements_full.txt
```

### 1.3 Environment file

```bash
sudo mkdir -p /etc/imdf
sudo cp /opt/nanobot-factory/.env.production.example /etc/imdf/imdf.env
sudo chmod 600 /etc/imdf/imdf.env
sudo chown imdf:imdf /etc/imdf/imdf.env

# Edit the env file with your real secrets
sudo nano /etc/imdf/imdf.env
```

Required variables (at minimum):

```bash
# Database
DATABASE_URL=postgresql://imdf:CHANGE_ME@127.0.0.1:5432/imdf
# Redis
REDIS_URL=redis://127.0.0.1:6379/0
# MinIO / S3
S3_ENDPOINT=http://127.0.0.1:9000
S3_ACCESS_KEY=CHANGE_ME
S3_SECRET_KEY=CHANGE_ME
S3_BUCKET=imdf-data
# Celery
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_CONCURRENCY=4
CELERY_QUEUES=default,video,cpu,index,network
CELERY_LOG_LEVEL=INFO
# LLM
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
# Auth
JWT_SECRET=CHANGE_ME_LONG_RANDOM_STRING
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=24
```

### 1.4 Install systemd units

```bash
# Copy every unit to /etc/systemd/system
sudo cp /opt/nanobot-factory/deploy/bare_metal/systemd/*.service \
        /opt/nanobot-factory/deploy/bare_metal/systemd/*.target \
        /etc/systemd/system/

# Copy healthcheck + start-all/stop-all/status/upgrade scripts
sudo cp /opt/nanobot-factory/deploy/bare_metal/scripts/*.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/*.sh

sudo systemctl daemon-reload
```

### 1.5 Database init

```bash
# Bootstrap postgres
sudo -u postgres createuser -s imdf
sudo -u postgres createdb -O imdf imdf
sudo -u postgres psql -c "ALTER USER imdf WITH PASSWORD 'CHANGE_ME';"

# Run migrations
cd /opt/nanobot-factory
sudo -u imdf venv/bin/alembic -c backend/alembic.ini upgrade head
```

### 1.6 TLS certificates

```bash
sudo certbot --nginx -d api.yourdomain.com
```

---

## 2. Day-to-day operations

### 2.1 Start the whole cluster

```bash
sudo systemctl start imdf-cluster.target
sudo systemctl status imdf-cluster.target

# Or, the bundled one-liner:
sudo /usr/local/bin/start-all.sh
```

The cluster target boots every service in dependency order: storage
(postgres / redis / minio) → gateway → domain APIs (12) → celery
worker + beat → monitor.

### 2.2 Stop the cluster

```bash
sudo systemctl stop imdf-cluster.target
# Or:
sudo /usr/local/bin/stop-all.sh
```

### 2.3 Restart a single service

```bash
sudo systemctl restart imdf-gateway.service
sudo systemctl status imdf-gateway.service
sudo journalctl -u imdf-gateway.service -n 50
```

The service's own `Restart=always` handles transient crashes within
~5 seconds. If a service crash-loops, watch for `StartLimitBurst=5`
trips and read the journal for the root cause.

### 2.4 Cluster-wide status

```bash
sudo /usr/local/bin/status.sh
# Shows: each imdf-* service active/inactive + last 5 journal lines
```

### 2.5 Health check

```bash
# One-shot
sudo /usr/local/bin/healthcheck.sh
# exit 0 = healthy, 1 = at least one service down

# Long-running watchdog (used by imdf-monitor.service)
sudo /usr/local/bin/healthcheck.sh --watch --interval=30 \
    --restart-target=imdf-cluster.target \
    --log=/var/log/imdf/monitor.log
```

Watchdog mode runs forever, writing to a log file. On **3 consecutive
failed health-checks** (~90s of bad health) it restarts the cluster
target — this recovers from deadlocks / cluster-wide crashes that
per-service Restart=always can't fix.

### 2.6 Cluster logs

```bash
# All cluster services
sudo journalctl -u imdf-cluster.target --since "1 hour ago"

# One service
sudo journalctl -u imdf-gateway.service -f

# All cluster healthchecks
tail -f /var/log/imdf/monitor.log
```

---

## 3. Upgrade

The cluster supports zero-downtime rolling upgrade via the
`upgrade.sh` script (P22-P2b ships with this).

```bash
# 1. Pull latest code
cd /opt/nanobot-factory
sudo -u imdf git pull origin main

# 2. Update deps
sudo -u imdf venv/bin/pip install -r requirements_full.txt

# 3. Run migrations (alembic handles online schema changes)
sudo -u imdf venv/bin/alembic -c backend/alembic.ini upgrade head

# 4. Restart one service at a time
sudo /usr/local/bin/upgrade.sh
```

`upgrade.sh` iterates through every imdf-* service in the target list,
waiting for each to be healthy before moving on, so the cluster stays
serving traffic throughout (each service is bounced in turn, others
continue answering).

### Rollback

```bash
cd /opt/nanobot-factory
sudo -u imdf git checkout v2.0.0
sudo -u imdf venv/bin/pip install -r requirements_full.txt
sudo -u imdf venv/bin/alembic -c backend/alembic.ini downgrade -1
sudo systemctl restart imdf-cluster.target
```

For multi-step rollbacks, the alembic history shows the linear chain;
use `alembic downgrade <rev>` with the target revision.

---

## 4. Backup + restore

`backup_cron.timer` triggers `backup_cron.sh` daily. Backups land in
`/var/backups/imdf/` (pg_dump) and `/var/backups/imdf/s3/` (MinIO bucket
mirror via mc mirror).

```bash
# Manual backup now
sudo systemctl start backup-cron.service

# List backups
ls -lh /var/backups/imdf/

# Restore from a specific backup
sudo /usr/local/bin/restore.sh /var/backups/imdf/2026-07-12/imdf-pg.sql.gz
```

The `restore.sh` script verifies checksum, stops the cluster, drops
the database, restores the dump, re-runs migrations, and brings the
cluster back up. Point-in-time recovery is supported by combining a
pg_basebackup with the WAL archive (configured in postgresql.conf).

---

## 5. Monitoring

The cluster ships with:

- **Prometheus** (`:9090`) — scrapes `/metrics` from every service
- **Grafana** (`:3000`) — pre-built dashboards under `monitoring/grafana/`
- **Loki + Promtail** — log aggregation
- **Alertmanager** — alerts on Prometheus rules

```bash
sudo systemctl start prometheus.service grafana-server.service \
                      loki.service promtail.service alertmanager.service
```

Default alert rules (in `monitoring/prometheus/rules/`):

- `HighErrorRate` — 5xx > 1% for 5 minutes
- `HighLatency` — p99 > 2s for 5 minutes
- `DiskFull` — any disk > 90%
- `PostgresConnections` — connection count > 80% of `max_connections`
- `RedisMemoryFull` — `used_memory > 80% of maxmemory`

For per-service custom alerts, edit `monitoring/prometheus/rules/*.yml`
and `sudo systemctl reload prometheus.service`.

---

## 6. Capacity planning

| Concurrent users | Gateway workers | Celery concurrency | RAM (host)  | CPU (host)  |
|------------------|-----------------|--------------------|-------------|-------------|
| 100              | 4               | 4                  | 16 GB       | 8 cores     |
| 500              | 8               | 8                  | 32 GB       | 16 cores    |
| **1000 (V5 SLA)**| **16**          | **16**             | **64 GB**   | **32 cores**|
| 5000             | 32              | 32                 | 128 GB      | 64 cores    |

**Tuning knobs** (in `/etc/imdf/imdf.env`):

- `UVICORN_WORKERS` per-service — typically `nproc / 2`
- `CELERY_CONCURRENCY` — `nproc / 2`, or memory-bound: `free -g | awk '/Mem/{print $2/2}'`
- `POSTGRES_SHARED_BUFFERS` — 25% of host RAM
- `POSTGRES_MAX_CONNECTIONS` — `workers × 4 + 100` headroom

---

## 7. Troubleshooting

### Symptom: gateway returns 502

```bash
sudo systemctl status imdf-gateway.service
sudo journalctl -u imdf-gateway.service -n 100 --no-pager
# Most common: imdf-gateway can't reach postgresql/redis. Check:
sudo systemctl status postgresql.service redis-server.service
```

### Symptom: cluster is up but `/readyz` is 503

```bash
# /readyz reports DB or Redis as down. Check:
sudo -u postgres psql -c "SELECT 1;"     # direct DB check
redis-cli ping                            # direct Redis check
sudo systemctl restart imdf-gateway.service
```

### Symptom: high error rate under load

```bash
# Check current RPS / p99
curl -s http://127.0.0.1:8000/metrics | grep -E 'http_requests_total|http_request_duration'

# If p99 > 2s, scale gateway workers:
sudo sed -i 's/--workers [0-9]\+/--workers 16/' /etc/systemd/system/imdf-gateway.service
sudo systemctl daemon-reload
sudo systemctl restart imdf-gateway.service
```

### Symptom: celery tasks piling up

```bash
sudo systemctl status imdf-celery.service imdf-celery-beat.service
sudo journalctl -u imdf-celery.service -n 100
# Check queue depth:
sudo -u imdf venv/bin/celery -A backend.imdf.celery_app:celery_app \
    inspect active
sudo -u imdf venv/bin/celery -A backend.imdf.celery_app:celery_app \
    inspect stats
```

If tasks accumulate: scale `CELERY_CONCURRENCY` up; if memory-bound
OOM, lower it.

### Symptom: imdf-monitor keeps restarting the cluster

```bash
# 3+ consecutive failures = watchdog kicks in. Look for the root cause
# in /var/log/imdf/monitor.log — it logs every health check cycle.
tail -100 /var/log/imdf/monitor.log

# To stop the auto-restart cycle while debugging:
sudo systemctl stop imdf-monitor.service
sudo systemctl restart imdf-cluster.target
# … then investigate before re-enabling the monitor
sudo systemctl start imdf-monitor.service
```

---

## 8. Files of interest

- `deploy/bare_metal/systemd/` — 25+ systemd unit files
- `deploy/bare_metal/systemd/imdf-cluster.target` — single-target cluster boot
- `deploy/bare_metal/systemd/imdf-monitor.service` — watchdog (P22-P2b)
- `deploy/bare_metal/scripts/healthcheck.sh` — both one-shot and watch modes
- `deploy/bare_metal/scripts/upgrade.sh` — zero-downtime rolling upgrade
- `deploy/bare_metal/scripts/restore.sh` — point-in-time recovery
- `deploy/bare_metal/backup_cron.sh` + `backup_cron.{service,timer}` — daily backups
- `deploy/bare_metal/.env.example` — env template
- `deploy/bare_metal/install.sh` — full one-shot install
- `deploy/bare_metal/README.md` — parent install doc
- `deploy/nginx/nginx.conf` — TLS reverse proxy

---

**This runbook is the source of truth for P22-P2b "real cluster deploy".
For Helm/Kubernetes, see `deploy/helm/README.md`.**
