# ⚠️ DEPRECATED — DO NOT USE ⚠️
# =============================================================================
# The Kubernetes deployment for nanobot-factory VDP-2026 is DEPRECATED as of
# 2026-06-24 (P4-1-W2). The platform now runs exclusively on bare-metal
# systemd units under `deploy/bare_metal/`.
#
# Why deprecated:
#   1. User directive (2026-06-22): "禁止 Docker / Kubernetes / 容器"
#   2. Bare-metal deploys ~30% faster per node, simpler ops story
#   3. Single-host tuning is easier than per-pod resource budgeting
#
# Migration path:
#   - See deploy/bare_metal/README.md §8 "Migrating from deploy/k8s/"
#   - Restore latest k8s pg_dump onto the bare-metal VM
#
# These manifests are kept in tree for diffing / replay only. Do NOT run
# `kubectl apply -f deploy/k8s/` on any production cluster.
# =============================================================================

# All resources below are superseded by deploy/bare_metal/systemd/*.service.
# No additional changes will be accepted to this directory.