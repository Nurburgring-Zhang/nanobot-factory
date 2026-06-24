"""P4-3-W2: MCP prompts — reusable prompt templates.

Prompts are how MCP clients *render* a templated message to send back
to the LLM.  The default 2 prompts are:

  * ``summarize_room``        — compress a MemoryPalace room into a story
  * ``generate_storyboard``    — turn a wing of rooms into a storyboard

Each prompt is a small handler that returns the standard MCP
``messages`` envelope::

    {"messages": [{"role": "user", "content": {"type": "text", "text": "..."}}]}
"""

from __future__ import annotations

from typing import Any, Dict

from .server import MCPPrompt


def _summarize_room(args: Dict[str, Any]) -> Dict[str, Any]:
    from services.agent_service.memory_palace import get_memory_palace

    palace = get_memory_palace()
    room_id = args.get("room_id")
    if not isinstance(room_id, str) or not room_id:
        raise ValueError("room_id is required")
    room = palace.get_room(room_id)
    if room is None:
        raise KeyError(f"room_not_found: {room_id}")
    drawers = palace.list_drawers(room_id=room_id, limit=200)
    body = (
        f"Compress the following MemoryPalace room into a 3-5 sentence "
        f"essential story. Preserve names, decisions, and constraints.\n\n"
        f"Room: {room.title}\n"
        f"Summary: {room.summary}\n\n"
        f"Drawers ({len(drawers)}):\n"
    )
    for d in drawers:
        body += f"- {d.title} ({d.content_type}): {d.content[:200]}\n"
    return {
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": body},
            }
        ]
    }


def _generate_storyboard(args: Dict[str, Any]) -> Dict[str, Any]:
    from services.agent_service.memory_palace import get_memory_palace

    palace = get_memory_palace()
    wing_id = args.get("wing_id")
    if not isinstance(wing_id, str) or not wing_id:
        raise ValueError("wing_id is required")
    wing = palace.get_wing(wing_id)
    if wing is None:
        raise KeyError(f"wing_not_found: {wing_id}")
    rooms = palace.list_rooms(wing_id=wing_id, limit=200)
    body = (
        f"Generate a storyboard for the following MemoryPalace wing.\n\n"
        f"Wing: {wing.name}\n"
        f"Description: {wing.description}\n\n"
        f"Rooms ({len(rooms)}):\n"
    )
    for r in rooms:
        body += f"- [{r.status}] {r.title}: {r.summary}\n"
    return {
        "messages": [
            {
                "role": "user",
                "content": {"type": "text", "text": body},
            }
        ]
    }


def build_default_prompts() -> list:
    return [
        MCPPrompt(
            name="summarize_room",
            description="Compress a single MemoryPalace room (and its drawers) into a 3-5 sentence essential story.",
            arguments=[
                {"name": "room_id", "description": "MemoryPalace room id (L3)", "required": True},
            ],
            handler=_summarize_room,
        ),
        MCPPrompt(
            name="generate_storyboard",
            description="Generate a storyboard outline from a wing of rooms (L2 → L3).",
            arguments=[
                {"name": "wing_id", "description": "MemoryPalace wing id (L2)", "required": True},
            ],
            handler=_generate_storyboard,
        ),
    ]


__all__ = ["build_default_prompts"]
