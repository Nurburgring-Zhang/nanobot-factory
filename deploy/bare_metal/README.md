# Bare-Metal Deployment Guide

> **Status**: PRODUCTION READY · **Owner**: Platform Team · **Last updated**: 2026-06-24

This directory contains the complete bare-metal deployment for **nanobot-factory VDP-2026** (智影 / ZhiYing). All 12 microservices run as standalone `systemd` units under the `imdf` user — no Docker, no Kubernetes, no containers.

The legacy `deploy/k8s/` and `deploy/helm/` trees are marked **DEPRECATED** and must not be used on production. The `deploy/entrypoint.sh` dev helper is kept for local Windows + Git Bash workflow only.

---

## 1. Architecture overview

```
                    ┌─────────────────────────────────────────────┐
                    │  nginx (80/443)  ← public traffic + static   │
                    └────────────────────┬────────────────────────┘
                                         │
                                ┌────────▼─────────┐
                                │  imdf-gateway    │  :8000 (4 workers)
                                └────────┬─────────┘
                                         │ HTTP
        ┌────────┬────────┬─────────┬─────┴───────┬─────────┬────────┐
        ▼        ▼        ▼         ▼             ▼         ▼        ▼
   imdf-user imdf-asset imdf-annot imdf-clean  imdf-score imdf-data imdf-eval
     :8001     :8002     :8003     :8004        :8005     :8006     :8007

   imdf-agent imdf-workflow imdf-notif imdf-search imdf-collection
     :8008      :8009        :8010     :8011      :8012

        ┌──────────────────┐         ┌─────────────────────────┐
        │ imdf-celery      │ ──────► │  Redis 7  (broker+state) │
        │ imdf-celery-beat │         └─────────────────────────┘
        └──────────────────┘
                │
                ▼
        ┌──────────────────┐         ┌─────────────────────────┐
        │ PostgreSQL 15    │         │  MinIO (S3-compatible)  │
        │ + pgvector       │         │  :9000 API / :9001 UI   │
        └──────────────────┘         └─────────────────────────┘

        ┌──────────────────┐         ┌─────────────────────────┐
        │ Prometheus :9090 │         │  Grafana :3000          │
        │ Jaeger   :16686  │         │  Loki    :3100          │
        │ Promtail         │         │  Alertmanager :9093     │
        └──────────────────┘         └─────────────────────────┘
```

| Layer | Components | Run as |
|-------|------------|--------|
| Edge | nginx, certbot | root |
| App | imdf-gateway + 12 services + 2 celery | `imdf` |
| Data | PostgreSQL+pgvector, Redis 7, MinIO | `postgres`, `redis`, `minio-user` |
| Observability | Prometheus, Grafana, Jaeger, Loki, Promtail, Alertmanager | `prometheus`, `grafana`, `jaeger`, `loki`, `promtail` |

---

## 2. Hardware minimum

| Role | CPU | RAM | Disk | Notes |
|------|-----|-----|------|-------|
| all-in-one dev | 8 cores | 32 GB | 1 TB SSD | Ubuntu 22.04 LTS |
| production (12 svc) | 16 cores | 64 GB | 2 TB SSD + 4 TB HDD | Ubuntu 22.04 LTS |
| GPU AI ops | + RTX 4090 / A100 | + 24 GB VRAM | — | Optional, separate node |

---

## 3. The 8 deployment steps

### Step 1 · System preparation

```bash
# Ubuntu 22.04 — root
apt update && apt upgrade -y
apt install -y python3.11 python3.11-venv python3.11-dev \
  postgresql-15 postgresql-server-dev-15 build-essential git curl \
  nginx redis-server certbot python3-certbot-nginx \
  prometheus grafana

# Optional observability
wget -qO /usr/local/bin/jaeger https://github.com/jaegertracing/jaeger/releases/download/v1.55/jaeger-1.55-linux-amd64
chmod +x /usr/local/bin/jaeger

# Node.js 20 (frontend build)
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt install -y nodejs
```

