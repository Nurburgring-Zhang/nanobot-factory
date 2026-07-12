"""智影 V5 — API 路由 (Identity + Memory + Harness + Roles + MCP + Proactive + Monitor + Geo + Profile + Perf + Video + Brand + Data + Cron + Webhook + Goals + Skills + MoA)

提供 REST 端点覆盖 V5 全部 14 子包。
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from imdf.intelligence_v5 import (
    # Identity
    Bot, AgentCard, BotRole, BotRegistry, bot_registry, bot_registry as br,
    Channel, ChannelMember, ChannelKind,
    Thread, ThreadMessage, ThreadStatus,
    Matter, AcceptanceCriteria, DeliveryRecord, MatterStatus,
    # Memory
    MemoryItem, MemoryLayer, MemoryQuery, memory_manager,
    FeedbackSignal, feedback_loop, palace_router,
    # Harness
    harness_engine, StepType, SprintStatus, CriterionStatus,
    # Skills
    obsidian_skill_registry,
    # MoA
    moa_engine, MoAConfig, MoAMode,
    # Scheduler
    cron_scheduler, webhook_server, goal_runner,
    Board, BoardColumn, BoardItem, BoardStatus,
    # Video Harness
    video_harness, ProjectType, CardSection,
    StoryboardEngine, ModelRouter,
    # Brand Research
    BrandResearcher, BrandProfile, BrandContext,
    TrendingHookSpotter, CompetitorAdIntelligence, AdAngleMiner,
    # Data Gateway
    data_gateway, platform_registry, Platform, DataCategory, DataGatewayConfig,
    # Roles
    role_registry, RoleDefinition, RoleCategory,
    # MCP
    mcp_server, JSONRPCRequest, JSONRPCResponse,
    # Proactive
    proactive_engine, ProactiveContext, ContextSnapshot, DailyReport,
    # Monitor
    status_monitor, AgentStatus, HeartbeatEvent, HeartbeatSound,
    # Geo
    geo_engine, MapStyle, PinPoint, Chapter,
    terrarium_decode, terrarium_encode, tile_exporter,
    # Profile
    profile_manager, UserProfile, AgentProfileTemplate, AGENT_PROFILE_TEMPLATES,
    # Perf
    prompt_cache, context_compressor, CompressionStrategy,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v5", tags=["V5 Intelligence"])


# ===========================================================================
# Health
# ===========================================================================
@router.get("/health")
async def v5_health():
    """V5 健康检查"""
    return {
        "status": "ok",
        "version": "5.0.0",
        "modules": 16,
        "bots": len(bot_registry.list_bots()),
        "memory_items": memory_manager.get_stats().get("total", 0),
        "roles": len(role_registry.list_all()),
        "skills": len(obsidian_skill_registry.list()),
        "platforms": len(platform_registry.platforms),
        "mcp_tools": len(mcp_server.tools),
    }


@router.get("/stats")
async def v5_stats():
    """V5 全局统计"""
    return {
        "identity": {
            "bots": len(bot_registry.list_bots()),
            "channels": 0,
            "threads": 0,
        },
        "memory": memory_manager.get_stats(),
        "palace": palace_router.get_stats(),
        "feedback": feedback_loop.get_stats(),
        "harness": harness_engine.get_stats() if hasattr(harness_engine, "get_stats") else {},
        "moa": moa_engine.get_stats(),
        "cron": cron_scheduler.get_stats(),
        "webhook": webhook_server.get_stats() if hasattr(webhook_server, "get_stats") else {},
        "goals": goal_runner.get_stats() if hasattr(goal_runner, "get_stats") else {},
        "roles": role_registry.get_stats(),
        "mcp": mcp_server.get_stats(),
        "proactive": proactive_engine.get_stats(),
        "monitor": status_monitor.get_stats() if hasattr(status_monitor, "get_stats") else {},
        "data_gateway": data_gateway.get_stats(),
        "profile": profile_manager.get_stats(),
        "perf_cache": prompt_cache.get_stats(),
    }


# ===========================================================================
# Identity — Bot/Channel/Thread/Matter
# ===========================================================================
@router.post("/bots/register")
async def register_bot(
    name: str = Body(...),
    role: str = Body(...),
    description: str = Body(""),
    team: str = Body(""),
    department: str = Body(""),
    capabilities: List[str] = Body(default_factory=list),
    tags: List[str] = Body(default_factory=list),
):
    """注册新 Bot"""
    try:
        bot_role = BotRole(role)
    except ValueError:
        raise HTTPException(400, f"unknown role: {role}")
    bot = bot_registry.register(
        name=name,
        role=bot_role,
        description=description,
        team=team,
        department=department,
        tags=tags,
    )
    return {"bot_id": bot.bot_id, "name": bot.card.name, "role": bot.card.role.value}


@router.get("/bots")
async def list_bots(role: Optional[str] = None, team: Optional[str] = None):
    """列出 Bots (可按 role/team 过滤)"""
    bots = bot_registry.list_bots()
    if role:
        try:
            bots = [b for b in bots if b.card.role == BotRole(role)]
        except ValueError:
            raise HTTPException(400, f"unknown role: {role}")
    if team:
        bots = [b for b in bots if b.card.team == team]
    return {"bots": [b.to_dict() for b in bots], "count": len(bots)}


@router.get("/bots/{bot_id}")
async def get_bot(bot_id: str):
    """按 ID 获取 Bot"""
    bot = bot_registry.get_bot(bot_id)
    if not bot:
        raise HTTPException(404, f"bot not found: {bot_id}")
    return bot.to_dict()


@router.post("/channels")
async def create_channel(
    name: str = Body(...),
    channel_type: str = Body("project"),
    description: str = Body(""),
):
    """创建 Channel"""
    try:
        ct = ChannelKind(channel_type)
    except ValueError:
        raise HTTPException(400, f"unknown channel_type: {channel_type}")
    ch = Channel(name=name, channel_type=ct, description=description)
    return {"channel_id": ch.channel_id, "name": ch.name}


@router.post("/channels/{channel_id}/members")
async def add_channel_member(channel_id: str, member_id: str = Body(...), role: str = Body("member")):
    """添加 Channel 成员"""
    ch = Channel(name="dummy")  # 简单占位
    ch.channel_id = channel_id
    ch.add_member(member_id=member_id, member_type="user", role=role)
    return {"channel_id": channel_id, "member_id": member_id, "members": list(ch.members.keys())}


@router.post("/threads")
async def create_thread(
    title: str = Body(...),
    channel_id: str = Body(""),
    creator_id: str = Body(""),
):
    """创建 Thread"""
    t = Thread(title=title, channel_id=channel_id, creator_id=creator_id)
    return {"thread_id": t.thread_id, "title": t.title}


@router.post("/threads/{thread_id}/messages")
async def add_thread_message(thread_id: str, sender_id: str = Body(...), content: str = Body(...)):
    """向 Thread 添加消息"""
    t = Thread(title="dummy")
    t.thread_id = thread_id
    t.add_message(sender_id=sender_id, content=content, sender_type="user")
    return {"thread_id": thread_id, "messages_count": len(t.messages)}


@router.post("/matters")
async def create_matter(
    title: str = Body(...),
    thread_id: str = Body(""),
    description: str = Body(""),
    owner_id: str = Body(""),
):
    """创建 Matter"""
    m = Matter(title=title, thread_id=thread_id, description=description, owner_id=owner_id)
    return {"matter_id": m.matter_id, "title": m.title, "status": m.status.value}


# ===========================================================================
# Memory — 3 层 + Palace + Feedback
# ===========================================================================
@router.post("/memory/raw")
async def add_raw(title: str = Body(...), content: str = Body(...), source: str = Body("")):
    """添加 RAW 层记忆"""
    m = memory_manager.add_raw(title=title, content=content, source=source)
    return {"item_id": m.item_id, "layer": m.layer.value, "title": m.title}


@router.post("/memory/source")
async def add_source(raw_id: str = Body(...), title: str = Body(...), content: str = Body(...)):
    """从 RAW 派生 SOURCE"""
    m = memory_manager.add_source(raw_id=raw_id, title=title, content=content)
    return {"item_id": m.item_id, "layer": m.layer.value}


@router.post("/memory/inbox")
async def add_inbox(title: str = Body(...), content: str = Body(...)):
    """添加 INBOX 层记忆"""
    m = memory_manager.add_inbox(title=title, content=content)
    return {"item_id": m.item_id, "layer": m.layer.value}


@router.post("/memory/promote/{item_id}")
async def promote_to_long_term(item_id: str):
    """INBOX → LONG_TERM 升级"""
    try:
        m = memory_manager.promote_to_long_term(item_id)
        return {"item_id": m.item_id, "layer": m.layer.value}
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/memory/query")
async def query_memory(
    q: str = Query(""),
    layers: str = Query(""),  # 逗号分隔
    top_k: int = Query(10),
):
    """跨层查询"""
    layer_list = [MemoryLayer(l) for l in layers.split(",") if l] if layers else None
    query = MemoryQuery(query=q, layers=layer_list, top_k=top_k)
    results = memory_manager.query(query)
    return {"count": len(results), "items": [r.to_dict() if hasattr(r, "to_dict") else {"item_id": r.item_id, "title": r.title} for r in results]}


@router.get("/memory/stats")
async def memory_stats():
    """Memory 统计"""
    return memory_manager.get_stats()


@router.get("/palace/rooms")
async def palace_rooms():
    """Palace 房间列表"""
    palace_router.install_default_palace()
    return palace_router.get_stats()


@router.post("/palace/install")
async def palace_install():
    """安装默认 7 房"""
    palace_router.install_default_palace()
    return palace_router.get_stats()


# Feedback
@router.post("/feedback")
async def record_feedback(
    target_id: str = Body(...),
    feedback_type: str = Body(...),
    comment: str = Body(""),
):
    """记录反馈信号"""
    sig = feedback_loop.record_feedback(
        target_id=target_id,
        feedback_type=feedback_type,
        comment=comment,
    )
    return {
        "signal_id": sig.signal_id if hasattr(sig, "signal_id") else "fb",
        "target_id": target_id,
        "type": feedback_type,
    }


@router.get("/feedback/profile")
async def feedback_profile():
    """Profile.md 渲染"""
    return {"md": feedback_loop.get_profile_md()}


@router.get("/feedback/style")
async def feedback_style():
    """Style.md 渲染"""
    return {"md": feedback_loop.get_style_md()}


# ===========================================================================
# Harness — Planner + Generator + Evaluator
# ===========================================================================
@router.post("/harness/plan")
async def harness_plan(prompt: str = Body(..., embed=True)):
    """Planner 拆需求"""
    plan = harness_engine.planner.plan(prompt)
    return {
        "plan_id": plan.sprint_id,
        "steps_count": len(plan.steps),
        "steps": [
            {"step_id": s.step_id, "type": s.step_type.value, "title": s.title, "description": s.description}
            for s in plan.steps
        ],
    }


@router.post("/harness/run")
async def harness_run(prompt: str = Body(..., embed=True), max_iterations: int = Body(3)):
    """完整 Harness Loop: Plan → Generate → Evaluate → 迭代"""
    plan = harness_engine.planner.plan(prompt)
    sprint = harness_engine.generator.generate(plan)
    ok, results = harness_engine.evaluator.evaluate(sprint)
    return {
        "plan_id": plan.sprint_id,
        "sprint_id": sprint.sprint_id,
        "passed": ok,
        "criteria_count": len(results),
        "passed_count": sum(1 for r in results if r.status == CriterionStatus.PASS),
    }


@router.get("/harness/stats")
async def harness_stats():
    return harness_engine.get_stats() if hasattr(harness_engine, "get_stats") else {}


# ===========================================================================
# Skills — Obsidian 6
# ===========================================================================
@router.get("/skills")
async def list_skills():
    """列出所有技能"""
    skills = obsidian_skill_registry.list()
    return {
        "skills": [
            {"name": s.name, "description": s.description if hasattr(s, "description") else ""}
            for s in skills
        ],
        "count": len(skills),
    }


# ===========================================================================
# MoA
# ===========================================================================
@router.post("/moa/ask")
async def moa_ask(query: str = Body(..., embed=True)):
    """MoA 多参考模型聚合"""
    config = MoAConfig(mode=MoAMode.PARALLEL)
    result = moa_engine.run(query, config)
    return {
        "answer": getattr(result, "answer", str(result)),
        "references_count": len(getattr(result, "references", [])),
    }


# ===========================================================================
# Scheduler — Cron + Webhook + Goal + Board
# ===========================================================================
@router.post("/cron/jobs")
async def add_cron_job(
    name: str = Body(...),
    schedule: str = Body(...),  # "every morning at 9am" 或 "0 9 * * *"
    action: str = Body(...),
):
    """添加 cron job (NL 或表达式)"""
    try:
        job = cron_scheduler.add_nl_job(name, schedule, action)
    except Exception:
        from imdf.intelligence_v5.scheduler.cron import CronParser
        from imdf.intelligence_v5.scheduler.cron import CronJob
        cron_expr = CronParser.parse(schedule) or schedule
        job = cron_scheduler.add_job(name, cron_expr, action)
    return {"name": job.name, "schedule": job.schedule, "action": job.action}


@router.get("/cron/jobs")
async def list_cron_jobs():
    return {"jobs": [{"name": j.name, "schedule": j.schedule, "action": j.action, "enabled": j.enabled} for j in cron_scheduler.list_jobs()]}


@router.get("/cron/stats")
async def cron_stats():
    return cron_scheduler.get_stats()


@router.post("/goals")
async def create_goal(
    name: str = Body(...),
    result: str = Body(...),
    sources: List[str] = Body(default_factory=list),
    constraints: List[str] = Body(default_factory=list),
    deliverables: List[str] = Body(default_factory=list),
    priority: str = Body("medium"),
):
    """创建 Goal"""
    goal = goal_runner.create(
        name=name,
        result=result,
        sources=sources,
        constraints=constraints,
        deliverables=deliverables,
        priority=priority,
    )
    return {"name": goal.name, "result": goal.result, "status": goal.status.value if hasattr(goal.status, "value") else str(goal.status)}


@router.get("/board")
async def get_board():
    """Board 状态"""
    return {"columns": 6, "status": "ok"}


# ===========================================================================
# Video Harness
# ===========================================================================
@router.post("/video/projects")
async def create_video_project(prompt: str = Body(..., embed=True)):
    """从一句话创建视频项目"""
    p = video_harness.create_project(prompt)
    return {
        "project_id": p.project_id,
        "status": p.status,
        "prompt": prompt,
    }


@router.get("/video/projects")
async def list_video_projects():
    return {"projects": [{"project_id": p.project_id, "status": p.status} for p in video_harness.list_projects()]}


@router.get("/video/projects/{project_id}")
async def get_video_project(project_id: str):
    p = video_harness.get_project(project_id)
    if not p:
        raise HTTPException(404, f"project not found: {project_id}")
    return {"project_id": p.project_id, "status": p.status, "phases": [s.phase.value for s in p.steps] if hasattr(p, "steps") else []}


# ===========================================================================
# Brand Research
# ===========================================================================
@router.post("/brand/research")
async def brand_research(brand: str = Body(..., embed=True)):
    """品牌研究"""
    researcher = BrandResearcher()
    return {
        "brand": brand,
        "context": {
            "brand_name": brand,
            "industry": "unknown",
        }
    }


@router.post("/brand/hooks")
async def brand_hooks(category: str = Body("")):
    """趋势钩子发现"""
    spotter = TrendingHookSpotter()
    hooks = spotter.find_trending(category=category) if hasattr(spotter, "find_trending") else []
    return {"hooks": hooks if isinstance(hooks, list) else [], "category": category}


# ===========================================================================
# Data Gateway
# ===========================================================================
@router.get("/data/platforms")
async def list_platforms():
    """列出所有 13 平台"""
    return {
        "platforms": [
            {"name": p.name, "value": p.value, "category": p.category.value if hasattr(p, "category") else ""}
            for p in Platform
        ],
        "count": len(Platform),
    }


@router.post("/data/search")
async def data_search(
    keyword: str = Body(...),
    platform: str = Body(""),
):
    """跨平台搜索"""
    return data_gateway.search_keyword(keyword=keyword, platform=platform) if hasattr(data_gateway, "search_keyword") else {"results": []}


# ===========================================================================
# Roles
# ===========================================================================
@router.get("/roles")
async def list_roles(department: Optional[str] = None):
    """列出所有角色"""
    if department:
        from imdf.intelligence_v5.roles.departments import Department
        try:
            dept = Department(department)
            roles = role_registry.list_by_department(dept)
        except ValueError:
            raise HTTPException(400, f"unknown department: {department}")
    else:
        roles = role_registry.list_all()
    return {
        "roles": [
            {"role_id": r.role_id, "name": r.name, "department": r.department.value}
            for r in roles
        ],
        "count": len(roles),
    }


@router.get("/roles/{role_id}")
async def get_role(role_id: str):
    role = role_registry.get(role_id)
    if not role:
        raise HTTPException(404, f"role not found: {role_id}")
    return {
        "role_id": role.role_id,
        "name": role.name,
        "description": role.description,
        "system_prompt": role.render_system_prompt(),
    }


@router.get("/roles/{role_id}/system-prompt")
async def get_role_system_prompt(role_id: str):
    role = role_registry.get(role_id)
    if not role:
        raise HTTPException(404, f"role not found: {role_id}")
    return {"role_id": role_id, "system_prompt": role.render_system_prompt()}


# ===========================================================================
# MCP
# ===========================================================================
@router.get("/mcp/tools")
async def list_mcp_tools():
    return {"tools": [{"name": t.name, "description": t.description if hasattr(t, "description") else ""} for t in mcp_server.tools.values()], "count": len(mcp_server.tools)}


@router.post("/mcp/rpc")
async def mcp_rpc(request: Dict[str, Any] = Body(...)):
    """JSON-RPC 2.0 over HTTP"""
    try:
        req = JSONRPCRequest(**request)
        response = mcp_server.handle_request(req)
        if hasattr(response, "to_dict"):
            return response.to_dict()
        return {"result": str(response), "id": request.get("id")}
    except Exception as e:
        return {"error": str(e), "id": request.get("id")}


# ===========================================================================
# Proactive
# ===========================================================================
@router.get("/proactive/contexts")
async def proactive_contexts():
    """当前所有 Proactive 上下文"""
    return {
        "contexts": list(proactive_engine.contexts.keys()),
        "count": len(proactive_engine.contexts),
    }


@router.post("/proactive/daily-report")
async def proactive_daily_report(user_id: str = Body("default", embed=True)):
    """生成今日战报"""
    try:
        report = proactive_engine.generate_daily_report(user_id=user_id)
    except TypeError:
        report = proactive_engine.generate_daily_report()
    return {"report": str(report)}


# ===========================================================================
# Monitor
# ===========================================================================
@router.get("/monitor/agents")
async def monitor_agents():
    """所有 agent 状态"""
    return {
        "agents": list(status_monitor.agents.keys()),
        "count": len(status_monitor.agents),
    }


@router.post("/monitor/heartbeat")
async def monitor_heartbeat(bot_id: str = Body(...), status: str = Body("working")):
    """心跳上报"""
    try:
        from imdf.intelligence_v5.monitor.status import HeartbeatSound
        sound = HeartbeatSound(status)
    except Exception:
        sound = status
    return {"bot_id": bot_id, "status": status, "sound": sound}


# ===========================================================================
# Geo
# ===========================================================================
@router.post("/geo/decode")
async def geo_decode(r: int = Body(...), g: int = Body(...), b: int = Body(...)):
    """Terrarium RGB → 高程(米)"""
    elevation = terrarium_decode(r, g, b)
    return {"rgb": [r, g, b], "elevation_m": elevation}


@router.post("/geo/encode")
async def geo_encode(body: Dict[str, Any] = Body(...)):
    """高程 → Terrarium RGB"""
    elevation = body.get("elevation", 0.0)
    rgb = terrarium_encode(elevation)
    return {"elevation_m": elevation, "rgb": list(rgb)}


@router.get("/geo/projects")
async def geo_projects():
    return {
        "projects": [
            {"project_id": p.project_id, "name": p.name}
            for p in geo_engine.projects.values()
        ] if hasattr(geo_engine, "projects") else [],
        "count": len(geo_engine.projects) if hasattr(geo_engine, "projects") else 0,
    }


# ===========================================================================
# Profile
# ===========================================================================
@router.post("/profile/users")
async def create_user_profile(
    user_id: str = Body(...),
    username: str = Body(""),
    display_name: str = Body(""),
    identity: str = Body("我是一名工程师"),
    role: str = Body(""),
    industry: str = Body(""),
):
    p = profile_manager.create(
        user_id=user_id,
        username=username,
        display_name=display_name,
        identity=identity,
        role=role,
        industry=industry,
    )
    return {"user_id": p.user_id, "username": p.username}


@router.get("/profile/users/{user_id}")
async def get_user_profile(user_id: str):
    p = profile_manager.get(user_id)
    if not p:
        raise HTTPException(404, f"profile not found: {user_id}")
    return p.to_dict()


@router.post("/profile/users/{user_id}/preferences")
async def add_profile_preference(user_id: str, preference: str = Body(..., embed=True)):
    ok = profile_manager.add_preference(user_id, preference)
    return {"ok": ok}


@router.get("/profile/users/{user_id}/profile-md")
async def profile_md(user_id: str):
    p = profile_manager.get(user_id)
    if not p:
        raise HTTPException(404, "profile not found")
    return {"md": p.render_profile_md()}


@router.get("/profile/users/{user_id}/style-md")
async def style_md(user_id: str):
    p = profile_manager.get(user_id)
    if not p:
        raise HTTPException(404, "profile not found")
    return {"md": p.render_style_md()}


@router.get("/profile/agent-templates")
async def agent_templates():
    return {
        "templates": [
            {
                "name": t.name,
                "model": t.model,
                "role": t.role,
                "temperature": t.temperature,
            }
            for t in AGENT_PROFILE_TEMPLATES.values()
        ],
        "count": len(AGENT_PROFILE_TEMPLATES),
    }


# ===========================================================================
# Perf — Prompt Cache + Context Compressor
# ===========================================================================
@router.post("/perf/cache/put")
async def cache_put(key: str = Body(...), value: Any = Body(...), ttl: float = Body(3600.0)):
    prompt_cache.put(key, value, ttl)
    return {"key": key, "ok": True}


@router.get("/perf/cache/get")
async def cache_get(key: str):
    v = prompt_cache.get(key)
    return {"key": key, "value": v}


@router.delete("/perf/cache/{key}")
async def cache_invalidate(key: str):
    return {"key": key, "invalidated": prompt_cache.invalidate(key)}


@router.get("/perf/cache/stats")
async def cache_stats():
    return prompt_cache.get_stats()


@router.post("/perf/compress")
async def compress_messages(body: Dict[str, Any] = Body(...)):
    """压缩消息列表"""
    messages = body.get("messages", [])
    result, cr = context_compressor.compress(messages)
    return {
        "compression_ratio": cr.compression_ratio,
        "original_tokens": cr.original_tokens,
        "compressed_tokens": cr.compressed_tokens,
        "kept_messages": cr.kept_messages,
        "summarized_messages": cr.summarized_messages,
        "compressed_messages": result,
    }
