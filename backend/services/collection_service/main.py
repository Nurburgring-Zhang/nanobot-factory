"""P3-5-W2: collection-service FastAPI app (port 8012).

Internal collection worker. Provides 15 collection operators that fetch
data from public sources (web pages, social media, public datasets).
In sandbox/test mode, operators return deterministic mock responses
without hitting the network.
"""

# P4-1-W1: refactored — see backend/common/ for the shared library.
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.collection_service.routes import router as collection_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = create_app(
    "collection_service",
    description='Asset collection bounded context — 15 operators (P3-5-W2)',
    version='0.1.0',
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

app.include_router(collection_router)

@app.get("/")
async def root():
    from services.collection_service.operators import OPERATORS, list_operators
    by_source = {}
    for op in list_operators():
        s = op.get("source", "?")
        by_source[s] = by_source.get(s, 0) + 1
    return {
        "service": "collection-service",
        "version": "0.1.0",
        "port": 8012,
        "operator_count": len(OPERATORS),
        "by_source": by_source,
        "endpoints": {
            "list": "/api/v1/collect/list",
            "execute": "POST /api/v1/collect/{op_id}",
            "schema": "/api/v1/collect/{op_id}/schema",
            "healthz": "/healthz",
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="collection_service",
        adapter=MultimodalAdapter(service_id="collection_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for collection_service: %%s", _mm_err)


__all__ = ["app"]