### Step 2 · Create the `imdf` system user

```bash
sudo ./install.sh            # runs `useradd imdf`, lays out /opt + /etc/imdf
```

### Step 3 · PostgreSQL + pgvector

```bash
# install.sh configures postgresql.conf + pg_hba.conf and creates the imdf DB
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "ALTER USER imdf_app WITH PASSWORD '$(awk -F= '/^DB_APP_PASSWORD=/ {print $2}' /etc/imdf/imdf.env)';"
sudo -u postgres psql -d imdf -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Step 4 · Redis

```bash
sudo systemctl enable --now redis-server
redis-cli ping        # → PONG
```

### Step 5 · MinIO

```bash
wget -qO /usr/local/bin/minio https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x /usr/local/bin/minio
mkdir -p /var/lib/minio
useradd -r -s /sbin/nologin minio-user
chown -R minio-user:minio-user /var/lib/minio
sudo systemctl enable --now minio
# open http://<host>:9001 → create buckets: imdf-assets / imdf-temp / imdf-archive
```

### Step 6 · Database migration + seed

```bash
sudo -u imdf bash -c '
  source /etc/imdf/imdf.env
  cd /opt/nanobot-factory
  $IMDF_VENV/bin/alembic -c backend/alembic.ini upgrade head
'
```

### Step 7 · systemd — enable & start everything

```bash
sudo cp deploy/bare_metal/systemd/imdf-*.service /etc/systemd/system/
sudo cp deploy/bare_metal/systemd/{postgresql,redis-server,minio,prometheus,grafana-server,jaeger,loki,promtail}.service /etc/systemd/system/   # only if not provided by apt
sudo systemctl daemon-reload

sudo deploy/bare_metal/scripts/start-all.sh
```

### Step 8 · nginx + TLS

```bash
sudo cp deploy/bare_metal/configs/nginx-imdf.conf /etc/nginx/sites-available/imdf
sudo ln -sf /etc/nginx/sites-available/imdf /etc/nginx/sites-enabled/imdf
sudo certbot --nginx -d imdf.example.com
sudo systemctl restart nginx
curl -fsS https://imdf.example.com/api/queue/health    # → {"status":"ok",...}
```

---

## 4. File map

```
deploy/bare_metal/
├── README.md                  ← you are here
├── install.sh                 ← idempotent installer (apt + binary + user + dirs)
├── .env.example               ← full environment variable template
├── configs/
│   ├── postgresql.conf        ← tuned for 64 GB / 16 cores
│   ├── pg_hba.conf            ← allow imdf_app from 127.0.0.1 + LAN
│   ├── redis.conf             ← tuned for 64 GB
│   ├── minio.env              ← MINIO_ROOT_USER / PASSWORD / VOLUMES
│   ├── prometheus.yml         ← scrapes 12 services + node-exporter
│   ├── alertmanager.yml       ← routes to Slack + PagerDuty
│   ├── grafana-datasources.yml
│   ├── grafana-dashboards.yml
│   ├── loki-config.yaml
│   ├── jaeger-config.yaml
│   └── nginx-imdf.conf        ← reverse proxy + static frontend
├── systemd/
│   ├── imdf-gateway.service          :8000   4 workers
│   ├── imdf-user.service             :8001   2 workers
│   ├── imdf-asset.service            :8002
│   ├── imdf-annotation.service       :8003
│   ├── imdf-cleaning.service         :8004
│   ├── imdf-scoring.service          :8005
│   ├── imdf-dataset.service          :8006
│   ├── imdf-evaluation.service       :8007
│   ├── imdf-agent.service            :8008
│   ├── imdf-workflow.service         :8009
│   ├── imdf-notification.service     :8010
│   ├── imdf-search.service           :8011
│   ├── imdf-collection.service       :8012
│   ├── imdf-celery.service           celery worker (concurrency 4)
│   ├── imdf-celery-beat.service      celery scheduler
│   ├── postgresql.service            (only if not provided by apt)
│   ├── redis-server.service          (only if not provided by apt)
│   ├── minio.service
│   ├── prometheus.service
│   ├── grafana-server.service
│   ├── jaeger.service
│   ├── loki.service
│   ├── promtail.service
│   └── alertmanager.service
└── scripts/
    ├── start-all.sh            ← systemctl enable --now imdf-* + dependencies
    ├── stop-all.sh             ← systemctl stop imdf-*
    ├── status.sh               ← systemctl status imdf-* (tabular)
    ├── backup-db.sh            ← legacy pg_dump (called by backup_cron.sh)
    ├── backup_cron.sh          ← unified PG/Redis/OSS backup + tiering (systemd)
    ├── backup_cron.service     ← systemd unit for backup_cron.sh
    ├── backup_cron.timer       ← systemd timer (03:00 + Sun 04:00)
    ├── restore.sh              ← tiered restore helper (--component pg|redis|oss)
    ├── upgrade.sh              ← git pull + pip install + alembic + restart
    └── healthcheck.sh          ← curl /api/queue/health every 30s
