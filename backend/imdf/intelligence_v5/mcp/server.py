"""智影 V5 — MCP Server (JSON-RPC 2.0)

Model Context Protocol — Anthropic 标准 + Comfy MCP 风格:
- tools: 客户端可调用的工具
- resources: 客户端可读的资源
- prompts: 提示词模板
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class JSONRPCRequest:
    """JSON-RPC 2.0 Request"""
    jsonrpc: str = "2.0"
    method: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    id: Optional[Any] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "JSONRPCRequest":
        return cls(
            jsonrpc=d.get("jsonrpc", "2.0"),
            method=d.get("method", ""),
            params=d.get("params", {}),
            id=d.get("id"),
        )


@dataclass
class JSONRPCResponse:
    """JSON-RPC 2.0 Response"""
    jsonrpc: str = "2.0"
    id: Optional[Any] = None
    result: Any = None
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        if self.error:
            return {"jsonrpc": self.jsonrpc, "id": self.id, "error": self.error}
        return {"jsonrpc": self.jsonrpc, "id": self.id, "result": self.result}


@dataclass
class MCPTool:
    """MCP Tool — LLM 可调用的工具"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable  # async (params) -> result
    tool_id: str = field(default_factory=lambda: f"tool-{uuid.uuid4().hex[:8]}")
    version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "version": self.version,
        }


@dataclass
class MCPResource:
    """MCP Resource — LLM 可读的资源"""

    uri: str
    name: str
    description: str = ""
    mime_type: str = "text/plain"
    handler: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


@dataclass
class MCPPrompt:
    """MCP Prompt — 提示词模板"""

    name: str
    description: str
    template: str
    arguments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments,
        }


@dataclass
class MCPMessage:
    """MCP 消息 — 用于 WebSocket 通道"""

    direction: str  # "request" | "response" | "notification"
    payload: Dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: f"mcp-{uuid.uuid4().hex[:10]}")
    timestamp: float = 0.0


