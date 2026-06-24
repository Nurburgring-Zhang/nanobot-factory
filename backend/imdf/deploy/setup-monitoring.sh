#!/bin/bash
# ============================================================================
# IMDF 监控栈一键部署
# ============================================================================
# Usage: sudo bash deploy/setup-monitoring.sh
# Installs: Prometheus + Node Exporter + Alertmanager + Grafana
# Configures: IMDF metrics scraping + alerts + dashboard
# ============================================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[+]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; }
info() { echo -e "${BLUE}[i]${NC} $1"; }

# ── Check root ──────────────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    err "请使用 sudo 运行此脚本: sudo bash $0"
    exit 1
fi

# ── Detect deploy directory ─────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEPLOY_DIR="$SCRIPT_DIR"

log "IMDF 监控栈部署"
log "项目根目录: $PROJECT_ROOT"
log "部署配置目录: $DEPLOY_DIR"
echo ""

# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Install packages
# ═══════════════════════════════════════════════════════════════════════════
log "Step 1/6: 安装监控组件..."

if ! command -v prometheus &>/dev/null; then
    log "  安装 Prometheus..."
    apt-get update -qq
    apt-get install -y -qq prometheus prometheus-node-exporter prometheus-alertmanager
else
    info "  Prometheus 已安装: $(prometheus --version 2>&1 | head -1)"
fi

if ! command -v grafana-server &>/dev/null; then
    log "  安装 Grafana..."
    apt-get install -y -qq wget gnupg software-properties-common
    wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key
    echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" \
        | tee /etc/apt/sources.list.d/grafana.list
    apt-get update -qq
    apt-get install -y -qq grafana
else
    info "  Grafana 已安装: $(grafana-server -v 2>&1 | head -1 || echo 'ok')"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Configure Prometheus
# ═══════════════════════════════════════════════════════════════════════════
log "Step 2/6: 配置 Prometheus..."

# Copy main config
if [ -f "$DEPLOY_DIR/prometheus.yml" ]; then
    cp "$DEPLOY_DIR/prometheus.yml" /etc/prometheus/prometheus.yml
    log "  prometheus.yml → /etc/prometheus/prometheus.yml"
else
    warn "  $DEPLOY_DIR/prometheus.yml 不存在 — 请手动创建"
fi

# Copy alert rules
mkdir -p /etc/prometheus/rules
if [ -f "$DEPLOY_DIR/prometheus-alerts.yml" ]; then
    cp "$DEPLOY_DIR/prometheus-alerts.yml" /etc/prometheus/rules/prometheus-alerts.yml
    log "  prometheus-alerts.yml → /etc/prometheus/rules/"
else
    warn "  $DEPLOY_DIR/prometheus-alerts.yml 不存在"
fi

# Validate config
if promtool check config /etc/prometheus/prometheus.yml &>/dev/null; then
    log "  Prometheus 配置验证通过"
else
    warn "  Prometheus 配置验证失败 — 请检查"
    promtool check config /etc/prometheus/prometheus.yml 2>&1 || true
fi

# Set ownership and permissions
chown -R prometheus:prometheus /etc/prometheus /var/lib/prometheus 2>/dev/null || true

# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Configure Alertmanager
# ═══════════════════════════════════════════════════════════════════════════
log "Step 3/6: 配置 Alertmanager..."

if [ -f "$DEPLOY_DIR/alertmanager.yml" ]; then
    cp "$DEPLOY_DIR/alertmanager.yml" /etc/prometheus/alertmanager.yml
    log "  alertmanager.yml → /etc/prometheus/alertmanager.yml"
    chown alertmanager:alertmanager /etc/prometheus/alertmanager.yml 2>/dev/null || true
else
    warn "  $DEPLOY_DIR/alertmanager.yml 不存在 — Alertmanager 将使用默认配置"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Start services
