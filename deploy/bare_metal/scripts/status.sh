#!/usr/bin/env bash
# ============================================================================
# status.sh — show tabular status for every IMDF + dependency unit
# ============================================================================
set -euo pipefail

ok()   { printf '  \033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
  echo "(run with sudo for full output)"
fi

UNITS=(
  postgresql.service
  redis-server.service
  minio.service
  prometheus.service
  alertmanager.service
  grafana-server.service
  jaeger.service
  loki.service
  promtail.service
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

printf '\033[1m%-30s  %-12s  %-9s  %-9s  %s\033[0m\n' "UNIT" "STATE" "ENABLED" "UPTIME" "MEM"
printf '%.0s-' {1..80}; printf '\n'

total_active=0
total_failed=0
total_inactive=0

for svc in "${UNITS[@]}"; do
  if ! systemctl list-unit-files "${svc}" >/dev/null 2>&1; then
    printf '%-30s  \033[33m%-12s\033[0m\n' "${svc}" "not-installed"
    continue
  fi
  state=$(systemctl is-active "${svc}" || true)
  enabled=$(systemctl is-enabled "${svc}" 2>/dev/null | head -1 || echo "disabled")
  uptime="-"
  mem="-"
  case "${state}" in
    active)
      total_active=$((total_active+1))
      # ActiveEnterTimestamp -> seconds since boot
      since=$(systemctl show "${svc}" -p ActiveEnterTimestamp --value 2>/dev/null || echo "")
      if [[ -n "${since}" && "${since}" != "n/a" ]]; then
        sec=$(( $(date +%s) - $(date -d "${since}" +%s 2>/dev/null || echo 0) ))
        uptime="${sec}s"
      fi
      # Main PID memory
      pid=$(systemctl show "${svc}" -p MainPID --value)
      if [[ "${pid}" =~ ^[0-9]+$ ]] && [[ "${pid}" -gt 0 ]] && [[ -r "/proc/${pid}/status" ]]; then
        rss=$(awk '/^VmRSS:/ {print $2}' "/proc/${pid}/status" 2>/dev/null || echo 0)
        if [[ "${rss}" -gt 0 ]]; then
          mem="$((rss / 1024))MB"
        fi
      fi
      state_color="\033[32m"
      ;;
    failed)
      total_failed=$((total_failed+1))
      state_color="\033[31m"
      ;;
    *)
      total_inactive=$((total_inactive+1))
      state_color="\033[33m"
      ;;
  esac
  printf '%-30s  '"${state_color}"'%-12s\033[0m  %-9s  %-9s  %s\n' \
    "${svc}" "${state}" "${enabled}" "${uptime}" "${mem}"
done

printf '\n'
printf '\033[1mSummary\033[0m: '
printf '\033[32m%d active\033[0m, ' "${total_active}"
printf '\033[33m%d inactive\033[0m, ' "${total_inactive}"
if [[ "${total_failed}" -gt 0 ]]; then
  printf '\033[31m%d failed\033[0m\n' "${total_failed}"
else
  printf '0 failed\n'
fi

# Quick smoke test
printf '\n\033[1mSmoke tests\033[0m:\n'
if curl -fsS --max-time 3 http://127.0.0.1:8000/api/queue/health >/dev/null 2>&1; then
  ok "gateway /api/queue/health"
else
  warn "gateway unreachable"
fi
if curl -fsS --max-time 3 http://127.0.0.1:9090/-/ready >/dev/null 2>&1; then
  ok "prometheus ready"
else
  warn "prometheus not ready"
fi
if redis-cli ping >/dev/null 2>&1; then
  ok "redis PONG"
else
  warn "redis not reachable"
fi