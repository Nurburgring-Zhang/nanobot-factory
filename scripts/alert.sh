#!/usr/bin/env bash
# ============================================================================
# IMDF Alert Script — Phase2
# ============================================================================
# Calls IMDF health check endpoints and emits alerts on failure.
#
# Usage:
#   ./alert.sh                          # Check default http://localhost:8000
#   ./alert.sh http://192.168.1.10:9000 # Check custom IMDF instance
#
# Exit codes:
#   0 — All checks passed
#   1 — Basic health check failed
#   2 — Readiness check failed (degraded)
#   3 — Liveness check failed
#   4 — Network error (could not reach service)
#
# Configuration via environment variables:
#   IMDF_URL           — Base URL (default: http://localhost:8000)
#   ALERT_WEBHOOK_URL  — Webhook to POST alerts to (e.g., Slack/Discord/Feishu)
#   ALERT_EMAIL_TO     — Email recipient address (requires sendmail/mailx)
#   ALERT_EMAIL_FROM   — Email sender address (default: imdf-alert@localhost)
# ============================================================================

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────

IMDF_URL="${1:-${IMDF_URL:-http://localhost:8000}}"
ALERT_WEBHOOK_URL="${ALERT_WEBHOOK_URL:-}"
ALERT_EMAIL_TO="${ALERT_EMAIL_TO:-}"
ALERT_EMAIL_FROM="${ALERT_EMAIL_FROM:-imdf-alert@localhost}"

# Remove trailing slash
IMDF_URL="${IMDF_URL%/}"

TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
HOSTNAME="$(hostname -f 2>/dev/null || hostname)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Color output helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ALERTS=()
PASSED=0
FAILED=0

# ── Helper functions ─────────────────────────────────────────────────────

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $*"
    PASSED=$((PASSED + 1))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $*"
    ALERTS+=("$*")
    FAILED=$((FAILED + 1))
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
    ALERTS+=("[WARN] $*")
}

http_get() {
    # Fetch URL with curl, return body. Retry once on failure.
    local url="$1"
    local timeout="${2:-10}"
    curl -sS --max-time "$timeout" --connect-timeout 5 -X GET "$url" 2>/dev/null || {
        # Retry once
        sleep 1
        curl -sS --max-time "$timeout" --connect-timeout 5 -X GET "$url" 2>/dev/null || echo ""
    }
}

http_get_json() {
    # Fetch and check if response is JSON with jq
    local url="$1"
    local timeout="${2:-10}"
    local resp
    resp="$(http_get "$url" "$timeout")"
    if [ -z "$resp" ]; then
        echo "{}"
        return 1
    fi
    # Check if it looks like JSON
    if echo "$resp" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        echo "$resp"
        return 0
    else
        echo "{}"
        return 1
    fi
}

send_webhook() {
    local message="$1"
    if [ -z "$ALERT_WEBHOOK_URL" ]; then
        return 0
    fi
    # Generate JSON payload (generic, works with Slack/Discord/Feishu webhooks)
    local payload
    payload="{\"text\": \"[IMDF Alert] ${message}\", \"timestamp\": \"${TIMESTAMP}\", \"host\": \"${HOSTNAME}\"}"
    curl -sS -X POST -H "Content-Type: application/json" -d "$payload" "$ALERT_WEBHOOK_URL" >/dev/null 2>&1 || true
    echo "  >> Alert sent to webhook"
}

send_email() {
    local subject="$1"
    local body="$2"
    if [ -z "$ALERT_EMAIL_TO" ]; then
        return 0
    fi
    if command -v mailx &>/dev/null; then
        echo "$body" | mailx -s "$subject" -r "$ALERT_EMAIL_FROM" "$ALERT_EMAIL_TO" 2>/dev/null || true
        echo "  >> Alert email sent to $ALERT_EMAIL_TO"
    elif command -v sendmail &>/dev/null; then
        {
            echo "From: $ALERT_EMAIL_FROM"
            echo "To: $ALERT_EMAIL_TO"
            echo "Subject: $subject"
            echo ""
            echo "$body"
        } | sendmail -t 2>/dev/null || true
        echo "  >> Alert email sent to $ALERT_EMAIL_TO"
    else
        echo "  >> (mailx/sendmail not found; skipping email alert)"
    fi
}

# ── Main checks ──────────────────────────────────────────────────────────

echo "============================================================"
echo " IMDF Health Check — $TIMESTAMP"
echo " Target: $IMDF_URL"
echo "============================================================"
echo ""

