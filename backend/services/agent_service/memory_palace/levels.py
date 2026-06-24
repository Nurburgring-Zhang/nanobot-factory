"""P4-3-W2: MemoryPalace level definitions + record types.

The 6 levels, in order from outermost (most stable) to innermost (most
volatile):

  L0 Identity        — identity layer, derived from SOUL.md.  Immutable for
                       a single session.  Stored in legacy agent_memory.
  L1 Essential Story — project-level core info; can be compressed by LLM.
                       Stored in legacy agent_memory.
  L2 Wing            — theme / topic trigger (e.g. "prompt engineering").
                       Persisted in ``memory_wings``.
  L3 Room            — concrete event / project / task.  Persisted in
                       ``memory_rooms`` (parent: wing_id).
  L4 Drawer          — document / resource / artefact inside a room.
                       Persisted in ``memory_drawers`` (parent: room_id).
  L5 Tunnel          — cross-wing bridge.  Persisted in ``memory_tunnels``
                       (parent_a_id, parent_b_id).
  +  memory_items    — free-form verbatim items (L0/L1/L3 entries).  Lives
                       in ``memory_items`` (parent: room_id OR wing_id).

The 5 persistent tables map as:

  L2  ── memory_wings
  L3  ── memory_rooms
  L4  ── memory_drawers
  L5  ── memory_tunnels
  free ─ memory_items

L0 and L1 piggy-back on the existing agent_memory table (P3-3-W1) so that
SOUL.md-derived identity is queryable through the legacy /api/v1/agent_memory
endpoint as well.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MemoryLevel(str, Enum):
    """The 6 hierarchical levels of MemoryPalace.

    The string values are stable wire/DB identifiers (do NOT rename without
    a migration).
    """

    L0_IDENTITY = "L0_identity"
    L1_ESSENTIAL_STORY = "L1_essential_story"
    L2_WING = "L2_wing"
    L3_ROOM = "L3_room"
    L4_DRAWER = "L4_drawer"
    L5_TUNNEL = "L5_tunnel"


#: Ordered list — used by introspection / OpenAPI documentation.
LEVELS: List[MemoryLevel] = [
    MemoryLevel.L0_IDENTITY,
    MemoryLevel.L1_ESSENTIAL_STORY,
    MemoryLevel.L2_WING,
    MemoryLevel.L3_ROOM,
    MemoryLevel.L4_DRAWER,
    MemoryLevel.L5_TUNNEL,
]


# ── Record dataclasses (immutable view) ──────────────────────────────────────
@dataclass
class WingRecord:
    """L2 Wing — a theme / topic trigger."""

    wing_id: str
    name: str
    description: str = ""
    trigger_keywords: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return f"wing-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class RoomRecord:
    """L3 Room — a concrete event / project / task inside a wing."""

    room_id: str
    wing_id: str
    title: str
    summary: str = ""
    status: str = "active"          # active / closed / archived
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return f"room-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DrawerRecord:
    """L4 Drawer — a document / resource / artefact inside a room."""

    drawer_id: str
    room_id: str
    title: str
    content: str = ""
    content_type: str = "text"      # text / file / url / code / image_ref
    uri: str = ""                   # optional pointer to actual file/url
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return f"drawer-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TunnelRecord:
    """L5 Tunnel — a cross-wing bridge connecting two wings/rooms."""

    tunnel_id: str
    from_id: str            # wing_id or room_id
    from_kind: str          # "wing" or "room"
    to_id: str
    to_kind: str
    relation: str = "related"   # related / causes / blocks / mirrors
    note: str = ""
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return f"tun-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ItemRecord:
    """Free-form verbatim item — supports L0/L1/L3 levels.

    Used to keep *raw* text snippets (e.g. a verbatim user instruction) in
    the palace without forcing them into the structured wing/room schema.
    """

    item_id: str
    level: str              # one of L0_identity / L1_essential_story / L3_room
    parent_id: str          # room_id / wing_id / "global" for L0
    content: str            # verbatim text
    role: str = "user"      # user / system / agent
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new_id() -> str:
        return f"item-{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


__all__ = [
    "MemoryLevel",
    "LEVELS",
    "WingRecord",
    "RoomRecord",
    "DrawerRecord",
    "TunnelRecord",
    "ItemRecord",
]
