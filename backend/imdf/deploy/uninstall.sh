#!/usr/bin/env bash
# ============================================================================
# IMDF Deployment Uninstaller
# ============================================================================
# Usage:
#   sudo bash deploy/uninstall.sh
#
# What it does:
#   1. Stop IMDF systemd service
#   2. Disable systemd service
#   3. Remove service unit file
#   4. Reload systemd
#   5. Optionally clean data/logs
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="imdf"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# ── Colors ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Must be root ────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    error "This script must be run as root. Use: sudo bash deploy/uninstall.sh"
    exit 1
fi

echo ""
echo "========================================="
echo "  IMDF Deployment Uninstaller"
echo "  Project: $PROJECT_ROOT"
echo "========================================="
echo ""

# ── 1. Stop service ─────────────────────────────────────────────────────────
info "Step 1/4: Stopping IMDF service..."
if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl stop "$SERVICE_NAME"
    success "Service stopped"
else
    info "Service was not running"
fi

# ── 2. Disable service ──────────────────────────────────────────────────────
info "Step 2/4: Disabling IMDF service..."
if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    systemctl disable "$SERVICE_NAME" 2>&1 | sed 's/^/  /'
    success "Service disabled"
else
    info "Service was not enabled"
fi

# ── 3. Remove service file ──────────────────────────────────────────────────
info "Step 3/4: Removing systemd unit file..."
if [[ -f "$SERVICE_FILE" ]]; then
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
    success "Removed $SERVICE_FILE"
else
    info "No service file found at $SERVICE_FILE — skipping"
fi

# Kill any remaining processes on port 8765
if lsof -ti:8765 &>/dev/null; then
    info "Killing leftover processes on port 8765..."
    lsof -ti:8765 | xargs -r kill -9 2>/dev/null || true
    success "Leftover processes terminated"
fi

# ── 4. Optional cleanup ─────────────────────────────────────────────────────
echo ""
read -r -p "Remove data/ and logs/ directories? (y/N): " CLEANUP
if [[ "$CLEANUP" =~ ^[Yy]$ ]]; then
    info "Step 4/4: Cleaning up data and logs..."
    rm -rf "$PROJECT_ROOT/data" 2>/dev/null || true
    rm -rf "$PROJECT_ROOT/logs" 2>/dev/null || true
    success "Removed data/ and logs/"
else
    info "Step 4/4: Skipped cleanup (data/logs preserved)"
fi

echo ""
echo "========================================="
echo "  IMDF Uninstalled Successfully"
echo "========================================="
echo ""
