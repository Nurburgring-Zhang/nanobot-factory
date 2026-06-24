"""
Agent v2 API routes — 基于 agent/ 模块的真实调用链

通过 AgentLoopEngine、EnhancedMemorySystem、ModelRouter、
AgentOrchestrator、AgentClusterManager 提供完整的 Agent 能力。

所有端点挂载在 /api/v2/agents/ 下，不与 /api/agents/ 冲突。
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, Optional, List
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


# ===========================================================================
# 依赖注入
# ===========================================================================

def _get_state():
    """Lazy import server state to avoid circular import"""
    from server import state, AGENT_SYSTEM_AVAILABLE
    return state, AGENT_SYSTEM_AVAILABLE


def _require_agent_system():
    """确保 Agent 系统可用"""
    from server import AGENT_SYSTEM_AVAILABLE
    if not AGENT_SYSTEM_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Agent system is not available. Check server logs for details."
        )


# ===========================================================================
# Pydantic 请求/响应模型
# ===========================================================================

try:
    from pydantic import BaseModel, Field

    class AgentChatRequest(BaseModel):
        message: str = Field(..., description="用户消息")
        session_id: Optional[str] = Field(None, description="已有会话 ID，为空则创建新会话")
        user_id: str = Field("default", description="用户标识")
        agent_type: str = Field("general", description="Agent 类型")
        context: Optional[Dict[str, Any]] = Field(None, description="额外上下文")

    class AgentChatResponse(BaseModel):
        success: bool
        message: str
        session_id: str
        thoughts: Optional[List[Dict[str, Any]]] = None
        tool_calls: Optional[List[Dict[str, Any]]] = None
        error: Optional[str] = None

    class AgentExecuteRequest(BaseModel):
        task: str = Field(..., description="任务描述")
        agent_type: str = Field("general", description="Agent 类型")
        context: Optional[Dict[str, Any]] = Field(None, description="额外上下文")

    class AgentExecuteResponse(BaseModel):
        success: bool
        task_id: str
        result: Any = None
        error: Optional[str] = None
        duration_ms: Optional[float] = None

    class AgentInfo(BaseModel):
        id: str
        name: str
        status: str
        capabilities: List[str] = []
        model: str = ""
        description: str = ""

    class AgentSystemStatus(BaseModel):
        available: bool
        agent_loop: bool = False
        model_router: bool = False
        enhanced_memory: bool = False
        orchestrator: bool = False
        cluster_manager: bool = False
        active_sessions: int = 0
        registered_tools: int = 0

except ImportError:
    BaseModel = None
    AgentChatRequest = None
    AgentChatResponse = None
    AgentExecuteRequest = None
    AgentExecuteResponse = None
    AgentInfo = None
    AgentSystemStatus = None


# ===========================================================================
# API 端点
# ===========================================================================

@router.post("/api/v2/agents/chat")
async def agent_chat(request_body: Dict[str, Any]):
    """
    通过 AgentLoopEngine 进行对话

    支持 ReAct 推理循环、虚拟工具调用、会话管理。
    """
    _require_agent_system()
    state, _ = _get_state()

    message = request_body.get("message", "")
    if not message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    session_id = request_body.get("session_id")
    user_id = request_body.get("user_id", "default")
    agent_type = request_body.get("agent_type", "general")
    context = request_body.get("context")

    agent_loop = state.agent_loop
    if not agent_loop:
        raise HTTPException(status_code=503, detail="AgentLoopEngine not initialized")

    try:
        # 创建新会话或使用已有会话
        if not session_id or not await agent_loop.get_session(session_id):
            session_id = await agent_loop.create_session(
                user_id=user_id,
                agent_type=agent_type,
                metadata={"source": "api_v2"},
            )

        # 运行 Agent 循环
        result = await agent_loop.run(
            session_id=session_id,
            user_input=message,
            context=context,
        )

        return {
            "success": result.get("success", False),
            "message": result.get("result", ""),
            "session_id": session_id,
            "thoughts": result.get("thoughts", []),
            "tool_calls": result.get("tool_calls", []),
            "error": result.get("error"),
        }

    except Exception as e:
        logger.error(f"Agent chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v2/agents/execute")
async def agent_execute(request_body: Dict[str, Any]):
    """
    通过 AgentOrchestrator 执行 Agent 任务

    支持任务编排、多步工作流、子任务分发。
    """
    _require_agent_system()
    state, _ = _get_state()

    task = request_body.get("task", "")
    if not task.strip():
        raise HTTPException(status_code=400, detail="task is required")

    agent_type = request_body.get("agent_type", "general")
    context = request_body.get("context")

    start_time = datetime.now()

    orchestrator = state.orchestrator
    agent_loop = state.agent_loop

    if not agent_loop:
        raise HTTPException(status_code=503, detail="AgentLoopEngine not initialized")

    try:
        # 创建会话并执行任务
        session_id = await agent_loop.create_session(
            user_id="system",
            agent_type=agent_type,
            metadata={"mode": "execute", "source": "api_v2"},
        )

        result = await agent_loop.run(
            session_id=session_id,
            user_input=task,
            context=context or {},
        )

        duration_ms = (datetime.now() - start_time).total_seconds() * 1000

        return {
            "success": result.get("success", False),
            "task_id": session_id,
            "result": result.get("result", ""),
            "error": result.get("error"),
            "duration_ms": round(duration_ms, 2),
        }

    except Exception as e:
        logger.error(f"Agent execute error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v2/agents")
async def list_agents():
    """
    列出所有可用 Agent

    从 AgentClusterManager 获取已注册的 Agent 列表。
    """
    state, available = _get_state()

    if not available:
        return {"agents": [], "source": "fallback"}

    try:
        agents_list = []

        # 从 cluster_manager 获取
        cluster_mgr = state.cluster_manager
        if cluster_mgr and hasattr(cluster_mgr, 'list_agents'):
            registered = cluster_mgr.list_agents()
            for agent in registered:
                agents_list.append({
                    "id": getattr(agent, 'id', ''),
                    "name": getattr(agent, 'name', ''),
                    "status": getattr(agent, 'status', 'unknown'),
                    "model": getattr(agent, 'model', ''),
                    "capabilities": getattr(agent, 'capabilities', []),
                })

        # 从 state.agents 补充
        for agent_id, agent_info in state.agents.items():
            if not any(a.get("id") == agent_id for a in agents_list):
                agents_list.append({
                    "id": agent_id,
                    "name": agent_info.get("name", agent_id),
                    "status": agent_info.get("status", "idle"),
                    "model": agent_info.get("model", ""),
                    "capabilities": agent_info.get("capabilities", []),
                })

        return {"agents": agents_list, "source": "agent_module"}
    except Exception as e:
        logger.warning(f"list_agents (agent) error: {e}")
        return {"agents": list(state.agents.values()), "source": "fallback"}


@router.get("/api/v2/agents/status")
async def agent_system_status():
    """获取 Agent 系统状态"""
    state, available = _get_state()

    if not available:
        return {
            "available": False,
            "message": "Agent system not initialized",
        }

    try:
        agent_loop = state.agent_loop
        enhanced_memory = state.enhanced_memory
        model_router = state.model_router_agent
        orchestrator = state.orchestrator
        cluster_mgr = state.cluster_manager

        active_sessions = 0
        registered_tools = 0

        if agent_loop:
            if hasattr(agent_loop, '_sessions'):
                active_sessions = len(agent_loop._sessions)
            if hasattr(agent_loop, '_tools'):
                registered_tools = len(agent_loop._tools)

        return {
            "available": True,
            "agent_loop": agent_loop is not None,
            "model_router": model_router is not None,
            "enhanced_memory": enhanced_memory is not None,
            "orchestrator": orchestrator is not None,
            "cluster_manager": cluster_mgr is not None,
            "active_sessions": active_sessions,
            "registered_tools": registered_tools,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"agent system status error: {e}")
        return {"available": False, "error": str(e)}


@router.post("/api/v2/agents/chat/simple")
async def agent_chat_simple(request_body: Dict[str, Any]):
    """
    简化对话接口 — 无会话管理，即发即收

    适用场景：一次性查询、无需上下文的快速问答。
    """
    _require_agent_system()
    state, _ = _get_state()

    message = request_body.get("message", "")
    if not message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    agent_loop = state.agent_loop
    if not agent_loop:
        raise HTTPException(status_code=503, detail="AgentLoopEngine not initialized")

    try:
        # 为每次请求创建独立会话
        session_id = await agent_loop.create_session(
            user_id=request_body.get("user_id", "anonymous"),
            agent_type="general",
            metadata={"mode": "simple", "source": "api_v2"},
        )

        result = await agent_loop.run(
            session_id=session_id,
            user_input=message,
            context=request_body.get("context"),
        )

        return {
            "success": result.get("success", False),
            "message": result.get("result", " "),
            "error": result.get("error"),
        }

    except Exception as e:
        logger.error(f"Agent simple chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