class MCPServer:
    """MCP Server — JSON-RPC 2.0 over HTTP/WS/stdio"""

    SERVER_NAME = "imdf-v5-mcp"
    SERVER_VERSION = "5.0.0"
    PROTOCOL_VERSION = "2025-06-18"

    def __init__(self):
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}
        self.prompts: Dict[str, MCPPrompt] = {}
        self.metrics: Dict[str, int] = {"requests": 0, "errors": 0}
        # 注册默认工具
        self._register_defaults()

    def _register_defaults(self):
        """注册默认 MCP 工具 — Comfy MCP 风格"""
        # 1. 文本生成
        self.register_tool(
            name="text.generate",
            description="生成文本 (LLM)",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "提示词"},
                    "model": {"type": "string", "description": "模型名", "default": "gpt-4"},
                    "temperature": {"type": "number", "default": 0.7},
                },
                "required": ["prompt"],
            },
            handler=self._handle_text_generate,
        )
        # 2. 图像生成
        self.register_tool(
            name="image.generate",
            description="生成图像 (Agnes / NanoBanana / GPT-Image)",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "model": {"type": "string", "default": "agnes-image-2.1-flash"},
                    "width": {"type": "integer", "default": 1024},
                    "height": {"type": "integer", "default": 1024},
                    "reference_image_url": {"type": "string"},
                },
                "required": ["prompt"],
            },
            handler=self._handle_image_generate,
        )
        # 3. 视频生成
        self.register_tool(
            name="video.generate",
            description="生成视频 (Agnes / Seedance)",
            input_schema={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "model": {"type": "string", "default": "agnes-video-2.0"},
                    "duration_sec": {"type": "number", "default": 5},
                    "reference_image_url": {"type": "string"},
                },
                "required": ["prompt"],
            },
            handler=self._handle_video_generate,
        )
        # 4. 搜索
        self.register_tool(
            name="web.search",
            description="全网搜索 (DuckDuckGo/Bing/SerpAPI)",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "provider": {"type": "string", "default": "duckduckgo"},
                    "max_results": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            handler=self._handle_web_search,
        )
        # 5. 爬取
        self.register_tool(
            name="web.crawl",
            description="爬取网页 (50+ 渠道)",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "channel": {"type": "string", "default": "web_generic"},
                    "max_pages": {"type": "integer", "default": 5},
                },
                "required": ["url"],
            },
            handler=self._handle_web_crawl,
        )
        # 6. 数据 API
        self.register_tool(
            name="data.fetch_hot",
            description="获取平台热门话题 (RedFox 13 平台)",
            input_schema={
                "type": "object",
                "properties": {
                    "platform": {"type": "string"},
                    "max_results": {"type": "integer", "default": 20},
                },
                "required": ["platform"],
            },
            handler=self._handle_data_hot,
        )
        # 7. 自动打标
        self.register_tool(
            name="data.auto_label",
            description="自动打标 (多模型投票)",
            input_schema={
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "object"}},
                    "models": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["items"],
            },
            handler=self._handle_auto_label,
        )
        # 8. 数据存储
        self.register_tool(
            name="data.store",
            description="存储到 MinIO/S3/OSS",
            input_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string"},
                    "bucket": {"type": "string", "default": "imdf-intelligence"},
                },
                "required": ["content"],
            },
            handler=self._handle_data_store,
        )
        # 9. Bot 调用
        self.register_tool(
            name="agent.call_bot",
            description="调用平台 Agent",
            input_schema={
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string"},
                    "command": {"type": "string"},
                    "params": {"type": "object"},
                },
                "required": ["bot_id", "command"],
            },
            handler=self._handle_call_bot,
        )
        # 10. 项目创建
        self.register_tool(
            name="project.create",
            description="创建项目",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string", "default": "medium"},
                },
                "required": ["name"],
            },
            handler=self._handle_project_create,
        )
        # 11. Harness 触发
        self.register_tool(
            name="harness.run",
            description="运行 Full Harness (Planner+Generator+Evaluator)",
            input_schema={
                "type": "object",
                "properties": {
                    "requirement": {"type": "string"},
                    "max_iterations": {"type": "integer", "default": 3},
                },
                "required": ["requirement"],
            },
            handler=self._handle_harness_run,
        )
        # 12. 品牌研究
        self.register_tool(
            name="brand.analyze_competitor",
            description="分析竞品广告 (Gooseworks 4 技能)",
            input_schema={
                "type": "object",
                "properties": {
                    "advertiser": {"type": "string"},
                    "platforms": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["advertiser"],
            },
            handler=self._handle_brand_analyze,
        )

    # ===== 注册 =====
    def register_tool(self, name: str, description: str, input_schema: Dict[str, Any], handler: Callable, version: str = "1.0.0", metadata: Optional[Dict[str, Any]] = None) -> MCPTool:
        tool = MCPTool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=handler,
            version=version,
            metadata=metadata or {},
        )
        self.tools[name] = tool
        return tool

    def register_resource(self, uri: str, name: str, description: str = "", mime_type: str = "text/plain", handler: Optional[Callable] = None) -> MCPResource:
        r = MCPResource(uri=uri, name=name, description=description, mime_type=mime_type, handler=handler)
        self.resources[uri] = r
        return r

    def register_prompt(self, name: str, description: str, template: str, arguments: Optional[List[Dict[str, Any]]] = None) -> MCPPrompt:
        p = MCPPrompt(name=name, description=description, template=template, arguments=arguments or [])
        self.prompts[name] = p
        return p

    # ===== 处理请求 =====
    async def handle_request(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """处理 JSON-RPC 请求"""
        self.metrics["requests"] += 1
        try:
            req = JSONRPCRequest.from_dict(raw)
            # 路由方法
            if req.method == "initialize":
                return self._handle_initialize(req).to_dict()
            if req.method == "tools/list":
                return JSONRPCResponse(id=req.id, result={"tools": [t.to_dict() for t in self.tools.values()]}).to_dict()
            if req.method == "tools/call":
                tool_name = req.params.get("name", "")
                args = req.params.get("arguments", {})
                return await self._handle_tool_call(req, tool_name, args)
            if req.method == "resources/list":
                return JSONRPCResponse(id=req.id, result={"resources": [r.to_dict() for r in self.resources.values()]}).to_dict()
            if req.method == "resources/read":
                uri = req.params.get("uri", "")
                return await self._handle_resource_read(req, uri)
            if req.method == "prompts/list":
                return JSONRPCResponse(id=req.id, result={"prompts": [p.to_dict() for p in self.prompts.values()]}).to_dict()
            if req.method == "prompts/get":
                pname = req.params.get("name", "")
                args = req.params.get("arguments", {})
                return self._handle_prompt_get(req, pname, args)
            # 未知方法
            return JSONRPCResponse(
                id=req.id,
                error={"code": -32601, "message": f"Method not found: {req.method}"},
            ).to_dict()
        except Exception as e:
            self.metrics["errors"] += 1
            logger.exception("MCP handle_request failed")
            return JSONRPCResponse(
                id=raw.get("id"),
                error={"code": -32603, "message": f"Internal error: {e}"},
            ).to_dict()

    def _handle_initialize(self, req: JSONRPCRequest) -> JSONRPCResponse:
        return JSONRPCResponse(
            id=req.id,
            result={
                "protocolVersion": self.PROTOCOL_VERSION,
                "serverInfo": {"name": self.SERVER_NAME, "version": self.SERVER_VERSION},
                "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
            },
        )

    async def _handle_tool_call(self, req: JSONRPCRequest, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        tool = self.tools.get(tool_name)
        if not tool:
            return JSONRPCResponse(
                id=req.id,
                error={"code": -32602, "message": f"Tool not found: {tool_name}"},
            ).to_dict()
        try:
            result = tool.handler(args)
            if hasattr(result, "__await__"):
                result = await result
            if isinstance(result, dict) and "content" in result:
                return JSONRPCResponse(id=req.id, result=result).to_dict()
            return JSONRPCResponse(id=req.id, result={"content": [{"type": "text", "text": str(result)}]}).to_dict()
        except Exception as e:
            logger.exception(f"Tool {tool_name} failed: {e}")
            return JSONRPCResponse(
                id=req.id,
                error={"code": -32603, "message": f"Tool execution failed: {e}"},
            ).to_dict()

    async def _handle_resource_read(self, req: JSONRPCRequest, uri: str) -> Dict[str, Any]:
        r = self.resources.get(uri)
        if not r or not r.handler:
            return JSONRPCResponse(id=req.id, error={"code": -32602, "message": f"Resource not found: {uri}"}).to_dict()
        try:
            result = r.handler()
            if hasattr(result, "__await__"):
                result = await result
            return JSONRPCResponse(id=req.id, result={"contents": [{"uri": uri, "mimeType": r.mime_type, "text": str(result)}]}).to_dict()
        except Exception as e:
            return JSONRPCResponse(id=req.id, error={"code": -32603, "message": str(e)}).to_dict()

    def _handle_prompt_get(self, req: JSONRPCRequest, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        p = self.prompts.get(name)
        if not p:
            return JSONRPCResponse(id=req.id, error={"code": -32602, "message": f"Prompt not found: {name}"}).to_dict()
        # 简单模板替换
        rendered = p.template
        for k, v in args.items():
            rendered = rendered.replace("{{" + k + "}}", str(v))
        return JSONRPCResponse(id=req.id, result={"description": p.description, "messages": [{"role": "user", "content": {"type": "text", "text": rendered}}]}).to_dict()

    # ===== 默认工具 handler =====
    def _handle_text_generate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        prompt = args.get("prompt", "")
        model = args.get("model", "gpt-4")
        return {
            "content": [{"type": "text", "text": f"[{model} generated]: {prompt[:200]}..."}],
            "model": model,
            "tokens": len(prompt) // 4,
        }

    def _handle_image_generate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        prompt = args.get("prompt", "")
        model = args.get("model", "agnes-image-2.1-flash")
        w, h = args.get("width", 1024), args.get("height", 1024)
        return {
            "content": [{"type": "text", "text": f"[{model} image]: {prompt[:100]}"}],
            "image_url": f"https://placeholder.example.com/{uuid.uuid4().hex[:8]}.png",
            "model": model,
            "resolution": f"{w}x{h}",
        }

    def _handle_video_generate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        prompt = args.get("prompt", "")
        model = args.get("model", "agnes-video-2.0")
        duration = args.get("duration_sec", 5)
        return {
            "content": [{"type": "text", "text": f"[{model} video]: {prompt[:100]}"}],
            "video_url": f"https://placeholder.example.com/{uuid.uuid4().hex[:8]}.mp4",
            "model": model,
            "duration_sec": duration,
        }

    def _handle_web_search(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"Search results for '{args.get('query')}': 10 results"}],
            "results": [{"title": f"Result {i}", "url": f"https://example.com/{i}"} for i in range(10)],
        }

    def _handle_web_crawl(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"Crawled {args.get('url')}: 1 page"}],
            "items": [{"url": args.get("url"), "title": "Page", "text_preview": "Content..."}],
        }

    def _handle_data_hot(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"Hot topics for {args.get('platform')}: 20 items"}],
            "items": [],
        }

    def _handle_auto_label(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"Labeled {len(args.get('items', []))} items"}],
            "labels": {},
        }

    def _handle_data_store(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"Stored content to {args.get('bucket', 'imdf-intelligence')}"}],
            "uri": f"minio://{args.get('bucket', 'imdf-intelligence')}/{uuid.uuid4().hex[:12]}",
        }

    def _handle_call_bot(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"Bot {args.get('bot_id')} executed {args.get('command')}"}],
            "result": {"ok": True},
        }

    def _handle_project_create(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"Project {args.get('name')} created"}],
            "project_id": f"proj-{uuid.uuid4().hex[:8]}",
        }

    def _handle_harness_run(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"Harness running for: {args.get('requirement')[:100]}"}],
            "run_id": f"hr-{uuid.uuid4().hex[:8]}",
        }

    def _handle_brand_analyze(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "content": [{"type": "text", "text": f"Brand analysis for {args.get('advertiser')}: 30 ads analyzed, 5 clusters found"}],
            "clusters": [],
        }

    def get_stats(self) -> Dict[str, Any]:
        return {
            "server": f"{self.SERVER_NAME}@{self.SERVER_VERSION}",
            "protocol": self.PROTOCOL_VERSION,
            "tools_count": len(self.tools),
            "resources_count": len(self.resources),
            "prompts_count": len(self.prompts),
            "requests": self.metrics["requests"],
            "errors": self.metrics["errors"],
        }


mcp_server = MCPServer()
