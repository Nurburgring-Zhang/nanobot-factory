"""P4-3-W1 + P6-Fix-B-3: Tool registry package.

Re-exports :class:`ToolRegistry`, :class:`Tool`, the :func:`tool`
decorator, the singleton helper, and the HMAC-signed
:class:`ToolAuditChain` bridge introduced in P6-Fix-B-3.
"""
from __future__ import annotations

from .audit import (
    ToolAuditChain,
    ToolAuditRecord,
    get_tool_audit_chain,
    reset_tool_audit_for_test,
)
from .registry import (
    AuditEntry,
    Tool,
    ToolRegistry,
    get_tool_registry,
    reset_tool_registry_for_test,
    tool,
)

__all__ = [
    # registry primitives
    "Tool",
    "ToolRegistry",
    "AuditEntry",
    "tool",
    "get_tool_registry",
    "reset_tool_registry_for_test",
    # P6-Fix-B-3: HMAC-signed tool audit bridge
    "ToolAuditChain",
    "ToolAuditRecord",
    "get_tool_audit_chain",
    "reset_tool_audit_for_test",
]
