"""backend/common/health — /healthz, /readyz, /metrics for the 12 services (P4-1-W1).

This module replaces the per-service ``monitoring quick_setup(app, ...)``
incantation with a single import. The P3-8 implementation lives at
``imdf.monitoring`` and is preserved for backwards compatibility; this
file adds:

  * An optional ``/healthz`` body that checks DB readiness (``common.db.ping``).
  * Cleaner Prometheus exposition (delegates to ``imdf.monitoring`` if
    available, else falls back to a no-op text renderer).
  * A ``register_metrics`` helper that combines the per-service counter
    registration + middleware in one call (no separate ``register_metrics_middleware``).
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from .db import ping as db_ping

logger = logging.getLogger(__name__)

# 12 service identifiers — kept in sync with imdf.monitoring.endpoints.SERVICE_NAMES
SERVICE_NAMES = [
    "agent_service",
    "annotation_service",
    "asset_service",
    "cleaning_service",
    "collection_service",
    "dataset_service",
    "evaluation_service",
    "notification_service",
    "scoring_service",
    "search_service",
    "user_service",
    "workflow_service",
]


# ── Metrics middleware (no-op if imdf.monitoring missing) ──────────────────
def register_metrics(app: FastAPI, service_name: str) -> Optional[Any]:
    """Attach the request-observation middleware used by Prometheus.

    Returns the :class:`ServiceMetrics` instance when available, else ``None``.
    The middleware counts requests, latencies, and per-endpoint status codes.
    """
    try:
        from imdf.monitoring import quick_setup  # type: ignore

        return quick_setup(app, service_name)
    except Exception as exc:  # pragma: no cover
        logger.warning("imdf.monitoring unavailable (%s); using lightweight fallback", exc)

    # Lightweight in-process counter fallback (kept tiny on purpose)
    state: Dict[str, Any] = {"requests": 0, "errors": 0, "latency_sum": 0.0}

    @app.middleware("http")
    async def _observe(request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            state["errors"] += 1
            raise
        finally:
            state["requests"] += 1
            state["latency_sum"] += time.perf_counter() - start
        return response

    app.state.lightweight_metrics = state  # for /metrics endpoint
    return None


# ── /metrics / /healthz / /readyz ──────────────────────────────────────────
def _render_metrics(app: FastAPI) -> str:
    """Return Prometheus text exposition for the service.

    Tries ``imdf.monitoring.ServiceMetrics.render`` first (full histogram
    support); falls back to a 3-line summary.
    """
    try:
        from imdf.monitoring import get_service  # type: ignore

        sm = get_service(getattr(app, "title", "").split("—")[-1].strip() or "unknown")
        if sm is not None and hasattr(sm, "render"):
            return sm.render()
    except Exception:
        pass

    # Lightweight fallback
    state = getattr(app.state, "lightweight_metrics", None) or {}
    requests = state.get("requests", 0)
    errors = state.get("errors", 0)
    avg_latency = (state.get("latency_sum", 0.0) / requests) if requests else 0.0
    return (
        "# HELP requests_total Total HTTP requests\n"
        "# TYPE requests_total counter\n"
        f'requests_total{{service="{getattr(app, "title", "unknown")}"}} {requests}\n'
        "# HELP errors_total HTTP requests that raised\n"
        "# TYPE errors_total counter\n"
        f'errors_total{service_label(app)} {errors}\n'
        "# HELP avg_latency_seconds Avg latency\n"
        "# TYPE avg_latency_seconds gauge\n"
        f'avg_latency_seconds{service_label(app)} {avg_latency:.6f}\n'
    )


def service_label(app: FastAPI) -> str:
    return f'{{service="{getattr(app, "title", "unknown")}"}}'


def mount_health(
    app: FastAPI,
    health_path: str = "/healthz",
    ready_path: str = "/readyz",
    metrics_path: str = "/metrics",
    *,
    service_name: Optional[str] = None,
    check_db: bool = True,
    include_in_schema: bool = False,
) -> None:
    """Mount ``/healthz``, ``/readyz``, ``/metrics`` on *app*.

    * ``/healthz``  — process liveness. Always 200 if the worker is up.
      Body: ``{"status": "ok", "service": ..., "version": ...}``.
    * ``/readyz``   — readiness probe. By default checks DB connectivity;
      200 with ``{"ready": true}`` when OK, 503 otherwise.
    * ``/metrics``  — Prometheus text exposition.
    """
    svc = service_name or os.environ.get("SERVICE_NAME", getattr(app, "title", "unknown"))
    version = os.environ.get("SERVICE_VERSION", "0.1.0")

    @app.get(health_path, include_in_schema=include_in_schema)
    async def _healthz() -> JSONResponse:
        return JSONResponse({
            "status": "ok",
            "service": svc,
            "version": version,
        })

    @app.get(ready_path, include_in_schema=include_in_schema)
    async def _readyz() -> Response:
        if check_db:
            ok = db_ping()
            if not ok:
                return JSONResponse(
                    {"ready": False, "service": svc, "db": False},
                    status_code=503,
                )
            return JSONResponse({"ready": True, "service": svc, "db": True})
        return PlainTextResponse("ready\n")

    @app.get(metrics_path, include_in_schema=include_in_schema)
    async def _metrics() -> Response:
        return Response(
            content=_render_metrics(app),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )


__all__ = [
    "SERVICE_NAMES",
    "mount_health",
    "register_metrics",
]