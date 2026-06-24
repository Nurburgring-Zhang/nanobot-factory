"""P4-3-W2: routes for /api/v1/memory/palace + /api/v1/memory/hindsight.

The 6-layer MemoryPalace exposes 5 REST surfaces — one per persistent
table.  Each surface is a thin CRUD wrapper that delegates to
:mod:`services.agent_service.memory_palace.manager`.

The Hindsight surface exposes 3 endpoints: ``search``, ``retain`` and
``recall``.  The retain endpoint is the verbatim-write hot path; the
search endpoint runs the 4-layer stack described in
:mod:`services.agent_service.hindsight`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .hindsight import get_hindsight
from .memory_palace import get_memory_palace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


# ── Schemas ──────────────────────────────────────────────────────────────────
class WingCreate(BaseModel):
    name: str
    description: str = ""
    trigger_keywords: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class WingUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_keywords: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class RoomCreate(BaseModel):
    wing_id: str
    title: str
    summary: str = ""
    status: str = "active"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RoomUpdate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class DrawerCreate(BaseModel):
    room_id: str
    title: str
    content: str = ""
    content_type: str = "text"
    uri: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DrawerUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    content_type: Optional[str] = None
    uri: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class TunnelCreate(BaseModel):
    from_id: str
    to_id: str
    from_kind: str = "wing"
    to_kind: str = "wing"
    relation: str = "related"
    note: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ItemCreate(BaseModel):
    level: str
    parent_id: str
    content: str
    role: str = "user"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HindsightRetain(BaseModel):
    content: str
    role: str = "user"
    source: str = ""
    layer: str = "L3_full"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HindsightSearchQuery(BaseModel):
    query: str
    layer: Optional[str] = None
    k: int = 10


# ── MemoryPalace — meta ──────────────────────────────────────────────────────
@router.get("/palace/levels")
async def list_levels() -> Dict[str, Any]:
    """Return the 6 layer definitions."""
    from .memory_palace.levels import LEVELS

    return {
        "count": len(LEVELS),
        "levels": [
            {
                "level": lvl.value,
                "table": _TABLE_FOR_LEVEL.get(lvl.value, ""),
                "description": _DESC_FOR_LEVEL.get(lvl.value, ""),
            }
            for lvl in LEVELS
        ],
    }


@router.get("/palace/tables")
async def list_tables() -> Dict[str, Any]:
    """Return the 5 persistent tables (and their current row counts)."""
    palace = get_memory_palace()
    stats = palace.stats()
    return {
        "tables": [
            {"name": "memory_wings", "level": "L2_wing", "rows": stats.get("memory_wings", 0)},
            {"name": "memory_rooms", "level": "L3_room", "rows": stats.get("memory_rooms", 0)},
            {"name": "memory_drawers", "level": "L4_drawer", "rows": stats.get("memory_drawers", 0)},
            {"name": "memory_tunnels", "level": "L5_tunnel", "rows": stats.get("memory_tunnels", 0)},
            {"name": "memory_items", "level": "free_form", "rows": stats.get("memory_items", 0)},
        ],
    }


@router.get("/palace/stats")
async def palace_stats() -> Dict[str, Any]:
    return get_memory_palace().stats()


# ── L2 Wings ────────────────────────────────────────────────────────────────
@router.post("/palace/wings")
async def create_wing(body: WingCreate) -> Dict[str, Any]:
    w = get_memory_palace().create_wing(
        name=body.name,
        description=body.description,
        trigger_keywords=body.trigger_keywords,
        metadata=body.metadata,
    )
    return w.to_dict()


@router.get("/palace/wings")
async def list_wings(limit: int = 200) -> Dict[str, Any]:
    items = get_memory_palace().list_wings(limit=limit)
    return {"count": len(items), "items": [w.to_dict() for w in items]}


@router.get("/palace/wings/{wing_id}")
async def get_wing(wing_id: str) -> Dict[str, Any]:
    w = get_memory_palace().get_wing(wing_id)
    if w is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="wing_not_found")
    return w.to_dict()


@router.put("/palace/wings/{wing_id}")
async def update_wing(wing_id: str, body: WingUpdate) -> Dict[str, Any]:
    w = get_memory_palace().update_wing(
        wing_id,
        name=body.name,
        description=body.description,
        trigger_keywords=body.trigger_keywords,
        metadata=body.metadata,
    )
    if w is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="wing_not_found")
    return w.to_dict()


@router.delete("/palace/wings/{wing_id}")
async def delete_wing(wing_id: str) -> Dict[str, Any]:
    ok = get_memory_palace().delete_wing(wing_id)
    return {"wing_id": wing_id, "deleted": ok}


# ── L3 Rooms ────────────────────────────────────────────────────────────────
@router.post("/palace/rooms")
async def create_room(body: RoomCreate) -> Dict[str, Any]:
    if get_memory_palace().get_wing(body.wing_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="wing_not_found")
    r = get_memory_palace().create_room(
        wing_id=body.wing_id,
        title=body.title,
        summary=body.summary,
        status=body.status,
        metadata=body.metadata,
    )
    return r.to_dict()


@router.get("/palace/rooms")
async def list_rooms(
    wing_id: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    items = get_memory_palace().list_rooms(wing_id=wing_id, status=status_filter, limit=limit)
    return {"count": len(items), "items": [r.to_dict() for r in items]}


@router.get("/palace/rooms/{room_id}")
async def get_room(room_id: str) -> Dict[str, Any]:
    r = get_memory_palace().get_room(room_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="room_not_found")
    return r.to_dict()


@router.put("/palace/rooms/{room_id}")
async def update_room(room_id: str, body: RoomUpdate) -> Dict[str, Any]:
    r = get_memory_palace().update_room(
        room_id,
        title=body.title,
        summary=body.summary,
        status=body.status,
        metadata=body.metadata,
    )
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="room_not_found")
    return r.to_dict()


@router.delete("/palace/rooms/{room_id}")
async def delete_room(room_id: str) -> Dict[str, Any]:
    ok = get_memory_palace().delete_room(room_id)
    return {"room_id": room_id, "deleted": ok}


# ── L4 Drawers ──────────────────────────────────────────────────────────────
@router.post("/palace/drawers")
async def create_drawer(body: DrawerCreate) -> Dict[str, Any]:
    if get_memory_palace().get_room(body.room_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="room_not_found")
    d = get_memory_palace().create_drawer(
        room_id=body.room_id,
        title=body.title,
        content=body.content,
        content_type=body.content_type,
        uri=body.uri,
        metadata=body.metadata,
    )
    return d.to_dict()


@router.get("/palace/drawers")
async def list_drawers(room_id: Optional[str] = None, limit: int = 500) -> Dict[str, Any]:
    items = get_memory_palace().list_drawers(room_id=room_id, limit=limit)
    return {"count": len(items), "items": [d.to_dict() for d in items]}


@router.get("/palace/drawers/{drawer_id}")
async def get_drawer(drawer_id: str) -> Dict[str, Any]:
    d = get_memory_palace().get_drawer(drawer_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="drawer_not_found")
    return d.to_dict()


@router.put("/palace/drawers/{drawer_id}")
async def update_drawer(drawer_id: str, body: DrawerUpdate) -> Dict[str, Any]:
    d = get_memory_palace().update_drawer(
        drawer_id,
        title=body.title,
        content=body.content,
        content_type=body.content_type,
        uri=body.uri,
        metadata=body.metadata,
    )
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="drawer_not_found")
    return d.to_dict()


@router.delete("/palace/drawers/{drawer_id}")
async def delete_drawer(drawer_id: str) -> Dict[str, Any]:
    ok = get_memory_palace().delete_drawer(drawer_id)
    return {"drawer_id": drawer_id, "deleted": ok}


# ── L5 Tunnels ──────────────────────────────────────────────────────────────
@router.post("/palace/tunnels")
async def create_tunnel(body: TunnelCreate) -> Dict[str, Any]:
    t = get_memory_palace().create_tunnel(
        from_id=body.from_id,
        to_id=body.to_id,
        from_kind=body.from_kind,
        to_kind=body.to_kind,
        relation=body.relation,
        note=body.note,
        metadata=body.metadata,
    )
    return t.to_dict()


@router.get("/palace/tunnels")
async def list_tunnels(anchor_id: Optional[str] = None, limit: int = 200) -> Dict[str, Any]:
    items = get_memory_palace().list_tunnels(anchor_id=anchor_id, limit=limit)
    return {"count": len(items), "items": [t.to_dict() for t in items]}


@router.delete("/palace/tunnels/{tunnel_id}")
async def delete_tunnel(tunnel_id: str) -> Dict[str, Any]:
    ok = get_memory_palace().delete_tunnel(tunnel_id)
    return {"tunnel_id": tunnel_id, "deleted": ok}


# ── Free-form Items ─────────────────────────────────────────────────────────
@router.post("/palace/items")
async def create_item(body: ItemCreate) -> Dict[str, Any]:
    it = get_memory_palace().create_item(
        level=body.level,
        parent_id=body.parent_id,
        content=body.content,
        role=body.role,
        metadata=body.metadata,
    )
    return it.to_dict()


@router.get("/palace/items")
async def list_items(
    level: Optional[str] = None,
    parent_id: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    items = get_memory_palace().list_items(level=level, parent_id=parent_id, limit=limit)
    return {"count": len(items), "items": [it.to_dict() for it in items]}


@router.get("/palace/items/search")
async def search_items(
    query: str,
    level: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    items = get_memory_palace().search_items(query=query, level=level, limit=limit)
    return {"count": len(items), "query": query, "items": [it.to_dict() for it in items]}


# ── Hindsight ────────────────────────────────────────────────────────────────
@router.post("/hindsight/retain")
async def hindsight_retain(body: HindsightRetain) -> Dict[str, Any]:
    hs = get_hindsight()
    if body.layer == "L0_identity":
        item = hs.retain_identity(body.content, source=body.source or "soul", metadata=body.metadata)
    else:
        item = hs.retain(
            body.content,
            role=body.role,
            source=body.source,
            layer=body.layer,
            metadata=body.metadata,
        )
    return item.to_dict()


@router.post("/hindsight/search")
async def hindsight_search(body: HindsightSearchQuery) -> Dict[str, Any]:
    hs = get_hindsight()
    results = hs.search(body.query, layer=body.layer, k=body.k)
    return {"count": len(results), "query": body.query, "results": results}


@router.get("/hindsight/recall/{item_id}")
async def hindsight_recall(item_id: str) -> Dict[str, Any]:
    item = get_hindsight().recall(item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="item_not_found")
    return item.to_dict()


@router.get("/hindsight/stats")
async def hindsight_stats() -> Dict[str, Any]:
    return get_hindsight().stats()


# ── Static helpers (used by /palace/levels) ─────────────────────────────────
_TABLE_FOR_LEVEL: Dict[str, str] = {
    "L0_identity": "agent_memory (legacy)",
    "L1_essential_story": "agent_memory (legacy)",
    "L2_wing": "memory_wings",
    "L3_room": "memory_rooms",
    "L4_drawer": "memory_drawers",
    "L5_tunnel": "memory_tunnels",
}

_DESC_FOR_LEVEL: Dict[str, str] = {
    "L0_identity": "Immutable identity, derived from SOUL.md.",
    "L1_essential_story": "Project-level core info, LLM-compressable.",
    "L2_wing": "Theme / topic trigger (e.g. prompt engineering).",
    "L3_room": "Concrete event / project / task.",
    "L4_drawer": "Document / resource / artefact inside a room.",
    "L5_tunnel": "Cross-wing bridge (relates / causes / blocks / mirrors).",
}


__all__ = ["router"]
