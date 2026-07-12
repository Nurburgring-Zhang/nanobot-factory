"""VDP-2026 R5 — Plugin HTTP routes."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Body

from .manager import PluginManager, get_manager, configure_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])


@router.get("")
async def list_plugins(
    tag: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
) -> Dict[str, Any]:
    m = get_manager()
    items = m.list(tag=tag, status=status, owner=owner, limit=limit)
    return {"total": len(items), "items": [p.to_dict() for p in items]}


@router.post("")
async def register_plugin(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    m = get_manager()
    required = {"id", "name", "version", "owner"}
    missing = required - set(payload.keys())
    if missing:
        raise HTTPException(400, f"missing fields: {sorted(missing)}")  # noqa: B904
    from .manager import Plugin, PluginStatus, TrustLevel
    pl = Plugin(
        id=str(payload["id"]),
        name=str(payload["name"]),
        version=str(payload["version"]),
        owner=str(payload["owner"]),
        description=str(payload.get("description", "")),
        category=str(payload.get("category", "community")),
        manifest=payload.get("manifest", {}) or {},
        capabilities=payload.get("capabilities", []) or [],
        hooks=payload.get("hooks", []) or [],
        tags=payload.get("tags", []) or [],
        status=payload.get("status", PluginStatus.ACTIVE.value),
        trust_level=payload.get("trust_level", TrustLevel.VERIFIED.value),
    )
    pl = m.register(pl)
    return pl.to_dict()


@router.get("/{pid}")
async def get_plugin(pid: str) -> Dict[str, Any]:
    m = get_manager()
    p = m.get(pid)
    if p is None:
        raise HTTPException(404, f"未知插件: {pid}")  # noqa: B904
    return p.to_dict()


@router.post("/{pid}/invoke")
async def invoke_plugin(
    pid: str,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    m = get_manager()
    cap = str(payload.get("capability_id", ""))
    if not cap:
        raise HTTPException(400, "missing capability_id")  # noqa: B904
    try:
        return m.invoke(pid, cap, payload.get("inputs", {}) or {},
                       actor=payload.get("actor", "system"))
    except ValueError as e:
        raise HTTPException(400, str(e))  # noqa: B904


@router.post("/{pid}/enable")
async def enable_plugin(pid: str) -> Dict[str, Any]:
    m = get_manager()
    ok = m.set_status(pid, "active")
    if not ok:
        raise HTTPException(404, f"未知插件: {pid}")  # noqa: B904
    return {"ok": True, "id": pid}


@router.post("/{pid}/disable")
async def disable_plugin(pid: str) -> Dict[str, Any]:
    m = get_manager()
    ok = m.set_status(pid, "disabled")
    if not ok:
        raise HTTPException(404, f"未知插件: {pid}")  # noqa: B904
    return {"ok": True, "id": pid}


@router.get("/_/health")
async def health() -> Dict[str, Any]:
    m = get_manager()
    items = m.list(limit=1000)
    return {
        "status": "ok",
        "plugins_total": len(items),
        "by_status": {
            "active": len([p for p in items if p.status == "active"]),
            "disabled": len([p for p in items if p.status == "disabled"]),
        },
        "by_trust": {
            "verified": len([p for p in items if p.trust_level == "verified"]),
            "official": len([p for p in items if p.trust_level == "official"]),
            "community": len([p for p in items if p.trust_level == "community"]),
        },
    }
