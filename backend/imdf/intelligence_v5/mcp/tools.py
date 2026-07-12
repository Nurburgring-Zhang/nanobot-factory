"""智影 V5 — MCP 工具注册表"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .server import MCPTool

logger = logging.getLogger(__name__)


class ParameterType(str, Enum):
    """参数类型"""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParameter:
    """工具参数"""

    name: str
    param_type: ParameterType = ParameterType.STRING
    description: str = ""
    required: bool = False
    default: Any = None
    enum: Optional[List[Any]] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None


@dataclass
class ToolResult:
    """工具执行结果"""

    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class MCPToolRegistry:
    """工具注册中心 — 简化 wrapper"""

    def __init__(self):
        self.tools: Dict[str, MCPTool] = {}

    def register(self, tool: MCPTool):
        self.tools[tool.name] = tool

    def get(self, name: str) -> Optional[MCPTool]:
        return self.tools.get(name)

    def list(self) -> List[MCPTool]:
        return list(self.tools.values())

    def search(self, keyword: str) -> List[MCPTool]:
        keyword_lower = keyword.lower()
        return [
            t for t in self.tools.values()
            if keyword_lower in t.name.lower() or keyword_lower in t.description.lower()
        ]


tool_registry = MCPToolRegistry()
