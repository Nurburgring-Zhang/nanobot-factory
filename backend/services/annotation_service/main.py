"""P3-2-W1: annotation-service FastAPI app (port 8003).

Wraps the original annotation / prelabel routers from imdf.api and adds
a new /api/v1/annotations + /api/v1/tasks REST surface.
"""

# P4-1-W1: refactored — see backend/common/ for the shared library.
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.annotation_service.routes import router as annotation_router

# Mount the original routers
try:
    from imdf.api.annotation_routes import router as legacy_annotation_router
    from imdf.api.annotation_history_routes import router as legacy_history_router
    from imdf.api.prelabel_router import router as legacy_prelabel_router
    HAS_LEGACY = True
except Exception as e:  # noqa: BLE001
    HAS_LEGACY = False
    legacy_annotation_router = legacy_history_router = legacy_prelabel_router = None
    import logging
    logging.getLogger(__name__).warning("legacy annotation routers unavailable: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = create_app(
    "annotation_service",
    description='Annotation / task bounded context (P3-2-W1)',
    version='0.1.0',
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

# legacy /api/annotations/*, /api/v1/annotations/history, /api/prelabel
if HAS_LEGACY and legacy_annotation_router is not None:
    app.include_router(legacy_annotation_router)
if HAS_LEGACY and legacy_history_router is not None:
    app.include_router(legacy_history_router)
if HAS_LEGACY and legacy_prelabel_router is not None:
    app.include_router(legacy_prelabel_router)

# new /api/v1/annotations + /api/v1/tasks
app.include_router(annotation_router)

@app.get("/")
async def root():
    return {
        "service": "annotation-service",
        "version": "0.1.0",
        "endpoints": {
            "legacy": [
                "/api/annotations/save",
                "/api/v1/annotations/history",
                "/api/prelabel",
            ],
            "annotations": [
                "/api/v1/annotations",
                "/api/v1/annotations/history",
            ],
            "tasks": [
                "/api/v1/tasks",
                "/api/v1/tasks/{id}",
                "/api/v1/tasks/{id}/annotations",
            ],
            "operators": ["/api/v1/operators"],
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="annotation_service",
        adapter=MultimodalAdapter(service_id="annotation_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for annotation_service: %%s", _mm_err)


__all__ = ["app"]
