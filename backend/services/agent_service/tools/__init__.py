"""P4-3-W1: Tool registry package.

Re-exports :class:`ToolRegistry`, :class:`Tool`, the :func:`tool`
decorator, and the singleton helper.  The actual implementation lives
in :mod:`registry`.
"""
from __future__ import annotations

from .registry import (
    AuditEntry,
    Tool,
    ToolRegistry,
    get_tool_registry,
    reset_tool_registry_for_test,
    tool,
)

__all__ = [
    "Tool",
    "ToolRegistry",
    "AuditEntry",
    "tool",
    "get_tool_registry",
    "reset_tool_registry_for_test",
]
