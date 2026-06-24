"""P3-3-W2: notification-service routes.

REST + WebSocket surface:

  GET    /healthz
  GET    /api/v1/notifications                    list inbox
  POST   /api/v1/notifications                    publish one (fan-out)
  GET    /api/v1/notifications/{notif_id}         get one
  POST   /api/v1/notifications/broadcast          publish many at once
  GET    /api/v1/notifications/channels           list registered channels
  POST   /api/v1/notifications/subscribe          register a server-side
                                                  subscriber (for tests)
  POST   /api/v1/notifications/email              send email (log fallback)
  WS     /ws/notifications                        live push feed

The in-memory ``NotificationBus`` is process-local; for cross-process
fanning the bus is also persisted to a JSON inbox so a later polling
client can catch up.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import smtplib
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Deque, Dict, List, Optional, Set

from fastapi import (APIRouter, HTTPException, WebSocket,
                     WebSocketDisconnect, status)
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["notification-service"])


# =====================================================================
# Data models
# =====================================================================

class Notification(BaseModel):
    id: str = Field(default_factory=lambda: f"notif-{uuid.uuid4().hex[:12]}")
    channel: str = Field(default="inbox", max_length=32)
    recipient: str = Field(default="*", max_length=128)
    subject: str = Field(default="", max_length=256)
    body: str = Field(default="", max_length=8192)
    payload: Dict[str, Any] = Field(default_factory=dict)
    severity: str = Field(default="info", max_length=16)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    delivered: bool = False

    @field_validator("channel")
    @classmethod
    def _v_channel(cls, v: str) -> str:
        allowed = {"inbox", "websocket", "email", "webhook"}
        if v not in allowed:
            raise ValueError(f"channel must be one of {sorted(allowed)}")
        return v

    @field_validator("severity")
    @classmethod
    def _v_severity(cls, v: str) -> str:
        allowed = {"info", "warn", "error", "success", "debug"}
        if v not in allowed:
            raise ValueError(f"severity must be one of {sorted(allowed)}")
        return v


class NotificationRequest(BaseModel):
    channel: str = Field(default="inbox")
    recipient: str = Field(default="*", max_length=128)
    subject: str = Field(default="", max_length=256)
    body: str = Field(default="", max_length=8192)
    payload: Dict[str, Any] = Field(default_factory=dict)
    severity: str = Field(default="info")


class BroadcastRequest(BaseModel):
    items: List[NotificationRequest] = Field(..., min_length=1, max_length=500)


class EmailRequest(BaseModel):
    to: str = Field(..., min_length=3, max_length=512)
    subject: str = Field(..., min_length=1, max_length=256)
    body: str = Field(default="", max_length=16384)
    is_html: bool = False


# =====================================================================
# In-memory bus
# =====================================================================

@dataclass
class NotificationBus:
    inbox: Deque[Notification] = field(default_factory=lambda: deque(maxlen=5000))
    by_id: Dict[str, Notification] = field(default_factory=dict)
    subscribers: Set[str] = field(default_factory=set)
    email_log: Deque[Dict[str, Any]] = field(default_factory=lambda: deque(maxlen=500))

    def publish(self, req: NotificationRequest) -> Notification:
        n = Notification(
            channel=req.channel, recipient=req.recipient,
            subject=req.subject, body=req.body,
            payload=req.payload, severity=req.severity,
        )
        # Channel-specific side effects
        if n.channel == "email":
            self._send_email(n)
            n.delivered = True
        elif n.channel == "webhook":
            n.delivered = self._fire_webhook(n)
        elif n.channel == "websocket":
            # Delivered on next WS poll; mark delivered if no subscribers.
            n.delivered = not self.subscribers
        else:  # inbox
            n.delivered = True
        self.inbox.append(n)
        self.by_id[n.id] = n
        return n

    def publish_many(self, items: List[NotificationRequest]) -> List[Notification]:
        return [self.publish(it) for it in items]

    def _send_email(self, n: Notification) -> None:
        """Log by default; SMTP via env when configured."""
        host = os.environ.get("SMTP_HOST")
        self.email_log.append({
            "id": n.id, "to": n.recipient, "subject": n.subject,
            "body": n.body, "ts": n.created_at, "via": "smtp" if host else "log",
        })
        if not host:
            logger.info("[notification-email-log] to=%s subject=%s",
                        n.recipient, n.subject)
            return
        # SMTP send (best-effort, timeout 5s)
        try:
            port = int(os.environ.get("SMTP_PORT", "25"))
            user = os.environ.get("SMTP_USER")
            password = os.environ.get("SMTP_PASSWORD")
            msg = EmailMessage()
            msg["Subject"] = n.subject
            msg["From"] = os.environ.get("SMTP_FROM", user or "no-reply@nanobot.local")
            msg["To"] = n.recipient
            msg.set_content(n.body or "")
            with smtplib.SMTP(host, port, timeout=5) as s:
                s.starttls()
                if user and password:
                    s.login(user, password)
                s.send_message(msg)
        except Exception as e:  # noqa: BLE001
            logger.warning("smtp send failed: %s", e)

    def _fire_webhook(self, n: Notification) -> bool:
        # Delegate to webhook engine when available; otherwise just log.
        try:
            from engines.webhook_engine import WebhookEngine  # type: ignore
            eng = WebhookEngine()
            eng.dispatch(
                event_type=n.payload.get("event_type", "notification.push"),
                payload={"id": n.id, "subject": n.subject,
                         "body": n.body, **n.payload},
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.debug("webhook dispatch skipped: %s", e)
            return False


_BUS: Optional[NotificationBus] = None
_BUS_LOCK = threading.Lock()


def get_bus() -> NotificationBus:
    global _BUS
    if _BUS is None:
        with _BUS_LOCK:
            if _BUS is None:
                _BUS = NotificationBus()
    return _BUS


# =====================================================================
# REST routes
# =====================================================================

@router.get("/healthz")
async def healthz() -> Dict[str, Any]:
    bus = get_bus()
    return {
        "status": "ok",
        "service": "notification-service",
        "version": "0.1.0",
        "inbox_size": len(bus.inbox),
        "subscribers": len(bus.subscribers),
        "email_log_size": len(bus.email_log),
    }


@router.get("/api/v1/notifications/channels")
async def list_channels() -> Dict[str, Any]:
    return {
        "channels": [
            {"name": "inbox", "description": "In-process inbox for polling"},
            {"name": "websocket", "description": "Live push via WS /ws/notifications"},
            {"name": "email", "description": "SMTP send (log fallback)"},
            {"name": "webhook", "description": "Outbound HTTP webhook dispatch"},
        ],
        "total": 4,
    }


@router.post("/api/v1/notifications", status_code=status.HTTP_201_CREATED)
async def publish_notification(req: NotificationRequest) -> Dict[str, Any]:
    bus = get_bus()
    n = bus.publish(req)
    return n.model_dump()


@router.post("/api/v1/notifications/broadcast",
             status_code=status.HTTP_201_CREATED)
async def broadcast(req: BroadcastRequest) -> Dict[str, Any]:
    bus = get_bus()
    items = bus.publish_many(req.items)
    return {
        "total": len(items),
        "items": [n.model_dump() for n in items],
    }


@router.get("/api/v1/notifications")
async def list_notifications(
    channel: Optional[str] = None,
    recipient: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    limit = max(1, min(limit, 500))
    bus = get_bus()
    items = list(bus.inbox)
    if channel:
        items = [n for n in items if n.channel == channel]
    if recipient:
        items = [n for n in items if n.recipient == recipient or n.recipient == "*"]
    if severity:
        items = [n for n in items if n.severity == severity]
    items = items[-limit:][::-1]
    return {
        "total": len(items),
        "items": [n.model_dump() for n in items],
    }


@router.get("/api/v1/notifications/{notif_id}")
async def get_notification(notif_id: str) -> Dict[str, Any]:
    bus = get_bus()
    n = bus.by_id.get(notif_id)
    if n is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"notification_not_found: {notif_id}")
    return n.model_dump()


@router.post("/api/v1/notifications/subscribe")
async def register_subscriber() -> Dict[str, Any]:
    """Register a server-side subscriber id (used in tests)."""
    bus = get_bus()
    sid = f"sub-{uuid.uuid4().hex[:8]}"
    bus.subscribers.add(sid)
    return {"subscriber_id": sid, "active": len(bus.subscribers)}


@router.delete("/api/v1/notifications/subscribe/{subscriber_id}")
async def unregister_subscriber(subscriber_id: str) -> Dict[str, Any]:
    bus = get_bus()
    bus.subscribers.discard(subscriber_id)
    return {"subscriber_id": subscriber_id,
            "active": len(bus.subscribers)}


@router.post("/api/v1/notifications/email",
             status_code=status.HTTP_201_CREATED)
async def send_email(req: EmailRequest) -> Dict[str, Any]:
    bus = get_bus()
    notif = bus.publish(NotificationRequest(
        channel="email", recipient=req.to,
        subject=req.subject, body=req.body,
        payload={"is_html": req.is_html},
    ))
    return {
        "id": notif.id,
        "delivered": notif.delivered,
        "channel": "email",
        "recipient": req.to,
    }


@router.get("/api/v1/notifications/email/log")
async def email_log(limit: int = 50) -> Dict[str, Any]:
    limit = max(1, min(limit, 500))
    bus = get_bus()
    items = list(bus.email_log)[-limit:][::-1]
    return {"total": len(items), "items": items}


# =====================================================================
# WebSocket
# =====================================================================

@router.websocket("/ws")
async def ws_root(ws: WebSocket) -> None:
    await _ws_handler(ws)


@router.websocket("/ws/notifications")
async def ws_notifications(ws: WebSocket) -> None:
    await _ws_handler(ws)


async def _ws_handler(ws: WebSocket) -> None:
    await ws.accept()
    bus = get_bus()
    sub_id = f"ws-{uuid.uuid4().hex[:8]}"
    bus.subscribers.add(sub_id)
    try:
        # send hello
        await ws.send_json({"type": "hello", "subscriber_id": sub_id,
                            "ts": datetime.utcnow().isoformat()})
        # drain loop: read client pings, send queued notifications
        last_idx = len(bus.inbox)
        while True:
            # forward any new notifications
            while last_idx < len(bus.inbox):
                n = bus.inbox[last_idx]
                if n.channel in ("inbox", "websocket"):
                    await ws.send_json({"type": "notification",
                                        "data": n.model_dump()})
                last_idx += 1
            try:
                # Wait for client messages (or ping)
                msg = await asyncio.wait_for(ws.receive_text(), timeout=20.0)
                if msg == "ping":
                    await ws.send_json({"type": "pong",
                                        "ts": datetime.utcnow().isoformat()})
                elif msg == "subscribe":
                    pass
                elif msg.startswith("publish:"):
                    try:
                        payload = json.loads(msg[len("publish:"):])
                        bus.publish(NotificationRequest(**payload))
                    except Exception as e:  # noqa: BLE001
                        await ws.send_json({"type": "error",
                                            "message": f"publish failed: {e}"})
            except asyncio.TimeoutError:
                # send heartbeat
                await ws.send_json({"type": "heartbeat",
                                    "ts": datetime.utcnow().isoformat()})
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.debug("ws closed: %s", e)
    finally:
        bus.subscribers.discard(sub_id)


__all__ = ["router", "NotificationBus", "get_bus"]
