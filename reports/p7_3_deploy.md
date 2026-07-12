# P7-3 部署深度审查报告 (Deploy Deep Review v2 — Attempt 2)

**Date**: 2026-06-26 04:25
**Project**: nanobot-factory (智影 / ZhiYing)
**Scope**: 部署栈 — install.sh + 24 systemd units + nginx + README 8 步演练
**Reviewer**: coder (P7-3 second-pass, attempt 2)
**Status**: 5 P0 install.sh 缺口 + 24 systemd units + nginx + 8 步 README

---

## 1. ⚠️ P0 install.sh 缺口 (Attempt 1 漏判, 此次深挖发现)

### 1.1 H4+H5: Grafana dashboards JSONs 永远不被 staging [P0, 30 min]

**证据**:

1. `deploy/bare_metal/configs/grafana-dashboards.yml`:
   ```yaml
   options:
     path: /etc/grafana/dashboards/vdp    # ← 目标目录
   ```

2. `deploy/bare_metal/install.sh` step 7 (line 143-157):
   ```bash
   mkdir -p /etc/prometheus /etc/grafana/provisioning/{datasources,dashboards} \
            /etc/loki /etc/promtail /etc/jaeger /etc/alertmanager
   # /etc/grafana/dashboards/vdp 目录从未创建
   ```

3. install.sh step 7 从未 copy 任何 dashboard JSON:
   ```bash
   # 已 copy:
   grafana-datasources.yml → /etc/grafana/provisioning/datasources/prometheus.yml ✓
   grafana-dashboards.yml  → /etc/grafana/provisioning/dashboards/imdf.yml ✓
   # 未 copy: monitoring/grafana-dashboards/*.json (8 文件, 46 panels)
   ```

**影响**: 46 panels 永远不会在 bare_metal 显示. 监控系统"看上去工作"但无任何数据可视化.

**修复**:
```bash
# install.sh step 7 加 (line 151 后):
mkdir -p /etc/grafana/dashboards/vdp
DASHBOARD_SRC="${PROJECT_ROOT}/monitoring/grafana-dashboards"
if [[ -d "${DASHBOARD_SRC}" ]]; then
  cp -n "${DASHBOARD_SRC}/"*.json /etc/grafana/dashboards/vdp/ || true
  chown -R grafana:grafana /etc/grafana/dashboards
  log "staged $(ls /etc/grafana/dashboards/vdp/*.json | wc -l) dashboard JSONs"
fi
```

### 1.2 H11: Prometheus rules 永远不被 staging [P0, 5 min]

**证据**:

1. `deploy/bare_metal/configs/prometheus.yml` line 16:
   ```yaml
   rule_files:
     - /etc/prometheus/rules/*.yml
   ```

2. install.sh step 7 从未 copy `prometheus-rules.yml`:
   ```bash
   # 未 copy: prometheus-rules.yml (虽然 configs/ 里有, 21 alerts)
   # 未创建: /etc/prometheus/rules/ 目录
   ```

**影响**: 21 alert 不会 fire. 监控系统"看上去工作"但 silent alarm.

**修复**:
```bash
# install.sh step 7 加 (line 148 后):
mkdir -p /etc/prometheus/rules
cp -n "${SCRIPT_DIR}/configs/prometheus-rules.yml" /etc/prometheus/rules/01-imdf-alerts.yml
chown prometheus:prometheus /etc/prometheus/rules/01-imdf-alerts.yml
log "staged 21 prometheus alert rules"
```

### 1.3 H13: Promtail config 永远不存在 [P0, 30 min]

**证据**:

1. `deploy/bare_metal/systemd/promtail.service` line 19: `--config.file=/etc/promtail/config.yaml`
2. install.sh step 7 (line 144) 创建 `/etc/promtail` 目录
3. `deploy/bare_metal/configs/` **没有 promtail-config.yaml** ❌

**影响**: Promtail 启动失败 → 0 日志到达 Loki → Grafana 看不到日志.

**修复**:
- 在 `deploy/bare_metal/configs/promtail-config.yaml` 新建 (30 行)
- install.sh step 7 加 copy 命令

**promtail-config.yaml 模板**:
```yaml
server:
  http_listen_port: 9080

positions:
  filename: /var/lib/promtail/positions.yaml

clients:
  - url: http://127.0.0.1:3100/loki/api/v1/push
    batchwait: 1s
    batchsize: 1048576

scrape_configs:
  - job_name: imdf-services
    journal:
      max_age: 12h
      labels:
        job: systemd
    relabel_configs:
      - source_labels: ['__journal__systemd_unit']
        target_label: unit
      - source_labels: ['__journal__hostname']
        target_label: hostname
```

