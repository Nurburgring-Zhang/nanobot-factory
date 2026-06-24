"""P3-3-W2 workflow-service routes.

Public REST surface:
  GET    /healthz                                      liveness
  GET    /api/v1/workflows                             list workflows
  POST   /api/v1/workflows                             create a workflow
  GET    /api/v1/workflows/{wf_id}                     get one workflow
  PUT    /api/v1/workflows/{wf_id}                     update
  DELETE /api/v1/workflows/{wf_id}                     delete
  POST   /api/v1/workflows/{wf_id}/run                 start a run
  GET    /api/v1/workflows/runs/{run_id}               run status
  POST   /api/v1/workflows/runs/{run_id}/cancel        cancel run
  GET    /api/v1/workflows/runs                        list runs
  GET    /api/v1/workflows/templates                   list templates
  GET    /api/v1/workflows/templates/{template_id}     one template
  POST   /api/v1/workflows/templates/{template_id}/clone
                                                         clone template -> workflow
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from services.workflow_service.dag import (
    NodeSpec, NodeStatus, WorkflowSpec, WorkflowStatus,
    get_dag_runtime,
)
from services.workflow_service.templates import (
    WORKFLOW_TEMPLATES, by_category, business_templates,
    categories, get_template,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["workflow-service"])


# =====================================================================
# Pydantic models
# =====================================================================

class NodeModel(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    node_type: str = Field(..., min_length=1, max_length=64)
    config: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)
    retry_max: int = Field(default=0, ge=0, le=10)
    timeout_seconds: int = Field(default=60, ge=1, le=3600)

    @field_validator("node_type")
    @classmethod
    def _v_node_type(cls, v: str) -> str:
        v = v.strip()
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("node_type must be alphanumeric/-/_")
        return v


class WorkflowCreate(BaseModel):
    id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=1024)
    nodes: List[NodeModel] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    owner: str = Field(default="system", max_length=64)


class WorkflowUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=1024)
    nodes: Optional[List[NodeModel]] = None
    tags: Optional[List[str]] = None


class RunRequest(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)
    trigger: str = Field(default="manual", max_length=32)
    sync: bool = Field(default=False, description="Wait for completion")


# =====================================================================
# Helpers
# =====================================================================

def _now() -> str:
    return datetime.utcnow().isoformat()


def _to_node_spec(n: NodeModel) -> NodeSpec:
    return NodeSpec(
        id=n.id, name=n.name, node_type=n.node_type,
        config=n.config, depends_on=list(n.depends_on),
        retry_max=n.retry_max, timeout_seconds=n.timeout_seconds,
    )


def _validate_nodes(nodes: List[NodeSpec]) -> None:
    ids = [n.id for n in nodes]
    if len(set(ids)) != len(ids):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="duplicate_node_ids")
    seen = set(ids)
    for n in nodes:
        for up in n.depends_on:
            if up not in seen:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"unknown upstream node: {up!r} in {n.id!r}",
                )


# =====================================================================
# Health
# =====================================================================

@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    rt = get_dag_runtime()
    runs = rt.list_runs(limit=500)
    return {
        "status": "ok",
        "service": "workflow-service",
        "version": "0.1.0",
        "templates": len(WORKFLOW_TEMPLATES),
        "workflows": len(rt.list_workflows()),
        "runs": len(runs),
    }


# =====================================================================
# Templates (read-only catalogue)
# =====================================================================

@router.get("/api/v1/workflows/templates")
async def list_templates(
    category: Optional[str] = None,
    q: Optional[str] = None,
) -> Dict[str, Any]:
    """List pre-built workflow templates.

    Optional filters: ``category`` (image/video/...) and ``q`` (substring
    match on name/description/tags).
    """
    items = WORKFLOW_TEMPLATES
    if category:
        items = by_category(category)
    if q:
        ql = q.lower()
        items = [
            t for t in items
            if ql in t["name"].lower()
            or ql in t["description"].lower()
            or any(ql in tag.lower() for tag in t["tags"])
        ]
    return {
        "total": len(items),
        "categories": categories(),
        "items": items,
    }


# =====================================================================
# P3-6-W2: business-template specific endpoints (25 export / pipeline /
# multimodal / feedback templates). These expose the same catalogue via
# dedicated paths so callers can request only the business-flow subset
# without filtering on every category.
# =====================================================================

_BUSINESS_CATEGORIES = {"export", "pipeline", "multimodal", "feedback"}


@router.get("/api/v1/workflows/templates/business")
async def list_business_templates(
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """List only the 25 P3-6-W2 business templates.

    Optional ``category`` filter restricts to one of:
      ``export`` (5) / ``pipeline`` (10) / ``multimodal`` (5) /
      ``feedback`` (5).
    """
    items = business_templates()
    if category:
        if category not in _BUSINESS_CATEGORIES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=(f"unknown business category: {category!r}; "
                        f"valid: {sorted(_BUSINESS_CATEGORIES)}"),
            )
        items = [t for t in items if t["category"] == category]
    return {
        "total": len(items),
        "business_categories": sorted(_BUSINESS_CATEGORIES),
        "items": items,
    }


@router.get("/api/v1/workflows/templates/categories/summary")
async def categories_summary() -> Dict[str, Any]:
    """Per-category count summary, splitting legacy vs business."""
    counts: Dict[str, int] = {}
    for t in WORKFLOW_TEMPLATES:
        counts[t["category"]] = counts.get(t["category"], 0) + 1
    business_count = sum(counts.get(c, 0) for c in _BUSINESS_CATEGORIES)
    legacy_count = sum(v for k, v in counts.items()
                       if k not in _BUSINESS_CATEGORIES)
    new_business_count = len(business_templates())
    return {
        "total": len(WORKFLOW_TEMPLATES),
        # Total templates whose category is one of the 4 business ones.
        # Includes legacy "export" entries — so it can exceed 25.
        "business_total": business_count,
        # Templates whose category is NOT one of the 4 business ones.
        "legacy_total": legacy_count,
        # Exactly the 25 P3-6-W2 templates.
        "p3_6_w2_new_total": new_business_count,
        "p3_6_w2_categories": sorted(_BUSINESS_CATEGORIES),
        "per_category": counts,
    }


@router.get("/api/v1/workflows/templates/{template_id}")
async def get_one_template(template_id: str) -> Dict[str, Any]:
    try:
        return get_template(template_id)
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"template_not_found: {template_id}")


@router.post("/api/v1/workflows/templates/{template_id}/clone",
             status_code=status.HTTP_201_CREATED)
async def clone_template(template_id: str, body: Optional[Dict[str, Any]] = None
                         ) -> Dict[str, Any]:
    """Clone a template into a new workflow (returns the created workflow)."""
    try:
        tpl = get_template(template_id)
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"template_not_found: {template_id}")
    body = body or {}
    wf_id = body.get("id") or f"wf-{uuid.uuid4().hex[:12]}"
    name = body.get("name") or f"{tpl['name']} (from template)"
    nodes = [_to_node_spec(NodeModel(**nd)) for nd in tpl["nodes"]]
    _validate_nodes(nodes)
    spec = WorkflowSpec(
        id=wf_id, name=name, description=tpl["description"],
        tags=list(tpl["tags"]) + ["from-template", tpl["id"]],
        owner=body.get("owner", "system"),
    )
    spec.nodes = nodes
    rt = get_dag_runtime()
    rt.upsert_workflow(spec)
    return spec.to_dict()


# =====================================================================
# Workflow CRUD
# =====================================================================

@router.get("/api/v1/workflows")
async def list_workflows(
    tag: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    limit = max(1, min(limit, 500))
    rt = get_dag_runtime()
    items = rt.list_workflows()
    if tag:
        items = [w for w in items if tag in w.tags]
    return {
        "total": len(items),
        "items": [w.to_dict() for w in items[:limit]],
    }


@router.post("/api/v1/workflows", status_code=status.HTTP_201_CREATED)
async def create_workflow(body: WorkflowCreate) -> Dict[str, Any]:
    wf_id = body.id or f"wf-{uuid.uuid4().hex[:12]}"
    nodes = [_to_node_spec(n) for n in body.nodes]
    _validate_nodes(nodes)
    spec = WorkflowSpec(
        id=wf_id, name=body.name, description=body.description,
        tags=body.tags, owner=body.owner,
    )
    spec.nodes = nodes
    rt = get_dag_runtime()
    existing = rt.get_workflow(wf_id)
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"workflow_exists: {wf_id}")
    rt.upsert_workflow(spec)
    return spec.to_dict()


@router.get("/api/v1/workflows/{wf_id}")
async def get_workflow(wf_id: str) -> Dict[str, Any]:
    rt = get_dag_runtime()
    wf = rt.get_workflow(wf_id)
    if wf is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"workflow_not_found: {wf_id}")
    return wf.to_dict()


@router.put("/api/v1/workflows/{wf_id}")
async def update_workflow(wf_id: str, body: WorkflowUpdate) -> Dict[str, Any]:
    rt = get_dag_runtime()
    wf = rt.get_workflow(wf_id)
    if wf is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"workflow_not_found: {wf_id}")
    if body.name is not None:
        wf.name = body.name
    if body.description is not None:
        wf.description = body.description
    if body.tags is not None:
        wf.tags = body.tags
    if body.nodes is not None:
        nodes = [_to_node_spec(n) for n in body.nodes]
        _validate_nodes(nodes)
        wf.nodes = nodes
    wf.version += 1
    rt.upsert_workflow(wf)
    return wf.to_dict()


@router.delete("/api/v1/workflows/{wf_id}")
async def delete_workflow(wf_id: str) -> Dict[str, Any]:
    rt = get_dag_runtime()
    ok = rt.delete_workflow(wf_id)
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"workflow_not_found: {wf_id}")
    return {"success": True, "workflow_id": wf_id}


# =====================================================================
# Run / execute
# =====================================================================

@router.post("/api/v1/workflows/{wf_id}/run")
async def run_workflow(wf_id: str, body: RunRequest,
                       bg: BackgroundTasks) -> Dict[str, Any]:
    rt = get_dag_runtime()
    wf = rt.get_workflow(wf_id)
    if wf is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"workflow_not_found: {wf_id}")
    try:
        run = rt.start_run(wf_id, body.inputs, trigger=body.trigger)
    except KeyError as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=str(e))

    async def _runner(rid: str) -> None:
        try:
            await rt.execute(rid)
        except Exception as e:  # noqa: BLE001
            logger.exception("workflow run %s crashed", rid)
            r = rt.get_run(rid)
            if r is not None:
                r.status = WorkflowStatus.FAILED
                r.log.append(f"crashed: {e}")
                r.finished_at = _now()

    if body.sync:
        await _runner(run.run_id)
        return rt.get_run(run.run_id).to_dict()

    bg.add_task(asyncio.create_task, _runner(run.run_id))
    return {
        "run_id": run.run_id,
        "workflow_id": wf_id,
        "status": "pending",
        "trigger": body.trigger,
        "started_at": run.started_at,
        "links": {
            "status": f"/api/v1/workflows/runs/{run.run_id}",
            "cancel": f"/api/v1/workflows/runs/{run.run_id}/cancel",
        },
    }


@router.get("/api/v1/workflows/runs")
async def list_runs(
    workflow_id: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    limit = max(1, min(limit, 200))
    rt = get_dag_runtime()
    runs = rt.list_runs(workflow_id=workflow_id, limit=limit)
    return {
        "total": len(runs),
        "items": [r.to_dict() for r in runs],
    }


@router.get("/api/v1/workflows/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    rt = get_dag_runtime()
    r = rt.get_run(run_id)
    if r is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"run_not_found: {run_id}")
    return r.to_dict()


@router.post("/api/v1/workflows/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> Dict[str, Any]:
    rt = get_dag_runtime()
    ok = rt.request_cancel(run_id)
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"run_not_found: {run_id}")
    return {"success": True, "run_id": run_id, "cancel_requested": True}


# =====================================================================
# Convenience: count summary
# =====================================================================

@router.get("/api/v1/workflows/stats/summary")
async def workflow_stats() -> Dict[str, Any]:
    rt = get_dag_runtime()
    runs = rt.list_runs(limit=500)
    by_status: Dict[str, int] = {}
    for r in runs:
        by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
    return {
        "workflows": len(rt.list_workflows()),
        "templates": len(WORKFLOW_TEMPLATES),
        "runs_total": len(runs),
        "runs_by_status": by_status,
        "categories": categories(),
    }


__all__ = ["router"]
