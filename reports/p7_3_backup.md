# P7-3 备份深度审查报告 (Backup Deep Review v2 — Attempt 2)

**Date**: 2026-06-26 04:25
**Project**: nanobot-factory (智影 / ZhiYing)
**Scope**: 备份系统 — backup_cron.sh + restore.sh + systemd timer + 3-tier 保留
**Reviewer**: coder (P7-3 second-pass, attempt 2)
**Status**: 2 P0 production-blockers + 3 P1 + 5 P2/P3

---

## 1. ⚠️ P0 Production-Blockers (Attempt 1 漏判, 此次深挖发现)

### 1.1 H1: backup_cron.timer 引用不存在的 service [P0, 5 min]

**证据** (3 处冲突):

1. `deploy/bare_metal/backup_cron.timer` (line 4, 17):
   ```ini
   [Unit]
   Requires=imdf-backup.service     # ← 引用 imdf-backup
   ...
   [Timer]
   Unit=imdf-backup.service         # ← 引用 imdf-backup
   ```

2. `deploy/bare_metal/backup_cron.service` (file name):
   ```
   backup_cron.service  (实际文件名)
   ```

3. `README.md` § 7.2 (line 272, 280) 引用:
   ```bash
   sudo systemctl enable --now imdf-backup.timer    # ← README 也用 imdf-backup
   sudo systemctl start imdf-backup.service         # ← README 也用 imdf-backup
   ```

**生产影响**:
- 用户按 README 执行 → `systemctl enable imdf-backup.timer` 失败 (文件不存在)
- 即使绕过 README, 直接复制 backup_cron.timer 到 /etc/systemd/system/, timer 触发时尝试启动 `imdf-backup.service` (Unit= 指令) — 找不到该 service
- **备份 永远 不会 自动执行** (除非用户手动 `systemctl start backup_cron.service`)

**修复** (二选一):
- A. timer 文件的 `Unit=` 和 `Requires=` 改成 `backup_cron.service` + README 同步 (2 min)
- B. 把 service/timer 文件改名为 `imdf-backup.service`/`imdf-backup.timer` (5 min, 涉及 install.sh 多个 cp 命令)

**推荐 A**: 最小破坏性.

### 1.2 H2: install.sh enable list 漏 backup [P0, 5 min]

**证据**: `deploy/bare_metal/install.sh` step 8 (line 162-168):
```bash
for svc in postgresql redis-server minio \
           prometheus grafana-server alertmanager \
           jaeger loki promtail \
           imdf-gateway imdf-user imdf-asset imdf-annotation imdf-cleaning \
           imdf-scoring imdf-dataset imdf-evaluation imdf-agent \
           imdf-workflow imdf-notification imdf-search imdf-collection \
           imdf-celery imdf-celery-beat; do
  systemctl enable "${svc}.service" 2>/dev/null || true
done
```

**漏掉**: `backup_cron.service` 和 `backup_cron.timer` 完全没在 list 里!

**生产影响**:
- 即使 H1 修复, install.sh 跑完也不 enable backup
- 用户必须手动 `systemctl enable --now backup_cron.timer` 才能启动自动备份
- README § 7.2 提到 enable, 但**没在 install.sh 主流程里**

**修复**:
```bash
# 在 install.sh step 8 加 (line 168 后):
log "enabling backup timer"
systemctl enable backup_cron.timer 2>/dev/null || true

# 同时, README § 7.2 应说明此步骤由 install.sh 自动完成
```

### 1.3 综合: H1 + H2 = 备份永远不跑

**双重 fail**: 即使修一个, 另一个还在 → 必须**同时修**.

**总 P0 修复时间**: ~10 min (双修)

---

## 2. 总体盘点 (Backup Stack Inventory)

