#!/usr/bin/env bash
# ============================================================================
# healthcheck.sh — periodic health probe (called by cron or systemd timer)
# ----------------------------------------------------------------------------
# Writes to /var/log/imdf-healthcheck.log; exit non-zero on any failure.
# Cron example:
#   * * * * * /opt/nanobot-factory/deploy/bare_metal/scripts/healthcheck.sh \
#       || systemctl restart imdf-gateway
# ============================================================================
set -uo pipefail

LOG="/var/log/imdf-healthcheck.log"
GATEWAY_URL="${IMDF_GATEWAY_URL:-http://127.0.0.1:8000}"
TIMEOUT="${HEALTHCHECK_TIMEOUT:-5}"

ts()   { date +%Y-%m-%dT%H:%M:%S%z; }
ok()   { printf '%s OK  %s\n' "$(ts)" "$*"; }
fail() { printf '%s FAIL %s\n' "$(ts)" "$*"; FAILED=1; }

FAILED=0

# ── Gateway health ──────────────────────────────────────────────────────
GW_RESP=$(curl -fsS --max-time "${TIMEOUT}" "${GATEWAY_URL}/api/queue/health" 2>/dev/null) || {
  fail "gateway ${GATEWAY_URL}/api/queue/health unreachable"
}
if [[ -n "${GW_RESP}" ]]; then
  STATUS=$(echo "${GW_RESP}" | grep -o '"status":"[^"]*"' | head -1 | cut -d'"' -f4)
  if [[ "${STATUS}" == "ok" || "${STATUS}" == "degraded" ]]; then
    ok "gateway status=${STATUS}"
  else
    fail "gateway status=${STATUS}"
  fi
fi

# ── /readyz (DB + Redis check) ──────────────────────────────────────────
RD_RESP=$(curl -fsS --max-time "${TIMEOUT}" "${GATEWAY_URL}/readyz" 2>/dev/null) || {
  fail "gateway /readyz unreachable"
}
[[ -n "${RD_RESP}" ]] && ok "readyz: ${RD_RESP}" || true

# ── /metrics endpoint reachable ─────────────────────────────────────────
curl -fsS --max-time "${TIMEOUT}" "${GATEWAY_URL}/metrics" >/dev/null 2>&1 \
  && ok "metrics endpoint reachable" \
  || fail "metrics endpoint unreachable"

# ── Per-service health (12 svc) ─────────────────────────────────────────
for port in 8001 8002 8003 8004 8005 8006 8007 8008 8009 8010 8011 8012; do
  curl -fsS --max-time 2 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1 \
    && ok "service :${port} healthy" \
    || fail "service :${port} unhealthy"
done

# ── Celery worker ───────────────────────────────────────────────────────
CELERY_ACTIVE=$(systemctl is-active imdf-celery.service || echo "inactive")
if [[ "${CELERY_ACTIVE}" == "active" ]]; then
  ok "celery worker ${CELERY_ACTIVE}"
else
  fail "celery worker ${CELERY_ACTIVE}"
fi

CELERY_BEAT_ACTIVE=$(systemctl is-active imdf-celery-beat.service || echo "inactive")
if [[ "${CELERY_BEAT_ACTIVE}" == "active" ]]; then
  ok "celery beat ${CELERY_BEAT_ACTIVE}"
else
  fail "celery beat ${CELERY_BEAT_ACTIVE}"
fi

# ── Log write ───────────────────────────────────────────────────────────
if [[ ${FAILED} -ne 0 ]]; then
  echo "$(ts) END  FAILED (see above)" >> "${LOG}"
  exit 1
fi
echo "$(ts) END  OK" >> "${LOG}"
exit 0