"""P4-6-W2: FastAPI router for the dag_v2 surface.

Mounted by ``workflow_service.main`` at ``/api/v1/workflow/...`` (note:
singular ``workflow`` to avoid colliding with the P3-3-W2
``/api/v1/workflows/...`` plural endpoints).

Endpoints
---------
* ``GET    /api/v1/workflow/dag``                 list DAGs
* ``POST   /api/v1/workflow/dag``                 create DAG
* ``GET    /api/v1/workflow/dag/{id}``            get DAG
* ``PUT    /api/v1/workflow/dag/{id}``            update DAG
* ``DELETE /api/v1/workflow/dag/{id}``            delete DAG
* ``POST   /api/v1/workflow/dag/{id}/run``        start run
* ``GET    /api/v1/workflow/dag/runs``            list runs
* ``GET    /api/v1/workflow/dag/runs/{run_id}``   one run
* ``POST   /api/v1/workflow/dag/runs/{run_id}/cancel``
* ``GET    /api/v1/workflow/dag/{id}/visual``     Vue Flow JSON
* ``POST   /api/v1/workflow/dag/{id}/layout``     recompute layout
* ``POST   /api/v1/workflow/dag/import-flow``     import Vue Flow JSON
* ``GET    /api/v1/workflow/operators``           list operators
* ``GET    /api/v1/workflow/operators/summary``   marketplace summary
* ``GET    /api/v1/workflow/operators/{id}/schema``  operator input/output schema
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from .engine import (
    AdvancedDAGEngine,
    DAGEdge,
    DAGDefinition,
    DAGNode,
    EdgeType,
    ErrorPolicy,
    ExecMode,
    NodeType,
    get_advanced_dag_engine,
)
from .operators import (
    CATEGORIES,
    market_summary,
    operator_schema,
    list_operators,
    search_operators,
)
from .visual import (
    auto_layout,
    dag_to_flow_json,
    flow_json_to_dag,
    LayoutEngine,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workflow", tags=["dag-v2"])


# =====================================================================
# Pydantic models
# =====================================================================

class EdgeModel(BaseModel):
    source: str
    target: str
    edge_type: str = "data"
    source_handle: str = "out"
    target_handle: str = "in"
    condition: Optional[str] = None

    @field_validator("edge_type")
    @classmethod
    def _v_et(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {e.value for e in EdgeType}:
            raise ValueError(f"invalid edge_type: {v!r}")
        return v


class NodeModel(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    node_type: str = "transform"
    operator_id: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    inputs: List[str] = Field(default_factory=list)
    retry_max: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=60, ge=1, le=3600)
    error_policy: str = "retry"
    fallback_node_id: Optional[str] = None
    position: List[float] = Field(default_factory=lambda: [0.0, 0.0])
    description: str = ""

    @field_validator("node_type")
    @classmethod
    def _v_nt(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {n.value for n in NodeType}:
            raise ValueError(f"invalid node_type: {v!r}")
        return v

    @field_validator("error_policy")
    @classmethod
    def _v_ep(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {p.value for p in ErrorPolicy}:
            raise ValueError(f"invalid error_policy: {v!r}")
        return v

    def to_dag_node(self) -> DAGNode:
        return DAGNode(
            id=self.id, name=self.name,
            node_type=NodeType(self.node_type),
            operator_id=self.operator_id,
            config=self.config,
            inputs=list(self.inputs),
            retry_max=self.retry_max,
            timeout_seconds=self.timeout_seconds,
            error_policy=ErrorPolicy(self.error_policy),
            fallback_node_id=self.fallback_node_id,
            position=(float(self.position[0]), float(self.position[1])),
            description=self.description,
        )


class DAGCreate(BaseModel):
    id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=1024)
    nodes: List[NodeModel] = Field(default_factory=list)
    edges: List[EdgeModel] = Field(default_factory=list)
    exec_mode: str = "parallel"
    tags: List[str] = Field(default_factory=list)
    owner: str = Field(default="system", max_length=64)

    @field_validator("exec_mode")
    @classmethod
    def _v_em(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {m.value for m in ExecMode}:
            raise ValueError(f"invalid exec_mode: {v!r}")
        return v

    def to_definition(self) -> DAGDefinition:
        nodes = [n.to_dag_node() for n in self.nodes]
        edges = [
            DAGEdge(
                source=e.source, target=e.target,
                edge_type=EdgeType(e.edge_type),
                source_handle=e.source_handle,
                target_handle=e.target_handle,
                condition=e.condition,
            )
            for e in self.edges
        ]
        return DAGDefinition(
            id=self.id or f"dag-{uuid.uuid4().hex[:12]}",
            name=self.name, description=self.description,
            nodes=nodes, edges=edges,
            exec_mode=ExecMode(self.exec_mode),
            tags=self.tags, owner=self.owner,
        )


class DAGUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[List[NodeModel]] = None
    edges: Optional[List[EdgeModel]] = None
    exec_mode: Optional[str] = None
    tags: Optional[List[str]] = None


class RunRequest(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)
    trigger: str = Field(default="manual", max_length=32)
    sync: bool = False


class FlowImport(BaseModel):
    payload: Dict[str, Any]
    name: Optional[str] = None


# =====================================================================
# Helpers
# =====================================================================

def _validate_dag(d: DAGDefinition) -> None:
    """Reject duplicate ids / unknown edges / cycles."""
    ids = [n.id for n in d.nodes]
    if len(set(ids)) != len(ids):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="duplicate_node_ids")
    by_id = set(ids)
    for n in d.nodes:
        for up in n.inputs:
            if up not in by_id:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"unknown upstream: {up!r} in {n.id!r}")
        if n.fallback_node_id and n.fallback_node_id not in by_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"unknown fallback: {n.fallback_node_id!r} in {n.id!r}")
    for e in d.edges:
        if e.source not in by_id or e.target not in by_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"edge references unknown node: {e.source}->{e.target}")
        if e.source == e.target:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"self-loop not allowed: {e.source}")


# =====================================================================
# DAG CRUD
# =====================================================================

@router.get("/dag")
async def list_dags(tag: Optional[str] = None,
                    limit: int = 100) -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    items = eng.list()
    if tag:
        items = [d for d in items if tag in d.tags]
    limit = max(1, min(limit, 500))
    return {
        "total": len(items),
        "items": [d.to_dict() for d in items[:limit]],
    }


@router.post("/dag", status_code=status.HTTP_201_CREATED)
async def create_dag(body: DAGCreate) -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    existing = eng.get(body.id or "")
    if body.id and existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail=f"dag_exists: {body.id}")
    defn = body.to_definition()
    _validate_dag(defn)
    eng.upsert(defn)
    return defn.to_dict()


@router.get("/dag/{dag_id}")
async def get_dag(dag_id: str) -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    d = eng.get(dag_id)
    if d is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"dag_not_found: {dag_id}")
    return d.to_dict()


@router.put("/dag/{dag_id}")
async def update_dag(dag_id: str, body: DAGUpdate) -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    d = eng.get(dag_id)
    if d is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"dag_not_found: {dag_id}")
    if body.name is not None:
        d.name = body.name
    if body.description is not None:
        d.description = body.description
    if body.tags is not None:
        d.tags = body.tags
    if body.exec_mode is not None:
        try:
            d.exec_mode = ExecMode(body.exec_mode)
        except ValueError:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail=f"bad exec_mode: {body.exec_mode!r}")
    if body.nodes is not None:
        d.nodes = [n.to_dag_node() for n in body.nodes]
    if body.edges is not None:
        d.edges = [
            DAGEdge(
                source=e.source, target=e.target,
                edge_type=EdgeType(e.edge_type),
                source_handle=e.source_handle,
                target_handle=e.target_handle,
                condition=e.condition,
            )
            for e in body.edges
        ]
    d.version += 1
    _validate_dag(d)
    eng.upsert(d)
    return d.to_dict()


@router.delete("/dag/{dag_id}")
async def delete_dag(dag_id: str) -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    ok = eng.delete(dag_id)
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"dag_not_found: {dag_id}")
    return {"success": True, "dag_id": dag_id}


# =====================================================================
# Runs
# =====================================================================

@router.post("/dag/{dag_id}/run")
async def run_dag(dag_id: str, body: RunRequest,
                  bg: BackgroundTasks) -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    d = eng.get(dag_id)
    if d is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"dag_not_found: {dag_id}")
    try:
        run = eng.start_run(dag_id, body.inputs, trigger=body.trigger)
    except KeyError as e:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=str(e))

    async def _runner(rid: str) -> None:
        try:
            await eng.execute(rid)
        except Exception as e:  # noqa: BLE001
            logger.exception("dag run %s crashed", rid)
            r = eng.get_run(rid)
            if r is not None:
                from .engine import RunStatus
                r.status = RunStatus.FAILED
                r.log.append(f"crashed: {e}")
                r.finished_at = datetime.utcnow().isoformat()

    if body.sync:
        await _runner(run.run_id)
        return eng.get_run(run.run_id).to_dict()
    bg.add_task(asyncio.create_task, _runner(run.run_id))
    return {
        "run_id": run.run_id,
        "workflow_id": dag_id,
        "status": "pending",
        "trigger": body.trigger,
        "started_at": run.started_at,
        "links": {
            "status": f"/api/v1/workflow/dag/runs/{run.run_id}",
            "cancel": f"/api/v1/workflow/dag/runs/{run.run_id}/cancel",
        },
    }


@router.get("/dag/runs")
async def list_runs(dag_id: Optional[str] = None,
                    limit: int = 50) -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    runs = eng.list_runs(workflow_id=dag_id, limit=max(1, min(limit, 200)))
    return {
        "total": len(runs),
        "items": [r.to_dict() for r in runs],
    }


@router.get("/dag/runs/{run_id}")
async def get_run(run_id: str) -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    r = eng.get_run(run_id)
    if r is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"run_not_found: {run_id}")
    return r.to_dict()


@router.post("/dag/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    ok = eng.request_cancel(run_id)
    if not ok:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"run_not_found: {run_id}")
    return {"success": True, "run_id": run_id, "cancel_requested": True}


# =====================================================================
# Visual editor
# =====================================================================

@router.get("/dag/{dag_id}/visual")
async def get_visual(dag_id: str,
                     direction: str = "LR") -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    d = eng.get(dag_id)
    if d is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"dag_not_found: {dag_id}")
    return dag_to_flow_json(d, layout=True, direction=direction)


@router.post("/dag/{dag_id}/layout")
async def recompute_layout(dag_id: str,
                           engine: str = "dagre",
                           direction: str = "LR",
                           persist: bool = True) -> Dict[str, Any]:
    """Recompute node positions via the chosen layout engine."""
    eng = get_advanced_dag_engine()
    d = eng.get(dag_id)
    if d is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"dag_not_found: {dag_id}")
    try:
        positions = auto_layout(d, engine=engine, direction=direction)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    if persist:
        for n in d.nodes:
            if n.id in positions:
                n.position = positions[n.id]
        d.version += 1
        eng.upsert(d)
    return {
        "dag_id": dag_id,
        "engine": engine,
        "direction": direction,
        "positions": {k: list(v) for k, v in positions.items()},
        "persisted": persist,
    }


@router.post("/dag/import-flow")
async def import_flow(body: FlowImport) -> Dict[str, Any]:
    """Import a Vue Flow JSON payload as a DAG."""
    eng = get_advanced_dag_engine()
    payload = body.payload or {}
    if body.name:
        payload["name"] = body.name
    try:
        defn = flow_json_to_dag(payload)
    except (KeyError, ValueError) as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"invalid_flow_payload: {e}")
    _validate_dag(defn)
    eng.upsert(defn)
    return defn.to_dict()


@router.get("/layout-engines")
async def list_layout_engines() -> Dict[str, Any]:
    return {"engines": LayoutEngine.list()}


# =====================================================================
# Operator marketplace
# =====================================================================

@router.get("/operators")
async def get_operators(q: Optional[str] = None,
                         category: Optional[str] = None,
                         limit: int = 200) -> Dict[str, Any]:
    """List operators in the marketplace.

    Optional filters: ``q`` (substring / token match) and ``category``.
    """
    items = search_operators(q or "", category=category)
    items = items[:max(1, min(limit, 1000))]
    return {
        "total": len(items),
        "query": q,
        "category": category,
        "items": [o.to_dict() for o in items],
    }


@router.get("/operators/summary")
async def operators_summary() -> Dict[str, Any]:
    return market_summary()


@router.get("/operators/categories")
async def operators_categories() -> Dict[str, Any]:
    return {
        "categories": CATEGORIES,
        "items": [{"name": c,
                   "count": len(list_operators(category=c))}
                  for c in CATEGORIES],
    }


@router.get("/operators/{op_id}/schema")
async def operators_schema(op_id: str) -> Dict[str, Any]:
    s = operator_schema(op_id)
    if s is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"operator_not_found: {op_id}")
    return s


# =====================================================================
# Summary / health
# =====================================================================

@router.get("/dag-stats/summary")
async def dag_stats() -> Dict[str, Any]:
    eng = get_advanced_dag_engine()
    runs = eng.list_runs(limit=500)
    by_status: Dict[str, int] = {}
    for r in runs:
        by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
    op = market_summary()
    return {
        "dags": len(eng.list()),
        "runs_total": len(runs),
        "runs_by_status": by_status,
        "operators": op,
        "layout_engines": LayoutEngine.list(),
    }


__all__ = ["router"]
