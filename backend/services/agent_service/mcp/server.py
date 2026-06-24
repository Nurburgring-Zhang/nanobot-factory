"""P4-3-W2: MCP server — JSON-RPC dispatcher with stdio + SSE transports.

The server keeps an in-memory registry of tools / resources / prompts.
External MCP clients call one of the 5 supported methods:

  * ``initialize``              — handshake; returns server info
  * ``tools/list``              — list available tools
  * ``tools/call``              — invoke a tool (name + args)
  * ``resources/list``          — list available resources
  * ``resources/read``          — read a resource by URI
  * ``prompts/list``            — list available prompts
  * ``prompts/get``             — render a prompt by name

The HTTP transport (``/mcp`` on port 8008) accepts a POST with a
JSON-RPC payload and returns a JSON-RPC response; for streaming
subscribes, a separate ``GET /mcp/sse`` endpoint emits SSE events.

The stdio transport is exposed via :meth:`serve_stdio` which is a
synchronous line loop — useful for spawning the server as a
subprocess and connecting it to Claude Code / Cursor.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Wire models ──────────────────────────────────────────────────────────────
@dataclass
class MCPTool:
    """A tool exposed by the MCP server."""

    name: str
    description: str
    schema: Dict[str, Any]   # JSON Schema for the arguments object
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.schema,
        }


@dataclass
class MCPResource:
    """A resource exposed by the MCP server."""

    uri: str                 # e.g. "soul://current"
    name: str
    description: str
    mime_type: str = "text/plain"
    handler: Optional[Callable[[], Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass
class MCPPrompt:
    """A prompt template exposed by the MCP server."""

    name: str
    description: str
    arguments: List[Dict[str, Any]] = field(default_factory=list)
    handler: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
        }


# ── Server ──────────────────────────────────────────────────────────────────
class MCPServer:
    """The MCP server.  Stateless beyond the in-memory registries."""

    SERVER_NAME = "nanobot-factory-mcp"
    SERVER_VERSION = "0.1.0"
    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self) -> None:
        self._tools: Dict[str, MCPTool] = {}
        self._resources: Dict[str, MCPResource] = {}
        self._prompts: Dict[str, MCPPrompt] = {}
        self._initialised = False
        self._started_at: float = time.time()
        self._request_count: int = 0
        self._error_count: int = 0

    # ── Registry helpers ────────────────────────────────────────────────────
    def register_tool(self, tool: MCPTool) -> None:
        self._tools[tool.name] = tool

    def register_resource(self, resource: MCPResource) -> None:
        self._resources[resource.uri] = resource

    def register_prompt(self, prompt: MCPPrompt) -> None:
        self._prompts[prompt.name] = prompt

    def list_tools(self) -> List[MCPTool]:
        return list(self._tools.values())

    def list_resources(self) -> List[MCPResource]:
        return list(self._resources.values())

    def list_prompts(self) -> List[MCPPrompt]:
        return list(self._prompts.values())

    def tool_count(self) -> int:
        return len(self._tools)

    def resource_count(self) -> int:
        return len(self._resources)

    def prompt_count(self) -> int:
        return len(self._prompts)

    # ── JSON-RPC dispatch ───────────────────────────────────────────────────
    def handle(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Synchronous JSON-RPC dispatcher.

        Returns a JSON-RPC response dict.  Always echoes the request id
        (or ``None`` for invalid envelopes).  ``parse_error`` /
        ``method_not_found`` are returned as proper error objects.
        """
        self._request_count += 1
        rid = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        if not isinstance(method, str):
            self._error_count += 1
            return self._error(rid, -32600, "invalid_request: missing method")

        try:
            if method == "initialize":
                self._initialised = True
                result = self._handle_initialize(params)
            elif method == "tools/list":
                result = self._handle_tools_list()
            elif method == "tools/call":
                result = self._handle_tools_call(params)
            elif method == "resources/list":
                result = self._handle_resources_list()
            elif method == "resources/read":
                result = self._handle_resources_read(params)
            elif method == "prompts/list":
                result = self._handle_prompts_list()
            elif method == "prompts/get":
                result = self._handle_prompts_get(params)
            else:
                self._error_count += 1
                return self._error(rid, -32601, f"method_not_found: {method}")
            return {"jsonrpc": "2.0", "id": rid, "result": result}
        except Exception as exc:  # noqa: BLE001
            self._error_count += 1
            logger.exception("MCP handler %s failed", method)
            return self._error(rid, -32603, f"internal_error: {exc}")

    @staticmethod
    def _error(rid: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": code, "message": message},
        }

    # ── Method handlers ────────────────────────────────────────────────────
    def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "protocolVersion": self.PROTOCOL_VERSION,
            "serverInfo": {"name": self.SERVER_NAME, "version": self.SERVER_VERSION},
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
            },
        }

    def _handle_tools_list(self) -> Dict[str, Any]:
        return {"tools": [t.to_dict() for t in self._tools.values()]}

    def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str):
            raise ValueError("params.name must be a string")
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"tool_not_found: {name}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ValueError("params.arguments must be an object")
        result = tool.handler(arguments)
        if not isinstance(result, dict):
            result = {"result": result}
        return {"content": [{"type": "json", "data": result}], "isError": False}

    def _handle_resources_list(self) -> Dict[str, Any]:
        return {"resources": [r.to_dict() for r in self._resources.values()]}

    def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        uri = params.get("uri")
        if not isinstance(uri, str):
            raise ValueError("params.uri must be a string")
        resource = self._resources.get(uri)
        if resource is None:
            raise KeyError(f"resource_not_found: {uri}")
        if resource.handler is None:
            return {"contents": [{"uri": uri, "mimeType": resource.mime_type, "text": ""}]}
        body = resource.handler() or {}
        text = json.dumps(body, ensure_ascii=False, indent=2) if not isinstance(body, str) else body
        return {"contents": [{"uri": uri, "mimeType": resource.mime_type, "text": text}]}

    def _handle_prompts_list(self) -> Dict[str, Any]:
        return {"prompts": [p.to_dict() for p in self._prompts.values()]}

    def _handle_prompts_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str):
            raise ValueError("params.name must be a string")
        prompt = self._prompts.get(name)
        if prompt is None:
            raise KeyError(f"prompt_not_found: {name}")
        arguments = params.get("arguments") or {}
        if prompt.handler is None:
            return {
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": f"[prompt: {name}]"},
                    }
                ]
            }
        body = prompt.handler(arguments) or {}
        return body

    # ── Status ──────────────────────────────────────────────────────────────
    def status(self) -> Dict[str, Any]:
        return {
            "server": self.SERVER_NAME,
            "version": self.SERVER_VERSION,
            "protocol": self.PROTOCOL_VERSION,
            "uptime_seconds": time.time() - self._started_at,
            "initialised": self._initialised,
            "tools": self.tool_count(),
            "resources": self.resource_count(),
            "prompts": self.prompt_count(),
            "requests_served": self._request_count,
            "errors": self._error_count,
        }

    # ── stdio transport ────────────────────────────────────────────────────
    def serve_stdio(self, stdin=None, stdout=None) -> None:  # pragma: no cover — I/O loop
        """Line-delimited JSON-RPC over stdin/stdout.  Used when the
        server is spawned as a subprocess for Claude Code / Cursor.
        """
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError as exc:
                err = self._error(None, -32700, f"parse_error: {exc}")
                stdout.write(json.dumps(err, ensure_ascii=False) + "\n")
                stdout.flush()
                continue
            resp = self.handle(req)
            stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            stdout.flush()


# ── Module-level singleton ──────────────────────────────────────────────────
_server: Optional[MCPServer] = None


def get_mcp_server() -> MCPServer:
    global _server
    if _server is None:
        # Lazy import to avoid a circular import at module load time.
        from .prompts import build_default_prompts
        from .resources import build_default_resources
        from .tools import build_default_tools

        _server = MCPServer()
        for tool in build_default_tools():
            _server.register_tool(tool)
        for resource in build_default_resources():
            _server.register_resource(resource)
        for prompt in build_default_prompts():
            _server.register_prompt(prompt)
    return _server


def reset_mcp_server_for_test() -> MCPServer:
    """Build a fresh server (for tests that need a clean registry)."""
    global _server
    from .prompts import build_default_prompts
    from .resources import build_default_resources
    from .tools import build_default_tools

    _server = MCPServer()
    for tool in build_default_tools():
        _server.register_tool(tool)
    for resource in build_default_resources():
        _server.register_resource(resource)
    for prompt in build_default_prompts():
        _server.register_prompt(prompt)
    return _server


__all__ = [
    "MCPServer",
    "MCPTool",
    "MCPResource",
    "MCPPrompt",
    "get_mcp_server",
    "reset_mcp_server_for_test",
]
