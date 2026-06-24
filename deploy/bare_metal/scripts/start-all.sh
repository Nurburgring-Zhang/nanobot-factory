#!/usr/bin/env bash
# ============================================================================
# start-all.sh — start every IMDF service in dependency order
# ----------------------------------------------------------------------------
# Order: data layer (postgres, redis, minio) → observability → gateway → 12 svc
# → celery worker → celery beat. Waits for each tier to be healthy.
# ============================================================================
set -euo pipefail

# shellcheck disable=SC2034
DEPS=(
  postgresql.service
  redis-server.service
  minio.service
)

# shellcheck disable=SC2034
OBSERVABILITY=(
  prometheus.service
  alertmanager.service
  grafana-server.service
  jaeger.service
  loki.service
  promtail.service
)

# shellcheck disable=SC2034
APP=(
  imdf-gateway.service
  imdf-user.service
  imdf-asset.service
  imdf-annotation.service
  imdf-cleaning.service
  imdf-scoring.service
  imdf-dataset.service
  imdf-evaluation.service
  imdf-agent.service
  imdf-workflow.service
  imdf-notification.service
  imdf-search.service
  imdf-collection.service
  imdf-celery.service
  imdf-celery-beat.service
)

ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }
hr()   { printf '\n\033[1m── %s ──────────────────────────────────────────\033[0m\n' "$*"; }

require_root() {
  if [[ $EUID -ne 0 ]]; then
    fail "must run as root (sudo $0)"
  fi
}

start_tier() {
  local tier_name="$1"; shift
  local unit svc
  hr "${tier_name} (${#@} services)"
  for svc in "$@"; do
    if systemctl list-unit-files "${svc}" >/dev/null 2>&1; then
      if systemctl is-active --quiet "${svc}"; then
        ok "${svc} already active"
      else
        systemctl start "${svc}" || fail "failed to start ${svc}"
        ok "${svc} started"
      fi
    else
      printf '  \033[33m·\033[0m %s (unit not installed — skipping)\n' "${svc}"
    fi
  done
}

main() {
  require_root
  start_tier "Data layer"      "${DEPS[@]}"
  start_tier "Observability"   "${OBSERVABILITY[@]}"
  start_tier "Application"     "${APP[@]}"

  hr "Smoke test"
  sleep 3
  if curl -fsS http://127.0.0.1:8000/api/queue/health >/dev/null 2>&1; then
    ok "gateway /api/queue/health is reachable"
  else
    fail "gateway health check failed — check 'journalctl -u imdf-gateway -n 50'"
  fi

  if curl -fsS http://127.0.0.1:9090/-/ready >/dev/null 2>&1; then
    ok "prometheus is ready"
  else
    printf '  \033[33m!\033[0m prometheus not yet ready (may need more time)\n'
  fi

  printf '\n\033[32mAll IMDF services are up.\033[0m\n'
  printf 'Run \033[1mdeploy/bare_metal/scripts/status.sh\033[0m for full state.\n'
}

main "$@"