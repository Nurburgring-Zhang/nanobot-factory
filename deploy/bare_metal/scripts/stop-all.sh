#!/usr/bin/env bash
# ============================================================================
# stop-all.sh — stop every IMDF service (reverse dependency order)
# ============================================================================
set -euo pipefail

ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
fail() { printf '  \033[31m✘\033[0m %s\n' "$*"; exit 1; }

if [[ $EUID -ne 0 ]]; then
  fail "must run as root (sudo $0)"
fi

APP=(
  imdf-celery-beat.service
  imdf-celery.service
  imdf-collection.service imdf-search.service imdf-notification.service
  imdf-workflow.service imdf-agent.service imdf-evaluation.service
  imdf-dataset.service imdf-scoring.service imdf-cleaning.service
  imdf-annotation.service imdf-asset.service imdf-user.service
  imdf-gateway.service
)
OBSERVABILITY=(
  promtail.service loki.service jaeger.service grafana-server.service
  alertmanager.service prometheus.service
)
DEPS=(
  minio.service redis-server.service postgresql.service
)

stop_tier() {
  local tier_name="$1"; shift
  printf '\n\033[1m── %s ──────────────────────────────────────────\033[0m\n' "${tier_name}"
  for svc in "$@"; do
    if systemctl list-unit-files "${svc}" >/dev/null 2>&1 && systemctl is-active --quiet "${svc}"; then
      systemctl stop "${svc}" || fail "failed to stop ${svc}"
      ok "${svc} stopped"
    fi
  done
}

stop_tier "Application"     "${APP[@]}"
stop_tier "Observability"   "${OBSERVABILITY[@]}"
stop_tier "Data layer"      "${DEPS[@]}"

printf '\n\033[33mAll IMDF services stopped.\033[0m\n'