```

---

## 5. Day-2 operations

```bash
# status of every imdf unit
sudo deploy/bare_metal/scripts/status.sh

# tail logs
sudo journalctl -u imdf-gateway -f
sudo journalctl -u imdf-celery -f

# graceful restart of one service
sudo systemctl restart imdf-gateway

# rolling restart of all app services
sudo deploy/bare_metal/scripts/stop-all.sh
sudo deploy/bare_metal/scripts/start-all.sh

# upgrade
sudo deploy/bare_metal/scripts/upgrade.sh v1.7.0
```

---

## 6. Security checklist

- [x] All `imdf-*` services run as non-root user `imdf`
- [x] `NoNewPrivileges`, `PrivateTmp`, `ProtectSystem=strict`, `ProtectHome=yes`
- [x] `JWT_SECRET_KEY` ≥ 32 bytes random (`openssl rand -hex 32`)
- [x] `AUDIT_CHAIN_SECRET` ≥ 32 bytes random (OWASP A08)
- [x] `OSS_ACCESS_KEY_SECRET` rotated, never committed
- [x] `EnvironmentFile=/etc/imdf/imdf.env` is `chmod 600 imdf:imdf`
- [x] DB password separate from `postgres` superuser
- [x] nginx rate-limits `/api/auth/*` (10 req/min/IP)
- [x] `client_max_body_size 1G` for asset uploads
- [x] TLS via Let's Encrypt (`certbot --nginx`)

---

## 7. Backup & disaster recovery

The backup system runs on **systemd timers** (not cron) and covers PG, Redis, and OSS across three retention tiers.

### 7.1 Backup schedule (systemd timer)

| When        | What              | Tier migration                  | Where                            |
|-------------|-------------------|----------------------------------|----------------------------------|
| 03:00 daily | `pg_dump` (full)  | hot 7d → warm 30d → cold 365d   | `/var/backups/imdf/db`           |
| 03:30 daily | Redis `BGSAVE` RDB | same tiers                     | `/var/backups/imdf/redis`        |
| Sun 04:00   | OSS `mc mirror`  | same tiers                      | `/var/backups/imdf/oss`          |
| Sun 04:30   | sample-restore verify (PG + Redis header checks) | — | `/var/log/imdf-backup/` |

All run via `backup_cron.sh` + `backup_cron.timer` (systemd), not crontab. Logs: `/var/log/imdf-backup/backup-YYYYMMDD.log`.

### 7.2 Install & enable

```bash
sudo cp deploy/bare_metal/backup_cron.{sh,service,timer} /etc/systemd/system/ /opt/nanobot-factory/deploy/bare_metal/
sudo chmod 750 /opt/nanobot-factory/deploy/bare_metal/backup_cron.sh /opt/nanobot-factory/deploy/bare_metal/restore.sh
sudo systemctl daemon-reload
sudo systemctl enable --now imdf-backup.timer
sudo systemctl list-timers imdf-backup.timer   # confirm next run
```

Manual trigger (one-off):

```bash
# full nightly (PG + Redis + OSS + verify)
sudo systemctl start imdf-backup.service

# single component
sudo BACKUP_TARGETS=pg /opt/nanobot-factory/deploy/bare_metal/backup_cron.sh
sudo BACKUP_TARGETS=redis /opt/nanobot-factory/deploy/bare_metal/backup_cron.sh
sudo BACKUP_TARGETS=oss /opt/nanobot-factory/deploy/bare_metal/backup_cron.sh
```

### 7.3 Retention tiers

| Tier    | Path                                | Default retention | Use case                          |
|---------|-------------------------------------|-------------------|-----------------------------------|
| hot     | `/var/backups/imdf/{db,redis,oss}/` | 7 days            | Fast local restore (RPO ≤ 24h)   |
| warm    | `/var/backups/imdf/warm/`           | 30 days           | Local disk recovery (RPO ≤ 7d)   |
| cold    | `/var/backups/imdf/cold/`           | 365 days          | Archival (compliance / forensics) |

Override per environment:

```bash
# /etc/imdf/imdf.env
HOT_TIER_DAYS=14
WARM_TIER_DAYS=60
COLD_TIER_DAYS=730
BACKUP_NOTIFY_WEBHOOK=https://hooks.slack.com/services/...   # optional Slack ping
```

### 7.4 Restore (operational runbook)

The `restore.sh` helper handles all three components and refuses to run without explicit `YES` confirmation.

```bash
# List available backups
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh --list

# Verify integrity without restoring
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh --component pg --latest --verify

# Restore latest PG dump to a NEW database (safe; doesn't clobber prod)
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
  --component pg --latest --target imdf_restored_$(date +%s)

# Restore a specific date
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
  --component pg --date 2026-06-23

# Restore a specific file
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
  --component redis --file /var/backups/imdf/redis/dump-20260624-030000.rdb.gz

# Restore OSS bucket from cold tier
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
  --component oss --latest

# Skip confirmation (for automation)
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh --component pg --latest --yes
```

PG restore creates a **new database** with timestamp suffix (e.g. `imdf_restored_1719225600`) so the original `imdf` DB is never overwritten. After verifying the restored DB, switch over manually:

```sql
ALTER DATABASE imdf RENAME TO imdf_old;
ALTER DATABASE imdf_restored_1719225600 RENAME TO imdf;
```

Redis restore stops `redis-server`, swaps in the RDB, then restarts. OSS restore uses `mc mirror` to re-populate the bucket.

### 7.5 Disaster recovery checklist

- [ ] Run `restore.sh --list` weekly to confirm backups exist
- [ ] Sample-restore drill every Sunday (auto via `backup_cron.sh`)
- [ ] Test off-host restore quarterly (copy `/var/backups/imdf/cold/` to a separate machine)
- [ ] Verify cold tier is replicated off-site (rsync to backup DC or `mc mirror` to remote bucket)
- [ ] WAL archiving to `/var/backups/imdf/wal/` enabled in `postgresql.conf` (for PITR beyond daily snapshots)
- [ ] Document RTO (≤ 1h) and RPO (≤ 24h) in on-call runbook

---

## 8. Migrating from `deploy/k8s/`

The Kubernetes tree is **DEPRECATED** since 2026-06. Operators on K8s should:

1. Drain the cluster (`kubectl drain` + `kubectl delete -f deploy/k8s/`).
2. Provision a Ubuntu 22.04 VM matching the prod hardware profile.
3. Run `install.sh`, then steps 1–8 above.
4. Restore DB from the latest K8s `pg_dump` snapshot.

The k8s manifests remain in tree for diffing/replay only — do not `kubectl apply`.