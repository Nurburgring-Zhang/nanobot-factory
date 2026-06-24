"""P4-8-W1: Memory palace hooks — auto-retain skill execution results.

When a Skill finishes, the SkillContext can be fed to a MemoryPalace
handle so the result is automatically stored as an L3 (Room) entry.  This
module is the glue; the actual MemoryPalace import is deferred so the
skills package works without it.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from .context import SkillContext
from .result import SkillResult

logger = logging.getLogger(__name__)


def retain_to_memory(
    palace: Any,
    *,
    skill_name: str,
    result: SkillResult,
    context: SkillContext,
    room_label: Optional[str] = None,
) -> Optional[Any]:
    """Best-effort retention of a SkillResult into MemoryPalace.

    Returns the created Room record (or None on failure).  Gracefully
    no-ops when ``palace`` is None.
    """
    if palace is None:
        return None
    if not result.success:
        logger.debug("retain_to_memory: skipping failed result for %s", skill_name)
        return None
    label = room_label or f"skill:{skill_name}"
    payload = {
        "skill": skill_name,
        "user_id": context.user_id,
        "project_id": context.project_id,
        "data": result.data,
        "logs": list(result.logs),
        "metadata": dict(result.metadata),
        "trace": context.trace_snapshot(),
        "ts": time.time(),
    }
    try:
        room = palace.add_room(label=label, payload=payload, level="L3")
        logger.info("retain_to_memory: stored skill result '%s' as room %s",
                    skill_name, getattr(room, "room_id", "?"))
        return room
    except Exception as exc:  # noqa: BLE001
        logger.warning("retain_to_memory failed for %s: %s", skill_name, exc)
        return None


__all__ = ["retain_to_memory"]