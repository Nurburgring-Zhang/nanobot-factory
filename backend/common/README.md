# backend/common — shared library for the 12 microservices (P4-1-W1)

A single Python package that every microservice under
``backend/services/<name>/`` imports. The 12 services used to copy-paste
~30 lines of identical bootstrap (sys.path bootstrap, CORS middleware,
monitoring endpoints, FastAPI constructor boilerplate). After this
package landed, each ``main.py`` dropped that duplication and the
import graph is uniform across the fleet.

## What's inside

| Module                  | What it provides                                                |
| ----------------------- | --------------------------------------------------------------- |
| ``common.config``       | ServiceConfig dataclass, SERVICE_PORTS table, .env loader       |
| ``common.logging``      | structlog + stdlib fallback, ``request_id`` contextvar          |
| ``common.middleware``   | RequestIdMiddleware, mount_cors, mount_middleware               |
| ``common.db``           | SQLAlchemy ``get_db`` Depends, ``setup_db``, ``ping``           |
| ``common.auth``         | JWT ``get_current_user``, ``require_role_dep``, ``issue_access_token`` |
| ``common.health``       | ``mount_health`` (``/healthz``, ``/readyz``, ``/metrics``)      |
| ``common.error_handler``| Uniform error envelopes + ``BusinessError``                     |
| ``common.responses``    | ``success_response``, ``error_response``, ``paginated_response`` |
| ``common.factory``      | ``create_app`` one-liner                                       |

The ``common`` namespace re-exports the public surface, so a service
typically needs only one import::

    from common import create_app, mount_health, register_exception_handlers

## 1-minute migration guide

**Before** (~30 lines of boilerplate per service):

```python
import os, sys
from contextlib import asynccontextmanager
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ... legacy router imports ...

@asynccontextmanager
async def lifespan(app):
    yield

app = FastAPI(title="Nanobot Factory — user-service", version="0.1.0", lifespan=lifespan)

try:
    from imdf.monitoring import quick_setup
    quick_setup(app, "user_service")
except Exception:
    pass

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], ...)
```

**After**:

```python
from common import create_app, mount_health, register_exception_handlers

@asynccontextmanager
async def lifespan(app):
    yield

app = create_app("user_service", description="...", version="0.1.0", lifespan=lifespan)
mount_health(app)
register_exception_handlers(app)
```

That's it — the rest of the file (routers, legacy imports, root
endpoint) is unchanged.

## Standard skeleton

```python
"""P3-X-WY: my-service FastAPI app."""
from __future__ import annotations

# P4-1-W1: migrated to backend.common
from common import create_app, mount_health, register_exception_handlers

from contextlib import asynccontextmanager
from fastapi import FastAPI

from services.my_service.routes import router as my_router

# Optional legacy routers — wrap in try/except so the service still boots
# when imdf.api.<X> is unavailable.
try:
    from imdf.api.legacy_X import router as legacy_router
except Exception:
    legacy_router = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Touch any singletons that need to boot here
    yield


app = create_app("my_service", description="...", version="0.1.0", lifespan=lifespan)
mount_health(app)
register_exception_handlers(app)

if legacy_router is not None:
    app.include_router(legacy_router)

app.include_router(my_router)


@app.get("/")
async def root():
    return {"service": "my-service", "version": "0.1.0"}


__all__ = ["app"]
```

## Configuration (env vars)

The shared library reads (in order): ``.env`` → ``os.environ`` → default.

| Variable                       | Default                              | Notes                                 |
| ------------------------------ | ------------------------------------ | ------------------------------------- |
| ``IMDF_WEB_HOST``              | ``0.0.0.0``                          | Bind host                             |
| ``SERVICE_PORT``               | ``SERVICE_PORTS[service_name]``      | Per-service port (8001-8012)          |
| ``LOG_LEVEL``                  | ``INFO``                             | structlog + stdlib log level          |
| ``IMDF_DEBUG``                 | ``false``                            | Verbose error envelopes               |
| ``CORS_ALLOW_ORIGINS``         | ``*``                                | Comma-separated                       |
| ``JWT_SECRET``                 | dev-only auto-secret                 | Required in prod; raise if missing    |
| ``JWT_ALGORITHM``              | ``HS256``                            | Symmetric for now                     |
| ``IMDF_P2_DB_URL`` / ``DATABASE_URL`` | ``sqlite:///backend/data/imdf_p2.db`` | SQLAlchemy URL                    |
| ``IMDF_DATA_DIR``              | ``backend/data``                     | Where SQLite files land               |
| ``IMDF_LOGS_DIR``              | ``backend/logs``                     | Log dir                               |
| ``IMDF_TEST_MODE``             | unset                                | Set to ``1`` to enable dev shortcuts  |
| ``METRICS_ENABLED``            | ``true``                             | Disable per service if needed        |

## Health endpoints

Every service that calls ``mount_health(app)`` exposes:

* ``GET /healthz`` — process liveness. Always 200 when the worker is up.
* ``GET /readyz`` — readiness probe; 200 with ``{"ready": true, "db": true}``
  when ``common.db.ping()`` succeeds, else 503.
* ``GET /metrics`` — Prometheus text exposition. Tries
  ``imdf.monitoring.ServiceMetrics.render`` first; falls back to a
  lightweight in-process counter.

Override the paths via::

    mount_health(app, health_path="/live", ready_path="/ready", metrics_path="/_metrics")

## Authentication

The ``get_current_user`` dependency decodes ``Authorization: Bearer
<jwt>``, resolves the user from ``imdf/db`` (or ``IMDF_TEST_USERS`` env
in dev), and returns::

    {"username": "...", "role": "...", "enabled": True, "payload": {...}}

To require a specific role::

    from common import require_role_dep

    @router.delete("/api/v1/users/{u}")
    def delete_user(u: str, user=Depends(require_role_dep("admin"))):
        ...

For tests/dev, ``IMDF_TEST_MODE=1`` lets you skip the JWT and pass
``X-User: alice`` instead. ``issue_access_token(username, role)`` mints a
short-lived JWT for unit tests.

## Error envelopes

All errors flowing through ``register_exception_handlers(app)`` are
serialized as::

    {
      "success": false,
      "error": {
        "code": "item_not_found",
        "message": "Item 42 missing",
        "status_code": 404,
        "request_id": "abc...",
        "details": {"item_id": 42}
      }
    }

Raise ``BusinessError(code, message, status_code, details=...)`` to get
this shape without touching ``HTTPException`` directly.

For success responses, return ``success_response(data)`` /
``error_response(code, message, status_code, details=...)` from
``common.responses``. Pagination helper: ``paginated_response(items,
total, page=1, page_size=20)``.

## What's *not* in common (deliberately)

* **Service-specific business logic** — stays in ``services/<name>/``.
* **Routers / endpoints** — service-local; only the bootstrap is shared.
* **Legacy ``imdf.api`` routers** — each service mounts its own subset
  inside a ``try/except`` block. We deliberately don't wrap them in a
  helper because the import lists differ per service.
* **The CORS allow-list policy** — each service can override at
  ``create_app(cors_origins=[...])`` time.

## Tests

``backend/tests/test_common.py`` covers:

* 65 test cases across the 9 modules
* 12-service TestClient smoke for ``/healthz /readyz /metrics``
* Per-service ``main.py`` reduction invariants (no leftover sys.path
  bootstrap, no leftover ``CORSMiddleware``, no leftover
  ``quick_setup``)
* Aggregate line-count reduction assertion

Run::

    pytest backend/tests/test_common.py -v