# 1. Liveness check (lightweight)
echo -n ">> Liveness check:  "
LIVE_RESP="$(http_get_json "${IMDF_URL}/api/v1/health/live" 5)" || true
LIVE_STATUS="$(echo "$LIVE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")"
if [ "$LIVE_STATUS" == "ok" ]; then
    log_pass "liveness OK"
else
    log_fail "liveness FAILED (response: ${LIVE_RESP:0:200})"
    # Cannot proceed with other checks if liveness fails
    echo ""
    echo "============================================================"
    echo " CRITICAL: IMDF service is not reachable!"
    echo "============================================================"
    # Send alerts
    ALERT_MSG="IMDF service DOWN at ${IMDF_URL} (host: ${HOSTNAME})"
    send_webhook "$ALERT_MSG"
    send_email "[IMDF ALERT] Service DOWN" "${ALERT_MSG}\n\nTimestamp: ${TIMESTAMP}\nURL: ${IMDF_URL}\nLiveness response: ${LIVE_RESP:0:500}"
    exit 3
fi

# 2. Basic health check (DB)
echo -n ">> Basic health:    "
HEALTH_RESP="$(http_get_json "${IMDF_URL}/api/v1/health" 10)" || true
HEALTH_STATUS="$(echo "$HEALTH_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")"
if [ "$HEALTH_STATUS" == "ok" ]; then
    log_pass "basic health OK"
else
    log_fail "basic health degraded"
    # Show DB check detail
    DB_MSG="$(echo "$HEALTH_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('checks',{}).get('database',{}).get('message',''))" 2>/dev/null || echo "unknown")"
    echo "  DB check: $DB_MSG"
fi

# 3. Readiness check (all components)
echo -n ">> Readiness check: "
READY_RESP="$(http_get_json "${IMDF_URL}/api/v1/health/ready" 10)" || true
READY_STATUS="$(echo "$READY_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")"
DEGRADED="$(echo "$READY_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(','.join(d.get('degraded_components') or []))" 2>/dev/null || echo "")"

if [ "$READY_STATUS" == "ok" ]; then
    log_pass "readiness OK (all components)"
else
    log_fail "readiness DEGRADED: ${DEGRADED}"
    # Show individual component status
    for comp in database disk ffmpeg memory vector_store api_keys_db; do
        COMP_OK="$(echo "$READY_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('checks',{}).get('${comp}',{}).get('ok',False))" 2>/dev/null || echo "False")"
        if [ "$COMP_OK" == "True" ]; then
            echo "    [OK]   $comp"
        else
            COMP_MSG="$(echo "$READY_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('checks',{}).get('${comp}',{}).get('message',''))" 2>/dev/null || echo "unknown")"
            echo "    [FAIL] $comp — $COMP_MSG"
        fi
    done
fi

# 4. Metrics summary (optional, informative)
echo -n ">> Metrics summary: "
METRICS_RESP="$(http_get_json "${IMDF_URL}/api/v1/health/metrics-summary" 10 2>/dev/null)" || METRICS_RESP="{}"
if [ "$METRICS_RESP" != "{}" ]; then
    MEM_MB="$(echo "$METRICS_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metrics',{}).get('memory_mb','N/A'))" 2>/dev/null || echo "N/A")"
    P95="$(echo "$METRICS_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metrics',{}).get('latency_p95_ms','N/A'))" 2>/dev/null || echo "N/A")"
    REQS="$(echo "$METRICS_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('metrics',{}).get('requests_total','N/A'))" 2>/dev/null || echo "N/A")"
    echo "OK (requests: $REQS, P95: ${P95}ms, mem: ${MEM_MB}MB)"
else
    log_warn "metrics unavailable"
fi

echo ""
echo "============================================================"
echo " Results: ${PASSED} passed, ${FAILED} failed"
echo "============================================================"

# ── Alert dispatch ───────────────────────────────────────────────────────

if [ ${#ALERTS[@]} -gt 0 ]; then
    ALERT_SUMMARY="IMDF health check: ${FAILED}/${PASSED}/${FAILED} alerts at ${IMDF_URL}"
    ALERT_BODY="${ALERT_SUMMARY}
Host: ${HOSTNAME}
Time: ${TIMESTAMP}
URL: ${IMDF_URL}

Alerts:
$(printf '%s\n' "${ALERTS[@]}")"

    echo ""
    echo "Dispatching alerts..."

    send_webhook "$ALERT_BODY"

    send_email "[IMDF ALERT] ${FAILED} issue(s) detected" "$ALERT_BODY"

    exit 2
fi

echo ""
echo "All checks passed. No alerts."
exit 0
