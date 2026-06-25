"""P6-Fix-P0-5: imdf.agents public API.

This package is the canonical home for the agent-plugin contract:

  * :class:`~imdf.agents.base.BaseAgent`     — abstract base
  * :class:`~imdf.agents.base.AgentContext`  — input value object
  * :class:`~imdf.agents.base.AgentResult`   — output value object
  * :class:`~imdf.agents.registry.PluginRegistry`
                                             — process-wide plugin store
  * :func:`~imdf.agents.loader.load_plugin`  — dynamic file loader
  * :mod:`imdf.agents.builtin`               — 23 built-in agents

Importing this package does NOT touch the registry — call
:func:`PluginRegistry.get_registry` explicitly so the import cost
stays predictable.  Use :func:`register_builtin_agents` to install
the 23 built-in classes in one call.
"""
from __future__ import annotations

from typing import List, Type

from .base import AgentContext, AgentResult, BaseAgent
from .loader import load_plugin, load_plugins
from .registry import PluginRegistry

__all__ = [
    "AgentContext",
    "AgentResult",
    "BaseAgent",
    "PluginRegistry",
    "load_plugin",
    "load_plugins",
    "register_builtin_agents",
]


def register_builtin_agents(
    registry: PluginRegistry | None = None,
) -> List[str]:
    """Register every concrete class in :mod:`imdf.agents.builtin`
    into ``registry`` (or the process-wide singleton).

    Returns the list of slugs registered.
    """
    # Local import: avoid loading the builtin bundle until the caller
    # actually asks for it.  The bundle in turn transitively imports
    # ``services.agent_service.agents`` (lazily) on its first
    # ``execute`` call, so this is safe to call early at boot time.
    from . import builtin

    reg = registry if registry is not None else PluginRegistry.get_registry()
    mapping = {
        cls().get_agent_type_slug(): cls
        for cls in builtin.get_builtin_classes()
    }
    # Drop empty slugs (defensive — should not happen).
    mapping = {k: v for k, v in mapping.items() if k}
    reg.bulk_register(mapping, overwrite=True)
    return sorted(mapping.keys())
