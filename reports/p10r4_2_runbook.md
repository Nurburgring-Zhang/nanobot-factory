# P10R4-2: Runbook 运维手册 (23 systemd 单元 · 21 告警 · 3-tier 备份)

> **Date**: 2026-06-26 13:55 (Asia/Shanghai)
> **Author**: coder (P10R4-2 worker)
> **Sources**: `deploy/bare_metal/scripts/{start,stop,status,upgrade,healthcheck}.sh` + 23 systemd 单元 + `backup_cron.sh` + `restore.sh` + `docs/runbook.md`

---

## 1. 服务拓扑 (23 systemd units)

```
data (3)    : postgresql · redis-server · minio
obs  (6)    : prometheus · alertmanager · grafana-server · jaeger · loki · promtail
app  (12)   : imdf-gateway + imdf-{user,asset,annotation,cleaning,scoring,dataset,evaluation,
              agent,workflow,notification,search,collection}
async (2)   : imdf-celery · imdf-celery-beat
backup (2)  : imdf-backup.service · imdf-backup.timer  (systemd timer, 不在主链)
─────────────────────────────────────
TOTAL: 23 systemd units
```

---

## 2. 启动 / 停止 / 重启

### 2.1 一键启动 (按依赖顺序)

```bash
# 入口: deploy/bare_metal/scripts/start-all.sh
# 顺序: data (3) → observability (6) → application (12 + 2 celery)

sudo deploy/bare_metal/scripts/start-all.sh

# 输出:
#   ── Data layer (3 services) ──────────
#     ✔ postgresql.service already active
#     ✔ redis-server.service started
#     ✔ minio.service started
#   ── Observability (6 services) ──────
#     ✔ prometheus.service already active
#     ✔ alertmanager.service already active
#     ✔ grafana-server.service started
#     ✔ jaeger.service started
#     ✔ loki.service started
#     ✔ promtail.service started
#   ── Application (15 services) ───────
#     ✔ imdf-gateway.service started
#     ✔ imdf-user.service started
#     ✔ imdf-asset.service started
#     ... (12 svc)
#     ✔ imdf-celery.service started
#     ✔ imdf-celery-beat.service started
#   ── Smoke test ──────────────────────
#     ✔ gateway http://127.0.0.1:8000/api/queue/health
```

### 2.2 一键停止

```bash
sudo deploy/bare_metal/scripts/stop-all.sh
# 顺序: 逆依赖 (app → obs → data)
```

### 2.3 单服务重启

```bash
# 重启 gateway
sudo systemctl restart imdf-gateway
sudo journalctl -u imdf-gateway -f --no-pager  # 看日志

# 重启 celery worker (新代码 / 新配置)
sudo systemctl restart imdf-celery
sudo journalctl -u imdf-celery -f --no-pager

# 全部 app 滚动重启 (deploy 时)
sudo deploy/bare_metal/scripts/stop-all.sh
sudo deploy/bare_metal/scripts/start-all.sh
```

### 2.4 状态总览

```bash
sudo deploy/bare_metal/scripts/status.sh
# 输出 (tabular):
# UNIT                          STATE       ENABLED    UPTIME        MEM
# postgresql.service            active      enabled    5d 12h        420M
# redis-server.service          active      enabled    5d 12h        85M
# minio.service                 active      enabled    5d 12h        220M
# prometheus.service            active      enabled    5d 12h        180M
# alertmanager.service          active      enabled    5d 12h        35M
# grafana-server.service        active      enabled    5d 12h        145M
# jaeger.service                active      enabled    5d 12h        75M
# loki.service                  active      enabled    5d 12h        60M
# promtail.service              active      enabled    5d 12h        22M
# imdf-gateway.service          active      enabled    5d 12h        1.2G
# imdf-user.service             active      enabled    5d 12h        240M
# imdf-asset.service            active      enabled    5d 12h        320M
# imdf-annotation.service       active      enabled    5d 12h        280M
# imdf-cleaning.service         active      enabled    5d 12h        410M
# imdf-scoring.service          active      enabled    5d 12h        380M
# imdf-dataset.service          active      enabled    5d 12h        260M
# imdf-evaluation.service       active      enabled    5d 12h        290M
# imdf-agent.service            active      enabled    5d 12h        1.8G
# imdf-workflow.service         active      enabled    5d 12h        320M
# imdf-notification.service     active      enabled    5d 12h        180M
# imdf-search.service           active      enabled    5d 12h        420M
# imdf-collection.service       active      enabled    5d 12h        260M
# imdf-celery.service           active      enabled    5d 12h        2.4G
# imdf-celery-beat.service      active      enabled    5d 12h        85M
# 
# Total: 23 active, 0 failed, 0 inactive
```

