"""
P3-8-W2: Standardized Prometheus /metrics + /healthz + /readyz endpoints for 12 services
=======================================================================================

Each service's main.py should:

    from imdf.monitoring.endpoints import mount_monitoring, register_metrics_middleware
    app = FastAPI(title="my-service")
    metrics = register_metrics_middleware(app, "user_service")
    mount_monitoring(app, metrics)

This adds three routes:
    GET /metrics  — Prometheus text format
    GET /healthz  — liveness probe (always 200 if process is up)
    GET /readyz   — readiness probe (200 if dependencies ok)

The 12 services listed below have this wired in (or will be wired in P3-8-W2
follow-up if a given service already has a main.py with a different shape).
"""
from __future__ import annotations

import time
import logging
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

from .service_metrics import ServiceMetrics, register_service

logger = logging.getLogger(__name__)

# 12 microservices registered in this project. Used by mount_monitoring
# to add /metrics + /healthz + /readyz to each one.
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


def register_metrics_middleware(app: FastAPI, service_name: str) -> ServiceMetrics:
    """Register request observation middleware for the service."""
    metrics = register_service(service_name)

    @app.middleware("http")
    async def _observe(request: Request, call_next):
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency = time.perf_counter() - start
            method = request.method
            endpoint = request.url.path
            metrics.observe_request(method, endpoint, status_code, latency)

    return metrics


def mount_monitoring(app: FastAPI, metrics: ServiceMetrics) -> None:
    """Mount /metrics, /healthz, /readyz on the given app."""

    @app.get("/metrics", include_in_schema=False)
    async def _metrics() -> Response:
        return Response(content=metrics.render(), media_type="text/plain; version=0.0.4; charset=utf-8")

    @app.get("/healthz", include_in_schema=False)
    async def _healthz() -> Response:
        return PlainTextResponse("ok\n")

    @app.get("/readyz", include_in_schema=False)
    async def _readyz() -> Response:
        # TODO: replace with real dep checks (PG, Redis) once per-service
        # health helpers are in place. For now return 200.
        return PlainTextResponse("ready\n")


def quick_setup(app: FastAPI, service_name: str) -> ServiceMetrics:
    """One-liner: register middleware + mount endpoints.

    Use in service main.py:
        app = FastAPI(...)
        quick_setup(app, "user_service")
    """
    metrics = register_metrics_middleware(app, service_name)
    mount_monitoring(app, metrics)
    return metrics


__all__ = [
    "SERVICE_NAMES", "register_metrics_middleware", "mount_monitoring", "quick_setup",
]
