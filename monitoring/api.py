"""P19 v5.2-A — Aggregated FastAPI router for the 7 new monitoring layers.

Exposes:

    GET  /api/v1/monitoring/sentry/stats
    GET  /api/v1/monitoring/errors                  (alias of sentry stats)
    GET  /api/v1/monitoring/errors/recent
    GET  /api/v1/monitoring/health/deep             (20-service deep check)
    GET  /api/v1/monitoring/agent/activity
    GET  /api/v1/monitoring/agent/stats
    WS   /api/v1/monitoring/agent/stream
    GET  /api/v1/monitoring/cost
    GET  /api/v1/monitoring/cost/per_user
    GET  /api/v1/monitoring/cost/per_model
    GET  /api/v1/monitoring/cost/per_task
    GET  /api/v1/monitoring/quality
    GET  /api/v1/monitoring/quality/drift
    GET  /api/v1/monitoring/quality/agreement
    GET  /api/v1/monitoring/compliance/gdpr/{user_id}
    POST /api/v1/monitoring/compliance/gdpr/{user_id}/erasure
    GET  /api/v1/monitoring/compliance/eu-ai-act
    GET  /api/v1/monitoring/heatmap
    GET  /api/v1/monitoring/heatmap/{route}
    POST /api/v1/monitoring/heatmap
    GET  /api/v1/monitoring/funnel
    POST /api/v1/monitoring/funnel

The router is designed to be mounted in ``backend/imdf/api/canvas_web.py`` (or
the legacy ``server.py``) with one line:

    from monitoring.api import mount_monitoring
    mount_monitoring(app)
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request, WebSocket, WebSocketDisconnect

from monitoring import sentry as sentry_mod
from monitoring import health as health_mod
from monitoring import agent_tracking as agent_mod
from monitoring import cost_tracking as cost_mod
from monitoring import quality_tracking as quality_mod
from monitoring import compliance_reports as compliance_mod
from monitoring import user_behavior as behavior_mod
from monitoring import observability as obs_mod
from monitoring import slo as slo_mod
from monitoring import tracing as tracing_mod
from monitoring import anomaly as anomaly_mod


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/monitoring", tags=["monitoring"])

    # ------------------------------------------------------------------ #
    # Layer 6 — Sentry
    # ------------------------------------------------------------------ #
    @router.get("/sentry/stats")
    async def sentry_stats() -> Dict[str, Any]:
        return sentry_mod.get_hub().stats()

    @router.get("/errors")
    async def errors_alias() -> Dict[str, Any]:
        return sentry_mod.get_hub().stats()

    @router.get("/errors/recent")
    async def errors_recent(
        limit: int = Query(100, ge=1, le=1000),
        level: Optional[str] = Query(None),
        service: Optional[str] = Query(None),
        layer: Optional[str] = Query(None),
    ) -> Dict[str, Any]:
        items = sentry_mod.get_hub().recent(limit=limit, level=level, service=service, layer=layer)
        return {"items": items, "count": len(items)}

    # ------------------------------------------------------------------ #
    # Layer 7 — Health
    # ------------------------------------------------------------------ #
    @router.get("/health/deep")
    async def health_deep(force: bool = Query(False, description="Bypass the 5s TTL cache")) -> Dict[str, Any]:
        return await health_mod.get_registry().deep_check(force=force)

    @router.get("/health/deep/aggregated")
    async def health_deep_aggregated(force: bool = Query(False)) -> Dict[str, Any]:
        """Aggregated 20-service health view (P19-D1).

        Wraps the standard deep_check payload with an ``aggregated`` summary
        so the dashboard can render a single status card. Cached for 5s.
        """
        return await health_mod.get_registry().deep_aggregated(force=force)

    @router.get("/health/services")
    async def health_services() -> Dict[str, Any]:
        return {"services": health_mod.get_registry().services()}

    # ------------------------------------------------------------------ #
    # Layer 8 — Agent tracking
    # ------------------------------------------------------------------ #
    @router.get("/agent/activity")
    async def agent_activity(
        limit: int = Query(100, ge=1, le=1000),
        agent_id: Optional[str] = Query(None),
        user_id: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        since: Optional[float] = Query(None),
    ) -> Dict[str, Any]:
        items = agent_mod.get_tracker().recent(
            limit=limit, agent_id=agent_id, user_id=user_id, status=status, since=since,
        )
        return {"items": items, "count": len(items)}

    @router.get("/agent/stats")
    async def agent_stats() -> Dict[str, Any]:
        return agent_mod.get_tracker().stats()

    @router.websocket("/agent/stream")
    async def agent_stream(ws: WebSocket) -> None:
        await ws.accept()
        tracker = agent_mod.get_tracker()
        queue = await tracker.subscribe()
        try:
            # initial snapshot
            await ws.send_json({"type": "snapshot", "items": tracker.recent(limit=50)})
            while True:
                ev = await queue.get()
                await ws.send_json({"type": "event", "event": ev})
        except WebSocketDisconnect:
            pass
        finally:
            await tracker.unsubscribe(queue)

    @router.post("/agent/record")
    async def agent_record(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        rec = agent_mod.get_tracker().record(**payload)
        return rec.to_dict()

    # ------------------------------------------------------------------ #
    # Layer 9 — Cost
    # ------------------------------------------------------------------ #
    @router.get("/cost")
    async def cost_overview() -> Dict[str, Any]:
        t = cost_mod.get_tracker()
        return {"stats": t.stats(), "recent": t.recent(limit=20)}

    @router.get("/cost/per_user")
    async def cost_per_user(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
        return {"rows": cost_mod.get_tracker().per_user(limit=limit)}

    @router.get("/cost/per_model")
    async def cost_per_model(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
        return {"rows": cost_mod.get_tracker().per_model(limit=limit)}

    @router.get("/cost/per_task")
    async def cost_per_task(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
        return {"rows": cost_mod.get_tracker().per_task(limit=limit)}

    @router.get("/cost/by-tenant")
    async def cost_by_tenant(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
        """P19-D1 — per-tenant cost aggregation (tenant_id attribution)."""
        return {"rows": cost_mod.get_tracker().per_tenant(limit=limit)}

    @router.post("/cost/record")
    async def cost_record(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        rec = cost_mod.get_tracker().record(**payload)
        return rec.to_dict()

    # ------------------------------------------------------------------ #
    # Layer 10 — Quality
    # ------------------------------------------------------------------ #
    @router.get("/quality")
    async def quality_overview() -> Dict[str, Any]:
        t = quality_mod.get_tracker()
        return {
            "stats": t.stats(),
            "per_annotator": t.per_annotator(),
            "recent": t.recent(limit=20),
        }

    @router.get("/quality/drift")
    async def quality_drift() -> Dict[str, Any]:
        return quality_mod.get_tracker().drift_report()

    @router.get("/quality/agreement")
    async def quality_agreement() -> Dict[str, Any]:
        return quality_mod.get_tracker().agreement()

    @router.post("/quality/record")
    async def quality_record(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        rec = quality_mod.get_tracker().record(**payload)
        return rec.to_dict()

    # ------------------------------------------------------------------ #
    # Layer 11 — Compliance
    # ------------------------------------------------------------------ #
    @router.get("/compliance/gdpr/{user_id}")
    async def gdpr_access(user_id: str) -> Dict[str, Any]:
        report = compliance_mod.generate_gdpr_access(user_id)
        return report.to_dict()

    # P19-D1 — REAL right-to-erasure (DELETE method, idempotent).
    @router.delete("/compliance/gdpr/erase/{user_id}")
    async def gdpr_erase(
        user_id: str,
        requester: str = Query("anonymous", description="Actor performing the erasure"),
        reason: str = Query("GDPR Art. 17 right-to-erasure"),
    ) -> Dict[str, Any]:
        """Perform REAL right-to-erasure for the given user.

        Removes every record across cost_tracking / agent_tracking /
        quality_tracking whose subject is ``user_id``. Records the erasure
        event in the audit chain. Idempotent — a second call returns
        ``erased.total == 0``.
        """
        return compliance_mod.execute_gdpr_erasure(
            user_id, requester=requester, reason=reason,
        )

    # P19-D1 — Data subject access export (machine-readable JSON).
    @router.get("/compliance/gdpr/export/{user_id}")
    async def gdpr_export(user_id: str) -> Dict[str, Any]:
        return compliance_mod.export_data_subject_access(user_id)

    # Dry-run preview (kept for legacy callers).
    @router.post("/compliance/gdpr/{user_id}/erasure")
    async def gdpr_erasure(
        user_id: str,
        confirm: bool = Body(False, embed=True),
    ) -> Dict[str, Any]:
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail="confirm=true required to perform erasure (GDPR Art. 17 safeguard). For real erasure use DELETE /api/v1/monitoring/compliance/gdpr/erase/{user_id}.",
            )
        return compliance_mod.execute_gdpr_erasure(user_id)

    @router.get("/compliance/eu-ai-act")
    async def eu_ai_act() -> Dict[str, Any]:
        return compliance_mod.generate_eu_ai_act_report()

    # ------------------------------------------------------------------ #
    # Layer 12 — User behavior
    # ------------------------------------------------------------------ #
    @router.get("/heatmap")
    async def heatmap_overview() -> Dict[str, Any]:
        return behavior_mod.get_tracker().heatmap_routes()

    @router.get("/heatmap/{route}")
    async def heatmap_route(route: str, limit: int = Query(1000, ge=1, le=5000)) -> Dict[str, Any]:
        items = behavior_mod.get_tracker().heatmap_for_route(route, limit=limit)
        return {"route": route, "items": items, "count": len(items)}

    @router.post("/heatmap")
    async def heatmap_record(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        ev = behavior_mod.get_tracker().record_heatmap(**payload)
        return ev.to_dict()

    @router.get("/funnel")
    async def funnel_report() -> Dict[str, Any]:
        return behavior_mod.get_tracker().funnel_report()

    @router.post("/funnel")
    async def funnel_record(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
        ev = behavior_mod.get_tracker().record_funnel(**payload)
        return ev.to_dict()

    # ------------------------------------------------------------------ #
    # Meta — capabilities advert
    # ------------------------------------------------------------------ #
    @router.get("/capabilities")
    async def capabilities() -> Dict[str, Any]:
        return {
            "layers": {
                "6_sentry":           {"sdk_installed": sentry_mod.get_hub().has_sdk,
                                       "dsn_configured": sentry_mod.get_hub().dsn_configured,
                                       "enabled": sentry_mod.get_hub().enabled},
                "7_health_deep":      {"services": len(health_mod.DEFAULT_SERVICES)},
                "8_agent_tracking":   {"buffer_size": len(agent_mod.get_tracker().buffer)},
                "9_cost_tracking":    {"buffer_size": len(cost_mod.get_tracker().buffer),
                                       "pricing_models": len(cost_mod.DEFAULT_MODEL_PRICING)},
                "10_quality":         {"buffer_size": len(quality_mod.get_tracker().buffer)},
                "11_compliance":      {"gdpr": True, "eu_ai_act": True},
                "12_user_behavior":   {"heatmap_buffer": len(behavior_mod.get_tracker().heatmap),
                                       "funnel_buffer": len(behavior_mod.get_tracker().funnel)},
                "13_observability":   {"counters": len(obs_mod.get_registry()._counters),
                                       "gauges": len(obs_mod.get_registry()._gauges)},
            },
            "version": "1.1.0",
        }

    # P19-D1 — Prometheus-compatible /metrics exposition.
    @router.get("/metrics")
    async def metrics() -> "Response":  # type: ignore[name-defined]
        from fastapi import Response
        return Response(content=obs_mod.get_registry().scrape(),
                        media_type="text/plain; version=0.0.4")

    @router.get("/observability/snapshot")
    async def observability_snapshot() -> Dict[str, Any]:
        return obs_mod.get_registry().snapshot()

    # ------------------------------------------------------------------ #
    # P19-E3 / F2 — SLO / Error Budget / Burn-rate alerts (Layer 13)
    # ------------------------------------------------------------------ #
    @router.get("/slo")
    async def slo_report() -> Dict[str, Any]:
        """Return the SLO catalog + live error-budget snapshot.

        JSON shape::

            {
                "generated_at": <epoch seconds>,
                "slos": [{name, description, service, target, window_seconds, ...}],
                "budgets": {<slo_name>: {valid_count, good_count, bad_count,
                                          error_budget_total, error_budget_remaining,
                                          burn_rate, target, compliant}}
            }
        """
        return slo_mod.build_slo_report().to_dict()

    @router.get("/slo/rules")
    async def slo_burn_rate_rules() -> "Response":  # type: ignore[name-defined]
        from fastapi import Response
        return Response(
            content=slo_mod.burn_rate_rules_yaml(),
            media_type="application/yaml",
        )

    @router.get("/slo/recorder/{slo_name}")
    async def slo_recorder_snapshot(slo_name: str) -> Dict[str, Any]:
        """Return the live in-process ring buffer for a single SLO recorder."""
        rec = slo_mod.get_recorder(slo_name)
        return {
            "slo_name": slo_name,
            "target": rec.target,
            "kind": rec.kind,
            "window_seconds": rec.window_seconds,
            "sample_count": len(rec.snapshot()),
            "budget": rec.compute_budget().to_dict(),
        }

    # ------------------------------------------------------------------ #
    # P19-E3 / F2 — Distributed tracing (Layer 14)
    # ------------------------------------------------------------------ #
    @router.get("/tracing/status")
    async def tracing_status() -> Dict[str, Any]:
        return tracing_mod.get_environment_status()

    @router.get("/tracing/spans")
    async def tracing_recent_spans(
        limit: int = Query(100, ge=1, le=1000),
        name: Optional[str] = Query(None),
    ) -> Dict[str, Any]:
        spans = tracing_mod.get_tracing_manager().exporter.get_finished_spans(name=name)
        spans = spans[-limit:]
        return {
            "count": len(spans),
            "items": [s.to_dict() for s in spans],
        }

    # ------------------------------------------------------------------ #
    # P19-E3 / F2 — Anomaly detection (Layer 15)
    # ------------------------------------------------------------------ #
    @router.get("/anomaly/status")
    async def anomaly_status() -> Dict[str, Any]:
        return anomaly_mod.environment_status()

    @router.get("/anomaly/recent")
    async def anomaly_recent(
        limit: int = Query(100, ge=1, le=1000),
        series: Optional[str] = Query(None),
    ) -> Dict[str, Any]:
        events = anomaly_mod.get_detector_manager().recent_events(limit=limit, series=series)
        return {
            "count": len(events),
            "items": [e.to_dict() for e in events],
        }

    return router


# --------------------------------------------------------------------------- #
# Mount helper (works on both FastAPI and Starlette)
# --------------------------------------------------------------------------- #
def mount_monitoring(app: Any) -> APIRouter:
    """Mount the monitoring router on a FastAPI/Starlette app."""
    router = build_router()
    app.include_router(router)
    # Install optional hooks.
    try:
        agent_mod.install_audit_chain_hook()
    except Exception:  # noqa: BLE001
        pass
    return router
