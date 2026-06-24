"""P3-3-W1: agent-service FastAPI app (port 8008).

The single entry point for the Agent dispatch framework + 15 agent types.

# P4-1-W1: refactored — see backend/common/ for the shared library.
"""
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.agent_service.agents import AGENT_REGISTRY
from services.agent_service.routes import router as agent_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise the singletons on startup so first request isn't penalised.
    from services.agent_service.executor import get_executor
    from services.agent_service.scheduler import get_scheduler
    from services.agent_service.store import get_store
    get_store()
    get_scheduler()
    get_executor()
    # P4-3-W2: initialise memory subsystems (MemoryPalace + Hindsight) and
    # register MCP tools/resources/prompts.  All are lazy-safe — they no-op
    # until a real request comes in, but the registry is built once.
    from services.agent_service.hindsight import get_hindsight
    from services.agent_service.mcp import get_mcp_server
    from services.agent_service.memory_palace import get_memory_palace
    get_memory_palace()
    get_hindsight()
    get_mcp_server()
    # P4-3-W1: multi-turn sessions / instructions / tools / variables / SOUL loader
    from services.agent_service.memory import get_long_term, get_short_term
    from services.agent_service.memory.multi_turn import get_session_manager
    from services.agent_service.instructions import get_instructions
    from services.agent_service.variables import get_variable_store
    from services.agent_service.tools.registry import get_tool_registry
    from services.agent_service.loader import get_loader
    get_long_term()
    get_short_term()
    get_session_manager()
    get_instructions()
    get_variable_store()
    get_tool_registry()
    get_loader()  # also starts the SOUL.md hot-reload watcher
    yield

app = create_app(
    "agent_service",
    description=(
        "Agent dispatch framework + 15 Agent type catalogue "
        "(P3-3-W1).  P4-3-W1 adds multi-turn session memory, agent "
        "instructions, tools/variables registry, and SOUL.md / AGENTS.md "
        "hot-reload.  P4-3-W2 layers on MemoryPalace, Hindsight, and MCP."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

# Routers
app.include_router(agent_router)
# P4-3-W2: 6-layer MemoryPalace + 4-layer Hindsight endpoints
from services.agent_service.routes_memory import router as memory_router  # noqa: E402
from services.agent_service.routes_mcp import router as mcp_router  # noqa: E402
app.include_router(memory_router)
app.include_router(mcp_router)
# P4-8-W1: extended-skills framework (10 built-in skills + SkillOrchestrator
# + Obsidian view + Skill marketplace).
try:
    from skills import api as skills_api
    app.include_router(skills_api.router)
    # Eager-load built-in skills so /api/v1/skills returns them immediately.
    import skills.builtin  # noqa: F401  -- side-effect: register @skill classes
    from skills.registry import SKILL_REGISTRY
    from skills.marketplace import get_marketplace
    get_marketplace()  # sync_from_registry() on first call
    import logging as _p48_log
    _p48_log.getLogger(__name__).info(
        "P4-8-W1: mounted skills router (registered=%d, marketplace populated)",
        len(SKILL_REGISTRY),
    )
except Exception as _p48_err:  # noqa: BLE001
    import logging as _p48_log
    _p48_log.getLogger(__name__).warning(
        "P4-8-W1 skills mount skipped: %s", _p48_err)

@app.get("/")
async def root() -> dict:
    return {
        "service": "agent-service",
        "version": "0.1.0",
        "agent_types": [t.value for t in AGENT_REGISTRY.keys()],
        "endpoints": {
            "healthz": ["/healthz"],
            "agents": [
                "/api/v1/agents",
                "/api/v1/agents/types",
                "/api/v1/agents/{agent_type}",
                "/api/v1/agents/{agent_type}/run",
            ],
            "tasks": [
                "/api/v1/agent_tasks",
                "/api/v1/agent_tasks/{task_id}",
                "/api/v1/agent_tasks/{task_id}/cancel",
                "/api/v1/agent_tasks/{task_id}/retry",
                "/api/v1/agent_tasks/stats",
            ],
            "memory": [
                "/api/v1/agent_memory/{scope}",
                "/api/v1/agent_memory/{scope}/{key}",
            ],
            "scheduler": ["/api/v1/scheduler/state"],
            # P4-3-W1
            "sessions": [
                "/api/v1/agent/sessions",
                "/api/v1/agent/sessions/{session_id}",
                "/api/v1/agent/sessions/{session_id}/messages",
                "/api/v1/agent/sessions/{session_id}/summary",
                "/api/v1/agent/sessions/{session_id}/usage",
                "/api/v1/agent/usage",
            ],
            "instructions": [
                "/api/v1/agent/instructions",
                "/api/v1/agent/instructions/{fragment_id}",
                "/api/v1/agent/instructions/render",
            ],
            "tools": [
                "/api/v1/agent/tools",
                "/api/v1/agent/tools/{name}",
                "/api/v1/agent/tools/{name}/invoke",
                "/api/v1/agent/tools/audit",
                "/api/v1/agent/tools/reload",
            ],
            "variables": [
                "/api/v1/agent/variables",
                "/api/v1/agent/variables/{var_id}",
                "/api/v1/agent/variables/render",
            ],
            "soul": ["/api/v1/agent/soul", "/api/v1/agent/soul/refresh"],
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="agent_service",
        adapter=MultimodalAdapter(service_id="agent_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for agent_service: %%s", _mm_err)


__all__ = ["app"]