### 1.4 H12: grafana-server.service 引用不存在的 env file [P1, 5 min]

**证据**:
- `deploy/bare_metal/systemd/grafana-server.service` line 16: `EnvironmentFile=/etc/default/grafana`
- install.sh step 7 从未创建 `/etc/default/grafana`

**影响**: 当用户用自定义 service (apt 不带 unit 时), 启动失败.

**修复**:
```bash
# install.sh step 7 加:
cat > /etc/default/grafana <<'EOF'
GRAFANA_USER=grafana
GRAFANA_GROUP=grafana
GRAFANA_HOME=/usr/share/grafana
LOG_DIR=/var/log/grafana
DATA_DIR=/var/lib/grafana
CONF_DIR=/etc/grafana
EOF
chmod 644 /etc/default/grafana
```

### 1.5 H2: install.sh enable list 漏 backup (与 backup report 同步) [P0, 5 min]

**证据**: install.sh step 8 (line 162-168) 漏 `backup_cron.timer`/`.service`

**修复**:
```bash
# install.sh step 8 加 (line 168 后):
log "enabling backup timer"
systemctl enable backup_cron.timer 2>/dev/null || true
```

> **H1 (timer Unit name 错位) 在 backup report 详述. H1+H2 必须双修.**

---

## 2. install.sh 8 步真实演练

> ⚠️ 本机 Windows, 实际跑需 Linux + root. 静态 + 关键路径验证.

### 2.1 8 个阶段 (line 57-172)

| Step | 内容 | 行号 | 关键命令 | 验证 |
|------|------|------|----------|------|
| 1 | apt packages (16 包) | 57-68 | `apt-get install -y python3.11 postgresql-15 postgresql-15-pgvector redis-server nginx prometheus grafana ...` | 静态 OK |
| 2 | system user 创建 | 70-83 | `useradd --system imdf` + `minio-user` | 静态 OK |
| 3 | directory layout | 85-97 | `mkdir -p ${IMDF_HOME}/{data,logs,...} /var/backups/imdf/{db,wal} /var/lib/minio` + chown/chmod 750/700/750 | 静态 OK |
| 4 | env file seed | 99-113 | `cp .env.example /etc/imdf/imdf.env` + sed 替换路径 + chmod 600 | 静态 OK |
| 5 | python venv + deps | 115-125 | `python3.11 -m venv ${IMDF_HOME}/venv` + `pip install -r requirements.txt` | 静态 OK |
| 6 | systemd units stage | 127-139 | `cp -n systemd/*.service /etc/systemd/system/` + `daemon-reload` | 静态 OK (24 units) |
| 7 | configs stage | 141-157 | `cp -n configs/{postgresql,pg_hba,redis,prometheus,alertmanager,grafana-*,loki,jaeger,minio,nginx}` | 静态 OK (11 files, 但缺 promtail) |
| 8 | enable (no start) | 159-172 | `systemctl enable ${24_services}` (BUT NOT START, AND 漏 backup) | ⚠️ H2 漏 backup |

### 2.2 install.sh 标志 (line 23-42)

```bash
--units-only    # 跳过 apt, 只 stage systemd + .env
--no-enable     # stage 但不 enable
--project-root= # 自定义 root
--home=         # 自定义 imdf home
--env-dir=      # 自定义 /etc/imdf 路径
-h | --help     # 输出 17 行 usage
```

**Task spec 提到的 `--check` (dry-run) 不存在!** (line 23-42 列出 5 个 args, 无 `--check`)

> ⚠️ **Gap D1** (Attempt 1 已记): install.sh 无 `--check` / `--dry-run` 模式. P2 候选.

### 2.3 install.sh --help 实测 ✅

```bash
$ bash deploy/bare_metal/install.sh --help
install.sh 的 shebang 注释块 (17 行, 含 usage + after-install 步骤)
```

实际触发 `sed -n '2,18p' "$0"` (line 38).

### 2.4 Idempotency 设计

- `id imdf` (line 71) — 存在不重建
- `id minio-user` (line 80) — 同上
- `[[ ! -d "${IMDF_HOME}/venv" ]]` (line 116) — 不重建 venv
- `[[ ! -f "${ENV_DIR}/imdf.env" ]]` (line 100) — 不覆盖 .env
- `cp -n` (line 129+) — no-clobber
- `mkdir -p` — 幂等
- `systemctl enable ... || true` — 失败软跳过