---

## 3. 健康检查

### 3.1 一键健康检查 (推荐每分钟 cron)

```bash
# deploy/bare_metal/scripts/healthcheck.sh
sudo deploy/bare_metal/scripts/healthcheck.sh

# 输出:
# 2026-06-26T13:55:01+0800 OK  gateway status=ok
# 2026-06-26T13:55:01+0800 OK  readyz: {"status":"ok",...}
# 2026-06-26T13:55:01+0800 OK  metrics endpoint reachable
# 2026-06-26T13:55:03+0800 OK  service :8001 healthy
# 2026-06-26T13:55:03+0800 OK  service :8002 healthy
# 2026-06-26T13:55:03+0800 OK  service :8003 healthy
# 2026-06-26T13:55:03+0800 OK  service :8004 healthy
# ... (8005-8012)
# 2026-06-26T13:55:05+0800 OK  celery worker active
# 2026-06-26T13:55:05+0800 OK  celery beat active
# 2026-06-26T13:55:05+0800 END  OK
```

### 3.2 单点 curl 检查

```bash
# Gateway
curl -fsS http://127.0.0.1:8000/healthz | jq
curl -fsS http://127.0.0.1:8000/readyz | jq
curl -fsS http://127.0.0.1:8000/metrics | grep imdf_requests_total | head -5

# 12 svc /healthz
for port in 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010 8011 8012; do
  status=$(curl -fsS --max-time 2 http://127.0.0.1:${port}/healthz 2>/dev/null | jq -r .status 2>/dev/null)
  printf '  :%s  %s\n' "$port" "${status:-UNREACHABLE}"
done
```

### 3.3 Cron 配置

```bash
# /etc/cron.d/imdf-healthcheck
* * * * * root /opt/nanobot-factory/deploy/bare_metal/scripts/healthcheck.sh \
  || systemctl restart imdf-gateway
```

或 systemd timer (推荐):

```ini
# /etc/systemd/system/imdf-healthcheck.timer
[Unit]
Description=IMDF health check (1min interval)

[Timer]
OnCalendar=*:*:00
AccuracySec=5s
Persistent=true

[Install]
WantedBy=timers.target
```

---

## 4. 故障转移 (Failover)

### 4.1 PostgreSQL 主备切换

```bash
# 1) 确认 standby 滞后
sudo -u postgres psql -c "SELECT now() - pg_last_xact_replay_timestamp() AS lag;"
# 应该 < 1s

# 2) 提升 standby 为 primary
sudo -u postgres pg_ctl promote -D /var/lib/postgresql/15/main

# 3) 切换应用连接
sudo -u imdf bash -c "source /etc/imdf/imdf.env && \
  psql -h pg-standby -c 'SELECT pg_is_in_recovery();'"
# f = promoted (success)

# 4) 更新 DNS / 切换 .env DB_HOST
sudo sed -i 's/^DB_HOST=.*/DB_HOST=pg-standby.imdf.local/' /etc/imdf/imdf.env

# 5) 滚动重启应用
sudo deploy/bare_metal/scripts/stop-all.sh
sudo deploy/bare_metal/scripts/start-all.sh
```

**预期 RTO**: 5 min (含 4 步 + 重启)

### 4.2 Redis Sentinel 切换

```bash
# 1) 看 sentinel 状态
redis-cli -p 26379 sentinel masters
redis-cli -p 26379 sentinel get-master-addr-by-name mymaster

# 2) 强制 failover (sentinel 会自动, 但手工场景)
redis-cli -p 26379 sentinel failover mymaster

# 3) 客户端重连 (应用代码应自动重试)
```

