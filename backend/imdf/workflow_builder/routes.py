"""VDP-2026 R2 — Workflow builder routes.

Endpoint summary
----------------

  GET    /api/v1/workflow_builder/templates                 — list starter templates
  POST   /api/v1/workflow_builder/templates/reload          — force-reload starter templates
  GET    /api/v1/workflow_builder/workflows                 — list user workflows
  POST   /api/v1/workflow_builder/workflows                 — save workflow (upsert)
  GET    /api/v1/workflow_builder/workflows/{id}            — load one
  DELETE /api/v1/workflow_builder/workflows/{id}            — delete
  POST   /api/v1/workflow_builder/workflows/{id}/run        — run workflow synchronously
  GET    /api/v1/workflow_builder/runs                      — recent runs
  GET    /api/v1/workflow_builder/runs/{id}                 — single run
  GET    /api/v1/workflow_builder/health
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Body

from .engine import (
    WorkflowEngine,
    Workflow,
    WorkflowNode,
    WorkflowEdge,
    build_starter_templates,
    get_engine,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow_builder", tags=["workflow_builder"])


# ----- templates ----------------------------------------------------------


@router.get("/templates")
async def list_templates() -> Dict[str, Any]:
    return {
        "total": len(build_starter_templates()),
        "items": [w.to_dict() for w in build_starter_templates()],
    }


@router.post("/templates/reload")
async def reload_templates() -> Dict[str, Any]:
    eng = get_engine()
    n = 0
    for tpl in build_starter_templates():
        eng.save_workflow(tpl)
        n += 1
    return {"ok": True, "loaded": n}


# ----- workflows ----------------------------------------------------------


@router.get("/workflows")
async def list_workflows(
    project_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> Dict[str, Any]:
    eng = get_engine()
    items = eng.list_workflows(project_id=project_id, limit=limit)
    return {"total": len(items), "items": [w.to_dict() for w in items]}


@router.post("/workflows")
async def save_workflow(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    wf = Workflow.from_dict(payload)
    eng = get_engine()
    eng.save_workflow(wf)
    return wf.to_dict()


@router.get("/workflows/{wf_id}")
async def get_workflow(wf_id: str) -> Dict[str, Any]:
    eng = get_engine()
    wf = eng.get_workflow(wf_id)
    if wf is None:
        raise HTTPException(404, f"未知工作流: {wf_id}")  # noqa: B904
    return wf.to_dict()


@router.delete("/workflows/{wf_id}")
async def delete_workflow(wf_id: str) -> Dict[str, Any]:
    eng = get_engine()
    ok = eng.delete_workflow(wf_id)
    if not ok:
        raise HTTPException(404, f"未知工作流: {wf_id}")  # noqa: B904
    return {"ok": True, "id": wf_id}


@router.post("/workflows/{wf_id}/run")
async def run_workflow(
    wf_id: str,
    payload: Dict[str, Any] = Body(default_factory=dict),
) -> Dict[str, Any]:
    eng = get_engine()
    wf = eng.get_workflow(wf_id)
    if wf is None:
        raise HTTPException(404, f"未知工作流: {wf_id}")  # noqa: B904
    actor = (payload or {}).get("actor", "system")
    refs = (payload or {}).get("refs", {}) or {}
    run = eng.run_workflow(wf, actor=actor, refs=refs)
    return run.to_dict()


# ----- runs ---------------------------------------------------------------


@router.get("/runs")
async def list_runs(
    workflow_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> Dict[str, Any]:
    eng = get_engine()
    runs = eng.list_runs(workflow_id=workflow_id, limit=limit)
    return {"total": len(runs), "items": [r.to_dict() for r in runs]}


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    eng = get_engine()
    run = eng.get_run(run_id)
    if run is None:
        raise HTTPException(404, f"未知运行: {run_id}")  # noqa: B904
    return run.to_dict()


# ----- health -------------------------------------------------------------


@router.get("/health")
async def health() -> Dict[str, Any]:
    eng = get_engine()
    return {
        "status": "ok",
        "workflows_saved": len(eng.list_workflows(limit=1000)),
        "starter_templates": len(build_starter_templates()),
    }
