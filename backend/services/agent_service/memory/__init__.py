"""P4-3-W1: Multi-turn session memory package.

This package owns the ``services.agent_service.memory`` namespace
(formerly a single ``memory.py`` file in P3-3-W1).  It contains:

* :mod:`legacy`      — short-term + long-term memory (P3-3-W1)
* :mod:`multi_turn`  — multi-turn session context (P4-3-W1)

External callers should keep using::

    from services.agent_service.memory import (
        get_long_term, get_short_term, remember, recall,
        get_session_manager, MultiTurnSessionManager, ...
    )
"""
from __future__ import annotations

# Re-export legacy P3-3-W1 memory surface (kept here so existing
# ``from services.agent_service.memory import get_long_term`` calls
# keep working after the directory conversion).
from .legacy import (  # noqa: F401  (re-export)
    LongTermMemory,
    ShortTermEntry,
    ShortTermMemory,
    get_long_term,
    get_short_term,
    recall,
    remember,
    reset_memory_for_test,
)

from .multi_turn import (  # noqa: F401  (re-export)
    Message,
    MultiTurnSessionManager,
    ROLE_ASSISTANT,
    ROLE_SYSTEM,
    ROLE_TOOL,
    ROLE_USER,
    SessionContext,
    TokenUsage,
    TokenUsageTracker,
    VALID_ROLES,
    get_session_manager,
    reset_session_manager_for_test,
)

__all__ = [
    # legacy (P3-3-W1)
    "LongTermMemory",
    "ShortTermEntry",
    "ShortTermMemory",
    "get_long_term",
    "get_short_term",
    "recall",
    "remember",
    "reset_memory_for_test",
    # new (P4-3-W1)
    "Message",
    "SessionContext",
    "MultiTurnSessionManager",
    "TokenUsage",
    "TokenUsageTracker",
    "ROLE_USER",
    "ROLE_ASSISTANT",
    "ROLE_SYSTEM",
    "ROLE_TOOL",
    "VALID_ROLES",
    "get_session_manager",
    "reset_session_manager_for_test",
]
