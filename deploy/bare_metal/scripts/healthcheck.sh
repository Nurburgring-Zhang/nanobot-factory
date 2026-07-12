#!/usr/bin/env bash
# ============================================================================
# healthcheck.sh — periodic health probe
# ----------------------------------------------------------------------------
# P22-P2b: Two modes of operation.
#
#   1. One-shot (default, used by cron):
#        healthcheck.sh                       # exit 0 on healthy, 1 otherwise
#        healthcheck.sh || systemctl restart imdf-gateway
#
#   2. Long-running watchdog (used by imdf-monitor.service):
#        healthcheck.sh --watch --interval=30 --restart-target=imdf-cluster.target
#
# Mode 2 loops forever, runs the same checks, and on any failure runs
# `systemctl restart <target>`. The cluster target's own Restart=always
# plus the watchdog's restart-on-failure form a self-healing stack:
# a single service crash → systemd restarts it; a cluster-wide crash
# (e.g. deadlock) → the watchdog restarts the whole target.
#
# Writes /var/log/imdf/healthcheck.log (one-shot) or /var/log/imdf/monitor.log
# (watchdog) so a crash-loop can be triaged after the fact.
# ============================================================================
set -uo pipefail

LOG_FILE="/var/log/imdf/healthcheck.log"
GATEWAY_URL="${IMDF_GATEWAY_URL:-http://127.0.0.1:8000}"
TIMEOUT="${HEALTHCHECK_TIMEOUT:-5}"
WATCH_INTERVAL=30
RESTART_TARGET=""

# ── arg parsing ────────────────────────────────────────────────────────
WATCH_MODE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --watch) WATCH_MODE=1; shift ;;
    --interval) WATCH_INTERVAL="$2"; shift 2 ;;
    --restart-target) RESTART_TARGET="$2"; shift 2 ;;
    --log) LOG_FILE="$2"; shift 2 ;;
    --help|-h)
      sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "$(dirname "${LOG_FILE}")" 2>/dev/null || true

ts()   { date +%Y-%m-%dT%H:%M:%S%z; }
ok()   { printf '%s OK   %s\n' "$(ts)" "$*"; }
fail() { printf '%s FAIL %s\n' "$(ts)" "$*"; FAILED=1; }

# ── the actual health check body (returns 0 on healthy, 1 otherwise) ──
run_healthcheck() {
  FAILED=0

  # Gateway
  GW_RESP=$(curl -fsS --max-time "${TIMEOUT}" "${GATEWAY_URL}/api/queue/health" 2>/dev/null) || {
    fail "gateway ${GATEWAY_URL}/api/queue/health unreachable"
  }
  if [[ -n "${GW_RESP:-}" ]]; then
    STATUS=$(echo "${GW_RESP}" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4 || true)
    if [[ "${STATUS}" == "ok" || "${STATUS}" == "degraded" ]]; then
      ok "gateway status=${STATUS}"
    else
      fail "gateway status=${STATUS:-<empty>}"
    fi
  fi

  # /readyz
  RD_RESP=$(curl -fsS --max-time "${TIMEOUT}" "${GATEWAY_URL}/readyz" 2>/dev/null) || {
    fail "gateway /readyz unreachable"
  }
  [[ -n "${RD_RESP:-}" ]] && ok "readyz: ${RD_RESP}" || true

  # /metrics
  if curl -fsS --max-time "${TIMEOUT}" "${GATEWAY_URL}/metrics" >/dev/null 2>&1; then
    ok "metrics endpoint reachable"
  else
    fail "metrics endpoint unreachable"
  fi

  # Per-service
  for port in 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010 8011 8012; do
    if curl -fsS --max-time 2 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
      ok "service :${port} healthy"
    else
      fail "service :${port} unhealthy"
    fi
  done

  # Celery
  if systemctl is-active imdf-celery.service >/dev/null 2>&1; then
    ok "celery worker active"
  else
    fail "celery worker inactive"
  fi
  if systemctl is-active imdf-celery-beat.service >/dev/null 2>&1; then
    ok "celery beat active"
  else
    fail "celery beat inactive"
  fi

  # Storage
  for svc in postgresql redis-server minio; do
    if systemctl is-active "${svc}.service" >/dev/null 2>&1; then
      ok "storage ${svc} active"
    else
      fail "storage ${svc} inactive"
    fi
  done

  return ${FAILED}
}

# ── one-shot mode (default) ────────────────────────────────────────────
if [[ ${WATCH_MODE} -eq 0 ]]; then
  if run_healthcheck; then
    printf '%s END  OK\n' "$(ts)" >> "${LOG_FILE}"
    exit 0
  else
    printf '%s END  FAILED\n' "$(ts)" >> "${LOG_FILE}"
    exit 1
  fi
fi

# ── watch mode (long-running watchdog) ────────────────────────────────
printf '%s START  watchdog mode interval=%ds target=%s\n' \
  "$(ts)" "${WATCH_INTERVAL}" "${RESTART_TARGET:-<none>}" >> "${LOG_FILE}"

# HUP-friendly: re-read LOG_FILE on SIGHUP (for log rotation)
trap 'echo "$(ts) HUP received, continuing" >> "${LOG_FILE}"' HUP
# TERM/INT: clean exit
trap 'echo "$(ts) STOP watchdog" >> "${LOG_FILE}"; exit 0' TERM INT

CONSECUTIVE_FAILURES=0
while true; do
  if run_healthcheck; then
    if [[ ${CONSECUTIVE_FAILURES} -gt 0 ]]; then
      printf '%s RECOVER  after %d failed cycle(s)\n' \
        "$(ts)" "${CONSECUTIVE_FAILURES}" >> "${LOG_FILE}"
      CONSECUTIVE_FAILURES=0
    fi
  else
    CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
    printf '%s FAIL cycle=%d\n' "$(ts)" "${CONSECUTIVE_FAILURES}" >> "${LOG_FILE}"

    # 3-strike rule: only restart the cluster target after 3 consecutive
    # failures (30s × 3 = 90s of bad health). Avoids thrashing on
    # transient blips.
    if [[ ${CONSECUTIVE_FAILURES} -ge 3 && -n "${RESTART_TARGET}" ]]; then
      printf '%s RESTART  target=%s (after %d failures)\n' \
        "$(ts)" "${RESTART_TARGET}" "${CONSECUTIVE_FAILURES}" >> "${LOG_FILE}"
      if systemctl restart "${RESTART_TARGET}"; then
        printf '%s RESTART  ok\n' "$(ts)" >> "${LOG_FILE}"
        CONSECUTIVE_FAILURES=0
      else
        printf '%s RESTART  FAILED — manual intervention required\n' \
          "$(ts)" >> "${LOG_FILE}"
      fi
    fi
  fi
  sleep "${WATCH_INTERVAL}"
done
