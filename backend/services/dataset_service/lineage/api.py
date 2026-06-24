"""P4-4-W2 lineage API router.

All endpoints are mounted under ``/api/v1/lineage`` (and ``/api/v1/lineage/visualize``).

Surface
-------
Collection
  POST /api/v1/lineage/collect                            — manual or driver collect
  POST /api/v1/lineage/collect/sql                        — parse + persist SQL
  POST /api/v1/lineage/collect/python                     — parse + persist Python AST
  POST /api/v1/lineage/collect/operator                   — record operator run
  POST /api/v1/lineage/collect/manual                     — record a single edge
  POST /api/v1/lineage/collect/pipeline-step              — record a P3-6 step

Graph
  GET  /api/v1/lineage/graph/{entity}                     — node + edges (1-hop)
  GET  /api/v1/lineage/graph/{entity}/upstream            — ancestors
  GET  /api/v1/lineage/graph/{entity}/downstream          — descendants
  GET  /api/v1/lineage/graph/full                         — full graph (paginated)
  POST /api/v1/lineage/graph/refresh                      — rebuild in-memory cache
  GET  /api/v1/lineage/graph/stats                        — node/edge counts

Impact
  GET  /api/v1/lineage/impact/{entity}                    — full impact report
  GET  /api/v1/lineage/impact/{entity}/upstream           — ancestors
  GET  /api/v1/lineage/impact/{entity}/downstream         — descendants
  POST /api/v1/lineage/impact/{entity}/notify             — build a notification plan

Visualize (UI-ready)
  GET  /api/v1/lineage/visualize/{entity}                 — vis.js / d3 / react-flow
  GET  /api/v1/lineage/visualize/dataset/{dataset}        — focus on one dataset
  GET  /api/v1/lineage/visualize/full                     — full graph (capped)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from . import collector
from .graph import get_graph
from .impact import get_analyzer
from .models import (
    Asset,
    Edge,
    Run,
    get_lineage_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/lineage", tags=["lineage"])


# ═════════════════════════════════════════════════════════════════════════════
# Pydantic request bodies
# ═════════════════════════════════════════════════════════════════════════════
class CollectSqlRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    target_entity: Optional[str] = None
    pipeline_id: str = ""


class CollectPythonRequest(BaseModel):
    script: str = Field(..., min_length=1)
    target_entity: Optional[str] = None
    pipeline_id: str = ""


class CollectOperatorRequest(BaseModel):
    operator_id: str = Field(..., min_length=1)
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(..., min_length=1)
    edge_type: str = "cleaned_by"
    pipeline_id: str = ""
    extra: Dict[str, Any] = Field(default_factory=dict)


class CollectManualRequest(BaseModel):
    from_entity: str = Field(..., min_length=1)
    to_entity: str = Field(..., min_length=1)
    edge_type: str = "manual"
    pipeline_id: str = ""
    note: str = ""


class CollectPipelineStepRequest(BaseModel):
    pipeline_id: str = Field(..., min_length=1)
    step_index: int = 0
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)
    operator_id: str = ""
    edge_type: str = "generated_by"


class NotifyImpactRequest(BaseModel):
    change_description: str = ""


# ═════════════════════════════════════════════════════════════════════════════
# Collection
# ═════════════════════════════════════════════════════════════════════════════
@router.post("/collect")
async def collect_dispatch(body: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a collect call by ``source`` field.

    Body shape::

        {
          "source": "sql" | "python" | "operator" | "manual" | "pipeline_step",
          ...rest
        }
    """
    source = (body.get("source") or "").lower()
    if source == "sql":
        return (
            collector.collect_from_sql(
                sql=body.get("sql", ""),
                target_entity=body.get("target_entity"),
                pipeline_id=body.get("pipeline_id", ""),
            ).to_dict()
        )
    if source == "python":
        return (
            collector.collect_from_python(
                script=body.get("script", ""),
                target_entity=body.get("target_entity"),
                pipeline_id=body.get("pipeline_id", ""),
            ).to_dict()
        )
    if source == "operator":
        return (
            collector.record_operator(
                operator_id=body.get("operator_id", ""),
                inputs=body.get("inputs") or [],
                outputs=body.get("outputs") or [],
                edge_type=body.get("edge_type", "cleaned_by"),
                pipeline_id=body.get("pipeline_id", ""),
                extra=body.get("extra") or {},
            ).to_dict()
        )
    if source == "manual":
        return (
            collector.record_manual(
                from_entity=body.get("from_entity", ""),
                to_entity=body.get("to_entity", ""),
                edge_type=body.get("edge_type", "manual"),
                pipeline_id=body.get("pipeline_id", ""),
                note=body.get("note", ""),
            ).to_dict()
        )
    if source == "pipeline_step":
        return (
            collector.record_pipeline_step(
                pipeline_id=body.get("pipeline_id", ""),
                step_index=int(body.get("step_index") or 0),
                inputs=body.get("inputs") or [],
                outputs=body.get("outputs") or [],
                operator_id=body.get("operator_id", ""),
                edge_type=body.get("edge_type", "generated_by"),
            ).to_dict()
        )
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        detail=f"unknown_source: {source!r}; expected sql|python|operator|manual|pipeline_step",
    )


