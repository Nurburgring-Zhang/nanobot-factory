"""P3-3-W2: search-service FastAPI app (port 8011).

Aggregates three search modes behind a single REST surface:

  * ``/api/v1/search/text``       - BM25 + keyword (vector_retrieval.py)
  * ``/api/v1/search/semantic``   - hybrid vector + BM25 (semantic_search.py)
  * ``/api/v1/search/vector``     - direct vector similarity (pgvector when
                                    available; falls back to local NumPy)

Plus a document registry (in-memory) so search returns something useful
out of the box. The registry is deliberately tiny and self-contained -
in production the gateway forwards real-document requests to this
service and document records come from upstream ingestion.
"""

# P4-1-W1: refactored — see backend/common/ for the shared library.
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.search_service.routes import router as search_router

# P4-7-W1: multimodal routes (parse / embed / search/multimodal / RAG)
from services.search_service.multimodal_routes import all_routers as mm_routers

# Mount legacy search routers
try:
    from imdf.api.search_routes import router as legacy_search_router  # type: ignore
    HAS_LEGACY_SEARCH = True
except Exception:  # noqa: BLE001
    HAS_LEGACY_SEARCH = False
    legacy_search_router = None
    import logging
    logging.getLogger(__name__).warning("legacy search_routes unavailable")

try:
    from imdf.api.search_advanced_routes import (
        router as legacy_advanced_router)  # type: ignore
    HAS_LEGACY_ADV = True
except Exception:  # noqa: BLE001
    HAS_LEGACY_ADV = False
    legacy_advanced_router = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Boot the in-memory corpus + vector index
    try:
        from services.search_service.routes import get_search_engine
        get_search_engine()
    except Exception:  # noqa: BLE001
        pass
    yield

app = create_app(
    "search_service",
    description='Text / semantic / vector search (P3-3-W2)',
    version='0.1.0',
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

if HAS_LEGACY_SEARCH and legacy_search_router is not None:
    app.include_router(legacy_search_router)
if HAS_LEGACY_ADV and legacy_advanced_router is not None:
    app.include_router(legacy_advanced_router)

app.include_router(search_router)

# P4-7-W1: mount multimodal routers
for _mmr in mm_routers():
    app.include_router(_mmr)

@app.get("/")
async def root():
    from services.search_service.routes import get_search_engine
    eng = get_search_engine()
    return {
        "service": "search-service",
        "version": "0.1.0",
        "port": 8011,
        "corpus_size": eng.corpus_size(),
        "vector_dim": eng.vector_dim(),
        "pgvector_enabled": eng.has_pgvector(),
        "endpoints": {
            "text": ["/api/v1/search/text"],
            "semantic": ["/api/v1/search/semantic"],
            "vector": ["/api/v1/search/vector"],
            "corpus": [
                "/api/v1/search/documents",
                "/api/v1/search/documents/{doc_id}",
            ],
            "multimodal": [
                "/api/v1/multimodal/parse",
                "/api/v1/multimodal/parse/batch",
                "/api/v1/multimodal/embed",
                "/api/v1/multimodal/embed/batch",
                "/api/v1/multimodal/process",
                "/api/v1/multimodal/health",
                "/api/v1/multimodal/modalities",
                "/api/v1/search/multimodal",
                "/api/v1/search/multimodal/rag",
                "/api/v1/search/multimodal/index",
                "/api/v1/search/multimodal/indexed",
            ],
            "healthz": ["/healthz"],
        },
    }

__all__ = ["app"]