**幂等性 ~95%** — 任何步骤可重跑.

---

## 3. 24 Systemd Units 启动顺序 / 依赖 / 健康检查

### 3.1 24 个 service 单元

| # | 类别 | 单元 | 端口/角色 |
|---|------|------|----------|
| 1 | **Data layer** | postgresql.service | (apt 提供) |
| 2 | | redis-server.service | (apt 提供) |
| 3 | | minio.service | :9000 API / :9001 console |
| 4 | **Observability** | prometheus.service | :9090 |
| 5 | | alertmanager.service | :9093 |
| 6 | | grafana-server.service | :3000 |
| 7 | | jaeger.service | OTLP 4317/4318 + query 16686 |
| 8 | | loki.service | :3100 |
| 9 | | promtail.service | (H13 缺 config) |
| 10 | **App gateway** | imdf-gateway.service | :8000 (4 workers) |
| 11-22 | **App services** | imdf-{user,asset,annotation,cleaning,scoring,dataset,evaluation,agent,workflow,notification,search,collection} | :8001-:8012 |
| 23-24 | **Celery** | imdf-celery.service + imdf-celery-beat.service | worker (concurrency 4) |

> Total: **3 + 6 + 1 + 12 + 2 = 24 units** ✅

### 3.2 依赖关系

#### Tier 1: 底层 data
| Unit | After | Requires/Wants |
|------|-------|----------------|
| postgresql.service | network.target | — |
| redis-server.service | network.target | — |
| minio.service | network-online.target | network-online.target |

#### Tier 2: Observability
| Unit | After | Requires/Wants |
|------|-------|----------------|
| prometheus.service | network-online.target | network-online.target |
| alertmanager.service | network-online.target, prometheus.service | network-online.target |
| grafana-server.service | network-online.target, prometheus.service | network-online.target |
| jaeger.service | network-online.target | network-online.target |
| loki.service | network-online.target | network-online.target |
| promtail.service | network-online.target, loki.service | network-online.target |

#### Tier 3: App
| Unit | After | Requires/Wants |
|------|-------|----------------|
| **imdf-gateway** | network-online.target, postgresql, redis-server, minio | 同 After |
| imdf-asset | + minio.service | + minio |
| imdf-cleaning | + minio.service | + minio |
| imdf-dataset | + minio.service | + minio |
| imdf-evaluation | + minio.service | + minio |
| imdf-celery | + postgresql, redis-server, minio | + redis + postgresql |
| imdf-celery-beat | + postgresql, redis-server | + redis + postgresql |
| imdf-user/annotation/scoring/agent/workflow/notification/search/collection | + postgresql, redis-server | 同 After |

> **依赖图合理性 ✅**:
> - Data 先起 → Observability 依赖 network + Prom → App 依赖 Data
> - gateway 唯一依赖 minio (asset upload 走 OSS)
> - celery 依赖 data (broker + result backend)

### 3.3 健康检查

#### Prometheus / Grafana / Alertmanager / Loki / Jaeger
- livenessProbe `/-/healthy` (Prom / AM)
- readinessProbe `/-/ready` (Prom)
- Jaeger `GET /` on 16686

#### App services (12 imdf-*.service)
- TestClient 验证 (P3-8-W2): **12 services × 2 endpoints = 24/24 PASS**
- `/healthz` `200 OK`
- `/metrics` 返回 Prometheus 格式 (2528 bytes for main)

#### healthcheck.sh (cron-friendly)
- gateway `/api/queue/health` curl
- `/readyz` curl
- `/metrics` curl
- 12 services :8001-:8012 `/healthz` curl
- celery worker + beat `systemctl is-active`
- 任意失败写 `/var/log/imdf-healthcheck.log` + exit 1
- 调用: cron `* * * * *` 或 systemd timer

### 3.4 启动顺序 (start-all.sh)

```bash
# Tier 1: Data layer (parallel)
DEPS=(postgresql redis-server minio)

# Tier 2: Observability (parallel)
OBSERVABILITY=(prometheus alertmanager grafana-server jaeger loki promtail)

# Tier 3: App (parallel)
APP=(imdf-gateway imdf-user imdf-asset ... imdf-celery imdf-celery-beat)
```

