"""智影 V4 — API 路由: Agent 对话窗口 + 智能数据采集控制面板"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence-v4"])

# 全局 orchestrator (单例)
_orchestrator = None


def get_orchestrator():
    """获取 orchestrator 单例"""
    global _orchestrator
    if _orchestrator is None:
        from imdf.intelligence.data_acquisition.orchestrator import DataAcquisitionOrchestrator
        _orchestrator = DataAcquisitionOrchestrator()
    return _orchestrator


class ChatRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    user_id: str = "default"


class ChatResponse(BaseModel):
    session_id: str
    user_text: str
    intent: str
    action: str
    success: bool
    response: str
    output: Optional[Any] = None
    suggestions: List[str] = Field(default_factory=list)
    error: Optional[str] = None
    duration_ms: float = 0.0


class CrawlRequest(BaseModel):
    url: str
    channel: str = "web_generic"
    max_pages: int = 10
    max_depth: int = 0
    strategy: str = "bfs"
    compliance_mode: str = "strict"


class CrawlResponse(BaseModel):
    success: bool
    url: str
    channel: str
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total_crawled: int = 0
    total_kept: int = 0
    metrics: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class SearchRequest(BaseModel):
    query: str
    provider: str = "duckduckgo"
    max_results: int = 20


class SessionInfo(BaseModel):
    session_id: str
    user_id: str
    started_at: float
    last_active: float
    history_count: int
    working_set_size: int
    status: str


@router.get("/")
async def v4_root():
    """V4 健康 + 能力概览"""
    orch = get_orchestrator()
    return {
        "name": "智影 V4 — 智能数据采集 & 全 Agent 驱动",
        "version": "4.0.0",
        "modules": {
            "crawler_channels": len(orch.dispatcher.list_supported_channels()),
            "platform_agents": len(orch.router.agents),
            "intent_actions": len(orch.router.list_routes()),
        },
        "agents": list(orch.router.agents.keys()),
        "channels_sample": [
            "web_generic", "web_playwright", "api_rest", "api_graphql",
            "rss_generic", "social_reddit", "social_hackernews",
            "file_s3", "file_minio", "search_duckduckgo", "search_bing",
            "deep_bfs", "deep_citation", "academic_arxiv", "academic_pubmed",
        ],
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """主对话接口 — 同步"""
    orch = get_orchestrator()
    result = orch.chat(req.text, session_id=req.session_id, user_id=req.user_id)
    return ChatResponse(
        session_id=result.session_id,
        user_text=result.user_text,
        intent=result.parsed_command.intent.category.value,
        action=result.parsed_command.action,
        success=result.router_result.success,
        response=result.response_text,
        output=result.router_result.output if result.router_result.success else None,
        suggestions=result.suggestions,
        error=result.router_result.error,
        duration_ms=result.router_result.duration_ms,
    )


@router.get("/chat")
async def chat_get(
    text: str = Query(..., description="User input"),
    session_id: Optional[str] = Query(None),
    user_id: str = Query("default"),
):
    """主对话接口 — GET 版本 (便于浏览器直接测试)"""
    req = ChatRequest(text=text, session_id=session_id, user_id=user_id)
    return await chat(req)


@router.post("/crawl", response_model=CrawlResponse)
async def crawl(req: CrawlRequest):
    """手动 crawl 接口"""
    from imdf.intelligence.crawler.base import ChannelType
    from imdf.intelligence.crawler.dispatcher import CrawlerDispatcher
    try:
        ch = ChannelType(req.channel)
    except ValueError:
        raise HTTPException(400, f"unknown channel: {req.channel}")
    dispatcher = CrawlerDispatcher()
    config = type("C", (), {"channel_type": ch, "max_pages": req.max_pages, "max_depth": req.max_depth, "selectors": {"strategy": req.strategy}})()
    # 用真实 config 类型
    from imdf.intelligence.crawler.base import CrawlerConfig
    config = CrawlerConfig(channel_type=ch, max_pages=req.max_pages, max_depth=req.max_depth)
    if req.strategy:
        config.selectors["strategy"] = req.strategy
    crawler = dispatcher.get_crawler(config)
    try:
        results: List[Dict[str, Any]] = []
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async for doc in crawler.crawl([req.url]):
                results.append({
                    "url": doc.url,
                    "title": doc.title,
                    "type": doc.type,
                    "text_preview": (doc.text or "")[:500],
                    "images_count": len(doc.images or []),
                    "links_count": len(doc.links or []),
                    "crawled_at": doc.crawled_at,
                })
        finally:
            loop.close()
        return CrawlResponse(
            success=True,
            url=req.url,
            channel=req.channel,
            items=results[:50],
            total_crawled=len(results),
            total_kept=len(results),
            metrics=crawler.get_metrics(),
        )
    except Exception as e:
        logger.exception("crawl failed")
        return CrawlResponse(success=False, url=req.url, channel=req.channel, error=str(e))


@router.post("/search")
async def search(req: SearchRequest):
    """搜索接口"""
    from imdf.intelligence.crawler.base import ChannelType, CrawlerConfig
    from imdf.intelligence.crawler.dispatcher import CrawlerDispatcher
    provider_map = {
        "duckduckgo": ChannelType.SEARCH_DUCKDUCKGO,
        "serpapi": ChannelType.SEARCH_SERPAPI,
        "google_cse": ChannelType.SEARCH_GOOGLE_CSE,
        "bing": ChannelType.SEARCH_BING,
        "brave": ChannelType.SEARCH_BRAVE,
    }
    ch = provider_map.get(req.provider, ChannelType.SEARCH_DUCKDUCKGO)
    dispatcher = CrawlerDispatcher()
    config = CrawlerConfig(channel_type=ch, max_pages=req.max_results)
    config.selectors["query"] = req.query
    config.selectors["provider"] = req.provider
    crawler = dispatcher.get_crawler(config)
    results: List[Dict[str, Any]] = []
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        try:
            doc = loop.run_until_complete(crawler.fetch(f"{req.provider}://{req.query}"))
        finally:
            loop.close()
        # 提取 results — 多种可能
        if isinstance(doc.json, dict):
            for key in ("results", "posts", "papers", "articles", "items", "entries", "stories"):
                if key in doc.json:
                    results = doc.json[key]
                    break
    except Exception as e:
        logger.exception("search failed")
        return {"success": False, "query": req.query, "provider": req.provider, "error": str(e)}
    return {
        "success": True,
        "query": req.query,
        "provider": req.provider,
        "results": results[: req.max_results],
        "total": len(results),
    }


@router.get("/sessions")
async def list_sessions(user_id: Optional[str] = None):
    """列出会话"""
    orch = get_orchestrator()
    if user_id:
        sessions = orch.session_manager.get_user_sessions(user_id)
    else:
        sessions = list(orch.session_manager.sessions.values())
    return {
        "success": True,
        "sessions": [
            SessionInfo(
                session_id=s.session_id,
                user_id=s.context.user_id,
                started_at=s.context.started_at,
                last_active=s.context.last_active,
                history_count=len(s.context.history),
                working_set_size=len(s.context.working_set),
                status=s.status,
            ).model_dump()
            for s in sessions
        ],
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, history_limit: int = 20):
    """获取会话详情"""
    orch = get_orchestrator()
    s = orch.session_manager.get_session(session_id)
    if s is None:
        raise HTTPException(404, f"session not found: {session_id}")
    return {
        "success": True,
        "session": SessionInfo(
            session_id=s.session_id,
            user_id=s.context.user_id,
            started_at=s.context.started_at,
            last_active=s.context.last_active,
            history_count=len(s.context.history),
            working_set_size=len(s.context.working_set),
            status=s.status,
        ).model_dump(),
        "history": s.context.history[-history_limit:],
        "last_intent": s.context.last_intent,
        "variables": s.context.variables,
    }


@router.delete("/sessions/{session_id}")
async def close_session(session_id: str):
    """关闭会话"""
    orch = get_orchestrator()
    orch.session_manager.close_session(session_id)
    return {"success": True, "session_id": session_id, "status": "closed"}


@router.get("/status")
async def status():
    """全平台状态"""
    orch = get_orchestrator()
    return {"success": True, "status": orch.get_status()}


@router.get("/channels")
async def channels():
    """列出所有支持的渠道"""
    from imdf.intelligence.crawler.base import ChannelType, ComplianceMode
    orch = get_orchestrator()
    return {
        "success": True,
        "channels": [c.value for c in orch.dispatcher.list_supported_channels()],
        "total": len(orch.dispatcher.list_supported_channels()),
        "compliance_modes": [m.value for m in ComplianceMode],
    }


@router.get("/agents")
async def agents():
    """列出所有平台 Agent"""
    orch = get_orchestrator()
    return {
        "success": True,
        "agents": [
            {
                "name": name,
                **agent.get_metrics(),
            }
            for name, agent in orch.router.agents.items()
        ],
    }


@router.get("/actions")
async def actions():
    """列出所有可路由 action"""
    orch = get_orchestrator()
    return {
        "success": True,
        "actions": orch.router.list_routes(),
        "total": len(orch.router.list_routes()),
    }


@router.get("/help")
async def help():
    """帮助"""
    from imdf.intelligence.platform_agents.system import HELP_TEXT
    return {"success": True, "text": HELP_TEXT}


# ===== WebSocket 流式对话 =====
@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """WebSocket 端点 — 流式对话"""
    await websocket.accept()
    orch = get_orchestrator()
    session_id = None
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except Exception:
                payload = {"text": data}
            text = payload.get("text", "")
            sid = payload.get("session_id") or session_id
            user_id = payload.get("user_id", "default")
            if not text:
                await websocket.send_json({"type": "error", "error": "empty text"})
                continue
            # 执行
            result = orch.chat(text, session_id=sid, user_id=user_id)
            session_id = result.session_id
            # 发送
            await websocket.send_json(
                {
                    "type": "turn",
                    "session_id": result.session_id,
                    "intent": result.parsed_command.intent.category.value,
                    "action": result.parsed_command.action,
                    "success": result.router_result.success,
                    "response": result.response_text,
                    "output": result.router_result.output if result.router_result.success else None,
                    "suggestions": result.suggestions,
                    "error": result.router_result.error,
                    "duration_ms": round(result.router_result.duration_ms, 2),
                }
            )
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected (session: {session_id})")
    except Exception as e:
        logger.exception("websocket error")
        try:
            await websocket.send_json({"type": "error", "error": str(e)})
        except Exception:
            pass