@router.post("/collect/sql")
async def collect_sql(req: CollectSqlRequest) -> Dict[str, Any]:
    return collector.collect_from_sql(
        sql=req.sql, target_entity=req.target_entity, pipeline_id=req.pipeline_id
    ).to_dict()


@router.post("/collect/python")
async def collect_python(req: CollectPythonRequest) -> Dict[str, Any]:
    return collector.collect_from_python(
        script=req.script,
        target_entity=req.target_entity,
        pipeline_id=req.pipeline_id,
    ).to_dict()


@router.post("/collect/operator")
async def collect_operator(req: CollectOperatorRequest) -> Dict[str, Any]:
    return collector.record_operator(
        operator_id=req.operator_id,
        inputs=req.inputs,
        outputs=req.outputs,
        edge_type=req.edge_type,
        pipeline_id=req.pipeline_id,
        extra=req.extra,
    ).to_dict()


@router.post("/collect/manual")
async def collect_manual(req: CollectManualRequest) -> Dict[str, Any]:
    return collector.record_manual(
        from_entity=req.from_entity,
        to_entity=req.to_entity,
        edge_type=req.edge_type,
        pipeline_id=req.pipeline_id,
        note=req.note,
    ).to_dict()


@router.post("/collect/pipeline-step")
async def collect_pipeline_step(req: CollectPipelineStepRequest) -> Dict[str, Any]:
    return collector.record_pipeline_step(
        pipeline_id=req.pipeline_id,
        step_index=req.step_index,
        inputs=req.inputs,
        outputs=req.outputs,
        operator_id=req.operator_id,
        edge_type=req.edge_type,
    ).to_dict()


# ═════════════════════════════════════════════════════════════════════════════
# Graph
# ═════════════════════════════════════════════════════════════════════════════
@router.post("/graph/refresh")
async def graph_refresh(
    edge_type: Optional[str] = None,
    source: Optional[str] = None,
    pipeline_id: Optional[str] = None,
) -> Dict[str, Any]:
    stats = get_graph().refresh(
        edge_type=edge_type, source=source, pipeline_id=pipeline_id
    )
    return {"ok": True, "refreshed": stats}


@router.get("/graph/stats")
async def graph_stats() -> Dict[str, Any]:
    get_graph().refresh()  # cheap if unchanged; explicit refresh in API path
    return {"ok": True, "stats": get_graph().stats()}


@router.get("/graph/{entity}")
async def graph_node(entity: str) -> Dict[str, Any]:
    g = get_graph()
    g.refresh()
    node = g.node(entity)
    if node is None:
        # Auto-create a stub so the UI can still show it
        return {
            "ok": True,
            "entity": entity,
            "node": {
                "qualified_name": entity,
                "entity_type": "table",
                "name": entity.split(".")[-1],
                "stub": True,
            },
            "edges": [],
            "upstream": [],
            "downstream": [],
        }
    return {
        "ok": True,
        "entity": entity,
        "node": node,
        "edges": g.edges_of(entity),
        "upstream": g.neighbors_upstream(entity),
        "downstream": g.neighbors_downstream(entity),
    }


@router.get("/graph/{entity}/upstream")
async def graph_upstream(entity: str, depth: int = -1) -> Dict[str, Any]:
    g = get_graph()
    g.refresh()
    return {"ok": True, "entity": entity, "depth": depth, "upstream": g.neighbors_upstream(entity, depth=depth)}


@router.get("/graph/{entity}/downstream")
async def graph_downstream(entity: str, depth: int = -1) -> Dict[str, Any]:
    g = get_graph()
    g.refresh()
    return {"ok": True, "entity": entity, "depth": depth, "downstream": g.neighbors_downstream(entity, depth=depth)}