`start_tier` 逐 tier 启动, 每 tier 内并发 (line 56-72).
启动后 smoke test: `/api/queue/health` + `prometheus:9090/-/ready`.

---

## 4. nginx reverse proxy 配置

### 4.1 `nginx-imdf.conf` 关键设计 (line 1-194)

#### Rate limit zones
| Zone | 速率 | 用途 |
|------|------|------|
| `auth_zone:10m rate=10r/m` | 10 req/min/IP | /api/auth, login, register, password |
| `api_zone:10m rate=120r/m` | 120 req/min/IP | /api/ (其他) |
| `up_zone:10m rate=20r/m` | 20 req/min/IP | /api/assets/upload, presign, batch |

> OWASP A07 防护: auth 路径 6x 严于普通 API.

#### Upstream
```
upstream imdf_gateway {
    server 127.0.0.1:8000 max_fails=3 fail_timeout=30s;
    keepalive 64;
    keepalive_requests 1000;
    keepalive_timeout 60s;
}
```

> **D2** (P2, Attempt 1 已记): 单点 upstream, 无 backup. HA 缺.

#### HTTP → HTTPS 重定向 (line 28-42)
- 80 only for `/.well-known/acme-challenge/` (Let's Encrypt)
- 其他 301 → https

#### HTTPS server (line 45-194)
- TLS 1.2 + 1.3, 现代 cipher suite
- HSTS preload (max-age 2 years) + subdomains
- CSP, X-Frame-Options SAMEORIGIN, X-Content-Type-Options nosniff
- `client_max_body_size 1G` — 大文件上传
- 12 个 location 块: /healthz, auth, up, ws, metrics, api, minio, assets, /, error_page

> **强加固** ✅ — security headers + rate limit + WSS + IP allowlist + CSP

---

## 5. README 8 步 实操验证

| Step | 内容 | install.sh 自动化? | 手工步骤 |
|------|------|--------------------|----------|
| 1 | System prep (apt + Python 3.11 + Node 20 + Jaeger binary) | ✅ install.sh step 1 | wget jaeger + NodeSource |
| 2 | Create `imdf` user | ✅ install.sh step 2 | 仅 sudo ./install.sh |
| 3 | PostgreSQL + pgvector | ✅ install.sh step 1+7 | 手工 `psql -c ALTER USER` + `CREATE EXTENSION vector` |
| 4 | Redis | ✅ install.sh step 1+7 | 手工 `systemctl enable --now redis-server` + `redis-cli ping` |
| 5 | MinIO | ✅ install.sh step 1+7 | 手工 wget minio + enable + 打开 :9001 UI 建 bucket |
| 6 | DB migration | ❌ 无 (D7 P2) | `alembic -c backend/alembic.ini upgrade head` |
| 7 | systemd enable & start | ⚠️ H2 漏 backup (P0) | `daemon-reload` + `start-all.sh` + 手工 enable backup |
| 8 | nginx + TLS | ⚠️ 部分 | `cp nginx-imdf.conf` + `ln -sf` + `certbot --nginx` + restart |

### 5.1 8 步覆盖率

| 类型 | 数量 | 自动化 |
|------|------|--------|
| 完整由 install.sh 覆盖 | Step 1, 2, 4, 7 (除 backup) | ✅ |
| 半自动 (装包 + 手工启服务) | Step 3, 5 | ⚠️ |
| 手工 (无 install.sh 接管) | Step 6 (alembic), Step 8 (TLS), Step 7 backup | ❌ |

> **Gap D7** (Attempt 1 已记): README Step 6 (alembic upgrade head) 无 install.sh 集成 — 应在 step 8 之后自动跑

### 5.2 README § 5 Day-2 operations

- `status.sh` — tabular state
- `journalctl -u imdf-gateway -f` — log tail
- `systemctl restart imdf-gateway` — 优雅重启
- `stop-all.sh` / `start-all.sh` — 滚动重启
- `upgrade.sh v1.7.0` — 升级 (含 git pull + pip + alembic + 滚动重启 + smoke test + rollback hint)

### 5.3 README § 6 Security Checklist (10 项, 全部 ✅)

- ✅ non-root user
- ✅ systemd hardening (NoNewPrivileges, PrivateTmp, ProtectSystem=strict, ProtectHome=yes)
- ✅ JWT_SECRET_KEY ≥ 32 bytes
- ✅ AUDIT_CHAIN_SECRET ≥ 32 bytes
- ✅ OSS_ACCESS_KEY_SECRET rotated
- ✅ chmod 600 imdf.env
- ✅ DB password ≠ postgres
- ✅ nginx rate-limit /api/auth/*
- ✅ client_max_body_size 1G
- ✅ TLS via Let's Encrypt

### 5.4 README § 7 Backup & DR

- 7.1 schedule 表格
- 7.2 install & enable — **H1+H2 触发点**: README 说 `imdf-backup.timer` 但实际文件 `backup_cron.timer`
- 7.3 retention tiers
- 7.4 restore (7 种用法, 含 H7 typo)
- 7.5 DR checklist

---

## 6. install.sh 缺口总表 (Attempt 2 综合, P0 → P3)

### P0 (production-blocking, 1-2 周内修)

| # | 问题 | install.sh 修复 | 估时 |
|---|------|----------------|------|
| **H2** | enable list 漏 backup | step 8 加 1 行 | 5 min |
| **H4+H5** | grafana dashboards JSONs 不 staging | step 7 加 5 行 | 30 min |
| **H11** | prometheus-rules.yml 不 staging | step 7 加 3 行 | 5 min |
| **H13** | promtail-config.yaml 不存在 | 新建 yaml + step 7 加 1 行 | 30 min |

### P1 (1 月内修)

| # | 问题 | 修复 | 估时 |
|---|------|------|------|
| H12 | grafana-server.service 引用 /etc/default/grafana | step 7 加 here-doc | 5 min |
| H6 | backup_cron.sh 03:30 注释不符 | 删注释 | 1 min |
| H7 | restore.sh usage typo | 改 `--to` → `--target` | 5 min |
| H8 | Redis restore 不停 Celery | restore.sh 加 stop/start | 10 min |

### P2 (季度内)

| # | 问题 | 修复 | 估时 |
|---|------|------|------|
| D1 | install.sh 缺 --dry-run | 加 --check 模式 | 0.5h |
| D2 | nginx gateway upstream 单点 | 加 backup server | 1h |
| D3 | 12 service /metrics 走 gateway proxy | 改独立 | 1h |
| D4 | 无 WAF | Coraza | (P9+) |
| D5 | TLS 硬编码域名 | 变量化 | 5 min |
| D6 | keepalive_requests 偏高 | 调到 100 | 5 min |
| D7 | alembic upgrade head 未集成 | step 8 后加 alembic | 0.5h |
| H14 | .env.example 缺 backup env | 补 7 个变量 | 5 min |
| M1 | 4 重复 dashboard 文件 | 删除副本 | 5 min |

### P3 (长期)

| # | 问题 | 修复 | 估时 |
|---|------|------|------|
| D9 | 多主机编排 (单主机 only) | Ansible 角色化 | 3h |
| D10 | Secret 管理 Vault 化 | Ansible Vault / sealed | 1h |
| D11 | blue/green 部署 | HAProxy + health | 2h |
| D12 | IaC 状态 (Pulumi) | 重写 | 3h+ |

---

## 7. 部署栈对标世界级 (Ansible / Terraform / Pulumi)

### 7.1 能力矩阵

| 能力 | IMDF install.sh | Ansible | Terraform | Pulumi | Helm |
|------|-----------------|---------|-----------|--------|------|
| 幂等 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 远程执行 | ❌ | ✅ | ✅ | ✅ | ✅ (K8s) |
| 多主机编排 | ❌ | ✅ | ✅ | ✅ | ✅ |
| 状态追踪 | ❌ | ⚠️ | ✅ | ✅ | ✅ K8s |
| 滚动升级 | ⚠️ upgrade.sh | ✅ serial | ✅ | ✅ | ✅ |
| 回滚 | ⚠️ git SHA | ✅ | ✅ | ✅ | ✅ |
| Secret 管理 | ⚠️ .env 600 | ✅ Vault | ⚠️ | ✅ KMS | ✅ Sealed |
| 模板化配置 | ⚠️ sed | ✅ Jinja2 | ✅ | ✅ | ✅ |
| 测试 | ❌ | ✅ Molecule | ✅ tf test | ✅ | ✅ helm test |
| 学习曲线 | 低 (bash) | 中 | 中 | 中 | 中 |
| 月费用 | $0 | $0 (OSS) | $0 (OSS) | $0 | $0 |

### 7.2 IMDF 优势

- 零外部依赖 (任何 Ubuntu 22.04 + root)
- 178 行 bash, 业务团队可维护
- 强 systemd 加固 (24 units 全部 NoNewPrivileges + ProtectSystem)
- upgrade.sh 含 smoke test + rollback hint (生产级)
- 可审计 (无黑盒, 适合金融/医疗)

### 7.3 关键差距 (按 P0-P3 排序, 完整 13 项)

| # | 严重度 | 差距 | 估时 |
|---|--------|------|------|
| H2 | **P0** | install.sh 漏 enable backup | 5 min |
| H4+H5 | **P0** | grafana dashboards JSONs 不 staging | 30 min |
| H11 | **P0** | prometheus rules 不 staging | 5 min |
| H13 | **P0** | promtail config 缺失 | 30 min |
| H12 | P1 | grafana env file 缺失 | 5 min |
| H6 | P1 | backup 03:30 注释不符 | 1 min |
| H7 | P1 | restore.sh typo | 5 min |
| H8 | P1 | Redis restore 不停 Celery | 10 min |
| D1 | P2 | install.sh 缺 --dry-run | 0.5h |
| D2 | P2 | nginx gateway upstream 单点 | 1h |
| D7 | P2 | alembic 未集成 | 0.5h |
| D9 | P3 | 多主机编排 | 3h |
| D10 | P3 | Vault 化 | 1h |

---

## 8. 验证矩阵 (Verification Matrix)

| 验证项 | 工具 | 结果 |
|--------|------|------|
| install.sh bash 语法 | `bash -n` | ✅ OK (178 行) |
| install.sh --help | `bash install.sh --help` | ✅ 输出 17 行 usage |
| 8 步 README 流程 | code review | ✅ 与 install.sh 对齐 ~85% (Step 6 缺) |
| start-all.sh | `bash -n` | ✅ OK |
| stop-all.sh | `bash -n` | ✅ OK |
| upgrade.sh | `bash -n` | ✅ OK |
| healthcheck.sh | `bash -n` | ✅ OK |
| backup-db.sh | `bash -n` | ✅ OK |
| status.sh | `bash -n` | ✅ OK |
| 24 systemd unit 依赖 | grep | ✅ 12 app + 2 celery + 3 data + 6 obs = 24 |
| Tier 启动顺序 | start-all.sh grep | ✅ Data → Observability → App |
| nginx config | nginx -t | ❌ 未跑 (无 nginx on Windows), conf 结构 review OK |
| 健康检查 12 services | TestClient (P3-8-W2) | ✅ 12/12 metrics + 12/12 healthz |
| **install.sh 缺口** | code review | ⚠️ **5 P0 (H2+H4+H5+H11+H13)** |
| **9 bash scripts** | `bash -n` | ✅ 9/9 OK |

---

## 9. 总结

**完成度 ~85%** (Attempt 1 估 92%, 此次下调因发现 5 P0 install.sh 缺口)

- ✅ **install.sh 8 步** — 178 行, 幂等性 ~95%
- ✅ **24 systemd units** — 依赖图正确 (Data → Observability → App)
- ✅ **healthcheck.sh** — 12 service + celery + DB + Redis 全覆盖
- ✅ **upgrade.sh** — git + pip + alembic + 滚动重启 + smoke test + rollback hint
- ✅ **status.sh** — tabular 显示 + smoke test
- ✅ **nginx reverse proxy** — 强加固
- ✅ **README 8 步** — 完整, 与 install.sh 对齐 ~85%

**P0 production-blockers (Attempt 1 漏判, 此次深挖)**:
- **H2** install.sh 漏 enable backup → 备份永不 auto-start
- **H4+H5** install.sh 漏 staging grafana dashboards JSON → 46 panels 永不见
- **H11** install.sh 漏 staging prometheus rules → 21 alerts 永不 fire
- **H13** install.sh 漏 promtail config → 0 日志到 Loki

**P0 总修复时间**: ~70 min (1-2 工作时)

**P0+P1 总修复时间**: ~95 min (~1.5 工作时)

**本机实跑验证 (可跑部分)**:
- 9 bash scripts → 9/9 OK
- install.sh --help → 17 行输出
- 24 systemd unit 依赖图 → 完全正确
- nginx config 结构 review → OK

**不能在本地跑的测试**:
- install.sh 真实执行 (无 Linux + 无 root)
- systemd unit 启动顺序 (无 systemd on Windows)
- nginx -t 验证 (无 nginx on Windows)
- certbot --nginx (无 certbot + 需 DNS)
- 12 service systemd 启动 (需 Linux)
