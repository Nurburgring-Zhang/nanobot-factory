"""P3-2-W2: scoring-service FastAPI app (port 8005).

Wraps the 15 scoring operators from imdf.engines.aesthetic_scorer (5 base) +
in-house extensions (10) into a dedicated microservice.
"""

# P4-1-W1: refactored — see backend/common/ for the shared library.
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.scoring_service.routes import router as scoring_router

# Mount the original scoring-related routers (preserve /api/aesthetic/* legacy)
try:
    from imdf.api.aesthetic_routes import router as legacy_aesthetic_router
    HAS_LEGACY = True
except Exception as e:  # noqa: BLE001
    HAS_LEGACY = False
    legacy_aesthetic_router = None
    import logging
    logging.getLogger(__name__).warning("legacy aesthetic_routes unavailable: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = create_app(
    "scoring_service",
    description='Data scoring bounded context — 15 operators (P3-2-W2)',
    version='0.1.0',
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

if HAS_LEGACY and legacy_aesthetic_router is not None:
    app.include_router(legacy_aesthetic_router)

app.include_router(scoring_router)

@app.get("/")
async def root():
    from services.scoring_service.operators import OPERATORS as _NEW_OPERATORS
    from services.scoring_service._legacy_operators import SCORING_OPERATORS
    return {
        "service": "scoring-service",
        "version": "0.1.0",
        "operator_count": len(_NEW_OPERATORS),
        "legacy_operator_count": len(SCORING_OPERATORS),
        "endpoints": {
            "operators": ["/api/v1/score/list", "/api/v1/score/{op_id}",
                          "/api/v1/score/operators", "/api/v1/score/operators/{op_id}"],
            "score": ["/api/v1/score/{op_id}/run", "/api/v1/score/run", "/api/v1/score/run/batch"],
            "legacy": ["/api/aesthetic/*"],
            "healthz": ["/healthz"],
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="scoring_service",
        adapter=MultimodalAdapter(service_id="scoring_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for scoring_service: %%s", _mm_err)


__all__ = ["app"]