### 4.3 MinIO 节点切换

```bash
# 1) mc admin info 看集群
mc admin info minio

# 2) mc admin heal 修复
mc admin heal --recursive minio/imdf-assets

# 3) mc mirror 切换到 secondary (DR 场景)
mc mirror --preserve --quiet minio-primary/imdf-assets/ minio-secondary/imdf-assets/
```

---

## 5. 数据恢复 (3-tier + restore.sh)

### 5.1 备份位置

```bash
# 查看所有备份
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh --list

# 输出:
# available backups in /var/backups/imdf:
#   db        30 files   12G       /var/backups/imdf/db
#   redis     30 files   850M      /var/backups/imdf/redis
#   oss       4 files    45G       /var/backups/imdf/oss
#   warm      12 files   35G       /var/backups/imdf/warm
#   cold      52 files   180G      /var/backups/imdf/cold
#
# Recent (last 10):
# 2026-06-26+03:00:01   1245678901  /var/backups/imdf/db/imdf-20260626-030000.sql.gz
# 2026-06-26+03:30:01    245678901  /var/backups/imdf/redis/dump-20260626-033000.rdb.gz
# 2026-06-25+03:00:01   1234567890  /var/backups/imdf/db/imdf-20260625-030000.sql.gz
# ... (7 more)
```

### 5.2 验证完整性 (无副作用)

```bash
# 验证最新 PG dump
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
  --component pg --latest --verify
# 输出:
# [restore] verify: /var/backups/imdf/db/imdf-20260626-030000.sql.gz
# [restore]   PG dump OK (1.2G)

# 验证最新 Redis RDB
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
  --component redis --latest --verify
# 输出:
# [restore]   Redis RDB OK (85M)

# 验证最新 OSS tarball
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
  --component oss --latest --verify
# 输出:
# [restore]   OSS tarball OK (12G)
```

### 5.3 恢复到新 DB (推荐: 不覆盖生产)

```bash
# PG 恢复到 imdf_restored_<timestamp>
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
  --component pg --latest --target imdf_restored_$(date +%s)
# 确认: 输入 YES
# 输出:
# [restore] creating target DB: imdf_restored_1719225600
# [restore] gunzip + psql pipe → imdf_restored_1719225600
# [restore] PG restore OK → imdf_restored_1719225600
# [restore] switch over:
#   sudo -u imdf bash -c 'psql -c "ALTER DATABASE imdf RENAME TO imdf_old; ALTER DATABASE imdf_restored_1719225600 RENAME TO imdf;"'

# 验证数据
sudo -u imdf bash -c "psql -d imdf_restored_1719225600 -c '\dt'"
# 应该看到完整 schema

# 切换 (5 秒内完成)
sudo -u imdf bash -c "psql -c 'ALTER DATABASE imdf RENAME TO imdf_old; ALTER DATABASE imdf_restored_1719225600 RENAME TO imdf;'"

# 应用自动重连
sudo deploy/bare_metal/scripts/healthcheck.sh
```

### 5.4 Redis 恢复

```bash
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
  --component redis --file /var/backups/imdf/redis/dump-20260624-030000.rdb.gz
# 确认: 输入 YES
# 输出:
# [restore] stopping redis-server to replace RDB
# [restore] starting redis-server; verify with redis-cli ping
# PONG
# [restore] Redis restore OK
```

### 5.5 OSS 恢复

```bash
sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
  --component oss --latest
# 确认: 输入 YES
# 输出:
# [restore] extracting to /tmp/imdf-oss-restore.xxxxxx
# [restore] OSS restore OK
```

### 5.6 灾难恢复 checklist

- [ ] 周日: `restore.sh --list` 确认备份存在
- [ ] 周日: `restore.sh --verify` 自动 sample-restore (通过 backup_cron.sh 自动化)
- [ ] 季度: 异地 restore (copy `/var/backups/imdf/cold/` 到另一个 DC + 跑 restore.sh)
- [ ] 季度: 验证 cold tier 复制到异地 (`mc mirror` to remote bucket)
- [ ] 配置: `postgresql.conf` 启用 WAL 归档 (PITR)
- [ ] 文档: RTO < 1h · RPO < 24h 在 oncall runbook

