"""P3-2-W2: evaluation-service FastAPI app (port 8007).

Wraps eval_engine.py from imdf.engines into a dedicated microservice.
Provides model evaluation task CRUD, metrics aggregation, and Bad Case
detection/feedback endpoints.
"""

# P4-1-W1: refactored — see backend/common/ for the shared library.
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.evaluation_service.routes import router as evaluation_router

# Mount original evaluation_routes if available
try:
    from imdf.api.eval_routes import router as legacy_eval_router
    HAS_LEGACY = True
except Exception as e:  # noqa: BLE001
    HAS_LEGACY = False
    legacy_eval_router = None
    import logging
    logging.getLogger(__name__).warning("legacy eval_routes unavailable: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = create_app(
    "evaluation_service",
    description='Model evaluation + Bad Case bounded context (P3-2-W2)',
    version='0.1.0',
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

if HAS_LEGACY and legacy_eval_router is not None:
    app.include_router(legacy_eval_router)

app.include_router(evaluation_router)

@app.get("/")
async def root():
    from services.evaluation_service.operators import OPERATORS
    return {
        "service": "evaluation-service",
        "version": "0.2.0",  # P3-5-W2
        "operator_count": len(OPERATORS),
        "endpoints": {
            "evaluations": ["/api/v1/evaluations", "/api/v1/evaluations/{id}"],
            "results": ["/api/v1/evaluations/{id}/results"],
            "bad_cases": ["/api/v1/bad_cases", "/api/v1/bad_cases/{id}"],
            "metrics": ["/api/v1/evaluations/metrics/catalog"],
            "eval_operators": ["/api/v1/eval/list", "/api/v1/eval/{op_id}",
                               "/api/v1/eval/{op_id}/schema"],
            "healthz": ["/healthz"],
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="evaluation_service",
        adapter=MultimodalAdapter(service_id="evaluation_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for evaluation_service: %%s", _mm_err)


__all__ = ["app"]
