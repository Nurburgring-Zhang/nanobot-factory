"""P3-3-W2: workflow-service FastAPI app (port 8009).

Workflow definition / execution / DAG monitoring.
"""

# P4-1-W1: refactored — see backend/common/ for the shared library.
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.workflow_service.routes import router as workflow_router
from services.workflow_service.templates_routes import router as templates_router
from services.workflow_service.editor_routes import router as editor_router

# Mount legacy workflow / scheduler routers if available
try:
    from imdf.api.scheduler_routes import router as legacy_scheduler_router  # type: ignore
    HAS_LEGACY = True
except Exception:  # noqa: BLE001
    HAS_LEGACY = False
    legacy_scheduler_router = None
    import logging
    logging.getLogger(__name__).warning("legacy scheduler_routes unavailable")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Touch DAG runtime so it boots the in-memory store on startup
    try:
        from services.workflow_service.dag import get_dag_runtime
        get_dag_runtime()
    except Exception:  # noqa: BLE001
        pass
    yield

app = create_app(
    "workflow_service",
    description='Workflow definition / DAG execution / monitoring '
                '(P3-3-W2 + P4-6-W2 dag_v2 + director studio)',
    version='0.2.0',
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

if HAS_LEGACY and legacy_scheduler_router is not None:
    app.include_router(legacy_scheduler_router)

app.include_router(workflow_router)
app.include_router(templates_router)

# P4-6-W2: dag_v2 (AdvancedDAGEngine + visual editor + operator marketplace)
# + director (Story → Visual → Assembly 3-module studio)
try:
    from services.workflow_service.dag_v2.routes import router as dag_v2_router
    app.include_router(dag_v2_router)
except Exception as e:  # noqa: BLE001
    import logging as _lg
    _lg.getLogger(__name__).warning("dag_v2 router unavailable: %s", e)
try:
    from services.workflow_service.director.routes import router as director_router
    app.include_router(director_router)
except Exception as e:  # noqa: BLE001
    import logging as _lg
    _lg.getLogger(__name__).warning("director router unavailable: %s", e)
app.include_router(editor_router)

@app.get("/")
async def root():
    from services.workflow_service.templates import WORKFLOW_TEMPLATES
    from services.workflow_service.dag_v2.operators import market_summary
    return {
        "service": "workflow-service",
        "version": "0.2.0",
        "port": 8009,
        "templates_count": len(WORKFLOW_TEMPLATES),
        "operator_marketplace": market_summary(),
        "endpoints": {
            "workflows": ["/api/v1/workflows", "/api/v1/workflows/{id}"],
            "execute": [
                "/api/v1/workflows/{id}/run",
                "/api/v1/workflows/runs/{run_id}",
            ],
            "templates": [
                "/api/v1/workflows/templates",
                "/api/v1/workflows/templates/{template_id}",
            ],
            "editor": [
                "/api/v1/workflow/editor/transitions",
                "/api/v1/workflow/editor/effects",
                "/api/v1/workflow/editor/montages",
                "/api/v1/workflow/editor/cut",
                "/api/v1/workflow/editor/detect_cuts",
                "/api/v1/workflow/editor/transition",
                "/api/v1/workflow/editor/effect",
                "/api/v1/workflow/editor/montage",
                "/api/v1/workflow/editor/render",
                "/api/v1/workflow/editor/projects",
            ],
            "dag_v2": [
                "/api/v1/workflow/dag",
                "/api/v1/workflow/dag/{id}/run",
                "/api/v1/workflow/dag/{id}/visual",
                "/api/v1/workflow/dag/{id}/layout",
                "/api/v1/workflow/dag/import-flow",
                "/api/v1/workflow/operators",
                "/api/v1/workflow/operators/{id}/schema",
            ],
            "director": [
                "/api/v1/workflow/director/run",
                "/api/v1/workflow/director/session",
                "/api/v1/workflow/director/session/{id}/story",
                "/api/v1/workflow/director/session/{id}/visual",
                "/api/v1/workflow/director/session/{id}/assemble",
            ],
            "healthz": ["/healthz"],
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="workflow_service",
        adapter=MultimodalAdapter(service_id="workflow_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for workflow_service: %%s", _mm_err)


__all__ = ["app"]