---

## 6. 扩容 (Scaling)

### 6.1 加 Worker 节点 (Celery)

```bash
# 节点 2 配置:
# 1) 同步代码 + venv
rsync -avz /opt/nanobot-factory/ worker02:/opt/nanobot-factory/
rsync -avz /etc/imdf/imdf.env worker02:/etc/imdf/imdf.env
ssh worker02 "cd /opt/nanobot-factory && venv/bin/pip install -r backend/requirements.txt"

# 2) 启动 celery (worker-02 hostname)
ssh worker02 "sudo -u imdf bash -c 'cd /opt/nanobot-factory && \
  source /etc/imdf/imdf.env && \
  venv/bin/celery -A backend.imdf.celery_app:celery_app worker \
    --loglevel=info --concurrency=8 \
    --queues=default,video,cpu,index,network \
    --hostname=imdf-celery@worker-02 \
    --max-tasks-per-child=200 -O fair' &"

# 3) 验证 (flower 或 IMDF /api/queue/stats)
curl http://127.0.0.1:8000/api/queue/stats | jq
# 应该看到 2 个 active worker
```

### 6.2 加 App 节点 (Gateway)

```bash
# 节点 2 配置:
# 1) 同步 + 启动 imdf-gateway (步骤同上)
ssh app02 "sudo systemctl start imdf-gateway"

# 2) nginx upstream 加新节点
upstream imdf_gateway {
    server 10.0.1.10:8000;   # 节点 1
    server 10.0.1.11:8000;   # 节点 2
    keepalive 64;
}
sudo nginx -t && sudo nginx -s reload

# 3) 验证 (curl /healthz 应返回两节点的混合)
for i in 1 2 3 4 5; do
  curl -fsS http://imdf.example.com/healthz | jq -r '.uptime_seconds'
done
```

### 6.3 DB 升级 (P9-5 P0 路径: SQLite → PostgreSQL)

详见 `reports/p9_5_database.md` (Pg 迁移 1-2 人天)。

---

## 7. 告警处理 (21 规则 oncall playbook)

### 7.1 P0 Critical (立即响应)

#### `ImdfServiceHighErrorRate` (5xx > 5% 持续 5min)

```yaml
label: severity=critical, category=service
影响: 用户大面积 5xx
响应: < 5 min

playbook:
  1. 看 Grafana: dashboard-vdp-business → 12 svc panel
     - 哪个 svc 错误率最高?
  2. 看日志: journalctl -u imdf-<svc> -n 200 --no-pager
     - 常见: DB 连接超时 / OOM / 业务异常
  3. 看 Prometheus: imdf_request_latency_seconds_bucket
     - P99 延迟是否飙升?
  4. 决策:
     a) 单 svc 问题: systemctl restart imdf-<svc>
     b) DB 问题:    看 postgresql.log, 切换主备
     c) 配置错误:   git revert, 触发 upgrade.sh
     d) 流量峰值:   启用 rate-limit fallback
  5. 跟踪: /healthz + /readyz 转绿 → 发布 status page
```

#### `ImdfGatewayDown` (gateway 不可达)

```yaml
响应: < 2 min (用户全部不可用)

playbook:
  1. 立即看: systemctl status imdf-gateway
  2. 常见根因:
     a) OOM (4G 上限)
        → systemctl edit imdf-gateway (MemoryMax=8G)
        → systemctl daemon-reload && systemctl restart imdf-gateway
     b) 端口占用
        → lsof -i :8000 → kill -9 <pid>
     c) DB 不可达 (启动阻塞)
        → systemctl status postgresql
        → systemctl start postgresql
     d) 配置错误 (Pydantic ValidationError)
        → journalctl -u imdf-gateway | grep ValidationError
        → 修复 .env → restart
  3. 启动后: curl http://127.0.0.1:8000/healthz → 200
```

#### `PostgresConnectionsHigh` (连接池 > 80%)

