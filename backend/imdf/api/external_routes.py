"""
F3.3: External Agent Mounting API
==================================
POST /api/external/register -> Register external API/Agent
Supports ComfyUI, MCP, and Dify protocols.
Workflow nodes can reference registered external capabilities.
"""
import uuid
import time
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from enum import Enum

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/external", tags=["external"])

# ── Protocol types ──

class ExternalProtocol(str, Enum):
    COMFYUI = "comfyui"
    MCP = "mcp"
    DIFY = "dify"
    WEBHOOK = "webhook"

# ── Request/Response Models ──

class ExternalRegisterRequest(BaseModel):
    name: str = Field(..., description="External agent/service name")
    protocol: ExternalProtocol = Field(..., description="Protocol type")
    endpoint: str = Field(..., description="Service endpoint URL")
    api_key: Optional[str] = Field(None, description="API key for authentication")
    description: Optional[str] = Field("", description="Human-readable description")
    capabilities: Optional[List[str]] = Field(default_factory=list, description="List of capabilities")
    workflow_node_type: Optional[str] = Field(None, description="Corresponding workflow node type")
    config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Protocol-specific config")
    health_check_path: Optional[str] = Field("/health", description="Health check path relative to endpoint")

class ExternalAgentInfo(BaseModel):
    id: str
    name: str
    protocol: str
    endpoint: str
    description: str
    capabilities: List[str]
    workflow_node_type: Optional[str]
    status: str = "unknown"
    registered_at: str
    last_health_check: Optional[str] = None
    config: Dict[str, Any] = {}

class ExternalListResponse(BaseModel):
    success: bool = True
    data: List[ExternalAgentInfo]
    total: int

# ── In-memory registry ──

_registry: Dict[str, Dict[str, Any]] = {}

# ── Persistence ──

_REGISTRY_FILE = Path("data/external_registry.json")


def _load_registry():
    """Load persisted external registry."""
    global _registry
    if _REGISTRY_FILE.exists():
        try:
            with open(_REGISTRY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _registry = data
        except Exception as e:
            logger.error(f"Operation failed: {e}")


def _save_registry():
    """Persist external registry."""
    _REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_REGISTRY_FILE, "w", encoding="utf-8") as f:
        json.dump(_registry, f, ensure_ascii=False, indent=2)


# Load on module import
_load_registry()


# ── Helper: Protocol-specific validation ──

def validate_comfyui_config(config: Dict[str, Any]) -> List[str]:
    """Validate ComfyUI-specific config."""
    errors = []
    if "workflow_api_json" in config:
        try:
            if isinstance(config["workflow_api_json"], str):
                json.loads(config["workflow_api_json"])
        except json.JSONDecodeError:
            errors.append("workflow_api_json must be valid JSON")
    return errors


def validate_mcp_config(config: Dict[str, Any]) -> List[str]:
    """Validate MCP-specific config."""
    errors = []
    if "server_command" not in config:
        errors.append("MCP requires 'server_command' in config")
    return errors


def validate_dify_config(config: Dict[str, Any]) -> List[str]:
    """Validate Dify-specific config."""
    errors = []
    if "app_id" not in config:
        errors.append("Dify requires 'app_id' in config")
    return errors


PROTOCOL_VALIDATORS = {
    ExternalProtocol.COMFYUI: validate_comfyui_config,
    ExternalProtocol.MCP: validate_mcp_config,
    ExternalProtocol.DIFY: validate_dify_config,
}


# ── Routes ──

@router.post("/register")
async def register_external(req: ExternalRegisterRequest):
    """Register an external API/Agent.

    Supports:
    - ComfyUI: Register a ComfyUI server as a workflow node executor
    - MCP: Register an MCP (Model Context Protocol) server
    - Dify: Register a Dify app/workflow
    - Webhook: Generic webhook integration
    """
    # Validate protocol-specific config
    if req.protocol in PROTOCOL_VALIDATORS:
        errors = PROTOCOL_VALIDATORS[req.protocol](req.config or {})
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})

    agent_id = f"ext_{req.protocol.value}_{uuid.uuid4().hex[:8]}"

    now = time.strftime("%Y-%m-%dT%H:%M:%S")

    agent_info = {
        "id": agent_id,
        "name": req.name,
        "protocol": req.protocol.value,
        "endpoint": req.endpoint,
        "api_key": req.api_key,
        "description": req.description or "",
        "capabilities": req.capabilities or [],
        "workflow_node_type": req.workflow_node_type or req.protocol.value,
        "config": req.config or {},
        "health_check_path": req.health_check_path or "/health",
        "status": "registered",
        "registered_at": now,
        "last_health_check": None,
    }

    _registry[agent_id] = agent_info
    _save_registry()

    return {
        "success": True,
        "data": agent_info,
        "message": f"External agent '{req.name}' registered as '{agent_id}'",
    }


