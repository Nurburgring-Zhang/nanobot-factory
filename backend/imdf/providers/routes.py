"""VDP-2026 R6 — Provider registry HTTP routes."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Body

from .registry import (
    ProviderRegistry, Provider, get_registry, configure_db, ProviderFamily,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/providers", tags=["providers"])


@router.get("")
async def list_providers(
    family: Optional[str] = Query(None),
) -> Dict[str, Any]:
    r = get_registry()
    items = r.list() if not family else r.by_family(family)
    return {"total": len(items), "items": [p.to_dict() for p in items]}


@router.post("")
async def upsert_provider(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    r = get_registry()
    required = {"id", "name", "family", "default_model"}
    missing = required - set(payload.keys())
    if missing:
        raise HTTPException(400, f"missing fields: {sorted(missing)}")  # noqa: B904
    p = Provider(
        id=str(payload["id"]), name=str(payload["name"]),
        family=str(payload["family"]), default_model=str(payload["default_model"]),
        api_base=payload.get("api_base", ""),
        price_per_1k_input=float(payload.get("price_per_1k_input", 0)),
        price_per_1k_output=float(payload.get("price_per_1k_output", 0)),
        quota_per_minute=int(payload.get("quota_per_minute", 60)),
        latency_p50_ms=int(payload.get("latency_p50_ms", 1000)),
        latency_p99_ms=int(payload.get("latency_p99_ms", 3000)),
        trust_level=payload.get("trust_level", "verified"),
        status=payload.get("status", "active"),
        config=payload.get("config", {}) or {},
    )
    r.upsert(p)
    return p.to_dict()


@router.post("/route")
async def route(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    r = get_registry()
    family = str(payload.get("family", "openai"))
    prefer = str(payload.get("prefer", "cost"))
    p = r.route(family=family, prefer=prefer, exclude=payload.get("exclude") or [])
    if p is None:
        raise HTTPException(404, f"无可用 provider: family={family}")  # noqa: B904
    return p.to_dict()


@router.get("/{pid}")
async def get_provider(pid: str) -> Dict[str, Any]:
    r = get_registry()
    p = r.get(pid)
    if p is None:
        raise HTTPException(404, f"未知 provider: {pid}")  # noqa: B904
    return p.to_dict()


@router.get("/_/summary")
async def call_summary() -> Dict[str, Any]:
    r = get_registry()
    return r.call_summary()


@router.post("/{pid}/record")
async def record_call(
    pid: str,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    r = get_registry()
    if r.get(pid) is None:
        raise HTTPException(404, f"未知 provider: {pid}")  # noqa: B904
    r.record_call(
        provider_id=pid,
        model=str(payload.get("model", "")),
        input_tokens=int(payload.get("input_tokens", 0)),
        output_tokens=int(payload.get("output_tokens", 0)),
        latency_ms=int(payload.get("latency_ms", 0)),
        status=str(payload.get("status", "success")),
    )
    return {"ok": True}