| 组件 | 路径 | 行数 | 状态 |
|------|------|------|------|
| Backup orchestrator | `deploy/bare_metal/backup_cron.sh` | 286 | bash -n OK |
| Backup service unit | `deploy/bare_metal/backup_cron.service` | 38 | OK (Type=oneshot) |
| **Backup timer** | `deploy/bare_metal/backup_cron.timer` | 20 | **H1: Unit name 错** |
| Restore helper | `deploy/bare_metal/restore.sh` | 267 | bash -n OK + --help/--list 实跑 |
| Legacy DB backup | `deploy/bare_metal/scripts/backup-db.sh` | — | bash -n OK |
| README § 7 | `deploy/bare_metal/README.md` (251-355) | 105 行 | 完整运行手册 |

---

## 3. backup_cron.sh 真实跑 (静态演练)

### 3.1 8 大子函数

| # | 函数 | 行号 | 功能 | 验证 |
|---|------|------|------|------|
| F1 | `acquire_lock` | 43-56 | LOCKFILE 互斥 (PID 检测 + 清理 stale lock) | ✅ 静态分析 |
| F2 | `load_env` | 58-67 | `set -a; . ${ENV_FILE}; set +a` | ✅ 静态分析 |
| F3 | `notify` | 70-81 | Slack webhook (5s timeout, fail-soft) | ✅ 静态分析 |
| F4 | `backup_pg` | 84-109 | `pg_dump \| gzip` + gzip integrity check | ⚠️ 需 PG |
| F5 | `backup_redis` | 112-145 | `BGSAVE` 等待 10s, fallback `redis-cli --rdb` | ⚠️ 需 Redis |
| F6 | `backup_oss` | 148-190 | `mc mirror` 优先, `rclone copy` 备选 | ⚠️ 需 MinIO |
| F7 | `migrate_tiers` | 193-216 | hot → warm → cold, cold prune | ✅ 逻辑正确 |
| F8 | `verify_sample` | 219-258 | 周日才跑: PG header check + Redis REDIS magic | ✅ 静态分析 |

### 3.2 入口逻辑 (Main)

```
acquire_lock                    # 1) 锁
load_env                        # 2) 加载 ENV
case "${BACKUP_TARGETS}" in     # 3) 选目标
  pg|all)  backup_pg ;;
  redis)   backup_redis ;;
  oss)     backup_oss ;;
esac
if [[ "all" ]]; then            # 4) 仅全量跑
  migrate_tiers
  verify_sample
fi
notify "OK"|"FAIL"              # 5) Slack
```

### 3.3 配置项 (8 env vars, H14 缺)

> **H14 (P2)**: `.env.example` 缺以下变量. backup_cron.sh 有 `:-` 默认值, 不致命, 但应同步.

| 变量 | 默认 | .env.example 有? |
|------|------|------------------|
| `ENV_FILE` | `/etc/imdf/imdf.env` | ❌ 无 |
| `BACKUP_ROOT` | `/var/backups/imdf` | ❌ 无 |
| `LOG_DIR` | `/var/log/imdf-backup` | ❌ 无 |
| `HOT_TIER_DAYS` | 7 | ❌ 无 |
| `WARM_TIER_DAYS` | 30 | ❌ 无 |
| `COLD_TIER_DAYS` | 365 | ❌ 无 |
| `JOB_TAG` | `manual` | ❌ 无 |
| `BACKUP_NOTIFY_WEBHOOK` | (空) | ❌ 无 (但有 SLACK_WEBHOOK_URL) |

**H14 修复**: .env.example 加 `# ── Backup ──` section + 7 个变量.

### 3.4 3 种触发方式

1. **systemd timer 自动** (默认 03:00 + Sun 04:00, 见 H6)
2. **手动单组件**: `BACKUP_TARGETS=pg sudo ./backup_cron.sh`
3. **手动全量**: `sudo systemctl start backup_cron.service`

---

## 4. restore.sh 真实演练

> **本机可跑**: `--help`, `--list`. **不可跑**: `--component pg/redis/oss` (需 PG/Redis/MinIO).

### 4.1 --help 实测 ✅

