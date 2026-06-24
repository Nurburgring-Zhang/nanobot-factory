#!/usr/bin/env bash
# ============================================================================
# restore.sh — IMDF restore from backup tier (hot / warm / cold)
# ----------------------------------------------------------------------------
# Usage:
#   restore.sh --component pg|redis|oss --file <path> [--to <restore-target>]
#   restore.sh --component pg --latest                 # restore most recent
#   restore.sh --component pg --date 2026-06-23        # restore that day's
#   restore.sh --list                                  # list available backups
#   restore.sh --verify                                # dry-run integrity check
#
# Examples:
#   sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
#        --component pg --latest --target imdf_restored
#
#   sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh \
#        --component redis --file /var/backups/imdf/redis/dump-20260624-030000.rdb.gz
#
#   sudo /opt/nanobot-factory/deploy/bare_metal/restore.sh --list
# ============================================================================
set -euo pipefail

# ── Defaults ────────────────────────────────────────────────────────────
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/imdf}"
ENV_FILE="${ENV_FILE:-/etc/imdf/imdf.env}"
COMPONENT=""
FILE=""
TARGET_DB=""
RESTORE_DATE=""
LIST_ONLY=false
VERIFY_ONLY=false
LATEST=false
ASSUME_YES=false

usage() {
  # Print only the contiguous top-of-file comment block (between #!/usr/bin line
  # and the first non-comment line). Subsequent section headers in the script
  # body (e.g. "── Defaults ──") must not leak into --help output.
  awk '
    NR == 1 { next }                       # skip shebang
    /^[^#]/ && printed { exit }            # stop at first code line after some #s
    /^[^#]/ { next }                       # skip blank/non-comment lines before any output
    { sub(/^# ?/, ""); printed = 1; print }
  ' "$0"
  exit "${1:-0}"
}

err() { echo "[restore] ERROR: $*" >&2; }
log() { echo "[restore] $(date -u +%FT%TZ) $*"; }

# ── Parse args ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --component)  COMPONENT="$2"; shift 2 ;;
    --file)       FILE="$2"; shift 2 ;;
    --target)     TARGET_DB="$2"; shift 2 ;;
    --date)       RESTORE_DATE="$2"; shift 2 ;;
    --latest)     LATEST=true; shift ;;
    --list)       LIST_ONLY=true; shift ;;
    --verify)     VERIFY_ONLY=true; shift ;;
    --yes)        ASSUME_YES=true; shift ;;
    -h|--help)    usage 0 ;;
    *)            err "unknown arg: $1"; usage 1 ;;
  esac
done

load_env() {
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "${ENV_FILE}"
    set +a
  fi
}

# ── List backups ────────────────────────────────────────────────────────
list_backups() {
  log "available backups in ${BACKUP_ROOT}:"
  for tier in db redis oss warm cold; do
    local dir="${BACKUP_ROOT}/${tier}"
    [[ -d "${dir}" ]] || continue
    local count
    count=$(find "${dir}" -type f \( -name '*.gz' -o -name '*.rdb' -o -name '*.tar*' \) | wc -l)
    local total_size
    total_size=$(du -sh "${dir}" 2>/dev/null | cut -f1)
    printf '  %-8s  %4d files  %8s  %s\n' "${tier}" "${count}" "${total_size:-?}" "${dir}"
  done
  echo
  echo "Recent (last 10):"
  find "${BACKUP_ROOT}" -type f \( -name '*.gz' -o -name '*.rdb' -o -name '*.tar*' \) \
    -printf '%T+  %10s  %p\n' 2>/dev/null | sort -r | head -10
}

# ── Find latest matching file ──────────────────────────────────────────
find_latest() {
  local pattern="$1"
  if [[ -n "${RESTORE_DATE}" ]]; then
    find "${BACKUP_ROOT}" -type f -name "${pattern}" \
      \( -path "*/db/*" -o -path "*/redis/*" -o -path "*/oss/*" -o -path "*/warm/*" -o -path "*/cold/*" \) \
      -newermt "${RESTORE_DATE}" ! -newermt "${RESTORE_DATE} +24 hours" 2>/dev/null \
      | sort | tail -1
  else
    find "${BACKUP_ROOT}" -type f -name "${pattern}" 2>/dev/null | sort | tail -1
  fi
}

# ── Verify (integrity check, no actual restore) ────────────────────────
verify_backup() {
  local file="$1"
  log "verify: ${file}"
  if [[ ! -f "${file}" ]]; then
    err "file not found"
    return 1
  fi
  case "${file}" in
    *.sql.gz)
      if gzip -t "${file}" 2>/dev/null && \
         gunzip -c "${file}" | head -50 | grep -q "PostgreSQL database dump"; then
        log "  PG dump OK ($(du -h "${file}" | cut -f1))"
        return 0
      fi
      err "  PG dump verify FAILED"
      return 1
      ;;
    *.rdb.gz)
      if gzip -t "${file}" 2>/dev/null && \
         gunzip -c "${file}" | head -c 5 | grep -q "REDIS"; then
        log "  Redis RDB OK ($(du -h "${file}" | cut -f1))"
        return 0
      fi
      err "  Redis RDB verify FAILED"
      return 1
      ;;
    *.tar.gz)
      if tar -tzf "${file}" >/dev/null 2>&1; then
        log "  OSS tarball OK ($(du -h "${file}" | cut -f1))"
        return 0
      fi
      err "  OSS tarball verify FAILED"
      return 1
      ;;
    *)
      err "  unknown file type: ${file}"
      return 1
      ;;
  esac
}

