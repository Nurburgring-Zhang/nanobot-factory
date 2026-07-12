"""VDP-2026 R8 — security HTTP routes (PII / rate limit / audit / secrets)."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Body, Query

from .hardening import (
    configure_db, get_audit, get_rate_limiter, get_vault, redact_pii,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/security", tags=["security_r8"])


@router.post("/redact")
async def redact(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    text = str(payload.get("text", ""))
    kinds = payload.get("kinds")
    result = redact_pii(text, kinds=kinds)
    get_audit().append("pii.redact", actor=payload.get("actor", "system"),
                       payload={"input_chars": len(text), "counts": result["counts"]})
    return result


@router.post("/rate-limit/check")
async def rate_check(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    bucket = str(payload.get("bucket", "default"))
    cap = int(payload.get("limit") or 60)
    rl = get_rate_limiter(max_per_min=cap)
    res = rl.check(bucket, max_per_min=cap)
    if not res["allowed"]:
        get_audit().append("ratelimit.deny", actor=payload.get("actor", "system"),
                           payload={"bucket": bucket})
    return res


@router.get("/audit/tail")
async def audit_tail(limit: int = Query(50, ge=1, le=500)) -> Dict[str, Any]:
    return {"items": get_audit().tail(limit=limit)}


@router.get("/audit/verify")
async def audit_verify() -> Dict[str, Any]:
    return get_audit().verify()


@router.post("/audit/append")
async def audit_append(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    et = str(payload.get("event_type", ""))
    if not et:
        raise HTTPException(400, "missing event_type")  # noqa: B904
    ev = get_audit().append(
        event_type=et,
        actor=payload.get("actor", "system"),
        payload=payload.get("payload", {}) or {},
        secret_ref=payload.get("secret_ref", ""),
    )
    return {
        "id": getattr(ev, "id", None),
        "event_type": ev.event_type,
        "actor": ev.actor,
        "hash": ev.hash,
        "prev_hash": ev.prev_hash,
        "created_at": ev.created_at,
    }


@router.get("/secrets")
async def secrets_list() -> Dict[str, Any]:
    return {"names": get_vault().list_names(), "values_redacted": True}


@router.post("/secrets/get")
async def secrets_get(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    name = str(payload.get("name", ""))
    v = get_vault().get(name, actor=payload.get("actor", "system"))
    if v is None:
        raise HTTPException(404, f"未知 secret: {name}")  # noqa: B904
    return {"name": name, "value": v}


@router.post("/secrets/rotate")
async def secrets_rotate(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    name = str(payload.get("name", ""))
    new_value = str(payload.get("value", ""))
    if not name or not new_value:
        raise HTTPException(400, "name and value are required")  # noqa: B904
    ok = get_vault().rotate(name, new_value, actor=payload.get("actor", "system"))
    return {"ok": ok}


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "audit_total": len(get_audit().tail(limit=1000)),
        "audit_verified": get_audit().verify()["verified"],
        "secrets_count": len(get_vault().list_names()),
    }