# ═══════════════════════════════════════════════════════════════════════════
log "Step 4/6: 启动服务..."

# Reload systemd
systemctl daemon-reload

# Start & enable each service
SERVICES=(
    "prometheus"
    "prometheus-node-exporter"
    "prometheus-alertmanager"
    "grafana-server"
)

for svc in "${SERVICES[@]}"; do
    if systemctl is-active --quiet "$svc"; then
        systemctl restart "$svc"
        info "  $svc: 已重启"
    else
        systemctl enable --now "$svc"
        log "  $svc: 已启动并设为开机自启"
    fi
done

# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Verify all services
# ═══════════════════════════════════════════════════════════════════════════
log "Step 5/6: 验证服务状态..."
echo ""
sleep 3  # 等所有服务启动

ALL_OK=true

check_service() {
    local svc=$1 port=$2 url=$3
    if systemctl is-active --quiet "$svc"; then
        printf "  ${GREEN}[✓]${NC} %-30s " "$svc"
    else
        printf "  ${RED}[✗]${NC} %-30s " "$svc"
        ALL_OK=false
    fi

    if [ -n "${port:-}" ] && command -v curl &>/dev/null; then
        if curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:$port${url:-/}" 2>/dev/null | grep -q "200\|302\|303\|301\|401"; then
            echo -e "${GREEN}可达 (:$port${url:-/})${NC}"
        else
            echo -e "${YELLOW}端口响应异常 (:$port${url:-/})${NC}"
        fi
    else
        echo ""
    fi
}

check_service "prometheus"          9090 "/api/v1/status/config"
check_service "prometheus-node-exporter" 9100 "/metrics"
check_service "prometheus-alertmanager"  9093 "/-/healthy"
check_service "grafana-server"        3000 "/api/health"

# Also check IMDF metrics endpoint
if curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:8765/metrics" 2>/dev/null | grep -q "200"; then
    echo -e "  ${GREEN}[✓]${NC} IMDF /metrics                 ${GREEN}可达 (localhost:8765/metrics)${NC}"
else
    echo -e "  ${YELLOW}[!]${NC} IMDF /metrics                 ${YELLOW}不可达 — 请确保IMDF服务在运行${NC}"
fi

# ═══════════════════════════════════════════════════════════════════════════
# Step 6: Summary
# ═══════════════════════════════════════════════════════════════════════════
log "Step 6/6: 部署完成!"

echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              IMDF 监控栈部署完成                            ║${NC}"
echo -e "${BLUE}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  Prometheus:    http://localhost:9090                    ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}  Grafana:       http://localhost:3000 (admin/admin)     ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}  Alertmanager:  http://localhost:9093                    ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}  Node Exporter: http://localhost:9100/metrics            ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}  IMDF Metrics:  http://localhost:8765/metrics            ${BLUE}║${NC}"
echo -e "${BLUE}╠══════════════════════════════════════════════════════════════╣${NC}"
echo -e "${BLUE}║${NC}  Dashboard: 部署后在Grafana中导入                         ${BLUE}║${NC}"
echo -e "${BLUE}║${NC}    $DEPLOY_DIR/grafana-dashboard.json                     ${BLUE}║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "下一步:"
echo "  1. 登录 Grafana: http://localhost:3000 (admin/admin)"
echo "  2. Import → Upload → $DEPLOY_DIR/grafana-dashboard.json"
echo "  3. 检查 Prometheus targets: http://localhost:9090/targets"
echo ""
echo "或通过API导入仪表盘:"
echo "  curl -X POST http://admin:NEW_PASSWORD@localhost:3000/api/dashboards/db \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d @$DEPLOY_DIR/grafana-dashboard.json"

if [ "$ALL_OK" = true ]; then
    echo -e "\n${GREEN}所有服务运行正常 ✅${NC}"
else
    echo -e "\n${YELLOW}部分服务未正常运行 — 请检查 journalctl -xe${NC}"
fi
