"""
F0.3: 多模型网关 API Routes
=============================
GET  /api/models   → 列出所有可用模型
POST /api/chat     → 统一聊天（自动路由+降级+熔断）
GET  /api/models/health → 模型健康检查
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field

from engines.model_gateway import get_gateway, ChatResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["model-gateway"])


# ─── Request/Response Models ────────────────────────────────────────────────


class ChatMessage(BaseModel):
    role: str = "user"          # user / assistant / system
    content: str = ""


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="对话消息列表")
    model: str = Field("auto", description="模型ID或'auto'自动选择")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int = Field(4096, ge=1, le=131072, description="最大输出token数")


class ModelInfoResponse(BaseModel):
    id: str
    provider: str
    display_name: str
    capabilities: List[str]
    max_tokens: int
    default: bool
    enabled: bool
    priority: int


# ─── Routes ──────────────────────────────────────────────────────────────────


@router.get("/models", response_model=Dict[str, Any])
async def list_models():
    """
    列出所有可用的AI模型。

    Returns:
        {
            "success": true,
            "data": [
                {
                    "id": "deepseek-chat",
                    "provider": "deepseek",
                    "display_name": "DeepSeek Chat",
                    "capabilities": ["chat"],
                    "max_tokens": 8192,
                    "default": true,
                    "enabled": true,
                    "priority": 0
                },
                ...
            ],
            "providers": [...],
            "default_model": "deepseek-chat"
        }
    """
    gateway = get_gateway()
    models = await gateway.list_models()
    providers = gateway.get_providers_info()
    return {
        "success": True,
        "data": models,
        "providers": providers,
        "default_model": gateway._default_model,
        "total": len(models),
    }


@router.post("/chat", response_model=Dict[str, Any])
async def unified_chat(req: ChatRequest):
    """
    统一聊天接口 — 自动路由、失败降级、熔断保护。

    示例请求:
        POST /api/chat
        {
            "messages": [
                {"role": "user", "content": "你好，请介绍一下自己"}
            ],
            "model": "auto",
            "temperature": 0.7,
            "max_tokens": 4096
        }

    返回:
        {
            "success": true,
            "content": "你好！我是...",
            "model": "deepseek-chat",
            "provider": "deepseek",
            "usage": {"prompt_tokens": 10, "completion_tokens": 50, "total_tokens": 60},
            "latency_ms": 1234.5
        }
    """
    gateway = get_gateway()

    # Convert Pydantic messages to plain dicts
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    response: ChatResponse = await gateway.chat(
        messages=messages,
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )

    return response.to_dict()


@router.get("/models/health", response_model=Dict[str, Any])
async def model_health_check(model: Optional[str] = None):
    """
    模型健康检查。

    Query参数:
        model: 可选，指定模型ID。不传则检查所有Provider。

    Returns:
        {
            "success": true,
            "status": "ok|degraded|down",
            "models": {
                "deepseek-chat": {"status": "ok", "latency_ms": 123.4},
                ...
            }
        }
    """
    gateway = get_gateway()
    result = await gateway.health_check(model)
    return {"success": True, **result}