```bash
$ bash deploy/bare_metal/restore.sh --help
[usage 块 18 行]
  Usage:
    restore.sh --component pg|redis|oss --file <path> [--to <restore-target>]
    restore.sh --component pg --latest
    restore.sh --component pg --date 2026-06-23
    restore.sh --list
    restore.sh --verify
  ...
```

> **代码质量**: `--help` 用 awk 从 shebang 后 contiguous 注释块解析 (line 39-46). 优雅实现, 避免泄露 section header.

### 4.2 --list 实测 ✅ (空目录)

```bash
$ bash deploy/bare_metal/restore.sh --list
[restore] 2026-06-25T19:33:30Z available backups in /var/backups/imdf:

Recent (last 10):
```

> 优雅降级: `[[ -d "${dir}" ]] || continue` (line 81) — 不会 crash.

### 4.3 --verify 逻辑 (3 种文件类型)

| 文件模式 | 校验 | 失败 |
|----------|------|------|
| `*.sql.gz` | `gzip -t` + `head -50 \| grep "PostgreSQL database dump"` | exit 1 |
| `*.rdb.gz` | `gzip -t` + `head -c 5 \| grep "REDIS"` (RDB magic) | exit 1 |
| `*.tar.gz` | `tar -tzf >/dev/null` | exit 1 |

### 4.4 3 种 restore 流程

#### PG restore (line 161-175)
1. 加载 env
2. 创建新 DB: `imdf_restored_$(date +%Y%m%d-%H%M%S)` — **永远不覆盖原 imdf**
3. `gunzip -c | psql -v ON_ERROR_STOP=1` 灌入
4. 提示用户手动 `ALTER DATABASE ... RENAME TO imdf` (避免破坏 prod)

#### Redis restore (line 178-191)
1. `systemctl stop redis-server`
2. 备份当前 RDB `dump.rdb.bak-$(date +...)`
3. `gunzip -c ${FILE} > /var/lib/redis/dump.rdb`
4. `systemctl start redis-server`
5. `redis-cli ping` 验证

#### OSS restore (line 194-217)
1. 解压 tarball 到临时目录
2. 用 `mc mirror --preserve` 反向同步到 MinIO bucket
3. 缺 `mc` 命令时提示手动 tar -xzf

### 4.5 安全保护

- `set -euo pipefail` (line 21) — 任何子命令失败立即 abort
- `confirm()` 必须输入 `YES` (除非 `--yes` 标志) — line 150-158
- `--list` / `--verify` 永远非破坏性

### 4.6 H7: restore.sh usage typo [P1, 5 min]

- usage 块 line 6: `--to <restore-target>`
- code line 56: `--target)     TARGET_DB="$2"`
- **拼写不一致** — usage 写 `--to`, code 实际是 `--target`

**修复**: usage 改成 `--target`.

### 4.7 H8: Redis restore 期间 Celery 仍可写 [P1, 10 min]

**证据**: restore.sh line 181: `systemctl stop redis-server` — 只停 Redis
**问题**: imdf-celery 还在跑, 仍可写 Celery result backend (Redis db 1/2)
**风险**: restore 期间新 task 的 result 丢失

**修复**:
```bash
# line 181 加:
systemctl stop imdf-celery imdf-celery-beat
systemctl stop redis-server
# ... 恢复 ...
systemctl start redis-server
systemctl start imdf-celery imdf-celery-beat
```

---

## 5. systemd timer 实际触发

### 5.1 3 个调度 (backup_cron.timer)

| # | OnCalendar | 含义 | 实际触发 |
|---|------------|------|----------|
| 1 | `*-*-* 03:00:00` | 每天 03:00 (PG + Redis 全量) | backup_cron.sh 启动, BACKUP_TARGETS=all |
| 2 | `Sun *-*-* 04:00:00` | 周日 04:00 (OSS) | 同上, verify_sample 触发 |
| 3 | (注释说 03:30 Redis) | (实际无) | **H6: 注释与实现不一致** |