# ── Confirm destructive action ─────────────────────────────────────────
confirm() {
  if [[ "${ASSUME_YES}" == "true" ]]; then return 0; fi
  echo
  echo "DESTRUCTIVE OPERATION — about to restore ${COMPONENT}"
  echo "  source: ${FILE}"
  echo "  target: ${TARGET_DB:-<default>}"
  read -rp "Type 'YES' to continue: " ans
  [[ "${ans}" == "YES" ]]
}

# ── Restore: PG ────────────────────────────────────────────────────────
restore_pg() {
  load_env
  TARGET_DB="${TARGET_DB:-imdf_restored_$(date +%Y%m%d-%H%M%S)}"
  log "creating target DB: ${TARGET_DB}"
  export PGPASSWORD="${DB_APP_PASSWORD:-${DB_PASSWORD:-}}"
  psql -h "${DB_HOST:-127.0.0.1}" -p "${DB_PORT:-5432}" \
       -U "${DB_SUPER_USER:-postgres}" -d postgres \
       -c "CREATE DATABASE ${TARGET_DB};" 2>>/tmp/restore-pg-err.log
  log "gunzip + psql pipe → ${TARGET_DB}"
  gunzip -c "${FILE}" | psql -h "${DB_HOST:-127.0.0.1}" -p "${DB_PORT:-5432}" \
         -U "${DB_APP_USER:-imdf_app}" -d "${TARGET_DB}" \
         -v ON_ERROR_STOP=1 2>>/tmp/restore-pg-err.log
  log "PG restore OK → ${TARGET_DB}"
  log "switch over:  sudo -u imdf bash -c 'psql -c \"ALTER DATABASE imdf RENAME TO imdf_old; ALTER DATABASE ${TARGET_DB} RENAME TO imdf;\"'"
}

# ── Restore: Redis ────────────────────────────────────────────────────
restore_redis() {
  load_env
  log "stopping redis-server to replace RDB"
  systemctl stop redis-server
  local rdb="/var/lib/redis/dump.rdb"
  cp "${rdb}" "${rdb}.bak-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
  gunzip -c "${FILE}" > "${rdb}"
  chown redis:redis "${rdb}" 2>/dev/null || true
  log "starting redis-server; verify with redis-cli ping"
  systemctl start redis-server
  sleep 2
  redis-cli -h "${REDIS_HOST:-127.0.0.1}" -p "${REDIS_PORT:-6379}" ping
  log "Redis restore OK"
}

# ── Restore: OSS ──────────────────────────────────────────────────────
restore_oss() {
  load_env
  local bucket="${OSS_BUCKET:-imdf-assets}"
  local workdir
  workdir="$(mktemp -d /tmp/imdf-oss-restore.XXXXXX)"
  trap 'rm -rf "${workdir}"' EXIT
  log "extracting to ${workdir}"
  tar -xzf "${FILE}" -C "${workdir}"
  if command -v mc >/dev/null 2>&1; then
    local alias="localminio"
    if ! mc alias list "${alias}" >/dev/null 2>&1; then
      mc alias set "${alias}" \
        "http://${MINIO_HOST:-127.0.0.1}:${MINIO_PORT:-9000}" \
        "${MINIO_ROOT_USER:-minioadmin}" \
        "${MINIO_ROOT_PASSWORD:-minioadmin}"
    fi
    mc mirror --preserve --quiet "${workdir}/staging-"*/ "${alias}/${bucket}/" \
      || err "some files failed to restore; check mc output"
  else
    err "mc not installed; extract manually with: tar -xzf ${FILE}"
    return 1
  fi
  log "OSS restore OK"
}

# ── Main ───────────────────────────────────────────────────────────────
load_env

if [[ "${LIST_ONLY}" == "true" ]]; then
  list_backups
  exit 0
fi

if [[ -z "${COMPONENT}" ]]; then
  err "--component required (pg|redis|oss)"
  usage 1
fi

# Resolve FILE
if [[ "${LATEST}" == "true" ]]; then
  case "${COMPONENT}" in
    pg)    FILE="$(find_latest 'imdf-*.sql.gz')" ;;
    redis) FILE="$(find_latest 'dump-*.rdb.gz')" ;;
    oss)   FILE="$(find_latest '*imdf-assets*.tar.gz')" ;;
    *)     err "unsupported component: ${COMPONENT}"; exit 1 ;;
  esac
  log "resolved --latest → ${FILE}"
fi

if [[ -z "${FILE}" ]]; then
  err "--file (or --latest) required"
  usage 1
fi

if [[ ! -f "${FILE}" ]]; then
  err "backup file not found: ${FILE}"
  exit 1
fi

if [[ "${VERIFY_ONLY}" == "true" ]]; then
  verify_backup "${FILE}"
  exit $?
fi

# Confirm
confirm || { err "aborted by user"; exit 1; }

# Dispatch
case "${COMPONENT}" in
  pg)    restore_pg ;;
  redis) restore_redis ;;
  oss)   restore_oss ;;
  *)     err "unsupported component: ${COMPONENT}"; exit 1 ;;
esac
