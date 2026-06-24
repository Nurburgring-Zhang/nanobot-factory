"""P3-3-W1 + P4-3-W1: Agent service package.

The ``agent-service`` FastAPI app (port 8008) hosts the 15 Agent type catalogue,
Agent task dispatch + execution, and Agent memory storage.  The service is the
single entry point for all agent-driven workflows in the platform.

Submodules
----------
- ``agents``           — 15 AgentType enum + default configs
- ``scheduler``        — Task routing, resource allocation, retry policy
- ``executor``         — 3 execution modes (full-auto / semi-auto / manual)
- ``memory``           — Short-term + long-term Agent memory (P3-3-W1)
- ``memory/multi_turn``— Multi-turn session context (P4-3-W1)
- ``instructions``     — AgentInstructions stack (P4-3-W1)
- ``tools/registry``   — ToolRegistry + 13 built-in tools (P4-3-W1)
- ``variables``        — Variable store + template engine (P4-3-W1)
- ``loader``           — SOUL.md / AGENTS.md hot-reload (P4-3-W1)
- ``store``            — In-memory + SQLite task store
- ``routes``           — FastAPI router
- ``main``             — FastAPI app factory + lifespan

Endpoints
---------
- ``GET  /healthz``                                    — liveness
- ``GET  /api/v1/agents``                              — list all 15 agent types
- ``GET  /api/v1/agents/types``                        — type catalogue
- ``GET  /api/v1/agents/{agent_type}``                 — single agent detail
- ``POST /api/v1/agents/{agent_type}/run``             — run an agent (sync)
- ``POST /api/v1/agent_tasks``                         — create an agent task
- ``GET  /api/v1/agent_tasks``                         — list tasks
- ``GET  /api/v1/agent_tasks/{task_id}``               — task detail + status
- ``POST /api/v1/agent_tasks/{task_id}/cancel``        — cancel a task
- ``POST /api/v1/agent_tasks/{task_id}/retry``         — retry a failed task
- ``GET  /api/v1/agent_tasks/stats``                   — task stats by status
- ``GET  /api/v1/agent_memory/{scope}``                — long-term memory list
- ``PUT  /api/v1/agent_memory/{scope}/{key}``          — long-term memory upsert

P4-3-W1 additions:
- Multi-turn sessions: ``/api/v1/agent/sessions`` + messages / summary / usage
- Agent instructions:  ``/api/v1/agent/instructions`` + render
- Tools registry:      ``/api/v1/agent/tools`` + invoke + audit
- Variables:           ``/api/v1/agent/variables`` + render
- SOUL loader:         ``/api/v1/agent/soul`` + refresh
"""