### 5.2 H6: 03:30 Redis 调度不存在 [P1, 5 min]

**证据**:
- `backup_cron.sh` line 4 注释: `#   - 03:30  Redis RDB       (hot  7d)`
- `backup_cron.timer` 只有 2 条 OnCalendar (03:00 + Sun 04:00), 无 03:30

**实际行为**: `BACKUP_TARGETS=all` 在 03:00 一把抓, 含 PG + Redis + OSS. 03:30 注释**误导**.

**修复** (二选一):
- A. 加第 3 条 OnCalendar: `OnCalendar=*-*-* 03:30:00` + 新 service 只跑 Redis (15 min)
- B. 删 03:30 注释 (1 min, 简单)

**推荐 B**: 当前"一把抓"已覆盖, 加分离 timer 复杂化且非必要.

### 5.3 鲁棒性配置

| 配置 | 值 | 作用 |
|------|-----|------|
| `Persistent=true` | true | 重启后补跑 |
| `RandomizedDelaySec=15min` | 15min | 避免雷暴 |
| `AccuracySec=1min` | 1min | 精度 |
| `OnBootSec=` | (缺) | 启动后多久跑 (未配) |

### 5.4 backup_cron.service 安全加固

| 字段 | 值 |
|------|-----|
| User / Group | imdf / imdf |
| Requires | postgresql.service redis-server.service minio.service |
| After | 同上 + network-online.target |
| Type | oneshot (跑完即退出) |
| TimeoutStartSec | 4h (OSS 大桶) |
| MemoryMax | 2G |
| Nice | 10 |
| IOSchedulingClass | best-effort / Priority 7 |
| PrivateTmp / ProtectSystem / ProtectHome / NoNewPrivileges | ✅ 全部加固 |
| SyslogIdentifier | imdf-backup |

> **生产级加固** ✅

---

## 6. 3-tier 7/30/365 天保留验证

### 6.1 目录结构

```
/var/backups/imdf/
├── db/          # hot: 7 days
├── redis/       # hot: 7 days
├── oss/         # hot: 7 days
├── warm/        # warm: 30 days
└── cold/        # cold: 365 days
```

### 6.2 迁移逻辑 (`migrate_tiers` 函数)

```bash
# 1) hot → warm (mtime > 7d)
find ${BACKUP_ROOT}/{db,redis,oss} -type f -mtime +7 -name '*.gz' \
  | while read f; do
    mv "$f" "${BACKUP_ROOT}/warm/${f#${BACKUP_ROOT}/}"
  done

# 2) warm → cold (mtime > 30d)
find ${BACKUP_ROOT}/warm -type f -mtime +30 \
  | while read f; do
    mv "$f" "${BACKUP_ROOT}/cold/${f#${BACKUP_ROOT}/warm/}"
  done

# 3) cold prune (mtime > 365d)
find ${BACKUP_ROOT}/cold -type f -mtime +365 -delete
```

### 6.3 RTO / RPO 目标

| 层级 | 保留 | 恢复 RPO | 恢复 RTO | 适用场景 |
|------|------|----------|----------|----------|
| hot | 7d | ≤ 24h | ≤ 1h | 日常回滚 |
| warm | 30d | ≤ 7d | ≤ 2h | 近期误操作 |
| cold | 365d | ≤ 365d | ≤ 4h (异地) | 合规 / 取证 |

---

## 7. ⚠️ 关键问题总表 (Attempt 2 综合)

### P0 (1-2 周内修, production-blocking)

| # | 问题 | 修复 | 估时 |
|---|------|------|------|
| **H1** | backup_cron.timer `Unit=imdf-backup.service` 引用不存在的 service | timer 改 `Unit=backup_cron.service` + README 同步 | 5 min |
| **H2** | install.sh step 8 enable list 漏 `backup_cron.timer`/`.service` | install.sh 加 enable 命令 | 5 min |