```yaml
响应: < 15 min

playbook:
  1. 看 PG: SELECT count(*) FROM pg_stat_activity;
  2. 看哪个 svc 占连接:
     SELECT application_name, count(*) FROM pg_stat_activity
     GROUP BY application_name ORDER BY 2 DESC;
  3. 决策:
     a) 单 svc 泄露: 重启 imdf-<svc>
     b) 全局过高: 增加 max_connections (postgresql.conf)
        + 加 pgbouncer
     c) 长事务: SELECT * FROM pg_stat_activity
        WHERE state='active' AND now()-xact_start > interval '1 min';
```

#### `RedisDown`

```yaml
响应: < 5 min

playbook:
  1. systemctl status redis-server
  2. 常见:
     a) OOM kill → 检查 vm.overcommit_memory
        sysctl -w vm.overcommit_memory=1
     b) RDB 失败 → /var/log/redis/redis-server.log
        看 "Can't save in background"
     c) AOF rewrite 失败 → 关 AOF 或修复 disk
  3. 启动: systemctl start redis-server
  4. 验证: redis-cli ping → PONG
```

### 7.2 P1 Warning (15 min 响应)

#### `ImdfServiceHighLatency` (P99 > 2s 持续 10min)

```yaml
playbook:
  1. 看 Grafana dashboard-vdp-business → latency panel
  2. 找慢的端点 (P95 > 500ms)
  3. 常见根因:
     a) DB 慢查询: 看 pg_stat_statements.top by mean_time
     b) 同步阻塞: 看 imdf_request_duration_seconds
     c) 外部依赖慢: jaeger trace 看 span
  4. 缓解:
     - 临时: 启用缓存 (LRU TTL 调大)
     - 长期: 优化 SQL / 加索引 / 升级 worker 池
```

#### `CeleryQueueBacklog` (队列堆积 > 1000 持续 10min)

```yaml
playbook:
  1. 看 /api/queue/stats 看哪个 queue 堆积
  2. 决策:
     a) 加 worker: scale-out (见 §6.1)
     b) 任务超时: 检查 task time_limit (600s)
     c) 任务卡死: 看 celery worker 日志
  3. 紧急: 清空 DLQ (慎用)
     celery purge -Q default -A backend.imdf.celery_app
```

#### `PipelineFailureRateHigh` (流水线失败 > 10%)

```yaml
playbook:
  1. 看 Grafana dashboard-vdp-ai → pipeline panel
  2. 哪个 stage 失败率高?
  3. 看 BadCase 列表:
     GET /api/v1/evaluation/badcase?since=1h
  4. 决策:
     a) 模型问题: 切换 fallback provider
     b) 数据问题: 重新清洗 + 重新评分
     c) 资源问题: 扩容 worker
```

#### `TicketSLABreach` (工单 SLA 突破 > 5)

```yaml
playbook:
  1. GET /api/v1/tickets/sla-breach
  2. 通知 on-call 分配人
  3. 紧急客户优先: P0 / P1 立即响应
  4. 升级路径: 通知 manager (24h 内未响应)
```

### 7.3 P2 Info (1h 响应)

#### `LoginFailureBurst` (登录失败 > 100/min 持续 5min)

```yaml
playbook:
  1. 看 IP 来源: Loki logs → filter by status=401
  2. 决策:
     a) 单 IP 暴力破解: nginx 临时 deny
        sudo iptables -I INPUT -s <ip> -j DROP
     b) 分布式爆破: 启用 fail2ban + 调整 rate-limit
     c) 凭据泄露: 强制受影响用户 reset-password
```

#### `AuditChainBroken` (审计链 hash 不连续)

```yaml
playbook (P10R4-1 已加严):
  1. 看 audit_chain 表最后 10 行:
     SELECT * FROM audit_chain ORDER BY id DESC LIMIT 10;
  2. 找断点 (prev_hash != 上行 hash)
  3. 决策:
     a) 应用 bug: 回滚代码 (upgrade.sh)
     b) DB 损坏: 切主备 + 恢复
     c) 安全事件: 立即告警安全团队 + 冻结 audit_chain 写入
```

#### `RateLimitTriggered` (429 占比 > 20%)

