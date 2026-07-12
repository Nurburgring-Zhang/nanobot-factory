"""
P19 v5.2-A: 12-Layer Monitoring Module
=======================================
Adds 7 new layers on top of the existing 5 (应用指标 / OTel/结构化日志 / EventBus / 数据血缘):

    Layer 6  : Sentry error aggregation       (monitoring.sentry)
    Layer 7  : 20-service deep health checks  (monitoring.health + health_checks/)
    Layer 8  : Agent behavior tracking        (monitoring.agent_tracking)
    Layer 9  : Cost tracking (model/task/user)(monitoring.cost_tracking)
    Layer 10 : Quality tracking (annotation)  (monitoring.quality_tracking)
    Layer 11 : Compliance reports (GDPR/EU AI)(monitoring.compliance_reports)
    Layer 12 : User behavior (heatmap/funnel) (monitoring.user_behavior)

All layers are exposed via a single FastAPI router at ``/api/v1/monitoring/*``.
A consolidated dashboard set is generated under ``monitoring/grafana-dashboards/layer_*``.

Backward-compatible: every layer degrades gracefully when its dependency is missing
(sentry-sdk, redis, postgres, audit-chain, usage-tracker, etc.).
"""

from monitoring.api import build_router, mount_monitoring  # noqa: F401

__all__ = ["build_router", "mount_monitoring"]
__version__ = "1.0.0"