### P1 (1 月内修)

| # | 问题 | 修复 | 估时 |
|---|------|------|------|
| H6 | backup_cron.sh 注释说 03:30 Redis, timer 实际无 | 删注释 或 加 OnCalendar | 1 min |
| H7 | restore.sh usage `--to` vs code `--target` 拼写不一致 | usage 改 `--target` | 5 min |
| H8 | Redis restore 期间 Celery 仍可写 | restore.sh 停 celery/beat | 10 min |

### P2 (季度内)

| # | 问题 | 修复 | 估时 |
|---|------|------|------|
| B1 | 跨 Region 复制 (README 写但无 cron) | 加 rsync timer | 1h |
| B3 | OSS 大桶全量 mirror 慢 | rclone 增量 `--max-age 24h` | 0.5h |
| B4 | 备份无加密静态 | gpg / age 加密 | 0.5h |
| B5 | 缺集中管理 UI | Restic UI / 自建 FastAPI | 2h |
| B6 | restore.sh 无 dry-run | 加 `--dry-run` 走 verify_only | 0.25h |
| H14 | .env.example 缺 backup 相关 7 个 env var | 补全 | 5 min |

### P3 (长期)

| # | 问题 | 修复 | 估时 |
|---|------|------|------|
| B2 | WAL archive 已配 (撤回) | — | — |

> **⚠️ 重要撤回**: Attempt 1 报告 B2 标 "WAL archive 未配, PITR 不可用". 
> **正确**: `configs/postgresql.conf` line 34-35 **已配** `archive_mode=on` + `archive_command='cp %p /var/backups/imdf/wal/%f'`. Attempt 1 漏看, **撤回此 gap**.

### 已 PASS 验证项 (撤销的 attempt 1 错误)

- ❌ B2 (WAL archive) → ✅ 已配, 撤回
- ❌ M4 (Loki retention 168h 偏短) → bare_metal 是 30d, 撤回

---

## 8. 备份系统对标世界级 (Velero / Kasten / Portworx / Veeam)

### 8.1 能力矩阵

| 能力 | IMDF | Velero | Kasten K10 | Portworx | Veeam |
|------|------|--------|------------|----------|-------|
| PG 备份 | ✅ pg_dump | ❌ | ✅ | ❌ | ✅ |
| Redis 备份 | ✅ BGSAVE | ❌ | ✅ | ❌ | ✅ |
| OSS 备份 | ✅ mc mirror | ✅ | ✅ | ✅ | ✅ |
| 3-tier 保留 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 应用一致性 | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| 跨 Region 复制 | ❌ (B1) | ✅ | ✅ | ✅ | ✅ |
| 增量备份 | ⚠️ (B3) | ✅ | ✅ | ✅ | ✅ |
| PITR (WAL) | ✅ (已配, 撤回 B2) | ❌ | ✅ | ❌ | ✅ |
| 加密静态 | ❌ (B4) | ✅ AES | ✅ | ✅ | ✅ |
| 备份验证 (自动) | ✅ 周日 | ✅ | ✅ | ✅ | ✅ SureBackup |
| 集中 UI | ❌ (B5) | ✅ | ✅ | ✅ | ✅ |
| 商业 License | $0 | $0 | $30K/yr | $50K/yr | $1K/yr/host |

### 8.2 IMDF 优势

- 零外部依赖 (system tools + bash)
- 286 行可读, 业务可维护
- 非阻塞备份 (PG plain + Redis BGSAVE)
- 强校验 (gzip + magic)
- PITR 已配 (postgresql.conf archive_mode=on, 撤回 B2)

### 8.3 关键差距 (按 P0-P3 排序)