@router.get("/graph/full")
async def graph_full(
    edge_type: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    g = get_graph()
    g.refresh()
    snap = g.full_graph(edge_type=edge_type, limit=limit)
    return {"ok": True, "graph": snap}


# ═════════════════════════════════════════════════════════════════════════════
# Impact
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/impact/{entity}")
async def impact_full(entity: str) -> Dict[str, Any]:
    a = get_analyzer()
    # Make sure the graph is up-to-date before analysis
    get_graph().refresh()
    report = a.full_impact(entity)
    return {"ok": True, "impact": report.to_dict()}


@router.get("/impact/{entity}/upstream")
async def impact_upstream(entity: str) -> Dict[str, Any]:
    get_graph().refresh()
    return {"ok": True, "entity": entity, "upstream": get_analyzer().upstream(entity)}


@router.get("/impact/{entity}/downstream")
async def impact_downstream(entity: str) -> Dict[str, Any]:
    get_graph().refresh()
    return {"ok": True, "entity": entity, "downstream": get_analyzer().downstream(entity)}


@router.post("/impact/{entity}/notify")
async def impact_notify(entity: str, req: NotifyImpactRequest) -> Dict[str, Any]:
    get_graph().refresh()
    plan = get_analyzer().build_notification(
        entity, change_description=req.change_description
    )
    return {"ok": True, "plan": plan.to_dict()}


# ═════════════════════════════════════════════════════════════════════════════
# Visualize (UI-ready)
# NOTE: ``/visualize/full`` and ``/visualize/dataset/{dataset}`` MUST be
# defined before ``/visualize/{entity}`` — otherwise FastAPI matches
# "full" / "dataset" as entity names.
# ═════════════════════════════════════════════════════════════════════════════
@router.get("/visualize/full")
async def visualize_full(
    type: Optional[str] = None,
    limit: int = 100,
    format: str = Query("react-flow", pattern="^(react-flow|vis|d3|cytoscape)$"),
) -> Dict[str, Any]:
    """Full graph (capped) — for the "show me everything" view."""
    g = get_graph()
    g.refresh()
    snap = g.full_graph(limit=limit)
    nodes = snap["nodes"]
    if type:
        nodes = [n for n in nodes if n.get("entity_type") == type]
    edges = snap["edges"]
    return {
        "ok": True,
        "format": format,
        "type": type,
        "limit": limit,
        "graph": _format_for(nodes, edges, format),
    }


@router.get("/visualize/dataset/{dataset}")
async def visualize_dataset(
    dataset: str,
    format: str = Query("react-flow", pattern="^(react-flow|vis|d3|cytoscape)$"),
    depth: int = 2,
) -> Dict[str, Any]:
    """Convenience: visualize by dataset name (e.g. ``coco_v1``)."""
    candidates = [
        f"ds.{dataset}",
        f"dataset.{dataset}",
        dataset,
    ]
    g = get_graph()
    g.refresh()
    for c in candidates:
        if g.node(c):
            return await visualize_entity(c, format=format, depth=depth)
    return await visualize_entity(candidates[0], format=format, depth=depth)


@router.get("/visualize/{entity}")
async def visualize_entity(
    entity: str,
    format: str = Query("react-flow", pattern="^(react-flow|vis|d3|cytoscape)$"),
    depth: int = 2,
) -> Dict[str, Any]:
    """Return a UI-ready graph centred on *entity*.

    Supported formats
    -----------------
    * ``react-flow`` — nodes/edges with ``id``/``source``/``target``/``data``
    * ``vis``        — vis.js ``nodes``/``edges`` with ``id``/``from``/``to``
    * ``d3``         — ``nodes``/``links`` with ``source``/``target``
    * ``cytoscape``  — ``elements`` ``{data: {...}}``
    """
    get_graph().refresh()
    g = get_graph()
    # BFS collect (cap at depth)
    visited: set = set()
    frontier: List[tuple] = [(entity, 0)]
    collected: set = {entity}
    edges: List[Dict[str, Any]] = []
    while frontier:
        cur, d = frontier.pop(0)
        if d >= depth:
            continue
        for e in g.edges_of(cur):
            f, t = e.get("from"), e.get("to")
            if not f or not t:
                continue
            edges.append(e)
            for nxt in (f, t):
                if nxt not in collected:
                    collected.add(nxt)
                    frontier.append((nxt, d + 1))
        visited.add(cur)
    nodes = []
    for qn in collected:
        n = g.node(qn) or {
            "qualified_name": qn,
            "entity_type": "table",
            "name": qn.split(".")[-1],
        }
        nodes.append(n)
    return {
        "ok": True,
        "format": format,
        "entity": entity,
        "depth": depth,
        "graph": _format_for(nodes, edges, format),
    }


# ═════════════════════════════════════════════════════════════════════════════
# Formatters — one function per UI framework
# ═════════════════════════════════════════════════════════════════════════════
_NODE_COLOR = {
    "table": "#4A90E2",
    "column": "#7ED321",
    "dataset": "#F5A623",
    "pipeline": "#BD10E0",
    "model": "#D0021B",
    "job": "#9013FE",
}
_NODE_SHAPE = {
    "table": "box",
    "column": "ellipse",
    "dataset": "box",
    "pipeline": "diamond",
    "model": "star",
    "job": "ellipse",
}
_EDGE_COLOR = {
    "derived_from": "#9013FE",
    "copied_to": "#4A90E2",
    "cleaned_by": "#F5A623",
    "scored_by": "#D0021B",
    "trained_by": "#7ED321",
    "generated_by": "#BD10E0",
    "refreshed_by": "#50E3C2",
    "manual": "#9B9B9B",
}


def _format_for(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    fmt: str,
) -> Dict[str, Any]:
    fmt = (fmt or "react-flow").lower()
    if fmt == "react-flow":
        return {
            "nodes": [
                {
                    "id": n["qualified_name"],
                    "type": _NODE_SHAPE.get(n.get("entity_type", "table"), "default"),
                    "data": {
                        "label": n.get("name", n["qualified_name"]),
                        "entity_type": n.get("entity_type", "table"),
                        "owner": n.get("owner", ""),
                        "team": n.get("team", ""),
                        "tier": n.get("tier", "bronze"),
                        "status": n.get("status", "active"),
                    },
                    "position": {"x": 0, "y": 0},
                    "style": {
                        "background": _NODE_COLOR.get(n.get("entity_type", "table"), "#888"),
                        "color": "#fff",
                    },
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": f"{e['from']}->{e['to']}::{e['edge_type']}::{e.get('source', 'manual')}",
                    "source": e["from"],
                    "target": e["to"],
                    "label": e.get("edge_type", "manual"),
                    "type": "default",
                    "data": {
                        "edge_type": e.get("edge_type", "manual"),
                        "source": e.get("source", "manual"),
                        "pipeline_id": e.get("pipeline_id", ""),
                    },
                    "style": {
                        "stroke": _EDGE_COLOR.get(e.get("edge_type", "manual"), "#888"),
                    },
                }
                for e in edges
            ],
        }
    if fmt == "vis":
        return {
            "nodes": [
                {
                    "id": n["qualified_name"],
                    "label": n.get("name", n["qualified_name"]),
                    "group": n.get("entity_type", "table"),
                    "color": {
                        "background": _NODE_COLOR.get(n.get("entity_type", "table"), "#888"),
                        "border": "#222",
                    },
                    "shape": _NODE_SHAPE.get(n.get("entity_type", "table"), "box"),
                    "title": (
                        f"{n.get('entity_type','table')} · {n.get('owner','')} · "
                        f"{n.get('team','')} · {n.get('tier','bronze')}"
                    ),
                }
                for n in nodes
            ],
            "edges": [
                {
                    "id": f"{e['from']}->{e['to']}::{e['edge_type']}",
                    "from": e["from"],
                    "to": e["to"],
                    "label": e.get("edge_type", "manual"),
                    "color": {"color": _EDGE_COLOR.get(e.get("edge_type", "manual"), "#888")},
                    "arrows": "to",
                }
                for e in edges
            ],
        }
    if fmt == "d3":
        return {
            "nodes": [
                {
                    "id": n["qualified_name"],
                    "name": n.get("name", n["qualified_name"]),
                    "group": n.get("entity_type", "table"),
                }
                for n in nodes
            ],
            "links": [
                {
                    "source": e["from"],
                    "target": e["to"],
                    "value": 1,
                    "type": e.get("edge_type", "manual"),
                }
                for e in edges
            ],
        }
    if fmt == "cytoscape":
        return {
            "elements": {
                "nodes": [
                    {
                        "data": {
                            "id": n["qualified_name"],
                            "label": n.get("name", n["qualified_name"]),
                            "entity_type": n.get("entity_type", "table"),
                        }
                    }
                    for n in nodes
                ],
                "edges": [
                    {
                        "data": {
                            "id": f"{e['from']}->{e['to']}::{e['edge_type']}",
                            "source": e["from"],
                            "target": e["to"],
                            "edge_type": e.get("edge_type", "manual"),
                        }
                    }
                    for e in edges
                ],
            }
        }
    # Fallback
    return {"nodes": nodes, "edges": edges}


__all__ = ["router"]