```yaml
playbook:
  1. 看哪个 IP / tenant 触发:
     Loki logs → filter by status=429
  2. 决策:
     a) 单 client bug: 通知 client + 临时 deny
     b) 攻击: 启用 Cloudflare / nginx 限速
     c) 正常流量: 提升 tier limit
```

### 7.4 告警通知路径

```yaml
# Alertmanager 路由
critical: Slack #imdf-oncall + PagerDuty (24/7) + 飞书机器人
warning:  Slack #imdf-oncall
info:     Slack #imdf-ops (每日 digest)
```

---

## 8. 升级流程 (deploy/bare_metal/scripts/upgrade.sh)

```bash
# 1) 升级到 HEAD (main 分支最新)
sudo deploy/bare_metal/scripts/upgrade.sh

# 2) 升级到指定 tag
sudo deploy/bare_metal/scripts/upgrade.sh v1.7.0

# 3) 跳过 git pull (本地修改)
sudo deploy/bare_metal/scripts/upgrade.sh --no-pull

# 4) 跳过 pip install (仅 alembic + restart)
sudo deploy/bare_metal/scripts/upgrade.sh --no-deps
```

**升级步骤 (内部)**:
1. pre-flight (git 仓库? venv 存在?)
2. 记录当前 SHA (rollback 准备)
3. git pull + checkout
4. pip install (生产依赖)
5. frontend build (如变更)
6. alembic upgrade head (DB 迁移)
7. 滚动重启 12 svc
8. 健康检查
9. 失败自动回滚 (记录 old/new SHA)

**日志位置**: `/opt/nanobot-factory/logs/upgrade-YYYYMMDD-HHMMSS.log`

---

## 9. 常见运维 SOP

### 9.1 清空 Redis 缓存 (谨慎)

```bash
# 1) 备份当前 RDB
sudo redis-cli BGSAVE
# 2) 等待 save 完成
sudo redis-cli LASTSAVE
# 3) 备份到 imdf-backup
sudo cp /var/lib/redis/dump.rdb /var/backups/imdf/redis/manual-clear-$(date +%s).rdb
# 4) FLUSHDB (仅当前 DB)
sudo redis-cli FLUSHDB
# 5) 验证
sudo redis-cli DBSIZE
```

### 9.2 重置 minio bucket (谨慎)

```bash
# 1) 备份当前 bucket
mc mirror --preserve minio/imdf-assets /var/backups/imdf/oss/manual-reset-$(date +%s)/
# 2) 清空
mc rm --recursive --force minio/imdf-assets
# 3) 重建
mc mb --ignore-existing minio/imdf-assets
```

### 9.3 查慢 SQL

```sql
-- PG top 20 by mean_time
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 20;

-- 当前长事务
SELECT pid, usename, application_name,
       now() - xact_start AS duration, query
FROM pg_stat_activity
WHERE state='active' AND xact_start IS NOT NULL
ORDER BY duration DESC;
```

### 9.4 查看 Celery 任务

```bash
# 当前活跃任务
sudo -u imdf bash -c "celery -A backend.imdf.celery_app:celery_app inspect active"

# 队列长度
sudo -u imdf bash -c "celery -A backend.imdf.celery_app:celery_app inspect reserved"

# worker 统计
sudo -u imdf bash -c "celery -A backend.imdf.celery_app:celery_app inspect stats"
```

### 9.5 看 WS 连接

```bash
# Gateway 的 WS 连接数 (在 /metrics)
curl http://127.0.0.1:8000/metrics | grep websocket
```

---

## 10. 参考文档

- `deploy/bare_metal/scripts/start-all.sh` (84 行)
- `deploy/bare_metal/scripts/stop-all.sh`
- `deploy/bare_metal/scripts/status.sh` (60+ 行)
- `deploy/bare_metal/scripts/healthcheck.sh` (74 行)
- `deploy/bare_metal/scripts/upgrade.sh` (180+ 行)
- `deploy/bare_metal/backup_cron.sh` (286 行)
- `deploy/bare_metal/restore.sh` (267 行)
- `monitoring/prometheus-rules.yaml` (21 alert rules)
- `monitoring/alertmanager.yaml` (Slack + PagerDuty 路由)
- `docs/runbook.md` (11KB, 6 故障 SOP)

