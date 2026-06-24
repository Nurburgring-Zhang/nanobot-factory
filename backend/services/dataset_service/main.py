"""P3-2-W2: dataset-service FastAPI app (port 8006).

Wraps dataset_manager.py from imdf.engines into a dedicated microservice.
Provides dataset version CRUD, sample listing, and export (jsonl / parquet mock).
"""

# P4-1-W1: refactored — see backend/common/ for the shared library.
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.dataset_service.routes import router as dataset_router

# P4-4-W1: OpenMetadata-inspired metadata platform (databases/schemas/tables/
# columns/datasets/tags/glossaries + auto-discovery + search)
from services.dataset_service.metadata import init_metadata_db
from services.dataset_service.metadata.routes import router as metadata_router

# P4-4-W2: lineage router (collection + graph + impact + visualize)
try:
    from services.dataset_service.lineage.api import router as lineage_router
    from services.dataset_service.lineage.models import init_lineage_db as _init_lineage_db
    HAS_LINEAGE = True
except Exception as e:  # noqa: BLE001
    HAS_LINEAGE = False
    lineage_router = None
    _init_lineage_db = None
    import logging
    logging.getLogger(__name__).warning("lineage router unavailable: %s", e)

# Mount original dataset_routes if available
try:
    from imdf.api.dataset_routes import router as legacy_dataset_router
    HAS_LEGACY = True
except Exception as e:  # noqa: BLE001
    HAS_LEGACY = False
    legacy_dataset_router = None
    import logging
    logging.getLogger(__name__).warning("legacy dataset_routes unavailable: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # P4-4-W1: create the 10 metadata tables on startup (idempotent)
    try:
        init_metadata_db(auto_create=True)
    except Exception as e:  # noqa: BLE001
        import logging as _logging
        _logging.getLogger(__name__).warning("metadata init failed: %s", e)
    # P4-4-W2: create the 3 lineage tables on startup (idempotent)
    if HAS_LINEAGE and _init_lineage_db is not None:
        try:
            _init_lineage_db(auto_create=True)
        except Exception as e:  # noqa: BLE001
            import logging as _logging
            _logging.getLogger(__name__).warning("lineage init failed: %s", e)
    yield

app = create_app(
    "dataset_service",
    description='Dataset version + export bounded context (P3-2-W2) + metadata (P4-4-W1) + lineage (P4-4-W2)',
    version='0.2.0',
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

if HAS_LEGACY and legacy_dataset_router is not None:
    app.include_router(legacy_dataset_router)

app.include_router(dataset_router)

# P4-4-W1 metadata platform (10 tables, OpenMetadata-inspired)
app.include_router(metadata_router)

# P4-4-W2 lineage platform (collection + graph + impact + visualize)
if HAS_LINEAGE and lineage_router is not None:
    app.include_router(lineage_router)


@app.get("/")
async def root():
    from services.dataset_service.operators import OPERATORS as FILTER_OPS
    from services.dataset_service.exporters import OPERATORS as EXPORT_OPS
    return {
        "service": "dataset-service",
        "version": "0.2.0",  # P4-4-W2: lineage added
        "filter_operator_count": len(FILTER_OPS),
        "export_operator_count": len(EXPORT_OPS),
        "metadata": {
            "tables": 10,  # P4-4-W1: 10 metadata tables
            "discovery": True,
            "auto_pii": True,
            "glossary": True,
            "search": True,
        },
        "lineage": {
            "enabled": HAS_LINEAGE,
            "tables": 3,  # P4-4-W2: 3 lineage tables
            "sources": ["sql", "ast", "operator", "manual", "scan"],
            "visualize_formats": ["react-flow", "vis", "d3", "cytoscape"],
        },
        "endpoints": {
            "datasets": ["/api/v1/datasets", "/api/v1/datasets/{name}"],
            "versions": ["/api/v1/datasets/{name}/versions"],
            "samples": ["/api/v1/datasets/{name}/versions/{v}/samples"],
            "export": ["/api/v1/datasets/{name}/versions/{v}/export"],
            "filter": ["/api/v1/dataset/filter/list",
                       "/api/v1/dataset/filter/{op_id}",
                       "/api/v1/dataset/filter/{op_id}/run"],
            "export_ops": ["/api/v1/dataset/export/list",
                           "/api/v1/dataset/export/{op_id}",
                           "/api/v1/dataset/export/{op_id}/run"],
            "metadata": [
                "/api/v1/metadata/health",
                "/api/v1/metadata/databases",
                "/api/v1/metadata/schemas",
                "/api/v1/metadata/tables",
                "/api/v1/metadata/columns",
                "/api/v1/metadata/datasets",
                "/api/v1/metadata/discovery/run",
                "/api/v1/metadata/discovery/schedule",
                "/api/v1/metadata/tags",
                "/api/v1/metadata/tags/auto/pii",
                "/api/v1/metadata/tags/propagate",
                "/api/v1/metadata/glossaries",
                "/api/v1/metadata/glossary/seed",
                "/api/v1/metadata/search",
                "/api/v1/metadata/recommend",
            ],
            "lineage": [
                "/api/v1/lineage/collect",
                "/api/v1/lineage/collect/sql",
                "/api/v1/lineage/collect/python",
                "/api/v1/lineage/collect/operator",
                "/api/v1/lineage/collect/manual",
                "/api/v1/lineage/collect/pipeline-step",
                "/api/v1/lineage/graph/{entity}",
                "/api/v1/lineage/graph/{entity}/upstream",
                "/api/v1/lineage/graph/{entity}/downstream",
                "/api/v1/lineage/graph/full",
                "/api/v1/lineage/graph/stats",
                "/api/v1/lineage/impact/{entity}",
                "/api/v1/lineage/impact/{entity}/notify",
                "/api/v1/lineage/visualize/{entity}",
                "/api/v1/lineage/visualize/dataset/{dataset}",
                "/api/v1/lineage/visualize/full",
            ] if HAS_LINEAGE else [],
            "healthz": ["/healthz"],
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="dataset_service",
        adapter=MultimodalAdapter(service_id="dataset_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for dataset_service: %%s", _mm_err)


__all__ = ["app"]
