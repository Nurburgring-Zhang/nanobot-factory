#!/usr/bin/env bash
# ============================================================================
# backup-db.sh — pg_dump daily backup with 14-day retention
# ----------------------------------------------------------------------------
# Cron entry (as root):
#   0 3 * * *  /opt/nanobot-factory/deploy/bare_metal/scripts/backup-db.sh
# ============================================================================
set -euo pipefail

BACKUP_ROOT="/var/backups/imdf/db"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DAY="$(date +%Y%m%d)"
BACKUP_FILE="${BACKUP_ROOT}/imdf-${TIMESTAMP}.sql.gz"

# ── Read credentials from /etc/imdf/imdf.env ───────────────────────────
ENV_FILE="/etc/imdf/imdf.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[backup] ERROR: ${ENV_FILE} not found" >&2
  exit 1
fi

DB_USER="$(grep -E '^DB_APP_USER=' "${ENV_FILE}" | cut -d= -f2)"
DB_PASS="$(grep -E '^DB_APP_PASSWORD=' "${ENV_FILE}" | cut -d= -f2)"
DB_HOST="$(grep -E '^DB_HOST=' "${ENV_FILE}" | cut -d= -f2)"
DB_PORT="$(grep -E '^DB_PORT=' "${ENV_FILE}" | cut -d= -f2)"
DB_NAME="$(grep -E '^DB_NAME=' "${ENV_FILE}" | cut -d= -f2)"

if [[ -z "${DB_USER}" || -z "${DB_NAME}" ]]; then
  echo "[backup] ERROR: DB_APP_USER / DB_NAME missing in ${ENV_FILE}" >&2
  exit 1
fi

mkdir -p "${BACKUP_ROOT}"
chmod 700 "${BACKUP_ROOT}"

# ── Dump ────────────────────────────────────────────────────────────────
echo "[backup] dumping ${DB_NAME}@${DB_HOST}:${DB_PORT} → ${BACKUP_FILE}"
export PGPASSWORD="${DB_PASS}"
if pg_dump \
    --host="${DB_HOST}" \
    --port="${DB_PORT}" \
    --username="${DB_USER}" \
    --dbname="${DB_NAME}" \
    --no-owner \
    --no-privileges \
    --format=plain \
    --verbose \
    2>>"${BACKUP_ROOT}/pg_dump-${DAY}.log" \
    | gzip -c > "${BACKUP_FILE}"; then
  chmod 600 "${BACKUP_FILE}"
  SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
  echo "[backup] OK ${BACKUP_FILE} (${SIZE})"
else
  echo "[backup] FAILED — see ${BACKUP_ROOT}/pg_dump-${DAY}.log" >&2
  exit 1
fi

# ── Retention sweep ─────────────────────────────────────────────────────
echo "[backup] pruning backups older than ${RETENTION_DAYS} days"
DELETED=$(find "${BACKUP_ROOT}" -type f -name 'imdf-*.sql.gz' -mtime +"${RETENTION_DAYS}" -delete -print | wc -l)
echo "[backup] pruned ${DELETED} old file(s)"

# ── Verify (smoke) ─────────────────────────────────────────────────────
echo "[backup] verifying backup header"
if gzip -t "${BACKUP_FILE}" 2>/dev/null; then
  if gunzip -c "${BACKUP_FILE}" | head -50 | grep -q "PostgreSQL database dump"; then
    echo "[backup] verification OK"
  else
    echo "[backup] WARNING: file is valid gzip but missing pg_dump header" >&2
    exit 1
  fi
else
  echo "[backup] FAILED gzip integrity check" >&2
  exit 1
fi

echo "[backup] DONE"