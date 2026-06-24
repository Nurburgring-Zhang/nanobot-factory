"""P4-8-W1: Skills MCP bridge.

Exposes the 10 built-in skills + the SkillOrchestrator as MCP tools so
the agent_service's MCP server can route ``tools/call`` requests into
them.  Same shape as ``services.agent_service.mcp.tools`` — a list of
``MCPTool`` definitions with handler callables.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .context import SkillContext
from .orchestrator import SkillOrchestrator
from .registry import SKILL_REGISTRY

logger = logging.getLogger(__name__)


@dataclass
class SkillMCPTool:
    """MCP tool descriptor bound to a Skill name."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    skill_name: Optional[str] = None
    handler: Optional[Callable[..., Awaitable[Any]]] = None


def _make_handler(skill_name: str) -> Callable[..., Awaitable[Dict[str, Any]]]:
    async def _h(args: Dict[str, Any]) -> Dict[str, Any]:
        if not SKILL_REGISTRY.has(skill_name):
            return {"success": False, "error": f"skill not found: {skill_name}"}
        ctx = SkillContext.create(
            user_id=str(args.pop("user_id", "mcp")),
            project_id=str(args.pop("project_id", "default")),
            inputs=args,
        )
        orch = SkillOrchestrator()
        result = await orch.run_skill(skill_name, ctx, inputs=args)
        return result.to_dict()
    return _h


def discover_skill_tools() -> List[SkillMCPTool]:
    """Return one MCP tool descriptor per registered skill."""
    out: List[SkillMCPTool] = []
    for info in SKILL_REGISTRY.list():
        name = str(info["name"])
        out.append(SkillMCPTool(
            name=f"skill_{name}",
            description=f"Run skill: {info.get('description', name)}",
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "project_id": {"type": "string"},
                    **dict(info.get("input_schema") or {}),
                },
                "additionalProperties": True,
            },
            skill_name=name,
            handler=_make_handler(name),
        ))
    return out


def list_skill_tool_names() -> List[str]:
    return [t.name for t in discover_skill_tools()]


async def invoke_skill_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Look up a skill by ``skill_<name>`` and invoke it."""
    if not name.startswith("skill_"):
        return {"success": False, "error": f"not a skill tool: {name}"}
    skill_name = name[len("skill_"):]
    return await _make_handler(skill_name)(args)


__all__ = [
    "SkillMCPTool",
    "discover_skill_tools",
    "list_skill_tool_names",
    "invoke_skill_tool",
]