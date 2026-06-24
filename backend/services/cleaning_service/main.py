"""P3-4-W1: cleaning-service FastAPI app (port 8004).

Hosts 32 cleaning operators with dynamic /api/v1/clean/{op_id} routing.

# P4-1-W1: refactored — see backend/common/ for the shared library.
"""
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.cleaning_service.routes import router as cleaning_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = create_app(
    "cleaning_service",
    description="Data cleaning bounded context — 32 operators (image/video/text/audio)",
    version="0.4.0",  # P3-4-W1
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

app.include_router(cleaning_router)

@app.get("/")
async def root():
    from services.cleaning_service.operators import OPERATORS, list_operators
    by_modality = {}
    for op in list_operators():
        m = op.get("modality", "?")
        by_modality[m] = by_modality.get(m, 0) + 1
    return {
        "service": "cleaning-service",
        "version": "0.4.0",
        "operator_count": len(OPERATORS),
        "by_modality": by_modality,
        "endpoints": {
            "list": "/api/v1/clean/list",
            "execute": "POST /api/v1/clean/{op_id}",
            "schema": "/api/v1/clean/{op_id}/schema",
            "preview": "POST /api/v1/clean/{op_id}/preview",
            "healthz": "/healthz",
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="cleaning_service",
        adapter=MultimodalAdapter(service_id="cleaning_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for cleaning_service: %%s", _mm_err)


__all__ = ["app"]