@router.get("/list")
async def list_externals(
    protocol: Optional[str] = Query(
        None, pattern=r"^(comfyui|mcp|dify|webhook)$",
        description="协议过滤 (comfyui/mcp/dify/webhook)",
    ),
    limit: int = Query(20, ge=1, le=100, description="每页条数 (1..100)"),
    offset: int = Query(0, ge=0, description="跳过条数 (≥0)"),
    sort_by: Optional[str] = Query(
        None, pattern=r"^[a-z_]{1,64}$",
        description="排序字段, 限小写字母+下划线 (1..64 字符)",
    ),
    order: Optional[str] = Query(
        "desc", pattern=r"^(asc|desc)$", description="排序方向: asc|desc",
    ),
    q: Optional[str] = Query(None, max_length=200, description="搜索关键词, ≤200 字符"),
):
    """List all registered external agents (R2.5-W1: Pydantic Query 验证)."""
    agents = list(_registry.values())
    if protocol:
        agents = [a for a in agents if a["protocol"] == protocol]
    if q:
        ql = q.lower()
        agents = [a for a in agents if ql in str(a.get("name", "")).lower() or ql in str(a.get("description", "")).lower()]
    total = len(agents)
    if sort_by:
        agents.sort(
            key=lambda a: a.get(sort_by, "") if isinstance(a, dict) else "",
            reverse=(order == "desc"),
        )
    page = agents[offset: offset + limit]
    return {
        "success": True,
        "data": page,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/protocols")
async def list_protocols():
    """List supported external protocols and their requirements."""
    return {
        "success": True,
        "data": {
            "comfyui": {
                "description": "ComfyUI workflow node executor",
                "required_config": ["workflow_api_json (optional)"],
                "typical_endpoint": "http://localhost:8188",
            },
            "mcp": {
                "description": "Model Context Protocol server",
                "required_config": ["server_command"],
                "typical_endpoint": "stdio:// or http://localhost:PORT",
            },
            "dify": {
                "description": "Dify AI workflow platform",
                "required_config": ["app_id"],
                "typical_endpoint": "https://api.dify.ai/v1",
            },
            "webhook": {
                "description": "Generic webhook integration",
                "required_config": [],
                "typical_endpoint": "https://your-service.com/webhook",
            },
        },
    }


@router.get("/{agent_id}")
async def get_external(agent_id: str):
    """Get a specific external agent by ID."""
    agent = _registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"External agent '{agent_id}' not found")
    return {"success": True, "data": agent}


@router.delete("/{agent_id}")
async def unregister_external(agent_id: str):
    """Unregister an external agent."""
    if agent_id not in _registry:
        raise HTTPException(status_code=404, detail=f"External agent '{agent_id}' not found")
    removed = _registry.pop(agent_id)
    _save_registry()
    return {"success": True, "data": removed, "message": f"Unregistered '{removed['name']}'"}


@router.post("/{agent_id}/health-check")
async def health_check_external(agent_id: str):
    """Perform a health check on a registered external agent."""
    agent = _registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"External agent '{agent_id}' not found")

    import urllib.request
    import urllib.error

    health_url = agent["endpoint"].rstrip("/") + agent.get("health_check_path", "/health")
    headers = {}
    if agent.get("api_key"):
        headers["Authorization"] = f"Bearer {agent['api_key']}"

    try:
        req = urllib.request.Request(health_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = "healthy" if 200 <= resp.status < 300 else "unhealthy"
            agent["status"] = status
    except Exception as e:
        agent["status"] = "unhealthy"
        status = "unhealthy"

    agent["last_health_check"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _registry[agent_id] = agent
    _save_registry()

    return {"success": True, "data": {"agent_id": agent_id, "status": status}}


@router.post("/{agent_id}/invoke")
async def invoke_external(agent_id: str, payload: Dict[str, Any] = Body(...)):
    """Invoke a registered external agent with the given payload.

    For workflow nodes, this is how the workflow engine calls external capabilities.
    """
    agent = _registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"External agent '{agent_id}' not found")

    import urllib.request
    import urllib.error

    endpoint = agent["endpoint"].rstrip("/") + "/invoke"
    headers = {"Content-Type": "application/json"}
    if agent.get("api_key"):
        headers["Authorization"] = f"Bearer {agent['api_key']}"

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_body = resp.read().decode("utf-8")
            return {"success": True, "data": json.loads(response_body) if response_body else {}}
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.reason}", "detail": e.read().decode("utf-8", errors="replace")}
    except Exception as e:
        return {"success": False, "error": str(e)}
