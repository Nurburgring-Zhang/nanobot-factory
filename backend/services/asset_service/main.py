"""P3-2-W1: asset-service FastAPI app (port 8002).

Wraps the original DAM / OSS / resource_library routers from imdf.api
and adds a new /api/v1/assets + /api/v1/items REST surface.
"""

# P4-1-W1: refactored — see backend/common/ for the shared library.
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.asset_service.routes import router as asset_router
from services.asset_service.characters import router as character_router
from services.asset_service.generators import router as generator_router

# P4-5-W2: iterative sessions + multi-agent + consistency endpoints
try:
    from services.asset_service.iteration.routes import router as iteration_router
    HAS_ITERATION = True
except Exception as e:  # noqa: BLE001
    HAS_ITERATION = False
    iteration_router = None
    import logging
    logging.getLogger(__name__).warning("iteration router unavailable: %s", e)

# Mount the original routers
try:
    from imdf.api.dam_routes import router as legacy_dam_router
    from imdf.api.oss_routes import router as legacy_oss_router
    from imdf.api.resource_library import router as legacy_library_router
    HAS_LEGACY = True
except Exception as e:  # noqa: BLE001
    HAS_LEGACY = False
    legacy_dam_router = legacy_oss_router = legacy_library_router = None
    import logging
    logging.getLogger(__name__).warning("legacy asset routers unavailable: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = create_app(
    "asset_service",
    description='Asset / DAM / OSS bounded context (P3-2-W1)',
    version='0.1.0',
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

# legacy /api/dam/*, /api/v1/oss/*, /imdf/library/*
if HAS_LEGACY and legacy_dam_router is not None:
    app.include_router(legacy_dam_router)
if HAS_LEGACY and legacy_oss_router is not None:
    app.include_router(legacy_oss_router)
if HAS_LEGACY and legacy_library_router is not None:
    app.include_router(legacy_library_router)

# P4-5-W1: character assets + multi-modal generators MUST be mounted
# BEFORE the legacy asset_router so they win the route-resolution match
# (e.g. /api/v1/assets/models would otherwise be captured by
# /api/v1/assets/{asset_id} in the legacy router).
app.include_router(character_router)
app.include_router(generator_router)

# new /api/v1/assets + /api/v1/items (legacy DAM/OSS library wrapper)
app.include_router(asset_router)

# P4-5-W2: iterative sessions + multi-agent + consistency (mounted under /api/v1/assets/*)
if HAS_ITERATION and iteration_router is not None:
    app.include_router(iteration_router)

@app.get("/")
async def root():
    return {
        "service": "asset-service",
        "version": "0.1.0",
        "endpoints": {
            "dam": ["/api/dam/files", "/api/dam/stats", "/api/dam/formats"],
            "oss": ["/api/v1/oss/health", "/api/v1/oss/list", "/api/v1/oss/upload"],
            "library": ["/imdf/library/items", "/imdf/library/categories"],
            "assets": ["/api/v1/assets", "/api/v1/assets/{id}"],
            "items": ["/api/v1/items", "/api/v1/items/categories"],
            # P4-5-W1
            "characters": [
                "/api/v1/assets/characters",
                "/api/v1/assets/characters/{id}",
                "/api/v1/assets/characters/{id}/lock",
                "/api/v1/assets/characters/{id}/consistency_check",
            ],
            "generators": [
                "/api/v1/assets/models",
                "/api/v1/assets/generate/image",
                "/api/v1/assets/generate/image/batch",
                "/api/v1/assets/generate/video",
                "/api/v1/assets/generate/video/edit/{video_id}",
                "/api/v1/assets/generate/video/extend/{video_id}",
                "/api/v1/assets/generate/voice",
                "/api/v1/assets/voices",
                "/api/v1/assets/voices/clone",
                "/api/v1/assets/generate/music",
                "/api/v1/assets/generate/storyboard",
                "/api/v1/assets/storyboard/{id}/render",
            ],
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="asset_service",
        adapter=MultimodalAdapter(service_id="asset_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for asset_service: %%s", _mm_err)


__all__ = ["app"]
