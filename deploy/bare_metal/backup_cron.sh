#!/usr/bin/env bash
# ============================================================================
# backup_cron.sh — IMDF unified backup orchestrator
# ----------------------------------------------------------------------------
# Daily 3 jobs (driven by systemd timer, not cron):
#   - 03:00  PG full dump    (hot  7d)         → /var/backups/imdf/db
#   - 03:30  Redis RDB       (hot  7d)         → /var/backups/imdf/redis
#   - Sun 04:00  OSS files   (warm 30d/cold 365d) → /var/backups/imdf/oss
#   - 04:30  retention sweep + sample-restore verify
#
# Retention tiers (configurable via env):
#   HOT_TIER_DAYS   (default 7)   /var/backups/imdf/{db,redis,oss}
#   WARM_TIER_DAYS  (default 30)  /var/backups/imdf/warm
#   COLD_TIER_DAYS  (default 365) /var/backups/imdf/cold
#
# Replaces ad-hoc crontab with systemd timer; see backup_cron.{service,timer}.
# ============================================================================
set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────
ENV_FILE="${ENV_FILE:-/etc/imdf/imdf.env}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/imdf}"
LOG_DIR="${LOG_DIR:-/var/log/imdf-backup}"
HOT_TIER_DAYS="${HOT_TIER_DAYS:-7}"
WARM_TIER_DAYS="${WARM_TIER_DAYS:-30}"
COLD_TIER_DAYS="${COLD_TIER_DAYS:-365}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DAY="$(date +%Y%m%d)"
JOB_TAG="${JOB_TAG:-manual}"   # cron | manual | verify
LOCKFILE="${BACKUP_ROOT}/.lock"
NOTIFY_WEBHOOK="${BACKUP_NOTIFY_WEBHOOK:-}"  # optional Slack webhook

mkdir -p "${BACKUP_ROOT}" "${LOG_DIR}" "${BACKUP_ROOT}/db" "${BACKUP_ROOT}/redis" "${BACKUP_ROOT}/oss" "${BACKUP_ROOT}/warm" "${BACKUP_ROOT}/cold"
chmod 700 "${BACKUP_ROOT}" "${LOG_DIR}"

# ── Helpers ─────────────────────────────────────────────────────────────
log() { printf '[%s] %s %s\n' "$(date -u +%FT%TZ)" "${JOB_TAG}" "$*"; }
logfile="${LOG_DIR}/backup-${DAY}.log"
exec > >(tee -a "${logfile}") 2>&1

err() { log "ERROR: $*" >&2; }

acquire_lock() {
  if [[ -e "${LOCKFILE}" ]]; then
    pid="$(cat "${LOCKFILE}" 2>/dev/null || echo '')"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      err "another backup is running (pid=${pid}); aborting"
      exit 1
    else
      log "stale lock (pid=${pid}) removed"
      rm -f "${LOCKFILE}"
    fi
  fi
  echo "$$" > "${LOCKFILE}"
  trap 'rm -f "${LOCKFILE}"' EXIT
}

load_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "${ENV_FILE}"
    set +a
  else
    err "env file ${ENV_FILE} not found; using process environment"
  fi
}

# Send Slack (or generic webhook) notification
notify() {
  local status="$1" msg="$2"
  if [[ -z "${NOTIFY_WEBHOOK}" ]]; then
    return 0
  fi
  local payload
  payload=$(printf '{"text":"[%s] %s — %s"}' "${status}" "$(hostname)" "${msg}")
  curl --silent --show-error --max-time 5 \
    -H 'Content-Type: application/json' \
    -d "${payload}" \
    "${NOTIFY_WEBHOOK}" >/dev/null || true
}

# ── PG dump ─────────────────────────────────────────────────────────────
backup_pg() {
  local out="${BACKUP_ROOT}/db/imdf-${TIMESTAMP}.sql.gz"
  log "PG dump → ${out}"
  export PGPASSWORD="${DB_APP_PASSWORD:-${DB_PASSWORD:-}}"
  if pg_dump \
      --host="${DB_HOST:-127.0.0.1}" \
      --port="${DB_PORT:-5432}" \
      --username="${DB_APP_USER:-imdf_app}" \
      --dbname="${DB_NAME:-imdf}" \
      --no-owner --no-privileges --format=plain --verbose \
      2>>"${LOG_DIR}/pg_dump-${DAY}.log" \
      | gzip -c > "${out}"; then
    chmod 600 "${out}"
    if gzip -t "${out}" 2>/dev/null; then
      log "PG dump OK ($(du -h "${out}" | cut -f1))"
      return 0
    else
      err "PG dump failed gzip integrity"
      rm -f "${out}"
      return 1
    fi
  else
    err "PG dump failed (see pg_dump-${DAY}.log)"
    return 1
  fi
}

