"""
F0.3: 多模型网关 API Routes
===============================
GET  /api/models   → 列出所有可用模型
POST /api/chat     → 统一聊天（自动路由+降级+熔断）
GET  /api/models/health → 模型健康检查

P11-A 变更:
- ``unified_chat`` 内部从 ``gateway.chat()`` (model_gateway.ModelGateway) 切换到
  ``call_provider_smart`` (provider_registry.P5-W1 统一入口), 这样 ``/api/chat``
  真正走限流/熔断/mock 降级/usage 记账/audit_chain 全链路。
- ``model_gateway`` 仍可通过 ``get_gateway()`` 用于 ``list_models`` / ``health_check``。
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

    P11-A: 内部从 ``gateway.chat()`` 切换到 ``call_provider_smart`` (P5-W1 统一入口),
    让 ``/api/chat`` 真正走 provider_registry 的限流/熔断/mock 降级/usage 记账/audit_chain。

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
            "model": "gpt-4o-mini",
            "provider": "openai-compatible",
            "provider_id": "openai-compatible",
            "cost_usd": 0.00021,
            "usage": {"prompt_tokens": 10, "completion_tokens": 50, "total_tokens": 60},
            "latency_ms": 1234.5,
            "mock": false
        }
    """
    # Convert Pydantic messages to plain dicts
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    # P11-A: 走 call_provider_smart 统一入口
    try:
        from engines.provider_registry import (
            call_provider_smart,
            _get_default_providers,
        )
    except ImportError as e:
        # import 失败 → 回退到老 gateway 路径
        logger.warning(f"unified_chat: provider_registry import failed ({e}); falling back to gateway.chat()")
        gateway = get_gateway()
        response: ChatResponse = await gateway.chat(
            messages=messages,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return response.to_dict()

    # 1. 选定 provider (enabled + chatModels 都齐的第一个; 否则第一个有 chatModels 的)
    provider = None
    for p in _get_default_providers() or []:
        if p.get("enabled") and p.get("chatModels"):
            provider = p
            break
    if not provider:
        for p in _get_default_providers() or []:
            if p.get("chatModels"):
                provider = p
                break

    # 2. 没 provider → 全部 disabled → 回退 gateway.chat
    if not provider:
        logger.warning("unified_chat: no enabled chat provider; falling back to gateway.chat()")
        gateway = get_gateway()
        response: ChatResponse = await gateway.chat(
            messages=messages,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return response.to_dict()

    # 3. 解析请求 model → 选具体模型
    requested_model = (req.model or "").strip()
    if requested_model and requested_model != "auto":
        model = requested_model
    else:
        model = (provider.get("defaults") or {}).get("chatModel", "") or (provider.get("chatModels") or ["gpt-4o-mini"])[0]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(req.temperature),
        "max_tokens": int(req.max_tokens),
    }

    # 4. 调 call_provider_smart (限流 + 熔断 + mock 降级 + usage 记账 + audit_chain)
    result = await call_provider_smart(
        provider, payload, kind="chat",
        user_id="anonymous",
        org_id="",
    )

    # 5. 把 result 映射成老 gateway 接口的返回结构 (向后兼容前端)
    if result.get("ok") and isinstance(result.get("data"), dict):
        content = (
            (result["data"].get("choices") or [{}])[0]
            .get("message", {}).get("content", "")
            or (result["data"].get("content", ""))
        )
        usage_raw = result["data"].get("usage") or {}
        usage = {
            "prompt_tokens": int(usage_raw.get("prompt_tokens", 0)),
            "completion_tokens": int(usage_raw.get("completion_tokens", 0)),
            "total_tokens": int(usage_raw.get("total_tokens", 0)),
        }
        return {
            "success": True,
            "content": content,
            "model": result["data"].get("model", model),
            "provider": provider.get("id"),
            "provider_id": result.get("provider_id", provider.get("id")),
            "cost_usd": result.get("cost_usd", 0.0),
            "usage": usage,
            "usage_tokens": result.get("usage_tokens", 0),
            "latency_ms": 0.0,
            "mock": result.get("mock", False),
        }

    # 6. 失败 — 兼容老接口的 error 结构
    return {
        "success": False,
        "error": result.get("error") or f"call_provider_smart failed: {result.get('code', 'unknown')}",
        "code": result.get("code", "unknown"),
        "provider_id": result.get("provider_id", provider.get("id")),
        "model": model,
        "content": "",
    }


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
