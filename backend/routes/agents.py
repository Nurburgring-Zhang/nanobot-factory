"""Agent cluster routes — CRUD + chat"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
import json
import logging

# Lazy imports to avoid circular dependency
from llm_client import LLMProvider, ChatMessage

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_state():
    """Lazy import server state to avoid circular import"""
    from server import state
    return state


def _get_models():
    """Lazy import Pydantic models to avoid circular import"""
    from server import AgentRequest, AgentResponse
    return AgentRequest, AgentResponse


@router.get("/api/agents")
async def get_agents():
    """Get all agents"""
    state = _get_state()
    return list(state.agents.values())


@router.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get specific agent"""
    state = _get_state()
    agents = state.agents
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agents[agent_id]


@router.post("/api/agents")
async def create_agent(request: Dict[str, Any]):
    """Create a new agent"""
    state = _get_state()
    agent_id = request.get("id", request.get("name", "").lower().replace(" ", "_"))
    agent = {
        "id": agent_id,
        "name": request.get("name", ""),
        "model": request.get("model", "anthropic/claude-3.5-sonnet"),
        "provider": request.get("provider", "openrouter"),
        "system_prompt": request.get("system_prompt", "You are a helpful AI assistant."),
        "status": "inactive",
        "config": request.get("config", {}),
    }
    state.agents[agent_id] = agent
    return agent


@router.put("/api/agents/{agent_id}")
async def update_agent(agent_id: str, request: Dict[str, Any]):
    """Update an existing agent"""
    state = _get_state()
    agents = state.agents
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent = agents[agent_id]
    for field in ("name", "model", "provider", "system_prompt", "status"):
        if field in request:
            agent[field] = request[field]
    if "config" in request:
        agent["config"] = request["config"]

    return agent


@router.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete an agent"""
    state = _get_state()
    agents = state.agents
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    del state.agents[agent_id]
    return {"success": True}


async def execute_agent_capability(agent_id: str, message: str, agent: dict) -> Optional[dict]:
    """Execute agent capability based on message content"""
    capabilities = agent.get("capabilities", [])
    message_lower = message.lower()

    keyword_map = {
        "image_generation": (["生成图片", "create image", "画图", "生成一张图"], "image_generation"),
        "video_generation": (["生成视频", "create video", "制作视频"], "video_generation"),
        "3d_generation": (["生成3d", "create 3d", "3d模型"], "3d_generation"),
        "auto_classification": (["分类", "classify", "打标签", "tag"], "data_classification"),
        "quality_scoring": (["评分", "score", "质量", "评估"], "quality_analysis"),
        "image_upscale": (["增强", "放大", "upscale", "enhance", "优化"], "data_enhancement"),
        "video_enhance": (["增强", "放大", "upscale", "enhance", "优化"], "data_enhancement"),
        "batch_generation": (["批量", "batch", "多个"], "batch_production"),
        "data_management": (["查询", "搜索", "找", "管理", "query", "search"], "database_query"),
    }

    for cap, (keywords, resp_type) in keyword_map.items():
        if cap in capabilities:
            if any(kw in message_lower for kw in keywords):
                return {"type": resp_type, "prompt": message}

    return None


@router.post("/api/agents/{agent_id}/chat")
async def chat_with_agent(agent_id: str, request_body: Dict[str, Any]):
    """Chat with an agent"""
    state = _get_state()
    AgentRequest, AgentResponse = _get_models()
    request = AgentRequest(**request_body)

    agents = state.agents
    if agent_id not in agents:
        raise HTTPException(status_code=404, detail="Agent not found")

    agents[agent_id]["status"] = "active"
    agent = agents[agent_id]

    provider_str = agent.get("provider", "openrouter")
    model = agent.get("model", "anthropic/claude-3.5-sonnet")

    try:
        provider_map = {
            "openai": LLMProvider.OPENAI,
            "anthropic": LLMProvider.ANTHROPIC,
            "google": LLMProvider.GOOGLE,
            "openrouter": LLMProvider.OPENROUTER,
        }
        provider = provider_map.get(provider_str.lower(), LLMProvider.OPENROUTER)

        messages = []
        if request.context:
            context_str = json.dumps(request.context)
            messages.append({"role": "system", "content": f"Context: {context_str}"})

        messages.append({"role": "user", "content": request.message})

        llm_manager = state.llm_manager
        if not llm_manager:
            raise HTTPException(status_code=503, detail="LLM manager not initialized")

        response = await llm_manager.chat_with_history(
            messages=messages,
            provider=provider,
            model=model,
            temperature=0.7,
            max_tokens=4096,
        )

        response_message = response.content
        logger.info(f"Agent {agent_id} responded with {len(response.content)} chars")

    except Exception as e:
        logger.error(f"Error calling LLM for agent {agent_id}: {e}")
        error_msg = str(e).lower()
        if "api key" in error_msg or "unauthorized" in error_msg:
            response_message = "API密钥无效或已过期，请检查配置。"
        elif "quota" in error_msg or "rate limit" in error_msg:
            response_message = "API配额已用尽或达到速率限制，请稍后再试。"
        elif "timeout" in error_msg or "connection" in error_msg:
            response_message = "连接超时，请检查网络并重试。"
        elif "model" in error_msg and "not found" in error_msg:
            response_message = f"模型 {model} 不可用，正在尝试备用模型..."
            try:
                fallback_model = "anthropic/claude-3.5-sonnet"
                logger.info(f"Trying fallback model: {fallback_model}")
                response = await llm_manager.chat_with_history(
                    messages=messages,
                    provider=provider,
                    model=fallback_model,
                    temperature=0.7,
                    max_tokens=4096,
                )
                response_message = response.content
            except Exception as fallback_error:
                logger.error(f"Fallback model also failed: {fallback_error}")
                response_message = "抱歉，当前AI服务暂时不可用。请检查API密钥配置或稍后再试。"
        else:
            response_message = "抱歉，处理您的请求时发生错误。请重试或稍后再试。"

    capability_result = await execute_agent_capability(agent_id, request.message, agent)
    if capability_result:
        logger.info(f"Agent {agent_id} capability triggered: {capability_result['type']}")

    agents[agent_id]["status"] = "idle"
    return AgentResponse(message=response_message, agent_id=agent_id, status="success")

