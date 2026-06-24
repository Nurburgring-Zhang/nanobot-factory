"""P3-3-W2: notification-service FastAPI app (port 8010).

In-process notification bus + WebSocket fan-out + email/webhook send.
Reuses the Webhook engine from ``imdf.engines.webhook_engine`` for
outbound HTTP and adds:

  * In-memory pub/sub for server-sent push (WebSocket /ws)
  * REST surface: POST /api/v1/notifications + GET inbox + GET channels
  * Email send (logs by default; SMTP optional via env)
"""

# P4-1-W1: refactored — see backend/common/ for the shared library.
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.notification_service.routes import router as notification_router

# Legacy webhook router from the monolith
try:
    from imdf.api.webhook_routes import router as legacy_webhook_router  # type: ignore
    HAS_LEGACY = True
except Exception:  # noqa: BLE001
    HAS_LEGACY = False
    legacy_webhook_router = None
    import logging
    logging.getLogger(__name__).warning("legacy webhook_routes unavailable")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise the in-memory bus singleton
    try:
        from services.notification_service.routes import get_bus  # noqa: F401
        get_bus()
    except Exception:  # noqa: BLE001
        pass
    yield

app = create_app(
    "notification_service",
    description='WebSocket / email / webhook fan-out (P3-3-W2)',
    version='0.1.0',
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

if HAS_LEGACY and legacy_webhook_router is not None:
    app.include_router(legacy_webhook_router)

app.include_router(notification_router)

@app.get("/")
async def root():
    from services.notification_service.routes import get_bus
    bus = get_bus()
    return {
        "service": "notification-service",
        "version": "0.1.0",
        "port": 8010,
        "inbox_size": len(bus.inbox),
        "active_subscribers": len(bus.subscribers),
        "channels": ["websocket", "email", "webhook", "inbox"],
        "endpoints": {
            "post": ["/api/v1/notifications"],
            "list": ["/api/v1/notifications", "/api/v1/notifications/{id}"],
            "channels": ["/api/v1/notifications/channels"],
            "subscribe": ["/api/v1/notifications/subscribe"],
            "websocket": ["/ws/notifications", "/ws"],
            "healthz": ["/healthz"],
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="notification_service",
        adapter=MultimodalAdapter(service_id="notification_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for notification_service: %%s", _mm_err)


__all__ = ["app"]