| # | 严重度 | 差距 | 估时 |
|---|--------|------|------|
| H1 | **P0** | timer Unit name mismatch | 5 min |
| H2 | **P0** | install.sh 漏 enable backup | 5 min |
| H6 | P1 | 03:30 Redis 注释 vs 实现不符 | 1 min |
| H7 | P1 | restore.sh usage typo | 5 min |
| H8 | P1 | Redis restore 不停 Celery | 10 min |
| H14 | P2 | .env.example 缺 backup env | 5 min |
| B1 | P2 | 跨 Region 复制 | 1h |
| B3 | P2 | OSS 增量备份 | 0.5h |
| B4 | P2 | 加密静态 | 0.5h |
| B5 | P3 | 集中 UI | 2h |
| B6 | P3 | restore --dry-run | 0.25h |

---

## 9. 验证矩阵 (Verification Matrix)

| 验证项 | 工具 | 结果 |
|--------|------|------|
| backup_cron.sh bash 语法 | `bash -n` | ✅ OK (286 行) |
| restore.sh bash 语法 | `bash -n` | ✅ OK (267 行) |
| backup-db.sh bash 语法 | `bash -n` | ✅ OK |
| backup_cron.timer 解析 | `systemd-analyze verify` | ❌ 未跑 (无 systemd on Windows) |
| backup_cron.service 解析 | `systemd-analyze verify` | ❌ 未跑 |
| restore.sh --help | `bash restore.sh --help` | ✅ 输出 18 行 usage |
| restore.sh --list | `bash restore.sh --list` | ✅ 空目录优雅降级 |
| restore.sh --component pg | 需 PG | ❌ 未跑 |
| migrate_tiers 逻辑 | 代码 review | ✅ find + mv 模式正确 |
| verify_sample 逻辑 | 代码 review | ✅ 周日条件 + 双重校验 |
| lock 互斥 | 代码 review | ✅ PID kill -0 检测 |
| postgresql.conf WAL archive | code review | ✅ archive_mode=on, archive_command 配置 |
| 全部 9 bash scripts | `bash -n` | ✅ 9/9 OK |

---

## 10. 总结

**完成度 ~85%** (Attempt 1 估 88%, 此次下调因发现 2 P0 production-blockers)

- ✅ **3-tier 保留策略** (hot 7d / warm 30d / cold 365d) — 实装正确
- ✅ **PG + Redis + OSS 3-tier 备份** — 全实装 (bash -n OK)
- ✅ **restore.sh 全功能** — --list/--help/--verify/--component/--latest/--date/--target/--yes
- ✅ **周日 sample-restore 验证** — PG + Redis magic check
- ✅ **9 bash scripts syntax OK** — 100% 通过 bash -n
- ✅ **PITR 已配** (postgresql.conf archive_mode=on + archive_command) — **撤回 attempt 1 B2 gap**
- ✅ **安全加固** — chmod 600, oneshot service, ProtectedSystem, IOSchedulingClass

**P0 production-blockers (Attempt 1 漏判, 此次深挖)**:
- **H1**: backup_cron.timer `Unit=imdf-backup.service` 引用不存在的 service — 备份不会自动跑
- **H2**: install.sh enable list 漏 backup — 即使 H1 修, 也不 enable
- **双修后** ~10 min, 备份才真正能跑

**P1 修复 (~16 min)**: H6 注释 / H7 typo / H8 Celery 暂停

**P2+P3**: B1 跨 Region / B3 OSS 增量 / B4 加密 / B5 UI / B6 dry-run / H14 env vars (~4h)

**总 P0+P1 修复工作量**: ~25 min (1 工作时)

**本机实跑验证 (可跑部分)**:
- `bash -n` × 9 scripts → 9/9 OK
- `restore.sh --help` → 18 行正确输出
- `restore.sh --list` → 空目录优雅输出

**不能在本地跑的测试** (无 PG/Redis/MinIO/systemd on Windows):
- PG dump 真实执行
- Redis BGSAVE 真实执行
- MinIO mc mirror 真实执行
- systemd timer 实际触发 (需 systemd)
- 完整 3-tier migrate_tiers (需先有 hot 数据)
