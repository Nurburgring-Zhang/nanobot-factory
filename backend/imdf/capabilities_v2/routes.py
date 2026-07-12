"""VDP-2026 v1.1 — Capability & dataflow HTTP routes.

All routes are mounted under `/api/v1/capabilities_v2` to keep them distinct
from the legacy OpenClaw capability surface.

Endpoints
---------

  GET    /capabilities_v2/catalogue                   — list all caps + categories
  GET    /capabilities_v2/categories                 — distinct categories only
  GET    /capabilities_v2/capabilities               — list (filter by ?category=&q=)
  GET    /capabilities_v2/capabilities/{id}          — describe one capability
  POST   /capabilities_v2/invoke                     — execute a capability call
  GET    /capabilities_v2/invocations                — list audit rows
  GET    /capabilities_v2/invocations/by-project/{p} — list invocations for project

  GET    /dataflow/stages                            — high-level stage counts
  GET    /dataflow/events                            — list recent events
  GET    /dataflow/snapshot                          — full lifecycle snapshot
  GET    /dataflow/health                            — health check
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Body

from .engine import get_registry, CapabilityCategory
from .dataflow import (
    get_tracker,
    SUBJECT_TO_STAGE,
    STAGES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/capabilities_v2", tags=["capabilities_v2"])

# separate router for /dataflow
flow_router = APIRouter(prefix="/api/v1/dataflow", tags=["dataflow"])


# ===========================================================================
# Catalogue / discovery
# ===========================================================================


@router.get("/catalogue")
async def catalogue() -> Dict[str, Any]:
    reg = get_registry()
    return reg.catalogue()


@router.get("/categories")
async def categories() -> Dict[str, Any]:
    reg = get_registry()
    return {"categories": reg.list_categories()}


@router.get("/capabilities")
async def list_capabilities(
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
) -> Dict[str, Any]:
    reg = get_registry()
    if category:
        try:
            cat = CapabilityCategory(category)
        except ValueError:
            raise HTTPException(404, f"unknown category '{category}'")  # noqa: B904
        caps = reg.list_by_category(cat)
    else:
        caps = reg.list_all()
    if q:
        ids = {c.id for c in reg.search(q)}
        caps = [c for c in caps if c.id in ids]
    return {
        "total": len(caps),
        "items": [c.describe() for c in caps],
    }


@router.get("/capabilities/{cap_id}")
async def describe_capability(cap_id: str) -> Dict[str, Any]:
    reg = get_registry()
    cap = reg.get(cap_id)
    if cap is None:
        raise HTTPException(404, f"unknown capability '{cap_id}'")  # noqa: B904
    return cap.describe()


@router.post("/invoke")
async def invoke_capability(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    cap_id = payload.get("capability_id")
    inputs = payload.get("inputs", {}) or {}
    actor = payload.get("actor", "system")
    refs = payload.get("refs", {}) or {}
    if not cap_id:
        raise HTTPException(400, "missing capability_id")  # noqa: B904
    reg = get_registry()
    res = reg.invoke(cap_id, inputs, actor=actor, refs=refs)
    if res.status == "error" and "unknown capability" in res.error:
        raise HTTPException(404, res.error)  # noqa: B904
    return res.to_dict()


@router.get("/invocations")
async def list_invocations(
    cap_id: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    reg = get_registry()
    rows = reg.list_invocations(cap_id=cap_id, ref_project_id=project_id, limit=limit)
    return {"total": len(rows), "items": rows}


@router.get("/invocations/by-project/{project_id}")
async def list_project_invocations(
    project_id: str,
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    reg = get_registry()
    rows = reg.list_invocations(ref_project_id=project_id, limit=limit)
    return {"total": len(rows), "items": rows}


@router.get("/health")
async def health() -> Dict[str, Any]:
    reg = get_registry()
    return {
        "status": "ok",
        "capabilities_registered": reg.count(),
        "categories": reg.list_categories(),
    }


# ===========================================================================
# Data flow tracker endpoints
# ===========================================================================


@flow_router.get("/stages")
async def stages_summary() -> Dict[str, Any]:
    tracker = get_tracker()
    bucket = tracker.stages_summary()
    return {
        "stages": [
            {**s, "event_count": bucket.get(s["key"], 0)}
            for s in STAGES
        ],
        "total_events": sum(bucket.values()),
    }


@flow_router.get("/events")
async def list_events(
    project_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=10_000),
) -> Dict[str, Any]:
    tracker = get_tracker()
    rows = tracker.list_events(project_id=project_id, limit=limit)
    return {"total": len(rows), "items": rows}


@flow_router.get("/snapshot")
async def snapshot(
    project_id: Optional[str] = Query(None),
    requirement_id: Optional[str] = Query(None),
    dataset_id: Optional[str] = Query(None),
    pack_id: Optional[str] = Query(None),
    delivery_id: Optional[str] = Query(None),
) -> Dict[str, Any]:
    tracker = get_tracker()
    snap = tracker.snapshot(
        project_id=project_id,
        requirement_id=requirement_id,
        dataset_id=dataset_id,
        pack_id=pack_id,
        delivery_id=delivery_id,
    )
    return snap.to_dict()


@flow_router.get("/subjects")
async def subject_to_stage_map() -> Dict[str, Any]:
    """Expose the subject → stage map so the frontend can colour labels."""
    return {
        "subject_to_stage": SUBJECT_TO_STAGE,
        "stages": STAGES,
    }


@flow_router.get("/health")
async def flow_health() -> Dict[str, Any]:
    tracker = get_tracker()
    rows = tracker.list_events(limit=10)
    return {
        "status": "ok",
        "events_recent": len(rows),
    }
