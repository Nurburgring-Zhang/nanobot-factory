"""P3-3-W1 + P4-3-W1: agent-service FastAPI routes.

Public REST surface (port 8008):

  GET    /healthz
  GET    /api/v1/agents
  GET    /api/v1/agents/types
  GET    /api/v1/agents/{agent_type}
  POST   /api/v1/agents/{agent_type}/run
  POST   /api/v1/agent_tasks
  GET    /api/v1/agent_tasks
  GET    /api/v1/agent_tasks/stats
  GET    /api/v1/agent_tasks/{task_id}
  POST   /api/v1/agent_tasks/{task_id}/cancel
  POST   /api/v1/agent_tasks/{task_id}/retry
  GET    /api/v1/agent_memory/{scope}
  GET    /api/v1/agent_memory/{scope}/{key}
  PUT    /api/v1/agent_memory/{scope}/{key}
  DELETE /api/v1/agent_memory/{scope}/{key}
  GET    /api/v1/scheduler/state

P4-3-W1 additions:
  POST   /api/v1/agent/sessions                  — create a multi-turn session
  GET    /api/v1/agent/sessions                  — list sessions
  GET    /api/v1/agent/sessions/{session_id}     — session detail
  DELETE /api/v1/agent/sessions/{session_id}     — drop session
  POST   /api/v1/agent/sessions/{session_id}/messages
  GET    /api/v1/agent/sessions/{session_id}/messages
  POST   /api/v1/agent/sessions/{session_id}/summary
  GET    /api/v1/agent/sessions/{session_id}/usage
  GET    /api/v1/agent/usage                     — global + per-user rollup

  GET    /api/v1/agent/instructions              — list
  POST   /api/v1/agent/instructions              — create
  GET    /api/v1/agent/instructions/{fragment_id}
  PUT    /api/v1/agent/instructions/{fragment_id}
  DELETE /api/v1/agent/instructions/{fragment_id}
  POST   /api/v1/agent/instructions/render       — render merged system prompt

  GET    /api/v1/agent/tools                     — list built-in + custom tools
  GET    /api/v1/agent/tools/{name}              — tool detail
  POST   /api/v1/agent/tools/{name}/invoke       — call a tool
  GET    /api/v1/agent/tools/audit               — audit chain
  POST   /api/v1/agent/tools/reload              — rescan custom_tools/

  GET    /api/v1/agent/variables                 — list
  PUT    /api/v1/agent/variables                 — upsert
  DELETE /api/v1/agent/variables/{var_id}        — delete
  POST   /api/v1/agent/variables/render          — render a template

  GET    /api/v1/agent/soul                      — current SOUL/AGENTS content
  POST   /api/v1/agent/soul/refresh              — force a reload
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from .agents import (
    AGENT_REGISTRY,
    AgentType,
    ExecutionMode,
    get_agent_config,
    list_agent_summaries,
)
from .executor import get_executor
from .instructions import (
    InstructionFragment,
    InstructionScope,
    get_instructions,
)
from .loader import get_loader
from .memory import get_long_term, get_short_term
from .memory.multi_turn import get_session_manager
from .scheduler import get_scheduler
from .store import TaskStatus, get_store
from .tools.registry import get_tool_registry
from .variables import VariableNamespace, get_variable_store, render_template

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-service"])


# ── Schemas ─────────────────────────────────────────────────────────────────
class CreateTaskRequest(BaseModel):
    agent_type: str = Field(..., description="One of the 15 AgentType slugs")
    payload: Dict[str, Any] = Field(default_factory=dict)
    mode: Optional[str] = Field(
        None,
        description="Override the agent's default mode (full_auto / semi_auto / manual).",
    )
    priority: Optional[int] = Field(None, ge=1, le=10)
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=86400)
    submitted_by: Optional[str] = "anonymous"
    parent_task_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    # If true, run synchronously and return the result inline.
    run_inline: bool = False


class RunAgentRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    mode: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    submitted_by: Optional[str] = "anonymous"


class MemoryUpsertRequest(BaseModel):
    value: Any


# ── /healthz ────────────────────────────────────────────────────────────────
@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    store = get_store()
    short = get_short_term()
    long_ = get_long_term()
    return {
        "status": "ok",
        "service": "agent-service",
        "version": "0.1.0",
        "agent_types": len(AGENT_REGISTRY),
        "short_term_keys": len(short.list()),
        "long_term_db": long_._db_path is not None,  # noqa: SLF001 — internal probe
        "task_stats": store.stats(),
    }


# ── /api/v1/agents ─────────────────────────────────────────────────────────
@router.get("/api/v1/agents")
async def list_agents() -> Dict[str, Any]:
    """Return the full 15-agent catalogue."""
    return {
        "count": len(AGENT_REGISTRY),
        "agents": list_agent_summaries(),
    }


@router.get("/api/v1/agents/types")
async def list_agent_types() -> Dict[str, Any]:
    """Return the list of agent type slugs (for dropdowns)."""
    return {
        "count": len(AGENT_REGISTRY),
        "types": [t.value for t in AgentType],
    }


@router.get("/api/v1/agents/{agent_type}")
async def get_agent(agent_type: str) -> Dict[str, Any]:
    try:
        cfg = get_agent_config(agent_type)
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"unknown_agent_type:{agent_type}",
        )
    out = dict(cfg)
    out["default_mode"] = (
        cfg["default_mode"].value
        if isinstance(cfg["default_mode"], ExecutionMode)
        else cfg["default_mode"]
    )
    return out


@router.post("/api/v1/agents/{agent_type}/run")
async def run_agent(agent_type: str, body: RunAgentRequest) -> Dict[str, Any]:
    """Submit + run an agent inline.  Returns the execution result."""
    try:
        get_agent_config(agent_type)
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"unknown_agent_type:{agent_type}",
        )
    cfg = get_agent_config(agent_type)
    mode = body.mode or (
        cfg["default_mode"].value
        if isinstance(cfg["default_mode"], ExecutionMode)
        else cfg["default_mode"]
    )
    priority = body.priority if body.priority is not None else cfg["default_priority"]
    store = get_store()
    task = store.create(
        agent_type=agent_type,
        payload=body.payload,
        mode=mode,
        priority=priority,
        max_retries=cfg["max_retries"],
        timeout_seconds=cfg["timeout_seconds"],
        submitted_by=body.submitted_by or "anonymous",
    )
    executor = get_executor()
    result = executor.run(task.task_id)
    return {"task": task.to_dict(), "result": result}


# ── /api/v1/agent_tasks ────────────────────────────────────────────────────
@router.post("/api/v1/agent_tasks")
async def create_task(body: CreateTaskRequest) -> Dict[str, Any]:
    """Submit a task (returns the task record; ``run_inline=true`` to execute)."""
    try:
        cfg = get_agent_config(body.agent_type)
    except KeyError:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"unknown_agent_type:{body.agent_type}",
        )

    mode = body.mode or (
        cfg["default_mode"].value
        if isinstance(cfg["default_mode"], ExecutionMode)
        else cfg["default_mode"]
    )
    priority = body.priority if body.priority is not None else cfg["default_priority"]
    max_retries = (
        body.max_retries if body.max_retries is not None else cfg["max_retries"]
    )
    timeout_seconds = (
        body.timeout_seconds if body.timeout_seconds is not None else cfg["timeout_seconds"]
    )

    store = get_store()
    task = store.create(
        agent_type=body.agent_type,
        payload=body.payload,
        mode=mode,
        priority=priority,
        max_retries=max_retries,
        timeout_seconds=timeout_seconds,
        submitted_by=body.submitted_by or "anonymous",
        parent_task_id=body.parent_task_id,
        metadata=body.metadata,
    )
    if body.run_inline:
        result = get_executor().run(task.task_id)
        return {"task": get_store().get(task.task_id).to_dict(), "result": result}
    return {"task": task.to_dict()}


@router.get("/api/v1/agent_tasks")
async def list_tasks(
    status: Optional[str] = None,
    agent_type: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    items = get_store().list(status=status, agent_type=agent_type, limit=limit)
    return {
        "count": len(items),
        "tasks": [t.to_dict() for t in items],
    }


@router.get("/api/v1/agent_tasks/stats")
async def task_stats() -> Dict[str, Any]:
    return get_store().stats()


@router.get("/api/v1/agent_tasks/{task_id}")
async def get_task(task_id: str) -> Dict[str, Any]:
    task = get_store().get(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task_not_found")
    return task.to_dict()


@router.post("/api/v1/agent_tasks/{task_id}/cancel")
async def cancel_task(task_id: str) -> Dict[str, Any]:
    task = get_executor().cancel(task_id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task_not_found")
    return task.to_dict()


@router.post("/api/v1/agent_tasks/{task_id}/retry")
async def retry_task(task_id: str) -> Dict[str, Any]:
    task = get_executor().retry(task_id)
    if task is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="task_not_found_or_not_retriable",
        )
    return task.to_dict()


# ── /api/v1/agent_memory ───────────────────────────────────────────────────
@router.get("/api/v1/agent_memory/{scope}")
async def list_memory(scope: str, limit: int = 100) -> Dict[str, Any]:
    items = get_long_term().list(scope, limit=limit)
    return {"scope": scope, "count": len(items), "items": items}


@router.get("/api/v1/agent_memory/{scope}/{key}")
async def get_memory(scope: str, key: str) -> Dict[str, Any]:
    val = get_long_term().get(scope, key)
    if val is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="memory_not_found")
    return {"scope": scope, "key": key, "value": val}


@router.put("/api/v1/agent_memory/{scope}/{key}")
async def put_memory(scope: str, key: str, body: MemoryUpsertRequest) -> Dict[str, Any]:
    mem_id = get_long_term().upsert(scope, key, body.value)
    return {"scope": scope, "key": key, "id": mem_id, "ok": True}


@router.delete("/api/v1/agent_memory/{scope}/{key}")
async def delete_memory(scope: str, key: str) -> Dict[str, Any]:
    deleted = get_long_term().delete(scope, key)
    return {"scope": scope, "key": key, "deleted": deleted}


# ── /api/v1/scheduler (diagnostic) ─────────────────────────────────────────
@router.get("/api/v1/scheduler/state")
async def scheduler_state() -> Dict[str, Any]:
    return {"buckets": get_scheduler().bucket_state()}


# ════════════════════════════════════════════════════════════════════════════
# P4-3-W1 — Multi-turn sessions
# ════════════════════════════════════════════════════════════════════════════
class CreateSessionRequest(BaseModel):
    user_id: str = Field(..., description="Owner user id")
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AddMessageRequest(BaseModel):
    role: str = Field(..., description="user|assistant|system|tool")
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("/api/v1/agent/sessions")
async def create_session(body: CreateSessionRequest) -> Dict[str, Any]:
    mgr = get_session_manager()
    ctx = mgr.create(
        user_id=body.user_id,
        session_id=body.session_id,
        metadata=body.metadata,
    )
    return ctx.to_dict()


@router.get("/api/v1/agent/sessions")
async def list_sessions(user_id: Optional[str] = None, limit: int = 50) -> Dict[str, Any]:
    items = get_session_manager().list(user_id=user_id, limit=limit)
    return {"count": len(items), "sessions": [s.to_dict() for s in items]}


@router.get("/api/v1/agent/sessions/{session_id}")
async def get_session(session_id: str) -> Dict[str, Any]:
    ctx = get_session_manager().get(session_id)
    if ctx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session_not_found")
    return ctx.to_dict()


@router.delete("/api/v1/agent/sessions/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    ok = get_session_manager().delete(session_id)
    return {"session_id": session_id, "deleted": ok}


@router.post("/api/v1/agent/sessions/{session_id}/messages")
async def add_message(session_id: str, body: AddMessageRequest) -> Dict[str, Any]:
    mgr = get_session_manager()
    try:
        msg = mgr.add_message(
            session_id=session_id,
            role=body.role,
            content=body.content,
            tool_calls=body.tool_calls,
            tool_call_id=body.tool_call_id,
            name=body.name,
            metadata=body.metadata,
        )
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return msg.to_dict()


@router.get("/api/v1/agent/sessions/{session_id}/messages")
async def list_messages(session_id: str, limit: Optional[int] = None) -> Dict[str, Any]:
    items = get_session_manager().get_messages(session_id, limit=limit)
    return {"session_id": session_id, "count": len(items), "messages": items}


@router.post("/api/v1/agent/sessions/{session_id}/summary")
async def summarize_session(session_id: str) -> Dict[str, Any]:
    mgr = get_session_manager()
    try:
        summary = mgr.summarize(session_id)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"session_id": session_id, "summary": summary}


@router.get("/api/v1/agent/sessions/{session_id}/usage")
async def get_session_usage(session_id: str) -> Dict[str, Any]:
    return {
        "session_id": session_id,
        "usage": get_session_manager().get_usage(session_id).to_dict(),
    }


@router.get("/api/v1/agent/usage")
async def usage_rollup() -> Dict[str, Any]:
    return {"snapshot": get_session_manager().usage_snapshot()}


# ════════════════════════════════════════════════════════════════════════════
# P4-3-W1 — Agent instructions
# ════════════════════════════════════════════════════════════════════════════
class InstructionCreate(BaseModel):
    name: str
    content: str
    scope: str = Field("user", description="system|project|user|per_session")
    session_id: Optional[str] = None
    description: str = ""
    priority: int = 100
    enabled: bool = True


class InstructionUpdate(BaseModel):
    name: Optional[str] = None
    content: Optional[str] = None
    scope: Optional[str] = None
    session_id: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class RenderInstructionsRequest(BaseModel):
    session_id: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None


def _validate_scope(value: str) -> InstructionScope:
    try:
        return InstructionScope(value)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid_scope:{value}",
        )


@router.get("/api/v1/agent/instructions")
async def list_instructions(
    scope: Optional[str] = None,
    session_id: Optional[str] = None,
    enabled_only: bool = False,
) -> Dict[str, Any]:
    sc = _validate_scope(scope) if scope else None
    items = get_instructions().list(
        scope=sc, session_id=session_id, enabled_only=enabled_only
    )
    return {
        "count": len(items),
        "summary": get_instructions().list_summary(),
        "items": [f.to_dict() for f in items],
    }


@router.post("/api/v1/agent/instructions")
async def create_instruction(body: InstructionCreate) -> Dict[str, Any]:
    sc = _validate_scope(body.scope)
    if sc == InstructionScope.SYSTEM:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="cannot_create_system_fragment",
        )
    frag = InstructionFragment(
        name=body.name,
        content=body.content,
        scope=sc,
        session_id=body.session_id,
        description=body.description,
        priority=int(body.priority),
        enabled=bool(body.enabled),
    )
    saved = get_instructions().add(frag)
    return saved.to_dict()


@router.get("/api/v1/agent/instructions/{fragment_id}")
async def get_instruction(fragment_id: str) -> Dict[str, Any]:
    f = get_instructions().get(fragment_id)
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="fragment_not_found")
    return f.to_dict()


@router.put("/api/v1/agent/instructions/{fragment_id}")
async def update_instruction(fragment_id: str, body: InstructionUpdate) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    if body.scope is not None:
        fields["scope"] = _validate_scope(body.scope)
    for k in ("name", "content", "session_id", "description", "priority", "enabled"):
        v = getattr(body, k)
        if v is not None:
            fields[k] = v
    f = get_instructions().update(fragment_id, **fields)
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="fragment_not_found")
    return f.to_dict()


@router.delete("/api/v1/agent/instructions/{fragment_id}")
async def delete_instruction(fragment_id: str) -> Dict[str, Any]:
    ok = get_instructions().delete(fragment_id)
    return {"fragment_id": fragment_id, "deleted": ok}


@router.post("/api/v1/agent/instructions/render")
async def render_instructions(body: RenderInstructionsRequest) -> Dict[str, Any]:
    text = get_instructions().render(
        session_id=body.session_id,
        variables=body.variables,
    )
    return {"prompt": text, "length": len(text)}


# ════════════════════════════════════════════════════════════════════════════
# P4-3-W1 — Tools
# ════════════════════════════════════════════════════════════════════════════
class InvokeToolRequest(BaseModel):
    args: Optional[Dict[str, Any]] = None
    actor: str = "anonymous"


@router.get("/api/v1/agent/tools")
async def list_tools(tag: Optional[str] = None, builtin_only: bool = False) -> Dict[str, Any]:
    tools = get_tool_registry().list(tag=tag, builtin_only=builtin_only)
    return {"count": len(tools), "tools": [t.to_dict() for t in tools]}


@router.get("/api/v1/agent/tools/audit")
async def tool_audit(
    limit: int = 100,
    tool: Optional[str] = None,
    actor: Optional[str] = None,
    since_seq: int = 0,
    verify: bool = True,
) -> Dict[str, Any]:
    """Return HMAC-signed tool audit records (P6-Fix-B-3 / P6-3 F-3.5).

    Query params
    ------------
    limit     : int  — max rows to return (default 100, capped at 1000)
    tool      : str  — filter by tool name (exact match)
    actor     : str  — filter by actor (exact match)
    since_seq : int  — return only records with seq > since_seq
    verify    : bool — run HMAC verify_chain and include integrity status

    Response
    --------
    {
      "count":     int,
      "limit":     int,
      "tool":      str | None,
      "actor":     str | None,
      "since_seq": int,
      "chain_ok":  bool | None,  # None when verify=False or chain unavailable
      "bad_seq":   int,          # -1 when chain_ok=True/None
      "records":   [ToolAuditRecord, ...]
    }
    """
    safe_limit = max(1, min(int(limit), 1000))
    try:
        from services.agent_service.tools.audit import get_tool_audit_chain
        return get_tool_audit_chain().query(
            tool=tool,
            actor=actor,
            limit=safe_limit,
            since_seq=int(since_seq),
            verify=bool(verify),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("tool audit endpoint fallback to in-memory chain: %s", exc)
        return {
            "count": safe_limit,
            "limit": safe_limit,
            "tool": tool,
            "actor": actor,
            "since_seq": since_seq,
            "chain_ok": None,
            "bad_seq": -1,
            "records": get_tool_registry().audit_chain(limit=safe_limit),
            "fallback": "in_memory",
        }


@router.get("/api/v1/agent/tools/audit/verify")
async def tool_audit_verify() -> Dict[str, Any]:
    """Verify HMAC integrity of the underlying audit chain.

    Returns ``{"chain_ok": bool, "bad_seq": int, "reason": str | None}``.
    When the chain is unavailable returns ``chain_ok=None``.
    """
    try:
        from services.agent_service.tools.audit import get_tool_audit_chain
        return get_tool_audit_chain().verify()
    except Exception as exc:  # noqa: BLE001
        return {"chain_ok": None, "bad_seq": -1, "reason": f"unavailable: {exc}"}


@router.post("/api/v1/agent/tools/reload")
async def tool_reload() -> Dict[str, Any]:
    n = get_tool_registry().reload_custom_tools()
    return {"reloaded": n, "total": len(get_tool_registry().list_names())}


@router.get("/api/v1/agent/tools/{name}")
async def get_tool(name: str) -> Dict[str, Any]:
    t = get_tool_registry().get(name)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="tool_not_found")
    return t.to_dict()


@router.post("/api/v1/agent/tools/{name}/invoke")
async def invoke_tool(name: str, body: InvokeToolRequest) -> Dict[str, Any]:
    try:
        entry = get_tool_registry().invoke(name, body.args, actor=body.actor)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    return entry


# ════════════════════════════════════════════════════════════════════════════
# P4-3-W1 — Variables
# ════════════════════════════════════════════════════════════════════════════
class SetVariableRequest(BaseModel):
    name: str
    value: Any
    namespace: str = "user"
    owner: Optional[str] = None
    description: str = ""


class RenderVariableRequest(BaseModel):
    template: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    turn: Optional[Dict[str, Any]] = None
    project: Optional[Dict[str, Any]] = None


def _validate_namespace(value: str) -> VariableNamespace:
    try:
        return VariableNamespace(value)
    except ValueError:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid_namespace:{value}",
        )


@router.get("/api/v1/agent/variables")
async def list_variables(
    namespace: Optional[str] = None,
    owner: Optional[str] = None,
) -> Dict[str, Any]:
    ns = _validate_namespace(namespace) if namespace else None
    items = get_variable_store().list(namespace=ns, owner=owner)
    return {
        "count": len(items),
        "summary": get_variable_store().summary(),
        "items": [v.to_dict() for v in items],
    }


@router.put("/api/v1/agent/variables")
async def set_variable(body: SetVariableRequest) -> Dict[str, Any]:
    ns = _validate_namespace(body.namespace)
    try:
        v = get_variable_store().set(
            name=body.name,
            value=body.value,
            namespace=ns,
            owner=body.owner,
            description=body.description,
        )
    except PermissionError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc))
    return v.to_dict()


@router.delete("/api/v1/agent/variables/{var_id}")
async def delete_variable(var_id: str) -> Dict[str, Any]:
    ok = get_variable_store().delete(var_id)
    return {"var_id": var_id, "deleted": ok}


@router.post("/api/v1/agent/variables/render")
async def render_variable(body: RenderVariableRequest) -> Dict[str, Any]:
    flat = get_variable_store().resolve(
        session_id=body.session_id,
        user_id=body.user_id,
        turn=body.turn,
        project=body.project,
    )
    out = render_template(body.template, flat)
    return {"template": body.template, "variables": flat, "rendered": out}


# ════════════════════════════════════════════════════════════════════════════
# P4-3-W1 — SOUL / AGENTS loader
# ════════════════════════════════════════════════════════════════════════════
@router.get("/api/v1/agent/soul")
async def get_soul() -> Dict[str, Any]:
    loader = get_loader()
    return {
        "soul": loader.current_soul(),
        "last_refresh": loader.last_refresh,
        "project_root": loader.project_root,
    }


@router.post("/api/v1/agent/soul/refresh")
async def refresh_soul() -> Dict[str, Any]:
    loader = get_loader()
    info = loader.refresh()
    return info
