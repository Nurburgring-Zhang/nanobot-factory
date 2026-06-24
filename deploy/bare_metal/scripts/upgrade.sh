#!/usr/bin/env bash
# ============================================================================
# upgrade.sh — pull + reinstall deps + alembic upgrade head + restart
# ----------------------------------------------------------------------------
# Usage:
#   sudo deploy/bare_metal/scripts/upgrade.sh           # upgrade to HEAD
#   sudo deploy/bare_metal/scripts/upgrade.sh v1.7.0    # checkout tag
#   sudo deploy/bare_metal/scripts/upgrade.sh --no-pull # skip git pull
#   sudo deploy/bare_metal/scripts/upgrade.sh --no-deps # skip pip install
# ============================================================================
set -euo pipefail

PROJECT_ROOT="${IMDF_PROJECT_ROOT:-/opt/nanobot-factory}"
VENV="${IMDF_VENV:-${PROJECT_ROOT}/venv}"
LOG_DIR="${IMDF_LOGS_DIR:-${PROJECT_ROOT}/logs}"
LOG_FILE="${LOG_DIR}/upgrade-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "${LOG_DIR}"

TARGET_REF=""
SKIP_PULL=0
SKIP_DEPS=0
for arg in "$@"; do
  case "${arg}" in
    --no-pull) SKIP_PULL=1 ;;
    --no-deps) SKIP_DEPS=1 ;;
    --help|-h)
      sed -n '2,12p' "$0"; exit 0 ;;
    *)
      if [[ -z "${TARGET_REF}" ]]; then TARGET_REF="${arg}"; else
        echo "unknown arg: ${arg}" >&2; exit 1
      fi
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "must run as root (sudo $0)" >&2
  exit 1
fi

exec &> >(tee -a "${LOG_FILE}")
echo "[upgrade $(date +%H:%M:%S)] log → ${LOG_FILE}"

# ── 0. pre-flight ───────────────────────────────────────────────────────
echo "[upgrade] pre-flight checks"
test -d "${PROJECT_ROOT}/.git" || { echo "[upgrade] not a git repo: ${PROJECT_ROOT}" >&2; exit 1; }
test -x "${VENV}/bin/python" || { echo "[upgrade] venv missing: ${VENV}" >&2; exit 1; }

# ── 1. snapshot current SHA for rollback note ───────────────────────────
OLD_SHA=$(sudo -u imdf git -C "${PROJECT_ROOT}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "[upgrade] current SHA: ${OLD_SHA}"

# ── 2. git pull ─────────────────────────────────────────────────────────
if [[ ${SKIP_PULL} -eq 0 ]]; then
  echo "[upgrade] fetching + checking out ${TARGET_REF:-HEAD}"
  sudo -u imdf bash -c "cd '${PROJECT_ROOT}' && git fetch --tags --prune && git checkout ${TARGET_REF:-HEAD} && git pull --ff-only"
else
  echo "[upgrade] skipping git pull (--no-pull)"
fi

NEW_SHA=$(sudo -u imdf git -C "${PROJECT_ROOT}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
echo "[upgrade] new SHA: ${NEW_SHA}"
if [[ "${OLD_SHA}" == "${NEW_SHA}" ]]; then
  echo "[upgrade] no change in HEAD — proceeding anyway to ensure deps + migrations"
fi

# ── 3. pip install ──────────────────────────────────────────────────────
if [[ ${SKIP_DEPS} -eq 0 ]]; then
  echo "[upgrade] installing python deps"
  sudo -u imdf bash -c "source '${VENV}/bin/activate' && \
    pip install --upgrade pip wheel setuptools && \
    pip install -r '${PROJECT_ROOT}/backend/requirements.txt'"
else
  echo "[upgrade] skipping pip install (--no-deps)"
fi

# ── 4. frontend build (only if frontend changed) ────────────────────────
if [[ -d "${PROJECT_ROOT}/frontend-v2" ]] && \
   sudo -u imdf git -C "${PROJECT_ROOT}/frontend-v2" diff --name-only "${OLD_SHA}..${NEW_SHA}" 2>/dev/null | grep -q .; then
  echo "[upgrade] frontend changes detected — rebuilding"
  sudo -u imdf bash -c "cd '${PROJECT_ROOT}/frontend-v2' && \
    (test -d node_modules || npm ci) && npm run build"
else
  echo "[upgrade] frontend unchanged — skipping build"
fi

# ── 5. alembic upgrade head ─────────────────────────────────────────────
echo "[upgrade] alembic upgrade head"
sudo -u imdf bash -c "
  source /etc/imdf/imdf.env
  source '${VENV}/bin/activate'
  cd '${PROJECT_ROOT}'
  alembic -c backend/alembic.ini upgrade head
"

# ── 6. rolling restart of app services ──────────────────────────────────
echo "[upgrade] restarting imdf app services"
SERVICES=(
  imdf-gateway
  imdf-user imdf-asset imdf-annotation imdf-cleaning
  imdf-scoring imdf-dataset imdf-evaluation imdf-agent
  imdf-workflow imdf-notification imdf-search imdf-collection
  imdf-celery imdf-celery-beat
)
for svc in "${SERVICES[@]}"; do
  if systemctl is-active --quiet "${svc}.service"; then
    systemctl restart "${svc}.service"
    echo "[upgrade]   restarted ${svc}.service"
  fi
done

# ── 7. smoke test ───────────────────────────────────────────────────────
echo "[upgrade] smoke test (10 s)"
sleep 5
for i in 1 2 3 4 5; do
  if curl -fsS --max-time 3 http://127.0.0.1:8000/api/queue/health >/dev/null 2>&1; then
    echo "[upgrade] gateway healthy — DONE"
    echo "[upgrade] rollback: sudo -u imdf git -C '${PROJECT_ROOT}' checkout ${OLD_SHA}"
    echo "[upgrade] then: deploy/bare_metal/scripts/upgrade.sh --no-pull --no-deps"
    exit 0
  fi
  echo "[upgrade] gateway not yet ready (try ${i}/5)..."
  sleep 2
done

echo "[upgrade] WARNING: gateway did not become healthy after restart" >&2
echo "[upgrade] check: journalctl -u imdf-gateway -n 100 --no-pager" >&2
exit 1