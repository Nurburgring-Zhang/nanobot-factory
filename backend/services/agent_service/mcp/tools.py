"""P4-3-W2: MCP tools — the 5 default tools exposed by the server.

Tools are how MCP clients *do things* with the agent.  Each tool is a
JSON-RPC call that returns a JSON object.  The default set covers the
two memory subsystems (MemoryPalace + Hindsight) plus a ``wake_up``
tool for "load everything relevant into context" scenarios.

The 5 tools:

  * ``mempalace_search``     — full-text search across wings / rooms
  * ``mempalace_retain``     — add a new room/drawer/item
  * ``mempalace_wake_up``    — return identity + recent wings
  * ``hindsight_search``     — 4-layer search (L0/L1/L2/L3)
  * ``hindsight_retain``     — verbatim store to L3

All handlers are pure-Python; they call into the
:mod:`memory_palace.manager` and :mod:`hindsight` modules.  No I/O
happens at import time, so this module is safe to import in tests.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .server import MCPTool


def _memory_palace_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """Search the MemoryPalace by keyword.

    ``args``::

        query: str
        level: str = "all"   # one of: L2_wing, L3_room, L4_drawer, all

    Returns a dict with a single ``matches`` list.
    """
    from services.agent_service.memory_palace import get_memory_palace

    palace = get_memory_palace()
    query = (args.get("query") or "").strip()
    if not query:
        return {"matches": [], "count": 0, "query": query}
    level = args.get("level") or "all"

    matches: List[Dict[str, Any]] = []
    if level in ("L2_wing", "all"):
        for w in palace.list_wings(limit=200):
            if query.lower() in (w.name + " " + w.description).lower() or any(
                query.lower() in (kw or "").lower() for kw in w.trigger_keywords
            ):
                matches.append({"level": "L2_wing", "record": w.to_dict()})
    if level in ("L3_room", "all"):
        for r in palace.list_rooms(limit=200):
            if query.lower() in (r.title + " " + r.summary).lower():
                matches.append({"level": "L3_room", "record": r.to_dict()})
    if level in ("L4_drawer", "all"):
        for d in palace.list_drawers(limit=500):
            if query.lower() in (d.title + " " + d.content).lower():
                matches.append({"level": "L4_drawer", "record": d.to_dict()})
    return {"matches": matches, "count": len(matches), "query": query, "level": level}


def _memory_palace_retain(args: Dict[str, Any]) -> Dict[str, Any]:
    """Add a new room (or drawer) to the MemoryPalace.

    ``args``::

        level:    "L2_wing" | "L3_room" | "L4_drawer"
        payload:  { name?, description?, trigger_keywords?, title?, summary?,
                    wing_id?, room_id?, content?, content_type?, metadata? }
    """
    from services.agent_service.memory_palace import get_memory_palace

    palace = get_memory_palace()
    level = (args.get("level") or "").strip()
    payload = args.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    if level == "L2_wing":
        if not payload.get("name"):
            raise ValueError("L2_wing payload requires 'name'")
        w = palace.create_wing(
            name=payload["name"],
            description=payload.get("description", ""),
            trigger_keywords=payload.get("trigger_keywords") or [],
            metadata=payload.get("metadata") or {},
        )
        return {"ok": True, "level": "L2_wing", "id": w.wing_id, "record": w.to_dict()}
    if level == "L3_room":
        if not (payload.get("wing_id") and payload.get("title")):
            raise ValueError("L3_room payload requires 'wing_id' and 'title'")
        r = palace.create_room(
            wing_id=payload["wing_id"],
            title=payload["title"],
            summary=payload.get("summary", ""),
            status=payload.get("status", "active"),
            metadata=payload.get("metadata") or {},
        )
        return {"ok": True, "level": "L3_room", "id": r.room_id, "record": r.to_dict()}
    if level == "L4_drawer":
        if not (payload.get("room_id") and payload.get("title")):
            raise ValueError("L4_drawer payload requires 'room_id' and 'title'")
        d = palace.create_drawer(
            room_id=payload["room_id"],
            title=payload["title"],
            content=payload.get("content", ""),
            content_type=payload.get("content_type", "text"),
            uri=payload.get("uri", ""),
            metadata=payload.get("metadata") or {},
        )
        return {"ok": True, "level": "L4_drawer", "id": d.drawer_id, "record": d.to_dict()}
    raise ValueError(f"unsupported level: {level!r}")


def _memory_palace_wake_up(args: Dict[str, Any]) -> Dict[str, Any]:
    """Return the most relevant context for "what should I remember?".

    Always returns L0 identity (from Hindsight) + a digest of the most
    recent L2/L3 records (from MemoryPalace).  This is what an agent
    pulls on cold start.
    """
    from services.agent_service.hindsight import get_hindsight
    from services.agent_service.memory_palace import get_memory_palace

    palace = get_memory_palace()
    hindsight = get_hindsight()

    identity_items = hindsight.list_identity(limit=10)
    recent_wings = palace.list_wings(limit=5)
    recent_rooms = palace.list_rooms(limit=10)
    return {
        "identity": [it.to_dict() for it in identity_items],
        "recent_wings": [w.to_dict() for w in recent_wings],
        "recent_rooms": [r.to_dict() for r in recent_rooms],
        "hindsight_stats": hindsight.stats(),
        "palace_stats": palace.stats(),
    }


def _hindsight_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """4-layer Hindsight search.

    ``args``::

        query: str
        layer: optional (L0_identity / L1_essential_story / L2_wing / L3_full)
        k:     int = 10
    """
    from services.agent_service.hindsight import get_hindsight

    hs = get_hindsight()
    query = (args.get("query") or "").strip()
    if not query:
        return {"results": [], "count": 0, "query": query}
    layer = args.get("layer")
    k = int(args.get("k") or 10)
    return {"results": hs.search(query, layer=layer, k=k), "count": min(k, len(hs.search(query, layer=layer, k=k))), "query": query}


def _hindsight_retain(args: Dict[str, Any]) -> Dict[str, Any]:
    """Verbatim store to Hindsight L3 (or L0 for identity).

    ``args``::

        content: str
        role:    "user" | "system" | "agent" | "tool"  (default "user")
        source:  optional source tag (e.g. "session:abc")
        layer:   "L3_full" (default) | "L0_identity"
    """
    from services.agent_service.hindsight import get_hindsight

    hs = get_hindsight()
    content = args.get("content")
    if not isinstance(content, str) or not content:
        raise ValueError("content must be a non-empty string")
    role = args.get("role") or "user"
    source = args.get("source") or ""
    layer = args.get("layer") or "L3_full"
    if layer == "L0_identity":
        item = hs.retain_identity(content, source=source or "soul", metadata=args.get("metadata"))
    else:
        item = hs.retain(content, role=role, source=source, layer=layer, metadata=args.get("metadata"))
    return {"ok": True, "id": item.item_id, "layer": item.layer, "role": item.role}


# ── Registry builder ────────────────────────────────────────────────────────
def build_default_tools() -> List[MCPTool]:
    return [
        MCPTool(
            name="mempalace_search",
            description=(
                "Search the MemoryPalace by keyword across wings (L2), rooms (L3) "
                "and drawers (L4).  Returns matching records + the level they matched at."
            ),
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "search query"},
                    "level": {
                        "type": "string",
                        "enum": ["L2_wing", "L3_room", "L4_drawer", "all"],
                        "default": "all",
                    },
                },
                "required": ["query"],
            },
            handler=_memory_palace_search,
        ),
        MCPTool(
            name="mempalace_retain",
            description=(
                "Add a new wing (L2), room (L3) or drawer (L4) to the MemoryPalace. "
                "Required payload keys depend on the level."
            ),
            schema={
                "type": "object",
                "properties": {
                    "level": {"type": "string", "enum": ["L2_wing", "L3_room", "L4_drawer"]},
                    "payload": {"type": "object"},
                },
                "required": ["level", "payload"],
            },
            handler=_memory_palace_retain,
        ),
        MCPTool(
            name="mempalace_wake_up",
            description=(
                "Return the most relevant long-term context for a fresh session: "
                "L0 identity (from Hindsight) + the most recent wings and rooms. "
                "Call this on session start."
            ),
            schema={"type": "object", "properties": {}},
            handler=_memory_palace_wake_up,
        ),
        MCPTool(
            name="hindsight_search",
            description=(
                "4-layer Hindsight search.  If layer is omitted, all four layers "
                "(L0 / L1 / L2 / L3) are scanned and the highest-scoring match wins."
            ),
            schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "layer": {
                        "type": "string",
                        "enum": [
                            "L0_identity",
                            "L1_essential_story",
                            "L2_wing",
                            "L3_full",
                        ],
                    },
                    "k": {"type": "integer", "default": 10, "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
            handler=_hindsight_search,
        ),
        MCPTool(
            name="hindsight_retain",
            description=(
                "Verbatim store to Hindsight.  Use L0_identity for SOUL.md-derived "
                "identity (immutable per session), L3_full for the verbatim agent log."
            ),
            schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "role": {"type": "string", "enum": ["user", "system", "agent", "tool"]},
                    "source": {"type": "string"},
                    "layer": {
                        "type": "string",
                        "enum": ["L0_identity", "L3_full"],
                        "default": "L3_full",
                    },
                },
                "required": ["content"],
            },
            handler=_hindsight_retain,
        ),
    ]


__all__ = ["build_default_tools"]
