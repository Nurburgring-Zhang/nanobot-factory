"""P4-7-W2: MultimodalAgent entry-point inside ``backend.services.agent_service``.

This thin wrapper imports the canonical ``MultimodalAgent`` from
``imdf.multimodal`` and exposes a module-level singleton + convenience
imports that the agent-service ``routes.py`` (P3-3-W1 + P4-3-W1) can call
without taking a hard dependency on the imdf package import path.

Why this lives here
-------------------
The task spec calls out ``backend/services/agent_service/multimodal_agent.py``
explicitly.  The agent service runs on port 8008 and already mounts the
13-tool registry (P4-3-W1).  We re-use the same MemoryPalace + MCP plumbing.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .memory_palace import get_memory_palace as get_palace
from .mcp import get_mcp_server

logger = logging.getLogger(__name__)


_agent_singleton = None


def get_multimodal_agent():
    """Lazy singleton wrapping ``imdf.multimodal.MultimodalAgent``."""
    global _agent_singleton
    if _agent_singleton is not None:
        return _agent_singleton
    try:
        from ...imdf.multimodal.multimodal_agent import MultimodalAgent
    except Exception as exc:
        logger.warning("imdf.multimodal unavailable, falling back to stub: %s", exc)
        from . import _stub_multimodal_agent as _stub  # type: ignore
        MultimodalAgent = _stub.StubMultimodalAgent  # type: ignore[assignment]
    _agent_singleton = MultimodalAgent()
    return _agent_singleton


def invoke(prompt: str, media: Optional[List[Dict[str, Any]]] = None, session_id: Optional[str] = None) -> Dict[str, Any]:
    """One-call helper used by the agent-service ``/api/v1/agent/multimodal`` route."""
    from ...imdf.multimodal.types import AgentRequest, MediaRef, parse_media_item
    refs: List[MediaRef] = []
    for m in (media or []):
        try:
            refs.append(parse_media_item(m))
        except Exception:
            continue
    req = AgentRequest(prompt=prompt, media=refs, session_id=session_id, save_to_memory=True)
    return get_multimodal_agent().invoke(req).to_dict()


def list_tools() -> List[Dict[str, Any]]:
    return get_multimodal_agent().tools


def register_with_mcp() -> Dict[str, Any]:
    """Bridge tools into the agent-service MCP server (P4-3-W1 surface)."""
    server = get_mcp_server()
    out = {"registered": 0, "names": []}
    for spec in get_multimodal_agent().tools:
        try:
            if hasattr(server, "register_tool"):
                server.register_tool(name=spec["name"], handler=None)
                out["registered"] += 1
                out["names"].append(spec["name"])
        except Exception as exc:
            logger.debug("mcp register_tool(%s) failed: %s", spec["name"], exc)
    return out


def save_to_memory(session_id: str, request_id: str, payload: Dict[str, Any]) -> List[str]:
    """Persist a multimodal agent invocation into MemoryPalace as an Item."""
    palace = get_palace()
    saved: List[str] = []
    try:
        if hasattr(palace, "create_item"):
            item = palace.create_item(
                drawer_id=session_id or "multimodal",
                title=request_id,
                content=payload,
            )
            saved.append(str(getattr(item, "item_id", request_id)))
        elif hasattr(palace, "save"):
            saved.append(str(palace.save(scope=session_id or "multimodal", key=request_id, value=payload)))
        elif hasattr(palace, "add"):
            saved.append(str(palace.add(scope=session_id or "multimodal", content=payload)))
    except Exception as exc:
        logger.debug("MemoryPalace save failed: %s", exc)
    return saved