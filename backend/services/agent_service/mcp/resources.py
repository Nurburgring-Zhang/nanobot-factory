"""P4-3-W2: MCP resources — read-only views over the memory surface.

Resources are how MCP clients *read* the agent's current state without
making a tool call.  The default 3 resources are:

  * ``soul://current``        — L0 identity records (Hindsight)
  * ``wings://list``          — current L2 wings (MemoryPalace)
  * ``rooms://list``          — current L3 rooms (MemoryPalace)

Each resource is a small handler that returns a dict; the server
serialises it to JSON in the MCP ``contents`` envelope.
"""

from __future__ import annotations

from typing import Any, Dict

from .server import MCPResource


def _soul_current() -> Dict[str, Any]:
    from services.agent_service.hindsight import get_hindsight

    hs = get_hindsight()
    items = hs.list_identity(limit=50)
    return {
        "identity": [it.to_dict() for it in items],
        "count": len(items),
    }


def _wings_list() -> Dict[str, Any]:
    from services.agent_service.memory_palace import get_memory_palace

    palace = get_memory_palace()
    wings = palace.list_wings(limit=200)
    return {
        "wings": [w.to_dict() for w in wings],
        "count": len(wings),
    }


def _rooms_list() -> Dict[str, Any]:
    from services.agent_service.memory_palace import get_memory_palace

    palace = get_memory_palace()
    rooms = palace.list_rooms(limit=200)
    return {
        "rooms": [r.to_dict() for r in rooms],
        "count": len(rooms),
    }


def build_default_resources() -> list:
    return [
        MCPResource(
            uri="soul://current",
            name="Current SOUL / Identity",
            description="The agent's L0 identity records (verbatim, from Hindsight).",
            mime_type="application/json",
            handler=_soul_current,
        ),
        MCPResource(
            uri="wings://list",
            name="MemoryPalace Wings",
            description="All L2 wings currently registered in the MemoryPalace.",
            mime_type="application/json",
            handler=_wings_list,
        ),
        MCPResource(
            uri="rooms://list",
            name="MemoryPalace Rooms",
            description="All L3 rooms currently registered in the MemoryPalace.",
            mime_type="application/json",
            handler=_rooms_list,
        ),
    ]


__all__ = ["build_default_resources"]
