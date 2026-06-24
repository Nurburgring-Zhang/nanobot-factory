"""backend/common — shared library for the 12 microservices (P4-1-W1).

Goal: deduplicate the bootstrap code that each service used to copy-paste:

  * CORS middleware + lifespan scaffolding         → ``middleware.py`` + ``create_app``
  * monitoring endpoints (/healthz/readyz/metrics) → ``health.py`` (refactor of P3-8)
  * JWT authentication / role guards               → ``auth.py``
  * SQLAlchemy session Depends                     → ``db.py`` (delegates to imdf.db)
  * structlog + request-id middleware              → ``logging.py``
  * .env + service config                          → ``config.py``
  * global exception handlers                      → ``error_handler.py``
  * success / error response envelopes             → ``responses.py``

Usage in a service ``main.py``::

    from fastapi import FastAPI
    from common import (
        setup_logging, setup_db, mount_health, mount_middleware,
        register_exception_handlers, service_metadata,
    )

    app = FastAPI(**service_metadata("my_service"))
    setup_logging(app, "my_service")
    setup_db(app)
    mount_middleware(app)              # CORS + request-id
    mount_health(app)                   # /healthz /readyz /metrics
    register_exception_handlers(app)
    app.include_router(my_router)
    # ...

See ``README.md`` for the full guide and migration recipe.
"""
from __future__ import annotations

# Re-export the public surface so ``from common import setup_logging, ...``
# Just Works at the call site.

from .auth import get_current_user, issue_access_token, require_role, require_role_dep
from .config import (
    SERVICE_PORTS,
    ServiceConfig,
    get_service_config,
    load_config,
)
from .db import (
    DB_READY,
    get_db,
    init_db,
    ping,
    setup_db,
)
from .error_handler import BusinessError, register_exception_handlers
from .factory import create_app, service_metadata
from .health import (
    mount_health,
    register_metrics,
)
from .logging import (
    bind_request_id,
    configure_logging,
    get_logger,
    setup_logging,
)
from .middleware import (
    RequestIdMiddleware,
    mount_cors,
    mount_middleware,
)
from .responses import (
    error_response,
    paginated_response,
    success_response,
)

__version__ = "0.1.0"

__all__ = [
    # factory
    "create_app",
    "service_metadata",
    # config
    "ServiceConfig",
    "SERVICE_PORTS",
    "get_service_config",
    "load_config",
    # db
    "get_db",
    "init_db",
    "ping",
    "setup_db",
    "DB_READY",
    # auth
    "get_current_user",
    "require_role",
    "require_role_dep",
    "issue_access_token",
    # logging
    "configure_logging",
    "setup_logging",
    "bind_request_id",
    "get_logger",
    # health / metrics
    "mount_health",
    "register_metrics",
    # middleware
    "RequestIdMiddleware",
    "mount_cors",
    "mount_middleware",
    # error handler
    "BusinessError",
    "register_exception_handlers",
    # responses
    "success_response",
    "error_response",
    "paginated_response",
    # convenience
    "__version__",
]