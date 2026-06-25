"""P1-8: 公开 Webhook HTTP API 路由."""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .webhooks import (
    SUPPORTED_EVENTS, SIGNATURE_HEADER, WebhookSubscription, EmitRecord,
    register_webhook, list_webhooks, get_webhook, delete_webhook, update_webhook,
    emit, list_emits,
)

router = APIRouter(prefix="/api/v1/public/hooks", tags=["public-webhooks"])


class RegisterWebhookRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=512)
    events: List[str] = Field(..., min_length=1, max_length=20)
    secret: Optional[str] = Field(None, min_length=8, max_length=128)
    metadata: Optional[dict] = None


class UpdateWebhookRequest(BaseModel):
    url: Optional[str] = Field(None, min_length=8, max_length=512)
    events: Optional[List[str]] = None
    active: Optional[bool] = None
    metadata: Optional[dict] = None


class EmitEventRequest(BaseModel):
    event_type: str = Field(..., min_length=3, max_length=64)
    payload: dict


@router.get("/_meta")
def meta():
    return {
        "supported_events": SUPPORTED_EVENTS,
        "signature_header": SIGNATURE_HEADER,
        "max_retry": 3,
    }


@router.post("")
def create(req: RegisterWebhookRequest):
    try:
        h = register_webhook(
            url=req.url, events=req.events,
            secret=req.secret, metadata=req.metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return h.to_dict()


@router.get("")
def list_all(
    active_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
):
    items = list_webhooks(active_only=active_only)
    return {"count": len(items), "items": [h.to_dict() for h in items[:limit]]}


@router.get("/emits")
def list_emits_endpoint(limit: int = Query(50, ge=1, le=200)):
    items = list_emits(limit=limit)
    return {"count": len(items), "items": [e.to_dict() for e in items]}


@router.get("/{hook_id}")
def get_one(hook_id: str):
    h = get_webhook(hook_id)
    if not h:
        raise HTTPException(status_code=404, detail=f"webhook {hook_id!r} not found")
    return h.to_dict()


@router.patch("/{hook_id}")
def update_one(hook_id: str, req: UpdateWebhookRequest):
    h = update_webhook(hook_id, **req.model_dump(exclude_none=True))
    if not h:
        raise HTTPException(status_code=404, detail=f"webhook {hook_id!r} not found")
    return h.to_dict()


@router.delete("/{hook_id}")
def delete_one(hook_id: str):
    ok = delete_webhook(hook_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"webhook {hook_id!r} not found")
    return {"deleted": True, "hook_id": hook_id}


@router.post("/emit")
def emit_event(req: EmitEventRequest):
    """发出事件 (admin/test 用)."""
    if req.event_type not in SUPPORTED_EVENTS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported event_type: {req.event_type!r}. valid: {SUPPORTED_EVENTS}",
        )
    rec = emit(req.event_type, req.payload)
    return rec.to_dict()
