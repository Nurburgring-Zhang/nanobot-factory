"""backend/common/middleware — CORS + request-id middleware (P4-1-W1).

Two middlewares, both small enough to live in their own file:

  * ``RequestIdMiddleware``   — issues / propagates ``X-Request-ID``
  * ``mount_cors``            — convenience wrapper for FastAPI ``CORSMiddleware``

Why split out from ``logging.py``? ``logging.py`` needs the request-id
middleware too, but it imports from here; to avoid the circular import
``middleware`` doesn't import ``logging``.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Per-request id middleware.

    Behaviour:
      * On entry, look for an inbound ``X-Request-ID`` header. If absent,
        generate a random UUID4 hex string.
      * Bind it to the logging contextvar so all log lines during the
        request carry the same id.
      * Echo it back on the response as ``X-Request-ID``.
      * Stamp the request latency on the response as ``X-Response-Time-Ms``.
    """

    HEADER_IN = "X-Request-ID"
    HEADER_OUT = "X-Request-ID"
    HEADER_LATENCY = "X-Response-Time-Ms"

    async def dispatch(self, request: Request, call_next) -> Response:
        # Late import to break the import cycle (logging → middleware → logging)
        from .logging import bind_request_id

        incoming = request.headers.get(self.HEADER_IN)
        rid = bind_request_id(incoming or uuid.uuid4().hex)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # We still want the header on error responses (FastAPI's default
            # 500 handler builds the response). We re-raise and let the
            # exception handler chain add the headers.
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0

        # ``Response`` here may be a streaming response; setting headers
        # after the body is sent is a no-op for some types — that's fine.
        try:
            response.headers[self.HEADER_OUT] = rid
            response.headers[self.HEADER_LATENCY] = f"{elapsed_ms:.2f}"
        except Exception:  # pragma: no cover
            pass
        return response


def mount_cors(
    app: FastAPI,
    *,
    allow_origins: Optional[List[str]] = None,
    allow_credentials: bool = True,
    allow_methods: Optional[List[str]] = None,
    allow_headers: Optional[List[str]] = None,
) -> None:
    """Add CORS middleware. Reads ``CORS_ALLOW_ORIGINS`` env when *allow_origins* is None."""
    origins = allow_origins or [
        o.strip() for o in os.environ.get("CORS_ALLOW_ORIGINS", "*").split(",") if o.strip()
    ] or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods or ["*"],
        allow_headers=allow_headers or ["*"],
    )


def mount_middleware(
    app: FastAPI,
    *,
    service_name: Optional[str] = None,
    enable_request_id: bool = True,
    cors_origins: Optional[List[str]] = None,
) -> None:
    """One-call helper: install request-id + CORS in the right order.

    Order matters: ``RequestIdMiddleware`` is added *inside* so it sits
    closer to the endpoint, which is what most callers expect — the
    request-id will still propagate to logs even if CORS short-circuits
    the request.
    """
    # Mount CORS first so it runs outermost (FastAPI middleware ordering is
    # last-added = outermost).
    mount_cors(app, allow_origins=cors_origins)
    if enable_request_id:
        app.add_middleware(RequestIdMiddleware)


__all__ = [
    "RequestIdMiddleware",
    "mount_cors",
    "mount_middleware",
]