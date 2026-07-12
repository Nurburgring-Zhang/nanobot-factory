"""VDP-2026 R3-R10 — Orchestration HTTP routes.

Endpoints expose the cross-module bus + lineage queries used by every
management view that needs to render "where does this row come from" or
"what is the platform doing right now" without bespoke joins.

  GET  /api/v1/orchestration/events           Query bus events
  GET  /api/v1/orchestration/stats            Platform-wide counters
  GET  /api/v1/orchestration/lifecycle        Per-stage counts in the 8-stage pipeline
  GET  /api/v1/orchestration/lineage          Find parents + children for an entity
  POST /api/v1/orchestration/lineage          Add a lineage link (e.g. dataset → export)
  POST /api/v1/orchestration/events           Record a manual event (other modules' hooks)
  GET  /api/v1/orchestration/health
  GET  /api/v1/orchestration/graph            Edge/relation list (for the platform map)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Body

from .bus import (
    RELATION_GRAPH,
    ENTITY_GROUPS,
    configure_db,
    get_bus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/orchestration", tags=["orchestration"])


@router.get("/events")
async def events(
    topic: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    dataset_id: Optional[str] = Query(None),
    pack_id: Optional[str] = Query(None),
    delivery_id: Optional[str] = Query(None),
    source_module: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=5000),
) -> Dict[str, Any]:
    bus = get_bus()
    rows = bus.query(
        topic=topic,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        dataset_id=dataset_id,
        pack_id=pack_id,
        delivery_id=delivery_id,
        source_module=source_module,
        limit=limit,
    )
    return {"total": len(rows), "items": rows}


@router.get("/stats")
async def stats() -> Dict[str, Any]:
    bus = get_bus()
    return bus.stats()


@router.get("/lifecycle")
async def lifecycle() -> Dict[str, Any]:
    bus = get_bus()
    return bus.lifecycle_summary()


@router.get("/lineage")
async def lineage(
    entity_type: str = Query(...),
    entity_id: str = Query(...),
) -> Dict[str, Any]:
    bus = get_bus()
    return bus.lineage_for(entity_type, entity_id)


@router.post("/lineage")
async def add_lineage(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    required = {"parent_type", "parent_id", "child_type", "child_id", "relation"}
    missing = required - set(payload.keys())
    if missing:
        raise HTTPException(400, f"missing fields: {sorted(missing)}")  # noqa: B904
    bus = get_bus()
    new_id = bus.record_lineage(
        parent_type=str(payload["parent_type"]),
        parent_id=str(payload["parent_id"]),
        child_type=str(payload["child_type"]),
        child_id=str(payload["child_id"]),
        relation=str(payload["relation"]),
        metadata=payload.get("metadata") or {},
    )
    return {"ok": True, "id": new_id}


@router.post("/events")
async def post_event(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    bus = get_bus()
    if "topic" not in payload:
        raise HTTPException(400, "missing topic")  # noqa: B904
    new_id = bus.record(
        topic=str(payload["topic"]),
        entity_type=str(payload.get("entity_type", "")),
        entity_id=str(payload.get("entity_id", "")),
        payload=payload.get("payload") or {},
        actor=str(payload.get("actor", "system")),
        refs=payload.get("refs") or {},
        source_module=str(payload.get("source_module", "external")),
    )
    return {"ok": True, "id": new_id}


@router.get("/graph")
async def graph() -> Dict[str, Any]:
    return {
        "entity_groups": ENTITY_GROUPS,
        "relations": [
            {"from": p.value, "to": c.value, "relation": rel}
            for p, c, rel in RELATION_GRAPH
        ],
    }


@router.get("/health")
async def health() -> Dict[str, Any]:
    bus = get_bus()
    return {"status": "ok", "bus": bus.stats()}
