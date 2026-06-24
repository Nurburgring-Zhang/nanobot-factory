"""P4-3-W2: MCP (Model Context Protocol) server for the agent service.

The MCP server exposes the agent's memory surface (MemoryPalace +
Hindsight) to external MCP-compatible clients — Claude Code, Cursor,
ChatGPT, etc.  The wire protocol follows the standard MCP JSON-RPC
shape::

    request  = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    response = {"jsonrpc": "2.0", "id": 1, "result": {"tools": [...]}}

We support two transports:

  * **stdio** — line-delimited JSON-RPC over stdin/stdout.  Used by
    Claude Code / Cursor when the user adds the server to their MCP
    config.  This is the *primary* transport.
  * **SSE**   — server-sent events over HTTP, mounted at ``/mcp`` on
    the agent_service port (8008).  Used by browser-based clients and
    by ChatGPT.

The HTTP transport is mounted as an ASGI sub-app on the existing
agent_service FastAPI instance (see ``routes.py``), so the same
``8008`` port serves both the REST API and the MCP/SSE endpoint.
"""

from __future__ import annotations

from .server import MCPServer, MCPTool, MCPResource, MCPPrompt, get_mcp_server, reset_mcp_server_for_test
from .tools import build_default_tools
from .resources import build_default_resources
from .prompts import build_default_prompts

__all__ = [
    "MCPServer",
    "MCPTool",
    "MCPResource",
    "MCPPrompt",
    "get_mcp_server",
    "reset_mcp_server_for_test",
    "build_default_tools",
    "build_default_resources",
    "build_default_prompts",
]
