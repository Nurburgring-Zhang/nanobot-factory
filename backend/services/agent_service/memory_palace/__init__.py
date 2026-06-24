"""P4-3-W2: MemoryPalace — 6-layer hierarchical memory.

Inspired by the MemPalace project (56.2k stars) which organises an agent's
long-term memory as a literal *palace* with six nested levels.  This module
implements the same model for the nanobot-factory agent_service so that we
get the same recall-quality + organisation benefits without inventing a new
vocabulary.

The 6 layers, from outermost (most stable) to innermost (most volatile):

  L0 Identity        — derived from SOUL.md, **immutable** for a session
  L1 Essential Story — project-level core info, compressible
  L2 Wing            — theme trigger (e.g. "prompt engineering")
  L3 Room            — concrete event / project / task
  L4 Drawer          — document / resource / artefact inside a room
  L5 Tunnel          — cross-wing bridge ("this prompt-engineering wing
                       connects to the data-cleaning wing via this idea")

Each layer is a thin wrapper around a SQLite table.  The five persistent
tables are:

  * memory_wings
  * memory_rooms
  * memory_drawers
  * memory_tunnels
  * memory_items

Identity and Essential Story are stored in the existing ``agent_memory``
table (scope = ``identity:`` and ``story:``) so they survive schema bumps
and remain queryable through the legacy ``/api/v1/agent_memory`` endpoint.

Public surface (this package only — see ``routes.py`` for the HTTP layer):

  * :class:`MemoryLevel`      — enum of the 6 levels
  * :class:`MemoryPalace`     — main facade, lazy singleton
  * :func:`get_memory_palace` — module-level singleton accessor
"""

from __future__ import annotations

from .levels import (
    LEVELS,
    MemoryLevel,
    RoomRecord,
    WingRecord,
    DrawerRecord,
    TunnelRecord,
    ItemRecord,
)
from .manager import MemoryPalace, get_memory_palace, reset_memory_palace_for_test

__all__ = [
    "LEVELS",
    "MemoryLevel",
    "WingRecord",
    "RoomRecord",
    "DrawerRecord",
    "TunnelRecord",
    "ItemRecord",
    "MemoryPalace",
    "get_memory_palace",
    "reset_memory_palace_for_test",
]
