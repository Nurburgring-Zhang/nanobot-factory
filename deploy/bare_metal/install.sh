#!/usr/bin/env bash
# ============================================================================
# install.sh — IMDF bare-metal installer
# ----------------------------------------------------------------------------
# Idempotent. Run as root on Ubuntu 22.04 LTS.
#
#   sudo ./install.sh                 # full install (apt + user + dirs + units)
#   sudo ./install.sh --units-only    # skip apt, just stage systemd + .env
#   sudo ./install.sh --no-enable     # stage units but don't auto-start
#
# After install:
#   1. cp /etc/imdf/imdf.env.example /etc/imdf/imdf.env  (edit secrets)
#   2. sudo deploy/bare_metal/scripts/start-all.sh
# ============================================================================
set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT_DEFAULT="/opt/nanobot-factory"
IMDF_HOME_DEFAULT="/opt/nanobot-factory"
ENV_DIR_DEFAULT="/etc/imdf"

# ── Args ─────────────────────────────────────────────────────────────────
UNITS_ONLY=0
NO_ENABLE=0
PROJECT_ROOT="${PROJECT_ROOT_DEFAULT}"
IMDF_HOME="${IMDF_HOME_DEFAULT}"
ENV_DIR="${ENV_DIR_DEFAULT}"

for arg in "$@"; do
  case "$arg" in
    --units-only)    UNITS_ONLY=1 ;;
    --no-enable)     NO_ENABLE=1 ;;
    --project-root=*)PROJECT_ROOT="${arg#*=}" ;;
    --home=*)        IMDF_HOME="${arg#*=}" ;;
    --env-dir=*)     ENV_DIR="${arg#*=}" ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0 ;;
    *) echo "Unknown arg: $arg" >&2; exit 1 ;;
  esac
done

# ── Pre-flight ───────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "[install] must run as root (sudo $0)" >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "[install] systemd not detected — abort" >&2
  exit 1
fi

log() { printf '[install %s] %s\n' "$(date +%H:%M:%S)" "$*"; }

# ── 1. apt packages (skip with --units-only) ─────────────────────────────
if [[ $UNITS_ONLY -eq 0 ]]; then
  log "updating apt cache"
  apt-get update -y
  log "installing apt packages"
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    python3.11 python3.11-venv python3.11-dev python3-pip \
    postgresql-15 postgresql-server-dev-15 postgresql-15-pgvector \
    redis-server nginx git curl wget ca-certificates \
    build-essential pkg-config libssl-dev \
    prometheus grafana
fi

# ── 2. system user ───────────────────────────────────────────────────────
if ! id imdf >/dev/null 2>&1; then
  log "creating system user 'imdf'"
  useradd --system \
          --home-dir "${IMDF_HOME}" \
          --shell /usr/sbin/nologin \
          --comment "IMDF nanobot-factory service account" \
          imdf
fi

if ! id minio-user >/dev/null 2>&1; then
  log "creating system user 'minio-user'"
  useradd --system --shell /usr/sbin/nologin --home-dir /var/lib/minio minio-user
fi

# ── 3. directory layout ─────────────────────────────────────────────────
log "laying out ${IMDF_HOME}"
mkdir -p "${IMDF_HOME}"/{data,logs,data/audit,data/prometheus,data/celery}
mkdir -p "${ENV_DIR}"
mkdir -p /var/backups/imdf/{db,wal}
mkdir -p /var/lib/minio

chown -R imdf:imdf "${IMDF_HOME}"
chmod 750 "${IMDF_HOME}"
chmod 700 "${IMDF_HOME}/data"
chmod 750 "${IMDF_HOME}/logs"
chown -R minio-user:minio-user /var/lib/minio
chmod 750 /var/lib/minio

# ── 4. environment file ─────────────────────────────────────────────────
if [[ ! -f "${ENV_DIR}/imdf.env" ]]; then
  log "seeding ${ENV_DIR}/imdf.env from .env.example"
  cp "${SCRIPT_DIR}/.env.example" "${ENV_DIR}/imdf.env"
  # replace defaults with project-root aware paths
  sed -i "s|^IMDF_PROJECT_ROOT=.*|IMDF_PROJECT_ROOT=${PROJECT_ROOT}|" "${ENV_DIR}/imdf.env"
  sed -i "s|^IMDF_VENV=.*|IMDF_VENV=${IMDF_HOME}/venv|" "${ENV_DIR}/imdf.env"
  sed -i "s|^IMDF_DATA_DIR=.*|IMDF_DATA_DIR=${IMDF_HOME}/data|" "${ENV_DIR}/imdf.env"
  sed -i "s|^IMDF_LOGS_DIR=.*|IMDF_LOGS_DIR=${IMDF_HOME}/logs|" "${ENV_DIR}/imdf.env"
  chmod 600 "${ENV_DIR}/imdf.env"
  chown imdf:imdf "${ENV_DIR}/imdf.env"
  log "*** EDIT ${ENV_DIR}/imdf.env and set all CHANGE_ME_* secrets before starting ***"
