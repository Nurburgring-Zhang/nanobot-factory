"""P3-2-W1: user-service FastAPI app (port 8001).

Wraps the original auth/admin/personnel routers from imdf.api and adds a
new /api/v1/users + /api/v1/roles REST surface.
"""

# P4-1-W1: refactored — see backend/common/ for the shared library.
from __future__ import annotations

# P4-1-W1: migrated to backend.common (auth/db/logging/config/health/metrics/middleware)
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from services.user_service.routes import router as user_router

# Mount the original routers so the existing API surface is preserved
# (gateway / older clients may still hit /auth/*, /api/admin/*, /api/stats/*).
try:
    from imdf.api.auth_routes import router as legacy_auth_router
    from imdf.api.admin_routes import router as legacy_admin_router
    from imdf.api.personnel_routes import router as legacy_personnel_router
    HAS_LEGACY = True
except Exception as e:  # noqa: BLE001
    HAS_LEGACY = False
    legacy_auth_router = legacy_admin_router = legacy_personnel_router = None
    import logging
    logging.getLogger(__name__).warning("legacy routers unavailable: %s", e)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = create_app(
    "user_service",
    description='User / auth / role bounded context (P3-2-W1)',
    version='0.1.0',
    lifespan=lifespan,
)
mount_health(app)
register_exception_handlers(app)

# CORS — keep open in dev; tighten in prod via env

# 1) legacy routers (preserve /auth/*, /api/admin/*, /api/stats/personnel/*)
if HAS_LEGACY and legacy_auth_router is not None:
    app.include_router(legacy_auth_router)
if HAS_LEGACY and legacy_admin_router is not None:
    app.include_router(legacy_admin_router)
if HAS_LEGACY and legacy_personnel_router is not None:
    app.include_router(legacy_personnel_router)

# 2) new /api/v1/users + /api/v1/roles surface
app.include_router(user_router)

@app.get("/")
async def root():
    return {
        "service": "user-service",
        "version": "0.1.0",
        "endpoints": {
            "auth": ["/auth/login", "/auth/me", "/auth/refresh"],
            "admin": ["/api/admin/users", "/api/admin/stats"],
            "users": ["/api/v1/users", "/api/v1/users/{username}"],
            "roles": ["/api/v1/roles", "/api/v1/roles/permissions"],
        },
    }


# P4-7-W1: multimodal adapter (6 input modalities / 3 output kinds)
try:
    from common.multimodal_adapter import (
        MultimodalAdapter, build_multimodal_router,
    )
    app.include_router(build_multimodal_router(
        service_id="user_service",
        adapter=MultimodalAdapter(service_id="user_service"),
    ))
except Exception as _mm_err:  # noqa: BLE001
    import logging as _mm_log
    _mm_log.getLogger(__name__).warning(
        "multimodal mount skipped for user_service: %%s", _mm_err)


__all__ = ["app"]