# ── Redis RDB ───────────────────────────────────────────────────────────
backup_redis() {
  local out="${BACKUP_ROOT}/redis/dump-${TIMESTAMP}.rdb.gz"
  log "Redis RDB → ${out}"
  local rdb="/var/lib/redis/dump.rdb"
  # Method 1: BGSAVE then copy (preferred, non-blocking)
  if redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" -a "${REDIS_PASSWORD:-}" \
       --no-auth-warning BGSAVE 2>>"${LOG_DIR}/redis-${DAY}.log"; then
    # wait for lastsave to advance
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      sleep 1
      local lastsave
      lastsave=$(redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" LASTSAVE 2>/dev/null || echo 0)
      [[ -n "${lastsave}" && "${lastsave}" != "0" ]] && break
    done
    # redis writes dump.rdb to its working dir
    if [[ -f "${rdb}" ]]; then
      gzip -c "${rdb}" > "${out}"
      chmod 600 "${out}"
      log "Redis RDB OK ($(du -h "${out}" | cut -f1))"
      return 0
    fi
  fi
  err "Redis RDB failed; falling back to CONFIG-less snapshot"
  # Method 2: redis-cli --rdb (Redis 5+)
  if redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" \
      --no-auth-warning --rdb "${out%.gz}" 2>>"${LOG_DIR}/redis-${DAY}.log"; then
    gzip -f "${out%.gz}"
    chmod 600 "${out}"
    log "Redis RDB OK via --rdb ($(du -h "${out}" | cut -f1))"
    return 0
  fi
  err "Redis RDB fully failed"
  return 1
}

# ── OSS files (MinIO / S3) ─────────────────────────────────────────────
backup_oss() {
  local bucket="${OSS_BUCKET:-imdf-assets}"
  local out="${BACKUP_ROOT}/oss/${bucket}-${TIMESTAMP}.tar.gz"
  log "OSS bucket ${bucket} → ${out}"
  # Use mc mirror if available, else fall back to rclone, else AWS CLI
  if command -v mc >/dev/null 2>&1; then
    local alias="localminio"
    if ! mc alias list "${alias}" >/dev/null 2>&1; then
      mc alias set "${alias}" \
        "http://${MINIO_HOST:-127.0.0.1}:${MINIO_PORT:-9000}" \
        "${MINIO_ROOT_USER:-minioadmin}" \
        "${MINIO_ROOT_PASSWORD:-minioadmin}" 2>>"${LOG_DIR}/oss-${DAY}.log"
    fi
    if mc mirror --preserve --quiet "${alias}/${bucket}/" "${BACKUP_ROOT}/oss/staging-${TIMESTAMP}/" \
        2>>"${LOG_DIR}/oss-${DAY}.log}"; then
      tar -czf "${out}" -C "${BACKUP_ROOT}/oss" "staging-${TIMESTAMP}"
      rm -rf "${BACKUP_ROOT}/oss/staging-${TIMESTAMP}"
      chmod 600 "${out}"
      log "OSS mirror OK ($(du -h "${out}" | cut -f1))"
      return 0
    fi
    err "OSS mirror failed"
    return 1
  elif command -v rclone >/dev/null 2>&1; then
    # rclone path style: :s3:bucket/
    if rclone copy ":s3:${bucket}/" "${BACKUP_ROOT}/oss/staging-${TIMESTAMP}/" \
        --s3-endpoint "http://${MINIO_HOST:-127.0.0.1}:${MINIO_PORT:-9000}" \
        --s3-access-key-id "${MINIO_ROOT_USER:-minioadmin}" \
        --s3-secret-access-key "${MINIO_ROOT_PASSWORD:-minioadmin}" \
        --quiet 2>>"${LOG_DIR}/oss-${DAY}.log"; then
      tar -czf "${out}" -C "${BACKUP_ROOT}/oss" "staging-${TIMESTAMP}"
      rm -rf "${BACKUP_ROOT}/oss/staging-${TIMESTAMP}"
      chmod 600 "${out}"
      log "OSS rclone OK ($(du -h "${out}" | cut -f1))"
      return 0
    fi
    err "OSS rclone failed"
    return 1
  else
    err "neither mc nor rclone installed; skipping OSS backup"
    return 1
  fi
}

# ── Tier migration (hot → warm → cold) ─────────────────────────────────
migrate_tiers() {
  log "migrating tiers: hot(${HOT_TIER_DAYS}d) → warm(${WARM_TIER_DAYS}d) → cold(${COLD_TIER_DAYS}d)"
  # Promote hot → warm
  find "${BACKUP_ROOT}/db" "${BACKUP_ROOT}/redis" "${BACKUP_ROOT}/oss" -type f \
    -mtime +"${HOT_TIER_DAYS}" -name '*.gz' 2>/dev/null | while read -r f; do
      local rel="${f#${BACKUP_ROOT}/}"
      local dest="${BACKUP_ROOT}/warm/${rel}"
      mkdir -p "$(dirname "${dest}")"
      mv "${f}" "${dest}"
      log "  hot→warm: ${rel}"
    done
  # Promote warm → cold
  find "${BACKUP_ROOT}/warm" -type f -mtime +"${WARM_TIER_DAYS}" 2>/dev/null | while read -r f; do
    local rel="${f#${BACKUP_ROOT}/warm/}"
    local dest="${BACKUP_ROOT}/cold/${rel}"
    mkdir -p "$(dirname "${dest}")"
    mv "${f}" "${dest}"
    log "  warm→cold: ${rel}"
  done
  # Prune cold beyond retention
  local pruned
  pruned=$(find "${BACKUP_ROOT}/cold" -type f -mtime +"${COLD_TIER_DAYS}" -delete -print 2>/dev/null | wc -l)
  log "  cold prune: ${pruned} file(s) deleted"
}

# ── Sample-restore verify (Sunday only, after OSS) ──────────────────────
verify_sample() {
  if [[ "$(date +%u)" != "7" ]]; then
    log "verify skipped (only runs Sunday)"
    return 0
  fi
  log "running sample-restore verify"
  local latest_pg latest_redis
  latest_pg="$(ls -t "${BACKUP_ROOT}/db"/imdf-*.sql.gz 2>/dev/null | head -1 || true)"
  latest_redis="$(ls -t "${BACKUP_ROOT}/redis"/dump-*.rdb.gz 2>/dev/null | head -1 || true)"
  local workdir
  workdir="$(mktemp -d /tmp/imdf-verify.XXXXXX)"
  trap 'rm -rf "${workdir}" "${LOCKFILE}"' EXIT
  local rc=0
  if [[ -n "${latest_pg}" ]]; then
    log "  verifying PG: ${latest_pg}"
    gunzip -c "${latest_pg}" > "${workdir}/dump.sql"
    if head -5 "${workdir}/dump.sql" | grep -q "PostgreSQL database dump"; then
      log "  PG verify OK"
    else
      err "  PG verify FAILED (missing header)"
      rc=1
    fi
  fi
  if [[ -n "${latest_redis}" ]]; then
    log "  verifying Redis RDB: ${latest_redis}"
    if gzip -t "${latest_redis}" 2>/dev/null; then
      # Heuristic: RDB magic starts with "REDIS" after gunzip
      if gunzip -c "${latest_redis}" | head -c 5 | grep -q "REDIS"; then
        log "  Redis verify OK"
      else
        err "  Redis verify FAILED (missing REDIS magic)"
        rc=1
      fi
    else
      err "  Redis verify FAILED (gzip integrity)"
      rc=1
    fi
  fi
  return "${rc}"
}

# ── Main ────────────────────────────────────────────────────────────────
acquire_lock
load_env
log "===== backup start (job=${JOB_TAG}) ====="

rc=0
case "${BACKUP_TARGETS:-all}" in
  pg|all)      backup_pg      || rc=1 ;;
  redis)       backup_redis   || rc=1 ;;
  oss)         backup_oss     || rc=1 ;;
  *)           err "unknown target: ${BACKUP_TARGETS}"; exit 2 ;;
esac

# tier migration + verify (only on full nightly run)
if [[ "${BACKUP_TARGETS:-all}" == "all" ]]; then
  migrate_tiers
  verify_sample || rc=1
fi

if [[ "${rc}" -eq 0 ]]; then
  log "===== backup done OK ====="
  notify "OK" "backup succeeded (job=${JOB_TAG})"
else
  log "===== backup FAILED (rc=${rc}) ====="
  notify "FAIL" "backup failed (job=${JOB_TAG}, rc=${rc}); see ${logfile}"
fi
exit "${rc}"