else
  log "${ENV_DIR}/imdf.env already exists — leaving untouched"
fi

# ── 5. python venv + deps ───────────────────────────────────────────────
if [[ ! -d "${IMDF_HOME}/venv" ]]; then
  log "creating python venv at ${IMDF_HOME}/venv"
  sudo -u imdf python3.11 -m venv "${IMDF_HOME}/venv"
  log "installing backend python deps (may take 2-3 min)"
  sudo -u imdf bash -c "
    source '${IMDF_HOME}/venv/bin/activate'
    pip install --upgrade pip wheel setuptools
    pip install -r '${PROJECT_ROOT}/requirements.txt'
  "
fi

# ── 6. systemd units ─────────────────────────────────────────────────────
log "staging systemd units to /etc/systemd/system/"
cp -n "${SCRIPT_DIR}/systemd/imdf-"*.service        /etc/systemd/system/ || true
cp -n "${SCRIPT_DIR}/systemd/postgresql.service"   /etc/systemd/system/ || true
cp -n "${SCRIPT_DIR}/systemd/redis-server.service" /etc/systemd/system/ || true
cp -n "${SCRIPT_DIR}/systemd/minio.service"        /etc/systemd/system/ || true
cp -n "${SCRIPT_DIR}/systemd/prometheus.service"   /etc/systemd/system/ || true
cp -n "${SCRIPT_DIR}/systemd/grafana-server.service" /etc/systemd/system/ || true
cp -n "${SCRIPT_DIR}/systemd/jaeger.service"       /etc/systemd/system/ || true
cp -n "${SCRIPT_DIR}/systemd/loki.service"         /etc/systemd/system/ || true
cp -n "${SCRIPT_DIR}/systemd/promtail.service"     /etc/systemd/system/ || true
cp -n "${SCRIPT_DIR}/systemd/alertmanager.service" /etc/systemd/system/ || true
systemctl daemon-reload

# ── 7. configs (postgres / redis / prometheus / nginx / loki / jaeger) ─
log "staging config files"
mkdir -p /etc/prometheus /etc/grafana/provisioning/{datasources,dashboards} \
         /etc/loki /etc/promtail /etc/jaeger /etc/alertmanager
cp -n "${SCRIPT_DIR}/configs/postgresql.conf" /etc/postgresql/15/main/postgresql.conf.bare_metal || true
cp -n "${SCRIPT_DIR}/configs/pg_hba.conf"     /etc/postgresql/15/main/pg_hba.conf.bare_metal    || true
cp -n "${SCRIPT_DIR}/configs/redis.conf"      /etc/redis/redis.conf.bare_metal                  || true
cp -n "${SCRIPT_DIR}/configs/prometheus.yml"  /etc/prometheus/prometheus.yml                    || true
cp -n "${SCRIPT_DIR}/configs/alertmanager.yml"/etc/alertmanager/alertmanager.yml                 || true
cp -n "${SCRIPT_DIR}/configs/grafana-datasources.yml" /etc/grafana/provisioning/datasources/prometheus.yml || true
cp -n "${SCRIPT_DIR}/configs/grafana-dashboards.yml"  /etc/grafana/provisioning/dashboards/imdf.yml      || true
cp -n "${SCRIPT_DIR}/configs/loki-config.yaml"  /etc/loki/config.yaml   || true
cp -n "${SCRIPT_DIR}/configs/jaeger-config.yaml"/etc/jaeger/config.yaml || true
cp -n "${SCRIPT_DIR}/configs/minio.env"         /etc/default/minio      || true
cp -n "${SCRIPT_DIR}/configs/nginx-imdf.conf"   /etc/nginx/sites-available/imdf || true
chown -R prometheus:prometheus /etc/prometheus || true
chown -R grafana:grafana      /etc/grafana    || true

# ── 8. enable / start ───────────────────────────────────────────────────
if [[ $NO_ENABLE -eq 0 ]]; then
  log "enabling services (no auto-start yet — edit imdf.env first)"
  for svc in postgresql redis-server minio \
             prometheus grafana-server alertmanager \
             jaeger loki promtail \
             imdf-gateway imdf-user imdf-asset imdf-annotation imdf-cleaning \
             imdf-scoring imdf-dataset imdf-evaluation imdf-agent \
             imdf-workflow imdf-notification imdf-search imdf-collection \
             imdf-celery imdf-celery-beat; do
    systemctl enable "${svc}.service" 2>/dev/null || true
  done
  log "run 'sudo deploy/bare_metal/scripts/start-all.sh' to start everything"
fi

log "DONE"
log "next steps:"
log "  1. sudo vim ${ENV_DIR}/imdf.env          # set CHANGE_ME_* secrets"
log "  2. sudo -u postgres createuser imdf_app  # if not yet created"
log "  3. sudo deploy/bare_metal/scripts/start-all.sh"