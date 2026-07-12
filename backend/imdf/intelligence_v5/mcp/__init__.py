"""智影 V5 — MCP (Model Context Protocol) 子包

迁移自 Comfy MCP + Anthropic MCP:
- 标准化工具暴露给 LLM
- JSON-RPC 2.0 over stdio / HTTP / WebSocket
- 创意工作流 (Comfy) / 数据访问 / 命令执行
"""
from .server import (
    MCPServer,
    MCPTool,
    MCPResource,
    MCPPrompt,
    MCPMessage,
    JSONRPCRequest,
    JSONRPCResponse,
    mcp_server,
)
from .tools import (
    MCPToolRegistry,
    ToolParameter,
    ToolResult,
    tool_registry,
)

__all__ = [
    "MCPServer",
    "MCPTool",
    "MCPResource",
    "MCPPrompt",
    "MCPMessage",
    "JSONRPCRequest",
    "JSONRPCResponse",
    "mcp_server",
    "MCPToolRegistry",
    "ToolParameter",
    "ToolResult",
    "tool_registry",
]
