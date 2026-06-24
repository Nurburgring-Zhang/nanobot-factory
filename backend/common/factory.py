"""backend/common/factory — ``create_app`` convenience factory (P4-1-W1).

The 12 service ``main.py`` files all opened with the same six lines:

    import os, sys, pathlib
    _BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
    if str(_BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(_BACKEND_ROOT))

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="...-service", description="...", version="0.1.0")

This module collapses that boilerplate into a single call::

    app = create_app("user_service", description="User / auth / role BC")

The factory:
  * Inserts the backend root into ``sys.path`` so ``imdf.*`` imports work.
  * Builds a :class:`fastapi.FastAPI` with sensible defaults.
  * Wires structlog + request-id middleware (``setup_logging``).
  * Wires CORS middleware (``mount_cors``).
  * Does **not** mount ``/healthz``/``/readyz``/``/metrics`` — those are
    still service-local decisions (you might want a different ``/readyz``
    body), but ``mount_health(app)`` is one line away.
  * Does **not** register exception handlers — call
    ``register_exception_handlers(app)`` after mounting routers.
"""
from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI

from .config import SERVICE_PORTS, get_service_config
from .logging import setup_logging
from .middleware import mount_cors


def _ensure_backend_on_path() -> None:
    """Make ``backend/`` importable so ``imdf.*`` / ``services.*`` resolve."""
    # backend/common/factory.py → backend/
    backend_root = Path(__file__).resolve().parent.parent
    backend_root_str = str(backend_root)
    if backend_root_str not in sys.path:
        sys.path.insert(0, backend_root_str)


def service_metadata(
    service_name: str,
    *,
    description: Optional[str] = None,
    version: str = "0.1.0",
) -> Dict[str, Any]:
    """Return the dict you would pass to ``FastAPI(**service_metadata(...))``."""
    title = f"Nanobot Factory — {service_name}"
    cfg = get_service_config(service_name)
    return {
        "title": title,
        "description": description or f"{service_name} (P4-1-W1)",
        "version": version,
        "contact": {"name": "Nanobot Factory Platform Team"},
    }


def create_app(
    service_name: str,
    *,
    description: Optional[str] = None,
    version: str = "0.1.0",
    lifespan: Optional[Any] = None,
    enable_cors: bool = True,
    enable_logging: bool = True,
    cors_origins: Optional[list] = None,
) -> FastAPI:
    """Build a :class:`FastAPI` with the standard middleware wired in.

    Defaults match what the legacy services had:
      * CORS open (``*``) — tighten via ``CORS_ALLOW_ORIGINS`` env.
      * structlog + request-id middleware mounted.

    The caller is still responsible for ``include_router``, ``mount_health``,
    and ``register_exception_handlers``.
    """
    _ensure_backend_on_path()
    cfg = get_service_config(service_name)

    if lifespan is None:
        @asynccontextmanager
        async def _default_lifespan(app: FastAPI):
            yield

        lifespan = _default_lifespan

    app = FastAPI(
        title=f"Nanobot Factory — {service_name}",
        description=description or f"{service_name} (P4-1-W1)",
        version=version,
        lifespan=lifespan,
    )

    # Stash the service name for downstream helpers
    app.state.service_name = service_name
    app.state.service_config = cfg

    # Logging / CORS — order matters: CORS first (outermost), request-id inside.
    if enable_cors:
        mount_cors(app, allow_origins=cors_origins, allow_credentials=cfg.cors_allow_credentials)
    if enable_logging:
        setup_logging(app, service_name, level=cfg.log_level)

    return app


__all__ = [
    "create_app",
    "service_metadata",
    "SERVICE_PORTS",
]